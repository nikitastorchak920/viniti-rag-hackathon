# RAG extraction roadmap

## Checkpoint protocol

- Work on one numbered task at a time. Stop after a completed task, a systemic fix, or a measured gain. The next task requires operator approval.
- At each stop, record the change, data and code revision, and before/after Strict P/R/F1 and Loose P/R/F1 on the same snapshot. Include TP, predictions, gold rows, and the proposed next task. Record results in `handoff/STRICT_F1_STATE.md` and keep Antigravity's task status in `handoff/FOR_ANTIGRAVITY.md`.
- Use existing version-2 caches and an offline rebuild first. Gold data is a diagnostic and scoring input. Extraction, normalization, and linking use source evidence and general rules. Paper IDs may select audit samples, never determine behavior.
- Measure full-corpus Strict F1 with the existing evaluator and fixed scoring keys. Track Loose F1, per-paper regressions, missing references, and structural errors alongside it. Compare both versions on the same cache and scope. Paid extraction follows an approved offline checkpoint.

## Accepted baseline

- [x] **Phase 1 and Domain 2 demo.** The 21-paper bundle and dashboard passed. Report `4b77325` for code `b5cb065` has 7,747/7,776 confirmed quotes (99.63%) and zero structural errors. The checker returned 2 with 521 missing links and 29 unresolved quotes.
- Full dev after OCR: **Strict P/R/F1 0.118/0.030/0.048 (579 TP)**, **Loose P/R/F1 0.350/0.089/0.142 (1,721 TP)**. Both score 4,922 predictions against 19,392 gold rows. Strict F1 excluding the largest paper is 0.093.
- The completed Domain 2 work includes shared OCR settings, output-cap handling, validation rules, exact-context UI comparison, and the dataset passport.

## P0 · Recover Strict context from existing evidence

- [x] **P0.1 Audit Loose versus Strict with the existing cache.** The full report has 1,142 Loose-only matches and 11 papers with zero Strict TP. On the local 17-paper cache scored against all 21 gold papers, Strict P/R/F1 was 0.10129/0.02032/0.03385 (394 TP) and Loose was 0.31003/0.06219/0.10360 (1,206 TP). Diagnostic projections and the code trace are in `handoff/STRICT_F1_STATE.md`. No extraction changes or API calls were made. **Checkpoint awaiting approval.**
- [ ] **P0.2 Fix evidence-backed inheritance of existing strict keys on cached rows.** Start with dataset row/column axes, then verify the joint RAG variant and generator mapping in the same linking change. Scope evidence to publication, page/table or a demonstrably continued table, and row/column group. Resolve an ID only when the source anchors one candidate. Preserve explicit links unless source evidence establishes a correction. Keep cross-table conflicts and generic numeric coincidences unresolved. Apply explicit `metric_k` only to the matching metric header. Check known-entity matches, collisions, conflict handling, cache v2, and strict gain on the same snapshot. Stop after the offline comparison.
- [ ] **P0.3 Recover source-supported entities and aliases missing from cached metadata.** Audit residuals after P0.2 and preserve verbatim dataset, variant, and generator labels with scope and provenance. Use exact-equivalent normalization and explicit table hierarchy. Add optional result labels only when existing cache evidence cannot represent a context and keep older caches readable. Measure each isolated change before authorizing a targeted re-extraction. Keep the evaluator unchanged.

## P1 · Recover numeric coverage in long or dense documents

- [ ] **P1.1 Audit page/table coverage before changing chunking.** Compare cache windows and output rows with actual page/table inventory, separating omitted windows, sparse windows that completed, and parser failures. Include appendices and multi-level tables. The largest dev paper has 91 predictions against 11,760 gold tuples, making coverage a meaningful corpus-wide constraint. Record the cause and bounded recovery plan before a live run.
- [ ] **P1.2 Make dense extraction resumable and validate a bounded recovery.** Split proactively by table and row/column groups, retain shared headers and provenance, and track empty/suspicious windows separately from verified completion. Retry only the unfinished slice on a provider limit. Treat appendix tables as candidates. Use cache-only fixtures and then one approved targeted pilot, preserving the previous demo bundle. Stop after comparing throughput, new unique valid values, token use, and full-corpus Strict/Loose metrics.

## P2 · Improve precision and reduce noise after recall work

- [ ] **P2.1 Audit false positives, duplicate links, and missing references on the updated cache.** Distinguish repeated normalized rows, valid distinct conditions, and unsupported value or context associations. Preserve legitimate distinct experiments and observations. Measure precision and recall impact together, confirm no structural regression, then stop.

## Release gates

- **Before any live pilot:** use an authorized official DeepSeek credential with `DEEPSEEK_BASE_URL=https://api.deepseek.com` and `DEEPSEEK_MODEL=deepseek-flash`. The tracked default matches DeepSeek-V4.1-Flash-1017. The local override still uses a third-party gateway and the legacy alias. Verify provider, model alias, and backend selection on the execution machine before spending tokens. See [DeepSeek model details](https://api-docs.deepseek.com/quick_start/pricing/).
- [ ] **Full test and defense.** After explicit approval, run the 111-paper test set on the validated configuration, check the seven CSVs, and refresh the passport and jury bundle. Keep the full test set outside the dev iteration loop.
