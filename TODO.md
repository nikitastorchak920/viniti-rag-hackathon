# RAG extraction roadmap · Recall first

## Checkpoint protocol

- Execute one numbered step per approval. Stop after resolving a systemic leak or measuring a Recall/F1 gain. Report the fix, before/after predicted rows and Strict/Loose R/P/F1, elapsed time and API tokens, and the proposed next step.
- Record snapshots, commands and results in `handoff/STRICT_F1_STATE.md`. Keep Antigravity's queue paused between approvals. Use the existing cache and an offline rebuild before requesting paid extraction.
- Keep the current LLM and provider configuration while fixing code and prompt coverage losses. Extraction must generalize to all 111 test papers. Gold is for diagnosis and scoring. Avoid paper IDs, benchmark entity names, and gold values in runtime behavior. Preserve cache v2, CSV schemas, and evaluator keys.

## Reference

- Full 21-paper Domain 2 report `4b77325` for code `b5cb065`: 4,922 scored predictions and 19,392 gold rows. Strict R/P/F1 **0.030/0.118/0.048** (579 TP). Loose R/P/F1 **0.089/0.350/0.142** (1,721 TP). Zero structural errors.
- Current local comparison uses the same 17 complete caches scored against all 21 gold papers. Keep the local and full snapshots distinct. Prior context gains through P0.3a are recorded in the state file.

## Stage 1 · Recover valid numeric coverage

- [x] **R1.1 Audit cache/export losses and recover missing native table cells.** Local first-pass windows contain 3,979 raw records and only 59 extracted rows are excluded as duplicates. The largest coverage gap is already present in cache. The new opt-in `--recover-table-cells` restores 34 unambiguous PDF table cells without API calls. Exact Strict and Loose Recall stayed unchanged because the table uses short metric labels that differ from gold. The standard export remains byte-identical to the previous one. **Checkpoint awaiting approval.**
- [ ] **R1.2 Audit graphical numeric coverage.** The largest gap is not explained by table chunking alone. In D014, 11,643 of 11,760 scored gold rows cite figures. Inspect recoverability from native PDF vector paths, chart axes and legends on a small sample, separating chart points from tick labels and repeated panels. Verify the printed scale and source location. Decide whether reliable vector recovery or bounded visual windows are justified before extracting thousands of points. Stop with a reproducible coverage estimate.
- [ ] **R1.3 Remove capacity losses in long and dense PDFs.** Detect eligible tables, figures, and appendices before extraction and distinguish omitted windows, truncated responses, and suspiciously sparse successful windows. Remove prompt wording that can suppress appendix results and avoid folding explicit baseline rows into a scalar baseline. Segment wide or layered tables into resumable slices with shared headers. Fix split deduplication so distinct metric variants, cutoffs and result contexts survive. Implement and measure each leak in its own checkpoint.
- [ ] **R1.4 Run one approved extraction pilot.** Start from the existing model and cache. Use the smallest set of slices the offline audit identifies. Measure unique valid cells, Loose Recall, tokens and latency. Expand only after a measured gain and approval.

## Stage 2 · Convert recovered volume into Strict Recall

- [x] Existing context work: positioned table relinking (P0.2) and explicit dataset aliases (P0.3a) raised local Strict TP from 394 to 485. Full-cache confirmation remains pending.
- [ ] Recover missing source-supported dataset, variant, and generator entities. Inherit labels and cutoffs only from the matching caption, headers and row/column group. Normalize explicit metric abbreviations and aliases against the source. Keep ambiguous links empty. Benchmark fixed Strict/Loose keys on the same cache and stop after each change.

## Stage 3 · Improve Precision while preserving Recall

- [ ] Audit false positives, evidence gaps and duplicate flags. Protect genuine distinct conditions. Require the agreed Recall and TP to hold before accepting a precision improvement.
- [ ] After operator approval, run all 111 test papers and refresh the validated CSVs, passport and jury bundle. Keep test outside the dev iteration loop.
