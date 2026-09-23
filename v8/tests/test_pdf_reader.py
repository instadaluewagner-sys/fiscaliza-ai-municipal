import fitz
import pytest

from v8.services.pdf_reader import extract_pages, MAX_PAGES_PER_FILE


def make_pdf(page_count: int) -> bytes:
    doc=fitz.open()
    for _ in range(page_count):
        doc.new_page(width=595,height=842)
    data=doc.tobytes()
    doc.close()
    return data


def test_pdf_com_paginas_acima_do_limite_e_bloqueado_antes_do_ocr():
    data=make_pdf(MAX_PAGES_PER_FILE+1)
    with pytest.raises(ValueError) as exc:
        extract_pages(data,"processo-enorme.pdf")
    assert "limite por PDF" in str(exc.value)
    assert str(MAX_PAGES_PER_FILE) in str(exc.value)
