from v8.core.models import Document
from v8.services.timeline import build_timeline


def doc(i, typ, text, page, page_texts=None):
    return Document(
        id=f"DOC-{i:03d}",
        file="processo.pdf",
        type=typ,
        title=typ,
        page_start=page,
        page_end=page,
        pages=[page],
        page_texts=page_texts or {page:text},
        confidence=.99,
        text=text,
    )


def test_timeline_herda_data_do_envelope_1doc_para_anexo():
    wrapper=doc(
        1,
        "movimentacao_1doc",
        "1Doc: Protocolo 9- 15.566/2025\nDe: Camila\nPara: Gabinete\nData: 06/10/2025 às 21:07:31\nAnexos: parecer.pdf",
        41,
    )
    parecer=doc(
        2,
        "parecer_juridico",
        "PARECER JURÍDICO Nº 1079/2025\nASSUNTO: EXTINÇÃO CONTRATUAL UNILATERAL",
        42,
    )
    events=build_timeline([wrapper,parecer])
    assert len(events)==1
    assert events[0].document_id=="DOC-002"
    assert events[0].date=="2025-10-06"
    assert events[0].date_source=="envelope"


def test_timeline_prefere_data_do_proprio_documento():
    decisao=doc(
        1,
        "decisao",
        "DESPACHO Nº 693/2025\nFrancisco Beltrão, 21 de outubro de 2025.\nANTONIO PEDRON",
        59,
    )
    events=build_timeline([decisao])
    assert events[0].date=="2025-10-21"
    assert events[0].date_source=="document"


def test_movimentacao_1doc_nao_polui_cronologia_executiva():
    docs=[
        doc(1,"movimentacao_1doc","1Doc: Protocolo\nDe: A\nPara: B\nData: 01/09/2025",1),
        doc(2,"notificacao","NOTIFICAÇÃO EXTRAJUDICIAL",2),
        doc(3,"movimentacao_1doc","1Doc: Protocolo\nDe: A\nPara: B\nData: 02/09/2025",3),
        doc(4,"defesa","ASSUNTO: DEFESA ADMINISTRATIVA",4),
    ]
    events=build_timeline(docs)
    assert [e.type for e in events]==["notificacao","defesa"]
