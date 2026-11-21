"""Optional OCR fallback for image-only PDFs (opt-in via --ocr; NOT for the 1 GB VPS).
Needs `pymupdf` plus a separately installed Tesseract and `pytesseract`. Renders ONE page at a time."""
from __future__ import annotations

import gc
import pathlib


def ocr_available() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001
        return False


def ocr_pages(path: str | pathlib.Path, lang: str = "eng", dpi: int = 200) -> list[str]:
    """Text per page: native text layer where present, OCR only for pages without one."""
    import io

    import pymupdf
    import pytesseract
    from PIL import Image

    out: list[str] = []
    with pymupdf.open(pathlib.Path(path)) as doc:
        for page in doc:
            txt = page.get_text() or ""
            if len(txt.strip()) < 30:
                pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
                with Image.open(io.BytesIO(pix.tobytes("png"))) as im:
                    txt = pytesseract.image_to_string(im, lang=lang)
                del pix
                gc.collect()
            out.append(txt)
    return out
