"""PDF text-layer inspection with optional OCR for pages with little text."""
from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import NamedTuple

MIN_CHARS_PER_TEXT_PAGE = 40


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

    def marked_text(self, first: int = 1, last: int | None = None) -> str:
        last = last or self.n_pages
        parts = [f"--- PAGE {n} ---\n{self.pages[n - 1].strip()}" for n in range(first, last + 1)]
        return "\n\n".join(parts)


def inspect_pdf(path: str | pathlib.Path, ocr: bool = False, *, layout_pages: set[int] | None = None) -> PdfInfo:
    import pymupdf  # lazy: keeps --help / rebuild working without the package

    path = pathlib.Path(path)
    layout = {}
    with pymupdf.open(path) as doc:
        pages = [(p.get_text() or "") for p in doc]
        if layout_pages:
            for number in sorted(layout_pages & set(range(1, len(doc) + 1))):
                flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
                blocks = doc[number - 1].get_text("dict", flags=flags)["blocks"]
                lines = []
                for block in blocks:
                    for line in block.get("lines", []):
                        spans = line["spans"]
                        if spans and line["dir"][0] > 0.99:
                            left, _, right, _ = line["bbox"]
                            lines.append(TextLine(left, right, spans[0]["origin"][1], "".join(s["text"] for s in spans)))
                layout[number] = lines
    short_pages = [i for i, t in enumerate(pages) if len(t.strip()) < MIN_CHARS_PER_TEXT_PAGE]
    with_text = len(pages) - len(short_pages)
    is_scan = not pages or with_text < max(1, int(0.9 * len(pages)))
    if ocr and short_pages:
        from core.llm_client import log
        from core.ocr import ocr_available, ocr_pages

        # Even one unreadable page may contain results in a mixed PDF.
        is_scan = True
        if not ocr_available():
            log(f"  [{path.stem}] WARN: OCR unavailable (Tesseract executable was not found on PATH)")
        else:
            try:
                recognized = ocr_pages(path)
                if len(recognized) != len(pages):
                    raise ValueError("OCR page count differs from the PDF")
            except Exception as exc:  # noqa: BLE001
                log(f"  [{path.stem}] WARN: OCR failed ({type(exc).__name__}: {exc})")
            else:
                unreadable = [str(i + 1) for i in short_pages
                              if len(recognized[i].strip()) < MIN_CHARS_PER_TEXT_PAGE]
                if not unreadable:
                    return PdfInfo(path, len(pages), recognized, is_scan=False, used_ocr=True, layout=layout)
                log(f"  [{path.stem}] WARN: OCR returned insufficient text on PDF pages {', '.join(unreadable)}")
    return PdfInfo(path=path, n_pages=len(pages), pages=pages, is_scan=is_scan, layout=layout)
