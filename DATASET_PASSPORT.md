# Паспорт датасета — RAG (кейс ВИНИТИ РАН + ЮФУ)

Формат: UTF-8, запятая, десятичная точка, 7 CSV (колонки и порядок — `submission_template/schema.json`). Пустая ячейка = в статье нет сведений (не 0). Ноль пишется `0`. Везде есть `publication_id` (имя PDF без расширения); остальные ключи уникальны внутри публикации. Номер страницы — страница PDF с 1.

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
| metric_scale | любая метрика (кроме разностей) вне [0,1] при `fraction` / вне [0,100] при `%`; либо значение >1 без указанной единицы (шкала не заявлена) |
| metric_k | в названии `@k`, но целое k не определено |
| percentage_vs_percentage_point | метрики-разности (Δ, improvement, gain…) в `%`: относительные проценты или п.п. — не установлено |
| metric_k_gt_top_k | `metric_k` больше `top_k` конфигурации (проверить, к какой стадии — поиск или reranker — относится k) |
| contradiction | расхождение значений одного ключа или противоречия в параметрах внутри статьи |

Дополнительно экспортёр: неизвестные ссылки на id обнуляются (с пометкой в `note`); строки без допустимой страницы PDF или без локатора источника исключаются с записью в лог; исключённая статья (`in_scope=false`) имеет строку только в publications.csv. Структурная проверка — `tools/check_submission.py` (код 1 — ошибка, 2 — требуется проверка источников); полнота и научная точность отдельно оцениваются `scripts/evaluate.py` по `dev_gold/`.

## Источники данных и режимы (поле `mode` в `cache/<id>.json`)
| mode | Источник | Приоритет при слиянии |
|---|---|---|
| `text` / `pdf` | LLM (Gemini или DeepSeek), текстовый слой / PDF целиком | 3 |
| `ocr_json` | OCR-JSON с ПК тиммейта для сканов + правила (без OCR на сервере) | 2 |
| `local` | только PyMuPDF + регулярные выражения (эвристика, не для сдачи) | 1 |

Формат OCR-JSON: `{"publication_id":"D002","pages":[{"source_page":1,"is_scanned":true,"raw_text":"","normalized_text":"","primary_section":"","tables":[{"caption":"Table 1: ...","rows":[["Method","EM"],["X",".31"]]}]}]}`. Цитаты из OCR на сервере не проверяются по PDF (код 2 у `check_submission.py`, либо `--ocr`).

## Воспроизведение
```powershell
python -m pip install -r requirements.txt -r tools/requirements.txt
python main.py --input dev --output out_dev                         # LLM (ключ в .env)
python main.py --input dev --output out_dev --local --skip-scans    # без API, эвристика
python main.py --input dev --output out_dev --ocr-json ocr_dev      # + OCR-JSON для сканов
python scripts/merge_cache.py incoming.zip --input dev --output out_dev   # слияние чужих кэшей + пересборка + проверка
python tools/check_submission.py out_dev dev --json-report report.json
python scripts/evaluate.py out_dev dev_gold
python scripts/serve_ui.py out_dev                                  # UI: http://127.0.0.1:8000/
```
