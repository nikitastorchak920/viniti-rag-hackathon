"""Relink cached results only when the PDF exposes an unambiguous table cell."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
import re
import unicodedata

from core.pdf_processor import TextLine


CAPTION = re.compile(r"^table\s+([a-z]?\d+(?:\.\d+)*[a-z]?)(?:\s*[.:](?=\s|$)|\s*$)", re.I)
NUMBER = re.compile(r"(?<![\w.])[-+−]?(?:\d+(?:\.\d+)?|\.\d+)%?(?![\w.]|[.,]\d)")


def label(text: str) -> str:
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold()))


def mentions(phrase: str, text: str) -> bool:
    return bool(phrase and f" {phrase} " in f" {text} ")


def number(text: str) -> tuple[Decimal, bool]:
    return Decimal(text.rstrip("%").replace("−", "-")), text.endswith("%")


def _visual_rows(lines: list[TextLine]) -> list[list[TextLine]]:
    rows: list[list[TextLine]] = []
    for line in sorted(lines, key=lambda item: (item.baseline, item.left)):
        if not line.text.strip():
            continue
        if not rows or line.baseline - rows[-1][0].baseline > 1:
            rows.append([])
        rows[-1].append(line)
    return [sorted(row, key=lambda item: item.left) for row in rows]


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


def _method(row_label, caption_label, configurations):
    matches = [(len(variant), variant, cfg_id) for cfg_id, variant, model in configurations
               if mentions(variant, row_label) and (not model or mentions(model, caption_label) or mentions(model, row_label))]
    if not matches:
        return "", set()
    best = max(m[0] for m in matches)
    variants = {variant for length, variant, _ in matches if length == best}
    if len(variants) != 1:
        return "", set()
    return next(iter(variants)), {cfg_id for length, _, cfg_id in matches if length == best}


def _table_candidates(lines, dataset_labels, configurations):
    """Index native cells by printed table identifier, exact metric label, and literal number."""
    candidates = defaultdict(list)
    rows = _visual_rows(lines)
    captions = [(i, match[1].casefold()) for i, row in enumerate(rows)
                if (match := CAPTION.match(row[0].text.strip()))]
    for j, (start, table) in enumerate(captions):
        if sum(name == table for _, name in captions) != 1:
            continue
        end = captions[j + 1][0] if j + 1 < len(captions) else len(rows)
        columns, caption = [], label(" ".join(line.text for line in rows[start]))
        last_y = rows[start][0].baseline
        for i in range(start + 1, end):
            row = rows[i]
            y = row[0].baseline
            header = _columns(rows[i-1], row, dataset_labels) if y - last_y <= 30 else []
            if header:
                columns = header
            elif columns and y - last_y > 30:
                columns = []
            last_y = y
            if not columns or header:
                continue
            # A body row must align with every header column. This excludes prose and partial matches.
            gap = min(b[0] - a[0] for a, b in zip(columns, columns[1:]))
            numeric = [(line, number(line.text.strip())) for line in row if NUMBER.fullmatch(line.text.strip())]
            aligned = [[value for line, value in numeric if abs((line.left + line.right) / 2 - x) < gap * .45]
                       for x, _, _ in columns]
            if any(len(values) != 1 for values in aligned):
                continue
            row_label = label(" ".join(line.text for line in row if line.right < columns[0][0] - gap * .4))
            variant, config_ids = _method(row_label, caption, configurations)
            if not config_ids:
                continue
            for (_, metric, dataset_id), (value,) in zip(columns, aligned):
                candidates[table, metric, value].append((dataset_id, variant, config_ids))
    return candidates


def relink(rows, layout, dataset_labels, configurations) -> None:
    for page, lines in layout.items():
        page_rows = [row for row in rows if row["source_page"] == str(page) and row["source_table"]
                     and row["result_origin"] == "primary" and row["extraction_status"] == "extracted"]
        if not page_rows:
            continue
        cells = _table_candidates(lines, dataset_labels, configurations)
        for row in page_rows:
            table = CAPTION.fullmatch(row["source_table"].strip())
            raw = row["raw_value"].strip()
            if not table or not NUMBER.fullmatch(raw):
                continue
            value = number(raw)
            quote = row["source_fragment"]
            if value not in {number(match[0]) for match in NUMBER.finditer(quote)}:
                continue
            options = cells.get((table[1].casefold(), label(row["metric_name"]), value), ())
            quoted = [item for item in options if mentions(item[1], label(quote))]
            anchored = quoted or [item for item in options if row["config_id"] and row["config_id"] in item[2]]
            if len(anchored) != 1:
                continue
            dataset, _, config_ids = anchored[0]
            row["dataset_id"] = dataset
            if quoted and len(config_ids) == 1:
                row["config_id"] = next(iter(config_ids))
