# RAG: пайплайн извлечения данных из научных PDF (кейс ВИНИТИ РАН + ЮФУ)

PDF → Gemini (structured JSON) → `cache/<id>.json` → 7 CSV (`publications, configurations, datasets, tasks, experiments, results, issues`) → проверка (`tools/check_submission.py`) и оценка по `dev_gold/` (`scripts/evaluate.py`).

## Установка (Windows PowerShell или Linux)
```powershell
git pull
python -m venv venv
.\venv\Scripts\Activate.ps1        # Linux: source venv/bin/activate
python -m pip install -r requirements.txt -r tools/requirements.txt
Copy-Item .env.example .env        # Linux: cp .env.example .env ; затем впишите GEMINI_API_KEY
```

## Переменные окружения (`.env`)
| Переменная | По умолчанию | Назначение |
|---|---|---|
| `GEMINI_API_KEY` | — (обязательна) | ключ Google AI Studio (`GOOGLE_API_KEY` тоже подходит) |
| `DEEPSEEK_API_KEY` | — | если нет ключа Gemini: DeepSeek (`deepseek-flash`, `https://api.deepseek.com/chat/completions`, только текст, thinking отключён; токены логируются, 429 с учётом Retry-After; `DEEPSEEK_MODEL`, `DEEPSEEK_MAX_TOKENS`) |
| `GEMINI_MODEL` | `gemini-3.8-flash` | модель |
| `GEMINI_MAX_RETRIES` | 6 | повторы при 429/500/502/503/504, таймаутах, обрыве связи, битом JSON |
| `GEMINI_BACKOFF_BASE` / `GEMINI_BACKOFF_MAX` | 2 / 60 | экспоненциальная пауза (сек) с jitter ×0.5–1.5 |
| `GEMINI_TIMEOUT_S` | 300 | таймаут одного запроса |
| `GEMINI_MAX_OUTPUT_TOKENS` | 65536 | лимит ответа |
| `GEMINI_TEMPERATURE` | 0 | температура |

## Запуск
```powershell
# смоук-тест: D001 (текстовый PDF) и D002 (скан)
python main.py --input dev --output out_dev --only D001 D002
python tools/check_submission.py out_dev dev
python scripts/evaluate.py out_dev dev_gold --only D001 D002

# весь dev (уже готовые документы берутся из cache/, упавшие докачиваются)
python main.py --input dev --output out_dev
python tools/check_submission.py out_dev dev --json-report report_dev.json
python scripts/evaluate.py out_dev dev_gold

# пересборка CSV без API (после правки exporter.py)
python main.py --input dev --output out_dev --rebuild-csv-only
```
Для сканов (D002, D013, D021) цитаты проверяются только с OCR: `check_submission.py ... --ocr` (нужен Tesseract); иначе — код 2 («не найдено/проверьте по изображению»), это не ошибка.

Коды `main.py`: `0` — все документы OK; `1` — есть FAIL (в CSV попадают только полностью обработанные документы; пустые/битые CSV не пишутся, если нет ни одного документа). Лог по документу: `D001: OK - ...` / `D001: FAIL - причина`. Ошибки API никогда не кэшируются; прогресс (мета + окна страниц) сохраняется, повторный запуск докачивает только недостающее. `--force` — игнорировать кэш.

Опции: `--window N` (страниц на запрос результатов, по умолчанию 3), `--pdf-mode auto|text|pdf` (auto: сканы шлются в Gemini как PDF и удаляются из облака после ответа).

## Как это устроено
- `core/pdf_processor.py` — текстовый слой через PyMuPDF, определение скана.
- `core/llm_client.py` — Gemini, retry/backoff, кэш.
- `plugins/rag/{schemas,prompts,pipeline,exporter}.py` — схемы, промпты, проход «мета + окна страниц», сборка CSV, нормализация и проверки.
- Нормализация: `.204`→`0.204` (`fraction` для ограниченных метрик), `%` сохраняется как `%`, секунды→мс, диапазоны не усредняются, `@k`→`metric_k`; цитаты сверяются с текстом страницы (исправление страницы/дословной цитаты при расхождении).
- Правила проверки (issues.csv): `metric_scale`, `metric_k`, `percentage_vs_percentage_point`, `contradiction`; повторы → `duplicate_of`.
- Просмотр результата: откройте `app/index.html` в браузере и выберите папку с CSV (`out_dev`).

## Дополнительно
- Без API: `--local --skip-scans` (эвристика), сканы — через `--ocr-json DIR` (готовые `<id>.json` с ПК, формат в `DATASET_PASSPORT.md`).
- Слияние кэшей/OCR-JSON тиммейта (папка или .zip): `python scripts/merge_cache.py incoming.zip --input dev --output out_dev` — пересобирает CSV и запускает `check_submission.py`.
- UI: `python scripts/serve_ui.py out_dev` → http://127.0.0.1:8000/ (поиск, фильтры in_scope/датасет/модель/метрика, источник: страница/таблица/цитата, вкладка issues). Паспорт: `DATASET_PASSPORT.md`.
