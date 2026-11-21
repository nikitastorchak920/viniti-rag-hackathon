# Strict F1 checkpoint state

## P0.1 · Completed offline baseline audit

- Status: waiting for operator approval before P0.2. No production settings or extraction code changed.
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

### Next proposed work item

P0.2 is the only proposed next task. Start with dataset context and verify joint variant/generator linkage from the same evidence. Judge the change on exact scores with fixed keys and stop at the first measured checkpoint.
