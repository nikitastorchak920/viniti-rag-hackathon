"""Digitize scatter observations from native PDF vector geometry and explicit axes."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
import re

from plugins.rag.table_context import identity_label, label, mentions, mentions_identity


FIGURE = re.compile(r"^\s*((?:figure|fig\.)\s+([a-z]?\d+)[.:])(?:\s|$)", re.I)
REFERENCE = re.compile(r"\bfig(?:ure)?s?\.?\s+([a-z]?\d+(?:\s*[-–]\s*[a-z]?\d+)?"
                       r"(?:\s*(?:,|&|and)\s*[a-z]?\d+(?:\s*[-–]\s*[a-z]?\d+)?)*)", re.I)
NUMERIC = re.compile(r"[-+−]?(?:\d+(?:\.\d+)?|\.\d+)%?")
RATIO_METRIC = re.compile(r"\b(?:precision|recall|f1|accuracy)\b", re.I)
EXPLICIT_SETTING = re.compile(r"\b(?:\w+\s*=\s*[-+]?\d+(?:[.,]\d+)?|top[-\s]*\d+)\b", re.I)


@dataclass(frozen=True)
class Text:
    box: tuple[float, float, float, float]
    value: str
    horizontal: bool

    @property
    def x(self):
        return (self.box[0] + self.box[2]) / 2

    @property
    def y(self):
        return (self.box[1] + self.box[3]) / 2


def _fit(ticks: list[tuple[float, float]], span: float) -> tuple[float, float] | None:
    """Require an affine scale supported by at least three well-separated ticks."""
    ticks = sorted(set(ticks))
    if len(ticks) < 3 or ticks[-1][0] - ticks[0][0] < span * .45:
        return None
    x0, y0 = ticks[0]
    x1, y1 = ticks[-1]
    slope = (y1 - y0) / (x1 - x0)
    if not slope or len({v for _, v in ticks}) != len(ticks):
        return None
    if any(abs((value - y0) / slope + x0 - pos) > .25 for pos, value in ticks):
        return None
    return slope, y0 - slope * x0


def _axis(texts, ticks, frame, horizontal):
    left, top, right, bottom = frame
    numbered = [text for text in texts if text.horizontal and NUMERIC.fullmatch(text.value)]
    pairs = []
    for tick in ticks:
        nearby = [text for text in numbered if (
            abs(text.x - tick) <= 2 and bottom <= text.y <= bottom + 16 if horizontal
            else abs(text.y - tick) <= 2 and left - 18 <= text.box[2] <= left
        )]
        if len(nearby) == 1:
            text = nearby[0].value
            pairs.append((tick, float(text.rstrip("%").replace("−", "-")), text.endswith("%")))
    units = {percent for _, _, percent in pairs}
    scale = _fit([(pos, value) for pos, value, _ in pairs], right - left if horizontal else bottom - top)
    if scale is None or len(units) != 1:
        return None
    titles = [t for t in texts if not NUMERIC.fullmatch(t.value) and (
        t.horizontal and abs(t.x - (left + right) / 2) <= (right - left) * .12 and bottom + 8 <= t.y <= bottom + 25
        if horizontal else not t.horizontal and abs(t.y - (top + bottom) / 2) <= (bottom - top) * .12
        and left - 26 <= t.x <= left - 8
    )]
    if len(titles) != 1:
        return None
    name = titles[0].value
    unit = "%" if units == {True} else "fraction" if RATIO_METRIC.search(name) and all(0 <= value <= 1 for _, value, _ in pairs) else ""
    return name, unit, scale


def _panel(paths, texts, frame):
    left, top, right, bottom = frame
    x_ticks, y_ticks, markers = set(), set(), defaultdict(list)
    x_axis = y_axis = False
    for path in paths:
        r = path["rect"]
        items = path["items"]
        if len(items) == 1 and items[0][0] == "l":
            if r.width < .02:
                x_axis |= abs(r.x0 - left) < .2 and abs(r.y0 - top) < .2 and abs(r.y1 - bottom) < .2
                if .5 <= r.height <= 8 and abs(r.y0 - bottom) < .2 and left <= r.x0 <= right:
                    x_ticks.add(r.x0)
            if r.height < .02:
                y_axis |= abs(r.y0 - bottom) < .2 and abs(r.x0 - left) < .2 and abs(r.x1 - right) < .2
                if .5 <= r.width <= 8 and abs(r.x1 - left) < .2 and top <= r.y0 <= bottom:
                    y_ticks.add(r.y0)
        if path.get("fill") and 4 <= len(items) <= 12 and all(item[0] == "c" for item in items):
            x, y = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
            if left <= x <= right and top <= y <= bottom and .4 <= r.width <= 8 and .4 <= r.height <= 8:
                # Color can express a third quantity; it does not determine an axis value or series label.
                signature = (len(items), round(r.width, 2), round(r.height, 2))
                markers[signature].append((x, y))
    groups = [points for points in markers.values() if len(points) >= 12]
    if not x_axis or not y_axis or len(groups) != 1:
        return None
    x = _axis(texts, x_ticks, frame, True)
    y = _axis(texts, y_ticks, frame, False)
    if x is None or y is None:
        return None
    return x, y, groups[0]


def _figure_experiment(experiments, figure):
    matches = set()
    for experiment in experiments:
        text = " ".join((experiment.get(field) or "") for field in ("note", "evaluation_protocol"))
        for match in REFERENCE.finditer(text):
            group = re.split(r"\s*(?:,|&|\band\b)\s*", match[1].casefold())
            for item in group:
                ends = re.split(r"\s*[-–]\s*", item)
                if figure in ends or (len(ends) == 2 and figure.isdigit() and all(v.isdigit() for v in ends)
                                      and int(ends[0]) <= int(figure) <= int(ends[1])):
                    matches.add(experiment.get("experiment_id", ""))
    return next(iter(matches)) if len(matches) == 1 else ""


def _dataset(title, datasets):
    choices = [(len(name), row["dataset_id"]) for row in datasets if (name := label(row["dataset_name"]))
               and mentions(name, label(title))]
    if not choices:
        return ""
    length = max(size for size, _ in choices)
    best = {key for size, key in choices if size == length}
    return next(iter(best)) if len(best) == 1 else ""


def _panel_configuration(title, generator, configurations):
    """Attach an existing configuration only when its method is printed in the panel."""
    # A panel can use a parameter whose meaning differs from the cached top_k.
    if EXPLICIT_SETTING.search(title):
        return ""
    text = label(title)
    candidates = [(len(variant), row["config_id"]) for row in configurations
                  if (variant := identity_label(row.get("rag_variant") or ""))
                  and mentions_identity(variant, text)
                  and identity_label(row.get("generator_model") or "") == identity_label(generator)]
    if not candidates:
        return ""
    longest = max(n for n, _ in candidates)
    ids = {cid for n, cid in candidates if n == longest}
    return next(iter(ids)) if len(ids) == 1 else ""


def recover_plot_points(pdf, pages, cache) -> list[dict]:
    """Return approximate axis observations without claiming unprinted point-level configurations."""
    import pymupdf
    from plugins.rag.exporter import canon_space

    panels, rows, seen_series = defaultdict(list), [], set()
    meta = cache["meta"]
    configurations = meta.get("configurations", [])
    generators = {canon_space(row.get("generator_model", "")) for row in configurations}
    generators.discard("")
    tasks = defaultdict(set)
    for window in cache.get("windows", {}).values():
        for row in window.get("results", []):
            if row.get("dataset_id") and row.get("task_id") and row.get("result_origin") == "primary":
                tasks[row["dataset_id"]].add(row["task_id"])
    with pymupdf.open(pdf) as doc:
        for page_number, text in enumerate(pages, 1):
            if not any(FIGURE.match(line) for line in text.splitlines()):
                continue
            page = doc[page_number-1]
            get_text_flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
            texts = [Text(tuple(line["bbox"]), "".join(s["text"] for s in line["spans"]).strip(), line["dir"][0] > .99)
                     for block in page.get_text("dict", flags=get_text_flags)["blocks"] for line in block.get("lines", [])]
            captions = [(entry, m) for entry in texts if (m := FIGURE.match(entry.value))]
            if not captions:
                continue
            paths = page.get_drawings()
            frames = sorted({tuple(path["rect"]) for path in paths
                             if path["type"] == "f" and path["rect"].width >= 40 and path["rect"].height >= 35})
            for frame in frames:
                left, top, right, bottom = frame
                below = [(caption, match) for caption, match in captions if bottom < caption.y
                         and caption.box[0] - 24 <= (left + right) / 2 <= caption.box[2] + 24]
                if not below:
                    continue
                caption, match = min(below, key=lambda item: item[0].y)
                if sum(other.y == caption.y for other, _ in below) != 1:
                    continue
                figure = match[2].casefold()
                experiment = _figure_experiment(meta.get("experiments", []), figure)
                titles = [t.value for t in texts if t.horizontal and top - 18 <= t.y <= top
                          and abs(t.x - (left + right)/2) <= (right - left) * .16 and _dataset(t.value, meta["datasets"])]
                if len(titles) != 1:
                    continue
                panel = _panel(paths, texts, frame)
                if panel is None:
                    continue
                title = titles[0]
                dataset = _dataset(title, meta["datasets"])
                panels[page_number, match[2], match[1]].append((experiment, title, dataset, panel))

    # Repeated views of a series use the most complete source figure, regardless of PDF order.
    ordered = sorted(panels.items(), key=lambda item: -sum(len(panel[2]) for _, _, _, panel in item[1]))
    for (page_number, figure, caption), group in ordered:
        for experiment, title, dataset, (x, y, points) in group:
            task = next(iter(tasks[dataset])) if len(tasks[dataset]) == 1 else ""
            named_models = {name for name in generators if mentions_identity(identity_label(name), label(title))}
            model = next(iter(named_models)) if len(named_models) == 1 else ""
            config_id = _panel_configuration(title, model, configurations) if len(named_models) <= 1 else ""
            for axis_index, (metric, unit, (slope, intercept)) in enumerate((x, y)):
                calibrated = [slope * p[axis_index] + intercept for p in points]
                if unit == "fraction" and any(v < -0.0001 or v > 1.0001 for v in calibrated):
                    continue
                values = [f"{max(0, min(1, v)) if unit == 'fraction' else v:.4f}" for v in calibrated]
                signature = (experiment or figure, label(title), label(metric), tuple(values))
                if signature in seen_series:
                    continue
                seen_series.add(signature)
                for point_index, (value, point) in enumerate(zip(values, points), 1):
                    if math.isfinite(float(value)):
                        rows.append(dict(source_page=page_number, source_figure=f"Figure {figure}", source_fragment=caption,
                                         metric_name=metric, raw_unit=unit, raw_value=f"~{value}", experiment_id=experiment,
                                         config_id=config_id, dataset_id=dataset, task_id=task,
                                         result_origin="primary", extraction_status="extracted",
                                         plot_observation=True, plot_generator=model,
                                         note=f"{title} | Vector marker {point_index} at ({point[0]:.3f}, {point[1]:.3f}) pt; approximate value calibrated against axis ticks."))
    return rows
