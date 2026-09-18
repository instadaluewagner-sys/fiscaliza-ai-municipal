from v8.core.models import Document
from v8.modules.penalizacao import analyze_penalizacao


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


def test_triagem_sem_fato_ou_pas():
    result=analyze_penalizacao([
        doc(1,"contrato","CONTRATO ADMINISTRATIVO Nº 140/2026.",1),
    ])
    assert result.stage.key=="triagem"
    assert result.stage.suggested_draft=="despacho_diligencia"


def test_apuracao_de_origem_nao_vira_contraditorio_sancionador():
    result=analyze_penalizacao([
        doc(1,"relatorio_tecnico","RELATÓRIO TÉCNICO. Não houve entrega do objeto.",1),
        doc(2,"notificacao","NOTIFICAÇÃO EXTRAJUDICIAL para regularização da entrega.",2),
        doc(3,"defesa","DEFESA ADMINISTRATIVA sobre o inadimplemento contratual.",3),
    ])
    assert result.stage.key=="apuracao_inicial"
    assert result.stage.suggested_draft=="despacho_instauracao"


def test_pas_instaurado_sem_notificacao():
    result=analyze_penalizacao([
        doc(1,"oficio","PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO Nº 2-0001/2026. Fica instaurado o procedimento.",1),
    ])
    assert result.stage.key=="instaurado"
    assert result.stage.suggested_draft=="notificacao_instauracao"


def test_pas_com_notificacao_aguarda_defesa():
    result=analyze_penalizacao([
        doc(1,"oficio","PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO Nº 2-0001/2026.",1),
        doc(2,"notificacao","NOTIFICAÇÃO DE INSTAURAÇÃO DO PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO Nº 2-0001/2026. Apresente defesa.",2),
    ])
    assert result.stage.key=="aguardando_defesa"
    assert result.stage.suggested_draft=="certidao_prazo"
    assert result.stage.sources
    assert result.stage.sources[0].document_id=="DOC-002"
    assert result.stage.sources[0].page==2


def test_pas_com_defesa_apresentada():
    result=analyze_penalizacao([
        doc(1,"notificacao","NOTIFICAÇÃO DE INSTAURAÇÃO DO PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO Nº 2-0001/2026.",1),
        doc(2,"defesa","DEFESA ADMINISTRATIVA no Processo Administrativo de Penalização nº 2-0001/2026.",2),
    ])
    assert result.stage.key=="defesa_apresentada"
    assert result.stage.suggested_draft=="despacho_diligencia"


def test_pas_em_instrucao_pos_defesa():
    result=analyze_penalizacao([
        doc(1,"notificacao","NOTIFICAÇÃO DE INSTAURAÇÃO DO PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO Nº 2-0001/2026.",1),
        doc(2,"defesa","DEFESA ADMINISTRATIVA no Processo Administrativo de Penalização nº 2-0001/2026.",2),
        doc(3,"parecer_juridico","PARECER JURÍDICO. Análise posterior à defesa.",3),
    ])
    assert result.stage.key=="instrucao_pos_defesa"
    assert result.stage.suggested_draft=="relatorio_conclusivo"


def test_pas_com_relatorio_conclusivo():
    result=analyze_penalizacao([
        doc(1,"notificacao","NOTIFICAÇÃO DE INSTAURAÇÃO DO PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO Nº 2-0001/2026.",1),
        doc(2,"defesa","DEFESA ADMINISTRATIVA no Processo Administrativo de Penalização nº 2-0001/2026.",2),
        doc(3,"relatorio_conclusivo","RELATÓRIO CONCLUSIVO DO PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO Nº 2-0001/2026.",3),
    ])
    assert result.stage.key=="relatorio_conclusivo"
    assert result.stage.suggested_draft=="decisao"


def test_pas_com_decisao_sancionadora():
    result=analyze_penalizacao([
        doc(1,"decisao","PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO Nº 2-0001/2026. DECIDO e APLICO A SANÇÃO de multa.",1),
    ])
    assert result.stage.key=="julgamento"
    assert result.stage.suggested_draft=="notificacao_decisao"


def test_pas_com_recurso_apos_decisao():
    result=analyze_penalizacao([
        doc(1,"decisao","PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO Nº 2-0001/2026. DECIDO e APLICO A SANÇÃO de multa.",1),
        doc(2,"recurso","RECURSO ADMINISTRATIVO contra a decisão sancionadora do Processo Administrativo de Penalização nº 2-0001/2026.",2),
    ])
    assert result.stage.key=="recurso"
    assert result.stage.suggested_draft=="decisao_recurso"


def test_decisao_de_origem_anexada_nao_rebaixa_pas_ja_instaurado():
    result=analyze_penalizacao([
        doc(1,"oficio","PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO Nº 2-0001/2026. Fica instaurado o procedimento.",1),
        doc(2,"decisao","DESPACHO Nº 693/2025. AUTORIZO A ABERTURA DE PROCESSO ADMINISTRATIVO SANCIONADOR para apuração das penalidades cabíveis.",2),
        doc(3,"notificacao","NOTIFICAÇÃO DE INSTAURAÇÃO DO PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO Nº 2-0001/2026. Apresente defesa.",3),
    ])
    assert result.stage.key=="aguardando_defesa"
    assert result.stage.suggested_draft=="certidao_prazo"


def test_estagio_autorizacao_pas_aponta_decisao_fonte():
    result=analyze_penalizacao([
        doc(1,"parecer_tecnico","PARECER TÉCNICO. A empresa não realizou nenhuma entrega.",35),
        doc(2,"decisao","DESPACHO Nº 693/2025. AUTORIZO A ABERTURA DE PROCESSO ADMINISTRATIVO SANCIONADOR para apuração das responsabilidades.",60),
    ])
    assert result.stage.key=="instauracao_sancionadora_autorizada"
    assert result.stage.sources
    assert result.stage.sources[0].document_id=="DOC-002"
    assert result.stage.sources[0].page==60
