# Repository workflow

## Priority and ownership

1. Deliver and sign off on a jury-ready MVP before optimizing strict F1.
2. **OpenAI Codex, Thunderobot 911 laptop** owns code in `core/`, `plugins/`, `scripts/`, `tools/`, `tests/`, `app/` and the pipeline entry point, plus architecture reviews, pytest, the roadmap, and Git checkpoints. It can inspect PDFs and run local tools, OCR, and cache rebuilds where inputs are available.
3. **Antigravity, second laptop** has the 21 PDFs in `dev/`, 111 PDFs in `test/`, local API credentials, and Tesseract. It pulls `origin/main`, runs the newest unanswered task, and pushes its report directly to `origin/main`. Its only handoff edit is the English evidence in `handoff/FROM_ANTIGRAVITY.md`.
4. **Human operator** reviews the Russian status report and demo checkpoint and signs off on the MVP before Phase 2. The agents exchange all task details and evidence through Git.

## Language, demos, and checkpoints

- Communicate with the operator in Russian. Write code and comments, commit messages, `TODO.md`, `handoff/` files, and inter-agent instructions in English. Preserve source quotations in their original language.
- After each task, update `TODO.md` with the observed checkpoint, run the relevant checks, and commit and push the intended changes to `origin/main`. Stage explicit paths if unrelated files are present.
- End every operator response with `[ОТЧЁТ ДЛЯ ПОЛЬЗОВАТЕЛЯ / ЧТО МОЖНО ПОСМОТРЕТЬ СЕЙЧАС]` (Russian, up to 10 lines, with the change, a command or URL, serious blockers, and whether the gate passed). If an Antigravity task was published, give its ID and repository link. Write the `[PROMPT FOR ANTIGRAVITY]` instructions in the repository.

## Repository handoff queue

- Codex prepends each task to `handoff/FOR_ANTIGRAVITY.md` with a unique ID, instructions, and acceptance evidence, then commits and pushes it. Keep the ID stable. Issue a new ID for a follow-up.
- At the start of its work, Antigravity runs `git pull --ff-only origin main` and reads both handoff files. It takes the newest task with no report for that ID. If all tasks have reports, it is idle.
- Antigravity prepends its English report to `handoff/FROM_ANTIGRAVITY.md`, using the same task ID, tested commit, and status `complete` or `blocked`. It stages that file alone, commits, and pushes to `origin/main`. Both statuses close the queue entry. The report gives the acceptance result separately.
- At the start of a follow-up, Codex fetches `origin/main`, reads any new reports, and uses the evidence to update `TODO.md` or publish a new task. The operator can inspect the inbox in GitHub or with a read-only Git command.

## Token economy and data safety

- Always test parser, exporter, and UI changes using `main.py --rebuild-csv-only` against the existing `cache/` before asking for live extraction. This spends zero API tokens. Run `python -m pytest tests/test_core.py` for code changes.
- Live dev retries must target identified failing or low-F1 papers using `--only`. Use `--force` only for affected IDs whose completed cache must be replaced. Resume partial extractions before forcing a restart. The first full 111-paper test run requires Phase 1 sign-off and operator approval. Resume test failures by ID.
- Preserve raw per-document cache version 2 and offline rebuild compatibility. Keep the seven CSVs conformant to `submission_template/schema.json`. Use an empty string for missing source evidence. Never guess.
- Generalize from document structure. Never hardcode dev paper IDs, dataset names, model names, or ablation strings from `dev_gold/` in extraction logic. IDs are allowed in targeted verification commands and their reports.
- Check `.gitignore` and the staged file list before committing. Never commit `.env`, keys, raw PDFs, `dev/`, `test/`, `cache/`, `out_dev/`, `out_test/`, or raw logs with sensitive material. Use `.env.example` for placeholders.
