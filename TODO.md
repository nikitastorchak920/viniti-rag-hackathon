# RAG extraction roadmap · Recall first

## Execution and checkpoints

- Continue through independent work after each measurement. Record the fix, before/after predicted rows and Strict/Loose R/P/F1, elapsed time and tokens. Yield when the next step depends on Antigravity's report.
- Record snapshots, commands and results in `handoff/STRICT_F1_STATE.md`. Use the existing cache and an offline rebuild before requesting paid extraction.
- Keep the current LLM and provider configuration while fixing code and prompt coverage losses. Extraction must generalize to all 111 test papers. Gold is for diagnosis and scoring. Avoid paper IDs, benchmark entity names, and gold values in runtime behavior. Preserve cache v2, CSV schemas, and evaluator keys.

## Reference

- Full 21-paper Domain 2 report `4b77325` for code `b5cb065`: 4,922 scored predictions and 19,392 gold rows. Strict R/P/F1 **0.030/0.118/0.048** (579 TP). Loose R/P/F1 **0.089/0.350/0.142** (1,721 TP). Zero structural errors.
- Latest full-cache report [RECALL-DEV-001](handoff/FROM_ANTIGRAVITY.md#recall-dev-001) at `676ef1f`, code `dae1acc`: default Strict R/P/F1 **0.038/0.149/0.060** (731 TP, +152 vs Domain 2). Combined recovery Loose R/P/F1 **0.618/0.629/0.623** (11,989 TP). Keep the earlier 17-cache snapshots distinct.

## Stage 1 · Recover valid numeric coverage

- [x] **R1.1 Audit cache/export losses and recover missing native table cells.** Local first-pass windows contain 3,979 raw records and 59 extracted rows are excluded as duplicates. The largest coverage gap is already present in cache. `--recover-table-cells` restores 34 unique PDF table cells without API calls.
- [x] **R1.2 Recover graphical numeric observations.** In D014, 11,643 of 11,760 scored gold rows cite figures. `--recover-plot-points` reads native vector markers on supported linear axes, records approximate values and preserves distinct coincident observations. The combined recovery pilot increased local Loose Recall from 0.06198 to 0.59169 and Strict Recall from 0.02501 to 0.02867. Keep plot recovery opt-in until full-cache verification and more complete strict context.
- [ ] **R1.3 Remove capacity losses in long and dense PDFs.** The extraction prompt now explicitly includes appendix results and preserves baseline cells as rows. Split deduplication keeps distinct values, variants, cutoffs and experiment contexts. Remaining work covers proactive resumable slicing and distinguishing omitted windows from truncated or suspiciously sparse successful windows.
- [x] **R1.4 Verify on the full cache.** Both offline exports covered all 21 papers with zero structural errors. The combined candidate gained 10,147 Loose TP and 10 Strict TP over the default with no per-paper Strict F1 regressions. Corpus Strict F1 declined from 0.060 to 0.039. The paper-by-paper report attributed the Strict gains to table recovery and confirmed the plot gains were Loose-only. Keep both recovery flags optional while isolating the table-only result and auditing plot context.

## Stage 2 · Convert recovered volume into Strict Recall

- [x] Confirm cumulative context gains from positioned table relinking, explicit dataset aliases, and metric abbreviation resolution. The current default gained 152 Strict TP over the previous full-cache reference.
- [ ] **S2.1 Isolate table recovery and audit recoverable plot context.** `RECALL-DEV-002` requests a full-cache table-only run and a source-first plot audit. Use the evidence to decide whether to enable table recovery by default and which plot context can be recovered from titles, legends, captions and methods.
- [ ] **S2.2 Implement source-supported context rules.** Prioritize documented dataset aliases, variants, generator and condition labels. Keep experiment parameters distinct from metric cutoffs. Treat repeated series as potential duplicates only when the complete context agrees. Measure Strict and Loose results against the same full-cache default with separate flags.

## Stage 3 · Improve Precision while preserving Recall

- [ ] Audit false positives, evidence gaps and duplicate flags. Protect genuine distinct conditions. Require the agreed Recall and TP to hold before accepting a precision improvement.
- [ ] After operator approval, run all 111 test papers and refresh the validated CSVs, passport and jury bundle. Keep test outside the dev iteration loop.
