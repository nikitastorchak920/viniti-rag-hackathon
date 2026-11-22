"""PDF text-layer inspection with optional OCR for pages with little text."""
from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field
from html import unescape
from statistics import median
from threading import Lock
from typing import NamedTuple

MIN_CHARS_PER_TEXT_PAGE = 40
_PDF_LAYOUT_LOCK = Lock()
_NUMBER = re.compile(r"(?<![\w.])[+−-]?\d+(?:[.,]\d+)*%?")
_HTML_TAG = re.compile(r"</?[a-zA-Z][^<>]*>")


class TextLine(NamedTuple):
    left: float
    right: float
    baseline: float
    text: str


@dataclass
class PdfInfo:
    path: pathlib.Path
    n_pages: int
    pages: list[str] = field(default_factory=list)  # raw text per page (1-based -> index+1)
    is_scan: bool = False
    used_ocr: bool = False
    layout: dict[int, list[TextLine]] = field(default_factory=dict)
    structured_pages: list[str] | None = None
    layout_tokens: dict[int, list[TextLine]] = field(default_factory=dict)

    @property
    def prompt_pages(self) -> list[str]:
        return self.structured_pages if self.structured_pages is not None else self.pages

    def marked_text(self, first: int = 1, last: int | None = None) -> str:
        last = last or self.n_pages
        parts = [f"--- PAGE {n} ---\n{self.prompt_pages[n - 1].strip()}" for n in range(first, last + 1)]
        return "\n\n".join(parts)


def _structured_text(doc, pages: list[str], ocr_pages: set[int]) -> list[str]:
    import pymupdf4llm

    # Markdown carries the document reading order. Inline HTML tables allow
    # merged header cells to retain their colspan/rowspan.
    chunks = pymupdf4llm.to_markdown(
        doc, page_chunks=True, use_ocr=False, table_output="html",
    )
    if len(chunks) != len(pages):
        raise ValueError("Markdown page count differs from the PDF")
    fallbacks = _native_layout_fallbacks(doc, pages, chunks, ocr_pages)
    out = []
    for i, (chunk, raw) in enumerate(zip(chunks, pages, strict=True)):
        markdown = fallbacks.get(i, chunk["text"])
        if i in ocr_pages:
            markdown = _add_ocr_table_positions(doc[i], chunk)
        out.append(_preserve_numeric_text(markdown.strip(), raw))
    return out


def _native_layout_fallbacks(doc, pages: list[str], chunks, ocr_pages: set[int]) -> dict[int, str]:
    """Try the alternate native grid detector on pages with substantial numeric loss."""
    import pymupdf4llm

    suspect = {}
    for i, (raw, chunk) in enumerate(zip(pages, chunks, strict=True)):
        if i in ocr_pages:
            continue
        numbers = set(_NUMBER.findall(raw))
        missing = len(numbers - _visible_numbers(chunk["text"]))
        if missing >= 8 and missing > len(numbers) * 0.12:
            suspect[i] = (numbers, missing)
    if not suspect:
        return {}

    try:
        pymupdf4llm.use_layout(False)
        alternatives = pymupdf4llm.to_markdown(
            doc, pages=list(suspect), page_chunks=True, table_output="html",
        )
    except Exception as exc:  # noqa: BLE001
        from core.llm_client import log

        log(f"  WARN: alternate native table detection failed ({exc})")
        return {}
    finally:
        pymupdf4llm.use_layout(True)
    if len(alternatives) != len(suspect):
        return {}
    return {
        i: chunk["text"]
        for (i, (numbers, missing)), chunk in zip(suspect.items(), alternatives, strict=True)
        if "<table" in chunk["text"] and len(numbers - _visible_numbers(chunk["text"])) < missing
    }


def _add_ocr_table_positions(page, chunk: dict) -> str:
    """Expose same-baseline words if a scan grid collapses into multiline cells."""
    import pymupdf

    markdown = chunk["text"]
    for box in reversed(chunk.get("page_boxes") or []):
        if box["class"] != "table":
            continue
        start, stop = box["pos"]
        table = markdown[start:stop]
        if table.count("<tr>") != 1 or table.count("<br") < 2:
            continue
        words = page.get_text("words", clip=pymupdf.Rect(box["bbox"]))
        if not words:
            continue
        tolerance = median(y1 - y0 for _, y0, _, y1, *_ in words) * 0.35
        rows: list[tuple[float, list[tuple[float, str]]]] = []
        for x0, y0, _, y1, text, *_ in sorted(words, key=lambda word: word[3]):
            if not rows or y1 - rows[-1][0] > tolerance:
                rows.append((y1, []))
            rows[-1][1].append((x0, text))
        if len(rows) < 3:
            continue
        layout = ["[Same table, positioned OCR text. Each line is a physical baseline. "
                  "Prefixes are horizontal coordinates. Count each source value once.]"]
        for _, row in rows:
            layout.append(" | ".join(f"x{x:.0f}: {text}" for x, text in sorted(row)))
        markdown = markdown[:stop] + "\n".join(layout) + "\n\n" + markdown[stop:]
    return markdown


def _preserve_numeric_text(markdown: str, raw: str) -> str:
    """Retain literal source lines when layout parsing drops numeric text."""
    if not markdown:
        return raw
    missing = set(_NUMBER.findall(raw)) - _visible_numbers(markdown)
    if not missing:
        return markdown
    lines = [line for line in raw.splitlines() if missing.intersection(_NUMBER.findall(line))]
    return markdown + "\n\n[Additional source text from this page]\n" + "\n".join(lines)


def _visible_numbers(markdown: str) -> set[str]:
    return set(_NUMBER.findall(unescape(_HTML_TAG.sub(" ", markdown))))


def inspect_pdf(path: str | pathlib.Path, ocr: bool = False, *, layout_pages: set[int] | None = None,
                structured: bool = False) -> PdfInfo:
    # The document layout and OCR libraries have process-global state.
    with _PDF_LAYOUT_LOCK:
        return _inspect_pdf(path, ocr, layout_pages=layout_pages, structured=structured)


def _inspect_pdf(path, ocr, *, layout_pages, structured) -> PdfInfo:
    import pymupdf  # lazy: keeps --help / rebuild working without the package

    path = pathlib.Path(path)
    layout, layout_tokens = {}, {}
    from core.llm_client import log

    with pymupdf.open(path) as doc:
        pages = [(p.get_text() or "") for p in doc]
        if layout_pages:
            for number in sorted(layout_pages & set(range(1, len(doc) + 1))):
                flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
                blocks = doc[number - 1].get_text("rawdict", flags=flags)["blocks"]
                lines, tokens = [], []
                for block in blocks:
                    for line in block.get("lines", []):
                        spans = line["spans"]
                        if spans and line["dir"][0] > 0.99:
                            left, _, right, _ = line["bbox"]
                            chars = [char for span in spans for char in span["chars"]]
                            text = "".join(char["c"] for char in chars)
                            lines.append(TextLine(left, right, spans[0]["origin"][1], text))
                            for match in re.finditer(r"[^\s↑↓]+", text):
                                start, stop = match.span()
                                first, last = chars[start], chars[stop - 1]
                                tokens.append(TextLine(first["bbox"][0], last["bbox"][2],
                                                       first["origin"][1], match[0]))
                layout[number] = lines
                layout_tokens[number] = tokens
        short_pages = [i for i, text in enumerate(pages) if len(text.strip()) < MIN_CHARS_PER_TEXT_PAGE]
        ocr_pages: set[int] = set()
        if ocr and short_pages:
            from core.ocr import ocr_available, recognize_page

            if not ocr_available():
                log(f"  [{path.stem}] WARN: RapidOCR unavailable; install the project requirements")
            else:
                for i in short_pages:
                    try:
                        recognized = recognize_page(doc[i])
                    except Exception as exc:  # noqa: BLE001
                        log(f"  [{path.stem}] WARN: RapidOCR failed on PDF page {i + 1} ({type(exc).__name__}: {exc})")
                        continue
                    if len(recognized.strip()) >= MIN_CHARS_PER_TEXT_PAGE:
                        pages[i] = recognized
                        ocr_pages.add(i)
                    else:
                        log(f"  [{path.stem}] WARN: RapidOCR returned insufficient text on PDF page {i + 1}")

        unreadable = sum(len(pages[i].strip()) < MIN_CHARS_PER_TEXT_PAGE for i in short_pages)
        is_scan = (not pages or len(pages) - unreadable < max(1, int(0.9 * len(pages)))
                   or bool(ocr and unreadable))
        markdown = None
        if structured and pages and not is_scan:
            try:
                markdown = _structured_text(doc, pages, ocr_pages)
            except Exception as exc:  # noqa: BLE001
                log(f"  [{path.stem}] WARN: structured PDF parsing failed; using raw page text ({exc})")
    return PdfInfo(path=path, n_pages=len(pages), pages=pages, is_scan=is_scan, used_ocr=bool(ocr_pages),
                   layout=layout, structured_pages=markdown, layout_tokens=layout_tokens)
