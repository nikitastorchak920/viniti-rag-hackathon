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

No pending tasks.
