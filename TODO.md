# RAG extraction roadmap

## Current checkpoint

- **Owner and queue:** Codex is active. Antigravity is occupied elsewhere. Both handoff queues are read-only until the operator explicitly authorizes changes. On `origin/main`, the newest available Antigravity report is `RECALL-DEV-002` (`96f3c30`). `RECALL-DEV-003` remains suspended.
- **Tested code and artifacts:** `b6c82cc` records the full dev recovery. The working cache and report are local at `out_dev_recovery/cache` and `out_dev_recovery/latest`. `out_dev_recovery/baseline.json` records the input and original cache hashes. Seventeen old local exports moved to `out_dev_recovery/archive`; the map is in `MOVED.txt`. Historical and jury bundles are preserved. These generated paths are ignored by Git.

| Snapshot | Coverage | Scored rows | Strict TP | Strict R/P/F1 | Loose TP | Loose R/P/F1 |
|---|---|---:|---:|---|---:|---|
| D009 recovery checkpoint | 19/21 complete | 4,687 | 814 | 0.04198/0.17367/0.06761 | 1,674 | 0.08632/0.35716/0.13904 |
| Latest full dev export | 21/21 complete | 5,305 | 860 | 0.04435/0.16211/0.06964 | 1,853 | 0.09555/0.34929/0.15006 |

- **Paper status:** D009 resumed from page 7 using its existing entity IDs and both saved windows. It now has 146 Strict and 324 Loose TP. D002's first passport hit the 16,384-token limit. A compact passport completed at the same limit with 3,113 output tokens. D002 is complete with 0 Strict and 57 Loose TP. D013 completed with 46 Strict and 122 Loose TP. The final export has zero stubs, 21/21 scope agreement, and zero structural errors. Both snapshots use the same 19,392 gold observations.
- **Constraints:** Keep RapidOCR at 200 dpi (9/9 on the checked scan row set; 150 dpi gave 8/9). Retain the current gateway's 16,384-token output cap. Keep the configured model, cache v2, seven CSV schemas, and evaluator unchanged. Prefer offline checks. Keep figure recovery opt-in, the frontend untouched, and the 111-paper test corpus out of dev experiments.
- **Handoff preparation verification:** 61 tests passed. Re-evaluation of the existing local export confirmed 860 Strict and 1,853 Loose TP. The ignore rules cover secrets, raw PDFs, local cache archives, generated reports and out bundles. Nothing under `handoff/` was edited in this checkpoint.
- **Active blockers:** The native-text checker left 941 citations unresolved out of 8,188, including pages on scanned PDFs. D014 accounts for 11,760 gold observations and still has zero Strict TP. The vector experiment adds 10,135 Loose TP and zero Strict TP. Its remaining scope and provenance gaps block adoption in the default export. D002 still needs source-backed Strict entity links.
- **Exact next step:** Run the zero-API command below against the existing full dev export. Inspect unresolved citations by paper and page, starting with D002, D013, and D021. Record OCR recovery counts and remaining failures here before making another extraction change. If the local export is absent, first rebuild it from `out_dev_recovery/cache` with `--rebuild-csv-only`.

```powershell
python tools/check_submission.py out_dev_recovery/latest dev --ocr --json-report out_dev_recovery/latest/validation_ocr.json
```

Full evidence is in the [metric audit](METRIC_AUDIT.md#итог-на-полном-dev) and [benchmark log](handoff/STRICT_F1_STATE.md#recovery-plan-execution--21-complete-papers).

## Notes for Antigravity

- Reuse successful page windows with their saved metadata and entity IDs when resuming a legacy extraction. D009 verified that the old plain-text plan can coexist with the current table-first workflow.
- The 16,384-token limit is specific to the configured gateway. Compact passports keep the cache format stable and resolved a metadata truncation before result extraction on D002.
- Verified figure captions establish source location. Point or series identity and configuration require separate evidence. Keep the vector experiment isolated while Strict coverage remains unresolved.

## Notes for Codex

- **Antigravity protocol sync (`2026-11-22`, synced onto `9a2964e`):** Confirmed clean fast-forward sync (`5703e2a..9a2964e`), reviewed `git log -n 5`, `AGENTS.md`, `handoff/FOR_ANTIGRAVITY.md`, and `TODO.md` — including the `19/21` D009 recovery checkpoint (`814` Strict / `1,674` Loose TP), the `21/21` full dev checkpoint (`860` Strict / `1,853` Loose TP), and all `## Notes for Antigravity`. Added the mirror Antigravity sequential/context-reset protocol in `AGENTS.md`.
- **Touched files and verification:** Only `AGENTS.md` and `TODO.md` edited in this checkpoint. Codex-owned code modules and both read-only `handoff/` queue files were left untouched; UI remains paused. Local `unittest` on `tests/test_core.py` passed (`61` tests in `1.71s`, `skipped=1`), and `.gitignore` verified clean (only the 2 intended markdown files modified).
- **Zero-token chart correspondence note (relevant to next chart-provenance priority):** An offline source-only audit on `dev/D014.pdf` + `out_dev_recall21_candidate` (`RECALL-DEV-003` draft preserved locally while `handoff/` queues are read-only) found: (1) all 7 CSVs of `out_dev_recall21_adopted` (`7797fd7`) match `out_dev_recall21_table` byte-for-byte with `0` OCR errors; (2) native affine tick calibration precision is `≤ 1.14e-7`; (3) 2D `(KP/KR/KF1, Answer F1)` matching on native panel pairs (`Fig 3 ↔ Fig 10/11/12`) resolves `348/352` (`98.9%`) points uniquely at `±1e-4`, leaving `4/352` (`2` exact coincident pairs) unresolvable without run IDs — note that `plot_recovery.py` `seen_series` currently drops axes prior to export, so 2D matching must run on native pairs before export; (4) `Fig 2 ↔ Fig 3/10/11` lacks a second calibrated shared axis (RGB colorbar only), leaving `40–210` 1D ties per panel; (5) `Fig 9 (k=3)`, cross-generator (`230/352` KP collisions between GPT-4o-mini and Mistral), cross-dataset (`47/231` KP collisions), and within-panel coincidences must remain independent (`duplicate_of=""`).
- **Antigravity next step:** Synced and ready for a clean context reset; idle pending operator direction (either next zero-token verification task or explicit authorization to publish `RECALL-DEV-003` into `handoff/FROM_ANTIGRAVITY.md`).

## Operating mode

- Codex executes one stage at a time on its own. After implementation and a dev measurement, record row counts, Strict and Loose R/P/F1, runtime and tokens. The operator approved continuing from Stage 2 directly to Stage 3.
- Keep the same configured model and provider in Stage 1. Start with a cache-only rebuild and local PDF checks. Use an isolated cache for targeted live extraction so the accepted dev bundle and raw cache remain reproducible.
- Use no benchmark IDs, entity names, or gold values in extraction rules. Preserve cache v2 and the seven CSV schemas. Keep the frontend and the 111-paper test corpus outside these stages.

## Reference measurements

- The [metric audit](METRIC_AUDIT.md) established the next priorities. The optional partial-cache export recovered 101 Strict and 150 Loose TP on the same local snapshot, with an explicit incomplete status and zero API calls.

- Domain 2 at `b5cb065`: 4,922 scored predictions and 19,392 gold observations. Strict R/P/F1 **0.030/0.118/0.048** (579 TP). Loose R/P/F1 **0.089/0.350/0.142** (1,721 TP).
- Historical full-cache reference, [RECALL-DEV-002](handoff/FROM_ANTIGRAVITY.md#recall-dev-002): 4,945 predictions, Strict R/P/F1 **0.038/0.150/0.061** (741 TP), Loose R/P/F1 **0.096/0.375/0.152** (1,854 TP). Compare local runs using the same input PDFs and available cache. Earlier experiments are in [the checkpoint log](handoff/STRICT_F1_STATE.md).

## Stage 1 · Structured PDF parsing and OCR

- [x] **1.1 Native PDFs.** Use page-aligned PyMuPDF4LLM Markdown with inline HTML grids and merged headers. Try an alternate native grid detector when the first pass omits substantial numeric text. Preserve page markers and end matter. Keep native text for citation checks and disable OCR on readable pages.
- [x] **1.2 Scanned and mixed PDFs.** Use local RapidOCR with spatial text injection, then apply the same structured page renderer. Supplement collapsed scan tables with aligned OCR baselines. Share the OCR engine with citation verification, report unreadable pages and preserve the existing multimodal fallback where available.
- [x] **1.3 Measure the local dev pilot.** 3,913 → 3,979 scored predictions, Strict R/P/F1 0.02867/0.14209/0.04772 → 0.02707/0.13194/0.04493, Loose R/P/F1 0.06905/0.34219/0.11491 → 0.06962/0.33928/0.11553. Both bundles had zero structural errors. The pilot refreshed two papers against the 21-paper gold set and left three local cache gaps. Strict F1 declined. See [the measurement log](handoff/STRICT_F1_STATE.md#stage-1--structured-pdf-and-ocr-local-pilot) for verification and limitations.
- [x] **Operator checkpoint.** Stages 2 and 3 are authorized in sequence.

## Stage 2 · Table windows and response capacity

- [x] **2.1 Table-first windows.** Send each table or row split with its caption, headers and section. Preserve merged cells, capture captioned flattened grids, checkpoint successful slices, and process remaining prose through the final page.
- [x] **2.2 Compact responses.** Validate positional arrays and expand them before cache writes. Default to 393,216 tokens on the official DeepSeek endpoint. Respect the configured 16,384-token cap on the current gateway. The targeted replay recovered 252 → 269 raw observations, with 2.43× fewer output tokens per observation. Corpus Strict and Loose TP stayed at 525 and 1,350. Proceed to Stage 3.

## Stage 3 · Strict context and seven-field tuples

- [x] **3.1 Paper entity passport.** Collect datasets, generators, RAG variants and scoped metric cutoffs in the first metadata request. Pass the matching page and table scope to each extraction request. The live pilot returned seven scopes and completed the paper.
- [x] **3.2 Source-backed normalization.** Resolve entity typography and explicit model identifiers, read metric cutoffs separately from display labels, and inherit context when the local source is unambiguous. On the same cache, Strict TP rose from 525 to 668 and Strict F1 from 0.04490 to 0.05713. The fresh-paper variant scored 607 Strict TP and remains an isolated comparison. Both bundles passed structural validation. [Detailed results](handoff/STRICT_F1_STATE.md#stage-3--entity-passport-and-source-backed-normalization)

The historical Stage 3 pilot used 18 complete caches against all 21 gold papers. The current checkpoint above supersedes its coverage status.

## Next priorities from the metric audit

- [x] Restore complete cache coverage and preserve compatible per-document progress across extraction retries. The local recovery benchmark processed 21/21 with 860 Strict TP and 1,853 Loose TP, after 668 and 1,350 at the initial baseline. Saved D009 windows and metadata were preserved.
- [ ] Verify chart provenance and source-supported series context. Evaluate vector recovery separately from the default bundle.
- [ ] Reduce confirmed dataset, generator and variant mismatches with source evidence on a frozen cache.
- [x] Run controlled gateway and OCR experiments after measuring the dominant coverage and context losses. The sampled source cells favored 200 dpi over 150 dpi. A matched Flash/Pro source row tied at 15/15; keep the configured model.
