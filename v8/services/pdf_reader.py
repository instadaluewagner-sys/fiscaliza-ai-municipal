import io
import os
import fitz
from PIL import Image
import pytesseract

MAX_FILE_BYTES = int(os.getenv("V8_MAX_FILE_BYTES", str(25 * 1024 * 1024)))
OCR_LANG = os.getenv("OCR_LANG", "por+eng")

def extract_pages(data: bytes, filename: str) -> tuple[list[dict], int]:
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"Arquivo excede o limite de {MAX_FILE_BYTES // (1024*1024)} MB.")
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ValueError("PDF inválido ou corrompido.") from exc

    pages = []
    ocr_count = 0
    for index, page in enumerate(doc, start=1):
        text = (page.get_text("text") or "").strip()
        used_ocr = False
        if len(text) < 80:
            pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            text = (pytesseract.image_to_string(image, lang=OCR_LANG) or "").strip()
            used_ocr = True
            ocr_count += 1
        pages.append({"file": filename, "page": index, "text": text, "ocr": used_ocr})
    doc.close()
    return pages, ocr_count
