# PROMPT FOR ANTIGRAVITY

After `git pull --ff-only origin main`, read this queue and `handoff/FROM_ANTIGRAVITY.md`. Tasks are listed newest first. Run the first task without a report for its ID. If the queue is empty or every ID already has a report, wait for a new task.

To finish a task, prepend an English report with the same ID to `handoff/FROM_ANTIGRAVITY.md`. Use `complete` or `blocked` and record whether the acceptance check passed. Commit and push only the report:

```powershell
git add -- handoff/FROM_ANTIGRAVITY.md
git diff --cached --name-only
git commit --only -m "Report <task ID> verification" -- handoff/FROM_ANTIGRAVITY.md
git push origin main
```

If `main` advanced, run `git pull --rebase origin main` and retry. Preserve existing reports. Keep credentials, PDFs, caches, generated bundles, and full logs local.

## Open tasks

### MVP-UI-001 · Open the jury dashboard with the dev bundle

From the repository root, with the project Python environment active, run:

```powershell
git pull origin main
python tools/check_submission.py out_dev dev --ocr --json-report out_dev/validation.json
python scripts/serve_ui.py out_dev
```

The checker uses local files and spends zero API tokens. If Tesseract is outside PATH, pass its executable using `--tesseract`. Exit code 2 still produces the report and allows the UI demo. Open `http://127.0.0.1:8000/`, show the four KPIs, search for a paper or metric, switch tabs, and open one verified result with its quote and one result with linked issues. Reply with the URL, commit, and observed checks under `MVP-UI-001` in `handoff/FROM_ANTIGRAVITY.md`.
