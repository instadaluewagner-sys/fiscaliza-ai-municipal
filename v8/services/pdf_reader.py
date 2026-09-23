import io
import os
import fitz
from PIL import Image
import pytesseract

MAX_FILE_BYTES = int(os.getenv("V8_MAX_PDF_BYTES", str(30 * 1024 * 1024)))
MAX_PAGES_PER_FILE = int(os.getenv("V8_MAX_PAGES_PER_FILE", "500"))
MAX_OCR_PAGES_PER_FILE = int(os.getenv("V8_MAX_OCR_PAGES_PER_FILE", "150"))
OCR_LANG = os.getenv("OCR_LANG", "por+eng")


def extract_pages(data: bytes, filename: str) -> tuple[list[dict], int]:
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"Arquivo excede o limite de {MAX_FILE_BYTES // (1024*1024)} MB.")

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ValueError("PDF inválido ou corrompido.") from exc

    try:
        if doc.page_count > MAX_PAGES_PER_FILE:
            raise ValueError(
                f"O arquivo '{filename}' possui {doc.page_count} páginas; "
                f"o limite por PDF é {MAX_PAGES_PER_FILE} páginas."
            )

        pages = []
        ocr_count = 0

        for index, page in enumerate(doc, start=1):
            text = (page.get_text("text") or "").strip()
            used_ocr = False

            if len(text) < 80:
                if ocr_count >= MAX_OCR_PAGES_PER_FILE:
                    raise ValueError(
                        f"O arquivo '{filename}' exige OCR em mais de "
                        f"{MAX_OCR_PAGES_PER_FILE} páginas. Divida o processo em PDFs menores "
                        "ou envie uma versão com camada de texto."
                    )
                pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
                image = Image.open(io.BytesIO(pix.tobytes("png")))
                text = (pytesseract.image_to_string(image, lang=OCR_LANG) or "").strip()
                used_ocr = True
                ocr_count += 1

            pages.append({
                "file": filename,
                "page": index,
                "text": text,
                "ocr": used_ocr,
            })

        return pages, ocr_count
    finally:
        doc.close()
