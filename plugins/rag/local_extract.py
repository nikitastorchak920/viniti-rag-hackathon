"""Local rule-based fallback (no API): PyMuPDF words + regex. Finds numeric table rows,
maps them to header cells, builds the same cache format as the DeepSeek pipeline so that
exporter / check_submission / evaluate work unchanged. Image-only PDFs are skipped.
Heuristic and lossy: meant for validating the pipeline on a tiny VPS, not for submission."""
from __future__ import annotations

import gc
import pathlib
import re
import time

from core.llm_client import load_cache, save_cache
from core.pdf_processor import MIN_CHARS_PER_TEXT_PAGE

CACHE_VERSION = 2
NUMTOK = re.compile(r"^[+-]?(?:\d+\.\d*|\d*\.\d+|\d+)%?$")
METRIC = re.compile(r"(?i)^(em|f1|f-?score|acc(?:uracy)?\.?|precision|recall|p|r|hits?|mrr|ndcg|map|bleu(?:-\d)?|"
                    r"rouge(?:-[12l])?|bertscore|exact match|faithfulness|correctness|latency|time|score|ef1)"
                    r"(?:\s*@\s*\d+)?$")
DATASET = re.compile(r"(?i)hotpot|2wiki|wikimulti|musique|nq\b|natural questions|triviaqa|popqa|ms ?marco|beir|fever|"
                     r"asqa|eli5|squad|webq|bamboogle|strategyqa|\w+qa\b")
CAPTION = re.compile(r"^((?:Table|Таблица)\s+\d+)\s*[:.]")
SECTION = re.compile(r"^(?:\d+(?:\.\d+)*\.?\s+)?(Abstract|Introduction|Related Work|Methods?|Methodology|Experiments?|Results?|"
                     r"Discussion|Conclusions?|References|Appendix)\s*$", re.I)
SCOPE_KW = ["rag", "retrieval-augmented generation", "dense retrieval", "sparse retrieval", "hybrid retrieval", "bm25",
            "vector database", "vector db", "vector store", "vector index", "embedding", "reranker", "re-ranker", "chunking",
            "top-k", "faiss", "chromadb", "weaviate", "qdrant", "milvus", "colbert", "splade", "graph rag", "graphrag",
            "agentic rag", "retriev"]
KNOWN_DS = {"Natural Questions": r"natural questions|\bNQ\b", "HotpotQA": r"hotpotqa", "MS MARCO": r"ms ?marco",
            "TriviaQA": r"triviaqa", "BEIR": r"\bBEIR\b", "FEVER": r"\bFEVER\b", "PubMedQA": r"pubmedqa",
            "2WikiMultiHopQA": r"2wiki\w*", "MuSiQue": r"musique", "ASQA": r"\bASQA\b", "ELI5": r"\bELI5\b"}
RX_TOPK = re.compile(r"(?i)\btop[- ]?k\s*(?:=|:|of|is|set to)\s*(\d+)|\btop[- ](\d+)\s+(?:passages|documents|chunks|results)")
RX_CHUNK = re.compile(r"(?i)chunk(?:s)?(?: size)?\s*(?:=|:|of|is|set to)?\s*(\d+)\s*(tokens?|characters?|words?)|(\d+)[- ](token|character|word)s? chunks?")
RX_OVER = re.compile(r"(?i)(?:chunk )?overlap\s*(?:=|:|of|is|set to)?\s*(\d+)")
RX_LAT = re.compile(r"(?i)\b(?:latency|ttft|time to first token)[^.\d]{0,40}?(\d+(?:\.\d+)?)\s*(ms|milliseconds?|s|sec|seconds?)\b")
RX_TOK = re.compile(r"(?i)(\d[\d,]*(?:\.\d+)?)\s*tokens?\s*(?:per|/)\s*(?:query|question)")
METH = {"hybrid": r"hybrid (?:retrieval|search)", "dense": r"dense retrieval", "sparse": r"sparse retrieval|\bbm25\b",
        "graph": r"graph[- ]?rag|graph retrieval"}


def _cells(words: list[tuple]) -> list[tuple[str, float]]:
    """Merge adjacent words (small x-gap) into cells -> [(text, y)]."""
    cells: list[list] = []
    for w in sorted(words, key=lambda w: w[0]):
        if cells and w[0] - cells[-1][2] < 6:
            cells[-1][0] += " " + w[4]
            cells[-1][2] = w[2]
        else:
            cells.append([w[4], w[0], w[2]])
    return [(c[0], c[1]) for c in cells]


def _lines(page) -> list[dict]:
    words = sorted(page.get_text("words"), key=lambda w: (w[1] + w[3]) / 2)
    groups: list[list] = []
    for w in words:
        yc = (w[1] + w[3]) / 2
        if groups and abs(yc - groups[-1][0]) <= 3.0:
            groups[-1][1].append(w)
        else:
            groups.append([yc, [w]])
    out = []
    for yc, ws in groups:
        ws.sort(key=lambda w: w[0])
        out.append({"y": yc, "words": [w[4] for w in ws], "cells": [c[0] for c in _cells(ws)],
                    "text": " ".join(w[4] for w in ws)})
    return out


def _data_row(line: dict) -> tuple[str, list[str]] | None:
    ws = line["words"]
    i = len(ws)
    while i > 0 and NUMTOK.match(ws[i - 1]):
        i -= 1
    nums = ws[i:]
    label = " ".join(ws[:i]).strip()
    if len(nums) < 2 or not label or len(label) > 60 or not re.search(r"[A-Za-z]", label):
        return None
    return label, nums


def _headers(lines: list[dict], start: int, k: int) -> tuple[list[str], list[str], list[str]]:
    """Walk upward from the first data row; return per-column (metric, dataset, other) labels."""
    metric = dataset = None
    other: list[list[str]] = []
    j = start - 1
    while j >= 0 and start - j <= 8:
        ln = lines[j]
        if _data_row(ln) or CAPTION.match(ln["text"]) or len(ln["words"]) > 40:
            break
        cells = ln["cells"]
        if len(cells) == k + 1:  # leading row-label header cell ("Method")
            cells = cells[1:]
        n = len(cells)
        if n >= 2 and k % n == 0 and not any(NUMTOK.match(c) for c in cells):
            cols = [cells[c // (k // n)] for c in range(k)]
            if metric is None and sum(bool(METRIC.match(c)) for c in cells) * 2 >= n:
                metric = cols
            elif dataset is None and sum(bool(DATASET.search(c)) for c in cells) * 2 >= n:
                dataset = cols
            else:
                other.append(cols)
        j -= 1
    return metric or [], dataset or [""] * k, [" / ".join(o[c] for o in other) for c in range(k)] if other else [""] * k


def extract_pages(pages) -> dict:
    """pages: iterable of pymupdf pages (consumed one at a time)."""
    return extract_lines((_lines(p) for p in pages))


def extract_lines(pages_lines) -> dict:
    """pages_lines: iterable (per page) of line dicts {y, words, cells, text}."""
    configs: dict[tuple, str] = {}
    datasets: dict[str, str] = {}
    exps: dict[str, str] = {}
    caps_text: dict[str, str] = {}
    results: list[dict] = []
    section = ""
    for pno, lines in enumerate(pages_lines, 1):
        caps = [(ln["y"], CAPTION.match(ln["text"]).group(1), ln["text"]) for ln in lines if CAPTION.match(ln["text"])]
        prev_row = -10
        hdr = None
        for i, ln in enumerate(lines):
            if len(ln["text"]) < 60 and SECTION.match(ln["text"]):
                section = SECTION.match(ln["text"]).group(1).title()
            dr = _data_row(ln)
            if not dr:
                continue
            label, nums = dr
            k = len(nums)
            if hdr is None or hdr[0] != k or i - prev_row > 4:
                hdr = (k, *_headers(lines, i, k))
            prev_row = i
            _, mets, dss, oth = hdr
            if len(mets) != k:
                continue
            tab, ctext = "", ""
            if caps:
                y, tab, ctext = min(caps, key=lambda c: abs(c[0] - ln["y"]))
            caps_text.setdefault(tab or "Table ?", ctext)
            for c in range(k):
                ck = (label, oth[c])
                cid = configs.setdefault(ck, f"C{len(configs) + 1:02d}")
                dn = dss[c]
                did = datasets.setdefault(dn, f"DS{len(datasets) + 1}") if dn else ""
                eid = exps.setdefault(tab or "Table ?", f"E{len(exps) + 1}")
                results.append({
                    "experiment_id": eid, "config_id": cid, "dataset_id": did, "task_id": "", "metric_group": "",
                    "metric_name": mets[c], "metric_variant": "", "metric_direction": "", "metric_k": "",
                    "raw_value": nums[c], "raw_unit": "%" if nums[c].endswith("%") else "", "baseline_value": "",
                    "aggregation": "", "sample_size": "", "result_origin": "primary", "cited_ref": "",
                    "source_page": pno, "source_section": section, "source_table": tab, "source_figure": "",
                    "source_fragment": ln["text"], "extraction_status": "extracted",
                    "note": "local rule-based extraction"})
    return {"configs": configs, "datasets": datasets, "exps": exps, "caps": caps_text, "results": results}


def build_cache(n: int, first: str, full: str, ex: dict, mode: str, is_scan: bool) -> dict:
    lines = [x.strip() for x in first.splitlines() if x.strip()]
    doi = re.search(r"10\.\d{4,9}/[^\s,;]+", first)
    year = re.search(r"\b(?:19|20)\d{2}\b", first)
    hits = len(re.findall(r"(?i)retriev|\bRAG\b", full))
    low = full.lower()
    kws = [k for k in SCOPE_KW if re.search(r"(?<![a-z])" + re.escape(k) + ("" if k == "retriev" else "(?![a-z])"), low)]
    in_scope = hits >= 8 and (len(kws) >= 3 or "rag" in kws or "retrieval-augmented generation" in kws)
    one = lambda vals: vals.pop() if len(set(vals)) == 1 else ""
    topk = one([m.group(1) or m.group(2) for m in RX_TOPK.finditer(full)])
    ch = [(m.group(1) or m.group(3), (m.group(2) or m.group(4)).lower().rstrip("s") + "s") for m in RX_CHUNK.finditer(full)]
    chunk = ch[0] if len(set(ch)) == 1 else ("", "")
    over = one([m.group(1) for m in RX_OVER.finditer(full)])
    meths = [k for k, rx in METH.items() if re.search(rx, low)]
    lat = []
    for m in RX_LAT.finditer(full):
        v = float(m.group(1)) * (1000 if m.group(2).lower() in ("s", "sec", "second", "seconds") else 1)
        lat.append(format(v, "g"))
    latency = one(lat)
    tpq = one([m.group(1).replace(",", "") for m in RX_TOK.finditer(full)])
    for name, rx in KNOWN_DS.items():
        if len(re.findall(rx, full, re.I)) >= 2:
            ex["datasets"].setdefault(name, f"DS{len(ex['datasets']) + 1}")
    z = {c: "" for c in ("rag_variant retrieval_method retriever_model embedding_model embedding_version chunking_method "
                         "chunk_size chunk_overlap chunk_unit index_type vector_store top_k reranker_model generator_model "
                         "generator_version prompt_strategy context_strategy note").split()}
    meta = {"publication": {"title": " ".join(lines[2:4]) if len(lines) > 3 else "", "year": year.group(0) if year else "",
                            "doi": doi.group(0).rstrip(".") if doi else "", "authors": "", "in_scope": in_scope,
                            "exclusion_reason": "" if in_scope else "Local heuristic: few retrieval/RAG mentions or no result tables found"},
            "configurations": [], "datasets": [], "tasks": [], "experiments": [], "issues": []}
    if in_scope:
        for (label, oth), cid in ex["configs"].items():
            meta["configurations"].append({**z, "config_id": cid, "rag_variant": label, "generator_model": oth, "top_k": topk, "chunk_size": chunk[0],
                                           "chunk_unit": chunk[1] if chunk[0] else "", "chunk_overlap": over,
                                           "retrieval_method": meths[0] if len(meths) == 1 else "",
                                           "note": "local rule-based extraction"})
        for name, did in ex["datasets"].items():
            meta["datasets"].append({"dataset_id": did, "dataset_name": name, "dataset_version": "", "language": "",
                                     "data_split": "", "scientific_domain": "", "note": ""})
        for tab, eid in ex["exps"].items():
            meta["experiments"].append({"experiment_id": eid, "evaluation_protocol": ex["caps"].get(tab, ""), "baseline_name": "",
                                        "hardware": "", "latency_ms": latency, "tokens_per_query": tpq, "sample_size": "",
                                        "note": tab})
    cache = {"version": CACHE_VERSION, "n_pages": n, "is_scan": is_scan, "mode": mode, "window": n, "complete": True,
             "meta": meta, "windows": {f"1-{n}": {"results": ex["results"] if in_scope else []}}}
    return cache


def process_local(pdf: pathlib.Path, cache_dir: pathlib.Path, force: bool, skip_scans: bool) -> tuple[bool | None, str]:
    import pymupdf

    doc_id = pdf.stem
    old = {} if force else load_cache(cache_dir, doc_id)
    if old.get("complete") and old.get("mode") in ("local", "ocr_json") and old.get("version") == CACHE_VERSION:
        return True, "cached"
    t0 = time.time()
    try:
        with pymupdf.open(pdf) as doc:
            n = len(doc)
            texts = [p.get_text() or "" for p in doc]
            with_text = sum(len(t.strip()) >= MIN_CHARS_PER_TEXT_PAGE for t in texts)
            if n == 0:
                return False, "PDF has 0 pages"
            if with_text < max(1, int(0.9 * n)):
                return None, "SKIPPED_SCAN (no text layer; local mode never uses OCR)"
            first = texts[0]
            full = "\n".join(texts)
            ex = extract_pages(doc)
        del texts
    except Exception as exc:  # noqa: BLE001
        return False, f"cannot read PDF: {type(exc).__name__}: {exc}"
    cache = build_cache(n, first, full, ex, "local", False)
    save_cache(cache_dir, doc_id, cache)
    gc.collect()
    return True, f"{len(ex['results'])} raw result rows, in_scope={cache['meta']['publication']['in_scope']}, {time.time() - t0:.1f}s"
