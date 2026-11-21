"""Build the 7 submission CSVs from cache/<doc_id>.json (stdlib csv only) and run
deterministic validation. Rows are never deleted because of a validation finding; findings
become rows of issues.csv. Rows that cannot satisfy the format (no valid page / locator)
are dropped with an explicit log line."""
from __future__ import annotations

import csv
import json
import pathlib
import re
import unicodedata
from collections import defaultdict
from decimal import Decimal, InvalidOperation

SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[2] / "submission_template" / "schema.json"
TABLES = ["publications", "configurations", "datasets", "tasks", "experiments", "results", "issues"]
DIRECTIONS = {"higher_is_better", "lower_is_better", "target"}
BOUNDED = re.compile(
    r"(?i)^(accuracy|acc|precision|recall|f1|f-?score|exact match|em|hit(?:s|\s*rate)?|mrr|ndcg|map|"
    r"faithfulness|answer relevan\w*|context (?:precision|recall|relevan\w*)|correctness)(?:\s*@\s*\d+)?$")
LOWER = re.compile(r"(?i)latency|loss|error|perplexity|hallucination|cost|time|tokens|wer\b|cer\b|memory")
HIGHER = re.compile(r"(?i)accuracy|\bacc\b|exact match|\bem\b|f1|f-?score|precision|recall|hit|mrr|ndcg|\bmap\b|"
                    r"rouge|bleu|faithfulness|relevan|correctness|win rate")
DELTA = re.compile(r"(?i)delta|Δ|improv|gain|change|increase|decrease|drop|diff|reduc|speedup")
NUM = re.compile(r"^[≈~]?\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?:%|±.*|\+/-.*)?$")


def columns() -> dict[str, list[str]]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["tables"]


def norm(text: str) -> str:
    """Same normalization as tools/check_submission.py (NFKC, dehyphenation, spaces)."""
    text = unicodedata.normalize("NFKC", text).replace("­", "")
    text = re.sub(r"(?<=\w)-\s*\r?\n\s*(?=\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_num(raw: str) -> str | None:
    s = unicodedata.normalize("NFKC", raw or "").replace("−", "-").strip()
    s = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", s)
    m = NUM.match(s)
    if not m:
        return None
    n = m.group(1).lstrip("+")
    if n.startswith("."):
        n = "0" + n
    elif n.startswith("-."):
        n = "-0" + n[1:]
    if n.endswith("."):
        n = n[:-1]
    return n


def to_bool(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in {"true", "1", "yes", "y"}
    return bool(v)


def to_page(v) -> int:
    if isinstance(v, bool):
        return 0
    if isinstance(v, int):
        return v
    m = re.fullmatch(r"\s*(\d+)\s*", str(v or ""))
    return int(m.group(1)) if m else 0


def stub_publication(doc_id: str) -> dict:
    return {"publication_id": doc_id, "title": doc_id, "year": "", "DOI": "", "authors": "", "in_scope": "false",
            "exclusion_reason": "Unprocessed: no scope decision"}


def as_int(v: str) -> str | None:
    v = (v or "").strip().replace(",", "")
    return v if re.fullmatch(r"\d+", v) else None


def as_num(v: str) -> str | None:
    n = parse_num(v) if v else None
    return n if n is not None and not n.startswith("-") else None


def _compact(t: str) -> str:
    return re.sub(r"[\s\-\u2010\u2011\u2012\u2013\u2212]+", "", t)


def ground(frag: str, page: int, pages_norm: list[str]) -> tuple[str, int, str]:
    """Return (fragment, page, status) status in ok|moved|repaired|unverified."""
    f = norm(frag)
    if not f:
        return frag, page, "ok"
    if 1 <= page <= len(pages_norm) and f in pages_norm[page - 1]:
        return frag, page, "ok"
    for i, t in enumerate(pages_norm):
        if f in t:
            return frag, i + 1, "moved"
    fc = _compact(f)
    if len(fc) >= 6:
        order = ([page - 1] if 1 <= page <= len(pages_norm) else []) + [i for i in range(len(pages_norm)) if i != page - 1]
        for i in order:
            t = pages_norm[i]
            tc = _compact(t)
            j = tc.find(fc)
            if j >= 0:
                # map the compact hit back to an exact substring of the page text (checker matches verbatim after norm)
                idx = [k for k, ch in enumerate(t) if not ch.isspace() and ch not in "-\u2010\u2011\u2012\u2013\u2212"]
                a, b = idx[j], idx[j + len(fc) - 1] + 1
                return t[a:b], i + 1, "repaired" if i == page - 1 else "moved"
    if len(f) >= 15 and 1 <= page <= len(pages_norm):
        try:
            from rapidfuzz import fuzz

            al = fuzz.partial_ratio_alignment(f, pages_norm[page - 1], score_cutoff=92)
            if al is not None:
                return pages_norm[page - 1][al.dest_start:al.dest_end], page, "repaired"
        except ImportError:
            pass
    return frag, page, "unverified"


def _subfragment(frag: str, raw: str, page: int, pages_norm: list[str]) -> tuple[str, int] | None:
    """Longest verbatim window of the quote's words around raw_value that exists on the page."""
    words = norm(frag).split(" ")
    rv = norm(raw)
    if not rv or not 1 <= page <= len(pages_norm):
        return None
    pos = [i for i, w in enumerate(words) if rv in w]
    if not pos:
        return None
    text = pages_norm[page - 1]
    best = None
    for L in range(len(words), 0, -1):
        for a in range(max(0, pos[0] - L + 1), min(pos[0], len(words) - L) + 1):
            cand = " ".join(words[a:a + L])
            if rv in cand and cand in text:
                return cand, page
    return best


def strip_names(variant: str, *names: str) -> str:
    """Remove generator/retriever names (and 'with/using/+/()' glue) from a rag_variant."""
    v = (variant or "").strip()
    for nm in sorted({x.strip() for x in names if x and x.strip()}, key=len, reverse=True):
        v2 = re.sub(r"[\s(\[,;:+/&-]*(?:with|using|w/|on|over|\+)?[\s(\[]*" + re.escape(nm) + r"[\s)\]]*", " ", v, flags=re.I).strip(" -+,;:/()[]")
        if v2:
            v = re.sub(r"\s+", " ", v2)
    return v


def canon_space(t: str) -> str:
    t = re.sub(r"\[?模型名称已隐藏\]?", "GPT", t or "")  # masked vendor token in some PDF text layers
    return re.sub(r"\s+", " ", t.replace("\u00a0", " ")).strip()


def canon_metric(name: str) -> str:
    """'nDCG @ 5' -> 'nDCG@5'; collapse whitespace; keep the paper's casing."""
    return re.sub(r"\s*@\s*(?=\d)", "@", canon_space(name))


def k_from_name(name: str) -> str:
    """k of an @k metric ('NDCG@5' -> '5'); a fractional threshold (OC@0.8) is not k."""
    m = re.search(r"@(\d+)(?![\d.]*\d)(?!\.\d)", name)
    return m.group(1) if m else ""


def iter_results(cache: dict):
    for wkey in sorted(cache["windows"], key=lambda k: int(k.split("-")[0])):
        yield from cache["windows"][wkey].get("results", [])
    for pg in sorted(cache.get("verify", {}), key=int):  # optional --verify-pass recoveries
        yield from cache["verify"][pg].get("results", [])


def _hint(r: dict) -> str:
    return canon_space(" ".join(r.get(k, "") for k in ("source_fragment", "source_table", "source_section",
                                                       "metric_variant", "note"))).lower()


def _unique_best(cands: list[tuple[int, str]]) -> str:
    if not cands:
        return ""
    cands.sort(reverse=True)
    top = [c for sc, c in cands if sc == cands[0][0]]
    return top[0] if len(set(top)) == 1 else ""


def _fill_ids(rows: list[dict], out: dict) -> None:
    """Fill blank ids of primary results: (1) single entity of a kind; (2) table named in one experiment's
    protocol; (3) config/dataset by name match in the row's own quote/table text; (4) experiment/task
    inherited from the same source_table when every labelled row of that table agrees."""
    only = {k: out[t][0][k] for t, k in (("experiments", "experiment_id"), ("configurations", "config_id"),
                                          ("datasets", "dataset_id"), ("tasks", "task_id")) if len(out[t]) == 1}
    for r in rows:
        if r["result_origin"] != "primary":
            continue
        tb = canon_space(r["source_table"]).lower()
        if not r["experiment_id"] and tb:
            hit = [e["experiment_id"] for e in out["experiments"]
                   if re.search(r"\b" + re.escape(tb) + r"\b(?!\d)", (e.get("evaluation_protocol") or "").lower())]
            if len(hit) == 1:
                r["experiment_id"] = hit[0]
        h = _hint(r)
        if not r["config_id"] and h:
            cands = []
            for c in out["configurations"]:
                v, g = canon_space(c["rag_variant"]).lower(), canon_space(c["generator_model"]).lower()
                if len(v) >= 3 and v in h and (not g or g in h):
                    cands.append((len(v) + len(g), c["config_id"]))
            r["config_id"] = _unique_best(cands)
        if not r["dataset_id"] and h:
            r["dataset_id"] = _unique_best([(len(n), d["dataset_id"]) for d in out["datasets"]
                                            if len(n := canon_space(d["dataset_name"]).lower()) >= 3 and n in h])
    by_tab: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for r in rows:
        tb = canon_space(r["source_table"]).lower()
        if tb:
            for k in ("experiment_id", "task_id"):
                if r[k]:
                    by_tab[tb][k].add(r[k])
    for r in rows:
        if r["result_origin"] != "primary":
            continue
        tb = canon_space(r["source_table"]).lower()
        for k in ("experiment_id", "task_id"):
            if not r[k] and tb and len(by_tab[tb][k]) == 1:
                r[k] = next(iter(by_tab[tb][k]))
        for k, v in only.items():
            if not r[k]:
                r[k] = v


def build_doc(doc_id: str, cache: dict, pages_norm: list[str] | None, log) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {t: [] for t in TABLES}
    meta = cache["meta"]
    p = meta["publication"]
    year = (re.search(r"(?:19|20)\d{2}", p.get("year", "")) or [""])[0]
    doi = re.sub(r"(?i)^(https?://(dx\.)?doi\.org/|doi:\s*)", "", p.get("doi", "").strip())
    in_scope = to_bool(p.get("in_scope"))
    out["publications"].append({
        "publication_id": doc_id, "title": p.get("title", "").strip(), "year": year, "DOI": doi,
        "authors": p.get("authors", "").strip(), "in_scope": "true" if in_scope else "false",
        "exclusion_reason": "" if in_scope else (p.get("exclusion_reason", "").strip() or "Out of scope: not a RAG system evaluation"),
    })
    if not in_scope:
        return out

    dup_ids: set[str] = set()

    def uniq_ids(items: list[dict], key: str, prefix: str) -> set[str]:
        """Duplicates/empty ids get fresh ids that collide with NO declared id; the first holder keeps
        the original id, so references in results keep pointing at it (ambiguous ones are noted)."""
        declared = {(it.get(key) or "").strip() for it in items}
        seen: set[str] = set()
        n = 0
        for it in items:
            v = (it.get(key) or "").strip()
            if not v or v in seen:
                if v:
                    dup_ids.add(f"{key}:{v}")
                while f"{prefix}{n + 1}" in declared or f"{prefix}{n + 1}" in seen:
                    n += 1
                n += 1
                v = f"{prefix}{n}"
            it[key] = v
            seen.add(v)
        return seen

    def num_fields(row: dict, spec: dict) -> None:
        extra = []
        for k, fn in spec.items():
            raw = (row.get(k) or "").strip()
            if not raw:
                row[k] = ""
                continue
            val = fn(raw)
            if val is None:
                extra.append(f"{k}: {raw}")
            row[k] = val or ""
        if extra:
            row["note"] = (row.get("note", "") + " | " if row.get("note") else "") + "; ".join(extra)

    idmap: dict[str, dict[str, str]] = {k: {} for k in ("config_id", "dataset_id", "task_id", "experiment_id")}

    def merge_entities(items: list[dict], key: str) -> list[dict]:
        """Drop later entities identical (ignoring id/note, case/space-insensitive) to an earlier one; map their ids."""
        seen: dict[tuple, str] = {}
        out_: list[dict] = []
        for it in items:
            sig = tuple(sorted((k, re.sub(r"\s+", " ", str(v or "")).strip().lower()) for k, v in it.items()
                               if k not in (key, "note", "publication_id")))
            vid = (it.get(key) or "").strip()
            if sig in seen and any(v for _, v in sig):
                if vid:
                    idmap[key].setdefault(vid, seen[sig])
                continue
            seen[sig] = vid
            out_.append(it)
        return out_

    cfg_in = [dict(c) for c in meta["configurations"]]
    for c in cfg_in:
        for f in ("generator_model", "retriever_model", "embedding_model", "reranker_model"):
            c[f] = canon_space(c.get(f, ""))
        c["rag_variant"] = strip_names(canon_space(c.get("rag_variant", "")), c.get("generator_model", ""), c.get("retriever_model", ""))
    cfgs = merge_entities(cfg_in, "config_id")
    dss = merge_entities([dict(d, dataset_name=canon_space(d.get("dataset_name", ""))) for d in meta["datasets"]], "dataset_id")
    tks = merge_entities([dict(t) for t in meta["tasks"]], "task_id")
    exs = merge_entities([dict(e) for e in meta["experiments"]], "experiment_id")
    cset = uniq_ids(cfgs, "config_id", "C")
    dset = uniq_ids(dss, "dataset_id", "DS")
    tset = uniq_ids(tks, "task_id", "T")
    eset = uniq_ids(exs, "experiment_id", "E")
    for c in cfgs:
        num_fields(c, {"chunk_size": as_int, "chunk_overlap": as_int, "top_k": as_int})
    for e in exs:
        num_fields(e, {"latency_ms": as_num, "tokens_per_query": as_num, "sample_size": as_int})
    for tab, items in (("configurations", cfgs), ("datasets", dss), ("tasks", tks), ("experiments", exs)):
        cols = columns()[tab]
        for it in items:
            out[tab].append({c: (it.get(c, "") or "").strip() if c != "publication_id" else doc_id for c in cols})

    # ---- results ----
    n_pages = cache.get("n_pages", 0)
    rows: list[dict] = []
    drops = defaultdict(int)
    fstat = defaultdict(int)
    nonnum: list[dict] = []
    for r in iter_results(cache):
        if True:
            note = (r.get("note") or "").strip()
            name = canon_metric(r.get("metric_name") or "")
            if not name:
                drops["no metric_name"] += 1
                continue
            page = to_page(r.get("source_page"))
            if not 1 <= page <= n_pages:
                drops["invalid source_page"] += 1
                continue
            row = {c: "" for c in columns()["results"]}
            row.update(publication_id=doc_id, metric_name=name, source_page=str(page))
            for k in ("metric_group", "metric_variant", "aggregation", "source_section", "source_table",
                      "source_figure", "source_fragment"):
                row[k] = (r.get(k) or "").strip()
            for k, valid in (("experiment_id", eset), ("config_id", cset), ("dataset_id", dset), ("task_id", tset)):
                v = (r.get(k) or "").strip()
                v = idmap[k].get(v, v) if v not in valid else v
                if v and f"{k}:{v}" in dup_ids:
                    note = (note + " | " if note else "") + f"ambiguous {k} '{v}' (duplicated in paper entities)"
                if v and v not in valid:
                    note = (note + " | " if note else "") + f"unresolved {k} '{v}' removed"
                    v = ""
                row[k] = v
            status = (r.get("extraction_status") or "extracted").strip()
            status = status if status in {"extracted", "present_not_extractable", "absent"} else "extracted"
            raw = (r.get("raw_value") or "").strip()
            raw_unit = (r.get("raw_unit") or "").strip()
            if status == "extracted" and not raw:
                status = "absent"
            if status == "extracted" and not (row["source_fragment"] or row["source_table"] or row["source_figure"]):
                drops["extracted without locator"] += 1
                continue
            origin = (r.get("result_origin") or "primary").strip()
            cref = (r.get("cited_ref") or "").strip()
            if origin != "cited" and cref:
                origin = "cited"
            if origin == "cited":
                cref = cref or "unspecified"
            else:
                origin, cref = "primary", ""
            sample = as_int(r.get("sample_size") or "")
            if (r.get("sample_size") or "").strip() and sample is None:
                note = (note + " | " if note else "") + f"sample_size: {r['sample_size'].strip()}"
            k = (r.get("metric_k") or "").strip()
            k = as_int(k) or k_from_name(name)
            direction = (r.get("metric_direction") or "").strip()
            if direction not in DIRECTIONS:
                direction = "lower_is_better" if LOWER.search(name) else ("higher_is_better" if HIGHER.search(name) else "")
            value, unit = "", ""
            if status == "extracted":
                value = parse_num(raw) or ""
                if not value:
                    note = (note + " | " if note else "") + "numeric value not parsed from raw_value (range/text)"
                else:
                    ru = raw_unit.lower()
                    if "%" in raw or raw_unit == "%":
                        unit = "%"
                    elif ru in {"s", "sec", "secs", "second", "seconds"}:
                        value = format((Decimal(value) * 1000).normalize(), "f")
                        unit = "ms"
                        note = (note + " | " if note else "") + "converted from seconds"
                    elif raw_unit:
                        unit = raw_unit
                    elif BOUNDED.match(name) and 0 <= Decimal(value) <= 1:
                        unit = "fraction"
            bl = (r.get("baseline_value") or "").strip()
            blv = parse_num(bl) if bl else ""
            if bl and blv is None:
                note = (note + " | " if note else "") + f"baseline_value: {bl}"
            frag, fpage = row["source_fragment"], page
            if pages_norm is not None and frag:
                frag, fpage, st = ground(frag, page, pages_norm)
                fstat[st] += 1
                if st == "unverified":
                    sub = _subfragment(frag, raw, page, pages_norm)
                    if sub:
                        frag, fpage = sub
                    else:
                        note = (note + " | " if note else "") + "quote not verified in text layer"
                        if row["source_table"] or row["source_figure"]:
                            frag = ""  # keep a table/figure locator instead of an unverifiable quote
            if status == "extracted" and not value:
                drops["non-numeric metric_value (routed to issues.csv)"] += 1
                nonnum.append({"page": str(page), "name": name, "raw": raw, "frag": row["source_fragment"], "note": note})
                continue
            row.update(metric_direction=direction, metric_k=k, metric_value=value, metric_unit=unit,
                       baseline_value=blv or "", sample_size=sample or "", raw_value=raw, raw_unit=raw_unit,
                       normalized_value=value, normalized_unit=unit, result_origin=origin,
                       cited_publication_id=cref, source_page=str(fpage), source_fragment=frag,
                       extraction_status=status, note=note)
            rows.append(row)
    _fill_ids(rows, out)
    if len(nonnum) > 40:  # keep issues.csv readable: group the rest per page
        by_page: dict[str, list[dict]] = defaultdict(list)
        for x in nonnum[40:]:
            by_page[x["page"]].append(x)
        nonnum = nonnum[:40] + [{"page": pg, "name": "; ".join(sorted({y["name"] for y in xs}))[:200],
                                 "raw": f"{len(xs)} qualitative values", "frag": xs[0]["frag"], "note": ""}
                                for pg, xs in by_page.items()]
    if fstat:
        log(f"  {doc_id}: quote check {dict(fstat)}")
    for why, n in drops.items():
        log(f"  {doc_id}: dropped {n} result rows ({why})")

    # ---- duplicates / contradictions ----
    groups: dict[tuple, list[dict]] = defaultdict(list)
    keep: list[dict] = []
    for r in rows:
        if r["extraction_status"] == "extracted" and r["metric_value"] and r["experiment_id"] and r["config_id"] and r["dataset_id"]:
            key = tuple(r[c] for c in ("experiment_id", "config_id", "dataset_id", "task_id", "metric_name", "metric_variant",
                                        "metric_k", "metric_unit", "aggregation", "sample_size", "result_origin",
                                        "cited_publication_id"))
            first = groups[key][0] if groups[key] else None
            loc = (r["source_page"], r["source_table"], r["source_fragment"])
            if first is not None and any(loc == (g["source_page"], g["source_table"], g["source_fragment"]) and
                                         r["metric_value"] == g["metric_value"] for g in groups[key]):
                drops["repeat of same extraction"] += 1
                continue
            groups[key].append(r)
        keep.append(r)
    rows = keep
    if drops.get("repeat of same extraction"):
        log(f"  {doc_id}: dropped {drops['repeat of same extraction']} repeated rows (same value, same location)")
    for i, r in enumerate(rows, 1):
        r["result_id"] = f"R{i:03d}"
    issues: list[dict] = []
    for g in groups.values():
        base = g[0]
        for r in g[1:]:
            try:
                same = Decimal(r["metric_value"]) == Decimal(base["metric_value"])
            except InvalidOperation:
                same = False
            if same:
                r["duplicate_of"] = base["result_id"]
            else:
                issues.append({"check_name": "contradiction", "record_ids": f"{base['result_id']};{r['result_id']}",
                               "description": f"{base['metric_name']}: {base['metric_value']} (p.{base['source_page']}) vs "
                                              f"{r['metric_value']} (p.{r['source_page']}) for the same experiment/configuration/dataset; both kept.",
                               "source_page": r["source_page"], "source_fragment": r["source_fragment"]})
    # ---- deterministic checks ----
    pp = defaultdict(list)
    for r in rows:
        v = r["metric_value"]
        if v and not DELTA.search(r["metric_name"]) and (BOUNDED.match(r["metric_name"]) or r["metric_unit"] in ("fraction", "%")):
            x = Decimal(v)
            lim = {"fraction": 1, "%": 100}.get(r["metric_unit"])
            if lim is not None and not 0 <= x <= lim:
                issues.append({"check_name": "metric_scale", "record_ids": r["result_id"],
                               "description": f"{r['metric_name']}={v} {r['metric_unit']} is outside the declared scale [0, {lim}]; value preserved.",
                               "source_page": r["source_page"], "source_fragment": r["source_fragment"]})
            elif lim is None and not r["metric_unit"] and x > 1:
                issues.append({"check_name": "metric_scale", "record_ids": r["result_id"],
                               "description": f"{r['metric_name']}={v} has no stated unit and exceeds 1: scale ([0,1] vs [0,100%]) is not declared; not converted.",
                               "source_page": r["source_page"], "source_fragment": r["source_fragment"]})
        if re.search(r"@\s*\d", r["metric_name"]) and not r["metric_k"]:
            issues.append({"check_name": "metric_k", "record_ids": r["result_id"],
                           "description": f"{r['metric_name']} looks like an @k metric but no integer k could be determined.",
                           "source_page": r["source_page"], "source_fragment": r["source_fragment"]})
        if v and r["metric_unit"] == "%" and DELTA.search(r["metric_name"]):
            pp[r["source_page"]].append(r)
    topk = {c["config_id"]: c["top_k"] for c in out["configurations"] if c["top_k"]}
    for r in rows:
        tk, mk = topk.get(r["config_id"], ""), r["metric_k"]
        if tk and mk and int(mk) > int(tk) and r["extraction_status"] == "extracted":
            issues.append({"check_name": "metric_k_gt_top_k", "record_ids": r["result_id"],
                           "description": f"{r['metric_name']}: metric_k={mk} > top_k={tk} of the configuration; check the retrieval/reranker stage that metric_k refers to.",
                           "source_page": r["source_page"], "source_fragment": r["source_fragment"]})
    for page, rs in pp.items():
        issues.append({"check_name": "percentage_vs_percentage_point", "record_ids": ";".join(x["result_id"] for x in rs),
                       "description": "Difference-type metrics are labeled with % in the source; it is not established whether they are relative "
                                      "percent or percentage points. Original unit retained, no conversion.",
                       "source_page": page, "source_fragment": rs[0]["source_fragment"]})
    for x in nonnum:
        issues.append({"check_name": "non_numeric_result", "record_ids": "",
                       "description": f"Qualitative/non-numeric finding not stored as a result: {x['name']} = '{x['raw']}'"
                                      + (f" ({x['note']})" if x["note"] else ""),
                       "source_page": x["page"], "source_fragment": x["frag"]})
    for mi in meta.get("issues", []):
        pg = to_page(mi.get("source_page"))
        pg = str(pg) if 1 <= pg <= n_pages else ""
        issues.append({"check_name": (mi.get("check_name") or "contradiction").strip(), "record_ids": "",
                       "description": (mi.get("description") or "").strip(), "source_page": pg,
                       "source_fragment": (mi.get("source_fragment") or "").strip() if pg else ""})
    for i, it in enumerate(issues, 1):
        row = {c: "" for c in columns()["issues"]}
        row.update(it, publication_id=doc_id, issue_id=f"I{i:02d}")
        out["issues"].append(row)
    out["results"] = rows
    for r in rows:
        r["publication_id"] = doc_id
    return out


class TableWriter:
    """Streaming CSV writer: one document at a time, files written as *.tmp and committed on close(True)."""

    def __init__(self, out_dir: pathlib.Path) -> None:
        self.dir = pathlib.Path(out_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        cols = columns()
        self.files, self.writers, self.counts = {}, {}, {t: 0 for t in TABLES}
        for t in TABLES:
            f = (self.dir / f"{t}.csv.tmp").open("w", encoding="utf-8", newline="")
            w = csv.DictWriter(f, fieldnames=cols[t], lineterminator="\n", extrasaction="ignore")
            w.writeheader()
            self.files[t], self.writers[t] = f, w

    def write_doc(self, doc: dict[str, list[dict]]) -> None:
        for t in TABLES:
            self.writers[t].writerows(doc.get(t, []))
            self.counts[t] += len(doc.get(t, []))

    def close(self, commit: bool) -> None:
        import os

        for t in TABLES:
            self.files[t].close()
            tmp = self.dir / f"{t}.csv.tmp"
            if commit:
                os.replace(tmp, self.dir / f"{t}.csv")
            else:
                tmp.unlink(missing_ok=True)
