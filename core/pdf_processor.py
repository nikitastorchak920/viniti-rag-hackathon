"""PDF text-layer inspection (PyMuPDF only; no OCR)."""
from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

MIN_CHARS_PER_TEXT_PAGE = 40


@dataclass
class PdfInfo:
    path: pathlib.Path
    n_pages: int
    pages: list[str] = field(default_factory=list)  # raw text per page (1-based -> index+1)
    is_scan: bool = False

    def marked_text(self, first: int = 1, last: int | None = None) -> str:
        last = last or self.n_pages
        parts = [f"--- PAGE {n} ---\n{self.pages[n - 1].strip()}" for n in range(first, last + 1)]
        return "\n\n".join(parts)


def inspect_pdf(path: str | pathlib.Path, ocr: bool = False) -> PdfInfo:
    import pymupdf  # lazy: keeps --help / rebuild working without the package

    path = pathlib.Path(path)
    with pymupdf.open(path) as doc:
        pages = [(p.get_text() or "") for p in doc]
    with_text = sum(1 for t in pages if len(t.strip()) >= MIN_CHARS_PER_TEXT_PAGE)
    # Scan = (almost) no text layer anywhere. Mixed PDFs are treated as scans too,
    # so that image-only pages are never silently lost.
    is_scan = not pages or with_text < max(1, int(0.9 * len(pages)))
    if is_scan and ocr and pages:
        from core.ocr import ocr_available, ocr_pages

        if ocr_available():
            pages = ocr_pages(path)
            is_scan = sum(1 for t in pages if len(t.strip()) >= MIN_CHARS_PER_TEXT_PAGE) < max(1, int(0.9 * len(pages)))
    return PdfInfo(path=path, n_pages=len(pages), pages=pages, is_scan=is_scan)
