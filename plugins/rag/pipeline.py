"""Per-document extraction: meta pass + page-window result passes, cached incrementally."""
from __future__ import annotations

import pathlib
import time

from core.llm_client import GeminiClient, LLMError, load_cache, log, save_cache
from core.pdf_processor import inspect_pdf
from plugins.rag.prompts import META_USER, SYSTEM, window_user
from plugins.rag.schemas import Meta, Window

CACHE_VERSION = 2


def process_document(pdf: pathlib.Path, client: GeminiClient, cache_dir: pathlib.Path, force: bool,
                     window: int, pdf_mode: str) -> tuple[bool, str]:
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
    use_pdf = pdf_mode == "pdf" or (pdf_mode == "auto" and info.is_scan)
    if not use_pdf and info.is_scan:
        return False, "no text layer and --pdf-mode text forbids multimodal upload"
    if cache and (cache.get("n_pages") != info.n_pages or cache.get("mode") != ("pdf" if use_pdf else "text")):
        cache = {}
    cache.update(version=CACHE_VERSION, n_pages=info.n_pages, is_scan=info.is_scan,
                 mode="pdf" if use_pdf else "text", window=window, windows=cache.get("windows", {}), complete=False)
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
            cache["meta"] = client.generate_json(contents(META_USER, 1, info.n_pages), SYSTEM, Meta, tag=doc_id)
            save_cache(cache_dir, doc_id, cache)
        if cache["meta"]["publication"].get("in_scope"):
            for first in range(1, info.n_pages + 1, window):
                last = min(first + window - 1, info.n_pages)
                key = f"{first}-{last}"
                if key in cache["windows"]:
                    continue
                log(f"  [{doc_id}] results pass pages {key}")
                cache["windows"][key] = client.generate_json(
                    contents(window_user(cache["meta"], first, last), first, last), SYSTEM, Window, tag=f"{doc_id}:{key}")
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
