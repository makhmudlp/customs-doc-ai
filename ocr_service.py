"""
ocr_service.py
Turns a PDF / scanned PDF / image into raw text for qwen3:4b.

Strategy:
  1. PDF: try direct text extraction first.
  2. If the PDF has almost no embedded text, treat it as scanned and OCR each page.
  3. Image: always OCR.
"""

from pathlib import Path

import fitz  # PyMuPDF
import numpy as np


DPI = 300


class OcrEngine:
    """Thin wrapper over PaddleOCR PP-OCRv5."""

    def __init__(self, rec_model: str = "cyrillic_PP-OCRv5_mobile_rec"):
        from paddleocr import PaddleOCR

        self.ocr = PaddleOCR(
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_recognition_model_name=rec_model,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device="cpu",
        )

    def read(self, img) -> str:
        """OCR one image. Returns raw text lines."""
        result = self.ocr.predict(img)

        if not result:
            return ""

        page = result[0]
        texts = page.get("rec_texts", [])

        return "\n".join(texts).strip()


_ocr_engine = None


def get_ocr_engine() -> OcrEngine:
    global _ocr_engine

    if _ocr_engine is None:
        _ocr_engine = OcrEngine()

    return _ocr_engine


def render_page(page, dpi: int = DPI):
    zoom = dpi / 72
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)

    img = np.frombuffer(pix.samples, dtype=np.uint8)
    img = img.reshape(pix.height, pix.width, pix.n)

    return img


def join_pages(pages: list[str]) -> str:
    chunks = []

    for i, text in enumerate(pages, start=1):
        chunks.append(f"--- Page {i} ---\n{text}".strip())

    return "\n\n".join(chunks).strip()


def extract_from_text(file_path: str = "test_searchable.pdf") -> dict:
    file_path = Path(file_path)
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        return extract_from_pdf(file_path)

    if suffix in (".jpg", ".jpeg", ".png"):
        return extract_from_image(file_path)

    raise ValueError(f"Unsupported file type: {suffix or '(none)'}")


def extract_from_pdf(file_path: Path) -> dict:
    pages = extract_searchable_pdf(file_path)

    has_text = any(len(text.strip()) > 20 for text in pages)

    if has_text:
        return {
            "source_file": file_path.name,
            "file_type": "pdf",
            "method": "direct_pdf_text",
            "pages": pages,
            "full_text": join_pages(pages),
            "structure": None,
        }

    return extract_from_scanned_pdf(file_path)


def extract_searchable_pdf(file_path: Path) -> list[str]:
    doc = fitz.open(file_path)
    pages = []

    for page in doc:
        text = page.get_text("text").strip()
        pages.append(text)

    doc.close()
    return pages


def extract_from_scanned_pdf(file_path: Path) -> dict:
    engine = get_ocr_engine()
    doc = fitz.open(file_path)
    pages = []

    for page in doc:
        img = render_page(page)
        text = engine.read(img)
        pages.append(text)

    doc.close()

    return {
        "source_file": file_path.name,
        "file_type": "pdf",
        "method": "ocr_scanned",
        "pages": pages,
        "full_text": join_pages(pages),
        "structure": None,
    }


def extract_from_image(file_path: Path) -> dict:
    engine = get_ocr_engine()

    text = engine.read(str(file_path))

    return {
        "source_file": file_path.name,
        "file_type": "image",
        "method": "ocr_image",
        "pages": [text],
        "full_text": join_pages([text]),
        "structure": None,
    }


if __name__ == "__main__":
    result = extract_from_text("invoice.pdf")
    print(result["full_text"])