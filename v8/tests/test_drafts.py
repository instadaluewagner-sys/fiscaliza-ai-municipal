import pytest

from v8.core.models import Document
from v8.modules.penalizacao import analyze_penalizacao
from v8.services.drafts import generate_draft


def doc(i, typ, text, page):
    return Document(
        id=f"DOC-{i:03d}",
        file="teste.pdf",
        type=typ,
        title=typ,
        page_start=page,
        page_end=page,
        pages=[page],
        page_texts={page:text},
        confidence=.99,
        text=text,
    )


def test_fase_que_autoriza_pas_gera_despacho_de_instauracao_e_nao_notificacao_final():
    docs=[
        doc(1,"decisao","DESPACHO Nº 693/2025. DEFIRO a extinção unilateral e AUTORIZO A ABERTURA DE PROCESSO ADMINISTRATIVO SANCIONADOR para apuração das penalidades cabíveis.",1)
    ]
    analysis=analyze_penalizacao(docs)
    draft=generate_draft(analysis)
    assert draft.kind=="despacho_instauracao"
    assert draft.stage_key=="instauracao_sancionadora_autorizada"
    assert "não representa reconhecimento antecipado" in draft.text.lower()
    assert "processo de origem" in draft.text.lower()


def test_nao_permite_minuta_incompativel_com_estagio():
    docs=[
        doc(1,"decisao","DESPACHO Nº 693/2025. AUTORIZO A ABERTURA DE PROCESSO ADMINISTRATIVO SANCIONADOR para apuração das penalidades cabíveis.",1)
    ]
    analysis=analyze_penalizacao(docs)
    with pytest.raises(ValueError):
        generate_draft(analysis,"notificacao_decisao")


def test_julgamento_sancionador_gera_notificacao_da_decisao():
    docs=[
        doc(1,"decisao","PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO Nº 2-0001/2026. DECISÃO ADMINISTRATIVA FINAL. DECIDO e APLICO A SANÇÃO de multa à empresa.",1)
    ]
    analysis=analyze_penalizacao(docs)
    draft=generate_draft(analysis)
    assert analysis.stage.key=="julgamento"
    assert draft.kind=="notificacao_decisao"
    assert "notificação de decisão" in draft.text.lower()
