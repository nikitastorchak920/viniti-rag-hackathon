"""Per-document extraction: meta pass + page-window result passes, cached incrementally."""
from __future__ import annotations

import pathlib
import re
import time

from core.llm_client import GeminiClient, LLMError, TruncatedResponseError, load_cache, log, save_cache
from core.pdf_processor import inspect_pdf
from plugins.rag.prompts import META_USER, SYSTEM, verify_user, window_user

CACHE_VERSION = 2


def _gen(client, contents, schema, tag: str) -> dict:
    """generate_json + strict validation (coerces "3"->3, "false"->False). Never returns unvalidated data."""
    from pydantic import ValidationError

    last = ""
    for _ in range(3):
        data = client.generate_json(contents, SYSTEM, schema, tag=tag)
        try:
            return schema.model_validate(data).model_dump()
        except ValidationError as exc:
            last = str(exc).splitlines()[0][:200] + " " + (str(exc.errors()[0].get("loc")) if exc.errors() else "")
            log(f"  [{tag}] schema validation failed ({last}); retrying")
    raise LLMError(f"model output failed schema validation 3x: {last}")


OVERLAP = 4  # lines shared by the two halves of a split page (keeps table header / context)


CAPTION = re.compile(r"(?i)^\s*(table|tab\.|figure|fig\.)\s*[A-Z]?\d+")
COLHEAD = re.compile(r"(?i)\b(method|model|dataset|metric|setting|config\w*|EM|F1|recall|precision|accuracy|MRR|nDCG)\b.*\b(EM|F1|recall|precision|accuracy|MRR|nDCG|score|avg|average)\b")
HDR_MARK, HDR_END = "[TABLE HEADER CONTEXT - do not extract values from these lines]", "[END HEADER CONTEXT]"
HEADER_LINES = 4


def _header(lines: list[str], idx: int) -> list[str]:
    """Table caption + column-header lines found above split index idx (empty if none or already in the overlap)."""
    for i in range(idx - 1, -1, -1):
        if lines[i] in (HDR_MARK, HDR_END):
            continue
        if CAPTION.match(lines[i]) or (COLHEAD.search(lines[i]) and not re.search(r"\d+\.\d", lines[i])):
            for j in range(i - 1, max(-1, i - 4), -1):  # caption just above the column-header line
                if CAPTION.match(lines[j]):
                    i = j
                    break
            if i >= idx - OVERLAP:
                return []
            out = []
            for x in lines[i:min(i + HEADER_LINES, idx - OVERLAP)]:
                if x in (HDR_MARK, HDR_END) or (out and re.search(r"\d+\.\d", x)):  # stop at first data row
                    break
                out.append(x)
            return out
    return []


def _dedupe(rows: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in rows:
        k = (r.get("config_id"), r.get("dataset_id"), r.get("metric_name"), r.get("raw_value"), r.get("source_fragment"))
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def _part(client, contents_fn, meta: dict, page: int, lines: list[str], doc_id: str, depth: int = 0) -> list[dict]:
    """One page, or a slice of its lines. On truncation split the lines in half (with overlap), recursively."""
    from plugins.rag.schemas import Window

    tag = f"{doc_id}:{page}-{page}" + (f"/L{len(lines)}" if depth else "")
    try:
        text = f"--- PAGE {page} ---\n" + "\n".join(lines)
        data = _gen(client, contents_fn(window_user(meta, page, page, part=depth > 0), page, page, text), Window, tag)
        return data["results"]
    except TruncatedResponseError:
        if len([x for x in lines if x not in (HDR_MARK, HDR_END)]) < 2 * OVERLAP + 2 or depth >= 8:
            raise
        mid = len(lines) // 2
        log(f"  [{doc_id}] page {page} still truncated ({len(lines)} lines): splitting by lines")
        a = _part(client, contents_fn, meta, page, lines[:mid + OVERLAP], doc_id, depth + 1)
        low = lines[mid - OVERLAP:]
        hdr = _header(lines, mid - OVERLAP)
        if hdr and HDR_MARK not in low:
            low = [HDR_MARK, *hdr, HDR_END, *low]
        b = _part(client, contents_fn, meta, page, low, doc_id, depth + 1)
        return _dedupe(a + b)


def _window(client, contents_fn, meta: dict, first: int, last: int, doc_id: str, page_text_fn=None) -> dict:
    """Extract pages first..last; on truncation halve the page range, then (single page) halve its lines."""
    from plugins.rag.schemas import Window

    try:
        return _gen(client, contents_fn(window_user(meta, first, last), first, last, None), Window, f"{doc_id}:{first}-{last}")
    except TruncatedResponseError:
        if first >= last:
            text = page_text_fn(first) if page_text_fn else None
            if not text or not text.strip():
                raise  # PDF/multimodal mode or empty text layer: cannot split text
            rows = _part(client, contents_fn, meta, first, text.strip().splitlines(), doc_id, depth=1)
            for r in rows:
                r["source_page"] = first
            return {"results": rows}
        mid = (first + last) // 2
        log(f"  [{doc_id}] truncated at pages {first}-{last}: splitting into {first}-{mid} and {mid + 1}-{last}")
        a = _window(client, contents_fn, meta, first, mid, doc_id, page_text_fn)
        b = _window(client, contents_fn, meta, mid + 1, last, doc_id, page_text_fn)
        return {"results": a["results"] + b["results"]}


NUM_TOKEN = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?%?(?![\w])")


def select_verify_pages(pages: list[str], cache: dict, min_numbers: int = 40, min_rows_ratio: float = 0.5) -> list[int]:
    """Pages worth a second look: dense numeric pages (tables), or pages whose extraction looks thin
    (fewer rows than numbers/ratio) or has quotes absent from the text layer."""
    from plugins.rag.exporter import norm

    rows_by_page: dict[int, list[dict]] = {}
    for w in cache.get("windows", {}).values():
        for r in w.get("results", []):
            try:
                rows_by_page.setdefault(int(r.get("source_page")), []).append(r)
            except (TypeError, ValueError):
                pass
    out = []
    for n, text in enumerate(pages, 1):
        dens = len(NUM_TOKEN.findall(text))
        rows = rows_by_page.get(n, [])
        pn = norm(text)
        unverified = sum(1 for r in rows if r.get("source_fragment") and norm(r["source_fragment"]) not in pn)
        if (dens >= min_numbers and len(rows) < dens * min_rows_ratio) or unverified:
            out.append(n)
    return out


def verify_pass(pdf: pathlib.Path, client, cache_dir: pathlib.Path, max_pages: int = 25) -> tuple[bool, str]:
    """Optional second LLM audit of dense pages; recovered rows go to cache['verify'][page] (idempotent,
    resumable). Text mode only. Never touches the first-pass windows."""
    doc_id = pdf.stem
    cache = load_cache(cache_dir, doc_id)
    if not cache.get("complete") or cache.get("mode") != "text" or not cache.get("meta", {}).get("publication", {}).get("in_scope"):
        return True, "verify skipped (no complete text-mode in-scope cache)"
    if client is None:
        return False, "no LLM client for --verify-pass"
    from plugins.rag.schemas import Window

    info = inspect_pdf(pdf)
    cache.setdefault("verify", {})
    todo = [p for p in select_verify_pages(info.pages, cache) if str(p) not in cache["verify"]][:max_pages]
    added = 0
    try:
        for p in todo:
            existing = [f"{r.get('config_id')}|{r.get('dataset_id')}|{r.get('metric_name')}|{r.get('raw_value')}|{r.get('result_origin')}"
                        for w in cache["windows"].values() for r in w.get("results", []) if str(r.get("source_page")) == str(p)]
            contents = ["PAPER TEXT (page markers are PDF page numbers):\n\n" + info.marked_text(p, p),
                        verify_user(cache["meta"], p, existing)]
            log(f"  [{doc_id}] verify pass page {p}")
            res = _gen(client, contents, Window, f"{doc_id}:verify{p}")
            for r in res["results"]:
                r["source_page"] = p
            cache["verify"][str(p)] = {"results": res["results"]}
            added += len(res["results"])
            save_cache(cache_dir, doc_id, cache)
    except LLMError as exc:
        return False, f"{exc} (verify progress kept)"
    return True, f"verified {len(todo)} pages, +{added} rows"


def process_document(pdf: pathlib.Path, client: GeminiClient | None, cache_dir: pathlib.Path, force: bool,
                     window: int, pdf_mode: str, skip_scans: bool = False) -> tuple[bool | None, str]:
    """Return (ok, message). Only successful model responses are cached; a document is
    'complete' only when the meta pass and every page window succeeded."""
    doc_id = pdf.stem
    t0 = time.time()
    cache = {} if force else load_cache(cache_dir, doc_id)
    if cache.get("version") != CACHE_VERSION:
        cache = {}
    if cache.get("complete"):
        return True, "cached"
    try:
        info = inspect_pdf(pdf)
    except Exception as exc:  # noqa: BLE001
        return False, f"cannot read PDF: {type(exc).__name__}: {exc}"
    if info.n_pages == 0:
        return False, "PDF has 0 pages"
    if info.is_scan and skip_scans:
        return None, "SKIPPED_SCAN (no text layer)"
    if client is None:
        return False, "GEMINI_API_KEY not set and no complete cache"
    use_pdf = pdf_mode == "pdf" or (pdf_mode == "auto" and info.is_scan)
    if getattr(client, "text_only", False):  # DeepSeek: no multimodal input
        if info.is_scan:
            return None, "SKIPPED_SCAN (text-only DeepSeek backend)"
        use_pdf = False
    if not use_pdf and info.is_scan:
        return False, "no text layer and --pdf-mode text forbids multimodal upload"
    if cache and (cache.get("n_pages") != info.n_pages or cache.get("mode") != ("pdf" if use_pdf else "text")):
        cache = {}
    cache.update(version=CACHE_VERSION, n_pages=info.n_pages, is_scan=info.is_scan,
                 mode="pdf" if use_pdf else "text", window=window, windows=cache.get("windows", {}), complete=False)
    from plugins.rag.schemas import Meta  # lazy: needs pydantic

    uploaded = None
    try:
        if use_pdf:
            log(f"  [{doc_id}] scan/multimodal mode: uploading PDF")
            uploaded = client.upload_pdf(pdf, tag=doc_id)

        def contents(prompt: str, first: int, last: int, text: str | None = None) -> list:
            if use_pdf:
                return [uploaded, prompt]
            return ["PAPER TEXT (page markers are PDF page numbers):\n\n" + (text if text is not None else info.marked_text(first, last)), prompt]

        if "meta" not in cache:
            log(f"  [{doc_id}] meta pass ({info.n_pages} pages)")
            cache["meta"] = _gen(client, contents(META_USER, 1, info.n_pages, None), Meta, doc_id)
            save_cache(cache_dir, doc_id, cache)
        if cache["meta"]["publication"].get("in_scope"):
            for first in range(1, info.n_pages + 1, window):
                last = min(first + window - 1, info.n_pages)
                key = f"{first}-{last}"
                if key in cache["windows"]:
                    continue
                log(f"  [{doc_id}] results pass pages {key}")
                cache["windows"][key] = _window(client, contents, cache["meta"], first, last, doc_id,
                                                None if use_pdf else (lambda n: info.pages[n - 1]))
                save_cache(cache_dir, doc_id, cache)
        cache["complete"] = True
        save_cache(cache_dir, doc_id, cache)
        n = sum(len(w.get("results", [])) for w in cache["windows"].values())
        return True, f"{n} raw result rows, {time.time() - t0:.0f}s"
    except LLMError as exc:
        return False, f"{exc} (progress kept in cache; rerun to resume)"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc} (progress kept in cache; rerun to resume)"
    finally:
        if uploaded is not None:
            client.delete_file(uploaded)


def run_documents(pdfs: list[pathlib.Path], fn, workers: int) -> list[tuple[str, bool | None, str]]:
    """Run fn(pdf)->(ok,msg) over documents with `workers` threads (1 = plain sequential loop).
    Each document is handled by exactly one thread (its cache file has a single writer). Progress lines
    are printed as documents finish; the returned list keeps the INPUT order (deterministic)."""
    import gc
    from concurrent.futures import ThreadPoolExecutor, as_completed

    total, t0, done = len(pdfs), time.time(), 0
    results: dict[str, tuple[bool | None, str]] = {}

    def report(pdf: pathlib.Path, ok, msg: str) -> None:
        nonlocal done
        done += 1
        el = time.time() - t0
        eta = el / done * (total - done)
        log(f"[{done}/{total}] {pdf.stem}: {'SKIP' if ok is None else 'OK' if ok else 'FAIL'} - {msg} "
            f"(elapsed {el:.0f}s, ETA {eta:.0f}s)")

    def safe(pdf: pathlib.Path):
        try:
            return fn(pdf)
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"

    if workers <= 1:
        for pdf in pdfs:
            ok, msg = safe(pdf)
            results[pdf.stem] = (ok, msg)
            report(pdf, ok, msg)
            gc.collect()
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(safe, p): p for p in pdfs}
            for f in as_completed(futs):  # report runs only in the main thread
                ok, msg = f.result()
                results[futs[f].stem] = (ok, msg)
                report(futs[f], ok, msg)
    return [(p.stem, *results[p.stem]) for p in pdfs]
