import fitz

from v8.modules.penalizacao import analyze_penalizacao
from v8.services.demo import build_demo_pdf
from v8.services.document_segmenter import segment_documents


def test_processo_modelo_e_pdf_valido_e_chega_ao_julgamento():
    data=build_demo_pdf()
    assert data.startswith(b"%PDF")
    assert len(data)>4000

    pdf=fitz.open(stream=data,filetype="pdf")
    pages=[]
    for i,page in enumerate(pdf,start=1):
        pages.append({
            "file":"fiscaliza-v8-processo-modelo.pdf",
            "page":i,
            "text":page.get_text("text"),
            "ocr":False,
        })
    pdf.close()

    docs=segment_documents(pages)
    result=analyze_penalizacao(docs)

    assert len(pages)==14
    assert result.stage.key=="julgamento"
    assert result.stage.suggested_draft=="notificacao_decisao"
    assert result.profile.pregao=="071/2026"
    assert result.profile.ata=="083/2026"
    assert result.profile.contrato=="140/2026"
    assert "1450/2026" in result.profile.empenhos
    assert result.profile.quantity is not None
    assert result.profile.quantity.startswith("500 kits")
    assert any(e.key=="non_delivery" for e in result.evidence)
    assert any(e.key=="sanction_decision" for e in result.evidence)
