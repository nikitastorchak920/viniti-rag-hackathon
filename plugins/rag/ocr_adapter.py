"""Ingest OCR-JSON produced elsewhere (teammate's PC) for scanned PDFs. No OCR runs here.
Format: {"publication_id": "D002", "pages": [{"source_page": 1, "is_scanned": true, "raw_text": "...",
  "normalized_text": "...", "primary_section": "Results", "tables": [{"caption": "Table 1: ...", "rows": [["RAG","0.5","0.6"]]}]}]}
`tables` is optional; its rows are appended to the page text as lines (cells joined by 2 spaces).
Rows are then parsed by the same rule-based extractor as local mode (heuristic, source_fragment = OCR line)."""
from __future__ import annotations

import json
import pathlib
import re

from core.llm_client import load_cache, save_cache
from plugins.rag.local_extract import build_cache, extract_lines

EMPTY = {"cells": [], "words": [], "text": ""}


def _page_lines(page: dict) -> tuple[list[dict], str]:
    text = page.get("normalized_text") or page.get("raw_text") or ""
    rows = text.splitlines()
    for t in page.get("tables") or []:
        if isinstance(t, dict):
            if t.get("caption"):
                rows.append(str(t["caption"]))
            for r in t.get("rows") or []:
                rows.append("  ".join(str(c) for c in r) if isinstance(r, (list, tuple)) else str(r))
    sec = (page.get("primary_section") or "").strip()
    lines = []
    if sec:
        lines.append({"y": 0, "words": sec.split(), "cells": [sec], "text": sec})
    for i, row in enumerate(rows, 1):
        row = row.strip()
        if row:
            lines.append({"y": i, "words": row.split(), "cells": [c for c in re.split(r"\s{2,}|\t", row) if c],
                          "text": " ".join(row.split())})
    return lines, text


def validate_ocr_json(doc: dict, n_pages: int | None) -> str | None:
    """Return error text or None."""
    if not isinstance(doc, dict) or not doc.get("publication_id") or not isinstance(doc.get("pages"), list):
        return "not an OCR-JSON (need publication_id and pages[])"
    nums = [p.get("source_page") for p in doc["pages"] if isinstance(p, dict)]
    if not nums or any(not isinstance(x, int) or x < 1 for x in nums):
        return "pages[].source_page must be integers >= 1"
    if len(set(nums)) != len(nums):
        return "duplicate source_page"
    if n_pages and max(nums) > n_pages:
        return f"source_page {max(nums)} exceeds PDF page count {n_pages}"
    return None


def ingest(doc: dict, cache_dir: pathlib.Path, n_pages: int | None = None, force: bool = False) -> tuple[bool, str]:
    err = validate_ocr_json(doc, n_pages)
    if err:
        return False, err
    pid = str(doc["publication_id"])
    old = load_cache(cache_dir, pid)
    if old.get("complete") and not force and old.get("mode") != "local":
        return True, f"kept existing {old.get('mode')} cache"
    n = n_pages or max(p["source_page"] for p in doc["pages"])
    by_page = {p["source_page"]: p for p in doc["pages"]}
    texts: dict[int, str] = {}

    def gen():
        for no in range(1, n + 1):
            lines, texts[no] = _page_lines(by_page.get(no, {}))
            yield lines

    ex = extract_lines(gen())
    full = "\n".join(texts[i] for i in sorted(texts))
    empty = [i for i in range(1, n + 1) if not texts[i].strip()]
    if len(empty) == n:
        return False, "all pages are empty: refusing to write an empty cache"
    cache = build_cache(n, texts.get(1, ""), full, ex, "ocr_json", True)
    cache["empty_pages"] = empty
    save_cache(cache_dir, pid, cache)
    return True, (f"{len(ex['results'])} raw result rows, in_scope={cache['meta']['publication']['in_scope']}, "
                  f"empty pages: {len(empty)}")


def ingest_file(path: pathlib.Path, cache_dir: pathlib.Path, pdf_dir: pathlib.Path | None = None,
                force: bool = False) -> tuple[bool, str]:
    try:
        doc = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"unreadable JSON: {exc}"
    n = None
    pid = doc.get("publication_id") if isinstance(doc, dict) else None
    if pdf_dir and pid and (pathlib.Path(pdf_dir) / f"{pid}.pdf").exists():
        try:
            import pymupdf

            with pymupdf.open(pathlib.Path(pdf_dir) / f"{pid}.pdf") as d:
                n = len(d)
        except Exception:  # noqa: BLE001
            n = None
    return ingest(doc, cache_dir, n, force)
