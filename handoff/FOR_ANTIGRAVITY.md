# PROMPT FOR ANTIGRAVITY

After `git pull --ff-only origin main`, run the newest task without a matching report in `handoff/FROM_ANTIGRAVITY.md`. Keep credentials, PDFs, caches, and generated bundles local.

## Open tasks

### RECALL-DEV-002 · Isolate table gains and trace plot conditions to source evidence

Use the complete 21-paper `out_dev_domain2_scan_cache` from RECALL-DEV-001. Spend zero API tokens. Keep the jury `out_dev/` and the previous comparison bundles intact. Leave the provider and the 111-paper test set untouched.

```powershell
git pull --ff-only origin main
git rev-parse --short HEAD
if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) {
    $env:Path = "C:\Program Files\Tesseract-OCR;$env:Path"
}
if (!(Test-Path out_dev_domain2_scan_cache)) {
    throw 'The benchmark requires the same full cache as RECALL-DEV-001.'
}
python main.py --input dev --cache out_dev_domain2_scan_cache --output out_dev_recall21_table --rebuild-csv-only --ocr --recover-table-cells
Write-Output "Rebuild exit $LASTEXITCODE"
python tools/check_submission.py out_dev_recall21_table dev --ocr --json-report out_dev_recall21_table/validation.json
Write-Output "Checker exit $LASTEXITCODE"
python scripts/evaluate.py out_dev_recall21_table dev_gold --show-diffs 20
Write-Output "Evaluator exit $LASTEXITCODE"
```

1. Compare the table-only run with the recorded default (4,911 scored predictions, 731 Strict TP, 1,842 Loose TP, 550 review items). Report document coverage, exit codes, wall time, scored predictions, Strict and Loose P/R/F1 and TP, structural errors, new reviews, changed papers, and the source page and table for added Strict matches. Table recovery is eligible for default adoption if the full run has zero structural errors, higher corpus Strict F1, and no per-paper Strict F1 or Loose TP loss. Report observed results even if this gate fails.
2. Use the existing candidate bundle and native PDF to produce a small source-evidence matrix for D014 Figures 2, 3, 5, 8, 9 and 10. For each figure, choose a representative panel and record PDF page, panel title or axis/panel locator, the applicable legend/caption/method locator, and the scope of each printed label (whole figure, panel, group, or point). Check whether PDF text extraction preserves the label and whether a legend style can be linked unambiguously to markers. Report a specific repeated-series pair and whether the source confirms the same conditions or only matching values. For Figure 9, determine whether its printed selection limit defines an experiment setting, a metric cutoff, or has unresolved semantics. For Figures 5 and 8, check if nearby text establishes the missing task/dataset relationship or generator and applies to the exact panel.
3. Complete the source matrix before consulting gold. Then compare representative rows against the proposed Strict keys and classify gaps as source-supported exact labels, explicit aliases, unsupported metadata, ambiguous grouping, or unlabeled plot values. Cite PDF locations for alias and variant claims. For context the PDF does not establish, record an empty value and the reason. Report whether precision work on repeated series or recovering missing axes/colorbars should follow the context fix, with evidence from the sampled panels.

Prepend `## RECALL-DEV-002` under Reports in `handoff/FROM_ANTIGRAVITY.md`. Include the status, tested commit, table-only metrics, and a concise evidence matrix with redacted excerpts or locators. Preserve earlier reports. If an input is unavailable, report what could be verified and the blocker. Commit only the report.

```powershell
git add -- handoff/FROM_ANTIGRAVITY.md
git commit --only -m "Report RECALL-DEV-002 table and plot context audit" -- handoff/FROM_ANTIGRAVITY.md
git push origin main
```
