import asyncio
import io

import pytest
from fastapi import HTTPException, UploadFile

from v8.main import app, analyze, MAX_FILES, MAX_TOTAL_PAGES


def test_app_rc1_importa_e_expoe_rotas_essenciais():
    paths = {route.path for route in app.routes}
    assert "/" in paths
    assert "/api/v8/health" in paths
    assert "/api/v8/demo.pdf" in paths
    assert "/api/v8/analyze" in paths
    assert "/api/v8/analysis/{analysis_id}" in paths
    assert "/api/v8/document/{analysis_id}/{document_id}" in paths
    assert "/api/v8/file/{analysis_id}/{file_index}" in paths
    assert "/api/v8/draft/{analysis_id}" in paths
    assert "/api/v8/report/{analysis_id}.pdf" in paths
    assert "/api/v8/report/{analysis_id}.json" in paths


def test_app_usa_versao_rc1():
    assert app.version == "8.0.0-rc.1"


def test_lote_com_mais_pdfs_que_o_limite_e_bloqueado():
    uploads=[UploadFile(file=io.BytesIO(b"x"),filename=f"arquivo-{i}.pdf") for i in range(MAX_FILES+1)]
    with pytest.raises(HTTPException) as exc:
        asyncio.run(analyze(files=uploads,module="penalizacao"))
    assert exc.value.status_code==413
    assert "no máximo" in str(exc.value.detail)


def test_lote_com_paginas_acima_do_limite_total_e_bloqueado(monkeypatch):
    def fake_extract(data, filename):
        pages=[
            {"file":filename,"page":i,"text":"conteúdo suficiente para dispensar OCR","ocr":False}
            for i in range(1,MAX_TOTAL_PAGES+2)
        ]
        return pages,0

    monkeypatch.setattr("v8.main.extract_pages",fake_extract)
    uploads=[UploadFile(file=io.BytesIO(b"%PDF-falso"),filename="processo.pdf")]
    with pytest.raises(HTTPException) as exc:
        asyncio.run(analyze(files=uploads,module="penalizacao"))
    assert exc.value.status_code==413
    assert "páginas por análise" in str(exc.value.detail)
