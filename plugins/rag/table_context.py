"""Resolve and recover cached table observations from native PDF cells."""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from functools import lru_cache
import re
import unicodedata
from typing import NamedTuple

from core.pdf_processor import TextLine


CAPTION = re.compile(r"^table\s+([a-z]?\d+(?:\.\d+)*[a-z]?)(?:\s*[.:](?=\s|$)|\s*$)", re.I)
NUMBER = re.compile(r"(?<![\w.])[-+−]?(?:\d+(?:\.\d+)?|\.\d+)%?(?![\w.]|[.,]\d)")


class TableCell(NamedTuple):
    dataset: str
    variant: str
    configs: set[str]
    single_metric: bool
    printed: str


def label(text: str) -> str:
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold()))


def mentions(phrase: str, text: str) -> bool:
    return bool(phrase and f" {phrase} " in f" {text} ")


def identity_label(text: str) -> str:
    """Ignore case and typography around letters, digits and version decimals."""
    normalized = label(text)
    return re.sub(r"(?<=[a-z]) (?=\d)|(?<=\d) (?=[a-z]\b)", "", normalized)


@lru_cache(maxsize=2048)
def _identity_pattern(phrase: str) -> re.Pattern:
    pattern = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z]\b)", " ?", re.escape(phrase))
    return re.compile(rf"(?<!\w){pattern}(?!\w)")


def mentions_identity(phrase: str, text: str) -> bool:
    return bool(phrase and _identity_pattern(phrase).search(text))


def number(text: str) -> tuple[Decimal, bool]:
    return Decimal(text.rstrip("%").replace("−", "-")), text.endswith("%")


def dataset_aliases(datasets, pages_norm) -> dict[str, set[str]]:
    """Read explicit acronym definitions, never infer an acronym from initials or a prefix."""
    aliases = defaultdict(set)
    token = r"[A-Z][A-Za-z0-9-]{1,11}"
    for dataset_id, name in datasets:
        if not name:
            continue
        full = rf"(?i:{re.escape(name)})"
        definition = re.compile(rf"(?<![\w-])(?:({token})\s*:\s*{full}(?![\w-])|{full}\s*\(\s*({token})(?=\s*[,;)]))")
        for page in pages_norm or ():
            for match in definition.finditer(page):
                alias = match[1] or match[2]
                if sum(c.isupper() or c.isdigit() for c in alias) >= 2:
                    aliases[label(alias)].add(dataset_id)
    return aliases


def _visual_rows(lines: list[TextLine]) -> list[list[TextLine]]:
    rows: list[list[TextLine]] = []
    for line in sorted(lines, key=lambda item: (item.baseline, item.left)):
        if not line.text.strip():
            continue
        if not rows or line.baseline - rows[-1][0].baseline > 1:
            rows.append([])
        rows[-1].append(line)
    return [sorted(row, key=lambda item: item.left) for row in rows]


def native_captions(layout):
    captions = defaultdict(set)
    for page, lines in layout.items():
        for row in _visual_rows(lines):
            if match := CAPTION.match(row[0].text.strip()):
                captions[str(page), label(f"Table {match[1]}")].add(row[0].text.strip())
    return {key: next(iter(values)) for key, values in captions.items() if len(values) == 1}


def _columns(headings, metrics, dataset_labels):
    ids = [dataset_labels.get(label(line.text), "") for line in headings]
    if len(ids) < 2 or not all(ids) or len(ids) != len(set(ids)):
        return []
    # Column groups must have repeated metric headers, with each dataset centered above its group.
    for width in range(len(metrics) // len(ids), 0, -1):
        cells = metrics[-width * len(ids):]
        names = [label(line.text) for line in cells]
        if not all(names) or len(set(names[:width])) != width or names != names[:width] * len(ids):
            continue
        if all(cells[i * width].left - 8 <= (h.left + h.right) / 2 <= cells[(i + 1) * width - 1].right + 8
               for i, h in enumerate(headings)):
            return [((line.left + line.right) / 2, names[i], ids[i // width]) for i, line in enumerate(cells)]
    return []


def _method(row_label, caption_label, configurations, *, anchor_model=True):
    matches = [(len(variant), variant, cfg_id) for cfg_id, variant, model in configurations
               if mentions(variant, row_label)
               and (not anchor_model or not model or mentions(model, caption_label) or mentions(model, row_label))]
    if not matches:
        return "", set()
    best = max(m[0] for m in matches)
    variants = {variant for length, variant, _ in matches if length == best}
    if len(variants) != 1:
        return "", set()
    return next(iter(variants)), {cfg_id for length, _, cfg_id in matches if length == best}


def _table_candidates(lines, dataset_labels, configurations, metrics):
    """Index native cells by printed table identifier, exact metric label, and literal number."""
    candidates = defaultdict(list)
    rows = _visual_rows(lines)
    captions = [(i, match[1].casefold()) for i, row in enumerate(rows)
                if (match := CAPTION.match(row[0].text.strip()))]
    for j, (start, table) in enumerate(captions):
        if sum(name == table for _, name in captions) != 1:
            continue
        end = captions[j + 1][0] if j + 1 < len(captions) else len(rows)
        prefix = [rows[start]]
        for row in rows[start + 1:min(start + 7, end)]:
            if len(row) != 1:
                break
            prefix.append(row)
        caption = label(" ".join(line.text for row in prefix for line in row))
        declared_metrics = {name for name in metrics if mentions(name, caption)}
        columns, single, row_group = [], False, ""
        last_y = rows[start][0].baseline
        for i in range(start + 1, end):
            row = rows[i]
            y = row[0].baseline
            header = _columns(rows[i-1], row, dataset_labels) if y - last_y <= 30 else []
            if header:
                columns = header
                single = False
                row_group = ""
            elif len(declared_metrics) == 1 and label(row[0].text) in {"method", "model", "configuration", "system"}:
                columns, row_group = [], ""
                ids = [dataset_labels.get(label(line.text), "") for line in row[1:]]
                if len({value for value in ids if value}) >= 2:
                    metric = next(iter(declared_metrics))
                    columns = [((line.left + line.right) / 2, metric, ds) for line, ds in zip(row[1:], ids)]
                    single, row_group = True, ""
                    last_y = y
                    continue
            elif columns and y - last_y > 30:
                columns = []
            last_y = y
            if not columns or header:
                continue
            # A body row must align with every header column. This excludes prose and partial matches.
            gap = min(b[0] - a[0] for a, b in zip(columns, columns[1:]))
            numeric = [(line, (number(line.text.strip()), line.text.strip()))
                       for line in row if NUMBER.fullmatch(line.text.strip())]
            left = " ".join(line.text.strip() for line in row if line.right < columns[0][0] - gap * .4)
            aligned = [[value for line, value in numeric if abs((line.left + line.right) / 2 - x) < gap * .45]
                       for x, _, _ in columns]
            if any(len(values) != 1 for values in aligned):
                if single and not numeric and len(row) == 1:
                    row_group, _ = _method(label(left), caption, configurations, anchor_model=False)
                continue
            row_label = label(left)
            if single and row_group and (left.startswith("+") or left in {"-", "–", "—"}):
                row_label = f"{row_group} {row_label}".strip()
            variant, config_ids = _method(row_label, caption, configurations, anchor_model=not single)
            if not config_ids:
                continue
            for (_, metric, dataset_id), ((value, printed),) in zip(columns, aligned):
                candidates[table, metric, value].append(TableCell(dataset_id, variant, config_ids, single, printed))
    return candidates


def _source_key(row):
    table = CAPTION.fullmatch((row.get("source_table") or "").strip())
    return (str(row.get("source_page")), table[1].casefold(), label(row.get("metric_name") or "")) if table else None


def index_cells(rows, layout, dataset_labels, configurations):
    by_page = defaultdict(set)
    for row in rows:
        key = _source_key(row)
        if key and key[2] and (row.get("result_origin") or "primary") == "primary":
            by_page[key[0]].add(key[2])
    return {(str(page), *key): values for page, lines in layout.items() if str(page) in by_page
            for key, values in _table_candidates(lines, dataset_labels, configurations, by_page[str(page)]).items()}


def relink(rows, cells) -> None:
    for row in rows:
        if row["result_origin"] != "primary" or row["extraction_status"] != "extracted":
            continue
        key = _source_key(row)
        raw = row["raw_value"].strip()
        if not key or not NUMBER.fullmatch(raw):
            continue
        value = number(raw)
        quote = row["source_fragment"]
        if value not in {number(match[0]) for match in NUMBER.finditer(quote)}:
            continue
        options = cells.get((*key, value), ())
        quoted = [item for item in options if not item.single_metric and mentions(item.variant, label(quote))]
        anchored = quoted or [item for item in options if row["config_id"] and row["config_id"] in item.configs]
        if len(anchored) != 1 or not anchored[0].dataset:
            continue
        cell = anchored[0]
        row["dataset_id"] = cell.dataset
        if quoted and len(cell.configs) == 1:
            row["config_id"] = next(iter(cell.configs))


RECOVERY_FIELDS = ("experiment_id", "task_id", "metric_name", "metric_group", "metric_variant", "metric_k",
                   "metric_direction", "raw_unit", "aggregation", "sample_size", "source_section")


def recover_missing(rows, cells, pages_norm) -> list[dict]:
    """Recover unique, unseen values in rectangular tables with a known result schema."""
    metadata = defaultdict(set)
    observed, blocked = set(), set()
    for row in rows:
        key = _source_key(row)
        raw = (row.get("raw_value") or "").strip()
        if not key:
            continue
        if NUMBER.fullmatch(raw):
            observed.add((*key, number(raw)[0]))
        if (row.get("result_origin") or "primary") != "primary" or row.get("cited_ref"):
            blocked.add(key)
        elif NUMBER.fullmatch(raw) and (row.get("extraction_status") or "extracted") == "extracted":
            metadata[key].add(tuple(row.get(field) or "" for field in RECOVERY_FIELDS))
    recovered = []
    multiplicity = Counter()
    for (p, t, m, value), options in cells.items():
        multiplicity[p, t, m, value[0]] += len(options)
    for (p, table, metric, value), options in cells.items():
        key = (p, table, metric)
        if key in blocked or len(metadata[key]) != 1 or len(options) != 1:
            continue
        physical_value = (*key, value[0])
        if physical_value in observed or multiplicity[physical_value] != 1:
            continue
        cell = options[0]
        if cell.single_metric or not cell.dataset or len(cell.configs) != 1:
            continue
        page = int(p)
        if not 1 <= page <= len(pages_norm) or cell.printed not in pages_norm[page-1]:
            continue
        row = dict(zip(RECOVERY_FIELDS, next(iter(metadata[key]))))
        if not row["experiment_id"] or not row["task_id"] or (row["raw_unit"] not in {"", "%"} and value[1]):
            continue
        recovered.append(dict(row, source_page=page, source_table=f"Table {table}", source_fragment=cell.printed,
                              raw_value=cell.printed, dataset_id=cell.dataset, config_id=next(iter(cell.configs)),
                              result_origin="primary", extraction_status="extracted",
                              note="Recovered an unambiguous numeric cell from native PDF table layout."))
        observed.add(physical_value)
    return recovered
