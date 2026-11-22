# Repository workflow

## Priority and ownership

Antigravity is occupied with a separate task. Codex owns the current repository work. Treat both handoff queue files as read-only until the operator explicitly authorizes queue changes. Existing unanswered entries are suspended while this restriction applies.

1. Deliver and sign off on a jury-ready MVP before optimizing strict F1.
2. **OpenAI Codex, Thunderobot 911 laptop** owns code in `core/`, `plugins/`, `scripts/`, `tools/`, `tests/`, `app/` and the pipeline entry point, plus architecture reviews, pytest, the roadmap, and Git checkpoints. It can inspect PDFs and run local tools, OCR, and cache rebuilds where inputs are available.
3. **Antigravity, second laptop**, when active, pulls `origin/main`, runs the newest unanswered task, and pushes its report directly to `origin/main`. Its only handoff edit is the English evidence in `handoff/FROM_ANTIGRAVITY.md`.
4. **Human operator** reviews the Russian status report and demo checkpoint and signs off on the MVP before Phase 2. The agents exchange all task details and evidence through Git.

## Start of every task and clean session

- Before making changes, inspect the worktree with `git status --short --branch`, then run `git fetch origin` and `git pull --ff-only origin main`. Keep local user changes intact. If a fast-forward is blocked or branches diverge, inspect the differences and coordinate with the operator before overlapping edits.
- Read `git log -n 5 --oneline`, `TODO.md`, and `handoff/FROM_ANTIGRAVITY.md` after synchronization. Check for changes from Antigravity or the operator that affect the active task.
- Work on shared modules sequentially. If another agent is changing the same files or has an active assignment covering them, record the overlap in `TODO.md` and coordinate before editing the overlapping area. Record architectural ideas, hazards, and validation evidence in `TODO.md` under `## Notes for Antigravity` without posting an active handoff task.

## Antigravity mirror protocol (sequential work and context resets)

- **Sequential work and file boundaries:** Antigravity and Codex work sequentially in the same repository. Antigravity does not edit core, parser, exporter, test, or UI modules owned by Codex (`core/`, `plugins/`, `scripts/`, `tools/`, `tests/`, `app/`, `main.py`) without explicit operator instruction, and does not overwrite Codex's active task queue or `## Current checkpoint` in `TODO.md`.
- **Mandatory start-of-session sync:** Before starting any task (and especially in every new clean chat), Antigravity runs `git status --short --branch`, `git fetch origin`, and `git pull --ff-only origin main`, then reads `git log -n 5 --oneline`, `TODO.md` (including `## Current checkpoint` and `## Notes for Antigravity`), and `handoff/FOR_ANTIGRAVITY.md` so all recent Codex changes and notes are accounted for.
- **Cross-agent notes without overlapping edits:** When Antigravity has architectural ideas, schema/interface warnings, audit evidence, or validation notes for Codex, it records them under `## Notes for Codex` in `TODO.md` (or `handoff/NOTES.md` if created) without modifying Codex-owned files or read-only handoff queues unless explicitly instructed.
- **Regular context-reset checkpointing:** `TODO.md` is the single source of truth between clean sessions. After completing any task and before resetting chat context, Antigravity updates its status, touched files, notes for Codex, and next step under `## Notes for Codex` in `TODO.md`, runs relevant local checks (keeping paused UI servers stopped unless asked), verifies `.gitignore` and the staged file list, commits only intended paths, and pushes to `origin/main` (verifying the remote commit).

## Language, demos, and checkpoints

- Communicate with the operator in Russian. Write code and comments, commit messages, `TODO.md`, `handoff/` files, and inter-agent instructions in English. Preserve source quotations in their original language.
- `TODO.md` is the source of truth between clean sessions. After each task and before resetting context, update its current checkpoint with the tested commit, metric scope and values, paper and cache status, active constraints, notes for Antigravity, blockers, and the exact next step. Link historical evidence when useful.
- Run the relevant checks. Confirm `.gitignore` and review the staged file list, stage only intended paths, commit, and push to `origin/main`. Verify the remote commit before considering the checkpoint saved. Record any validation or synchronization blocker explicitly.
- End every operator response with `[ОТЧЁТ ДЛЯ ПОЛЬЗОВАТЕЛЯ / ЧТО МОЖНО ПОСМОТРЕТЬ СЕЙЧАС]` (Russian, up to 10 lines, with the change, a command or URL, serious blockers, and whether the gate passed). If an Antigravity task was published, give its ID and repository link. Write the `[PROMPT FOR ANTIGRAVITY]` instructions in the repository.

## Repository handoff queue

This protocol applies after explicit authorization from the operator. While Antigravity is occupied, Codex reads `handoff/FROM_ANTIGRAVITY.md` for context and leaves both queue files intact. Architecture notes belong in `TODO.md`.

- Codex prepends each task to `handoff/FOR_ANTIGRAVITY.md` with a unique ID, instructions, and acceptance evidence, then commits and pushes it. Keep the ID stable. Issue a new ID for a follow-up.
- At the start of its work, Antigravity runs `git pull --ff-only origin main` and reads both handoff files. It takes the newest task with no report for that ID. If all tasks have reports, it is idle.
- Antigravity prepends its English report to `handoff/FROM_ANTIGRAVITY.md`, using the same task ID, tested commit, and status `complete` or `blocked`. It stages that file alone, commits, and pushes to `origin/main`. Both statuses close the queue entry. The report gives the acceptance result separately.
- At the start of a follow-up, Codex fetches `origin/main` and reads any new reports. After recording the evidence in `TODO.md`, remove the answered or superseded task instructions from the open queue. Preserve the report and Git history. Use a new task ID if further work is needed. The operator can inspect the inbox in GitHub or with a read-only Git command.

## Token economy and data safety

- Always test parser, exporter, and UI changes using `main.py --rebuild-csv-only` against the existing `cache/` before asking for live extraction. This spends zero API tokens. Run `python -m pytest tests/test_core.py` for code changes.
- Live dev retries must target identified failing or low-F1 papers using `--only`. Use `--force` only for affected IDs whose completed cache must be replaced. Resume partial extractions before forcing a restart. The first full 111-paper test run requires Phase 1 sign-off and operator approval. Resume test failures by ID.
- Preserve raw per-document cache version 2 and offline rebuild compatibility. Keep the seven CSVs conformant to `submission_template/schema.json`. Use an empty string for missing source evidence. Never guess.
- Generalize from document structure. Never hardcode dev paper IDs, dataset names, model names, or ablation strings from `dev_gold/` in extraction logic. IDs are allowed in targeted verification commands and their reports.
- Check `.gitignore` and the staged file list before committing. Never commit `.env`, keys, raw PDFs, `dev/`, `test/`, `cache/`, `out_dev/`, `out_test/`, or raw logs with sensitive material. Use `.env.example` for placeholders.
