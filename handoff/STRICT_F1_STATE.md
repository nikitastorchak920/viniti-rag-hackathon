# Strict F1 checkpoint state

## Stage 3 · Entity passport and source-backed normalization

The metadata pass now emits page and table scopes alongside paper entities. The exporter resolves model and dataset spellings against printed evidence, removes generic author markers from method labels, and checks metric cutoff declarations against the cited page. It separates the parsed cutoff from the printed metric display label and preserves the existing CSV convention and evaluator.

| Comparison against 21 gold papers (18 complete local caches) | Scored predictions | Strict R/P/F1 | Strict TP | Loose R/P/F1 | Loose TP | Structural errors |
|---|---:|---|---:|---|---:|---:|
| Stage 2 reference | 3,994 | 0.02707/0.13145/0.04490 | 525 | 0.06962/0.33801/0.11545 | 1,350 | 0 |
| Stage 3 on the same cache | 3,994 | 0.03445/0.16725/0.05713 | 668 | 0.06962/0.33801/0.11545 | 1,350 | 0 |
| Stage 3 with one fresh paper | 4,031 | 0.03130/0.15058/0.05183 | 607 | 0.06962/0.33490/0.11527 | 1,350 | 0 |

The same-cache gain was +144 Strict TP on D007 and -1 on D011, where the earlier configuration assignment came from a substring of an extraction note. D007's source states the model identifier in a parenthetical declaration and marks the authors' method separately. The rules are based on those document structures. The fresh D007 run used seven passport scopes, 15 detected tables, and 859 raw results. It increased D007 Strict TP from the Stage 2 reference's 180 to 263, but the normalized earlier cache scored 324. Keep these snapshots separate.

The offline check took 5.6 seconds and zero tokens. The full-paper pilot took 332.5 seconds and reported 145,718 input and 63,294 output tokens. The final rebuild and evaluation took 8.8 seconds. The checker reported 420 review items for the same-cache comparison and 347 with the refreshed paper. Both used native text for quote checks. The local cache gaps are D002, D009 and D013. All 56 core tests passed. The original caches, jury bundle, front end and held-out test data were outside the verification run.

## Stage 2 · Table requests and compact results

The same D007 pages 7–9 and Stage 1 metadata were replayed on the configured DeepSeek gateway. The first pass exposed a captioned table rendered as plain text. The final planner captured both header groups and returned 210 observations in the two slices of that table. It also kept the other table and residual prose requests. Eight identical table responses were reused between experiments.

| 21-paper gold comparison (18 complete local caches) | Scored predictions | Strict R/P/F1 | Strict TP | Loose R/P/F1 | Loose TP |
|---|---:|---|---:|---|---:|
| Stage 1 reference | 3,979 | 0.02707/0.13194/0.04493 | 525 | 0.06962/0.33928/0.11553 | 1,350 |
| Stage 2 targeted replay | 3,994 | 0.02707/0.13145/0.04490 | 525 | 0.06962/0.33801/0.11545 | 1,350 |

The replay produced 269 raw results versus 252, and used 16,687 completion tokens versus 37,980 for the same pages, a 2.43× reduction per raw result. Related input tokens rose from 12,402 to 66,483 because table calls repeated the entity list. The two Stage 2 executions took 187.7 seconds in total and spent 75,877 input and 31,235 output tokens, including the first attempt. The checker reported zero structural errors, and 52 core tests passed. Cache-only replay of the Stage 1 data reproduced its previous scores. Official DeepSeek defaults to 393,216 completion tokens; the configured custom gateway ran at its existing 16,384-token setting.

## Stage 1 · Structured PDF and OCR local pilot

- All 21 local PDFs were classified by their native text layer. Eighteen required no OCR. Native Markdown checks on sampled papers retained page markers and appendix text, and emitted native table grids and merged headers. D014 retained all 18 pages and a nonempty last page. D021 OCR retained text across all 16 pages; PDF page 11 confirmed that positioned OCR baselines expose rows when the layout engine collapses a scan table.
- The first live pass identified a native grid loss on D007 page 7. The alternate grid detector reduced omitted distinct numeric literals from 179 to 12 before the raw-text safety supplement. Replaying only pages 7–9 with the same metadata restored raw observations from 42 to 252. For the full D007 replay, Strict TP rose from 90 to 180 and Loose TP from 301 to 425 versus the first structured pass. The earlier reference had 211 Strict and 414 Loose TP. The scanned paper produced 21 observations after OCR and had zero Strict and Loose matches against gold. The exporter verified or repaired five of its result quotes; 16 remained unverified.
- The baseline used 17 complete local caches, and the candidate used the same caches with D007 replaced and D021 added. Three local caches (D002, D009, D013) remained incomplete. All scores use the same 21-paper gold corpus, with 19,392 scored gold observations. This is a targeted live comparison against cached results from earlier extraction, so the difference includes model/run effects. It is separate from the historical 21-cache RECALL-DEV-002 benchmark.

| Local export | Scored predictions | Strict R/P/F1 | Strict TP | Loose R/P/F1 | Loose TP |
|---|---:|---|---:|---|---:|
| Cached reference | 3,913 | 0.02867/0.14209/0.04772 | 556 | 0.06905/0.34219/0.11491 | 1,339 |
| First structured pass | 3,769 | 0.02243/0.11542/0.03756 | 435 | 0.06322/0.32529/0.10587 | 1,226 |
| Structured pass with alternate grid replay | 3,979 | 0.02707/0.13194/0.04493 | 525 | 0.06962/0.33928/0.11553 | 1,350 |

Both reference and final candidate had zero structural errors. The final corpus checker used native PDF text (381 review items); the targeted live export separately ran RapidOCR for D021 quote checks. The local core suite passed 48 tests.

The configured DeepSeek model was kept. The two-paper live run took 615.6 seconds, with a 173.9-second targeted replay overlapping it. Total usage reported by the API was 134,632 input and 143,206 output tokens. Reference and candidate offline checks took 22.6 and 8.4 seconds. An earlier broader attempt was interrupted during local preprocessing before extraction requests. Relative OCR speed versus Tesseract remains unmeasured. The accepted jury bundle and original cache were preserved.

## S2.1 · Table recovery approved for the default export

[RECALL-DEV-002](FROM_ANTIGRAVITY.md#recall-dev-002) at `96f3c30` isolated table recovery on the complete 21-paper cache with zero API calls. Scored predictions rose from 4,911 to 4,945. Strict R/P/F1 was 0.038/0.150/0.061 (741 TP, +10), and Loose R/P/F1 was 0.096/0.375/0.152 (1,854 TP, +12). All 34 cells came from D007 PDF page 7, Table 2. There were zero structural errors, per-paper regressions or new table-recovery reviews. A laptop sleep during OCR affected the separate quote-review count.

Default adoption was verified locally on D007 with byte-identical CSVs for the default and explicit opt-in, 729 to 763 result rows compared with opting out, and a clean slice checker. The 17-document local comparison gained the same 10 Strict and 12 Loose TP. All 44 core tests passed.

The source audit confirms that the selection cap belongs to the experimental configuration rather than the metric cutoff. It identifies explicit aliases, repeated replots, and a pre-generation plot with no generator. Exact bespoke variant wording in gold is not evidence for extraction. The next handoff verifies the default change and checks point correspondence before implementing `duplicate_of` links or recovering colorbars.

## R1.4 · Full-cache verification completed

The [RECALL-DEV-001 report](FROM_ANTIGRAVITY.md#recall-dev-001) at `676ef1f` tested `dae1acc` on all 21 caches in `out_dev_domain2_scan_cache`. Both rebuilds completed without API calls, stubs or structural errors. The checker exited 2 with review items.

| Full-cache export | Scored predictions | Strict R/P/F1 | Strict TP | Loose R/P/F1 | Loose TP | Strict F1 without D014 |
|---|---:|---|---:|---|---:|---:|
| Domain 2 reference | 4,922 | 0.030/0.118/0.048 | 579 | 0.089/0.350/0.142 | 1,721 | 0.093 |
| Current default | 4,911 | 0.038/0.149/0.060 | 731 | 0.095/0.375/0.152 | 1,842 | 0.117 |
| Both recovery flags | 19,069 | 0.038/0.039/0.039 | 741 | 0.618/0.629/0.623 | 11,989 | 0.119 |

The combined candidate had zero per-paper Strict F1 regressions and 10 additional Strict matches from 34 table cells on D007. D014 contributed 10,135 additional Loose TP and zero Strict TP. Spot checks confirmed linear-axis calibration on inspected panels and identified missed axes and colorbars, repeated plotted series, an explicit selection limit omitted from metadata, and gaps in the cited configuration and task context. Review items rose from 550 to 2,420. Caption verification alone cannot confirm calibrated coordinates or point-level conditions.

`RECALL-DEV-002` isolates the table flag to measure its effect on corpus Strict F1 and audits native PDF evidence for plot context before implementation. The original report and full metric history remain in the repository.

## R1.2 · Offline figure recovery and abbreviation resolution

- Same 17 complete local caches, scored against all 21 gold papers. The new default export expands uniquely defined abbreviations printed in the source. The optional pilot adds 14,124 vector observations and 34 table cells. All values derived from plot geometry are marked approximate. Literal generator names in panel titles can be linked to partial configurations. Unavailable point-level parameters are left empty.
- The prompt requests results throughout the document, including appendices, and independent rows for numeric baseline cells. Split deduplication preserves differences in validated result fields. Live extraction changes still need a targeted measurement.

| Local export | Scored predictions | Strict R/P/F1 | Strict TP | Loose R/P/F1 | Loose TP |
|---|---:|---|---:|---|---:|
| Previous default | 3,879 | 0.02501/0.12503/0.04168 | 485 | 0.06198/0.30987/0.10330 | 1,202 |
| Current default | 3,879 | 0.02816/0.14076/0.04693 | 546 | 0.06843/0.34210/0.11405 | 1,327 |
| Current default with both recovery flags | 18,037 | 0.02867/0.03083/0.02971 | 556 | 0.59169/0.63614/0.61311 | 11,474 |

- Both exports passed structural validation. Review items rose from 260 in the default to 2,130 in the optional pilot. For plots, quote validation confirms only the caption. Direct checks of axis calibration and figure context are part of the full-cache handoff. Keep the plot pilot opt-in while strict context is sparse and Strict F1 declines.
- The two offline rebuilds, checkers and scoring took 15.6 seconds and used zero API tokens. Pytest passed 44 tests. The rebuild reports four incomplete or unavailable local caches. The next validation is `RECALL-DEV-001` on Antigravity's complete cache.

## R1.1 · Recall-first audit and opt-in table recovery

- Historical checkpoint. The two rebuilds, checker and evaluator took 9.6 seconds locally and used zero API tokens. Pytest passed 38 tests.
- The 17 complete local caches have 3,979 first-pass observations, 3,934 parseable numeric values and 49 empty windows out of 104. The pre-fix CSV has 3,983 rows including earlier verification recoveries. Of these, 45 are non-extractable and 59 are numeric duplicate rows. The evaluator accepts 3,879. Postprocessing does not account for the large difference versus 19,392 corpus gold entries or the 4,922 predictions in the full remote reference.
- D014 caches all six physical page windows but five yielded zero rows. Only 108 of its 11,760 scored gold cells cite tables. Another 11,643 cite figures and nine have neither locator. Do not claim the table recovery solves chart-point coverage or that missing PDF pages were dropped from the input.
- The new opt-in `--recover-table-cells` exports unseen numeric cells from native, captioned tables with aligned metric/dataset headers, one configuration and consistent cached experiment/task metadata. D007 gained 34 source-confirmed rows. The printed metric labels `Acc`, `Step` and `Time` do not match their long-form evaluator keys in this sample, so neither TP count increased. The default CSV files are byte-identical to P0.3a.

| Same local cache, 21 gold papers | Scored predictions | Strict R/P/F1 | Strict TP | Loose R/P/F1 | Loose TP |
|---|---:|---|---:|---|---:|
| Default / before | 3,879 | 0.02501/0.12503/0.04168 | 485 | 0.06198/0.30987/0.10330 | 1,202 |
| Opt-in / after | 3,913 | 0.02501/0.12395/0.04162 | 485 | 0.06198/0.30718/0.10315 | 1,202 |

Reproduce with `python main.py --input dev --output out_dev_recall_01 --rebuild-csv-only --recover-table-cells`, then `python tools/check_submission.py out_dev_recall_01 dev --json-report out_dev_recall_01/validation.json` and `python scripts/evaluate.py out_dev_recall_01 dev_gold --show-diffs 0`. The checker has zero structural errors and 260 review items in the opt-in build. The rebuild reports four incomplete local caches; no LLM calls were made. Next proposed step: R1.2, source-based graphical coverage audit.

## P0.3a · Completed offline alias recovery

- Historical checkpoint. No API calls or evaluator changes. Both builds scored the same 17 usable document caches against 21 gold publications.
- Extracted only acronym definitions printed in the native PDF, in `full name (ABBR)` or `ABBR: full name` form. Conflicting names are excluded. For single-metric tables, the caption must identify one cached metric and the existing configuration must match the printed row method. Unlabeled numeric columns still participate in ambiguity checks. No new entities or configuration IDs were introduced.

| Snapshot | Strict P | Strict R | Strict F1 | Strict TP | Loose P | Loose R | Loose F1 | Loose TP | Pred | Gold |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Before P0.3a | 0.11831 | 0.02372 | 0.03952 | 460 | 0.31019 | 0.06219 | 0.10361 | 1,206 | 3,888 | 19,392 |
| After P0.3a | 0.12503 | 0.02501 | 0.04168 | 485 | 0.30987 | 0.06198 | 0.10330 | 1,202 | 3,879 | 19,392 |

All 25 new Strict matches came from 39 dataset reference changes in D006; no prior Strict matches were lost. Nine observations gained duplicate flags and remain in CSV, reducing Loose TP by four. The validator reported zero structural errors and 260 review items before and after. `pytest` passed 37 tests.

Reproduce with `python main.py --input dev --output out_dev_strict_p03 --rebuild-csv-only` and `python scripts/evaluate.py out_dev_strict_p03 dev_gold --show-diffs 20`. The next proposed step, P0.3b, targets entities whose source labels have no matching entry in cached metadata.

## P0.2 · Completed offline relinking

- Historical checkpoint. No API calls and no evaluator changes. Both builds scored the same 17 available local document caches against 21 gold publications.
- Changes: `core/pdf_processor.py` exposes optional native line coordinates only for result pages. `plugins/rag/table_context.py` links an exact cached value and metric to repeated column groups under known printed dataset labels. It scopes to a uniquely captioned table, checks row method and generator evidence, and leaves ambiguous cells unresolved. A configuration reassignment requires a quoted method and a unique configuration. Cache version 2 and the seven CSV schemas are unchanged.

| Snapshot | Strict P | Strict R | Strict F1 | Strict TP | Loose P | Loose R | Loose F1 | Loose TP | Pred | Gold |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Before P0.2 | 0.10129 | 0.02032 | 0.03385 | 394 | 0.31003 | 0.06219 | 0.10360 | 1,206 | 3,890 | 19,392 |
| After P0.2 | 0.11831 | 0.02372 | 0.03952 | 460 | 0.31019 | 0.06219 | 0.10361 | 1,206 | 3,888 | 19,392 |

The source-supported relinks changed 142 dataset references and uncovered 66 new strict matches in D007. No previous strict matches were lost. Two observations remained in CSV but were marked duplicates after their contexts were corrected. The joint configuration path is covered by synthetic fixtures; this cache comparison had no configuration reference changes. The checker reported zero structural errors and 260 review items in both builds. `pytest` passed 35 tests. The four missing local caches and OCR-only layouts were outside this measurement.

Reproduce the candidate with `python main.py --input dev --output out_dev_strict_p02 --rebuild-csv-only`. Use `python scripts/evaluate.py out_dev_strict_p02 dev_gold --show-diffs 20` to inspect changes beside the P0.1 export. P0.3 is the next proposed task: audit missing labels, then recover source-supported entities and aliases with a separate measured checkpoint.

## P0.1 · Completed offline baseline audit

- Historical checkpoint. No production settings or extraction code changed during P0.1.
- Reference: code `b5cb065`, full report [DOMAIN2-DEV-001](FROM_ANTIGRAVITY.md#domain2-dev-001) at `4b77325`.
- Local command: `python main.py --input dev --output out_dev_strict_audit --rebuild-csv-only`. Exit 1 reflects four incomplete local caches. The build has 17 processed papers, no API calls, and retained all 21 gold papers in the scoring denominator. It is distinct from the full, 21-paper post-OCR snapshot. Scoring used the repository evaluator's strict and loose multiset keys.

| Snapshot | Strict P | Strict R | Strict F1 | Strict TP | Loose P | Loose R | Loose F1 | Loose TP | Pred | Gold |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Full reference report | 0.118 | 0.030 | 0.048 | 579 | 0.350 | 0.089 | 0.142 | 1,721 | 4,922 | 19,392 |
| Local cache audit | 0.10129 | 0.02032 | 0.03385 | 394 | 0.31003 | 0.06219 | 0.10360 | 1,206 | 3,890 | 19,392 |

There is no before/after change within either snapshot. The full report contains 11 papers with zero Strict TP. The local residual paired 812 Loose-only matches after removing strict matches. Of these, 419 differed in one context field, 360 in two, and 33 in three. The full report records 1,142 residual pairs and field counts of dataset 696, variant 471, generator 525, and k 51.

| Local strict field | Mismatched pairs | Prediction blank | Gold blank | Both nonempty | Extra TP if this field alone is removed from the comparison |
|---|---:|---:|---:|---:|---:|
| `dataset_name` | 556 | 48 | 2 | 506 | 193 |
| `rag_variant` | 305 | 40 | 1 | 264 | 147 |
| `generator_model` | 377 | 10 | 85 | 282 | 88 |
| `metric_k` | 0 | 0 | 0 | 0 | 0 |

The projection recomputes multiset overlap after omitting one key at a time. Deltas are non-additive and describe sensitivity, not recoverable TP. Per-field mismatch counts use diagnostic residual pairing, so a repeated numeric value is not proven to refer to the same cell. For 167 of the 812 paired residuals both expected labels were already represented in the predicted entity tables, treating legitimately empty expected dimensions as satisfied. For 645 at least one expected name or variant/generator pair was absent as an exact label. This is evidence to examine both links and representation; it does not establish that the paired gold entity is the right target.

### Code trace

- `scripts/evaluate.py::keys` dereferences dataset/configuration IDs before the strict comparison. Loose ignores those context dimensions.
- `plugins/rag/prompts.py::window_user` restricts results to IDs emitted by the document-wide metadata pass. A row/column label missing in that pass cannot be represented by an existing ID.
- `plugins/rag/exporter.py::_fill_ids` fills blank IDs for primary rows using names in the row hint, single-entity fallback, and table-level consensus for dataset/task/experiment. It has no row/column configuration context and does not revisit already-filled IDs. Dataset display normalization runs after linking. Missing-link fixes alone cannot account for the many nonempty mismatches.
- The page loop enumerates the whole physical PDF. Window splitting reacts to declared truncation or capped malformed output. A successful but sparse window remains complete, which is a coverage hypothesis for P1, not a validated cause for an individual paper.

### Model check

On 2026-11-21, the [official model documentation](https://api-docs.deepseek.com/quick_start/pricing/) identifies `deepseek-flash` at `https://api.deepseek.com` as DeepSeek-V4.1-Flash-1017. The legacy V4 Flash model is retired. The official endpoint still routes legacy aliases to the current model. The exact November 15 date was not verified. Both the code fallback and `.env.example` use the official alias. The effective local settings select DeepSeek through a third-party gateway with `deepseek-v4-flash`, so the model served there cannot be inferred. No credentials were read into the report and no provider request was sent. The provider migration is a prerequisite before any approved live pilot.
