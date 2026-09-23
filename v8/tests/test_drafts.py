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


def test_notificacao_de_instauracao_e_detalhada_e_nao_inventa_prazo():
    docs=[
        doc(1,"oficio","PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO Nº 2-0001/2026. Processo originado do Protocolo nº 1-9999/2026. Fica instaurado o procedimento para apuração.",1),
        doc(2,"ata_registro_precos","ATA DE REGISTRO DE PREÇOS Nº 083/2026. Pregão Eletrônico nº 071/2026. Empresa: EMPRESA MODELO LTDA. CNPJ: 00.000.000/0000-00.",2),
        doc(3,"contrato","CONTRATO ADMINISTRATIVO Nº 140/2026. Pregão Eletrônico nº 071/2026. Contratada: EMPRESA MODELO LTDA. Objeto: fornecimento de 500 kits de higiene bucal. Quantidade total: 500 kits de higiene bucal.",3),
        doc(4,"empenho","NOTA DE EMPENHO Nº 1450/2026. Contrato nº 140/2026.",4),
        doc(5,"relatorio_tecnico","RELATÓRIO TÉCNICO. A empresa não realizou nenhuma entrega do objeto. Lei Federal nº 14.133/2021, art. 155.",5),
    ]
    analysis=analyze_penalizacao(docs)
    assert analysis.stage.key=="instaurado"
    draft=generate_draft(analysis)
    text=draft.text

    assert draft.kind=="notificacao_instauracao"
    assert "Processo Administrativo de Penalização: nº 2-0001/2026" in text
    assert "Ata de Registro de Preços: nº 083/2026" in text
    assert "Pregão Eletrônico: nº 071/2026" in text
    assert "Contrato: nº 140/2026" in text
    assert "500 kits de higiene bucal" in text
    assert "I — DOS FATOS E DA ORIGEM DA APURAÇÃO" in text
    assert "III — DO ENQUADRAMENTO JURÍDICO PRELIMINAR" in text
    assert "V — DO CONTRADITÓRIO, DA DEFESA E DAS PROVAS" in text
    assert "[PRAZO EM DIAS ÚTEIS — CONFERIR NORMA APLICÁVEL]" in text
    assert "5 dias úteis" not in text
    assert "15 dias úteis" not in text
    assert "não representa imputação definitiva" in text.lower()
    assert draft.source_refs
    refs={(r.document_id,r.page) for r in draft.source_refs}
    assert ("DOC-001",1) in refs
    assert ("DOC-003",3) in refs
    assert ("DOC-005",5) in refs
