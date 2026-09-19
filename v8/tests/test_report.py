import fitz

from v8.core.models import Document
from v8.modules.penalizacao import analyze_penalizacao
from v8.services.report import build_audit_payload, build_pdf_report


def doc(i, typ, text, page):
    return Document(
        id=f"DOC-{i:03d}",
        file="processo.pdf",
        type=typ,
        title=typ,
        page_start=page,
        page_end=page,
        pages=[page],
        page_texts={page:text},
        confidence=.99,
        text=text,
    )


def sample_analysis():
    docs=[
        doc(1,"oficio","PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO Nº 2-0001/2026. Fica instaurado o procedimento.",1),
        doc(2,"contrato","CONTRATO ADMINISTRATIVO Nº 140/2026. Pregão Eletrônico nº 071/2026. Contratada: EMPRESA MODELO LTDA. CNPJ: 12.345.678/0001-95. Objeto: fornecimento de 500 kits de higiene bucal. Quantidade total: 500 kits de higiene bucal.",2),
        doc(3,"relatorio_tecnico","RELATÓRIO TÉCNICO. A empresa não realizou nenhuma entrega referente aos itens contratados.",3),
    ]
    return analyze_penalizacao(docs)


def test_payload_auditavel_preserva_hash_e_analise():
    analysis=sample_analysis()
    payload=build_audit_payload(
        analysis_id="abc123",
        analysis=analysis,
        source_files=[{
            "filename":"processo.pdf",
            "sha256":"a"*64,
            "size_bytes":1234,
        }],
        page_count=3,
        ocr_pages=0,
    )
    assert payload["schema"]=="fiscaliza-ai-v8-audit-report/1"
    assert payload["analysis_id"]=="abc123"
    assert payload["source_files"][0]["sha256"]=="a"*64
    assert payload["analysis"]["stage"]["key"]=="instaurado"
    assert payload["analysis"]["profile"]["contrato"]=="140/2026"


def test_relatorio_pdf_e_legivel_e_traz_fontes():
    analysis=sample_analysis()
    pdf=build_pdf_report(
        analysis_id="abc123",
        analysis=analysis,
        source_files=[{
            "filename":"processo.pdf",
            "sha256":"b"*64,
            "size_bytes":5678,
        }],
        page_count=3,
        ocr_pages=0,
    )
    assert pdf.startswith(b"%PDF")
    assert len(pdf)>1500

    document=fitz.open(stream=pdf,filetype="pdf")
    text="\n".join(page.get_text("text") for page in document)
    document.close()

    assert "Fiscaliza.AI Municipal" in text
    assert "140/2026" in text
    assert "DOC-003" in text
    assert "bbbbbbbbbbbb" in text
    assert "revisao humana" in text.lower()
