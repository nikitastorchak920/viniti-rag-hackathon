# Antigravity reports

Antigravity prepends replies under **Reports** and pushes this file to `origin/main` for Codex. Use `## <task ID>` as the reply heading and preserve older replies. Include only redacted excerpts. Keep API keys, raw PDFs, caches, generated CSVs, and full raw logs local.

### Report template

- Status (`complete` or `blocked`):
- Git commit (from `git rev-parse --short HEAD`):
- Python and Tesseract versions:
- Cache-only rebuild exit code and unresolved IDs:
- Live commands, exit codes, backend, and token totals:
- Per-paper evidence for D002, D009, D013, D021 (mode, raw rows, numeric CSV rows, scope or failure):
- Final `out_dev` publication coverage, unprocessed IDs, and row counts for all seven tables:
- Checker exit code, structural errors, review counts by category, and matched/requested quotes:
- Evaluator scope agreement, strict and loose TP/F1, and top mismatch fields:
- UI URL and observed paper/dataset/metric/issue filters, source page/quote, and row counts:
- MVP checkpoint for 1.1 and 1.2 (pass/pending and exact blockers):
- Redacted failure or review excerpts:

### Reports

<!-- Prepend replies here. The template above is not a task response. -->

## DOMAIN1-SOLAR-001

- Status (`complete` or `blocked`): `complete`
- Base Git commit (from `git rev-parse --short HEAD` before commit): `63ed702`
- Acceptance check: **PASS — DOMAIN 1 (THIN-FILM SOLAR CELLS) ISOLATED PLUGIN READY FOR TEST SPLIT** (`0` errors in `область_1/tools/check_submission.py`, `3` minor warnings, **`895 / 895` (`100.0%`)** verbatim `pypdf` quotes verified, **`21/21` (`100.0%`) `in_scope` agreement**, **`Loose F1 = 0.915`** (`P=0.908, R=0.922`), **`Medium F1 = 0.812`**, **`Schema-Strict F1 = 0.750`**, **`Strict+Label F1 = 0.324`**; zero modifications to any existing RAG/shared files).
- Backend & isolation: `DeepSeekClient` (`deepseek-v4-flash`, `DEEPSEEK_MAX_TOKENS=8192`, `--ocr` with Tesseract fallback); separate cache/output folders (`cache_solar/`, `out_solar_dev/`, none committed). Total live extraction tokens across 21 dev PDFs (smoke + 17 + 4): `in=1,046,673`, `out=160,648`. Two offline exporter tuning iterations (`--rebuild-csv-only`) spent **`0` API tokens**.

### 1 · New Isolated Files Created (Zero Overlap with RAG / Codex)

1. `plugins/solar/__init__.py`
2. `plugins/solar/schemas.py` — Pydantic v2 wire models (`Publication`, `Material`, `Device`, `Layer`, `Measurement`, `MetaIssue`, `Meta`, `CompactMeta`, `Result`, `Window`, `CompactWindow`) accepting both positional arrays and dict rows safely.
3. `plugins/solar/prompts.py` — Domain 1 scope rules (experimental single-junction thin-film PV only; excludes DFT/SCAPS/MATLAB/Maple/tandem), 11 canonical metrics, reverse/forward measurement separation, no-duplicate-device-per-scan/champion rule, no relative deltas in `results.csv`, absorber-only bandgap, substrate-excluded `layer_order=1..N`.
4. `plugins/solar/pipeline.py` — `Meta`/`CompactMeta` + `Window`/`CompactWindow` with solar-aware recursive line-splitting `_header`, `verify_pass`, and local `pytesseract` fallback for `--ocr` on image-only pages under `text_only` DeepSeek.
5. `plugins/solar/exporter.py` — Deterministic CSV exporter enforcing exact 7 CSV schemas (including uppercase `DOI` in `publications.csv`), all 18 `VOCAB` dictionaries, all 6 `NUMERIC` columns, 11 canonical metric synonyms + unit normalization (`Voc mV->V`, `FF 0.71%->71%` + `unit_inconsistency`, `HI` fraction->`%`, `Jsc A/m2->mA/cm2`, `Rs/Rsh kOhm*cm2->Ohm*cm2`, `T80 days/min->h`, `active_area mm2->cm2`, `layer_thickness um->nm`), `Voc_deficit`/`Voc_SQ_ratio` guard, `_fill_ids()` + orphan `device_id` resolution + strict FK scrubbing, exact + prose-to-table `duplicate_of` + `contradiction` detection, `pypdf` quote grounding (`norm()` matching `область_1/tools/check_submission.py`), and 7 physical/logical checks (`jv_consistency`, `voc_limit` restricted to `device_type=="cell"`, `eqe_consistency`, `champion_vs_mean`, `range`, `hysteresis_index`, `missing_conditions`/`comparability`).
6. `scripts/run_solar.py` — Standalone CLI mirroring `main.py` (`--input`, `--output`, `--cache cache_solar`, `--only`, `--force`, `--rebuild-csv-only`, `--window`, `--pdf-mode`, `--skip-scans`, `--workers`, `--ocr`, `--verify-pass`; prefers `DEEPSEEK_API_KEY`).
7. `scripts/evaluate_solar.py` — Stdlib-only evaluator against `область_1/dev_gold/` reporting `in_scope`, 7 table row counts, `materials`, `devices`, `Strict+Label`, `Schema-Strict`, `Medium`, `Loose` P/R/F1, loose-to-strict mismatch breakdown, and per-publication F1.

### 2 · Dev Verification & Metrics (`область_1/dev` — 21 PDFs: `D001`–`D022` excl. `D011`)

- **`область_1/tools/check_submission.py out_solar_dev область_1/dev`:**
  - `таблиц: 7, результатов: 741, ошибок: 0, предупреждений: 3, проверено цитат: 895, не найдено: 0`
  - Remaining 3 warnings are general abstract/prose statements without a single specific device (`D021` rows 586–587 general PED/RFMS `Voc` ranges, `D022` row 705 abstract upper bound `0.5%`).
- **`scripts/evaluate_solar.py out_solar_dev область_1/dev_gold` (Iteration 2 offline `--rebuild-csv-only`):**
  - `in_scope agreement`: **`21/21 = 100.0%`** (`19` included, `2` excluded: `D006` ab initio DFT and `D016` MATLAB/Maple simulation; `0` wrong).
  - Row counts (pred vs gold): `publications=21/21`, `materials=72/57`, `devices=117/89`, `layers=571/519`, `measurements=82/45`, `results=741/659`, `issues=176/53`.
  - `materials (class + formula/name)`: `P=0.500 R=0.632 F1=0.558 (tp=36)`
  - `devices (label + architecture)`: `P=0.291 R=0.382 F1=0.330 (tp=34)`
  - **`Strict+Label` (`device_label+scan+agg+origin+metric+val`)**: **`P=0.322 R=0.327 F1=0.324 (tp=189, pred=587, gold=578)`** (up from `0.294` baseline; note `316` of `344` loose-to-strict pairs differ only on free-text `device_label` wording, e.g. `A1` vs `A1 (RFMS 1200 nm / PED 0 nm)`).
  - **`Schema-Strict` (`material_class+scan+agg+origin+metric+val`)**: **`P=0.744 R=0.756 F1=0.750 (tp=437, pred=587, gold=578)`**
  - **`Medium` (`agg+origin+metric+val`)**: **`P=0.806 R=0.818 F1=0.812 (tp=473, pred=587, gold=578)`** (up from `0.791`)
  - **`Loose` (`metric+val`)**: **`P=0.908 R=0.922 F1=0.915 (tp=533, pred=587, gold=578)`** (up from `0.877`; every in-scope paper scored `0.755–1.000`, with `D002`/`D007`/`D018` at `1.000`, `D001` at `0.988`, `D012` at `0.960`, `D017` at `0.957`, `D014` at `0.945`, `D019` at `0.938`, `D015` at `0.931`, `D020` at `0.927`, `D021` at `0.922`, `D003` at `0.919`, `D005` at `0.909`).
- **Offline `область_1/test` readiness check:** `90` PDFs (`1,000` total pages), `89` fully native-text PDFs + `1` PDF (`P018`, 2/13 short pages) covered by `--ocr`. Ready for full test extraction upon operator approval.

### 3 · Integration Notes for Codex (`--domain solar` & `DATASET_PASSPORT.md`)

1. **`main.py` (`--domain {rag,solar}`, default `rag`):**
   - Add `ap.add_argument("--domain", choices=["rag", "solar"], default="rag")`.
   - When `a.domain == "solar"`, delegate directly to `scripts.run_solar.main(...)` (or import `plugins.solar.pipeline` + `plugins.solar.exporter` with default `--cache cache_solar`), preserving all existing RAG flags unchanged.
2. **`DATASET_PASSPORT.md`:**
   - Add a **Domain 1 (Thin-Film Solar Cells)** section listing the 7 tables (`publications`, `materials`, `devices`, `layers`, `measurements`, `results`, `issues` — noting uppercase `DOI`), the 18 strict `VOCAB` constraints, the 6 `NUMERIC` columns, the 11 canonical PV metrics with normalized units (`%`, `V`, `mA/cm2`, `Ohm*cm2`, `h`), and the 7 deterministic physical checks (`jv_consistency`, `voc_limit` on `cell` only, `eqe_consistency`, `champion_vs_mean`, `range`, `hysteresis_index`, `missing_conditions`/`comparability`).

## STRICT-DEV-PLOT-001

- Status (`complete` or `blocked`): `complete`
- Git commit (from `git rev-parse --short HEAD`): `e21e3b7`
- Acceptance check: **COMPLETE — SOURCE-ONLY AUDIT & SAFE-SCOPE VERDICT (`0 / 14,124` current scatter rows eligible for default Strict export; `40`-row single-curve polyline slice identified on `D006` Figure 3 as smallest high-precision candidate)**. Offline only (`0` API tokens); `core/`, `plugins/`, `scripts/`, `tools/`, `tests/`, `app/`, `main.py`, `TODO.md`, accepted exports, and `test/` untouched; only `handoff/FROM_ANTIGRAVITY.md` modified.
- Environment & cache: Python `3.13.1` (`.venv`), `PyMuPDF` native text/drawing geometry; complete 21-paper local cache `out_dev_domain2_scan_cache` (note: differs from Codex's `out_dev_recovery/cache` on `D002`/`D009`/`D013`, yielding `4,945` baseline scored predictions vs `5,305` on `out_dev_recovery/cache`, while `D014` vector recovery is identical at `14,124` rows).

### 1 · D014 PDF Provenance Audit (Printed Evidence vs Gold Naming Conventions)

All 21 dev PDFs were scanned with `plugins/rag/plot_recovery.py` at `e21e3b7`: **`20/21` papers yield `0` recovered scatter rows**, and **`D014` alone produces all `14,124` recovered vector scatter rows** across 8 figures (Figures 2, 3, 5, 8, 9, 10, 11, 12; `231` WoW points/panel, `352` HotpotQA points/panel).

#### A. Printed PDF evidence by figure and condition (`dev/D014.pdf`)

| Scope / Condition | Locators (PDF page, section, figure) | Verbatim printed PDF evidence | Current export (`e21e3b7`) | Provenance verdict |
|---|---|---|---|---|
| **Method / RAG variant** | p.2 Fig 1; p.3 Sec 3.2; p.4 Sec 4.3 & Tables 1–2; p.12 Sec A.1.1 | Fig 1 box: `"Simulated Knowledge Retrieval & Selection"`. Sec 3.2: `"sample gold knowledge and distractor knowledge at varying rates pgold and pnoise... Each sampling produces a full experiment... reported as one data point in Figures 2-4"`. Tables 1–2 print only `"No knowledge"`, `"Full knowledge"`, `"Gold knowledge"`. No scatter panel title prints any `rag_variant` or per-point `(p_gold, p_noise)` label. | `PC1`–`PC3` partial configs (`rag_variant=""`, generator only) on `12,958` rows; `config_id=""` on `1,166` rows. | **Unprinted point/panel variant**: no scatter panel matches any cached table config (`C01`–`C09`). |
| **Datasets & aliases** | p.3 Sec 4.1; p.4 Tables 1–2; pp.5,6,13,14,16–18 panel titles & captions; p.12 Sec A.5 | Sec 4.1 defines explicit alias `"Wizard of Wikipedia (WoW; Dinan et al., 2019)"` and `"HotpotQA (Yang et al., 2018)"`. Panel titles print `"Wizard of Wikipedia"` / `"HotpotQA"` / `"Noisy HotpotQA"`; captions & Table 1 use `"WoW"`. Sec A.5 defines `"noisy HotpotQA"` by removing 1 gold sentence per HotpotQA example (same QA task `T2`). | `DS1` (`Wizard of Wikipedia`), `DS2` (`HotpotQA`), `DS3` (`Noisy HotpotQA`, `task_id=""` on all `704` Fig 5 rows → `+704` checker reviews). | Dataset names are printed; `Noisy HotpotQA` lacks a cached primary table row so `task_id` is dropped despite Sec A.5 confirming the HotpotQA QA task. |
| **Generators** | p.4 Sec 4.2 & Tables 1–2; p.12 Sec A.1.2; pp.5,6,13,14,16–18 | Sec 4.2 & panel titles print `"GPT-4o-mini"`, `"LLaMA 3.1 8B"`, `"Mistral 7B-Instruct"` (Tables 1–2 print `"Mistral 7B Instruct"`, Fig 3 caption prints `"LLaMa 3.1 8B"` and `"Mistral-7B-Instruct"`). Sec A.1.2 lists API IDs `gpt-4o-mini-2024-07-18`, `meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo`, `mistralai/Mistral-7B-Instruct-v0.1`. | Generator parsed from panel title into `PC1`–`PC3` (`GPT-4o-mini`, `LLaMA 3.1 8B`, `Mistral 7B Instruct`). | Printed verbatim for Figs 2, 3, 5, 9, 10–12; typography matches PDF, not gold's spaceless form. |
| **Input cap (`k=3`)** | p.13 Sec A.6; p.14 Fig 9 (`1,166` rows) | Panel titles: `"Wizard of Wikipedia GPT-4o-mini k=3"`, `"HotpotQA GPT-4o-mini k=3"`. Sec A.6: `"limit the number of knowledge sentences to k by randomly sub-sampling k sentences when more than k sentences are selected... We choose k = 3"`. Fig 9 caption: `"by limiting the number of knowledge sentences up to k=3"`. | `_panel_configuration` blocks existing config attachment (`EXPLICIT_SETTING`), **but** `exporter.py:720-732` immediately assigns generator-only `PC1` (`GPT-4o-mini`), collapsing `k=3` with unconstrained runs! `metric_k=""`. | `k=3` is an **input-length condition** (NOT `metric_k`). 2D `(KP, KR)` check vs Fig 2 confirms `329/352` HotpotQA and `205/231` WoW points do NOT match Fig 2 — must remain a distinct configuration/condition. |
| **Generator-free panels** | p.13 Sec A.6; p.14 Fig 8 (`1,166` rows) | Panel titles: `"Wizard of Wikipedia Number of Knowledge Sentences"`, `"HotpotQA Number of Knowledge Sentences"`. Sec A.6 & Fig 8 caption characterize selected knowledge set $K'$ length before generation; **no generator is printed anywhere in Fig 8 or Sec A.6**. | `plot_generator=""`, `config_id=""` (`+1,166` checker `primary result without config_id` reviews). | Legitimately generator-free; leaving `generator_model=""` is source-faithful. 2D `(KP, KR)` check vs Fig 2 confirms `194/231` (WoW GPT), `101/352` (HotpotQA GPT), `311/352` (HotpotQA LLaMA), and `55/352` (HotpotQA Mistral) unmatched points — distinct sampling draw, must stay independent. |
| **Repeated views with 2 independent axes** | p.6 Fig 3 vs pp.16–18 Figs 10–12; p.12 Sec A.3 | Sec A.3 explicitly states: `"Figures 10, 11, and 12 extend Figure 3"`. All 6 HotpotQA panel pairs (`GPT-4o-mini` & `Mistral 7B-Instruct` × `KP`, `KR`, `KF1` vs `Answer F1`) share two calibrated independent axes (`352` pts/panel). | `plot_recovery.py:204-219` sorts by total points (running Fig 3 before Figs 10–12) and deduplicates via exact ordered 4-decimal 1D `tuple(values)` (`seen_series`). | **2D native audit (`±1e-4` on both axes):** `0/352` unmatched in all 6 pairs (`max_err ≤ 2.63e-6`); `348/352` (`98.9%`) unique mutual 1-to-1 in 5 pairs and `328/352` (`93.2%`) in `Fig 3 Mid ↔ Fig 11` (`HotpotQA GPT-4o-mini` `KR × Answer F1`). Remaining `4` or `24` points are exact within-panel 2D coincidences (`≤1e-4`). Current 1D `seen_series` leaks **`Fig 3 Mistral Answer F1` `3×` (`1,056` rows)** from `0.62089` vs `0.62088` rounding while dropping canonical Fig 10/11 series. |
| **1D-only cross-figure views & colorbars** | p.5 Fig 2; p.13 Fig 5; pp.16–18 Figs 10–12 | `Fig 10 ↔ Fig 11 ↔ Fig 12` share only 1 calibrated axis (`Answer F1`); `Fig 2 ↔ Fig 3/10/11` share only 1 axis (`KP` or `KR`) while `Answer F1` in Figs 2/5/9 and sentence count in Fig 8 are uncalibrated continuous RGB colorbars. | Emits unlinked duplicate series across Fig 2, Fig 3, and Figs 10–12 (`14,124` rows vs `11,643` scored gold figure rows). | 1D `Answer F1` matching (`Fig 10 ↔ Fig 11/12`, `±1e-4`) leaves `0` unmatched but **`112–131/231` (WoW)** and **`47–77/352` (HotpotQA)** ambiguous ties per panel; `Fig 2 ↔ Fig 3` leaves `69–294` ties. Cannot prove point-level `duplicate_of` from 1D overlap or drawing order. |
| **Dashed reference baselines** | pp.6,8,13,16–18 Figs 3, 4, 6, 10–12 | Legend boxes label red dashed `"Full Knowledge Answer F1"` and black dashed `"No Knowledge Answer F1"`. Calibrated y-positions match Tables 1–2 within `±0.001` (e.g., HotpotQA GPT-4o-mini `0.7797` vs `0.780`, `0.4373` vs `0.437`; Fig 6 Noisy HotpotQA has identical `0.7797` / `0.4373`, matching Sec A.5 p.13). | Not emitted by `plot_recovery.py`. | Already reported in Tables 1–2 (`dev_gold` marks `9/12` Fig 10 baseline lines as `duplicate_of` Tables 1–2; emitting them adds duplicates). |

#### B. Printed PDF evidence vs `dev_gold` naming conventions (inspected only after source audit)

| Field | Printed in `dev/D014.pdf` | `dev_gold` convention | Exact Strict impact (`evaluate.py` `n()`) |
|---|---|---|---|
| `rag_variant` | Fig 1 `"Simulated Knowledge Retrieval & Selection"`; Tables 1–2 `"No knowledge"` / `"Full knowledge"` / `"Gold knowledge"`; no printed per-panel variant strings | Synthetic colon taxonomy (not printed verbatim): `'Simulated knowledge retrieval/selection: unconstrained sampled knowledge'` (`6,996` rows), `'...noisy HotpotQA'` (`1,056`), `'...input-length sampling'` (`1,749`), `'...maximum3sampled sentences'` (`1,749`, missing spaces), `'...ambiguous repeated/noisy contour'` (`40`) | **Primary blocker (`0` Strict TP on all `14,124` D014 plot rows)**: neither `""` nor verbatim `"Simulated Knowledge Retrieval & Selection"` matches gold's synthetic suffixes. |
| `dataset_name` | Panel titles `"Wizard of Wikipedia"`; Sec 4.1 alias `"Wizard of Wikipedia (WoW)"`; captions `"WoW"` | Exclusively `'WoW'` (`'HotpotQA'` and `'Noisy HotpotQA'` match verbatim) | `'wizard of wikipedia' != 'wow'` fails Strict on all WoW panels unless canonicalized via explicit Sec 4.1 alias. |
| `generator_model` | `"GPT-4o-mini"`, `"LLaMA 3.1 8B"`, `"Mistral 7B-Instruct"` / `"Mistral 7B Instruct"`; absent in Fig 8 | `'GPT-4o-mini'`, `'LLaMA3.1-8B'` (spaceless), `'Mistral7B-Instruct'` (spaceless), synthetic `'Generator-independent'` on Fig 8 | `'llama 3.1 8b' != 'llama3.1 8b'`, `'mistral 7b instruct' != 'mistral7b instruct'`, and `'' != 'generator independent'`. |
| `duplicate_of` | Sec A.3 links Figs 10–12 with Fig 3; no point IDs printed | Marks 100% of Fig 2 (`5,247` rows), 100% of Fig 3 (`4,236` rows), and `Answer F1` in Figs 11–12 (`3,522` rows) as `duplicate_of` Fig 10–12 (`28,531` raw → `11,643` scored). | Unlinked Fig 2/3/11/12 emissions inflate scored predictions above gold (`14,215` pred vs `11,760` gold). |

---

### 2 · Smallest Source-Supported Export Slice, Coverage & Generalizable Decision Rule

#### A. Eligible rows vs abstentions (quantified across all 21 dev PDFs)

1. **Current scatter-plot extractor (`plugins/rag/plot_recovery.py`, `14,124` candidate rows across 21 dev PDFs, all in `D014`)**:
   - **Eligible rows for Strict-safe default export: `0 / 14,124` (`0.0%`)**.
   - **Abstentions: `14,124 / 14,124` (`100.0%`)**:
     - `1,166` rows (`D014` Fig 8, p.14): generator-free panel (`config_id=""`, unprinted variant).
     - `1,166` rows (`D014` Fig 9, p.14): explicit input cap `k=3` with unprinted variant (currently mis-collapsed into unconstrained `PC1`).
     - `704` rows (`D014` Fig 5, p.13): `Noisy HotpotQA` with unprinted simulation variant and unlinked `task_id=""`.
     - `11,088` rows (`D014` Figs 2, 3, 10, 11, 12, pp.5,6,16–18): unnamed `(p_gold, p_noise)` simulation points with `rag_variant=""`, plus order/rounding-sensitive duplicate series (`Fig 3 Mistral Answer F1` emitted `3× = 1,056` rows).
   - **Actionable conclusion for scatter mode:** Keep `--recover-plot-points` strictly opt-in (off by default). Exporting partial-config scatter points (`rag_variant=""`) strictly harms corpus Strict Precision (`0.235 → 0.061`) and Strict F1 (`0.096 → 0.060`) while adding `0` Strict TP.

2. **Smallest source-supported vector-plot export slice that CAN improve Strict Precision & Recall (source-only proposal for future single-series polyline recovery)**:
   - Scanning all 20 other dev PDFs for calibrated native vector frames (`_axis` linear fit ≥3 ticks) surfaced 8 PDFs (`D001`, `D003`, `D006`, `D007`, `D009`, `D012`, `D016`, `D019`).
   - **Smallest high-precision positive slice: `D006` Figure 3 (p.14; Sec 4.4 pp.12–13; Sec 4.1.2 p.10) — `40` eligible rows (`0` currently extracted in baseline)**:
     - **Printed structure:** 4 single-curve vector panels (`(a) Retriever-Only`, `(b) RankGPT`, `(c) RankT5`, `(d) Cross-Encoder`), each containing exactly one 9-segment polyline (`10` vertices at `QT = 0.1..1.0`), calibrated y-axis `NDCG@5` (`metric_k="5"`), caption-printed dataset `NaturalQuestions` and retriever `BM25 Retriever`, and section-declared default LLM `Qwen2.5-7B-Instruct` (Sec 4.1.2 p.10: *"For the confidence quantification and pre-trained LLM-based rerankers, we use Qwen2.5-7B-Instruct (Qwen7B)"*). Each panel maps cleanly to an existing cached configuration in `D006` (`C02` `Retriever-Only + LCR`, `C08` `RankGPT + LCR`, `C14` `RankT5 + LCR`, `C12` `Cross-Encoder + LCR`, all `BM25` + `Qwen2.5-7B-Instruct`), where `+ LCR` is established by Sec 4.4 and the `"w/o LCR (QT=0)"` baseline line.
     - **Offline calibration verification (post-audit gold check):** All **`40 / 40` (`100.0%`)** calibrated polyline vertices match `dev_gold` to **5 decimal places (`0.00000` error)** (e.g., `(a) Retriever-Only`: `0.04877, 0.04911, ..., 0.05691`; `(d) Cross-Encoder`: `0.08117, ..., 0.08139`).
     - **Projected corpus impact on `e21e3b7` (`out_dev_domain2_scan_cache`):** **`+40` Strict TP** (`1,163 → 1,203`), **`+40` Loose TP** (`2,410 → 2,450`), **`100.0%` slice precision** (`P: 0.235 → 0.241`, `R: 0.060 → 0.062`, `F1: 0.096 → 0.099`), `0` structural errors, `0` duplicate views, `0` missing IDs.
     - **Honest scope caveat:** Resolving `Qwen2.5-7B-Instruct` and `+ LCR` for `D006` Fig 3 requires **section-level default-setup inheritance** (Sec 4.1.2 p.10 + Sec 4.4 pp.12–13), not just text inside the panel frame; if a rule restricts strictly to panel-local text, `D006` Fig 3 also abstains (leaving `0` eligible rows across all 21 dev PDFs).

#### B. Generalizable source-only decision rule (6 gates — no paper IDs, no gold strings, no order inference)

Export a vector plot observation to the default Strict submission **if and only if all 6 gates pass** (otherwise abstain or keep under an opt-in diagnostic flag):

1. **Affine linear axis calibration gate:** Axis has ≥3 printed numeric ticks with linear fit residual ≤0.25 pt, uniform unit (`%` or fraction), and an explicit axis metric label. Reject RGB colorbars and uncalibrated encodings.
2. **Complete printed configuration gate:** Every exported row must resolve (a) an explicit printed `dataset_name` (or explicit paper-defined alias), (b) an explicit non-empty `rag_variant` bound unambiguously to the panel or visual series style (panel title, single-curve caption/section binding to an existing cached configuration, or uniquely matched legend marker/line style), and (c) an explicit `generator_model` whenever the metric depends on generation. **Hard abstention if `rag_variant=""` or generator is absent.**
3. **Explicit condition & hyperparameter isolation gate:** Any printed panel/axis parameter (`k=3`, `QT=0.1..1.0`, noise perturbation, `top-k`) must be kept as a distinct configuration/experiment condition — never collapse into an unconstrained configuration, and never map an input-length cap (`k=3`) or threshold (`QT`) into `metric_k`.
4. **Source-proven 2D deduplication gate:** Never deduplicate across figures using ordered rounded 1D arrays (`seen_series`) or PDF drawing order. Emit cross-figure `duplicate_of` links **only** when (i) the PDF explicitly states both figures plot the same experimental runs AND (ii) two independent calibrated axes establish a unique mutual 1-to-1 point match within calibration tolerance (`±1e-4`). Leave within-panel coincidences and 1D-only overlaps unlinked (`duplicate_of=""`).
5. **No table-duplicate reference baselines:** Do not emit horizontal reference lines (e.g., dashed baseline lines) when the same `(dataset, variant, generator, metric)` baseline already exists in a primary table.
6. **Single-series / bound-legend ambiguity gate:** Require either a single plotted series per calibrated panel (with panel-level method identity) or a 1-to-1 visual binding (stroke color + dash pattern + marker geometry) between each legend label and exactly one plotted series; abstain on multi-series overlays with overlapping or unbound styles.

#### C. Positive and negative cases (with PDF locators)

- **Positive cases:**
  - *Strict-safe export (with section-level setup binding):* **`D006` Fig 3 (p.14; Sec 4.1.2 p.10; Sec 4.4 pp.12–13)** — 4 single-polyline panels (`(a)`–`(d)`), calibrated `NDCG@5` (`metric_k=5`), printed `NaturalQuestions` + `BM25`, 1-to-1 match to cached `C02`/`C08`/`C12`/`C14` (`40` eligible rows, `40/40` exact to 5 decimals).
  - *Proven 2D cross-figure deduplication (structure only; still fails Gate 2 for Strict export):* **`D014` Fig 3 (p.6) ↔ Figs 10–12 (pp.16–18; Sec A.3 p.12)** — explicit textual link plus two independent calibrated axes resolve `348/352` (`5` pairs) and `328/352` (`1` pair) points uniquely (`max_err ≤ 2.63e-6`), cleanly isolating the `4–24` coincident points that must stay unlinked.
- **Negative cases (must abstain):**
  - **`D014` Fig 8 (p.14; Sec A.6 p.13)** — `1,166` rows, generator-free input-length plot (`config_id=""`, fails Gate 2); 2D check vs Fig 2 confirms distinct sampling draw (`55–311` unmatched).
  - **`D014` Fig 9 (p.14; Sec A.6 p.13)** — `1,166` rows, explicit `k=3` sentence-count cap (`metric_k=""`, fails Gates 2 & 3; `329/352` HotpotQA & `205/231` WoW points differ from Fig 2).
  - **`D014` Fig 5 (p.13; Sec A.5 p.12)** — `704` rows, `Noisy HotpotQA` unnamed simulation points + missing `task_id=""` (fails Gate 2; `328/352` unmatched vs Fig 2).
  - **`D014` Figs 2, 3, 10–12 scatter points (pp.5,6,16–18; Sec 3.2 p.3)** — `11,088` rows, unnamed `(p_gold, p_noise)` points (`rag_variant=""`, fails Gate 2); `Fig 10 ↔ 11 ↔ 12` share only 1D `Answer F1` (`47–131` ties/panel, fails Gate 4); `4–24` within-panel coincidences must never be linked by drawing order.
  - **`D014` Figs 2, 5, 8, 9 colorbars (pp.5,13,14)** — continuous RGB fill without calibrated axis ticks (fails Gate 1).
  - **`D014` Figs 3, 4, 6, 10–12 dashed reference lines (pp.6,8,13,16–18)** & **`D006` Fig 3 red dashed `w/o LCR (QT=0)` lines (p.14)** — duplicate primary Tables 1–2 / Table 2 (fail Gate 5).
  - **`D009` Fig 3 (p.7; Sec 4.4 / Sec 5)** — 6 panels (`PopQA`, `HotpotQA`, `2WikiMultiHopQA` × `WMV`/`BoN`) with 4 overlapping multi-series curves (`Majority Voting`, `PRO-STEP PRM`, `VersaPRM`, `Qwen-Math-PRM`); requires verified legend-to-style binding and composite variant naming before safe export (fails Gate 6 without explicit multi-series legend binder).
  - **`D012` Fig 2 (p.9; Sec 5)** — multi-line stress test whose printed 30%-noise endpoint values duplicate Table 5 on the same page (fails Gates 5 & 6).

---

### 3 · Reproducible Isolated Candidate Benchmark at `e21e3b7`

Reproduced offline (`0` API tokens) from the complete 21-paper `out_dev_domain2_scan_cache` into scratch directories outside the repository (leaving all workspace exports untouched):

```powershell
python main.py --input dev --cache out_dev_domain2_scan_cache --output <isolated_base> --rebuild-csv-only
python main.py --input dev --cache out_dev_domain2_scan_cache --output <isolated_plot> --rebuild-csv-only --recover-plot-points
python tools/check_submission.py <dir> dev --json-report <dir>/validation.json
python scripts/evaluate.py <dir> dev_gold --show-diffs 0
```

| Isolated export (`e21e3b7`, `out_dev_domain2_scan_cache`, 21/21) | Scored rows | Strict P / R / F1 (TP) | Loose P / R / F1 (TP) | Without D014 Strict F1 (TP) | Structural errors | Review items | Matched citations (native PDF text) |
|---|---:|---|---|---|---:|---:|---|
| Default (`--rebuild-csv-only`) | 4,945 | `0.235 / 0.060 / 0.096` (`1,163`) | `0.487 / 0.124 / 0.198` (`2,410`) | `0.186` (`1,163`) | `0` | `1,073` | `7,194 / 7,743` (`549` scan-page unresolved; `0` native unresolved) |
| Plot candidate (`--recover-plot-points`) | 19,069 (`+14,124`) | `0.061 / 0.060 / 0.060` (`1,163`, **`+0 TP`, `-0.174 P`, `-0.036 F1`**) | `0.658 / 0.647 / 0.652` (`12,545`, `+10,135 TP`) | `0.186` (`1,163`, `+0`) | `0` | `2,943` (`+1,870`) | `21,318 / 21,867` (`+14,124/+14,124` D014 figure captions matched; `549` scan-page unresolved) |

- **Scope & table counts (`--recover-plot-points`):** `in_scope agreement = 21/21 (100.0%)`, `stubs=0`, `publications=21`, `configurations=500 (+3: PC1–PC3)`, `datasets=106`, `tasks=54`, `experiments=132`, `results=19,237 (+14,124)`, `issues=2,642 (+0)`.
- **Review delta (`+1,870`):** `+1,166` `primary result without config_id` (100% `D014` Fig 8) + `+704` `primary result without task_id` (100% `D014` Fig 5).
- **Mismatch delta (`evaluate.py`):** Paired loose-to-strict rows jumped `1,247 → 11,382` (`dataset_name: 781 → 4,528`, `rag_variant: 445 → 10,580`, `generator_model: 709 → 6,628`, `metric_k: 58 → 58`).
- **Gate verdict:** **DO NOT adopt `--recover-plot-points` into default export.** Keep scatter recovery opt-in; if Codex later implements a Strict-safe vector plot path, gate it with the 6-rule source-only filter above and pilot on single-curve polyline plots (`D006` Fig 3, `40` rows) rather than unconfigured dense scatter grids.

## RECALL-DEV-002

- Status (`complete` or `blocked`): `complete`
- Acceptance check: **PASS — `--recover-table-cells` ELIGIBLE FOR DEFAULT ADOPTION** (`0` structural errors, higher corpus Strict F1 `0.060 → 0.061`, `+10` Strict TP, `+12` Loose TP, `0` per-paper Strict F1 or Loose TP losses, `0` new review items from table recovery).
- Git commit (from `git rev-parse --short HEAD`): `5d872ad`
- Cache & constraints: Used complete 21-paper `out_dev_domain2_scan_cache`; spent **`0` API tokens**; kept jury `out_dev/`, previous comparison bundles, LLM config, and 111-paper `test/` untouched; Tesseract `v5.4.0.20240606` via `C:\Program Files\Tesseract-OCR`.

### Part 1 · Isolated Table-Recovery Benchmark (`out_dev_recall21_table` vs `out_dev_recall21_default`)

- **Coverage, exit codes, and wall times**:
  - Coverage: `21/21` publications (`in_scope agreement = 21/21 = 100.0%`, `stubs=0`).
  - Rebuild (`--rebuild-csv-only --ocr --recover-table-cells`): exit **`0`**, wall time `371.0s` (`results=5113 (+34)`, `issues=2634 (+26)`, other 5 tables unchanged: `publications=21, configurations=492, datasets=106, tasks=54, experiments=132`).
  - Checker (`check_submission.py --ocr`): exit **`2`**, wall time `1573.2s` (included a ~20-minute laptop sleep mid-run that triggered a transient Windows negative-timeout clock jump on `D013` page 11: `timed out after -1200.38s`).
  - Evaluator (`evaluate.py --show-diffs 20`): exit **`0`**, wall time `1.5s`.
- **Metrics vs recorded default (`4,911` scored predictions, `731` Strict TP, `1,842` Loose TP, `550` review items)**:
  - Scored predictions: `4,945` (`+34`)
  - `datasets (by name)`: `P=0.604 R=0.266 F1=0.369 (tp=64)` (`+0`)
  - `models (rag_variant+generator)`: `P=0.419 R=0.044 F1=0.079 (tp=206)` (`+0`)
  - **`Strict value`**: **`P=0.150 R=0.038 F1=0.061 (tp=741, pred=4945, gold=19392)`** (**`+10 TP`, `+0.001 F1`, `+0.001 P`** vs default `0.060 / 731`)
  - **`Loose value`**: **`P=0.375 R=0.096 F1=0.152 (tp=1854, pred=4945, gold=19392)`** (**`+12 TP`, `+0.001 R`** vs default `1,842`)
  - **`without D014`**: Strict **`P=0.153 R=0.097 F1=0.119 (tp=741, pred=4854, gold=7632)`** (`+10 TP / +0.002 F1` vs default `0.117`); Loose **`P=0.378 R=0.241 F1=0.294 (tp=1836)`** (`+12 TP` vs default `1,824`)
  - Loose-to-strict mismatches: `Paired rows: 1113 (+2); dataset_name=644 (+0), rag_variant=467 (+0), generator_model=579 (+2), metric_k=51 (+0)`.
- **Structural errors & reviews**:
  - Structural errors: **`0`**.
  - New reviews from table recovery: **`0`** (`D007` quote check `{'ok': 763}` — all `34` recovered cells verified verbatim with complete `config_id`/`dataset_id`/`task_id`/`experiment_id`). Missing-reference counts identical to default (`dataset_id=210, task_id=165, config_id=146`); observed `validation.json` had `549` review items (`26` quote not found + `1` page-9 quote + `1` sleep-induced `D013` OCR timeout warning leaving `259` unresolved quotes instead of `29` on non-sleep runs).
- **Changed papers & source location of added Strict matches**:
  - Only **`D007`** changed across all 21 papers (`0` regressions on any paper): `pred 698 → 732`, `Strict F1 0.276 → 0.283`, `Strict TP 201 → 211 (+10)`, `Loose TP 402 → 414 (+12)`.
  - All `34` recovered cells and all **`10` newly added Strict matches** come from **`D007`, PDF page `7`, `Table 2`** (`FLAN-T5-XL (3B)` `Accuracy` across `MuSiQue`, `HotpotQA`, `2WikiMultiHopQA`): `R731` (`HotpotQA / Adaptive Retrieval = 25.00`), `R732` (`2WikiMultiHopQA / Adaptive Retrieval = 34.20`), `R738` (`MuSiQue / Adaptive-RAG = 26.00`), `R741` (`HotpotQA / Adaptive-RAG = 44.40`), `R744` (`2WikiMultiHopQA / Adaptive-RAG = 46.40`), `R747` (`MuSiQue / Multi-step Approach = 25.80`), `R750` (`HotpotQA / Multi-step Approach = 47.00`), `R753` (`2WikiMultiHopQA / Multi-step Approach = 55.40`), `R758` (`HotpotQA / Adaptive-RAG w/ Oracle = 54.80`), `R761` (`2WikiMultiHopQA / Adaptive-RAG w/ Oracle = 59.40`).
- **Default adoption gate verdict**: **PASS** (`0` structural errors, higher corpus Strict F1 `0.060 → 0.061`, `0` per-paper Strict F1 or Loose TP losses).

### Part 2 · D014 Source-Evidence Matrix (Native PDF `dev/D014.pdf` + `out_dev_recall21_candidate`, completed before consulting gold)

All printed panel titles, axis labels, legends, and captions on pages 5, 6, 13, 14, and 16 are preserved identically by both `PyMuPDF` and `pypdf` native text extraction.

| Fig | PDF p. | Representative panel title / axes | Legend, caption & method locators | Printed label scopes | Legend-to-marker linkability (vector drawings) |
|---|---|---|---|---|---|
| **Fig 2** | p.5 | `HotpotQA GPT-4o-mini` (x: `Knowledge Precision` 0–1, y: `Knowledge Recall` 0–1, colorbar: 0.4–0.8) | Caption p.5 (*"response/answer F1... by GPT-4o-mini (top), LLaMA 3.1 8B (middle), Mistral 7B-Instruct (bottom). Left: WoW; right: HotpotQA. Dots in orange outperform 'full knowledge', cyan underperform 'no knowledge'"*); Sec 3.2 p.3 (*"hundreds of configurations... simulated retrieved and selected knowledge K'"*); Fig 1 p.2 (*"Simulated Knowledge Retrieval & Selection"*) | Whole figure: simulation pipeline, orange/cyan group rules; Panel: dataset (`Wizard of Wikipedia`/`HotpotQA`), generator (`GPT-4o-mini`, `LLaMA 3.1 8B`, `Mistral 7B-Instruct`); Group: orange/cyan halos; Point: **no** per-point `(p_gold, p_noise)` text label | **Group halos unambiguous** (exact RGB fill `(1.0, 0.65, 0.0)` orange / `(0.0, 1.0, 1.0)` cyan + larger radius); colorbar value is continuous RGB (`214` fills), **no** per-point label |
| **Fig 3** | p.6 | `HotpotQA Mistral 7B-Instruct` (top/mid/bot x: `Knowledge Precision` / `Knowledge Recall` / `Knowledge F1` 0–1; y: `Answer F1` 0.1–0.6) | Panel legend box (`---- Full Knowledge Answer F1`, `---- No Knowledge Answer F1`); Caption p.6 (*"HotpotQA answer F1 versus KP (top), KR (middle), KF1 (bottom). Left: GPT-4o-mini; right: Mistral-7B-Instruct"*) | Whole figure: HotpotQA meta-experiments; Panel: dataset + generator + x/y metrics; Group: 2 dashed reference baselines; Point: uniform blue marker, **no** per-point text label | **Reference lines unambiguous** (red dashed `(1,0,0)` = Full Knowledge, black dashed `(0,0,0)` = No Knowledge); all `2,112` scatter dots share 1 blue fill `(0.12, 0.47, 0.71)` (no per-point identity) |
| **Fig 5** | p.13 | `Noisy HotpotQA GPT-4o-mini` (x: `Knowledge Precision` 0–1, y: `Knowledge Recall` 0–1, colorbar: 0.4–0.7) | Caption p.13 (*"answer F1 versus knowledge precision for GPT-4o-mini on noisy HotpotQA"*); **Sec A.5 p.12** (*"deliberately inject noise into HotpotQA by removing one sentence from the gold knowledge set... create a noisy HotpotQA dataset"*) | Panel/Figure: `Noisy HotpotQA` + `GPT-4o-mini` + x/y metrics; Group: cyan halos `(0,1,1)` (`29` drawings); Point: continuous RGB fill (`150` fills), **no** per-point label | Cyan halos unambiguous; colorbar continuous RGB; **no** per-point label |
| **Fig 8** | p.14 | `HotpotQA Number of Knowledge Sentences` (x: `Knowledge Precision` 0–1, y: `Knowledge Recall` 0–1, colorbar: `0..8`; WoW panel: `1..7`) | Caption p.14 (*"number of selected knowledge sentences versus knowledge precision on Wizard of Wikipedia (left) and HotpotQA (right)"*); **Sec A.6 p.13** (*"As Figure 8 shows, the length of the knowledge input mostly correlates with knowledge precision"*) | Panel: dataset + `Number of Knowledge Sentences` (colorbar) + x/y metrics; **NO generator printed anywhere in Fig 8 or Sec A.6** (characterizes simulated input set $K'$ before generation) | Continuous RGB fill (`203` fills on p.14); **no** legend box, **no** generator |
| **Fig 9** | p.14 | `HotpotQA GPT-4o-mini k=3` (x: `Knowledge Precision` 0–1, y: `Knowledge Recall` 0–1, colorbar: 0.3–0.8) | Caption p.14 (*"by limiting the number of knowledge sentences up to k=3. Orange... cyan..."*); **Sec A.6 p.13** (*"we limit the number of knowledge sentences to k by randomly sub-sampling k sentences when more than k sentences are selected... We choose k = 3"*) | Panel: dataset + `GPT-4o-mini` + **`k=3` selection-cap condition**; Group: orange `(1,0.65,0)` / cyan `(0,1,1)` halos; Point: continuous RGB, **no** per-point label | Orange/cyan halos unambiguous; colorbar continuous RGB; **no** per-point label |
| **Fig 10** | p.16 | `Wizard of Wikipedia LLaMA 3.1 8B` (x: `Knowledge Precision` 0–1, y: `Answer F1` 0.22–0.28) | Panel legend box (`Full Knowledge Answer F1`, `No Knowledge Answer F1`); Caption p.16 (*"answer F1 versus KP for GPT-4o-mini (top), LLaMA 3.1 8B (middle), Mistral 7B-Instruct (bottom); left: WoW, right: HotpotQA"*); **Sec A.3 p.12** (*"Figures 10, 11, and 12 extend Figure 3"*) | Whole figure: extension of Fig 3 across all 3 generators × 2 datasets; Panel: dataset + generator + x/y metrics; Group: 2 dashed baselines; Point: uniform blue `(0.12,0.47,0.71)` (`1,749` dots) | Red/black dashed lines unambiguous; scatter dots uniform blue (no per-point label) |

- **Specific repeated-series pairs (source confirmation)**:
  1. *Intra-figure*: `Figure 3` (p.6) `HotpotQA Mistral 7B-Instruct` emits **`Answer F1` 3 times (`1,056 = 3 × 352`)** across its top (KP), middle (KR), and bottom (KF1) panels. The caption (p.6) and Sec 3.2 (p.3) confirm all three panels replot the **exact same `352` meta-experiment runs** against three different x-axes (same conditions, not independent experiments).
  2. *Cross-figure*: `Figure 2` (p.5) vs `Figure 3` (p.6) `HotpotQA GPT-4o-mini` `Knowledge Precision` have **`352 / 352` identical values** (`100%` overlap), and `Figure 2` vs `Figure 10` (p.16) `HotpotQA LLaMA 3.1 8B` `Knowledge Precision` match identically. **Sec A.3 (p.12)** explicitly confirms *"Figures 10, 11, and 12 extend Figure 3"* and **Sec 3.2 (p.3)** confirms Figures 2–4 plot the same simulated meta-experiments — so the source **confirms identical underlying conditions**, not coincidental matching values.
- **Figure 9 `k=3` semantics**: **Experiment / configuration setting (NOT `metric_k`)**. Sec A.6 (p.13) states *"we limit the number of knowledge sentences to k by randomly sub-sampling k sentences when more than k sentences are selected... We choose k = 3"* and Fig 9 caption (p.14) says *"by limiting the number of knowledge sentences up to k=3"*. It constrains input context length (configuration/protocol parameter), whereas the evaluated metrics remain `Knowledge Precision`, `Knowledge Recall`, and `Answer F1` (none are `@3` metrics).
- **Figures 5 & 8 nearby text**:
  - **Figure 5 (`Noisy HotpotQA`)**: Sec A.5 (p.12) explicitly defines `Noisy HotpotQA` as a perturbed version of the `HotpotQA` multi-hop QA dataset (1 gold knowledge sentence removed per example, average gold sentences `2.4 → 1.4`), directly establishing that the same **question-answering task** (`HotpotQA` QA / knowledge selection evaluation) applies to the exact Figure 5 panel!
  - **Figure 8 (`Number of Knowledge Sentences`)**: Sec A.6 (p.13) and caption (p.14) confirm Figure 8 plots the simulated knowledge set $K'$ length against KP/KR **before generation** — **no generator model applies** to Figure 8. Leaving `generator_model=""` (empty) is therefore faithful to the PDF (any invented generator label would be unsupported metadata).

### Part 3 · Comparison Against `dev_gold` Strict Keys, Gap Classification & Priority Order

Comparing representative `out_dev_recall21_candidate` rows against `dev_gold` Strict keys (`dataset_name`, `rag_variant`, `generator_model`, `metric_name`, `metric_k`, `value`) yields five distinct gap classes:

1. **`source-supported exact labels`**:
   - Datasets `HotpotQA` (Sec 4.1 p.3; panel titles pp.5,6,14,16) and `Noisy HotpotQA` (Sec A.5 p.12; panel title p.13); generator `GPT-4o-mini` (panel titles pp.5,6,13,14,16); metrics `Knowledge Precision`, `Knowledge Recall`, `Knowledge F1`, `Answer F1` (axis labels pp.5,6,13,14,16); `metric_k=""` (confirmed even for Fig 9 `k=3`).
   - *Tokenization/punctuation mismatch on source-supported labels*: PDF prints `LLaMA 3.1 8B` and `Mistral 7B-Instruct` (pp.5,6,16), whereas `dev_gold` omits spaces (`LLaMA3.1-8B`, `Mistral7B-Instruct`), which `evaluate.py`'s `n()` normalizes to different tokens (`'llama 3.1 8b'` vs `'llama3.1 8b'`; `'mistral 7b instruct'` vs `'mistral7b instruct'`).
2. **`explicit aliases`**:
   - `Wizard of Wikipedia` vs gold `WoW`: explicitly linked in **Sec 4.1 p.3** (*"Wizard of Wikipedia (WoW; Dinan et al., 2019)"*) and used interchangeably between panel titles (`Wizard of Wikipedia`, pp.5,14,16) and captions (`WoW`, Figs 2, 3, 10).
   - Table 1/2 abbreviations `KP`/`KR`/`KF1` vs `Knowledge precision`/`Knowledge recall`/`Knowledge F1`: explicitly defined in **Table 1 caption p.4** (*"knowledge precision (KP), recall (KR), and F1 (KF1)"*).
3. **`unsupported metadata` (leave empty in source-faithful extraction unless normalized by an explicit rubric)**:
   - `Figure 8` `generator_model`: PDF prints no generator (Sec A.6 p.13); gold wrote synthetic `'Generator-independent'` → leave `generator_model=""` because no generator exists in the PDF.
   - `rag_variant` exact gold strings: gold authored four bespoke descriptions (`'Simulated knowledge retrieval/selection: unconstrained sampled knowledge'`, `'...noisy HotpotQA'`, `'...input-length sampling'`, `'...maximum3sampled sentences'`). While the PDF prints `'Simulated Knowledge Retrieval & Selection'` (Fig 1 p.2) and `k=3` (Sec A.6 p.13 / Fig 9 p.14), gold's exact sub-variant phrasing is **not printed verbatim** in the PDF.
4. **`ambiguous grouping` / repeated-series duplication**:
   - In `dev_gold`, Figures 2 and 3 mark repeated `(KP, KR, Answer F1)` observations with `duplicate_of` pointing back to Figures 10–12 (`R109`, `R1495`, etc.), reducing `28,649` raw gold D014 rows to `11,760` scored rows. Candidate emitted all `14,124` rows with `duplicate_of=""` (`14,215` scored pred vs `11,760` gold), causing `+2,455` excess predictions (including `Figure 3 Mistral Answer F1` 3× repetition `1,056 = 3×352` and `Figure 2`/`Figure 3` `352/352` KP duplication).
   - `Figure 9` (`k=3`) is currently collapsed into the unconstrained `PC1` config instead of a distinct configuration with the `k=3` constraint recorded.
5. **`unlabeled plot values`**:
   - Individual scatter points have no printed numeric coordinates or `(p_gold, p_noise)` tags (calibrated linearly from axis ticks to `±0.0001`); colorbar metrics (`Answer F1` on Figs 2, 5, 9; `Mean selected knowledge sentences` on Fig 8) are encoded solely in continuous RGB fill without point labels.

- **Priority recommendation after context fixes (repeated-series precision vs missing axes/colorbars)**:
  - **Prioritize repeated-series precision (`duplicate_of` linking / deduplication) BEFORE recovering missing axes or colorbars.**
  - *Evidence*: `candidate` already over-predicts D014 (`14,215` scored predictions vs `11,760` scored gold) because `Figure 3 Mistral Answer F1` repeats `352` points 3× (`1,056`) and `Figure 2` / `Figure 3` / `Figures 10–12` emit identical replotted KP/KR/Answer F1 series without `duplicate_of`. Adding colorbars (`+~5,000` approximate RGB-quantized rows) or missing Figure 2 panels before deduplicating repeated series and fixing `rag_variant`/`WoW`/whitespace-alias linking would only worsen global Strict Precision dilution (`0.039`) and bloat review counts without improving Strict F1. Conversely, adopting `--recover-table-cells` as default is an immediate, clean win (`+10` Strict TP, `+12` Loose TP, `0` new reviews, `0` regressions).

## RECALL-DEV-001

- Status (`complete` or `blocked`): `complete`
- Acceptance check: **PASS WITH AUDIT FINDINGS** (zero API tokens spent; `out_dev/` jury bundle and `test/` untouched; `0` structural errors on both bundles; `0` per-paper Strict F1 regressions; `--recover-table-cells` adds `+10` Strict TP on `D007`; `--recover-plot-points` boosts overall Loose Recall `9.5% → 61.8%` / Loose F1 `0.152 → 0.623` (`+10,147` Loose TP) with accurate linear axis calibration, but dilutes overall Strict P/F1 `0.060 → 0.039` because D014 vector rows lack `rag_variant` and add `1,166` missing `config_id` + `704` missing `task_id` review warnings).
- Git commit (from `git rev-parse --short HEAD`): `dae1acc`
- Environment, cache, and unit tests:
  - Cache used: `out_dev_domain2_scan_cache` (all `21/21` complete JSONs from `DOMAIN2-DEV-001`; no fallback to `cache/` needed).
  - Tesseract: `v5.4.0.20240606` (`C:\Program Files\Tesseract-OCR` prepended to session `PATH`).
  - `python -m pytest tests/test_core.py`: not installed in `.venv`; ran `python -m unittest discover -s tests -p "test_core.py" -v` → exit **`0`**, **`Ran 44 tests in 1.381s — OK (skipped=1: test_gemini_retries_remote_protocol_error 'httpx missing')`**.
  - API tokens spent: **`0`** (`--rebuild-csv-only --ocr` only; configured LLM unchanged; `test/` 111 PDFs not touched).
- **Side-by-side comparison (`out_dev_recall21_default` vs `out_dev_recall21_candidate`, both on `out_dev_domain2_scan_cache`)**:
  - **Exit codes & runtimes** (note: `default` rebuild elapsed time `379.9s` included laptop sleep/wake; active OCR runtime was similar to `candidate`):
    - `out_dev_recall21_default`: rebuild exit `0` (`379.9s`), checker `--ocr` exit `2` (`367.8s`), evaluator exit `0` (`1.1s`).
    - `out_dev_recall21_candidate` (`--recover-table-cells --recover-plot-points`): rebuild exit `0` (`313.4s`; recovered `+34` table cells on `D007` and `+14,124` vector plot observations on `D014`), checker `--ocr` exit `2` (`450.1s`), evaluator exit `0` (`2.8s`).
  - **Coverage & row counts**:
    - Both: `21/21` publications (`in_scope agreement = 21/21 = 100.0%`, `stubs=0`).
    - `default`: `publications=21, configurations=492, datasets=106, tasks=54, experiments=132, results=5079, issues=2608` (scored numeric predictions: `4911`).
    - `candidate`: `publications=21, configurations=495 (+3: PC1/PC2/PC3), datasets=106, tasks=54, experiments=132, results=19237 (+14158), issues=2634 (+26)` (scored numeric predictions: `19069`, `+14158`).
  - **Strict & Loose P / R / F1 and TP** (vs `DOMAIN2-DEV-001` baseline `Strict TP=579 / F1=0.048`, `without D014 TP=579 / F1=0.093`, `Loose TP=1721 / F1=0.142`):
    - **`default` (`dae1acc` without recovery flags — already `+152` Strict TP over `b5cb065`!)**:
      - `datasets (by name)`: `P=0.604 R=0.266 F1=0.369 (tp=64)`
      - `models (rag_variant+generator)`: `P=0.419 R=0.044 F1=0.079 (tp=206)`
      - `Strict value`: **`P=0.149 R=0.038 F1=0.060 (tp=731, pred=4911, gold=19392)`** (`+152 TP` vs `DOMAIN2-DEV-001`!)
      - `Loose value`: **`P=0.375 R=0.095 F1=0.152 (tp=1842, pred=4911, gold=19392)`** (`+121 TP` vs `DOMAIN2-DEV-001`)
      - `without D014`: Strict `P=0.152 R=0.096 F1=0.117 (tp=731, pred=4820, gold=7632)`; Loose `P=0.378 R=0.239 F1=0.293 (tp=1824)`
      - Loose-to-strict mismatches: `Paired rows: 1111; dataset_name=644, rag_variant=467, generator_model=577, metric_k=51`
    - **`candidate` (`--recover-table-cells --recover-plot-points`)**:
      - `datasets (by name)`: `P=0.604 R=0.266 F1=0.369 (tp=64)` (`+0`)
      - `models (rag_variant+generator)`: `P=0.416 R=0.044 F1=0.079 (tp=206, pred=495)` (`+0 TP`, `+3 pred`)
      - `Strict value`: **`P=0.039 R=0.038 F1=0.039 (tp=741, pred=19069, gold=19392)`** (`+10 TP` vs `default`, `-0.021 F1` due to `+14,124` D014 rows having `0` Strict TP)
      - `Loose value`: **`P=0.629 R=0.618 F1=0.623 (tp=11989, pred=19069, gold=19392)`** (**`+10,147 TP`**, **`+52.3 pp` Loose Recall**, **`+0.471` Loose F1** vs `default`!)
      - `without D014`: Strict **`P=0.153 R=0.097 F1=0.119 (tp=741, pred=4854, gold=7632)`** (`+10 TP / +0.002 F1` vs `default`); Loose **`P=0.378 R=0.241 F1=0.294 (tp=1836)`** (`+12 TP`)
      - Loose-to-strict mismatches: `Paired rows: 11248; dataset_name=4391, rag_variant=10602, generator_model=6498, metric_k=51`
  - **Per-paper regressions (`default` vs `candidate`)**:
    - **`0` per-paper Strict F1 regressions!**
    - `D007` improved `F1=0.276 → 0.283` (`pred=698 → 732`, `+10` Strict TP from `--recover-table-cells`; also vs `b5cb065`, `default` improved `D006` `0.219 → 0.273` and `D007` `0.102 → 0.276`).
    - All other 20 publications had identical per-paper Strict F1 between `default` and `candidate`.
  - **Checker structural errors & review item categories (`check_submission.py --ocr`)**:
    - Structural errors: **`0`** on both `default` and `candidate`.
    - `default`: `550` review items — `dataset_id=210`, `task_id=165`, `config_id=146`, `quote not found=28`, `quote found on page 9=1`; quotes **`7,639 / 7,668 (99.62%)` matched**, `unresolved=29`.
    - `candidate`: **`2,420`** review items (`+1,870`) — **`config_id=1,312 (+1,166)`**, **`task_id=869 (+704)`**, `dataset_id=210 (+0)`, `quote not found=28 (+0)`, `quote found on page 9=1 (+0)`; quotes `21,823 / 21,852 (99.87%)` matched (`unresolved=29` — note checker confirms only caption text for vector observations).
- **D014 Vector Plot Spot-Check (rendered `dev/D014.pdf` pages 5, 6, 13, 14 at 180 DPI and visually inspected printed axis ticks & panel titles)**:
  - Total D014 vector observations recovered: **`14,124`** across 8 figures (`Figure 2` p.5: `2,442`; `Figure 3` p.6: `3,520`; `Figure 5` p.13: `704`; `Figure 8` p.14: `1,166`; `Figure 9` p.14: `1,166`; `Figure 10` p.16: `2,211`; `Figure 11` p.17: `1,166`; `Figure 12` p.18: `1,749`).
  - **Calibration against printed linear axis ticks (PASS — accurate on inspected panels)**:
    - `Figure 2` (p.5): printed linear x/y ticks `0.0, 0.2, 0.4, 0.6, 0.8, 1.0` (`Knowledge Precision`, `Knowledge Recall`); recovered min/max `0.0000..1.0000` across WoW (`231` pts/panel) and HotpotQA (`352` pts/panel). Dataset and credited generator (`GPT-4o-mini`, `LLaMA 3.1 8B`, `Mistral 7B-Instruct`) all appear verbatim in the corresponding panel titles.
    - `Figure 3` (p.6): printed y-axis (`Answer F1`) ticks are `0.3..0.8` for `HotpotQA GPT-4o-mini` (top dots visibly just above `0.8`, bottom dot at `~0.30`) and `0.1..0.6` for `HotpotQA Mistral 7B-Instruct` (top dots visibly just above `0.6`, bottom dot at `~0.10`). Recovered `Answer F1` ranges are **`0.3015..0.8379`** (`GPT-4o-mini`) and **`0.0987..0.6209`** (`Mistral 7B-Instruct`) — accurate linear calibration! Panel titles verbatim match dataset (`HotpotQA`) and generator.
    - `Figure 5` (p.13): panel title `Noisy HotpotQA GPT-4o-mini`; printed ticks `0.0..1.0` (`Knowledge Precision`, `Knowledge Recall`); recovered `n=352` each, `0.0000..1.0000`.
    - `Figure 9` (p.14): panel title `HotpotQA GPT-4o-mini k=3`; printed y-axis visibly peaks just below `1.0` (`~0.96`); recovered `Knowledge Recall max=0.9626` (`n=352`) — accurate!
  - **Calibration / panel coverage discrepancies**:
    - `Figure 2` (p.5): `HotpotQA GPT-4o-mini` recovered `Knowledge Precision` (`352`) but **missed `Knowledge Recall` (`0`)**, and `HotpotQA Mistral 7B-Instruct` (bottom-right panel) was **completely missed (`0` rows)**; colorbars (`Answer F1` on Figures 2, 5, 9 and sentence count on Figure 8) are not extracted.
    - `Figure 3` (p.6): `HotpotQA GPT-4o-mini` emitted `Answer F1` from only 1 of 3 vertical panels (`n=352`), whereas `HotpotQA Mistral 7B-Instruct` emitted `Answer F1` from all 3 vertical panels (`n=1,056`).
  - **Unsupported / dropped context**:
    - `Figure 9` (p.14) panel titles explicitly include **`k=3`** (`Wizard of Wikipedia GPT-4o-mini k=3`, `HotpotQA GPT-4o-mini k=3` — length-constrained selection up to 3 sentences), yet those `1,166` rows are credited to the same unconstrained `PC1` (`generator_model='GPT-4o-mini', rag_variant=''`) with `metric_k=''`, losing the `k=3` experimental condition.
  - **Repeated series**:
    - Intra-figure: `Figure 3` `HotpotQA Mistral 7B-Instruct` repeats the same `352`-point `Answer F1` series **3x** (`1,056` rows across the KP/KR/KF1 panels).
    - Cross-figure: `HotpotQA GPT-4o-mini` `Knowledge Precision` (`352` pts) is **100% identical (`352/352` overlap)** between `Figure 2` and `Figure 3` (and substantially overlaps `Figure 8`: `303/352`, `Figure 3 Mistral`: `279/352`); `HotpotQA LLaMA 3.1 8B` KP is identical between `Figure 2` and `Figure 10` (same underlying meta-experiment replotted across figures).
  - **Points without complete configuration / links**:
    - **`1,166` rows with `config_id=""`** (all from `Figure 8` p.14, whose panel titles `Wizard of Wikipedia / HotpotQA Number of Knowledge Sentences` legitimately omit any generator model — accounts for 100% of the `+1,166` checker `primary result without config_id` jump).
    - **`704` rows with `task_id=""`** (all from `Figure 5` p.13 `Noisy HotpotQA` — accounts for 100% of the `+704` checker `primary result without task_id` jump).
    - **`12,958` rows (`PC1=5137, PC2=4323, PC3=3498`) have `rag_variant=""`** (generator-only configs; `0` missing `dataset_id`, `0` missing `experiment_id`). Because every D014 vector row lacks `rag_variant` (and `Wizard of Wikipedia` vs gold `WoW`), `D014` contributes **`+10,135` Loose TP** but **`0` Strict TP**, explaining the global Strict F1 dilution (`0.060 → 0.039`).
- **Exact `scripts/evaluate.py out_dev_recall21_candidate dev_gold --show-diffs 20` Output**:
  ```text
  Scored publications: 21 (D001, D002, D003, D004, D005, D006, D007, D008, D009, D010, D011, D012, D013, D014, D015, D016, D017, D018, D019, D020, D021)
  MISSING from result (recall=0): 0 -

  == publications.csv: scope decision
  in_scope agreement: 21/21 = 100.0%
  unprocessed (scope unresolved): 0 -
  included: pred 21 vs gold 21; wrong: -

  == row counts (result vs gold, scored pubs only)
  publications         21 vs      21  (+0)
  configurations      495 vs    4733  (-4238)
  datasets            106 vs     241  (-135)
  tasks                54 vs      90  (-36)
  experiments         132 vs     142  (-10)
  results           19237 vs   37616  (-18379)
  issues             2634 vs     134  (+2500)

  == Precision / Recall / F1
  datasets (by name)                                         P=0.604 R=0.266 F1=0.369  (tp=64, pred=106, gold=241)
  models (rag_variant+generator)                             P=0.416 R=0.044 F1=0.079  (tp=206, pred=495, gold=4733)
  metric values (strict: dataset+model+metric+k+value)       P=0.039 R=0.038 F1=0.039  (tp=741, pred=19069, gold=19392)
  metric values (loose: metric name+value)                   P=0.629 R=0.618 F1=0.623  (tp=11989, pred=19069, gold=19392)

  == loose matches that fail strict matching
    D001 em=0.172: rag_variant pred='threadrag w o stm llm extracted triplets' gold='threadrag ablation no sn no stg no edp'
    D001 em=0.206: rag_variant pred='graph free' gold='graph free controlled graph free ablation'
    D001 em=0.224: rag_variant pred='threadrag w o stm llm extracted triplets' gold='threadrag ablation no sn no stg no edp'
    D001 em=0.232: rag_variant pred='threadrag w o sn fixed length chunks' gold='threadrag ablation edp only no sn or stg'
    D001 em=0.238: rag_variant pred='threadrag w o stm llm extracted triplets' gold='threadrag ablation no sn no stg no edp'
    D001 em=0.258: rag_variant pred='graph free' gold='graph free controlled graph free ablation'
    D001 em=0.274: rag_variant pred='graph free' gold='graph free controlled graph free ablation'
    D001 em=0.286: rag_variant pred='no subgraph' gold='threadrag selection no subgraph'
    D001 em=0.286: rag_variant pred='threadrag w o edp' gold='threadrag ablation sn stg no edp'
    D001 em=0.292: rag_variant pred='threadrag full' gold='threadrag ablation stg edp no sn'
    D001 em=0.294: rag_variant pred='bfs depth 3' gold='threadrag selection bfs depth 3'
    D001 em=0.302: rag_variant pred='dfs depth 3' gold='threadrag selection dfs depth 3'
    D001 em=0.304: rag_variant pred='kg paths' gold='threadrag representation kg paths'
    D001 em=0.308: rag_variant pred='threadrag w o sn fixed length chunks' gold='threadrag ablation edp only no sn or stg'
    D001 em=0.31: rag_variant pred='kg triplets' gold='threadrag representation kg triplets'
    D001 em=0.316: rag_variant pred='kg texts' gold='threadrag representation kg texts'
    D001 em=0.324: generator_model pred='' gold='llama3 8b instruct'
    D001 em=0.324: rag_variant pred='edp' gold='threadrag selection edp'
    D001 em=0.324: rag_variant pred='threadrag full' gold='threadrag ablation sn stg edp'
    D001 em=0.326: rag_variant pred='threadrag w o sn fixed length chunks' gold='threadrag ablation edp only no sn or stg'
  Paired rows: 11248; shown: 20
  Field mismatches: dataset_name=4391, rag_variant=10602, generator_model=6498, metric_k=51

  == without D014
  value        P=0.153 R=0.097 F1=0.119  (tp=741, pred=4854, gold=7632)
  value_loose  P=0.378 R=0.241 F1=0.294  (tp=1836, pred=4854, gold=7632)

  == per publication (strict value F1)
  D001: F1=0.231 P=0.465 R=0.154 pred=127 gold=383
  D002: F1=0.000 P=0.000 R=0.000 pred=216 gold=316
  D003: F1=0.024 P=0.118 R=0.013 pred=76 gold=673
  D004: F1=0.000 P=0.000 R=0.000 pred=225 gold=207
  D005: F1=0.000 P=0.000 R=0.000 pred=262 gold=346
  D006: F1=0.273 P=0.332 R=0.232 pred=394 gold=565
  D007: F1=0.283 P=0.288 R=0.278 pred=732 gold=758
  D008: F1=0.282 P=0.576 R=0.187 pred=125 gold=385
  D009: F1=0.275 P=0.300 R=0.254 pred=609 gold=721
  D010: F1=0.000 P=0.000 R=0.000 pred=62 gold=152
  D011: F1=0.216 P=0.302 R=0.168 pred=192 gold=345
  D012: F1=0.016 P=0.019 R=0.013 pred=525 gold=765
  D013: F1=0.006 P=0.011 R=0.004 pred=188 gold=486
  D014: F1=0.000 P=0.000 R=0.000 pred=14215 gold=11760
  D015: F1=0.000 P=0.000 R=0.000 pred=193 gold=222
  D016: F1=0.000 P=0.000 R=0.000 pred=8 gold=72
  D017: F1=0.000 P=0.000 R=0.000 pred=221 gold=232
  D018: F1=0.000 P=0.000 R=0.000 pred=242 gold=317
  D019: F1=0.030 P=0.048 R=0.021 pred=126 gold=280
  D020: F1=0.000 P=0.000 R=0.000 pred=312 gold=343
  D021: F1=0.000 P=0.000 R=0.000 pred=19 gold=64
  ```

## DOMAIN2-DEV-001

- Status (`complete` or `blocked`): `complete`
- Acceptance check: **PASS WITH NOTES** (0 structural errors, 99.63% verified quotes across all 21 dev PDFs including 3 scans, 100% native-text quote verification, +60 Strict TP over `MVP-DEV-001`, all 4 Domain 2 UI checks PASS with 0 console/network errors; note checker exit `2` due to `521` missing primary-result IDs + `29` remaining scan quotes, plus a `D013` re-extraction Strict F1 dip noted under Regressions).
- Git commit (from `git rev-parse --short HEAD`): `b5cb065`
- Python, Tesseract, and unit tests:
  - Python: `3.13.1` (`.venv\Scripts\python.exe`), Tesseract: `v5.4.0.20240606` (`C:\Program Files\Tesseract-OCR\tesseract.exe`, added to session `PATH`).
  - `python -m pytest tests/test_core.py`: exit `1` (`No module named pytest` in `.venv`).
  - `python -m unittest discover -s tests -p "test_core.py" -v`: exit **`0`** — `Ran 34 tests in 0.979s — OK (skipped=1: test_gemini_retries_remote_protocol_error 'httpx missing')`.
- **Stage 1 (Zero-token checkpoint on existing `cache/` → `out_dev_domain2/`)**:
  - Commands & exit codes:
    - `python main.py --input dev --output out_dev_domain2 --rebuild-csv-only` → exit **`0`** (`docs=21 stubs=0`)
    - `python tools/check_submission.py out_dev_domain2 dev --json-report out_dev_domain2/validation.json` → exit **`2`** (`Errors: 0; review items: 1138`; `source_text_mode: "native PDF text only"`)
    - `python scripts/evaluate.py out_dev_domain2 dev_gold --show-diffs 20` → exit **`0`**
  - Row counts: `publications=21, configurations=487, datasets=105, tasks=51, experiments=135, results=5112, issues=2731`.
  - Evaluator vs `MVP-DEV-001` baseline (`Strict TP=519 / F1=0.043`, `without D014 F1=0.083`, `Loose TP=1756 / F1=0.144`):
    - `in_scope agreement`: `21/21 = 100.0%` (`+0`)
    - `datasets (by name)`: `P=0.600 R=0.261 F1=0.364 (tp=63)` (**`+7 TP`**, **`+0.040 F1`**)
    - `models (rag_variant+generator)`: `P=0.435 R=0.045 F1=0.081 (tp=212)` (`+0`)
    - `Strict value`: `P=0.122 R=0.031 F1=0.050 (tp=605, pred=4970)` (**`+86 TP`**, **`+0.007 F1`**; without D014: `F1=0.097`, **`+0.014`**; `D008` jumped `0.024 → 0.282`, `D007` `0.074 → 0.102`)
    - `Loose value`: `P=0.354 R=0.091 F1=0.145 (tp=1761)` (**`+5 TP`**, **`+0.001 F1`**; without D014: `F1=0.279`, `tp=1743`)
    - Loose-to-strict mismatches: `Paired rows: 1156; dataset_name=694 (-89), rag_variant=457 (+1), generator_model=519 (+5), metric_k=81 (+0)`.
  - Missing-reference breakdown (Stage 1): `541` total (`dataset_id=269, task_id=136, config_id=135, experiment_id=1`).
  - Issue & quote counts (Stage 1, native-only checker): `quotes requested=7831, matched=7234, unresolved=597` (all `597` are `no text layer/OCR text on this page` from the 3 scans); **native-text unresolved quotes: `0` in `results.csv`, `0` in `issues.csv`** (down from `13` in `MVP-DEV-001`); `issues` non-empty `source_fragment`: `2719 / 2731` (**`12` unverified native-text issue quotes cleared**).
- **Stage 2 (Targeted live 300-DPI RGB PSM-3 OCR + DeepSeek on `D002, D013, D021` in scratch cache `out_dev_domain2_scan_cache` → promoted to `out_dev/`)**:
  - Preserved original `cache/` untouched; copied all 21 JSONs to fresh `out_dev_domain2_scan_cache`.
  - Backend confirmed in CLI log: `backend=DeepSeekClient model=deepseek-v4-flash docs=3 workers=1`.
  - Commands & exit codes:
    - `python main.py --input dev --output out_dev_domain2_scan_retry --cache out_dev_domain2_scan_cache --only D002 D013 D021 --force --ocr --workers 1` → exit **`0`** (`1785s`, `docs=3 stubs=0`)
    - `python main.py --input dev --output out_dev --cache out_dev_domain2_scan_cache --rebuild-csv-only --ocr` → exit **`0`** (`docs=21 stubs=0`)
    - `python tools/check_submission.py out_dev dev --ocr --json-report out_dev/validation.json` → exit **`2`** (`Errors: 0; review items: 550`; `source_text_mode: "native plus local OCR on image-only pages"`)
    - `python scripts/evaluate.py out_dev dev_gold --show-diffs 20` → exit **`0`**
  - Total Stage 2 API tokens (`DeepSeekClient / deepseek-v4-flash`): **`in=262,579`, `out=87,133`** (`D002: in=84,028 out=38,306`; `D013: in=129,119 out=43,278`; `D021: in=49,432 out=5,549`).
  - Final Stage 2 `out_dev/` row counts: `publications=21, configurations=492 (+5 vs MVP), datasets=106 (+1), tasks=54 (+3), experiments=132 (-3), results=5079 (+21), issues=2716 (+712; includes RULE_UNIT_AMBIGUITY=2286, RULE_AT_K_CONSISTENCY=13)`.
  - **Per-scan evidence (`D002`, `D013`, `D021` — mode, row counts, and quote coverage vs `MVP-DEV-001`)**:
    - `D002`: `OCR text mode (300 dpi RGB PSM 3)`, `227` raw / `227` results / **`216` numeric CSV rows**, `53` issues (`5` unverified issue quotes cleared), quote check `ok=187, repaired=12, unverified=28`, checker OCR quotes **`250 / 275 (90.9%)` matched**, `unresolved=25` (down from **`161`** in `MVP-DEV-001`, **`-136`**!).
    - `D013`: `OCR text mode (300 dpi RGB PSM 3)`, `214` raw / `214` results / **`188` numeric CSV rows**, `19` issues (`1` unverified issue quote cleared), quote check `ok=204, repaired=6, unverified=4`, checker OCR quotes **`230 / 232 (99.1%)` matched**, `unresolved=2` (down from **`219`** in `MVP-DEV-001`, **`-217`**!).
    - `D021`: `OCR text mode (300 dpi RGB PSM 3)`, `22` raw / `22` results / **`19` numeric CSV rows**, `14` issues (`1` unverified issue quote cleared), quote check `ok=20, unverified=2`, checker OCR quotes **`33 / 35 (94.3%)` matched**, `unresolved=2` (down from **`19`** in `MVP-DEV-001`, **`-17`**!).
  - **Quote verification breakdown — cleared unverified issue quotes vs newly confirmed OCR evidence**:
    - Overall quotes (`out_dev/validation.json`): **`7,747 / 7,776 (99.63%)` matched**, `unresolved=29` (down from `6,650 / 7,062 = 94.17%`, `unresolved=412` in `MVP-DEV-001` — **`-383` unresolved quotes, `-93.0%`**, and total checker review items dropped `953 → 550`, **`-403`**!).
    - **Cleared as unverified in `issues.csv`**: **`19` total** (`12` on the 18 native-text PDFs + `7` on the 3 scans: `D002=5, D013=1, D021=1`; `2,697 / 2,716` issue rows retain verified `source_fragment`; `0` unresolved quotes remain in `issues.csv`).
    - **Newly confirmed OCR evidence**: across the 3 scans, **`513 / 542 (94.6%)`** requested quotes are now exact-substring confirmed against 300-DPI RGB PSM-3 OCR text (dropping scan unresolved quotes from `399 → 29`: `D002=25, D013=2, D021=2`, with `0` unresolved across all 18 native-text PDFs).
  - **Missing-reference breakdown (Stage 2 vs `MVP-DEV-001`)**: `521` total (`-20` vs `541` in `MVP-DEV-001`): `dataset_id=210 (-59)`, `task_id=165 (+29)`, `config_id=146 (+11)`, `experiment_id=0 (-1)`.
  - **Stage 2 Evaluator vs `MVP-DEV-001` (and vs Stage 1)**:
    - `in_scope agreement`: `21/21 = 100.0%`
    - `datasets (by name)`: `P=0.604 R=0.266 F1=0.369 (tp=64)` (**`+8 TP / +0.045 F1` vs MVP**, `+1 TP` vs Stage 1)
    - `models (rag_variant+generator)`: `P=0.419 R=0.044 F1=0.079 (tp=206)` (`-6 TP` vs MVP/Stage 1)
    - `Strict value`: `P=0.118 R=0.030 F1=0.048 (tp=579, pred=4922)` (**`+60 TP / +0.005 F1` vs MVP**; `-26 TP` vs Stage 1 due to `D013` re-extraction; without D014: `F1=0.093`, **`+0.010` vs MVP**)
    - `Loose value`: `P=0.350 R=0.089 F1=0.142 (tp=1721)` (`-35 TP / -0.002 F1` vs MVP; without D014: `F1=0.273`, `tp=1703`)
    - Loose-to-strict mismatches: `Paired rows: 1142; dataset_name=696 (-87 vs MVP), rag_variant=471 (+15), generator_model=525 (+11), metric_k=51 (-30 vs MVP)`.
- **Stage 3 UI Demo Verification (`http://127.0.0.1:8000/` via `python scripts/serve_ui.py out_dev`)**:
  - Health & KPIs (**PASS**): 0 console errors, 9/9 HTTP 200 fetches (all 7 CSVs + `/data/validation.json`). Four KPIs: `Обработанные статьи: 21 (из 21 в пакете)`, `Извлечённые результаты: 4 973 (Числовые значения)`, `Проверенные цитаты: 99,6 % (7 747 из 7 776 подтверждены)`, `Замечания: 2 716 (Записи в issues.csv)`.
  - Exact-context comparison with signed baseline delta (**PASS**): `Сравнить с baseline` on `D006` (`NaturalQuestions · NDCG@5 · k=5 · fraction`) compared baseline `C01` (`Retriever-Only`, `BM25`, `top_k=10`, `0.0489 fraction`) vs `C08` (`RankGPT + LCR`, `Qwen2.5-7B-Instruct`, `0.0587 fraction`) with exact signed delta **`+0,0098`**.
  - Result with raw + normalized values & verbatim quote (**PASS**): `D001 / R001` (`EM`) shows raw `.204`, normalized `0.204 fraction`, `стр. 6 · Table 1`, quote `RA-CoT\n.204\n.330\n.202\n.261\n.142\n.210` (also verified `D006 / R002`: raw `0.0587`, normalized `0.0587 fraction`, `стр. 11 · 4.2`, quote `to 0.0587 (a 20% relative increase)`).
  - `RULE_*` filter (**PASS**): `RULE_AT_K_CONSISTENCY` filtered `13` rows (sample: `D009 | F1: metric_k=128 exceeds configuration top_k=3; check the retrieval stage.`); `RULE_UNIT_AMBIGUITY` filtered `2 286` rows (sample: `D001 | EM=0.204: the source does not establish a unique scale. Value retained.`).
  - Data Passport tab (`Паспорт данных`) (**PASS**): displays schema with exact row counts matching `out_dev/validation.json` (`publications=21, configurations=492, datasets=106, tasks=54, experiments=132, results=5079, issues=2716`), type/normalization rules, and the 4 `RULE_*` definitions.
- **Parser, Checker, and UI Regressions / Notes**:
  1. **Parser/LLM variance on `D013` re-extraction (regression in Strict F1)**: `D013` went from `235` numeric rows (`Strict F1=0.078`, `tp=28`) in Stage 1 / `MVP-DEV-001` to `188` numeric rows (`Strict F1=0.006`, `tp=2`) in Stage 2 (`-26` Strict TP overall vs Stage 1, though OCR quote coverage surged from `13/232` to `230/232 = 99.1%`). Also `D013:1-3` had 2 brief `JSONDecodeError` retries (`out=1` empty responses) before succeeding on attempt 3, and `D002:meta` had 1 `TimeoutError` retry (`1118s` total for `D002`).
  2. **Transient Windows Tesseract timeout quirk during export**: During `out_dev_domain2_scan_retry` export, `D013` logged `WARN OCR quote check skipped (PDF page 4: Command '['tesseract', 'stdin', 'stdout', '-l', 'eng', '--psm', '3']' timed out after -19.77612660000159 seconds)` (negative elapsed timeout, likely OS clock/sleep or `pytesseract` timeout edge case). It did NOT recur during `--rebuild-csv-only --ocr`, where `D013` completed cleanly (`ok=204, repaired=6, unverified=4`).
  3. **Checker**: `0` regressions — `errors=0`, unresolved quotes dropped `-93.0%` (`412 → 29`), review items dropped `-42.3%` (`953 → 550`). Note `results:163` (`D002`) is the only quote found on another page (`found on pages 9`).
  4. **UI**: `0` blocking regressions (4 tabs render cleanly at `1280x800`; minor CSS slide-in transition when reopening detail drawer right after closing another).
  5. **Test runner**: `.venv` does not have `pytest` installed (`unittest` ran all 34 tests cleanly). `test/` (111 PDFs) was not touched.
- **Exact Stage 2 `scripts/evaluate.py out_dev dev_gold --show-diffs 20` Output**:
  ```text
  Scored publications: 21 (D001, D002, D003, D004, D005, D006, D007, D008, D009, D010, D011, D012, D013, D014, D015, D016, D017, D018, D019, D020, D021)
  MISSING from result (recall=0): 0 -

  == publications.csv: scope decision
  in_scope agreement: 21/21 = 100.0%
  unprocessed (scope unresolved): 0 -
  included: pred 21 vs gold 21; wrong: -

  == row counts (result vs gold, scored pubs only)
  publications         21 vs      21  (+0)
  configurations      492 vs    4733  (-4241)
  datasets            106 vs     241  (-135)
  tasks                54 vs      90  (-36)
  experiments         132 vs     142  (-10)
  results            5079 vs   37616  (-32537)
  issues             2716 vs     134  (+2582)

  == Precision / Recall / F1
  datasets (by name)                                         P=0.604 R=0.266 F1=0.369  (tp=64, pred=106, gold=241)
  models (rag_variant+generator)                             P=0.419 R=0.044 F1=0.079  (tp=206, pred=492, gold=4733)
  metric values (strict: dataset+model+metric+k+value)       P=0.118 R=0.030 F1=0.048  (tp=579, pred=4922, gold=19392)
  metric values (loose: metric name+value)                   P=0.350 R=0.089 F1=0.142  (tp=1721, pred=4922, gold=19392)

  == loose matches that fail strict matching
    D001 em=0.172: rag_variant pred='threadrag w o stm llm extracted triplets' gold='threadrag ablation no sn no stg no edp'
    D001 em=0.206: rag_variant pred='graph free' gold='graph free controlled graph free ablation'
    D001 em=0.224: rag_variant pred='threadrag w o stm llm extracted triplets' gold='threadrag ablation no sn no stg no edp'
    D001 em=0.232: rag_variant pred='threadrag w o sn fixed length chunks' gold='threadrag ablation edp only no sn or stg'
    D001 em=0.238: rag_variant pred='threadrag w o stm llm extracted triplets' gold='threadrag ablation no sn no stg no edp'
    D001 em=0.258: rag_variant pred='graph free' gold='graph free controlled graph free ablation'
    D001 em=0.274: rag_variant pred='graph free' gold='graph free controlled graph free ablation'
    D001 em=0.286: rag_variant pred='no subgraph' gold='threadrag selection no subgraph'
    D001 em=0.286: rag_variant pred='threadrag w o edp' gold='threadrag ablation sn stg no edp'
    D001 em=0.292: rag_variant pred='threadrag full' gold='threadrag ablation stg edp no sn'
    D001 em=0.294: rag_variant pred='bfs depth 3' gold='threadrag selection bfs depth 3'
    D001 em=0.302: rag_variant pred='dfs depth 3' gold='threadrag selection dfs depth 3'
    D001 em=0.304: rag_variant pred='kg paths' gold='threadrag representation kg paths'
    D001 em=0.308: rag_variant pred='threadrag w o sn fixed length chunks' gold='threadrag ablation edp only no sn or stg'
    D001 em=0.31: rag_variant pred='kg triplets' gold='threadrag representation kg triplets'
    D001 em=0.316: rag_variant pred='kg texts' gold='threadrag representation kg texts'
    D001 em=0.324: generator_model pred='' gold='llama3 8b instruct'
    D001 em=0.324: rag_variant pred='edp' gold='threadrag selection edp'
    D001 em=0.324: rag_variant pred='threadrag full' gold='threadrag ablation sn stg edp'
    D001 em=0.326: rag_variant pred='threadrag w o sn fixed length chunks' gold='threadrag ablation edp only no sn or stg'
  Paired rows: 1142; shown: 20
  Field mismatches: dataset_name=696, rag_variant=471, generator_model=525, metric_k=51

  == without D014
  value        P=0.120 R=0.076 F1=0.093  (tp=579, pred=4831, gold=7632)
  value_loose  P=0.353 R=0.223 F1=0.273  (tp=1703, pred=4831, gold=7632)

  == per publication (strict value F1)
  D001: F1=0.231 P=0.465 R=0.154 pred=127 gold=383
  D002: F1=0.000 P=0.000 R=0.000 pred=216 gold=316
  D003: F1=0.024 P=0.118 R=0.013 pred=76 gold=673
  D004: F1=0.000 P=0.000 R=0.000 pred=225 gold=207
  D005: F1=0.000 P=0.000 R=0.000 pred=262 gold=346
  D006: F1=0.219 P=0.263 R=0.188 pred=403 gold=565
  D007: F1=0.102 P=0.106 R=0.098 pred=700 gold=758
  D008: F1=0.282 P=0.576 R=0.187 pred=125 gold=385
  D009: F1=0.275 P=0.300 R=0.254 pred=609 gold=721
  D010: F1=0.000 P=0.000 R=0.000 pred=62 gold=152
  D011: F1=0.216 P=0.302 R=0.168 pred=192 gold=345
  D012: F1=0.016 P=0.019 R=0.013 pred=525 gold=765
  D013: F1=0.006 P=0.011 R=0.004 pred=188 gold=486
  D014: F1=0.000 P=0.000 R=0.000 pred=91 gold=11760
  D015: F1=0.000 P=0.000 R=0.000 pred=193 gold=222
  D016: F1=0.000 P=0.000 R=0.000 pred=8 gold=72
  D017: F1=0.000 P=0.000 R=0.000 pred=221 gold=232
  D018: F1=0.000 P=0.000 R=0.000 pred=242 gold=317
  D019: F1=0.030 P=0.048 R=0.021 pred=126 gold=280
  D020: F1=0.000 P=0.000 R=0.000 pred=312 gold=343
  D021: F1=0.000 P=0.000 R=0.000 pred=19 gold=64

  == top-5 discrepancies (worst publications; sample missing / extra values)
  D002 (F1=0.000) missing=316 extra=216
     missing: ('morse general cybersecurity questions', 'morse', 'mistralai mistral 7b instruct', 'answer relevance', '', '0.9')
     extra:   ('general cybersecurity questions', 'morse', 'mistralai mistral 7b instruct v0.2', 'answer relevance', '', '0.9')
  D004 (F1=0.000) missing=207 extra=225
     missing: ('e commerce seller forums', 'traditional rag raw kb', 'anthropic claude sonnet', 'entity match rate', '20', '24.8')
     extra:   ('', 'opinion enriched kb o rag', 'anthropic claude sonnet 4.5', 'human preference rate', '', '79.2')
  D005 (F1=0.000) missing=346 extra=262
     missing: ('crag', 'baseline', 'meta llama instruct 70b', 'factuality', '', '34.2')
     extra:   ('crag', 'prismrag', 'llama 3.1 70b instruct', 'factuality', '', '4.5')
  D010 (F1=0.000) missing=152 extra=62
     missing: ('mirage', 'ragroute', 'llama3.1 8b instruct', 'classification accuracy', '', '86.63')
     extra:   ('mirage', 'ragroute', 'llama 3.1 8b instruct', 'communication volume reduction', '', '80.65')
  D014 (F1=0.000) missing=11760 extra=91
     missing: ('wow', 'simulated knowledge retrieval selection no knowledge', 'gpt 4o mini', 'knowledge precision', '', '0')
     extra:   ('wizard of wikipedia', 'no retrieval', 'gpt 4o mini', 'kp', '', '0')
  ```

## MVP-UI-001

- Status (`complete` or `blocked`): `complete`
- Acceptance check: **PASS** (all jury dashboard checks passed cleanly with 0 console errors and 0 failed fetches; 0 API tokens spent)
- Git commit (from `git rev-parse --short HEAD`): `8ee6e10`
- Checker command and result:
  - Command: `.\.venv\Scripts\python.exe tools/check_submission.py out_dev dev --ocr --tesseract "C:\Program Files\Tesseract-OCR\tesseract.exe" --json-report out_dev/validation.json`
  - Exit code: `2` (`Errors: 0; review items: 953`; `source_text_mode: "native plus local OCR on image-only pages"`)
  - Table counts (`out_dev/validation.json`): `publications=21, configurations=487, datasets=105, tasks=51, experiments=135, results=5058, issues=2004`
  - Quotes: `requested=7062, matched=6650 (94.2%), unresolved=412`
- UI URL and server:
  - `http://127.0.0.1:8000/` (`python scripts/serve_ui.py out_dev`, serving updated `app/index.html` "RAG Atlas — Обзор корпуса RAG", all 7 CSVs + `/data/validation.json` returning HTTP 200; 0 console errors).
- Observed four KPI cards (matching `out_dev/validation.json` and CSVs):
  - `Обработанные статьи`: `21` (`из 21 в пакете`)
  - `Извлечённые результаты`: `5 020` (`Числовые значения`)
  - `Проверенные цитаты`: `94,2 %` (`6 650 из 7 062 подтверждены`)
  - `Замечания`: `2 004` (`Записи в issues.csv`)
- Observed search, filters, and tab switching:
  - Main tabs verified: `Извлечённые результаты` (`5 058` total rows), `Публикации` (`21` rows, all `D001`–`D021` `В области` with `>= 8` results each, `0` unprocessed), `Проверка и замечания` (`2 004` rows). Related `configurations`/`datasets`/`tasks`/`experiments` render inside each result's detail dialog.
  - Paper & metric search verified: publication filter `D009` -> `616` rows; `D009` + search `"EM"` -> `606` rows; global search `"EM"` -> `4 843` rows; `С замечаниями` filter -> `1 992` rows.
- Observed verified result row with quote:
  - `D001 / R001`: `EM = 0.204 fraction`, `стр. 6 · Table 1`, badge `Проверен`, quote: `RA-CoT\n.204\n.330\n.202\n.261\n.142\n.210`.
- Observed result row with linked issues:
  - `D001 / R059`: `EM delta`, `Связанные замечания (1)` -> rule `percentage_vs_percentage_point` (`I01`): *"Difference-type metrics are labeled with % in the source; it is not established whether they are relative percent or percentage points. Original unit retained, no conversion."*
- MVP UI checkpoint: **PASS — READY FOR JURY DEMO**.

## MVP-DEV-001

- Status (`complete` or `blocked`): `complete`
- Git commit (from `git rev-parse --short HEAD`): `0f78235` (verification commands ran on `369aa4c`, identical pipeline/exporter/checker code; `0f78235` only updated docs/handoff)
- Python and Tesseract versions:
  - Python: `3.13.1` (`.venv\Scripts\python.exe`)
  - Tesseract: `v5.4.0.20240606` (`C:\Program Files\Tesseract-OCR\tesseract.exe`)
  - Python OCR packages: `pytesseract 0.3.13` (`get_tesseract_version() -> 5.4.0.20240606`), `Pillow 13.0.0`
- Cache-only rebuild exit code and unresolved IDs:
  - Merged `cache.zip` via `scripts/merge_cache.py cache.zip --input dev --output out_dev --no-check`: `{'merged': 17, 'kept': 1, 'ocr': 0, 'bad': 0}`.
  - Initial rebuild exit code: `1`; unresolved IDs before live runs: `D002, D009, D013` (plus `D021` cached with wrong `in_scope=false`).
  - Final cache-only rebuild exit code: **`0`** (`docs=21 stubs=0`, unresolved IDs: **none**).
- Live commands, exit codes, backend, and token totals:
  - Note: Initial Gemini run (`gemini-3.8-flash`) failed on `503 UNAVAILABLE` / `429 RESOURCE_EXHAUSTED` (`0` tokens). Operator switched `.env` to `DeepSeekClient` (`DEEPSEEK_MODEL=deepseek-v4-flash`, `DEEPSEEK_MAX_TOKENS=16384`).
  - Run 1: `main.py --input dev --output out_dev_retry --only D002 D009 D013 --ocr --workers 1` (`DeepSeekClient / deepseek-v4-flash`)
    - `D002`: **OK** (`226` raw rows, `250s`, tokens `in=73,367 out=38,307`)
    - `D009`: **OK** (`633` raw rows, `514s`, tokens `in=103,857 out=101,573`)
    - `D013`: completed `meta`, `1-3`, `4-6` (`87` raw rows), then stalled on `7-8` (`out=24576` truncated JSON without `finish_reason=length`, triggering 5x `JSONDecodeError` retries); manually stopped to avoid wasting tokens (partial cache preserved).
  - Run 2: `main.py --input dev --output out_dev_retry --only D021 --force --ocr --workers 1` -> exit code **`0`** (`26` raw rows, `in_scope=true`, `412s`, tokens `in=57,293 out=32,275`).
  - Run 3 (aborted attempt): `--only D013 --force --ocr --workers 1 --window 1` truncated `meta pass` at `16384` (`finish_reason=length`, `in=24,965 out=16,384`); previous partial `cache/D013.json` preserved.
  - Run 4 (resumed `D013` with `$env:DEEPSEEK_MAX_TOKENS = "8192"`): `main.py --input dev --output out_dev_retry --only D013 --ocr --workers 1` -> exit code **`0`** (`244` total raw rows, `171s`, resumed from page 7, tokens `in=44,641 out=24,759`).
  - Total successful live extraction tokens: `in=279,158`, `out=196,914` (all-inclusive with retries/aborts: `in=~420,295`, `out=~386,781`).
- Per-paper evidence for D002, D009, D013, D021 (mode, raw rows, numeric CSV rows, scope or failure):
  - `D002`: `mode=text (OCR text mode)`, `in_scope=true`, `226` raw rows, **`216` exported numeric CSV rows** (9 non-numeric routed to `issues.csv`), sample: `page=8, Answer Relevance=0.90, quote='MoRSE 0.90 0.05 0.95 0.02 0.7'`.
  - `D009`: `mode=text (native PDF text)`, `in_scope=true`, `633` raw rows, **`612` exported numeric CSV rows** (17 non-numeric routed to `issues.csv`; quote check `ok=626, repaired=7, unverified=0`; **0** unresolved checker quotes; Strict F1=`0.277`), sample: `page=5, EM=14.8, quote='Direct\n14.8\n19.0'`.
  - `D013`: `mode=text (OCR text mode)`, `in_scope=true`, `244` raw rows, **`235` exported numeric CSV rows**, sample: `page=1, Exact Match (EM)=31.8, quote='31.8/49.6/18.7'`.
  - `D021`: `mode=text (OCR text mode)`, `in_scope=true` (corrected from cached `false`), `26` raw rows, **`20` exported numeric CSV rows**, sample: `page=4, Correlation with human judgments=0.81, quote='GPT-4-based evaluation achieves 0.81 correlation with'`.
- Final `out_dev` publication coverage, unprocessed IDs, and row counts for all seven tables:
  - Coverage: `21/21` dev PDFs (`docs=21 stubs=0`, `in_scope=true` for all 21, unprocessed IDs: **none**).
  - Row counts: `publications=21`, `configurations=487`, `datasets=105`, `tasks=51`, `experiments=135`, `results=5058`, `issues=2004`.
- Checker exit code, structural errors, review counts by category, and matched/requested quotes:
  - Command: `.\.venv\Scripts\python.exe tools/check_submission.py out_dev dev --ocr --tesseract "C:\Program Files\Tesseract-OCR\tesseract.exe" --json-report out_dev/validation.json`
  - Exit code: `2` (`source_text_mode: "native plus local OCR on image-only pages"`)
  - Structural errors: **`0`**
  - Review items (`953` total, `0` unprocessed publications):
    - `411`: `quote not found on declared page`
    - `269`: `primary result without dataset_id`
    - `136`: `primary result without task_id`
    - `135`: `primary result without config_id`
    - `1`: `primary result without experiment_id`
    - `1`: `quote not found on declared page; found on pages 6` (`issues:73`)
  - Quotes: `requested=7062`, `matched=6650` (`94.17%`), `unresolved=412`.
  - Unresolved quote breakdown: **`399 / 412 (96.8%)`** come from the 3 scanned PDFs (`D002`: 161, `D013`: 219, `D021`: 19); only **`13 / 412`** come from the 18 native-text PDFs (all 13 in `issues.csv`, **0** in `results.csv`; `D009` has **0** unresolved quotes).
  - Warnings by publication (`total/unres_quotes`): `D001: 9/3`, `D002: 249/161`, `D003: 8/1`, `D004: 7/1`, `D005: 7/0`, `D006: 9/0`, `D008: 11/1`, `D009: 189/0`, `D010: 7/0`, `D011: 30/3`, `D012: 162/0`, `D013: 223/219`, `D015: 15/1`, `D016: 2/2`, `D017: 1/0`, `D018: 1/1`, `D021: 23/19` (`D007, D014, D019, D020`: `0` warnings).
- Evaluator scope agreement, strict and loose TP/F1, and top mismatch fields:
  - Command: `.\.venv\Scripts\python.exe scripts/evaluate.py out_dev dev_gold --show-diffs 20` (exit code `0`)
  - `in_scope` agreement: **`21/21 = 100.0%`** (`unprocessed: 0`, `wrong: -`)
  - `datasets (by name)`: `P=0.533 R=0.232 F1=0.324 (tp=56, pred=105, gold=241)`
  - `models (rag_variant+generator)`: `P=0.435 R=0.045 F1=0.081 (tp=212, pred=487, gold=4733)`
  - `metric values (strict)`: `P=0.105 R=0.027 F1=0.043 (tp=519, pred=4951, gold=19392)`
  - `metric values (loose)`: `P=0.355 R=0.091 F1=0.144 (tp=1756, pred=4951, gold=19392)`
  - `without D014`: strict `P=0.107 R=0.068 F1=0.083 (tp=519, pred=4860, gold=7632)`; loose `P=0.358 R=0.228 F1=0.278 (tp=1738, pred=4860, gold=7632)`
  - Loose-to-strict mismatches: `Paired rows: 1237; Field mismatches: dataset_name=783, rag_variant=456, generator_model=514, metric_k=81`
- UI URL and observed paper/dataset/metric/issue filters, source page/quote, and row counts:
  - Live at `http://127.0.0.1:8000/` (`python scripts/serve_ui.py out_dev`, `Cache-Control: no-store`, open in operator browser).
  - Row counts match `out_dev/validation.json` (`publications=21, configurations=487, datasets=105, tasks=51, experiments=135, results=5058, issues=2004`); `publications` unprocessed filter is empty (`0`).
- MVP checkpoint for 1.1 and 1.2 (pass/pending and exact blockers):
  - **1.1 Pipeline stability and clean dev run**: **PARTIAL PASS** — all `21/21` dev PDFs resolved (`in_scope=21/21`, `stubs=0`, `rebuild-csv-only` exit `0`, `0` structural errors), but `check_submission.py --ocr` exits `2` due to `953` non-structural review items (`412` unresolved quotes + `541` missing primary-result IDs).
  - **1.2 Interactive explorer and dataset passport**: **PASS on live UI** (needs `DATASET_PASSPORT.md` refresh with final 21/21 counts).
  - **Demo readiness**: **READY FOR JURY DEMO NOW**; fix the two systemic issues below before Phase 2 / `test/` run.
- Redacted failure or review excerpts:
  - **Systemic OCR mismatch (`399/412` unresolved quotes)**: `core/ocr.py` renders pages at `dpi=200, colorspace=pymupdf.csGRAY` (default PSM), while `tools/check_submission.py --ocr` renders at `dpi=300, colorspace=pymupdf.csRGB, --psm 3`, and `main.py` skips `_repair_quote` when `cache.get("ocr") == True`. Aligning `core/ocr.py` to `dpi=300, csRGB, --psm 3` + running `_repair_quote` on OCR text will eliminate almost all scanned-PDF quote warnings.
  - **Systemic `DeepSeekClient` truncation loop**: `[D013:7-8] tokens in=12911 out=24576 -> retry 1/6: JSONDecodeError: Unterminated string... -> retry 2..5/6: JSONDecodeError: Expecting value: line 1 column 1`. Raise `TruncatedResponseError` in `DeepSeekClient.generate_json` when JSON parsing fails and `completion_tokens >= self.max_out`, so `pipeline.py` splits the window immediately instead of burning 6 retries.
  - **Exact `scripts/evaluate.py out_dev dev_gold --show-diffs 20` output**:
    ```text
    Scored publications: 21 (D001, D002, D003, D004, D005, D006, D007, D008, D009, D010, D011, D012, D013, D014, D015, D016, D017, D018, D019, D020, D021)
    MISSING from result (recall=0): 0 -

    == publications.csv: scope decision
    in_scope agreement: 21/21 = 100.0%
    unprocessed (scope unresolved): 0 -
    included: pred 21 vs gold 21; wrong: -

    == row counts (result vs gold, scored pubs only)
    publications         21 vs      21  (+0)
    configurations      487 vs    4733  (-4246)
    datasets            105 vs     241  (-136)
    tasks                51 vs      90  (-39)
    experiments         135 vs     142  (-7)
    results            5058 vs   37616  (-32558)
    issues             2004 vs     134  (+1870)

    == Precision / Recall / F1
    datasets (by name)                                         P=0.533 R=0.232 F1=0.324  (tp=56, pred=105, gold=241)
    models (rag_variant+generator)                             P=0.435 R=0.045 F1=0.081  (tp=212, pred=487, gold=4733)
    metric values (strict: dataset+model+metric+k+value)       P=0.105 R=0.027 F1=0.043  (tp=519, pred=4951, gold=19392)
    metric values (loose: metric name+value)                   P=0.355 R=0.091 F1=0.144  (tp=1756, pred=4951, gold=19392)

    == loose matches that fail strict matching
      D001 em=0.172: rag_variant pred='threadrag w o stm llm extracted triplets' gold='threadrag ablation no sn no stg no edp'
      D001 em=0.206: rag_variant pred='graph free' gold='graph free controlled graph free ablation'
      D001 em=0.224: rag_variant pred='threadrag w o stm llm extracted triplets' gold='threadrag ablation no sn no stg no edp'
      D001 em=0.232: rag_variant pred='threadrag w o sn fixed length chunks' gold='threadrag ablation edp only no sn or stg'
      D001 em=0.238: rag_variant pred='threadrag w o stm llm extracted triplets' gold='threadrag ablation no sn no stg no edp'
      D001 em=0.258: rag_variant pred='graph free' gold='graph free controlled graph free ablation'
      D001 em=0.274: rag_variant pred='graph free' gold='graph free controlled graph free ablation'
      D001 em=0.286: rag_variant pred='no subgraph' gold='threadrag selection no subgraph'
      D001 em=0.286: rag_variant pred='threadrag w o edp' gold='threadrag ablation sn stg no edp'
      D001 em=0.292: rag_variant pred='threadrag full' gold='threadrag ablation stg edp no sn'
      D001 em=0.294: rag_variant pred='bfs depth 3' gold='threadrag selection bfs depth 3'
      D001 em=0.302: rag_variant pred='dfs depth 3' gold='threadrag selection dfs depth 3'
      D001 em=0.304: rag_variant pred='kg paths' gold='threadrag representation kg paths'
      D001 em=0.308: rag_variant pred='threadrag w o sn fixed length chunks' gold='threadrag ablation edp only no sn or stg'
      D001 em=0.31: rag_variant pred='kg triplets' gold='threadrag representation kg triplets'
      D001 em=0.316: rag_variant pred='kg texts' gold='threadrag representation kg texts'
      D001 em=0.324: generator_model pred='' gold='llama3 8b instruct'
      D001 em=0.324: rag_variant pred='edp' gold='threadrag selection edp'
      D001 em=0.324: rag_variant pred='threadrag full' gold='threadrag ablation sn stg edp'
      D001 em=0.326: rag_variant pred='threadrag w o sn fixed length chunks' gold='threadrag ablation edp only no sn or stg'
    Paired rows: 1237; shown: 20
    Field mismatches: dataset_name=783, rag_variant=456, generator_model=514, metric_k=81

    == without D014
    value        P=0.107 R=0.068 F1=0.083  (tp=519, pred=4860, gold=7632)
    value_loose  P=0.358 R=0.228 F1=0.278  (tp=1738, pred=4860, gold=7632)

    == per publication (strict value F1)
    D001: F1=0.231 P=0.465 R=0.154 pred=127 gold=383
    D002: F1=0.000 P=0.000 R=0.000 pred=216 gold=316
    D003: F1=0.024 P=0.118 R=0.013 pred=76 gold=673
    D004: F1=0.000 P=0.000 R=0.000 pred=225 gold=207
    D005: F1=0.000 P=0.000 R=0.000 pred=262 gold=346
    D006: F1=0.219 P=0.264 R=0.188 pred=402 gold=565
    D007: F1=0.074 P=0.077 R=0.071 pred=700 gold=758
    D008: F1=0.024 P=0.048 R=0.016 pred=125 gold=385
    D009: F1=0.277 P=0.306 R=0.254 pred=598 gold=721
    D010: F1=0.000 P=0.000 R=0.000 pred=62 gold=152
    D011: F1=0.218 P=0.309 R=0.168 pred=188 gold=345
    D012: F1=0.016 P=0.019 R=0.013 pred=525 gold=765
    D013: F1=0.078 P=0.121 R=0.058 pred=231 gold=486
    D014: F1=0.000 P=0.000 R=0.000 pred=91 gold=11760
    D015: F1=0.000 P=0.000 R=0.000 pred=193 gold=222
    D016: F1=0.000 P=0.000 R=0.000 pred=8 gold=72
    D017: F1=0.000 P=0.000 R=0.000 pred=221 gold=232
    D018: F1=0.000 P=0.000 R=0.000 pred=242 gold=317
    D019: F1=0.030 P=0.048 R=0.021 pred=126 gold=280
    D020: F1=0.000 P=0.000 R=0.000 pred=313 gold=343
    D021: F1=0.000 P=0.000 R=0.000 pred=20 gold=64

    == top-5 discrepancies (worst publications; sample missing / extra values)
    D002 (F1=0.000) missing=316 extra=216
       missing: ('morse general cybersecurity questions', 'morse', 'mistralai mistral 7b instruct', 'answer relevance', '', '0.9')
       extra:   ('general cybersecurity questions', 'morse', 'mistralai mistral 7b instruct v0.2', 'answer relevance', '', '0.9')
    D004 (F1=0.000) missing=207 extra=225
       missing: ('e commerce seller forums', 'traditional rag raw kb', 'anthropic claude sonnet', 'entity match rate', '20', '24.8')
       extra:   ('', 'opinion enriched kb o rag', 'anthropic claude sonnet 4.5', 'human preference rate', '', '79.2')
    D005 (F1=0.000) missing=346 extra=262
       missing: ('crag', 'baseline', 'meta llama instruct 70b', 'factuality', '', '34.2')
       extra:   ('crag', 'prismrag', 'llama 3.1 70b instruct', 'factuality', '', '4.5')
    D010 (F1=0.000) missing=152 extra=62
       missing: ('mirage', 'ragroute', 'llama3.1 8b instruct', 'classification accuracy', '', '86.63')
       extra:   ('mirage', 'ragroute', 'llama 3.1 8b instruct', 'communication volume reduction', '', '80.65')
    D014 (F1=0.000) missing=11760 extra=91
       missing: ('wow', 'simulated knowledge retrieval selection no knowledge', 'gpt 4o mini', 'knowledge precision', '', '0')
       extra:   ('wizard of wikipedia', 'no retrieval', 'gpt 4o mini', 'kp', '', '0')
    ```
  - **Next-step recommendations for Codex**:
    1. Align `core/ocr.py` (`dpi=300, csRGB, --psm 3`) with `tools/check_submission.py --ocr` and enable `_repair_quote` on OCR text to clear ~399 scanned-PDF quote warnings before `test/`.
    2. Guard `DeepSeekClient.generate_json` against `JSONDecodeError` when `completion_tokens >= max_out` (raise `TruncatedResponseError`).
    3. Refresh `DATASET_PASSPORT.md` with the final 21/21 numbers and proceed to Phase 2.1/2.2 (`_fill_ids` inheritance will also clear `540` missing `dataset_id`/`config_id`/`task_id` warnings on a 0-token rebuild).
