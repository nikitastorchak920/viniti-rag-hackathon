# RAG extraction roadmap

## Phase 1 · Jury-ready working MVP

Deliver a complete seven-table `out_dev/` bundle, a working local explorer, and a passport that describes the verified data. The operator reviews a demo checkpoint after each task.

- [ ] **1.1 Pipeline stability and clean dev run.** Verify that D002, D009, D013, and D021 finish with numeric rows and that all 21 dev publications are accounted for. Verify that failure and skip placeholders remain visible, count as unresolved scope, and block MVP sign-off. The local cache rebuild processed 17 publications and flagged four. The checker reported zero structural errors and 273 review items. Live OCR and source checks are queued as `MVP-DEV-001` in `handoff/FOR_ANTIGRAVITY.md`. Read the matching report in `handoff/FROM_ANTIGRAVITY.md` when it arrives.
  - **Demo checkpoint.** Rebuild from cache, then run `python tools/check_submission.py out_dev dev --ocr`. Show the per-paper status, extracted counts for the four IDs, and the checker result. Resolve review findings before a clean pass.
- [x] **1.2 Interactive explorer and dataset passport.** Verified the rebuilt seven-table bundle in Microsoft Edge, including combined paper/dataset/metric filters, issue filtering, source pages and quotes, and the four unprocessed flags. `DATASET_PASSPORT.md` records measured partial-cache statistics, provenance, and validation findings. Refresh the counts at sign-off after teammate verification.
  - **Demo checkpoint.** Run `python scripts/serve_ui.py out_dev`, open `http://127.0.0.1:8000/`, and show a filtered result with its source quote and an issue. Compare UI row counts with the validation report.
- [ ] **1.3 MVP sign-off.** Confirm the complete `out_dev/` package for all 21 dev PDFs, a clean checker result, working local UI, and an up-to-date passport. Obtain the operator's sign-off before Phase 2.
  - **Demo checkpoint.** Rebuild the verified package without API use and repeat the jury walkthrough from the delivered bundle.

## Phase 2 · Strict F1 and final defense

Close the loose-to-strict matching gap with general rules. Use `dev_gold/` to measure progress and keep cache v2 rebuilds compatible.

- [ ] **2.1 Granular sub-datasets and ablation variants.** Add `dataset_label` and `variant_label` in `schemas.py`, `prompts.py`, and `exporter.py`. Register sub-corpora, splits, and ablation or sweep qualifiers directly from table rows and headers.
  - **Demo checkpoint.** Show distinct entities and valid links for a synthetic table. Rebuild a legacy cache, then compare the same targeted dev IDs with strict/loose F1 and `--show-diffs`.
- [ ] **2.2 Dense table context and ID inheritance.** Preserve the section heading and two pre-table lines inside `[TABLE HEADER CONTEXT...]` when `TruncatedResponseError` splits a page. In `_fill_ids`, carry unambiguous `dataset_id` and `config_id` across sibling rows or columns of the same `source_table`.
  - **Demo checkpoint.** Show a split-table case with intact context and correct links. Confirm that explicit IDs survive, conflicting candidates stay unresolved, and context lines supply no duplicate values or quotations.
- [ ] **2.3 Full test extraction and final defense pack.** After operator approval, process all 111 `test/` PDFs on the teammate laptop and validate `out_test/` against those PDFs. Refresh the dataset passport and local UI demo data. Prepare a jury executive report with coverage, validation results, dev strict/loose F1, and known limitations.
  - **Demo checkpoint.** Show input coverage, a clean checker result, an offline rebuild, and a jury walkthrough using the final local bundle.

Existing foundations include Gemini OCR-to-PDF fallback, DeepSeek scan handling, network retries, zero-row diagnostics, cache-backed extraction and `--show-diffs N`.
