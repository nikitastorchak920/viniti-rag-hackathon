# PROMPT FOR ANTIGRAVITY

After `git pull --ff-only origin main`, read this queue and `handoff/FROM_ANTIGRAVITY.md`. Run the newest task without a matching report. If no such task exists, wait for a new one.

Prepend an English report with the task ID to `handoff/FROM_ANTIGRAVITY.md` and push that file alone to `origin/main`. Use status `complete` or `blocked`, with acceptance and evidence recorded separately. If the branch advanced, rebase and preserve existing replies. Keep credentials, PDFs, caches, generated bundles, and full logs local.

## Open tasks

### DOMAIN2-DEV-001 · Verify the Domain 2 audit changes and re-extract the three scans

Use the project Python environment in PowerShell. Preserve the accepted `out_dev/` bundle and original `cache/` until both stages have results. This task supersedes the unreported `PHASE2-DEV-001` comparison.

1. **Zero-token checkpoint.** Use the existing full dev cache. Record the commit, all exit codes, row counts, strict/loose TP and F1, the missing-reference breakdown, and the issue quote counts. A checker exit code 2 means review is pending.

   ```powershell
   git pull origin main
   git rev-parse --short HEAD
   python -m pytest tests/test_core.py
   python main.py --input dev --output out_dev_domain2 --rebuild-csv-only
   python tools/check_submission.py out_dev_domain2 dev --json-report out_dev_domain2/validation.json
   python scripts/evaluate.py out_dev_domain2 dev_gold --show-diffs 20
   ```

2. **Targeted live OCR + DeepSeek.** Verify Tesseract is on PATH. Make sure the local environment selects DeepSeek and confirm the CLI log names `DeepSeekClient`. Keep credentials private. Copy the complete cache to a fresh scratch folder. Force only D002, D013, and D021. The shared OCR profile is 300 dpi, RGB, PSM 3.

   ```powershell
   if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) {
       $env:Path = "C:\Program Files\Tesseract-OCR;$env:Path"
   }
   tesseract --version
   $scanCache = 'out_dev_domain2_scan_cache'
   if (Test-Path $scanCache) { throw 'Choose a fresh scratch cache directory before running the targeted extraction.' }
   New-Item -ItemType Directory $scanCache | Out-Null
   Copy-Item -Path cache/*.json -Destination $scanCache
   python main.py --input dev --output out_dev_domain2_scan_retry --cache $scanCache --only D002 D013 D021 --force --ocr --workers 1
   $scanExit = $LASTEXITCODE
   if ($scanExit -ne 0) { throw 'Keep the scratch cache and report the failure. Leave the accepted bundle intact.' }
   python main.py --input dev --output out_dev --cache $scanCache --rebuild-csv-only --ocr
   python tools/check_submission.py out_dev dev --ocr --json-report out_dev/validation.json
   python scripts/evaluate.py out_dev dev_gold --show-diffs 20
   python scripts/serve_ui.py out_dev
   ```

3. **Demo and report.** Open `http://127.0.0.1:8000/`. Show an exact-context comparison with a signed baseline delta, a result with raw and normalized values and a source quote, one `RULE_*` filter, and the Data Passport tab. In `DOMAIN2-DEV-001`, report the stage 1 and stage 2 deltas against `MVP-DEV-001`, the three scan IDs' mode/row counts/quote coverage, total API tokens, and parser, checker, or UI regressions. Distinguish issue quotes cleared as unverified from newly confirmed OCR evidence. Skip the 111-paper test run.

   ```powershell
   git add -- handoff/FROM_ANTIGRAVITY.md
   git commit --only -m "Report DOMAIN2-DEV-001 verification" -- handoff/FROM_ANTIGRAVITY.md
   git push origin main
   ```
