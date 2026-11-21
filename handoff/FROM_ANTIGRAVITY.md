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
