# TODO: Пайплайн извлечения данных RAG (Кейс ВИНИТИ РАН + ЮФУ)

## ЖЁСТКИЕ ПРАВИЛА ДЛЯ CLAUDE:
1. **Разделение ролей (Сервер -> GitHub -> ПК тиммейта):**
   - Этот сервер (1 ГБ RAM, 10 ГБ диска) используется **ТОЛЬКО** для чтения текстовых спецификаций (`README_участникам.md`, `submission_template/`, `dev_gold/`, `tools/check_submission.py`), написания кода и пуша в GitHub.
   - **НЕ ЗАПУСКАЙ** на этом сервере пакетную обработку PDF, `pip install` тяжёлых библиотек (`pandas`, `streamlit`, `tesseract`, `torch`) и локальный OCR. Все запуски прогонов PDF и проверок будут выполняться на ПК тиммейта через `git pull`.
   - Пиши весь код строго кроссплатформенно (используй `pathlib`, UTF-8 без привязки к Linux-путям), чтобы он без правки запускался и на Windows, и на Linux, с минимальным набором лёгких пакетов (`google-genai`, `pydantic`, `pymupdf`, `python-dotenv`, `rapidfuzz`).
2. **Обязательный чекпоинт после КАЖДОГО шага:**
   - Отмечай выполненные подзадачи `[ ]` прямо в этом файле `TODO.md`.
   - Выполняй `git add . && git commit -m "<осмысленное сообщение>" && git push` (если `remote` не настроен — проверь `git remote -v` и сообщи пользователю).
3. **Правила кейса ВИНИТИ РАН:**
   - Никогда не выдумывай отсутствующие в статье значения (`""` / `null`).
   - Всегда кэшируй сырой JSON-ответ LLM в `cache/<doc_id>.json`, чтобы пересобирать CSV (`--rebuild-csv-only`) без повторных запросов к API и траты токенов.

---

## Выполнено (Шаги 1–3 и доп. работы)
- [x] **Шаг 1.** Схема, эталон и валидатор изучены; `.gitignore`, `.env.example`, лёгкий `requirements.txt`.
- [x] **Шаг 2.** Архитектура `core/` + `plugins/rag/`: `pdf_processor`, `llm_client` (Gemini + `DeepSeekClient`), `schemas`, `prompts`, `pipeline`, `exporter`, CLI `main.py` (`--only`, `--force`, `--rebuild-csv-only`, `--window`, `--pdf-mode`, `--skip-scans`, `--local`, `--ocr-json`).
- [x] **Шаг 3.** `scripts/evaluate.py` (P/R/F1, пропущенные публикации = recall 0, отдельный F1 без `D014`) и инструкция для ПК в `README.md`.
- [x] **Входы без API:** `--local` (PyMuPDF + regex), OCR-JSON адаптер `plugins/rag/ocr_adapter.py` (id из имени файла, перезапись `ocr_json`), `scripts/merge_cache.py` (проверка `version==2`, `n_pages`, `meta.publication`).
- [x] **Надёжность LLM-клиентов:** прокси `DEEPSEEK_BASE_URL` (TokenWave), ретраи SSL/EOF/`URLError`/`HTTPException`/`OSError`, снятие ```json-обёртки, `preflight()`, `DEEPSEEK_FREQUENCY_PENALTY` (по умолчанию 0).
- [x] **Устойчивость к обрезке вывода:** `TruncatedResponseError` → деление окна страниц пополам → деление одной страницы по строкам (перекрытие 4 строки, рекурсивно, дедупликация); компактный JSON в промпте.
- [x] **Валидация и экспорт:** Pydantic-валидация ответов до `save_cache`, приведение `"3"`→3 и `"false"`→false, заглушки в `publications.csv` для `SKIPPED_SCAN`/`FAIL`, потоковая запись CSV (`TableWriter`), безопасные `uniq_ids`.
- [x] **UI и документация:** `app/index.html` + `scripts/serve_ui.py`, `DATASET_PASSPORT.md`.
- Проверено только синтетическими тестами и на заглушках; реальных прогонов на `dev/` в репозитории пока нет.

---

## Шаг 4. Оставшиеся задачи (по одной за сессию, между задачами `/clear`)
- [ ] **4.1. Параллельное выполнение (`--workers N`).** Добавить потокобезопасный `--workers` (по умолчанию 4) через `ThreadPoolExecutor` в `main.py` / `plugins/rag/pipeline.py`: параллелить окна страниц и/или документы; блокировки на чтение/запись кэша, счётчики токенов `DeepSeekClient`/`GeminiClient` и общий лог прогресса; сохранить порядок строк в CSV (детерминированный). Проверка: фейковый клиент, `--workers 1` и `--workers 4` дают одинаковые CSV.
- [ ] **4.2. Исправление проблем `check_submission` и `dev_gold`.** Разобрать причины провалов `tools/check_submission.py` и `scripts/evaluate.py` по логам реального прогона `dev/` (`unverified` цитаты, расхождения шкал, пропавшие ссылки, потеря шапки таблицы при делении страницы по строкам) и доработать `plugins/rag/prompts.py` и `plugins/rag/exporter.py` для максимального F1 и кода выхода 0.
- [ ] **4.3. Финальная готовность и синхронизация UI/документов.** Сверить `app/index.html` и `DATASET_PASSPORT.md` с последними изменениями схемы и экспортёра; убедиться, что одна команда (`python main.py --input dev --output out_dev`, затем `--input test` только с явного разрешения пользователя) выдаёт чистые валидированные CSV.
- [ ] **Чекпоинт 4:** отметить выполненные пункты в `TODO.md`, `git add . && git commit && git push` в `main`.
