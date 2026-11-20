# Project Rules (Strict Token Economy)

## Role & Division of Labor
- You are the surgical code executor.
- Research, architecture design, prompt engineering, and large-file analysis are handled externally. Do NOT spend tokens brainstorming or exploring alternatives unless explicitly asked.

## Workflow & Context Discipline
- Execute strictly ONE atomic task at a time (from `TODO.md` or user prompt).
- If `TODO.md` exists: complete ONLY the first unchecked `[ ]` item, mark it `[x]`, and stop immediately.
- Never read entire directories or large files blindly. Use targeted search/line ranges or inspect schemas and first 5 lines only.
- NEVER read raw datasets, `*.pdf`, `*.csv`, `*.xlsx`, `*.parquet`, `*.log`, lockfiles, or large `*.json` files.

## Output & Coding Style
- Be maximally concise. No greetings, no summaries, no "why this works" explanations, no trailing remarks.
- Write clean, minimal, working MVP code. No over-engineering.
- Edit only the specific files required for the current task.
- When fixing errors, state the root cause in 1 line and apply the minimal patch.

## Project Context
- Goal: Scientific PDF parsing pipeline (table/formula/entity extraction -> exact source linking -> unit normalization -> consistency validation -> search/filter UI).
- Stack: [TBD]
- Run / Test commands: [TBD]

## Server Hardware & Resource Limits (STRICT)
- The server has ONLY 1 GB RAM and 10 GB disk space.
- NEVER install heavy libraries (e.g., `pandas`, `torch`, `tensorflow`, `scipy`, local OCR engines like `tesseract`/`easyocr`, or heavy PDF/image suites). Use Python stdlib (`csv`, `json`, `re`, `sqlite3`) and lightweight parsers only.
- Process files strictly ONE by one in streaming/sequential mode; never load the full dataset or multiple PDFs into memory at once.
- Immediately delete any temporary files, caches, and intermediate artifacts after processing.

## Safe Testing on This VPS (MANDATORY)
- Before any test run: `free -m && df -h /`. If free RAM < 300 MB or free disk < 1 GB, clean caches/temp files first.
- Wrap every test execution with limits, e.g. `timeout 60s python3 <script>`.
- Run in stages: (1) 1-2 PDFs from `dev/`, inspect output; (2) only after Stage 1 succeeds within memory limits, full `dev/` (21 files) validated against `dev_gold/`; (3) NEVER run on `test/` (90 files) until `dev/` fully passes and the user explicitly confirms.
- Per PDF: open -> extract -> write output to disk -> explicitly close document -> `gc.collect()`.
- Image-only scans without a text layer: skip immediately and log with a separate status (e.g. `SKIPPED_SCAN`). No OCR or heavy image rendering on this server.
- Do not keep text dumps or debug artifacts in the repository; clean `/tmp` and caches right after testing.
- After every test run report concisely: files processed, files skipped, peak RAM, errors, validation mismatches.

## Autonomy & Package Policy
- Pre-approved: installing lightweight system/Python packages (e.g. `python3-pymupdf`, `pypdf`, `pydantic`) via `apt install -y` or `pip --no-cache-dir`; run `apt clean` / clear pip caches afterwards.
- Still banned: heavy ML/OCR packages (`torch`, `tensorflow`, `pandas`, `scipy`, `tesseract`, `easyocr`) and running the full 90-file `test/` set without explicit user approval.
- Do small technical fixes and Stage 1-2 tests autonomously; do not pause to ask for minor confirmations.
