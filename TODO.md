# RAG extraction roadmap

## Operating mode

- Codex executes one stage at a time on its own. After implementation and a dev measurement, record row counts, Strict and Loose R/P/F1, runtime and tokens. The operator approved continuing from Stage 2 directly to Stage 3.
- Keep the same configured model and provider in Stage 1. Start with a cache-only rebuild and local PDF checks. Use an isolated cache for targeted live extraction so the accepted dev bundle and raw cache remain reproducible.
- Use no benchmark IDs, entity names, or gold values in extraction rules. Preserve cache v2 and the seven CSV schemas. Keep the frontend and the 111-paper test corpus outside these stages.

## Reference measurements

- The [metric audit](METRIC_AUDIT.md) established the next priorities. The optional partial-cache export recovered 101 Strict and 150 Loose TP on the same local snapshot, with an explicit incomplete status and zero API calls.

- Domain 2 at `b5cb065`: 4,922 scored predictions and 19,392 gold observations. Strict R/P/F1 **0.030/0.118/0.048** (579 TP). Loose R/P/F1 **0.089/0.350/0.142** (1,721 TP).
- Latest verified full-cache reference, [RECALL-DEV-002](handoff/FROM_ANTIGRAVITY.md#recall-dev-002): 4,945 predictions, Strict R/P/F1 **0.038/0.150/0.061** (741 TP), Loose R/P/F1 **0.096/0.375/0.152** (1,854 TP). Compare local runs using the same input PDFs and available cache. Earlier experiments are in [the checkpoint log](handoff/STRICT_F1_STATE.md).

## Stage 1 · Structured PDF parsing and OCR

- [x] **1.1 Native PDFs.** Use page-aligned PyMuPDF4LLM Markdown with inline HTML grids and merged headers. Try an alternate native grid detector when the first pass omits substantial numeric text. Preserve page markers and end matter. Keep native text for citation checks and disable OCR on readable pages.
- [x] **1.2 Scanned and mixed PDFs.** Use local RapidOCR with spatial text injection, then apply the same structured page renderer. Supplement collapsed scan tables with aligned OCR baselines. Share the OCR engine with citation verification, report unreadable pages and preserve the existing multimodal fallback where available.
- [x] **1.3 Measure the local dev pilot.** 3,913 → 3,979 scored predictions, Strict R/P/F1 0.02867/0.14209/0.04772 → 0.02707/0.13194/0.04493, Loose R/P/F1 0.06905/0.34219/0.11491 → 0.06962/0.33928/0.11553. Both bundles had zero structural errors. The pilot refreshed two papers against the 21-paper gold set and left three local cache gaps. Strict F1 declined. See [the measurement log](handoff/STRICT_F1_STATE.md#stage-1--structured-pdf-and-ocr-local-pilot) for verification and limitations.
- [x] **Operator checkpoint.** Stages 2 and 3 are authorized in sequence.

## Stage 2 · Table windows and response capacity

- [x] **2.1 Table-first windows.** Send each table or row split with its caption, headers and section. Preserve merged cells, capture captioned flattened grids, checkpoint successful slices, and process remaining prose through the final page.
- [x] **2.2 Compact responses.** Validate positional arrays and expand them before cache writes. Default to 393,216 tokens on the official DeepSeek endpoint. Respect the configured 16,384-token cap on the current gateway. The targeted replay recovered 252 → 269 raw observations, with 2.43× fewer output tokens per observation. Corpus Strict and Loose TP stayed at 525 and 1,350. Proceed to Stage 3.

## Stage 3 · Strict context and seven-field tuples

- [x] **3.1 Paper entity passport.** Collect datasets, generators, RAG variants and scoped metric cutoffs in the first metadata request. Pass the matching page and table scope to each extraction request. The live pilot returned seven scopes and completed the paper.
- [x] **3.2 Source-backed normalization.** Resolve entity typography and explicit model identifiers, read metric cutoffs separately from display labels, and inherit context when the local source is unambiguous. On the same cache, Strict TP rose from 525 to 668 and Strict F1 from 0.04490 to 0.05713. The fresh-paper variant scored 607 Strict TP and remains an isolated comparison. Both bundles passed structural validation. [Detailed results](handoff/STRICT_F1_STATE.md#stage-3--entity-passport-and-source-backed-normalization)

The local measurements cover 18 complete caches against all 21 gold papers. D002, D009 and D013 remain unresolved in the local snapshot. The accepted jury bundle and test corpus remain outside this pilot.

## Next priorities from the metric audit

- [ ] Restore complete cache coverage and preserve compatible per-document progress across extraction retries.
- [ ] Verify chart provenance and source-supported series context. Evaluate vector recovery separately from the default bundle.
- [ ] Reduce confirmed dataset, generator and variant mismatches with source evidence on a frozen cache.
- [ ] Run controlled gateway and OCR experiments after measuring the dominant coverage and context losses.
