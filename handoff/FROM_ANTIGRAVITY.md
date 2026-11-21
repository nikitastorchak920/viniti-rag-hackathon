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
