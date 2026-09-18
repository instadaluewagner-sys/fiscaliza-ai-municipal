from v8.core.models import Document
from v8.services.evidence import evidence_from_document
from v8.services.document_segmenter import segment_documents
from v8.modules.penalizacao import analyze_penalizacao

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


def test_evidencia_de_fato_prefere_parecer_tecnico_a_notificacao_posterior():
    pages=[
        {"file":"processo.pdf","page":35,"ocr":False,"text":"""
PARECER TÉCNICO – ANÁLISE DA EXECUÇÃO
Além disso, é relevante observar que, até o presente momento, a empresa não realizou nenhuma entrega referente aos itens contratados.
"""},
        {"file":"processo.pdf","page":38,"ocr":False,"text":"""
NOTIFICAÇÃO EXTRAJUDICIAL
NOTIFICANTE: MUNICÍPIO EXEMPLO
NOTIFICADO: EMPRESA MODELO LTDA
Objeto da Notificação: sobre a não entrega dos materiais.
Assunto: início imediato das entregas.
"""},
    ]
    result=analyze_penalizacao(segment_documents(pages))
    ev=next(e for e in result.evidence if e.key=="non_delivery")
    assert ev.page==35
    assert ev.document_id=="DOC-001"
    assert "nenhuma entrega" in ev.excerpt.lower()
