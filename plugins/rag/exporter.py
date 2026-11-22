"""Build the seven submission CSVs from cached extraction and report validation findings."""
from __future__ import annotations

import csv
import pathlib
import re
import unicodedata
from collections import defaultdict
from decimal import Decimal
from itertools import chain
from typing import get_args

from core.validator import RULE_PROVENANCE_COMPLETE, check_result, finding
from domains.base_schema import ExtractionStatus
from domains.rag.schema import MetricDirection
from domains.rag.submission import SUBMISSION_MODELS, submission_row
from plugins.rag.table_context import dataset_aliases, identity_label, label, mentions_identity, native_captions

TABLES = tuple(SUBMISSION_MODELS)
DIRECTIONS = frozenset(get_args(MetricDirection))
STATUSES = frozenset(get_args(ExtractionStatus))
BOUNDED = re.compile(
    r"(?i)^(accuracy|acc|precision|recall|f1|f-?score|exact match|em|hit(?:s|\s*rate)?|mrr|ndcg|map|"
    r"faithfulness|answer relevan\w*|context (?:precision|recall|relevan\w*)|correctness)(?:\s*@\s*\d+)?$")
LOWER = re.compile(r"(?i)latency|loss|error|perplexity|hallucination|cost|time|tokens|wer\b|cer\b|memory")
HIGHER = re.compile(r"(?i)accuracy|\bacc\b|exact match|\bem\b|f1|f-?score|precision|recall|hit|mrr|ndcg|\bmap\b|"
                    r"rouge|bleu|faithfulness|relevan|correctness|win rate")
DELTA = re.compile(r"(?i)delta|Δ|improv|gain|change|increase|decrease|drop|diff|reduc|speedup")
NUM = re.compile(r"^[≈~]?\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?:%|±.*|\+/-.*)?$")


def columns() -> dict[str, list[str]]:
    return {table: list(model.model_fields) for table, model in SUBMISSION_MODELS.items()}


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


def _ground_ocr(frag: str, raw: str, page_text: str) -> tuple[str, str]:
    """Only accept same-page text. A shorter quote must keep the metric's literal number and context."""
    quote = norm(frag)
    raw = norm(raw)
    value = re.compile(rf"(?<![\w.+−-]){re.escape(raw)}(?![\w.%])")
    if raw and (literal := value.search(quote)):
        exact = re.escape(quote[:literal.start()]) + value.pattern + re.escape(quote[literal.end():])
        if re.search(exact, page_text):
            return frag, "ok"
    elif quote and quote in page_text:
        return frag, "ok"
    if not raw or not re.search(r"\d", raw):
        return frag, "unverified"
    words = quote.split()
    for size in range(len(words) - 1, 1, -1):
        for first in range(len(words) - size + 1):
            candidate = " ".join(words[first:first + size])
            if (literal := value.search(candidate)) and any(c.isalpha() for c in candidate) and candidate in page_text:
                exact = re.escape(candidate[:literal.start()]) + value.pattern + re.escape(candidate[literal.end():])
                if re.search(exact, page_text):
                    return candidate, "repaired"
    return frag, "unverified"


def strip_names(variant: str, *names: str) -> str:
    """Remove generator/retriever names (and 'with/using/+/()' glue) from a rag_variant."""
    v = (variant or "").strip()
    for nm in sorted({x.strip() for x in names if x and x.strip()}, key=len, reverse=True):
        v2 = re.sub(r"[\s(\[,;:+/&-]*(?:with|using|w/|on|over|\+)?[\s(\[]*(?<!\w)" + re.escape(nm)
                    + r"(?!\w)[\s)\]]*", " ", v, flags=re.I).strip(" -+,;:/()[]")
        if v2:
            v = re.sub(r"\s+", " ", v2)
    return v


def canon_space(t: str) -> str:
    t = unicodedata.normalize("NFKC", t or "")
    t = re.sub(r"\[?模型名称已隐藏\]?", "GPT", t)  # masked vendor token in some PDF text layers
    return re.sub(r"\s+", " ", re.sub(r"[‐‑‒–]", "-", t)).strip()


_MODEL_DECLARATION = re.compile(
    r"(?i)(?<![\w.-])(?P<family>[\w.-]*\d[\w.-]*)\s+model\s*"
    r"\(\s*(?P<identifier>[\w.]+(?:-[\w.]+)+)\s*\)"
)
_AUTHOR_LABEL = re.compile(r"(?i)\s*(?:\(\s*ours\s*\)|\[\s*ours\s*\])$")


def _model_parts(name: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[^\W\d_]+|\d+(?:\.\d+)*", name.casefold()))


def _model_declarations(pages_norm):
    return [(m["family"], m["identifier"]) for page in pages_norm or () for m in _MODEL_DECLARATION.finditer(page)]


def canonical_model(name: str, declarations: list[tuple[str, str]], printed_ids=()) -> str:
    """Complete an intermediate model identifier only from an explicit source declaration."""
    parts = _model_parts(name)
    if parts in printed_ids:
        return name
    matches = {}
    for family, identifier in declarations:
        base, full = _model_parts(family), _model_parts(identifier)
        if len(base) < len(parts) <= len(full) and parts[:len(base)] == base and full[:len(parts)] == parts:
            matches[full] = identifier
    return next(iter(matches.values())) if len(matches) == 1 else name


def dataset_display_name(name: str, version: str) -> str:
    """Remove an explicitly recorded version suffix from the display name."""
    version = canon_space(version)
    if not re.fullmatch(r"(?:v(?:ersion)?\s*)?\d+(?:\.\d+)*[a-z]?", version, re.I):
        return name
    suffix = re.escape(version)
    return re.sub(rf"(?:\s+{suffix}|\s*\({suffix}\)|\s*\[{suffix}\])$", "", name, flags=re.I).strip() or name


def _canonicalize_datasets(datasets: list[dict], pages_norm: list[str] | None) -> None:
    """Use a printed subset label when the paper explicitly lists the family and its members."""
    families = defaultdict(list)
    name_counts = defaultdict(int)
    for row in datasets:
        row["dataset_name"] = dataset_display_name(row["dataset_name"], row["dataset_version"])
        name = row["dataset_name"]
        name_counts[name.casefold()] += 1
        parts = re.split(r"\s+[-/]\s+", name, maxsplit=1)
        if len(parts) == 2:
            parent, child = parts
            name_counts[child.casefold()] += 1
            families[parent].append((row, child))
    for parent, members in families.items():
        if len(members) < 2 or any(name_counts[child.casefold()] != 1 for _, child in members):
            continue
        heading = re.compile(rf"(?<!\w){re.escape(parent)}\s+(?:subsets|splits|sub[- ]?corpora)\b", re.I)
        labels = [re.compile(rf"(?<!\w){re.escape(child)}(?!\w)", re.I) for _, child in members]
        if not any(all(label.search(page, found.end(), min(found.end() + 600, len(page))) for label in labels)
                   for page in pages_norm or () for found in heading.finditer(page)):
            continue
        for row, child in members:
            row["dataset_name"] = child
            row["note"] = (row["note"] + " | " if row["note"] else "") + f"Dataset family: {parent}"


def canon_metric(name: str) -> str:
    """'nDCG @ 5' -> 'nDCG@5'; collapse whitespace; keep the paper's casing."""
    return re.sub(r"\s*@\s*(?=\d)", "@", canon_space(name))


_METRIC_AT_K = re.compile(r"@\s*(\d+)(?![\w%]|[.,]\d|[-–]\d)")


def metric_identity(name: str) -> tuple[str, str]:
    """Return the underlying metric and an unambiguous explicitly printed cutoff."""
    cuts = list(_METRIC_AT_K.finditer(name))
    if len(cuts) != 1:
        return canon_metric(name), ""
    match = cuts[0]
    return canon_space(name[:match.start()] + name[match.end():]), match[1].lstrip("0") or "0"


def _passport_cutoffs(meta: dict, pages_norm: list[str] | None) -> dict:
    candidates = defaultdict(set)
    for scope in meta.get("table_scopes", []):
        number = to_page(scope.get("source_page"))
        table = label(scope.get("source_table") or "")
        if not table or not pages_norm or not 1 <= number <= len(pages_norm):
            continue
        for item in scope.get("metric_cutoffs", []):
            name, _ = metric_identity(item.get("metric_name") or "")
            fragment = norm(item.get("source_fragment") or "")
            base, cutoff = metric_identity(fragment)
            if (cutoff and cutoff == item.get("metric_k") and label(name) == label(base)
                    and fragment in pages_norm[number - 1]):
                candidates[str(number), table, label(name)].add(cutoff)
    return {key: next(iter(values)) for key, values in candidates.items() if len(values) == 1}


def _expand_metric_abbreviations(rows: list[dict], pages_norm: list[str] | None) -> None:
    """Restore one-word metric expansions only when explicitly defined in this PDF."""
    definitions = defaultdict(set)
    for page in pages_norm or ():
        for full, short in re.findall(r"\b([A-Z][a-z][a-z-]{2,})\s*\(([A-Z][A-Za-z]{1,6})\)", page):
            if full.casefold().startswith(short.casefold()):
                definitions[short.casefold()].add(full)
    for row in rows:
        original = row["metric_name"]
        possible = definitions[original.casefold()]
        if len(possible) == 1:
            row["metric_name"] = next(iter(possible))
            row["note"] = (row["note"] + " | " if row["note"] else "") + f"Printed metric abbreviation: {original}."


CUTOFF = re.compile(r"(?i)(?:@\s*|\bk\s*=\s*|\btop[-\s]*)([0-9]+)(?![\w%]|[.,]\d|[-–]\d)")


def printed_cutoffs(*labels: str) -> set[str]:
    return {m.lstrip("0") or "0" for label in labels for m in CUTOFF.findall(label)}


def k_from_name(name: str, variant: str = "") -> str:
    """Read an unambiguous integer cutoff from the metric name and variant."""
    cutoffs = printed_cutoffs(name, variant)
    return next(iter(cutoffs)) if len(cutoffs) == 1 else ""


def iter_results(cache: dict):
    for wkey in sorted(cache["windows"], key=lambda k: int(k.split("-")[0])):
        yield from cache["windows"][wkey].get("results", [])
    for pg in sorted(cache.get("verify", {}), key=int):  # optional --verify-pass recoveries
        yield from cache["verify"][pg].get("results", [])


def _unique_best(cands: list[tuple[int, str]]) -> str:
    if not cands:
        return ""
    cands.sort(reverse=True)
    top = [c for sc, c in cands if sc == cands[0][0]]
    return top[0] if len(set(top)) == 1 else ""


def _fill_ids(rows: list[dict], out: dict, captions=None, row_captions=None, pages_norm=None,
              model_aliases=None) -> None:
    """Fill missing IDs using row evidence and unambiguous local table context."""
    captions, row_captions = captions or {}, row_captions or {}
    only = {k: out[t][0][k] for t, k in (("experiments", "experiment_id"), ("configurations", "config_id"),
                                          ("datasets", "dataset_id"), ("tasks", "task_id")) if len(out[t]) == 1}
    configs = {c["config_id"]: (identity_label(c["rag_variant"]), identity_label(c["generator_model"]))
               for c in out["configurations"]}
    models = {g for _, g in configs.values() if g}
    model_names = defaultdict(set)
    for model in models:
        model_names[model].add(model)
    for short, full in (model_aliases or {}).items():
        model_names[identity_label(short)].add(identity_label(full))
    datasets = defaultdict(set)
    for d in out["datasets"]:
        datasets[identity_label(d["dataset_name"])].add(d["dataset_id"])
    for alias, ids in dataset_aliases(((d["dataset_id"], d["dataset_name"]) for d in out["datasets"]), pages_norm).items():
        datasets[identity_label(alias)].update(ids)

    def local_scope(row):
        return row["source_page"], label(row["source_table"])

    def models_in(text):
        return {model for name, candidates in model_names.items() if mentions_identity(name, text)
                for model in candidates}

    for r in rows:
        if r["result_origin"] != "primary":
            continue
        tb = canon_space(r["source_table"]).lower()
        if not r["experiment_id"] and tb:
            hit = [e["experiment_id"] for e in out["experiments"]
                   if re.search(r"\b" + re.escape(tb) + r"\b(?!\d)", (e.get("evaluation_protocol") or "").lower())]
            if len(hit) == 1:
                r["experiment_id"] = hit[0]
        quote = label(r["source_fragment"])
        cap = label(captions.get(local_scope(r)) or row_captions.get(r.get("result_id")) or "")
        stated_models = models_in(quote) or models_in(cap)
        cands = [(len(v), cid) for cid, (v, g) in configs.items() if len(v) >= 3 and mentions_identity(v, quote)
                 and (g in stated_models if len(stated_models) == 1 else not (g or stated_models))]
        config = _unique_best(cands)
        if config and not r["config_id"]:
            r["config_id"] = config
        elif config and config != r["config_id"] and len(stated_models) == 1:
            old_variant, old_model = configs[r["config_id"]]
            variant, model = configs[config]
            if old_variant == variant and old_model != model:
                r["config_id"] = config
        if not r["dataset_id"]:
            named = [(len(n), next(iter(ids))) for n, ids in datasets.items()
                     if len(n) >= 2 and len(ids) == 1 and mentions_identity(n, quote)]
            in_caption = {cid for n, ids in datasets.items() if len(n) >= 2 and mentions_identity(n, cap) for cid in ids}
            r["dataset_id"] = _unique_best(named) or (next(iter(in_caption)) if not named and len(in_caption) == 1 else "")
    by_tab = defaultdict(lambda: defaultdict(set))
    for r in rows:
        page, tb = local_scope(r)
        if tb:
            for k in ("experiment_id", "task_id", "dataset_id", "config_id"):
                if r[k]:
                    by_tab[page if k in {"dataset_id", "config_id"} else "", tb][k].add(r[k])
    for r in rows:
        if r["result_origin"] != "primary":
            continue
        page, tb = local_scope(r)
        for k in ("experiment_id", "task_id", "dataset_id"):
            ids = by_tab[page if k == "dataset_id" else "", tb][k]
            if not r[k] and tb and len(ids) == 1:
                r[k] = next(iter(ids))
        cfg_ids = by_tab[page, tb]["config_id"]
        if not r["config_id"] and tb and len(cfg_ids) == 1:
            cfg_id = next(iter(cfg_ids))
            variant, generator = configs[cfg_id]
            cap = label(captions.get(local_scope(r)) or row_captions.get(r.get("result_id")) or "")
            quote = label(r["source_fragment"])
            if (mentions_identity(variant, cap) and (not generator or models_in(cap) == {generator})
                    and not any(v != variant and mentions_identity(v, quote) for v, _ in configs.values())):
                r["config_id"] = cfg_id
        for k, v in only.items():
            if not r[k]:
                r[k] = v


def build_doc(doc_id: str, cache: dict, pages_norm: list[str] | None, log, *, table_layout=None,
              recover_table_cells: bool = False, plot_rows=()) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {t: [] for t in TABLES}
    fields = columns()
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
        names = {"generator_model", "retriever_model", "embedding_model", "reranker_model", "dataset_name"}
        for it in items:
            sig = tuple(sorted((k, identity_label(str(v or "")) if k in names else canon_space(str(v or "")).casefold())
                               for k, v in it.items()
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
    model_declarations = _model_declarations(pages_norm)
    printed_ids = {_model_parts(value) for page in pages_norm or () for value in
                   re.findall(r"(?<![\w.-])[\w.]+(?:-[\w.]+)+(?![\w-])", page) if any(c.isdigit() for c in value)}
    model_aliases = {}
    if plot_rows:
        # A generator printed on a panel is evidence for a partial configuration only.
        declared_ids = {c.get("config_id") for c in cfg_in}
        partial_by_model = {}
        sourced_rows = []
        next_id = 0
        for point in plot_rows:
            model = point.get("plot_generator")
            if model and not point.get("config_id"):
                if model not in partial_by_model:
                    next_id += 1
                    while f"PC{next_id}" in declared_ids:
                        next_id += 1
                    config_id = f"PC{next_id}"
                    partial_by_model[model] = config_id
                    cfg_in.append({"config_id": config_id, "generator_model": model,
                                   "note": "Only the generator is specified by the plot panel. Point-level retrieval settings are not identified."})
                point = dict(point, config_id=partial_by_model[model])
            sourced_rows.append(point)
        plot_rows = sourced_rows
    for c in cfg_in:
        for f in ("generator_model", "retriever_model", "embedding_model", "reranker_model"):
            c[f] = canon_space(c.get(f, ""))
        generator = c["generator_model"]
        c["generator_model"] = canonical_model(generator, model_declarations, printed_ids)
        if generator != c["generator_model"]:
            model_aliases[generator] = c["generator_model"]
        variant = canon_space(c.get("rag_variant", ""))
        variant = _AUTHOR_LABEL.sub("", variant).strip() or variant
        c["rag_variant"] = strip_names(variant, generator, c["generator_model"], c["retriever_model"])
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
        cols = fields[tab]
        for it in items:
            out[tab].append({c: (it.get(c, "") or "").strip() if c != "publication_id" else doc_id for c in cols})

    # ---- results ----
    n_pages = cache.get("n_pages", 0)
    ocr_pages_norm = pages_norm if cache.get("ocr") else None
    rows: list[dict] = []
    row_captions = {}
    scoped_cutoffs = _passport_cutoffs(meta, pages_norm)
    fstat = defaultdict(int)
    issues: list[dict] = []
    validations = []
    plot_ids = set()
    source_rows = iter_results(cache)
    cells = {}
    if table_layout:
        from plugins.rag.table_context import index_cells, recover_missing, relink

        labels = defaultdict(set)
        for dataset in out["datasets"]:
            for name in (dataset["dataset_name"], dataset_display_name(dataset["dataset_name"], dataset["dataset_version"])):
                labels[label(name)].add(dataset["dataset_id"])
        aliases = dataset_aliases(((d["dataset_id"], d["dataset_name"]) for d in out["datasets"]), pages_norm)
        for alias, ids in aliases.items():
            labels[alias].update(ids)
        known = {name: next(iter(ids)) for name, ids in labels.items() if name and len(ids) == 1}
        configurations = [(cfg["config_id"], label(cfg["rag_variant"]), label(cfg["generator_model"]))
                          for cfg in out["configurations"]]
        configurations.extend((cfg["config_id"], label(cfg["rag_variant"]), label(short))
                              for cfg in out["configurations"] for short, full in model_aliases.items()
                              if full == cfg["generator_model"])
        cached_rows = list(source_rows)
        cells = index_cells(cached_rows, table_layout, known, configurations)
        recovered = recover_missing(cached_rows, cells, pages_norm or []) if recover_table_cells else []
        if recovered:
            log(f"  {doc_id}: recovered {len(recovered)} numeric table cells from native PDF layout")
        source_rows = iter(cached_rows + recovered)
    for r in chain(source_rows, plot_rows):
        if True:
            note = (r.get("note") or "").strip()
            name = canon_metric(r.get("metric_name") or "")
            page = to_page(r.get("source_page"))
            page = page if 1 <= page <= n_pages else 0
            if not name:
                evidence = {"source_page": str(page or ""), "source_fragment": (r.get("source_fragment") or "").strip() if page else ""}
                issues.append(finding(evidence, RULE_PROVENANCE_COMPLETE,
                                      f"Cached observation has no metric name; raw value was {r.get('raw_value', '')!r}."))
                continue
            row = dict.fromkeys(fields["results"], "")
            row.update(publication_id=doc_id, result_id=f"R{len(rows) + 1:03d}", metric_name=name, source_page=str(page or ""))
            for k in ("metric_group", "metric_variant", "aggregation", "source_section", "source_table",
                      "source_figure", "source_fragment"):
                row[k] = (r.get(k) or "").strip()
            provenance = []
            if not page:
                provenance.append(f"Invalid or missing PDF page: {r.get('source_page')!r}. Original quote: {row['source_fragment']!r}.")
                row["source_fragment"] = ""
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
            status = status if status in STATUSES else "extracted"
            raw = (r.get("raw_value") or "").strip()
            raw_unit = (r.get("raw_unit") or "").strip()
            if status == "extracted" and not raw:
                status = "absent"
            if status != "absent" and not (row["source_fragment"] or row["source_table"] or row["source_figure"]):
                provenance.append("Source quote, table, and figure locator are missing.")
            if status == "extracted" and provenance:
                status = "present_not_extractable"
            origin = (r.get("result_origin") or "primary").strip()
            cref = (r.get("cited_ref") or "").strip()
            if origin != "cited" and cref:
                origin = "cited"
            if origin == "cited":
                if not cref or cref == "unspecified":
                    provenance.append("Cited result has no identified reference in the extraction.")
                cref = cref or "unspecified"
            else:
                origin, cref = "primary", ""
            sample = as_int(r.get("sample_size") or "")
            if (r.get("sample_size") or "").strip() and sample is None:
                note = (note + " | " if note else "") + f"sample_size: {r['sample_size'].strip()}"
            explicit_k = (r.get("metric_k") or "").strip()
            cutoffs = printed_cutoffs(name, row["metric_variant"])
            base_metric, printed_k = metric_identity(name)
            scope_k = scoped_cutoffs.get((str(page), label(row["source_table"]), label(base_metric)), "")
            if scope_k:
                cutoffs.add(scope_k)
            k = ((explicit_k.lstrip("0") or "0") if re.fullmatch(r"[0-9]+", explicit_k) else
                 printed_k or (next(iter(cutoffs)) if len(cutoffs) == 1 else ""))
            direction = (r.get("metric_direction") or "").strip()
            if direction not in DIRECTIONS:
                direction = "lower_is_better" if LOWER.search(name) else ("higher_is_better" if HIGHER.search(name) else "")
            value, unit = "", ""
            nonnumeric = False
            if status == "extracted":
                value = parse_num(raw) or ""
                if not value:
                    note = (note + " | " if note else "") + "numeric value not parsed from raw_value (range/text)"
                    status, nonnumeric = "present_not_extractable", True
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
            baseline_conflict = bool(blv and value and "%" in bl and unit != "%")
            if baseline_conflict:
                blv = None
            if blv and unit == "ms" and raw_unit.lower() in {"s", "sec", "secs", "second", "seconds"}:
                blv = format((Decimal(blv) * 1000).normalize(), "f")
                note = (note + " | " if note else "") + f"baseline converted from {bl!r} seconds"
            if bl and blv is None:
                note = (note + " | " if note else "") + f"baseline_value: {bl}"
            frag, fpage = row["source_fragment"], page
            if pages_norm is not None and ocr_pages_norm is None and frag:
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
            row.update(metric_direction=direction, metric_k=k, metric_value=value, metric_unit=unit,
                       baseline_value=blv or "", sample_size=sample or "", raw_value=raw, raw_unit=raw_unit,
                       normalized_value=value, normalized_unit=unit, result_origin=origin,
                       cited_publication_id=cref, source_page=str(fpage or ""), source_fragment=frag,
                       extraction_status=status, note=note)
            rows.append(row)
            if r.get("table_caption"):
                row_captions[row["result_id"]] = r["table_caption"]
            if r.get("plot_observation"):
                plot_ids.add(row["result_id"])
            validations.append((row, explicit_k, cutoffs, provenance, nonnumeric, baseline_conflict))
    if cells:
        relink(rows, cells)
    _fill_ids([row for row in rows if row["result_id"] not in plot_ids], out,
              native_captions(table_layout or {}), row_captions, pages_norm, model_aliases)
    _expand_metric_abbreviations(rows, pages_norm)
    _canonicalize_datasets(out["datasets"], pages_norm)
    # ---- duplicates / contradictions ----
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if (r["result_id"] not in plot_ids and r["extraction_status"] == "extracted" and r["metric_value"]
                and r["experiment_id"] and r["config_id"] and r["dataset_id"]):
            key = tuple(r[c] for c in ("experiment_id", "config_id", "dataset_id", "task_id", "metric_name", "metric_variant",
                                        "metric_group", "metric_direction", "metric_k", "metric_unit", "aggregation",
                                        "sample_size", "result_origin", "cited_publication_id", "baseline_value"))
            groups[key].append(r)
    if ocr_pages_norm is not None:
        # Keep linking and duplicate detection based on the original extraction evidence.
        for row in rows:
            if row["source_fragment"]:
                quote, status = _ground_ocr(row["source_fragment"], row["raw_value"], ocr_pages_norm[int(row["source_page"]) - 1])
                row["source_fragment"] = quote
                fstat[status] += 1
                if status == "unverified":
                    row["note"] = (row["note"] + " | " if row["note"] else "") + "quote not verified in OCR text"
    if fstat:
        log(f"  {doc_id}: quote check {dict(fstat)}")
    for g in groups.values():
        base = g[0]
        seen_values = {Decimal(base["metric_value"]): base["result_id"]}
        for r in g[1:]:
            numeric = Decimal(r["metric_value"])
            if numeric in seen_values:
                r["duplicate_of"] = seen_values[numeric]
            else:
                seen_values[numeric] = r["result_id"]
                issues.append({"check_name": "contradiction", "record_ids": f"{base['result_id']};{r['result_id']}",
                               "description": f"{base['metric_name']}: {base['metric_value']} (p.{base['source_page']}) vs "
                                              f"{r['metric_value']} (p.{r['source_page']}) for the same experiment/configuration/dataset; both kept.",
                               "source_page": r["source_page"], "source_fragment": r["source_fragment"]})
    # ---- deterministic checks ----
    topk = {c["config_id"]: c["top_k"] for c in out["configurations"] if c["top_k"]}
    for r, explicit_k, cutoffs, provenance, nonnumeric, baseline_conflict in validations:
        issues.extend(check_result(r, printed_cutoffs=cutoffs, explicit_k=explicit_k, top_k=topk.get(r["config_id"], ""),
                                   bounded=bool(BOUNDED.match(r["metric_name"])),
                                   difference=bool(DELTA.search(r["metric_name"])), provenance=provenance,
                                   baseline_conflict=baseline_conflict))
        if nonnumeric:
            issues.append(finding(r, "non_numeric_result", f"Raw value {r['raw_value']!r} cannot be normalized to one number."))
    for mi in meta.get("issues", []):
        pg = to_page(mi.get("source_page"))
        pg = str(pg) if 1 <= pg <= n_pages else ""
        issues.append({"check_name": (mi.get("check_name") or "contradiction").strip(), "record_ids": "",
                       "description": (mi.get("description") or "").strip(), "source_page": pg,
                       "source_fragment": (mi.get("source_fragment") or "").strip() if pg else ""})
    for i, it in enumerate(issues, 1):
        row = dict.fromkeys(fields["issues"], "")
        row.update(it, publication_id=doc_id, issue_id=f"I{i:02d}")
        if pages_norm is not None and row["source_fragment"] and row["source_page"]:
            page = int(row["source_page"])
            original = row["source_fragment"]
            fragment, verified_page, state = ground(original, page, pages_norm)
            unique_native_match = (state == "moved" and ocr_pages_norm is None
                                   and sum(norm(original) in text for text in pages_norm) == 1)
            if state == "ok" or unique_native_match:
                row.update(source_fragment=fragment, source_page=str(verified_page))
            else:
                row["source_fragment"] = ""
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
            w = csv.DictWriter(f, fieldnames=cols[t], lineterminator="\n")
            w.writeheader()
            self.files[t], self.writers[t] = f, w

    def write_doc(self, doc: dict[str, list[dict]]) -> None:
        rows = {table: [submission_row(table, row) for row in doc.get(table, [])] for table in TABLES}
        for t in TABLES:
            self.writers[t].writerows(rows[t])
            self.counts[t] += len(rows[t])

    def close(self, commit: bool) -> None:
        import os

        for t in TABLES:
            self.files[t].close()
            tmp = self.dir / f"{t}.csv.tmp"
            if commit:
                os.replace(tmp, self.dir / f"{t}.csv")
            else:
                tmp.unlink(missing_ok=True)
