"""Plan table requests from page-aligned Markdown without discarding residual text."""
from __future__ import annotations

import re
from bisect import bisect_left
from dataclasses import dataclass

_HTML_TABLE = re.compile(r"<table\b[^>]*>.*?</table\s*>", re.I | re.S)
_HTML_ROW = re.compile(r"<tr\b[^>]*>.*?</tr\s*>", re.I | re.S)
_ROWSPAN = re.compile(r'\browspan\s*=\s*["\x27]?(\d+)', re.I)
_SPAN_ATTR = re.compile(r'\s+rowspan\s*=\s*(?:"\d+"|\x27\d+\x27|\d+)', re.I)
_COLSPAN = re.compile(r'\bcolspan\s*=\s*["\x27]?(\d+)', re.I)
_CELL = re.compile(r"<t[dh]\b", re.I)
_HTML_CELL = re.compile(r"<(t[dh])\b([^>]*)>(.*?)</\1\s*>", re.I | re.S)
_POSITIONED = re.compile(r"\s*\[Same table, positioned OCR text\.[^\n]*\]\n(?:x\d+:[^\n]*\n?)+")
_PIPE_LINES = re.compile(r"(?m)(?:^[ \t]*\|[^\n]*\|[ \t]*(?:\n|$))+")
_SEPARATOR = re.compile(r"^[\s|:-]+$")
_CAPTION = re.compile(
    r"(?im)^[ \t]*(?:[*_]{1,2})?(?P<label>(?:table|tab\.)\s+[A-Z]?\d+[a-z]?(?:\.\d+)?)\b"
    r"[ \t]*(?P<continued>\(?continued\b\)?)?(?(continued)|[.:\-–—*])[^\n]*"
)
_SECTION = re.compile(r"(?m)^#{1,6}[ \t]+.*\S")
_TAG = re.compile(r"<[^>]+>")
_NUMBER = re.compile(r"(?<![\w.])[-+−]?\d+(?:[.,]\d+)*%?(?![\w.])")
_POSITIONAL_NOTE = (
    "[Same table, positioned OCR text. Each line is a physical baseline. "
    "Prefixes are horizontal coordinates. Count each source value once.]"
)


@dataclass(frozen=True)
class Table:
    page: int
    index: int
    caption: str
    label: str
    context: str
    header: tuple[str, ...]
    rows: tuple[str, ...]
    format: str
    supplement: str = ""

    def parts(self, budget: int):
        start, used = 0, 0
        for i, row in enumerate(self.rows):
            if self.format == "html":
                cells = len(_CELL.findall(row))
            elif self.format == "pipe":
                cells = row.count("|") - 1
            else:
                cells = len(_NUMBER.findall(_TAG.sub(" ", row)))
            weight = max(1, cells, len(row) // 160)
            if i > start and used + weight > budget:
                yield start, i
                start, used = i, 0
            used += weight
        yield start, len(self.rows)

    def source(self, start: int, stop: int) -> str:
        rows = self.rows[start:stop]
        context = [self.context, self.caption]
        if self.format == "positioned":
            body = _POSITIONAL_NOTE + "\n" + "\n".join(rows)
            if self.header:
                context.append("Printed column text (context only):\n" + "\n".join(self.header))
        elif self.format == "html":
            header, rows = _html_fragment(self.header, self.rows, start, stop)
            head = "<thead>\n" + "\n".join(header) + "\n</thead>\n" if header else ""
            body = "<table>\n" + head + "\n".join(rows) + "\n</table>"
        elif self.format == "pipe":
            body = "\n".join((*self.header, *rows))
        else:
            context.extend(self.header)
            body = "\n".join(rows)
        return "\n\n".join(filter(None, (
            f"--- PAGE {self.page} ---",
            "[TABLE HEADER CONTEXT - context only]\n" + "\n".join(filter(None, context)) + "\n[END HEADER CONTEXT]",
            body, self.supplement,
        )))


def _span(pattern: re.Pattern, attrs: str) -> int:
    match = pattern.search(attrs)
    return max(1, int(match[1])) if match else 1


def _html_fragment(header, rows, start, stop):
    if (start == 0 and stop == len(rows)) or not any(_ROWSPAN.search(row) for row in (*header, *rows)):
        return header, rows[start:stop]
    kept = [*range(len(header)), *range(len(header) + start, len(header) + stop)]
    cells = [[] for _ in kept]
    occupied_until: dict[int, int] = {}
    for i, row in enumerate((*header, *rows[:stop])):
        col = 0
        for match in _HTML_CELL.finditer(row):
            tag, attrs, value = match.groups()
            width = _span(_COLSPAN, attrs)
            while any(occupied_until.get(c, 0) > i for c in range(col, col + width)):
                col += 1
            end = i + _span(_ROWSPAN, attrs)
            for c in range(col, col + width):
                occupied_until[c] = end
            first = bisect_left(kept, i)
            length = bisect_left(kept, end, lo=first) - first
            if length:
                attrs = _SPAN_ATTR.sub("", attrs)
                if length > 1:
                    attrs += f' rowspan="{length}"'
                if kept[first] != i:
                    attrs += ' data-context-only="true"'
                cells[first].append((col, f"<{tag}{attrs}>{value}</{tag}>"))
            col += width
    rendered = tuple("<tr>" + "".join(cell for _, cell in sorted(row)) + "</tr>" for row in cells)
    return rendered[:len(header)], rendered[len(header):]


def _headers(html: str, rows: tuple[str, ...]) -> int:
    thead = re.search(r"<thead\b[^>]*>(.*?)</thead>", html, re.I | re.S)
    if thead:
        return min(len(rows) - 1, len(_HTML_ROW.findall(thead[1])))
    count = 0
    for row in rows:
        if not re.search(r"<th\b", row, re.I) or re.search(r"<td\b", row, re.I):
            break
        count += 1
    return min(len(rows) - 1, count)


def _page_tables(text: str):
    blocks = []
    for match in _HTML_TABLE.finditer(text):
        raw = match[0]
        rows = tuple(_HTML_ROW.findall(raw))
        if not rows:
            continue
        end = match.end()
        supplement = _POSITIONED.match(text, end)
        n = _headers(raw, rows)
        if supplement and len(rows) == 1:
            # The layout detector grouped the scan by column. Actual baselines
            # have the row boundaries. Keep its column text as read-only context.
            lines = tuple(line for line in supplement[0].splitlines() if line.startswith("x"))
            if lines:
                blocks.append((match.start(), supplement.end(), rows, lines, "positioned", "", None))
                continue
        blocks.append((match.start(), supplement.end() if supplement else end,
                       rows[:n], rows[n:], "html", supplement[0].strip() if supplement else "", None))
    html = tuple(blocks)
    for match in _PIPE_LINES.finditer(text):
        if any(match.start() < block[1] and block[0] < match.end() for block in html):
            continue
        lines = tuple(match[0].strip().splitlines())
        if len(lines) >= 3 and _SEPARATOR.fullmatch(lines[1]) and "---" in lines[1]:
            blocks.append((match.start(), match.end(), lines[:2], lines[2:], "pipe", "", None))
    return sorted(blocks)


def _plain_tables(text, captions, blocks):
    """Recover captioned numeric grids whose layout renderer emitted plain lines."""
    output = []
    for i, caption in enumerate(captions):
        if any(start <= caption.start() < stop for start, stop, *_ in blocks):
            continue
        limit = captions[i + 1].start() if i + 1 < len(captions) else len(text)
        following = (start for start, *_ in blocks if start >= caption.end())
        limit = min(limit, min(following, default=limit))
        lines = [(caption.end() + m.start(), caption.end() + m.end(), m[0].strip())
                 for m in re.finditer(r"[^\n]+", text[caption.end():limit]) if m[0].strip()]
        numeric = [j for j, (_, _, line) in enumerate(lines)
                   if len(_NUMBER.findall(_TAG.sub(" ", line))) >= 3]
        if len(numeric) < 2 or numeric[0] > 6:
            continue
        first = numeric[0]
        header_key = lines[first - 1][2] if first else ""
        headers = tuple(line for _, _, line in lines[:first])
        start = lines[0][0]
        rows = [lines[first][2]]
        last = first
        for j in numeric[1:]:
            gap = lines[last + 1:j]
            if header_key and gap and gap[-1][2] == header_key and len(rows) >= 2:
                output.append((start, lines[last][1], headers, tuple(rows), "plain", "", caption))
                start = gap[0][0]
                headers = tuple(line for _, _, line in gap)
                rows = []
                gap = []
            if len(gap) > 3 or any(len(line.split()) > 14 for _, _, line in gap):
                break
            rows.append("\n".join([*(line for _, _, line in gap), lines[j][2]]))
            last = j
        if len(rows) >= 2:
            output.append((start, lines[last][1], headers, tuple(rows), "plain", "", caption))
    return output


def plan(pages: list[str]) -> tuple[list[Table], list[str]]:
    tables, residual = [], []
    last_section = ""
    for number, text in enumerate(pages, 1):
        blocks = _page_tables(text)
        captions = tuple(_CAPTION.finditer(text))
        blocks = sorted([*blocks, *_plain_tables(text, captions, blocks)])
        sections = tuple(_SECTION.finditer(text))
        used_captions = set()
        previous = 0
        prose = []
        for index, (start, stop, header, rows, style, supplement, anchor) in enumerate(blocks, 1):
            after = blocks[index][0] if index < len(blocks) else len(text)
            matches = [(max(start - m.end(), m.start() - stop), m) for m in captions
                       if m.start() not in used_captions and
                       (previous <= m.start() < start or stop <= m.start() < after)]
            distance, caption = min(matches, key=lambda match: match[0], default=(501, None))
            caption = anchor or (caption if distance <= 500 else None)
            if caption:
                used_captions.add(caption.start())
            section = next((m[0] for m in reversed(sections) if m.start() < start), last_section)
            caption_text = caption[0].strip() if caption else ""
            pre = [line.strip() for line in text[previous:start].splitlines()
                   if line.strip() and line.strip() != caption_text][-2:]
            context = "\n".join(dict.fromkeys(filter(None, (section, *pre))))
            label = caption["label"] if caption else ""
            if caption and caption["continued"] and not header:
                earlier = next((t for t in reversed(tables)
                                if t.label.casefold() == label.casefold() and t.format == style), None)
                if earlier:
                    header = earlier.header
                    caption_text = earlier.caption + "\n" + caption_text
            tables.append(Table(number, index, caption_text, label, context, header, rows, style, supplement))
            prose.append(text[previous:start])
            previous = stop
        prose.append(text[previous:])
        residual.append("\n".join(prose))
        if sections:
            last_section = sections[-1][0]
    return tables, residual
