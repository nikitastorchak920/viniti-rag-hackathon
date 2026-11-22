# PROMPT FOR ANTIGRAVITY

After `git pull --ff-only origin main`, run the newest task without a matching report in `handoff/FROM_ANTIGRAVITY.md`. Keep credentials, PDFs, caches, and generated bundles local.

## Open tasks

### STRICT-DEV-PLOT-001 · Audit source-backed plot configuration and safe export scope

Use the full 21-paper dev cache if available and use local PDFs for provenance. Work offline. Leave code, TODO, accepted exports, and the test corpus alone. Codex owns frozen-cache text and table linkage.

1. Start with D014. Find PDF evidence for methods, datasets, generators and conditions in vector panels, especially the input cap, generator-free panels, and repeated views with two independent axes. Distinguish printed evidence from gold naming conventions.
2. Identify the smallest source-supported export slice that could improve Strict precision and recall. Report eligible rows, abstentions and a generalizable decision rule. Include positive and negative cases with page, figure and section locators. Do not infer configurations or point identity from order or gold.
3. If a reproducible isolated candidate already exists, report scored rows, Strict and Loose P/R/F1 and TP, structural errors, and matched citations. A source-only proposal with quantified coverage also completes the audit.

Prepend `## STRICT-DEV-PLOT-001` to `handoff/FROM_ANTIGRAVITY.md` with the tested commit, status, acceptance result, and evidence. Commit and push that report alone.

### RECALL-DEV-003 · Suspended · Verify default table recovery and build a plot correspondence audit

Use the same complete 21-paper `out_dev_domain2_scan_cache` and the existing `out_dev_recall21_candidate` vector export from RECALL-DEV-001. Use zero API tokens. Leave `out_dev/`, the comparison bundles, the configured provider and the 111-paper test set alone. Do not edit source files.

```powershell
git pull --ff-only origin main
git rev-parse --short HEAD
if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) {
    $env:Path = "C:\Program Files\Tesseract-OCR;$env:Path"
}
if (!(Test-Path out_dev_domain2_scan_cache)) {
    throw 'Use the same full cache as RECALL-DEV-002.'
}
python main.py --input dev --cache out_dev_domain2_scan_cache --output out_dev_recall21_adopted --rebuild-csv-only --ocr
Write-Output "Rebuild exit $LASTEXITCODE"
python tools/check_submission.py out_dev_recall21_adopted dev --ocr --json-report out_dev_recall21_adopted/validation.json
Write-Output "Checker exit $LASTEXITCODE"
python scripts/evaluate.py out_dev_recall21_adopted dev_gold --show-diffs 0
Write-Output "Evaluator exit $LASTEXITCODE"
```

1. Confirm that a rebuild with no recovery flags reproduces the previous table-only benchmark (`out_dev_recall21_table`): 21 processed papers, 5,113 result rows, 4,945 scored predictions, 741 Strict TP, 1,854 Loose TP and zero structural errors. Compare all seven CSVs with the prior table-only bundle if available and summarize any differences. Note checker review counts separately and record any OCR failures. Confirm `--no-recover-table-cells` is available in the help output; its behavior was tested on the Codex laptop.
2. Use D014 Figures 3 and 10 to test **point-level** correspondence for a source-confirmed shared series. Start with the three Figure 3 panels for the same dataset and generator and compare their repeated Answer F1 values. Compare a cross-figure pair sharing two calibrated measures if available. Use exported coordinates or native drawing coordinates. For each pair, report panel and metric locators, whether the PDF identifies the same runs, marker counts, value collisions, unique matches versus equally plausible matches at the actual calibration precision, and whether a second measure or documented marker identity resolves those ties. Keep drawing order as an observation unless evidence establishes identity. If cross-figure joint alignment is impossible, report the missing evidence.
3. Include a keep case for the Figure 9 selection-cap condition and one for a different dataset or generator. Include one coincident-value example in a single panel. Record why each must remain independent. Report which sampled observations can safely receive a `duplicate_of` link, which should remain unlinked, and how many could be affected. Use gold only for an optional comparison after the source-based audit. Do not manually relabel or remove rows in the benchmark bundles. Defer colorbars and additional axes to a later task.

Prepend `## RECALL-DEV-003` under Reports in `handoff/FROM_ANTIGRAVITY.md`. Record the tested commit, status, metrics, and a compact correspondence matrix with PDF locators, confidence limits and any blockers. Commit only the report.

```powershell
git add -- handoff/FROM_ANTIGRAVITY.md
git commit --only -m "Report RECALL-DEV-003 default and plot correspondence audit" -- handoff/FROM_ANTIGRAVITY.md
git push origin main
```
