#!/usr/bin/env python3
"""RAG scientific-PDF extraction pipeline. Usage:
  python main.py --input dev --output out_dev --only D001 D002
  python main.py --input dev --output out_dev --rebuild-csv-only
"""
from __future__ import annotations

import argparse
import pathlib
import sys

try:  # UTF-8 console on Windows
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=pathlib.Path, required=True, help="folder with PDFs (e.g. dev or test)")
    ap.add_argument("--output", type=pathlib.Path, required=True, help="folder for the 7 CSV files (e.g. out_dev)")
    ap.add_argument("--cache", type=pathlib.Path, default=pathlib.Path("cache"), help="raw LLM JSON cache folder")
    ap.add_argument("--only", nargs="+", metavar="ID", help="document ids to process, e.g. D001 D002")
    ap.add_argument("--force", action="store_true", help="ignore cache and re-query the API")
    ap.add_argument("--rebuild-csv-only", action="store_true", help="no API calls: rebuild CSV from cache")
    ap.add_argument("--window", type=int, default=3, help="pages per result-extraction request (default 3)")
    ap.add_argument("--pdf-mode", choices=["auto", "text", "pdf"], default="auto",
                    help="auto: text layer, scans sent as PDF; pdf: always send PDF; text: text layer only")
    a = ap.parse_args(argv)

    from core.llm_client import log
    from core.pdf_processor import inspect_pdf
    from plugins.rag import exporter
    from core.llm_client import load_cache

    pdfs = sorted(a.input.glob("*.pdf"))
    if a.only:
        wanted = {x.upper() for x in a.only}
        pdfs = [p for p in pdfs if p.stem.upper() in wanted]
        missing = wanted - {p.stem.upper() for p in pdfs}
        if missing:
            log(f"ERROR: not found in {a.input}: {', '.join(sorted(missing))}")
            return 1
    if not pdfs:
        log(f"ERROR: no PDFs in {a.input}")
        return 1

    failed: list[str] = []
    if not a.rebuild_csv_only:
        from core.llm_client import GeminiClient, LLMError

        try:
            client = GeminiClient()
        except (LLMError, ImportError) as exc:
            log(f"ERROR: {exc}")
            return 1
        log(f"model={client.model} docs={len(pdfs)}")
        from plugins.rag.pipeline import process_document

        for pdf in pdfs:
            ok, msg = process_document(pdf, client, a.cache, a.force, max(1, a.window), a.pdf_mode)
            log(f"{pdf.stem}: {'OK' if ok else 'FAIL'} - {msg}")
            if not ok:
                failed.append(pdf.stem)

    tables = {t: [] for t in exporter.TABLES}
    built = 0
    for pdf in pdfs:
        cache = load_cache(a.cache, pdf.stem)
        if not cache.get("complete"):
            if pdf.stem not in failed:
                log(f"{pdf.stem}: FAIL - no complete cache (run without --rebuild-csv-only)")
                failed.append(pdf.stem)
            continue
        pages_norm = None
        if not cache.get("is_scan") and cache.get("mode") == "text":
            try:
                pages_norm = [exporter.norm(t) for t in inspect_pdf(pdf).pages]
            except Exception as exc:  # noqa: BLE001
                log(f"  {pdf.stem}: WARN quote check skipped ({exc})")
        try:
            doc = exporter.build_doc(pdf.stem, cache, pages_norm, log)
        except Exception as exc:  # noqa: BLE001
            log(f"{pdf.stem}: FAIL - export error {type(exc).__name__}: {exc}")
            failed.append(pdf.stem)
            continue
        for t in exporter.TABLES:
            tables[t].extend(doc[t])
        built += 1

    if built == 0:
        log("ERROR: nothing to export, CSV files not written")
        return 1
    exporter.write_tables(a.output, tables)
    log(f"wrote {a.output}/ docs={built} " + " ".join(f"{t}={len(tables[t])}" for t in exporter.TABLES))
    if failed:
        log(f"INCOMPLETE: {len(failed)} document(s) failed and are missing from CSV: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
