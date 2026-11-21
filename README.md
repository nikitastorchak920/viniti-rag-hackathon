# RAG · извлечение данных из научных PDF

Пайплайн извлекает измеренные результаты через Gemini или DeepSeek, хранит ответы в `cache/<id>.json` версии 2 и экспортирует семь связанных CSV. Текущий приоритет — демонстрационный MVP на 21 статье `dev/`. Оптимизация строгого F1 и прогон 111 статей `test/` идут после приёмки MVP. План и критерии демонстрации — в [TODO.md](TODO.md).

## Работа на двух ноутбуках

- Codex меняет код, проводит ревью, запускает pytest и проверяет изменения пересборкой из кэша без API.
- Antigravity обновляется из `origin/main`, запускает целевые извлечения и проверки с PDF, ключами и Tesseract. Инструкции и шаблон отчёта лежат в [handoff/](handoff/).
- Оператор передаёт задания между ноутбуками, принимает демонстрации и подтверждает переход к следующей фазе.

## Установка

```powershell
git pull --ff-only origin main
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r tools/requirements.txt pytest
Copy-Item .env.example .env
```

На Linux активируйте окружение через `source venv/bin/activate`. Для `--ocr` установите Tesseract с английскими языковыми данными и выполните `python -m pip install pytesseract`. Для API настройте в локальном `.env` ключ `GEMINI_API_KEY` (также подходит `GOOGLE_API_KEY`) или `DEEPSEEK_API_KEY`. Модели, таймауты и число повторов настраиваются через `.env.example`. Ключи, PDF, кэш и результаты остаются вне Git.

## Проверка и демонстрация

```powershell
python -m pytest tests/test_core.py
python main.py --input dev --output out_dev --rebuild-csv-only
python tools/check_submission.py out_dev dev --ocr --json-report out_dev/validation.json
python scripts/evaluate.py out_dev dev_gold --show-diffs 20
python scripts/serve_ui.py out_dev
```

Откройте [http://127.0.0.1:8000/](http://127.0.0.1:8000/). В `results` можно совместить фильтры по публикации, датасету и метрике и открыть строку с номером страницы и цитатой. В `issues` доступен фильтр по правилу. В `publications` статус «не обработано» показывает статьи, для которых решение по области исследования отсутствует. Можно также открыть `app/index.html` напрямую и выбрать папку с семью CSV.

Сначала используйте пересборку из существующего `cache/`: она не обращается к API. При необходимости повторите обработку только проблемных документов. Например, для одной статьи:

```powershell
python main.py --input dev --output out_dev_retry --only D021 --ocr --workers 1
```

`--force` используйте для выбранных ID только при замене завершённого кэша. Gemini в режиме `auto` читает PDF, если OCR недоступен или его текст недостаточен. DeepSeek принимает текст и сообщает `SKIPPED_SCAN`, если его недостаточно. После выборочного запуска пересоберите полный `out_dev/`.

`main.py` возвращает 1 при неполной обработке. Когда есть успешно обработанные документы, частичный пакет содержит явные заглушки для остальных. `check_submission.py` возвращает 0 при чистой проверке, 1 при структурных ошибках, 2 при открытых замечаниях. Описание таблиц, нормализации и статистика — в [DATASET_PASSPORT.md](DATASET_PASSPORT.md).

## Дополнительные режимы

- `--local --skip-scans`: локальные эвристики без API.
- `--ocr-json DIR`: импорт локальных OCR-JSON.
- `scripts/merge_cache.py`: объединение локально переданных кэшей и пересборка экспорта.
