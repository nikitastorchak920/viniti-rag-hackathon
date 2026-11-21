"""Shared Tesseract rendering and OCR for extraction and source verification."""
from __future__ import annotations

import pathlib
import shutil
import subprocess

from core.pdf_processor import MIN_CHARS_PER_TEXT_PAGE

DEFAULT_DPI = 300


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def recognize_page(page, *, executable: str = "tesseract", lang: str = "eng", dpi: int = DEFAULT_DPI) -> str:
    import pymupdf

    pixmap = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
    process = subprocess.run(
        [str(executable), "stdin", "stdout", "-l", lang, "--psm", "3"],
        input=pixmap.tobytes("png"), capture_output=True, check=True, timeout=120,
    )
    return process.stdout.decode("utf-8", "replace")


def ocr_pages(path: str | pathlib.Path, lang: str = "eng", dpi: int = DEFAULT_DPI) -> list[str]:
    """Preserve native text and run Tesseract for pages with little text."""
    import pymupdf

    out: list[str] = []
    with pymupdf.open(pathlib.Path(path)) as doc:
        for number, page in enumerate(doc, 1):
            txt = page.get_text() or ""
            if len(txt.strip()) < MIN_CHARS_PER_TEXT_PAGE:
                try:
                    txt = recognize_page(page, lang=lang, dpi=dpi)
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(f"PDF page {number}: {exc}") from exc
            out.append(txt)
    return out
