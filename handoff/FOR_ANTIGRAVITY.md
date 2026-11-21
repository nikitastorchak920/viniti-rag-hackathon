# PROMPT FOR ANTIGRAVITY

After `git pull --ff-only origin main`, run the newest task without a matching report in `handoff/FROM_ANTIGRAVITY.md`. Keep credentials, PDFs, caches, and generated bundles local. This task supersedes the unreported `STRICT-DEV-001` investigation.

## Open tasks

### RECALL-DEV-001 · Validate offline recall on the full 21-paper cache

Compare the current default export against its optional vector and table recovery. Use the same complete cache in both commands and keep the jury demo `out_dev/` intact. Prefer the complete `out_dev_domain2_scan_cache` from the last handoff; record any fallback to the original full `cache/`. Use zero API tokens. Keep the configured LLM unchanged. Do not run the 111-paper test set.

```powershell
git pull --ff-only origin main
git rev-parse --short HEAD
if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) {
    $env:Path = "C:\Program Files\Tesseract-OCR;$env:Path"
}
$benchCache = 'out_dev_domain2_scan_cache'
if (-not (Test-Path $benchCache)) { $benchCache = 'cache' }
python -m pytest tests/test_core.py
python main.py --input dev --cache $benchCache --output out_dev_recall21_default --rebuild-csv-only --ocr
python main.py --input dev --cache $benchCache --output out_dev_recall21_candidate --rebuild-csv-only --ocr --recover-table-cells --recover-plot-points
foreach ($bundle in 'out_dev_recall21_default','out_dev_recall21_candidate') {
    python tools/check_submission.py $bundle dev --ocr --json-report "$bundle/validation.json"
    Write-Output "Checker exit $LASTEXITCODE"
    python scripts/evaluate.py $bundle dev_gold --show-diffs 20
    Write-Output "Evaluator exit $LASTEXITCODE"
}
```

Record coverage, scored predictions, Strict and Loose R/P/F1 and TP, structural errors, review item categories, runtime, and any per-paper regression. For D014, spot-check several vector observations from at least two figures against printed linear axis ticks and verify that the selected dataset and any credited generator appear in the panel title. The checker only confirms the caption text. Report unsupported context, calibration discrepancies, repeated series, and points without complete configuration separately. Leave the jury bundle untouched.

Prepend `## RECALL-DEV-001` with your findings and tested commit to `handoff/FROM_ANTIGRAVITY.md`. Push only the report. If a local tool or complete cache is missing, report the blocker and whatever evidence is available.

```powershell
git add -- handoff/FROM_ANTIGRAVITY.md
git commit --only -m "Report RECALL-DEV-001 full-cache benchmark" -- handoff/FROM_ANTIGRAVITY.md
git push origin main
```
