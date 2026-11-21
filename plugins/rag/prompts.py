"""Prompts for the RAG case (VINITI adaptation). Output language of free text: English
(as in dev_gold); source quotes stay verbatim in the PDF language."""
from __future__ import annotations

import json

SYSTEM = """You extract structured data from scientific papers about Retrieval-Augmented Generation (RAG) for a benchmark that is scored against expert annotation.

HARD RULES
1. Never invent. If a value is not stated in the paper, output "" (empty string). Zero is "0", never "". Never output null/NaN/unknown/N/A.
2. Do not infer versions, parameters, scales or conditions from general knowledge or other papers. Keep the paper's own notation (e.g. "GPT-4o mini", "LLaMA3-8B-Instruct"). Explain ambiguity in `note`.
3. Ranges (e.g. "256-512") must NOT be averaged: leave the numeric field empty and put the range in `note`.
4. Numbers: copy `raw_value` exactly as printed (".204", "62.4", "≈62.4", "3.0%", "-1.5"). Put the printed unit in `raw_unit` only if it is printed ("%", "ms", "s", "tokens"); otherwise "". Do not convert units or scales yourself.
5. Page numbers are PDF page numbers starting at 1 (the `--- PAGE N ---` markers, or the physical page index of the PDF file), NOT printed journal page numbers.
6. `source_fragment` is a short VERBATIM quote (copy characters exactly, ideally one table row or one sentence, max ~200 chars) from exactly the declared page that contains the value. Never paraphrase. For values read from a plot/figure, use the figure caption start or axis label as the quote, set `source_figure` ("Figure 3") and explain how the value was read in `note`.
7. `result_origin`: "primary" = number obtained by the authors in this work (including re-runs of other authors' methods); "cited" = number copied from another work (then `cited_ref` = reference as written, e.g. "[12]" or "Lewis et al., 2020"). Otherwise cited_ref = "".
8. `extraction_status`: "extracted" (default, value readable), "present_not_extractable" (value clearly exists but cannot be read reliably), "absent" (metric announced but value not given). Do not create rows for absent combinations of metrics x configurations.
9. Separate configurations: different generators, ablation variants, retrieval settings are DIFFERENT configurations. Different datasets/splits/versions are different datasets. Do not merge experiments with different protocols.
10. Do not multiply percentages/fractions: keep what is printed. Differences/deltas in tables (e.g. "+3.2", "Δ", "improvement") are separate metrics: put the delta in metric_name (e.g. "EM delta") and raw_unit "%" only if printed with %.
11. metric_direction: "higher_is_better", "lower_is_better", "target" or "" if unclear. metric_k: integer k for @k metrics (Recall@5 -> metric_name "Recall@5", metric_k "5"); "" otherwise. A fractional threshold (OC@0.8) is not k. top_k of the retriever is a configuration field, not metric_k.
12. source_fragment must be copied character-for-character from the text layer (keep its spacing, symbols and line order; do not re-join hyphenated line breaks, do not fix typos, do not add "..."). Prefer the shortest span that contains the number (e.g. "Recall@5 0.712"). Same number printed in a table and in text: quote the table row once.
13. Never output the same entity twice: one configuration/dataset/task/experiment per distinct setting, with the SAME name spelling as the paper. result_origin "cited" iff cited_ref is non-empty. Do not scale values: if the table says 62.4 without %, raw_unit is "".
14. `rag_variant` = METHOD/pipeline name only (e.g. "Vanilla RAG", "Focal Mixed Training", "RA-CoT", "retriever only"); NEVER append the generator/backbone/retriever name to it. `generator_model` = the LLM only (paper notation), "" for retriever-only systems. Same method with 3 generators = 3 configurations with the same rag_variant.
15. EXHAUSTIVENESS: extract EVERY numeric cell of EVERY results, ablation, hyperparameter, cost/efficiency, analysis and appendix table (all baselines, all ablation rows, all datasets x metrics x generators), plus numbers in running text. Never summarize, sample or skip rows/columns; if a table is long, keep going until the last row. Each metric column = its own row (EM and F1 separately). Do not output rows without a numeric value.
16. Identifiers: configurations C01, C02, ...; datasets DS1, DS2, ...; tasks T1, T2, ...; experiments E1, E2, ... (consistent everywhere).
"""

FEWSHOT = """
CANONICAL CONVENTIONS (from the expert-annotated gold set)
- Table "Method x Generator x Dataset x Metric" is expanded to ATOMIC rows: one configuration per (method, generator); one result row per (configuration, dataset, metric).
  Example: row "RA-CoT" with generators LLaMA3-8B-Instruct / Qwen3.5 plus / GPT-4o mini and datasets HotpotQA, 2Wiki each with EM and F1
  -> 3 configurations {rag_variant:"RA-CoT", generator_model:"LLaMA3-8B-Instruct"|"Qwen3.5 plus"|"GPT-4o mini"}, each with 2 datasets x 2 metrics = 4 rows.
- Retriever-only systems: {rag_variant:"Retriever-Only", generator_model:""}; reranker variants: {rag_variant:"Retriever-Only + LCR"}. The reranker/method is part of rag_variant, the LLM never is.
- No retrieval / closed-book LLM rows: {rag_variant:"No Retrieval" (or "Baseline" if the paper calls it so), generator_model:<LLM>}.
- WRONG: {rag_variant:"Vanilla RAG Llama 3.1 8B Instruct"}. RIGHT: {rag_variant:"Vanilla RAG", generator_model:"Llama 3.1 8B Instruct"}.
- @k metrics: metric_name "NDCG@5" (no spaces) and metric_k "5"; plain "Accuracy" has metric_k "". OC@0.8 is a threshold: metric_k "".
- Scale: copy the printed number. ".204" -> raw_value ".204" (fraction); "62.4%" -> raw_value "62.4%", raw_unit "%". Never convert 0.204 <-> 20.4.
- A column of deltas/improvements ("EM improvement over X", "EM decrease") is its own metric name. A cost table (tokens, ms, USD) is its own experiment with its own metric names and units.
- Ablation rows ("w/o X") are separate configurations: rag_variant "<Method> w/o X".
- Numbers copied from another paper's results (marked with a citation or "reported in [x]") = cited with cited_ref; the authors' own runs of baselines = primary.
- DATASETS are granular: every sub-corpus, domain, language, property, split or aggregate shown as a row/column gets its OWN dataset ("DocBench / Law", "OpinioBank: Ala Moana Honolulu", "RAG-Multi-Corpus / Overall", "mean over TREC DL19 and DL20"). Use the table's own label. A table without a dataset dimension => dataset_id "" unless the paper has one dataset.
- METRIC NAMES: use the full name as the paper defines it ("Entity Match Rate", "Factuality", "Answer accuracy"), not a table abbreviation ("EM-R", "Fac.", "Acc"). Keep one spelling for the same metric everywhere.
- metric_k: if a column/section is computed at a stated retrieval depth (top-20 retrieved items, "k=5"), put that integer in metric_k even if the name has no "@".
- rag_variant: the full row label as printed, including qualifiers ("Traditional RAG raw KB", "PrismRAG w/o Distractor", "ThreadRAG ablation SN+STG+EDP"); ablation/sweep rows keep their own variant, do not collapse them into the full method.
- generator_model: copy the notation printed in the table/caption ("LLaMA3-8B-Instruct", "Qwen-14B", "GPT-4o mini"); do NOT expand it to a full official model name or add version numbers/vendor prefixes that are not printed there.
- A qualitative statement without a number ("significantly better") is NOT a result row.
"""

IN_SCOPE_RUBRIC = """IN_SCOPE RUBRIC (precision matters: every excluded paper must have in_scope=false and EMPTY entity lists, otherwise its metrics count as false positives)
in_scope=true when ALL hold: (a) a system, method, benchmark or analysis in the paper retrieves from an EXTERNAL document/knowledge collection (chunks, passages, web, KB, graph built from documents) and conditions generation of an answer on it; (b) the paper reports measured evaluation results (tables/plots/text numbers) for such configurations. Includes: RAG methods, RAG training/reranking/chunking/watermarking/security/benchmark papers, RAG analyses, domain RAG applications with evaluation.
in_scope=false when ANY holds: pure retrieval/embedding paper with no generation step evaluated; pure LLM paper without external retrieval (parametric knowledge only, long-context, fine-tuning only); survey/position paper with no new measurements; RAG only mentioned as related work or motivation; no quantitative results at all.
Decide from the paper's content, not its title. exclusion_reason: one sentence stating which criterion fails.
"""

META_USER = """TASK: read the whole paper and return the paper-level entities.

1. publication (apply the IN_SCOPE RUBRIC at the end of this message): title, year (4 digits), doi (only if printed), authors ("First Last; First Last"), in_scope, exclusion_reason.
   in_scope=true only if the paper itself describes a system that retrieves information from an external document collection and uses the retrieved context to produce an answer, AND reports a configuration with evaluation results. Decide by content, not by the word RAG in the title. If false: give a short exclusion_reason and return EMPTY lists for configurations, datasets, tasks, experiments, issues. If true: exclusion_reason = "".
2. configurations (rag_variant = method only, generator_model = LLM only; one row per method x generator, including baselines, ablations, appendix and analysis setups): every distinct RAG system/baseline/ablation/generator variant that has results (one row per table row x generator when generators differ). `note`: where defined (page, table row).
3. datasets (name, version, language, split, domain), tasks (task_type, e.g. "open-domain multi-hop question answering"), experiments (evaluation protocol, baseline names joined by ";", hardware, latency in ms only if the source unit is known, tokens per query, evaluation sample size).
4. issues: contradictions inside the paper about configuration or protocol facts (e.g. two different embedding models stated); use check_name such as protocol_mismatch, contradiction, normalization. Empty list if none. source_page 0 and source_fragment "" if not applicable.

Use only the paper. Leave unknown fields "".
"""
META_USER = META_USER + "\n" + IN_SCOPE_RUBRIC

VERIFY_USER = """TASK: AUDIT of PDF page {page}. Rows already extracted from this page are listed below (compact). Find numeric values on this page that are MISSING (every table cell of every table on the page, appendix tables, ablation/baseline rows, values in text) and return ONLY the missing rows in `results`, following all rules. Do not repeat existing rows. Return an empty list if nothing is missing.
Return compact JSON.

ENTITIES: {entities}

ALREADY EXTRACTED (config_id|dataset_id|metric|raw_value|origin): {existing}
"""


def verify_user(meta: dict, page: int, existing: list[str]) -> str:
    ent = window_user(meta, page, page).split("ENTITIES (already extracted, ids fixed):\n", 1)[1]
    return VERIFY_USER.format(page=page, entities=ent, existing=json.dumps(existing, ensure_ascii=False))


def window_user(meta: dict, first: int, last: int, part: bool = False) -> str:
    ent = {
        "configurations": [{k: c.get(k, "") for k in ("config_id", "rag_variant", "generator_model", "retriever_model", "note")}
                           for c in meta["configurations"]],
        "datasets": [{k: d.get(k, "") for k in ("dataset_id", "dataset_name", "dataset_version", "data_split")}
                     for d in meta["datasets"]],
        "tasks": [{k: t.get(k, "") for k in ("task_id", "task_type")} for t in meta["tasks"]],
        "experiments": [{k: e.get(k, "") for k in ("experiment_id", "evaluation_protocol")}
                        for e in meta["experiments"]],
    }
    return (
        f"TASK: extract ALL result values (every metric value in every table, plus results stated in the running text or readable from figures) "
        f"located on PDF pages {first}-{last} ONLY. Ignore other pages. Return rows in `results`.\n\n"
        "One row = one value of one metric for one experiment/configuration/dataset/task. Use experiment_id/config_id/dataset_id/task_id "
        "ONLY from the entity lists below (copy the id exactly; \"\" if none fits). Include baseline rows reported in the paper's tables "
        "(origin primary if re-run by the authors, cited if copied from other work). A numeric baseline cell with its own identifiable setting is a separate "
        "result row. `baseline_value` can also link a comparable baseline; it never replaces an independently reported result.\n"
        "Set source_page for every row to the PDF page where the value appears; source_table like \"Table 1\"; source_section like \"4.2\".\n"
        "Apply the same extraction rules to appendices and supplementary pages. For reference lists and pages that genuinely have no numeric results, return an empty list.\n"
        "OUTPUT SIZE: return compact JSON (no indentation, no extra whitespace or blank lines). source_fragment must be a SHORT verbatim quote "
        "(at most 15 words around the value, e.g. the table row); keep note short or empty.\n"
        + ("NOTE: the text below is only a FRAGMENT of the page (a few lines may repeat from the neighbouring fragment); "
           "extract only values visible in it and keep source_page = the page number in the marker. "
           "Lines between [TABLE HEADER CONTEXT...] and [END HEADER CONTEXT] are only the table caption/column headers repeated from above: "
           "use them to name metrics/columns (and source_table), never as a source of values or quotes.\n" if part else "")
        + "\n"
        "ENTITIES (already extracted, ids fixed):\n" + json.dumps(ent, ensure_ascii=False)
    )

SYSTEM = SYSTEM + FEWSHOT
