"""Per-document extraction: meta pass + page-window result passes, cached incrementally."""
from __future__ import annotations

import pathlib
import time

from core.llm_client import GeminiClient, LLMError, TruncatedResponseError, load_cache, log, save_cache
from core.pdf_processor import inspect_pdf
from plugins.rag.prompts import META_USER, SYSTEM, window_user

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


def _window(client, contents_fn, meta: dict, first: int, last: int, doc_id: str) -> dict:
    """Extract pages first..last; on truncation split the range in half (down to one page)."""
    from plugins.rag.schemas import Window

    try:
        return _gen(client, contents_fn(window_user(meta, first, last), first, last), Window, f"{doc_id}:{first}-{last}")
    except TruncatedResponseError:
        if first >= last:
            raise
        mid = (first + last) // 2
        log(f"  [{doc_id}] truncated at pages {first}-{last}: splitting into {first}-{mid} and {mid + 1}-{last}")
        a = _window(client, contents_fn, meta, first, mid, doc_id)
        b = _window(client, contents_fn, meta, mid + 1, last, doc_id)
        return {"results": a["results"] + b["results"]}


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

        def contents(prompt: str, first: int, last: int) -> list:
            if use_pdf:
                return [uploaded, prompt]
            return ["PAPER TEXT (page markers are PDF page numbers):\n\n" + info.marked_text(first, last), prompt]

        if "meta" not in cache:
            log(f"  [{doc_id}] meta pass ({info.n_pages} pages)")
            cache["meta"] = _gen(client, contents(META_USER, 1, info.n_pages), Meta, doc_id)
            save_cache(cache_dir, doc_id, cache)
        if cache["meta"]["publication"].get("in_scope"):
            for first in range(1, info.n_pages + 1, window):
                last = min(first + window - 1, info.n_pages)
                key = f"{first}-{last}"
                if key in cache["windows"]:
                    continue
                log(f"  [{doc_id}] results pass pages {key}")
                cache["windows"][key] = _window(client, contents, cache["meta"], first, last, doc_id)
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
