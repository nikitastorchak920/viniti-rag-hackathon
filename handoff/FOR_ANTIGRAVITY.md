# PROMPT FOR ANTIGRAVITY

After `git pull --ff-only origin main`, read this queue and `handoff/FROM_ANTIGRAVITY.md`. Run the newest task without a matching report. If none is pending, wait. Keep credentials, PDFs, caches, generated bundles, and full logs local.

## Open tasks

**Paused at P0.1.** Read `handoff/STRICT_F1_STATE.md` for the completed offline audit. Wait for operator approval before starting the queued task below or any extraction changes. The next proposed implementation is P0.2 in `TODO.md`.

### STRICT-DEV-001 · Audit dense-table coverage and compare the two D013 caches

Work from the project Python environment in PowerShell. This is a **zero-token** checkpoint. Preserve the accepted `out_dev/`, `cache/`, and `out_dev_domain2_scan_cache/`. Use fresh output folders. Skip live extraction and the 111-paper test run.

1. **Find where D014 loses coverage.** Measure D014 separately. The latest report shows 91 scored predictions against 11,760 gold tuples and zero Strict TP. Compare the exported and gold row counts grouped by PDF page and table. For the three largest gaps, inspect the original PDF locally and report the PDF page, table or figure label, visible row/column axes, numerical density, and whether the existing cache window returned zero rows, sampled a large table, or emitted rows with mismatched context. Distinguish a genuine missed table from repeated or analysis-heavy gold rows. Propose the smallest generic extraction intervention and the exact pages or windows to target. Use gold only to measure the gaps.

   ```powershell
   git pull --ff-only origin main
   git rev-parse --short HEAD
   python scripts/evaluate.py out_dev dev_gold --only D014 --show-diffs 20
   ```

2. **Measure the D013 regression under the same OCR checker.** The old cache retained 28 Strict TP and the live OCR cache retained 2. Rebuild both with the current code and the same Tesseract settings. Use a one-PDF input folder for the checker so a scoped export does not create spurious missing-publication errors.

   ```powershell
   if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) {
       $env:Path = "C:\Program Files\Tesseract-OCR;$env:Path"
   }
   tesseract --version
   $d013Input = 'out_dev_strict_d013_input'
   New-Item -ItemType Directory -Path $d013Input -Force | Out-Null
   Copy-Item -LiteralPath dev/D013.pdf -Destination $d013Input
   python main.py --input $d013Input --output out_dev_strict_d013_old --cache cache --rebuild-csv-only --ocr
   python main.py --input $d013Input --output out_dev_strict_d013_live --cache out_dev_domain2_scan_cache --rebuild-csv-only --ocr
   foreach ($bundle in 'out_dev_strict_d013_old','out_dev_strict_d013_live') {
       python tools/check_submission.py $bundle $d013Input --ocr --json-report "$bundle/validation.json"
       $LASTEXITCODE
       python scripts/evaluate.py $bundle dev_gold --only D013 --show-diffs 20
       $LASTEXITCODE
   }
   ```

   Compare numeric rows, strict and loose TP/F1, matched/requested quotes, and missing IDs by field. Identify whether the old cache preserves strict matches under the current OCR verifier and summarize where the newer extraction lost valid rows. Report the trade-off without promoting either cache.

3. **Publish evidence.** Prepend `## STRICT-DEV-001` to `handoff/FROM_ANTIGRAVITY.md` with the tested commit, status, command exit codes, D014 page/table gap summary, D013 comparison, and recommended next experiment. Use short redacted examples. Push only that file:

   ```powershell
   git add -- handoff/FROM_ANTIGRAVITY.md
   git commit --only -m "Report STRICT-DEV-001 verification" -- handoff/FROM_ANTIGRAVITY.md
   git push origin main
   ```

If `main` advanced, rebase and preserve existing replies. Report blockers if a required cache or Tesseract is missing.
