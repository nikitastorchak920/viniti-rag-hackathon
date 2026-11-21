# PROMPT FOR ANTIGRAVITY

After `git pull --ff-only origin main`, read this queue and `handoff/FROM_ANTIGRAVITY.md`. Tasks are listed newest first. Run the first task without a report for its ID. If the queue is empty or every ID already has a report, wait for a new task.

To finish a task, prepend an English report with the same ID to `handoff/FROM_ANTIGRAVITY.md`. Use `complete` or `blocked` and record whether the acceptance check passed. Commit and push only the report:

```powershell
git add -- handoff/FROM_ANTIGRAVITY.md
git diff --cached --name-only
git commit --only -m "Report <task ID> verification" -- handoff/FROM_ANTIGRAVITY.md
git push origin main
```

If `main` advanced, run `git pull --rebase origin main` and retry. Preserve existing reports. Keep credentials, PDFs, caches, generated bundles, and full logs local.

## Open tasks

### PHASE2-DEV-001 · Compare the Phase 2 changes on the existing dev cache

Use the 21-paper dev cache from `MVP-DEV-001`. Keep the accepted `out_dev/` bundle as the demo baseline and write the comparison to `out_dev_phase2/`. Use PowerShell from the repository root with the project Python environment active.

```powershell
git pull --ff-only origin main
git rev-parse --short HEAD
if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) {
    $env:Path = "C:\Program Files\Tesseract-OCR;$env:Path"
}
tesseract --version
python -m pytest tests/test_core.py
$LASTEXITCODE
python main.py --input dev --output out_dev_phase2 --rebuild-csv-only --ocr
$LASTEXITCODE
python tools/check_submission.py out_dev_phase2 dev --ocr --json-report out_dev_phase2/validation.json
$LASTEXITCODE
python scripts/evaluate.py out_dev_phase2 dev_gold --show-diffs 10
$LASTEXITCODE
```

The rebuild, OCR, checker, and tests must use zero API tokens. Keep all live extraction and `test/` runs out of this task. If Tesseract remains unavailable, report the blocker.

Compare the new report to the accepted baseline: 21 publications, zero structural errors, 5,058 result rows, 6,650/7,062 confirmed quotes (412 unresolved), 541 missing result links, strict F1 0.043 (519 TP), and loose F1 0.144 (1,756 TP). Report the new totals and their deltas. Verify that OCR quote repair preserves the declared pages and numeric values; inspect examples from D002, D013, and D021. Separate remaining OCR mismatches from source text that the checker never verified. Check the synthetic DeepSeek output-limit and recursive-split tests through pytest; skip a live replay. If a count decreases, identify the affected paper and check whether quote repair made distinct source locations look like duplicates.

Post the report under `PHASE2-DEV-001` in `handoff/FROM_ANTIGRAVITY.md`. Include commit, commands and exit codes, 21-paper coverage, structural errors, per-scan quote coverage, total review counts, strict and loose F1/TP, and observed regressions. Treat checker exit code 2 as unresolved review evidence.
