#!/usr/bin/env python3
"""Standalone Domain 1 (Thin-film solar cells) PDF extraction pipeline.

Usage:
  python scripts/run_solar.py --input область_1/dev --output out_solar_dev --only D001 D006 --ocr
  python scripts/run_solar.py --input область_1/dev --output out_solar_dev --rebuild-csv-only
"""
from __future__ import annotations

import argparse
import gc
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=pathlib.Path, required=True, help="folder with solar PDFs")
    ap.add_argument("--output", type=pathlib.Path, required=True, help="folder for the 7 CSV files")
    ap.add_argument("--cache", type=pathlib.Path, default=pathlib.Path("cache_solar"), help="raw JSON cache folder (default cache_solar)")
    ap.add_argument("--only", nargs="+", metavar="ID", help="document ids to process, e.g. D001 D006")
    ap.add_argument("--force", action="store_true", help="ignore cache and re-query the API")
    ap.add_argument("--rebuild-csv-only", action="store_true", help="no API calls: rebuild CSV from cache")
    ap.add_argument("--window", type=int, default=3, help="pages per result-extraction request (default 3)")
    ap.add_argument("--pdf-mode", choices=["auto", "text"], default="auto", help="use PDF text or local OCR with --ocr")
    ap.add_argument("--skip-scans", action="store_true", help="skip image-only PDFs without text layer")
    ap.add_argument("--workers", type=int, default=None, help="parallel documents for LLM mode (default: env WORKERS or 4)")
    ap.add_argument("--ocr", action="store_true", help="run local OCR on image-only pages")
    ap.add_argument("--verify-pass", action="store_true", help="second LLM audit of dense numeric pages (resumable)")
    a = ap.parse_args(argv)

    from core.llm_client import load_cache, log
    from plugins.solar import exporter

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
    skipped: list[str] = []
    client = None

    if not a.rebuild_csv_only:
        from core.llm_client import DeepSeekClient, LLMError, load_env

        load_env()
        try:
            if os.environ.get("DEEPSEEK_API_KEY", "").strip():
                client = DeepSeekClient()
        except (LLMError, ImportError) as exc:
            log(f"ERROR: {exc}")
            return 1

        if client is not None:
            try:
                client.preflight()
            except LLMError as exc:
                log(f"ERROR: {exc}")
                return 1
            log(f"backend={type(client).__name__} model={client.model} max_out={getattr(client, 'max_out', '?')} docs={len(pdfs)}")
        else:
            a.skip_scans = True
            log("WARN: no DEEPSEEK_API_KEY; only already cached documents can be exported")

        from plugins.solar.pipeline import process_document, run_documents

        workers = a.workers if a.workers is not None else int(os.environ.get("WORKERS") or 4)
        workers = max(1, min(workers, len(pdfs) or 1))
        log(f"workers={workers}")
        for stem, ok, msg in run_documents(
            pdfs,
            lambda p: process_document(p, client, a.cache, a.force, max(1, a.window), a.pdf_mode, a.skip_scans, a.ocr),
            workers,
        ):
            if ok is None:
                skipped.append(stem)
            elif not ok:
                failed.append(stem)

    if a.verify_pass and not a.rebuild_csv_only and client is not None:
        from plugins.solar.pipeline import verify_pass

        for pdf in pdfs:
            if pdf.stem in failed or pdf.stem in skipped:
                continue
            ok, msg = verify_pass(pdf, client, a.cache, ocr=a.ocr)
            log(f"{pdf.stem}: verify - {msg}")

    if getattr(client, "tokens_in", 0):
        log(f"TOKENS total in={client.tokens_in} out={client.tokens_out}")

    writer = exporter.TableWriter(a.output)
    built = 0
    stubs: list[str] = []

    def write_stub(pid: str) -> None:
        stubs.append(pid)
        writer.write_doc({"publications": [exporter.stub_publication(pid)]})

    try:
        for pdf in pdfs:
            if pdf.stem in failed or pdf.stem in skipped:
                write_stub(pdf.stem)
                continue
            cache = load_cache(a.cache, pdf.stem)
            if not cache.get("complete"):
                log(f"{pdf.stem}: FAIL - no complete cache (run without --rebuild-csv-only)")
                failed.append(pdf.stem)
                write_stub(pdf.stem)
                continue
            pages_raw = exporter.load_pdf_pages_for_grounding(pdf, cache)
            try:
                doc = exporter.build_doc(pdf.stem, cache, pages_raw=pages_raw, log_fn=log)
            except Exception as exc:  # noqa: BLE001
                log(f"{pdf.stem}: FAIL - export error {type(exc).__name__}: {exc}")
                failed.append(pdf.stem)
                write_stub(pdf.stem)
                continue
            writer.write_doc(doc)
            built += 1
            del doc, cache, pages_raw
            gc.collect()
    finally:
        writer.close(built > 0)

    if built == 0:
        log("ERROR: nothing to export, CSV files not written")
        return 1
    log(
        f"wrote {a.output}/ docs={built} stubs={len(stubs)} "
        + " ".join(f"{t}={writer.counts[t]}" for t in exporter.TABLES)
    )
    if stubs:
        log(f"NOT PROCESSED (stub rows in publications.csv): {', '.join(stubs)}")
    if skipped:
        log(f"SKIPPED_SCAN: {len(skipped)} document(s): {', '.join(skipped)}")
    if failed:
        log(f"INCOMPLETE: {len(failed)} document(s) failed: {', '.join(failed)}")
    return 1 if (stubs or failed) else 0


if __name__ == "__main__":
    sys.exit(main())
