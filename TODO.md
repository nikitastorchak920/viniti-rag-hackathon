# RAG extraction roadmap

## Phase 1 · Jury-ready working MVP

Deliver a complete seven-table `out_dev/` bundle, a working local explorer, and a passport that describes the verified data. The operator reviews a demo checkpoint after each task.

- [x] **1.1 Pipeline stability and dev bundle.** `MVP-DEV-001` (`455b5d6`) confirms 21/21 dev PDFs, no stubs, rebuild exit code 0, and zero structural errors. D002, D009, D013, and D021 exported 216, 612, 235, and 20 numeric rows respectively. Checker exit code 2 leaves 412 unresolved quotes and 541 missing primary-result links for Phase 2.
  - **Demo checkpoint.** The cache-only rebuild reproduced the complete dev bundle. The validator and dashboard expose outstanding review findings.
- [x] **1.2 Interactive explorer and dataset passport.** Verified the rebuilt seven-table bundle in Microsoft Edge, including combined paper/dataset/metric filters, issue filtering, source pages and quotes, and the four unprocessed flags in the local preview. Antigravity confirmed the UI counts for the full dev bundle. `DATASET_PASSPORT.md` now records those totals, provenance, and validation findings.
  - **Jury dashboard upgrade.** `MVP-UI-001` (`60129ff`) passed on the full bundle with zero console errors or failed requests. The reporter confirmed four KPIs, search, filters, and the source drawer with linked issues.
  - **Demo checkpoint.** Run `python scripts/serve_ui.py out_dev`, open `http://127.0.0.1:8000/`, and show a filtered result with its source quote and an issue. Compare UI row counts with the validation report.
- [x] **1.3 MVP sign-off.** The operator accepted the complete 21/21 dev bundle and jury dashboard. The dataset passport records the accepted counts, checker review findings, and F1 baseline.

## Phase 2 · Strict F1 and final defense

Close the loose-to-strict matching gap with general rules. Use `dev_gold/` to measure progress and keep cache v2 rebuilds compatible.

- [x] **2.0 Reliability fixes.** Extraction and the validator share OCR settings. The offline rebuild can re-ground OCR quotes on their declared page while preserving the metric value and unresolved evidence. DeepSeek sends malformed JSON at its output cap to window splitting and still retries ordinary parse failures below the cap.
- [x] **2.0 verification.** `DOMAIN2-DEV-001` (`4b77325`) verified 21/21 dev publications, zero structural errors, 7,747/7,776 confirmed quotes (99.63%), and all Domain 2 UI checks. Unresolved quotes fell from 412 to 29. Checker exit code 2 reflects 521 missing primary-result references and 29 unresolved scan quotes. Strict TP rose from 519 to 579 compared with MVP. The cache-only stage scored 605 Strict TP before the live OCR rerun.
- [ ] **2.1 Granular sub-datasets and ablation variants.** Add `dataset_label` and `variant_label` in `schemas.py`, `prompts.py`, and `exporter.py`. Register sub-corpora, splits, and ablation or sweep qualifiers directly from table rows and headers.
  - **Completed preprocessing.** Export separates an explicitly duplicated version suffix from `dataset_name` after linking. Distinct versions and their IDs remain in `dataset_version` and `dataset_id`. On the same local cache with 17 processed papers, strict matches increased from 308 to 328 (all-dev F1 0.02646 to 0.02818), loose matches stayed at 1,202, and structural errors stayed at zero. Full-cache verification is pending.
  - **Domain 2 audit.** Printed family/subset lists now resolve compound labels without changing the entity IDs. Compared with the previous build on the same local cache, strict matches rose from 328 to 394 and loose matches rose from 1,202 to 1,206. D014 contributes 11,760 gold numeric tuples against 91 predictions and remains a separate coverage issue.
  - **Demo checkpoint.** Show distinct entities and valid links for a synthetic table. Rebuild a legacy cache, then compare the same targeted dev IDs with strict/loose F1 and `--show-diffs`.
- [ ] **2.2 Dense table context and ID inheritance.** The splitter preserves the section heading and two pre-table lines across recursive splits. `_fill_ids` now fills `dataset_id` for a table with one uncontested label. Configuration inheritance and multi-dataset row/column context remain open.
  - **Next evidence checkpoint.** `STRICT-DEV-001` maps D014's coverage gaps to concrete PDF pages and runs a zero-token, same-checker A/B comparison of both D013 caches. The accepted dev bundle stays available for the demo.
  - **Demo checkpoint.** Show a split-table case with intact context and correct links. Confirm that explicit IDs survive, conflicting candidates stay unresolved, and context lines supply no duplicate values or quotations.
- [ ] **2.3 Full test extraction and final defense pack.** After operator approval, process all 111 `test/` PDFs on the teammate laptop and validate `out_test/` against those PDFs. Refresh the dataset passport and local UI demo data. Prepare a jury executive report with coverage, validation results, dev strict/loose F1, and known limitations.
  - **Demo checkpoint.** Show input coverage, a clean checker result, an offline rebuild, and a jury walkthrough using the final local bundle.

- [x] **Domain 2 submission surfaces.** The export retains named observations and records structured `RULE_*` findings. The dashboard adds a context-aware baseline comparison, rule filters, evidence details, and a Data Passport view. CSV columns and cache v2 remain compatible.
