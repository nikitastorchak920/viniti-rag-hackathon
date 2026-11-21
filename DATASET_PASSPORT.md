# Паспорт датасета — RAG (кейс ВИНИТИ РАН + ЮФУ)

Формат: UTF-8, запятая, десятичная точка, 7 CSV (колонки и порядок — `submission_template/schema.json`). Пустая ячейка = в статье нет сведений (не 0). Ноль пишется `0`. Везде есть `publication_id` (имя PDF без расширения); остальные ключи уникальны внутри публикации. Номер страницы — страница PDF с 1.

## Принятый снимок MVP на dev

На ноутбуке Antigravity пакет `out_dev/` пересобран из кэша версии 2 без API для всех 21 PDF. Заглушек нет. D002, D009, D013 и D021 дали соответственно 216, 612, 235 и 20 числовых строк. Источник статистики — [отчёт MVP-DEV-001](handoff/FROM_ANTIGRAVITY.md#mvp-dev-001).

| Таблица | Строки |
|---|---:|
| `publications` | 21 |
| `configurations` | 487 |
| `datasets` | 105 |
| `tasks` | 51 |
| `experiments` | 135 |
| `results` | 5 058 |
| `issues` | 2 004 |

Пакет и дашборд приняты для демонстрации. [Проверка интерфейса MVP-UI-001](handoff/FROM_ANTIGRAVITY.md#mvp-ui-001) подтвердила загрузку всех таблиц, поиск, фильтры и карточку источника. Интерфейс показал 5 020 числовых результатов из 5 058 строк таблицы и 94,2% проверенных цитат.

Валидатор запущен с PDF и OCR. Структурных ошибок 0, из 7 062 цитат найдено 6 650. Код проверки — 2: остаются 412 неподтверждённых цитат и 541 пропущенная ссылка у результата. Из 412 неподтверждённых цитат 399 относятся к трём отсканированным статьям. Базовая оценка по `dev_gold/`: strict F1 0,043 (519 совпадений), loose F1 0,144 (1 756 совпадений). Эти цифры относятся к принятому снимку, до изменений Фазы 2.

## Таблицы
| Таблица | Ключ | Содержание |
|---|---|---|
| publications | publication_id | title, year (int), DOI, authors (`;`), in_scope (`true/false`), exclusion_reason (обязательна при `false`, пуста при `true`) |
| configurations | config_id (`C01…`) | вариант RAG/baseline/ablation: rag_variant, retrieval_method, retriever/embedding/reranker/generator модели и версии, chunking (chunk_size, chunk_overlap — int, chunk_unit), index_type, vector_store, top_k (int ≥ 0), prompt/context_strategy, note |
| datasets | dataset_id (`DS1…`) | dataset_name, версия, language, data_split, scientific_domain |
| tasks | task_id (`T1…`) | task_type (свободный текст) |
| experiments | experiment_id (`E1…`) | evaluation_protocol, baseline_name (`;`), hardware, latency_ms (число, мс), tokens_per_query, sample_size (int) |
| results | result_id (`R001…`) | одно значение одной метрики; ссылки experiment_id/config_id/dataset_id/task_id; metric_*, raw_*/normalized_*, result_origin, source_*, extraction_status, duplicate_of |
| issues | issue_id (`I01…`) | check_name, description, record_ids (`;` result_id), source_page, source_fragment |

## results: поля и единицы
- `raw_value`/`raw_unit` — как напечатано (`.204`, `62.4%`, `≈62.4`); `metric_value` = `normalized_value` (число, точка), `metric_unit` = `normalized_unit`.
- `metric_unit`: `fraction` — безразмерная метрика в [0,1] (`.204`→`0.204`); `%` — значение напечатано в процентах и **не** пересчитывается в доли; `ms` — секунды пересчитываются ×1000 (исходное в raw); прочие единицы — как в источнике; пусто — шкала не указана.
- `metric_k` — целое k из `Метрика@k` (дробные пороги вида `@0.8` — не k); `top_k` конфигурации — отдельное поле.
- `metric_direction`: `higher_is_better | lower_is_better | target | ""`.
- `result_origin`: `primary` (получено авторами, включая перезапуск чужих методов) | `cited` (+ `cited_publication_id` — ссылка как в статье).
- `extraction_status`: `extracted | present_not_extractable | absent`.
- Диапазоны (`256-512`), `±` и нечисловые значения: число пусто/берётся ведущее, исходный текст в `raw_value`/`note`; среднее не подставляется.
- Происхождение: `source_page`, `source_section`, `source_table`, `source_figure`, `source_fragment` (дословная цитата страницы; для текстовых PDF сверяется с текстом страницы, страница/цитата исправляются при расхождении; для сканов проверка — OCR/визуально).

## Нормализация
1. `.204`→`0.204`, `−`→`-`, `1,234`→`1234`, `%` вырезается из числа и сохраняется как единица.
2. Доли/проценты, BLEU/ROUGE не пересчитываются; `fraction` ставится только для ограниченных метрик (accuracy, EM, F1, precision, recall, Hit, MRR, nDCG, MAP и т. п.) при значении в [0,1] без единицы.
3. Повторное упоминание того же значения (тот же эксперимент/конфигурация/набор/метрика/k/единица/агрегация, другое место) → `duplicate_of` на первую запись; одинаковый ключ с разными числами → обе записи + issue `contradiction`.

## Правила валидации (issues.csv; строки не удаляются)
| check_name | Условие |
|---|---|
| metric_scale | ограниченная метрика (кроме разностей) вне [0,1] при `fraction` или вне [0,100] при `%`; также ограниченная метрика со значением >1 без указанной единицы |
| metric_k | в названии `@k`, но целое k не определено |
| percentage_vs_percentage_point | метрики-разности (Δ, improvement, gain…) в `%`: относительные проценты или п.п. — не установлено |
| metric_k_gt_top_k | `metric_k` больше `top_k` конфигурации (проверить, к какой стадии — поиск или reranker — относится k) |
| contradiction | расхождение значений одного ключа или противоречия в параметрах внутри статьи |
| non_numeric_result | исходное значение не удалось представить числом; оно сохранено в замечании вместо строки результата |

Экспортёр очищает неизвестные ссылки на ID и отмечает это в `note`. Строки без допустимой страницы PDF или без локатора источника исключаются с записью в лог. Исключённая статья имеет только строку в `publications.csv`. Для необработанной статьи булево поле сериализуется как `false` с зарезервированной причиной `Unprocessed: no scope decision`. Интерфейс и оценщик показывают её как отсутствие решения по области исследования. Проверяющий скрипт считает её открытым замечанием.

`tools/check_submission.py` проверяет заголовки, типы, ключи и ссылки, согласованность полей и источники. Код 0 означает чистую проверку, 1 — структурные ошибки, 2 — открытые замечания. `scripts/evaluate.py` отдельно сравнивает извлечение с `dev_gold/`.

## Источники данных и режимы (поле `mode` в `cache/<id>.json`)
| mode | Источник | Приоритет при слиянии |
|---|---|---|
| `text` / `pdf` | Текстовый слой или Tesseract для Gemini и DeepSeek, исходный PDF для Gemini | 3 |
| `ocr_json` | Импорт готового OCR-JSON со второго ноутбука | 2 |
| `local` | только PyMuPDF + регулярные выражения (эвристика, не для сдачи) | 1 |

Формат OCR-JSON: `{"publication_id":"P001","pages":[{"source_page":1,"is_scanned":true,"raw_text":"","normalized_text":"","primary_section":"","tables":[{"caption":"Table 1: ...","rows":[["Method","EM"],["X",".31"]]}]}]}`. Извлечение и валидатор используют общий режим Tesseract для страниц со слабым текстовым слоем: 300 dpi, RGB, PSM 3. При пересборке `--ocr` позволяет заново сверить цитаты из OCR-кэша с той же страницей. При сокращении цитаты сохраняется точное напечатанное число, а неподтверждённая цитата остаётся видимой. Для независимой проверки запустите `check_submission.py --ocr`.

## Воспроизведение
```powershell
python -m pip install -r requirements.txt -r tools/requirements.txt
python main.py --input dev --output out_dev --rebuild-csv-only --ocr
python tools/check_submission.py out_dev dev --ocr --json-report out_dev/validation.json
python scripts/evaluate.py out_dev dev_gold --show-diffs 20
python scripts/serve_ui.py out_dev
```
