"""Per-document extraction pipeline for Domain 1 (Thin-film solar cells)."""
from __future__ import annotations

import pathlib
import re
import time

from core.llm_client import LLMError, TruncatedResponseError, load_cache, log, save_cache
from core.pdf_processor import MIN_CHARS_PER_TEXT_PAGE, PdfInfo, inspect_pdf
from plugins.solar.prompts import (
    META_USER, RESULT_SYSTEM, SYSTEM, compact_meta_format, compact_result_format, verify_user, window_user,
)

CACHE_VERSION = 2

OVERLAP = 4
CAPTION = re.compile(r"(?i)^\s*(table|tab\.|figure|fig\.)\s*[A-Z]?\d+")
COLHEAD = re.compile(
    r"(?i)\b(PCE|Voc|Jsc|FF|V_oc|J_sc|Device|Sample|Cell|Scan|Reverse|Forward|EQE|T80|Rs|Rsh)\b"
    r".*\b(PCE|Voc|Jsc|FF|V_oc|J_sc|Device|Sample|Cell|Scan|Reverse|Forward|EQE|T80|Rs|Rsh|efficiency|voltage|current)\b"
)
SECTION = re.compile(r"(?i)^\s*(?:(?:section\s+)?\d+(?:\.\d+)*\.?|appendix\s+[a-z])\s+([^\W\d_].{1,99})$")
TABLE_VALUES = re.compile(r"(?<!\w)[+−-]?(?:\d+\.\d+|\.\d+|\d+%)|(?:\s+\d+){2}(?:\s|$)")
HDR_MARK, HDR_END = "[TABLE HEADER CONTEXT - do not extract values from these lines]", "[END HEADER CONTEXT]"
HEADER_LINES = 5
NUM_TOKEN = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?%?(?![\w])")


def _tesseract_fallback_pages(pdf: pathlib.Path, info: PdfInfo) -> PdfInfo:
    """Fallback to local Tesseract OCR on image-only pages if RapidOCR is unavailable."""
    short = [i for i, t in enumerate(info.pages) if len((t or "").strip()) < MIN_CHARS_PER_TEXT_PAGE]
    if not short:
        return info
    try:
        import pymupdf
        import pytesseract
        from PIL import Image
    except ImportError:
        return info

    pages = list(info.pages)
    recognized_any = False
    with pymupdf.open(pdf) as doc:
        for idx in short:
            try:
                pix = doc[idx].get_pixmap(dpi=250, colorspace=pymupdf.csRGB)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                text = pytesseract.image_to_string(img, lang="eng", config="--psm 3", timeout=90) or ""
            except Exception as exc:  # noqa: BLE001
                log(f"  [{pdf.stem}] WARN: Tesseract OCR failed on page {idx + 1}: {exc}")
                continue
            if len(text.strip()) >= MIN_CHARS_PER_TEXT_PAGE:
                pages[idx] = text
                recognized_any = True
    if not recognized_any:
        return info
    unreadable = sum(len((pages[i] or "").strip()) < MIN_CHARS_PER_TEXT_PAGE for i in short)
    is_scan = (not pages or len(pages) - unreadable < max(1, int(0.9 * len(pages))))
    return PdfInfo(
        path=info.path,
        n_pages=info.n_pages,
        pages=pages,
        is_scan=is_scan,
        used_ocr=True,
        layout=info.layout,
        structured_pages=None,
        layout_tokens=info.layout_tokens,
    )


def _gen(client, contents: list, schema, tag: str, *, is_result: bool = False) -> dict:
    from pydantic import ValidationError
    from plugins.solar.schemas import CompactMeta, CompactWindow

    if schema is CompactWindow:
        system = RESULT_SYSTEM + "\n\n" + compact_result_format()
    elif schema is CompactMeta:
        system = SYSTEM + "\n\n" + compact_meta_format()
    elif is_result:
        system = RESULT_SYSTEM
    else:
        system = SYSTEM

    last = ""
    for _ in range(3):
        data = client.generate_json(contents, system, schema, tag=tag)
        try:
            validated = schema.model_validate(data)
            return validated.expanded() if schema in (CompactWindow, CompactMeta) else validated.model_dump()
        except ValueError as exc:
            errors = exc.errors() if isinstance(exc, ValidationError) else []
            last = str(exc).splitlines()[0][:200] + " " + (str(errors[0].get("loc")) if errors else "")
            log(f"  [{tag}] schema validation failed ({last}); retrying")
    raise LLMError(f"model output failed schema validation 3x: {last}")


def _result_schema(client):
    from plugins.solar.schemas import CompactWindow, Window

    return CompactWindow if getattr(client, "compact_results", False) is True else Window


def _header(lines: list[str], idx: int) -> list[str]:
    """Preserve section heading, caption, and solar table column header across line splits."""
    for i in range(idx - 1, -1, -1):
        if CAPTION.match(lines[i]) or (COLHEAD.search(lines[i]) and not TABLE_VALUES.search(lines[i])):
            for j in range(i - 1, max(-1, i - 4), -1):
                if CAPTION.match(lines[j]):
                    i = j
                    break
            heading = next(
                (j for j in range(i - 1, -1, -1)
                 if (section := SECTION.match(lines[j])) and not TABLE_VALUES.search(section[1])),
                None,
            )
            start = (heading + 1) if heading is not None else 0
            pre_table = [line for line in lines[start:i] if line.strip()][-2:]
            out = ([lines[heading]] if heading is not None else []) + pre_table
            for j in range(i, min(i + HEADER_LINES, idx)):
                if j > i and TABLE_VALUES.search(lines[j]):
                    break
                out.append(lines[j])
            return out
    return []


def _dedupe(rows: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in rows:
        k = tuple(sorted((field, value) for field, value in r.items() if field != "note"))
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def _part(client, contents_fn, meta: dict, page: int, lines: list[str], doc_id: str, depth: int = 0,
          context: list[str] | None = None) -> list[dict]:
    tag = f"{doc_id}:{page}-{page}" + (f"/L{len(lines)}" if depth else "")
    try:
        prefix = [HDR_MARK, *context, HDR_END] if context else []
        text = f"--- PAGE {page} ---\n" + "\n".join(prefix + lines)
        data = _gen(
            client,
            contents_fn(window_user(meta, page, page, part=depth > 0), page, page, text),
            _result_schema(client),
            tag,
            is_result=True,
        )
        return data["results"]
    except TruncatedResponseError:
        if len(lines) < 2 * OVERLAP + 2 or depth >= 8:
            raise
        mid = len(lines) // 2
        log(f"  [{doc_id}] page {page} truncated ({len(lines)} lines): splitting by lines")
        a = _part(client, contents_fn, meta, page, lines[:mid + OVERLAP], doc_id, depth + 1, context)
        split = mid - OVERLAP
        b = _part(client, contents_fn, meta, page, lines[split:], doc_id, depth + 1, _header(lines, split) or context)
        return _dedupe(a + b)


def _window(client, contents_fn, meta: dict, first: int, last: int, doc_id: str, page_text_fn=None) -> dict:
    try:
        return _gen(
            client,
            contents_fn(window_user(meta, first, last), first, last, None),
            _result_schema(client),
            f"{doc_id}:{first}-{last}",
            is_result=True,
        )
    except TruncatedResponseError:
        if first >= last:
            text = page_text_fn(first) if page_text_fn else None
            if not text or not text.strip():
                raise
            rows = _part(client, contents_fn, meta, first, text.strip().splitlines(), doc_id, depth=1)
            for r in rows:
                r["source_page"] = first
            return {"results": rows}
        mid = (first + last) // 2
        log(f"  [{doc_id}] truncated at pages {first}-{last}: splitting into {first}-{mid} and {mid + 1}-{last}")
        a = _window(client, contents_fn, meta, first, mid, doc_id, page_text_fn)
        b = _window(client, contents_fn, meta, mid + 1, last, doc_id, page_text_fn)
        return {"results": a["results"] + b["results"]}


def select_verify_pages(pages: list[str], cache: dict, min_numbers: int = 25, min_rows_ratio: float = 0.25) -> list[int]:
    from plugins.solar.exporter import norm

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
        unverified = sum(
            1 for r in rows
            if r.get("source_fragment")
            and not re.match(r"^(?:Table|TABLE|Supplementary)\b", str(r["source_fragment"]).strip())
            and norm(r["source_fragment"]) not in pn
        )
        has_solar_kw = bool(re.search(r"(?i)\b(PCE|Voc|Jsc|FF|V_oc|J_sc|efficiency|Table\s+\d)\b", text))
        if (has_solar_kw and dens >= min_numbers and len(rows) < dens * min_rows_ratio) or unverified:
            out.append(n)
    return out


def verify_pass(pdf: pathlib.Path, client, cache_dir: pathlib.Path, max_pages: int = 20, ocr: bool = False) -> tuple[bool, str]:
    doc_id = pdf.stem
    cache = load_cache(cache_dir, doc_id)
    if not cache.get("complete") or cache.get("mode") != "text" or not cache.get("meta", {}).get("publication", {}).get("in_scope"):
        return True, "verify skipped (no complete text-mode in-scope cache)"
    if client is None:
        return False, "no LLM client for --verify-pass"
    info = inspect_pdf(pdf, ocr=ocr, structured=True)
    if ocr and info.is_scan:
        info = _tesseract_fallback_pages(pdf, info)
    cache.setdefault("verify", {})
    todo = [p for p in select_verify_pages(info.pages, cache) if str(p) not in cache["verify"]][:max_pages]
    added = 0
    try:
        for p in todo:
            existing = [
                f"{r.get('device_id')}|{r.get('measurement_id')}|{r.get('metric_name')}|{r.get('raw_value')}|{r.get('aggregation')}|{r.get('result_origin')}"
                for w in cache["windows"].values()
                for r in w.get("results", [])
                if str(r.get("source_page")) == str(p)
            ]
            contents = [
                "PAPER TEXT (page markers are PDF page numbers):\n\n" + info.marked_text(p, p),
                verify_user(cache["meta"], p, existing),
            ]
            log(f"  [{doc_id}] verify pass page {p}")
            res = _gen(client, contents, _result_schema(client), f"{doc_id}:verify{p}", is_result=True)
            for r in res["results"]:
                r["source_page"] = p
            cache["verify"][str(p)] = {"results": res["results"]}
            added += len(res["results"])
            save_cache(cache_dir, doc_id, cache)
    except LLMError as exc:
        return False, f"{exc} (verify progress kept)"
    return True, f"verified {len(todo)} pages, +{added} rows"


def process_document(
    pdf: pathlib.Path,
    client,
    cache_dir: pathlib.Path,
    force: bool,
    window: int,
    pdf_mode: str,
    skip_scans: bool = False,
    ocr: bool = False,
) -> tuple[bool | None, str]:
    doc_id = pdf.stem
    t0 = time.time()
    cache = {} if force else load_cache(cache_dir, doc_id)
    if cache.get("version") != CACHE_VERSION:
        cache = {}
    if cache.get("complete"):
        return True, "cached"

    wants_text = pdf_mode != "pdf" or getattr(client, "text_only", False)
    try:
        info = inspect_pdf(pdf, ocr=ocr and wants_text, structured=wants_text)
        if ocr and wants_text and info.is_scan:
            info = _tesseract_fallback_pages(pdf, info)
    except Exception as exc:  # noqa: BLE001
        return False, f"cannot read PDF: {type(exc).__name__}: {exc}"
    if info.n_pages == 0:
        return False, "PDF has 0 pages"
    if info.is_scan and skip_scans:
        return None, "SKIPPED_SCAN (insufficient page text)"
    if client is None:
        return False, "API key not set and no complete cache"

    use_pdf = pdf_mode == "pdf" or (pdf_mode == "auto" and info.is_scan)
    if getattr(client, "text_only", False):
        if info.is_scan:
            return None, "SKIPPED_SCAN (insufficient page text for text-only backend; pass --ocr)"
        use_pdf = False
    if not use_pdf and info.is_scan:
        return False, "no text layer and --pdf-mode text forbids multimodal upload"

    mode = "pdf" if use_pdf else "text"
    used_ocr = info.used_ocr and not use_pdf
    if cache and (cache.get("n_pages") != info.n_pages or cache.get("mode") != mode or cache.get("window") != window):
        cache = {}
    cache.update(
        version=CACHE_VERSION,
        n_pages=info.n_pages,
        is_scan=info.is_scan,
        ocr=used_ocr,
        mode=mode,
        window=window,
        windows=cache.get("windows", {}),
        complete=False,
    )
    if used_ocr:
        cache["ocr_pages"] = info.pages

    from plugins.solar.schemas import CompactMeta, Meta

    uploaded = None
    try:
        if use_pdf:
            log(f"  [{doc_id}] scan/multimodal mode: uploading PDF")
            uploaded = client.upload_pdf(pdf, tag=doc_id)
        elif used_ocr:
            log(f"  [{doc_id}] OCR text mode")

        def contents(prompt: str, first: int, last: int, text: str | None = None) -> list:
            if use_pdf:
                return [uploaded, prompt]
            body = text if text is not None else info.marked_text(first, last)
            return ["PAPER TEXT (page markers are PDF page numbers):\n\n" + body, prompt]

        if "meta" not in cache:
            log(f"  [{doc_id}] meta pass ({info.n_pages} pages)")
            meta_schema = CompactMeta if getattr(client, "compact_results", False) is True else Meta
            cache["meta"] = _gen(client, contents(META_USER, 1, info.n_pages, None), meta_schema, f"{doc_id}:meta", is_result=False)
            save_cache(cache_dir, doc_id, cache)

        in_scope = bool(cache["meta"]["publication"].get("in_scope"))
        if in_scope:
            page_text = None if use_pdf else (lambda p: info.prompt_pages[p - 1])
            for first in range(1, info.n_pages + 1, window):
                last = min(first + window - 1, info.n_pages)
                key = f"{first}-{last}"
                if key in cache["windows"]:
                    continue
                log(f"  [{doc_id}] results pass pages {key}")
                cache["windows"][key] = _window(client, contents, cache["meta"], first, last, doc_id, page_text)
                save_cache(cache_dir, doc_id, cache)

        cache["complete"] = True
        save_cache(cache_dir, doc_id, cache)
        if not in_scope:
            reason = cache["meta"]["publication"].get("exclusion_reason", "")
            return True, f"out of scope ({reason}), {time.time() - t0:.0f}s"
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
            for f in as_completed(futs):
                ok, msg = f.result()
                results[futs[f].stem] = (ok, msg)
                report(futs[f], ok, msg)
    return [(p.stem, *results[p.stem]) for p in pdfs]
