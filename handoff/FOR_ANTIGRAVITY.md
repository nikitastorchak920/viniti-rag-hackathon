# PROMPT FOR ANTIGRAVITY

Verify the Phase 1 MVP on the laptop that has the 21 dev PDFs, local credentials, and Tesseract. Use PowerShell from the repository root with the project environment active. Leave source files untouched and keep credentials, PDFs, caches, generated bundles, and full logs local. The operator will relay your English report.

1. Sync and record the versions. Use Gemini if available for the PDF fallback.

   ```powershell
   git pull --ff-only origin main
   git rev-parse --short HEAD
   python --version
   tesseract --version
   ```

   Check that `python -c "import pytesseract; print(pytesseract.get_tesseract_version())"` succeeds. If the Python package is missing, run `python -m pip install pytesseract`. If Tesseract is outside PATH, add its install directory to the current PowerShell session's PATH. The checker also accepts the executable path via `--tesseract`.

2. Rebuild the full dev preview first. This command uses zero API tokens. Capture its exit code and the unresolved IDs. On exit 1, use the generated preview if available.

   ```powershell
   python main.py --input dev --output out_dev --rebuild-csv-only
   $LASTEXITCODE
   ```

3. If D002, D009, D013, or D021 are unresolved, retry only those IDs with `--ocr` and `--workers 1`. For example, if all four are unresolved:

   ```powershell
   python main.py --input dev --output out_dev_retry --only D002 D009 D013 D021 --ocr --workers 1
   $LASTEXITCODE
   ```

   Omit IDs already healthy. The targeted command resumes partial caches. If an ID reports `cached` but its export still has no numeric rows or has an incorrect scope decision, rerun only that ID with `--force`. For example, for D021 alone: `python main.py --input dev --output out_dev_retry --only D021 --force --ocr --workers 1`. Record the selected OCR/PDF mode, token totals, and raw/numeric row counts. For a persistent transport error, capture a short redacted excerpt and preserve partial progress. Keep `test/` for Phase 2.

4. Rebuild the full bundle and capture each exit code. A checker exit code 2 means review is still pending even with zero structural errors. Do not mark the MVP clean until the checker passes and every dev paper has a resolved extraction status. Report review findings with the relevant paper/row and category.

   ```powershell
   python main.py --input dev --output out_dev --rebuild-csv-only
   $LASTEXITCODE
   python tools/check_submission.py out_dev dev --ocr --json-report out_dev/validation.json
   $LASTEXITCODE
   python scripts/evaluate.py out_dev dev_gold --show-diffs 5
   $LASTEXITCODE
   ```

   Count exported numeric rows for each target paper:

   ```powershell
   $rows = Import-Csv out_dev/results.csv
   foreach ($paper in 'D002','D009','D013','D021') {
       $count = @($rows | Where-Object { $_.publication_id -eq $paper -and $_.extraction_status -eq 'extracted' -and $_.metric_value -ne '' }).Count
       "${paper}: $count exported numeric rows"
   }
   ```

5. Start `python scripts/serve_ui.py out_dev` and open `http://127.0.0.1:8000/`. In `results`, combine paper, dataset, and metric filters, then open a row and check the PDF page and a source quote. In `issues`, filter by rule. In `publications`, verify the unprocessed filter is empty for a complete bundle. Compare the table counts with `out_dev/validation.json`.

6. Fill `handoff/FROM_ANTIGRAVITY.md` in English and relay it to the operator. Include mode and numeric row counts for each of the four target papers, counts for all seven tables, unresolved IDs, structural errors, review categories, quote counts, evaluator strict and loose TP/F1, and the UI checkpoint. Summarize any blockers with short redacted excerpts.
