#!/usr/bin/env python3
"""RAG scientific-PDF extraction pipeline. Usage:
  python main.py --input dev --output out_dev --only D001 D002
  python main.py --input dev --output out_dev --rebuild-csv-only
"""
from __future__ import annotations

import argparse
import gc
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
    ap.add_argument("--cache", type=pathlib.Path, default=None, help="raw JSON cache folder (default cache; cache_local with --local)")
    ap.add_argument("--only", nargs="+", metavar="ID", help="document ids to process, e.g. D001 D002")
    ap.add_argument("--force", action="store_true", help="ignore cache and re-query the API")
    ap.add_argument("--rebuild-csv-only", action="store_true", help="no API calls: rebuild CSV from cache")
    ap.add_argument("--include-partial-cache", action="store_true",
                    help="export successful windows from incomplete caches with an explicit review marker")
    ap.add_argument("--recover-table-cells", action=argparse.BooleanOptionalAction, default=True,
                    help="export uniquely identified missing native PDF table cells (enabled by default, no API calls)")
    ap.add_argument("--recover-plot-points", action="store_true",
                    help="also export calibrated native vector scatter points (works without API calls)")
    ap.add_argument("--window", type=int, default=3, help="pages per result-extraction request (default 3)")
    ap.add_argument("--pdf-mode", choices=["auto", "text", "pdf"], default="auto",
                    help="auto: structured text, unreadable scans sent as PDF; pdf: request PDF; text: structured text only")
    ap.add_argument("--skip-scans", action="store_true",
                    help="skip image-only PDFs (status SKIPPED_SCAN); enabled automatically when GEMINI_API_KEY is not set")
    ap.add_argument("--ocr-json", type=pathlib.Path, default=None, metavar="DIR",
                    help="folder with <id>.json OCR files from the teammate's PC (scanned PDFs); no OCR is run here")
    ap.add_argument("--workers", type=int, default=None,
                    help="parallel documents for LLM mode (default: env WORKERS or 4; 1 = sequential)")
    ap.add_argument("--ocr", action="store_true",
                    help="use RapidOCR on low-text pages and recheck OCR-cache quotes; Gemini auto mode falls back to PDF")
    ap.add_argument("--verify-pass", action="store_true",
                    help="second LLM audit of dense/thin pages (cache-backed, resumable) to recover missed table rows; needs API key")
    ap.add_argument("--local", action="store_true", help="no API: rule-based local extraction (text PDFs only; heuristic)")
    a = ap.parse_args(argv)
    if a.include_partial_cache and not a.rebuild_csv_only:
        ap.error("--include-partial-cache requires --rebuild-csv-only")
    if a.cache is None:
        a.cache = pathlib.Path("cache_local" if a.local else "cache")

    from pydantic import ValidationError

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
    skipped: list[str] = []
    ocr_done: set[str] = set()
    if a.ocr_json:
        from plugins.rag.ocr_adapter import ingest_file

        for pdf in pdfs:
            j = a.ocr_json / f"{pdf.stem}.json"
            if j.exists():
                ok, msg = ingest_file(j, a.cache, a.input, a.force)
                log(f"{pdf.stem}: {'OK' if ok else 'FAIL'} - OCR-JSON: {msg}")
                if ok:
                    ocr_done.add(pdf.stem)
                else:
                    failed.append(pdf.stem)
    pdfs_todo = [p for p in pdfs if p.stem not in ocr_done and p.stem not in failed]
    if a.local and not a.rebuild_csv_only:
        from plugins.rag.local_extract import process_local

        for pdf in pdfs_todo:
            ok, msg = process_local(pdf, a.cache, a.force, True)
            log(f"{pdf.stem}: {'SKIP' if ok is None else 'OK' if ok else 'FAIL'} - {msg}")
            if ok is None:
                skipped.append(pdf.stem)
            elif not ok:
                failed.append(pdf.stem)
            gc.collect()
    elif not a.rebuild_csv_only:
        import os
        from core.llm_client import GeminiClient, LLMError, load_env

        load_env()
        client = None
        try:
            if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
                client = GeminiClient()
            elif os.environ.get("DEEPSEEK_API_KEY"):
                from core.llm_client import DeepSeekClient

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
            log(f"backend={type(client).__name__} model={client.model} docs={len(pdfs)}")
        else:
            a.skip_scans = True
            log("WARN: no GEMINI_API_KEY / DEEPSEEK_API_KEY: --skip-scans enabled automatically; only cached documents can be exported")
        from plugins.rag.pipeline import process_document, run_documents

        workers = a.workers if a.workers is not None else int(os.environ.get("WORKERS") or 4)
        workers = max(1, min(workers, len(pdfs_todo) or 1))
        log(f"workers={workers}")
        for stem, ok, msg in run_documents(
                pdfs_todo, lambda p: process_document(p, client, a.cache, a.force, max(1, a.window), a.pdf_mode, a.skip_scans, a.ocr),
                workers):
            if ok is None:
                skipped.append(stem)
            elif not ok:
                failed.append(stem)

    if a.verify_pass and not a.rebuild_csv_only and locals().get("client") is not None:
        from plugins.rag.pipeline import verify_pass

        for pdf in pdfs_todo if "pdfs_todo" in locals() else pdfs:
            ok, msg = verify_pass(pdf, client, a.cache)
            log(f"{pdf.stem}: verify - {msg}")
    if getattr(locals().get("client"), "tokens_in", 0):
        log(f"TOKENS total in={client.tokens_in} out={client.tokens_out}")
    writer = exporter.TableWriter(a.output)
    built = 0
    stubs: list[str] = []
    partials: list[str] = []

    def stub(pid: str) -> None:
        stubs.append(pid)
        writer.write_doc({"publications": [exporter.stub_publication(pid)]})

    try:
        for pdf in pdfs:
            if pdf.stem in failed or pdf.stem in skipped:
                stub(pdf.stem)
                continue
            cache = load_cache(a.cache, pdf.stem)
            partial = not cache.get("complete")
            if partial:
                meta, windows = cache.get("meta") or {}, cache.get("windows") or {}
                if not (a.include_partial_cache and cache.get("version") == 2
                        and isinstance(meta, dict) and isinstance(windows, dict)
                        and isinstance(meta.get("publication"), dict)
                        and meta.get("publication", {}).get("in_scope") is True
                        and all(isinstance(window, dict) for window in windows.values())
                        and any(window.get("results") for window in windows.values())):
                    log(f"{pdf.stem}: FAIL - no complete cache (run without --rebuild-csv-only)")
                    failed.append(pdf.stem)
                    stub(pdf.stem)
                    continue
                from core.validator import PARTIAL_EXTRACTION

                marker = {"check_name": PARTIAL_EXTRACTION,
                          "description": f"Partial extraction. The cache has {len(windows)} saved result windows "
                                         "and the full paper was not processed.",
                          "source_page": 0, "source_fragment": ""}
                cache["meta"] = dict(meta, issues=[*meta.get("issues", []), marker])
            pages_norm = None
            table_layout = None
            plot_rows = []
            if a.ocr and cache.get("ocr"):
                from core.ocr import ocr_pages

                try:
                    pages_norm = [exporter.norm(text) for text in ocr_pages(pdf)]
                    if len(pages_norm) != cache.get("n_pages"):
                        pages_norm = None
                        log(f"  {pdf.stem}: WARN OCR quote check skipped (page count differs from cache)")
                except Exception as exc:  # noqa: BLE001
                    log(f"  {pdf.stem}: WARN OCR quote check skipped ({exc})")
            elif not cache.get("is_scan") and not cache.get("ocr") and cache.get("mode") in ("text", "local"):
                try:
                    table_pages = {exporter.to_page(row.get("source_page")) for row in exporter.iter_results(cache)
                                   if row.get("source_table") and (row.get("result_origin") or "primary") == "primary"}
                    info = inspect_pdf(pdf, layout_pages=table_pages)
                    pages_norm = [exporter.norm(t) for t in info.pages]
                    table_layout = info.layout
                except Exception as exc:  # noqa: BLE001
                    log(f"  {pdf.stem}: WARN quote check skipped ({exc})")
                if a.recover_plot_points and pages_norm is not None and cache.get("meta", {}).get("publication", {}).get("in_scope"):
                    from plugins.rag.plot_recovery import recover_plot_points

                    try:
                        plot_rows = recover_plot_points(pdf, info.pages, cache)
                        if plot_rows:
                            log(f"  {pdf.stem}: recovered {len(plot_rows)} vector plot observations")
                    except (ValueError, RuntimeError, OSError) as exc:
                        log(f"  {pdf.stem}: WARN plot recovery skipped ({exc})")
            try:
                doc = exporter.build_doc(pdf.stem, cache, pages_norm, log, table_layout=table_layout,
                                         recover_table_cells=a.recover_table_cells, plot_rows=plot_rows)
            except Exception as exc:  # noqa: BLE001
                log(f"{pdf.stem}: FAIL - export error {type(exc).__name__}: {exc}")
                failed.append(pdf.stem)
                stub(pdf.stem)
                continue
            if doc["publications"][0]["in_scope"] == "true" and not any(
                r["extraction_status"] == "extracted" and r["metric_value"] for r in doc["results"]
            ):
                log(f"{pdf.stem}: FAIL - in-scope publication has no exportable numeric results (review extraction)")
                failed.append(pdf.stem)
                if not doc["results"]:
                    stub(pdf.stem)
                    continue
            try:
                writer.write_doc(doc)
            except ValidationError as exc:
                log(f"{pdf.stem}: FAIL - normalized CSV rows failed validation: {exc}")
                if pdf.stem not in failed:
                    failed.append(pdf.stem)
                stub(pdf.stem)
                continue
            built += 1
            if partial:
                partials.append(pdf.stem)
            del doc, cache, pages_norm
            gc.collect()
    finally:
        writer.close(built > 0)

    if built == 0:
        log("ERROR: nothing to export, CSV files not written")
        return 1
    log(f"wrote {a.output}/ docs={built} stubs={len(stubs)} " + " ".join(f"{t}={writer.counts[t]}" for t in exporter.TABLES))
    if stubs:
        log(f"NOT PROCESSED (stub rows in publications.csv): {', '.join(stubs)}")
    if partials:
        log(f"PARTIAL EXTRACTION (saved result windows only): {', '.join(partials)}")
    if skipped:
        log(f"SKIPPED_SCAN: {len(skipped)} document(s): {', '.join(skipped)}")
    if failed:
        log(f"INCOMPLETE: {len(failed)} document(s) failed: {', '.join(failed)}")
    if stubs or failed or partials:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
