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
    known = [value for value in ids if value]
    if len(known) < 2 or len(known) != len(set(known)):
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
        anchor_left = None
        last_y = rows[start][0].baseline
        for i in range(start + 1, end):
            row = rows[i]
            y = row[0].baseline
            header = _columns(rows[i-1], row, dataset_labels) if y - last_y <= 30 else []
            if header:
                columns = header
                single = False
                row_group = ""
                anchor_left = None
            elif len(declared_metrics) == 1 and label(row[0].text) in {"method", "model", "configuration", "system"}:
                columns, row_group = [], ""
                anchor_left = None
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
                    anchor_left = row[0].left if row_group else None
                continue
            row_label = label(left)
            continuation = left.startswith("+") or left in {"-", "–", "—"}
            if single and row_group and continuation and anchor_left is not None and row[0].left >= anchor_left:
                row_label = f"{row_group} {row_label}".strip()
            elif single and not continuation:
                # A body row can also be the parent of subsequent indented modifiers.
                row_group, anchor_left = row_label, row[0].left
            if single and continuation and row_label != label(left):
                exact = [configuration for configuration in configurations if configuration[1] == row_label]
                variant, config_ids = _method(row_label, caption, exact, anchor_model=False)
            else:
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


_AGGREGATE_LABELS = {"average", "avg", "mean", "overall"}
_NUMBER_PAIR = re.compile(rf"\s*({NUMBER.pattern})\s*/\s*({NUMBER.pattern})\s*")


def _aggregate_columns(header, next_rows, caption, metrics):
    aggregate = [line for line in header if label(line.text) in _AGGREGATE_LABELS]
    if len(aggregate) != 1 or len(header) < 4 or aggregate[0] != header[-1]:
        return None
    printed = aggregate[0].text.strip()
    # Two-row grouped tables repeat the metric sequence under each corpus.
    for offset, row in enumerate(next_rows[:2], 1):
        slots = [line for line in row if label(line.text) in metrics]
        for count in (len(header), len(header) - 1):
            width, remainder = divmod(len(slots), count)
            names = [label(line.text) for line in slots]
            groups = header[-count:]
            if (width and not remainder and len(set(names[:width])) == width
                    and names == names[:width] * count
                    and all(slots[i * width].left - 8 <= (group.left + group.right) / 2
                            <= slots[(i + 1) * width - 1].right + 8
                            for i, group in enumerate(groups))):
                return offset, printed, [(line, (name,), i >= len(slots) - width)
                                          for i, (line, name) in enumerate(zip(slots, names))]
    # Compact tables put several values in one cell and declare their order in the caption.
    pair = re.findall(r"\b([A-Za-z][\w@]*)\s*/\s*([A-Za-z][\w@]*)\b", caption)
    metric_pairs = {tuple(map(label, names)) for names in pair
                    if len(set(map(label, names))) == 2 and all(label(name) in metrics for name in names)}
    if len(metric_pairs) == 1:
        names = next(iter(metric_pairs))
        return 0, printed, [(line, names, line == aggregate[0]) for line in header[1:]]
    return None


def _aggregate_cells(lines, metrics):
    indexed = defaultdict(list)
    visual = _visual_rows(lines)
    captions = [(i, match[1].casefold()) for i, row in enumerate(visual)
                if (match := CAPTION.match(row[0].text.strip()))]
    for j, (start, table) in enumerate(captions):
        if sum(name == table for _, name in captions) != 1:
            continue
        end = captions[j + 1][0] if j + 1 < len(captions) else len(visual)
        for i in range(start + 1, min(start + 10, end)):
            caption = " ".join(cell.text for row in visual[start:i] for cell in row)
            if header := _aggregate_columns(visual[i], visual[i + 1:end], caption, metrics):
                break
        else:
            continue
        offset, printed, columns = header
        centers = [(line.left + line.right) / 2 for line, _, _ in columns]
        gap = min(b - a for a, b in zip(centers, centers[1:]))
        previous_y = visual[i + offset][0].baseline
        for row in visual[i + offset + 1:end]:
            y = row[0].baseline
            if y - previous_y > 30:
                break
            previous_y = y
            if row[0].right >= centers[0] - gap * .4:
                continue
            cells = defaultdict(list)
            for cell in row[1:]:
                center = (cell.left + cell.right) / 2
                for x, (_, names, is_aggregate) in zip(centers, columns):
                    if abs(center - x) >= gap * .45:
                        continue
                    raw = cell.text.strip()
                    if len(names) == 1 and NUMBER.fullmatch(raw):
                        cells[x].append((names[0], number(raw), is_aggregate))
                    if len(names) == 2 and (pair := _NUMBER_PAIR.fullmatch(raw)):
                        cells[x].extend((name, number(value), is_aggregate) for name, value in zip(names, pair.groups()))
            complete = all(len(cells[x]) == len(names) for x, (_, names, _) in zip(centers, columns))
            for metric, value, is_aggregate in (item for values in cells.values() for item in values):
                indexed[table, metric, value].append(printed if complete and is_aggregate else "")
    return {key: labels[0] for key, labels in indexed.items() if len(labels) == 1 and labels[0]}


def link_aggregates(rows, table_layout, pages_norm, datasets) -> None:
    """Link reported aggregate columns without treating the value as an individual corpus."""
    from plugins.rag.exporter import norm

    metrics = defaultdict(set)
    for row in rows:
        if key := _source_key(row):
            metrics[key[0]].add(key[2])
    cells = {(str(page), *key): heading for page, lines in table_layout.items() if str(page) in metrics
             for key, heading in _aggregate_cells(lines, metrics[str(page)]).items()}
    used = {row["dataset_id"] for row in datasets}
    scoped = {}
    next_id = 1
    for row in rows:
        if row["dataset_id"] or row["result_origin"] != "primary" or row["extraction_status"] != "extracted":
            continue
        key, raw, quote = _source_key(row), row["raw_value"], norm(row["source_fragment"])
        if (not key or not NUMBER.fullmatch(raw) or not quote or not 1 <= int(key[0]) <= len(pages_norm)
                or quote not in pages_norm[int(key[0]) - 1]
                or number(raw) not in {number(match[0]) for match in NUMBER.finditer(quote)}):
            continue
        heading = cells.get((*key, number(raw)))
        if not heading:
            continue
        scope = (*key[:2], heading)
        if scope not in scoped:
            while f"DSA{next_id}" in used:
                next_id += 1
            dataset_id = f"DSA{next_id}"
            used.add(dataset_id)
            scoped[scope] = dataset_id
            datasets.append(dict(publication_id=row["publication_id"], dataset_id=dataset_id,
                                 dataset_name=heading, dataset_version="",
                                 note=f"Printed aggregate column, PDF page {key[0]}, Table {key[1]}."))
        row["dataset_id"] = scoped[scope]


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
