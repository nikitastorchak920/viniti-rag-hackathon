"""RapidOCR for image-only pages, retaining recognized text coordinates."""
from __future__ import annotations

import importlib.util
import pathlib
from functools import cache
from threading import Lock

from core.pdf_processor import MIN_CHARS_PER_TEXT_PAGE

DEFAULT_DPI = 200
_OCR_LOCK = Lock()


def ocr_available() -> bool:
    return all(importlib.util.find_spec(module) is not None
               for module in ("rapidocr", "onnxruntime", "pymupdf4llm"))


@cache
def _engine():
    from rapidocr import RapidOCR

    # Unbounded ONNX pools compete with layout decoding and with each other.
    return RapidOCR(params={
        "EngineConfig.onnxruntime.intra_op_num_threads": 2,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        "Global.log_level": "warning",
    })


def _recognize_boxes(image):
    result = _engine()(image)
    if result.boxes is None or result.txts is None or result.scores is None:
        return []
    return list(zip(result.boxes, result.txts, result.scores, strict=True))


def recognize_page(page, *, dpi: int = DEFAULT_DPI) -> str:
    """Add positioned OCR text to an in-memory page and return readable text."""
    from pymupdf4llm.ocr.exec_ocr_interface import exec_ocr_full

    with _OCR_LOCK:
        exec_ocr_full(page, _recognize_boxes, dpi=dpi, keep_ocr_text=False)
        return page.get_text(sort=True) or ""


def ocr_pages(path: str | pathlib.Path, *, dpi: int = DEFAULT_DPI) -> list[str]:
    """Use the same OCR text for quotes, preserving any native text pages."""
    import pymupdf

    out: list[str] = []
    with pymupdf.open(pathlib.Path(path)) as doc:
        for number, page in enumerate(doc, 1):
            text = page.get_text() or ""
            if len(text.strip()) < MIN_CHARS_PER_TEXT_PAGE:
                try:
                    text = recognize_page(page, dpi=dpi)
                except Exception as exc:
                    raise RuntimeError(f"PDF page {number}: {exc}") from exc
            out.append(text)
    return out
