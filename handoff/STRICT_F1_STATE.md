# Strict F1 checkpoint state

## P0.3a · Completed offline alias recovery

- Status: awaiting operator approval before P0.3b. No API calls or evaluator changes. Both builds scored the same 17 usable document caches against 21 gold publications.
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
