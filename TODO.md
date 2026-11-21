# RAG extraction roadmap

## Operating mode

- Codex executes one stage at a time on its own. After implementation and a dev measurement, record row counts, Strict and Loose R/P/F1, runtime and tokens, then wait for explicit operator approval before the next stage.
- Keep the same configured model and provider in Stage 1. Start with a cache-only rebuild and local PDF checks. Use an isolated cache for targeted live extraction so the accepted dev bundle and raw cache remain reproducible.
- Use no benchmark IDs, entity names, or gold values in extraction rules. Preserve cache v2 and the seven CSV schemas. Keep the frontend and the 111-paper test corpus outside these stages.

## Reference measurements

- Domain 2 at `b5cb065`: 4,922 scored predictions and 19,392 gold observations. Strict R/P/F1 **0.030/0.118/0.048** (579 TP). Loose R/P/F1 **0.089/0.350/0.142** (1,721 TP).
- Latest verified full-cache reference, [RECALL-DEV-002](handoff/FROM_ANTIGRAVITY.md#recall-dev-002): 4,945 predictions, Strict R/P/F1 **0.038/0.150/0.061** (741 TP), Loose R/P/F1 **0.096/0.375/0.152** (1,854 TP). Compare local runs using the same input PDFs and available cache. Earlier experiments are in [the checkpoint log](handoff/STRICT_F1_STATE.md).

## Stage 1 · Structured PDF parsing and OCR

- [x] **1.1 Native PDFs.** Use page-aligned PyMuPDF4LLM Markdown with inline HTML grids and merged headers. Try an alternate native grid detector when the first pass omits substantial numeric text. Preserve page markers and end matter. Keep native text for citation checks and disable OCR on readable pages.
- [x] **1.2 Scanned and mixed PDFs.** Use local RapidOCR with spatial text injection, then apply the same structured page renderer. Supplement collapsed scan tables with aligned OCR baselines. Share the OCR engine with citation verification, report unreadable pages and preserve the existing multimodal fallback where available.
- [x] **1.3 Measure the local dev pilot.** 3,913 → 3,979 scored predictions, Strict R/P/F1 0.02867/0.14209/0.04772 → 0.02707/0.13194/0.04493, Loose R/P/F1 0.06905/0.34219/0.11491 → 0.06962/0.33928/0.11553. Both bundles had zero structural errors. The pilot refreshed two papers against the 21-paper gold set and left three local cache gaps. Strict F1 declined. See [the measurement log](handoff/STRICT_F1_STATE.md#stage-1--structured-pdf-and-ocr-local-pilot) for verification and limitations.
- [ ] **Operator checkpoint.** Review the pilot before authorizing Stage 2.

## Stage 2 · Table windows and response capacity

- [ ] **2.1 Table-first windows.** Send one table with its caption, headers and section per result request. Split oversized tables on row boundaries, repeat required headers, and track all pieces through the final appendix.
- [ ] **2.2 Compact responses.** Check the configured DeepSeek model and its documented output cap. Use the available cap and a validated compact row-array response, expanded to the existing cache/CSV shape. Measure capacity, output tokens per observation, Strict/Loose metrics and completeness on dev. Stop for approval.

## Stage 3 · Strict context and seven-field tuples

- [ ] **3.1 Paper entity passport.** Collect datasets, generators, RAG variants and cutoffs in one metadata request per paper. Include the supported entities with each table and inherit keys from the applicable headers and captions.
- [ ] **3.2 Source-backed normalization.** Split metric suffixes such as `Metric@k`, canonicalize names and spacing, and inherit unambiguous context without filling unsupported values. Keep experiment limits distinct from metric cutoffs. Measure Strict/Loose results and review diagnostics on dev. Stop for approval.
