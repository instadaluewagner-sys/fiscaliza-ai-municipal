from v8.core.models import Document
from v8.modules.penalizacao import analyze_penalizacao

def doc(i, typ, text, page):
    return Document(
        id=f"DOC-{i:03d}", file="teste.pdf", type=typ, title=typ,
        page_start=page, page_end=page, pages=[page], confidence=.99, text=text
    )

def test_decisao_final_nao_sugere_notificacao_de_instauracao():
    docs=[
        doc(1,"contrato","CONTRATO ADMINISTRATIVO Nº 140/2026",1),
        doc(2,"notificacao","NOTIFICAÇÃO EXTRAJUDICIAL. Apresente defesa.",2),
        doc(3,"defesa","DEFESA ADMINISTRATIVA. A empresa requer improcedência.",3),
        doc(4,"relatorio_conclusivo","RELATÓRIO CONCLUSIVO DA COMISSÃO",4),
        doc(5,"decisao","DECISÃO ADMINISTRATIVA FINAL. DECIDO pela aplicação da medida cabível.",5),
    ]
    result=analyze_penalizacao(docs)
    assert result.stage.key=="julgamento"
    assert result.stage.suggested_draft=="notificacao_decisao"

def test_ata_so_e_obrigatoria_quando_arp_e_aplicavel():
    docs=[doc(1,"contrato","CONTRATO ADMINISTRATIVO Nº 140/2026. Aquisição direta vinculada à nota de empenho.",1)]
    result=analyze_penalizacao(docs)
    ata=next(x for x in result.checklist if x.key=="ata")
    assert ata.status=="not_applicable"
