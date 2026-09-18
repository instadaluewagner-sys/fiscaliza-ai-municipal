from v8.core.models import Document
from v8.services.evidence import evidence_from_document

def test_evidencia_aponta_pagina_exata_da_peca_multiplas_paginas():
    doc=Document(
        id="DOC-010",
        file="processo.pdf",
        type="relatorio_tecnico",
        title="RELATÓRIO TÉCNICO",
        page_start=10,
        page_end=12,
        pages=[10,11,12],
        page_texts={
            10:"RELATÓRIO TÉCNICO. Histórico da contratação.",
            11:"Após conferência, não houve entrega do objeto contratado.",
            12:"Conclusão e encaminhamentos.",
        },
        confidence=.99,
        text="RELATÓRIO TÉCNICO. Histórico da contratação. Após conferência, não houve entrega do objeto contratado. Conclusão."
    )
    ev=evidence_from_document(doc,"Não entrega",[r"não houve entrega"],.95)
    assert ev.document_id=="DOC-010"
    assert ev.page==11
    assert "não houve entrega" in ev.excerpt.lower()
