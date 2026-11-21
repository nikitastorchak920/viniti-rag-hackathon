# RAG extraction roadmap · Recall first

## Execution and checkpoints

- Continue through independent work after each measurement. Record the fix, before/after predicted rows and Strict/Loose R/P/F1, elapsed time and tokens. Yield when the next step depends on Antigravity's report.
- Record snapshots, commands and results in `handoff/STRICT_F1_STATE.md`. Use the existing cache and an offline rebuild before requesting paid extraction.
- Keep the current LLM and provider configuration while fixing code and prompt coverage losses. Extraction must generalize to all 111 test papers. Gold is for diagnosis and scoring. Avoid paper IDs, benchmark entity names, and gold values in runtime behavior. Preserve cache v2, CSV schemas, and evaluator keys.

## Reference

- Full 21-paper Domain 2 report `4b77325` for code `b5cb065`: 4,922 scored predictions and 19,392 gold rows. Strict R/P/F1 **0.030/0.118/0.048** (579 TP). Loose R/P/F1 **0.089/0.350/0.142** (1,721 TP). Zero structural errors.
- Current local comparison uses the same 17 complete caches scored against all 21 gold papers. Keep the local and full snapshots distinct. Prior context gains through P0.3a are recorded in the state file.

## Stage 1 · Recover valid numeric coverage

- [x] **R1.1 Audit cache/export losses and recover missing native table cells.** Local first-pass windows contain 3,979 raw records and 59 extracted rows are excluded as duplicates. The largest coverage gap is already present in cache. `--recover-table-cells` restores 34 unique PDF table cells without API calls.
- [x] **R1.2 Recover graphical numeric observations.** In D014, 11,643 of 11,760 scored gold rows cite figures. `--recover-plot-points` reads native vector markers on supported linear axes, records approximate values and preserves distinct coincident observations. The combined recovery pilot increased local Loose Recall from 0.06198 to 0.59169 and Strict Recall from 0.02501 to 0.02867. Keep plot recovery opt-in until full-cache verification and more complete strict context.
- [ ] **R1.3 Remove capacity losses in long and dense PDFs.** The extraction prompt now explicitly includes appendix results and preserves baseline cells as rows. Split deduplication keeps distinct values, variants, cutoffs and experiment contexts. Remaining work covers proactive resumable slicing and distinguishing omitted windows from truncated or suspiciously sparse successful windows.
- [ ] **R1.4 Verify on the full cache and scope the next pilot.** `RECALL-DEV-001` asks Antigravity for a zero-token 21-paper comparison and independent plot checks. Use that report to decide whether a targeted live extraction is justified. No provider change or test-set run is part of the current task.

## Stage 2 · Convert recovered volume into Strict Recall

- [x] Existing context work: positioned table relinking (P0.2) and explicit dataset aliases (P0.3a) raised local Strict TP from 394 to 485. Full-cache confirmation remains pending.
- [ ] Recover missing source-supported dataset, variant, and generator entities. The default exporter now expands uniquely defined metric abbreviations and gains 61 Strict TP and 125 Loose TP locally without increasing predictions. The plot pilot links generator-only configurations where supported by printed titles. Point-level retrieval context remains empty when absent from the figure. Compare fixed keys on the full cache before expanding these paths.

## Stage 3 · Improve Precision while preserving Recall

- [ ] Audit false positives, evidence gaps and duplicate flags. Protect genuine distinct conditions. Require the agreed Recall and TP to hold before accepting a precision improvement.
- [ ] After operator approval, run all 111 test papers and refresh the validated CSVs, passport and jury bundle. Keep test outside the dev iteration loop.
