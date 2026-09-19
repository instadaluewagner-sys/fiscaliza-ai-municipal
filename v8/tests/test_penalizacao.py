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
        doc(5,"decisao","PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO. DECISÃO ADMINISTRATIVA FINAL. DECIDO e APLICO A SANÇÃO de multa à empresa.",5),
    ]
    result=analyze_penalizacao(docs)
    assert result.stage.key=="julgamento"
    assert result.stage.suggested_draft=="notificacao_decisao"

def test_ata_so_e_obrigatoria_quando_arp_e_aplicavel():
    docs=[doc(1,"contrato","CONTRATO ADMINISTRATIVO Nº 140/2026. Aquisição direta vinculada à nota de empenho.",1)]
    result=analyze_penalizacao(docs)
    ata=next(x for x in result.checklist if x.key=="ata")
    assert ata.status=="not_applicable"


def test_decisao_de_origem_que_autoriza_novo_pas_nao_e_julgamento_sancionador():
    docs=[
        doc(1,"contrato","CONTRATO ADMINISTRATIVO Nº 308/2025",1),
        doc(2,"notificacao","NOTIFICAÇÃO EXTRAJUDICIAL para início das entregas.",2),
        doc(3,"defesa","DEFESA ADMINISTRATIVA apresentada pela contratada.",3),
        doc(4,"parecer_juridico","PARECER JURÍDICO sobre extinção contratual.",4),
        doc(5,"decisao","DESPACHO Nº 693/2025. DEFIRO a extinção unilateral do contrato e AUTORIZO A ABERTURA DE PROCESSO ADMINISTRATIVO SANCIONADOR para apuração das penalidades cabíveis.",5),
    ]
    result=analyze_penalizacao(docs)
    assert result.stage.key=="instauracao_sancionadora_autorizada"
    assert result.stage.suggested_draft=="despacho_instauracao"


def test_atos_do_processo_de_origem_nao_preenchem_fases_do_futuro_pas():
    docs=[
        doc(1,"notificacao","NOTIFICAÇÃO EXTRAJUDICIAL para início imediato das entregas do contrato.",1),
        doc(2,"defesa","DEFESA ADMINISTRATIVA sobre a extinção contratual.",2),
        doc(3,"parecer_juridico","PARECER JURÍDICO sobre extinção unilateral do contrato.",3),
        doc(4,"decisao","DESPACHO Nº 693/2025. DEFIRO a extinção unilateral e AUTORIZO A ABERTURA DE PROCESSO ADMINISTRATIVO SANCIONADOR para apuração das penalidades cabíveis.",4),
    ]
    result=analyze_penalizacao(docs)
    assert result.stage.key=="instauracao_sancionadora_autorizada"

    rows={x.key:x for x in result.checklist}
    assert rows["autorizacao_pas"].status=="located"
    assert rows["notificacao"].status=="not_applicable"
    assert rows["defesa"].status=="not_applicable"
    assert rows["decisao"].status=="not_applicable"

    facts=[x.fact for x in result.evidence]
    assert any("processo de origem" in x.lower() for x in facts)


def test_pendencias_nao_contam_itens_nao_aplicaveis():
    docs=[
        doc(1,"decisao","DESPACHO Nº 693/2025. AUTORIZO A ABERTURA DE PROCESSO ADMINISTRATIVO SANCIONADOR para apuração das penalidades cabíveis.",1)
    ]
    result=analyze_penalizacao(docs)
    assert result.stage.key=="instauracao_sancionadora_autorizada"
    assert all(x.key not in {"notificacao","defesa","relatorio_conclusivo","decisao","recurso"} for x in result.pending_items)
    assert any(x.kind=="next_step" for x in result.pending_items)


def test_relatorio_ausente_vira_pendencia_real_quando_instrucao_pos_defesa():
    docs=[
        doc(1,"notificacao","NOTIFICAÇÃO DE INSTAURAÇÃO DO PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO.",1),
        doc(2,"defesa","DEFESA ADMINISTRATIVA. A empresa apresenta suas razões.",2),
        doc(3,"parecer_juridico","PARECER JURÍDICO. Análise posterior à defesa.",3),
    ]
    result=analyze_penalizacao(docs)
    assert result.stage.key=="instrucao_pos_defesa"
    pending={x.key:x for x in result.pending_items}
    assert pending["relatorio_conclusivo"].kind=="missing"
    assert pending["relatorio_conclusivo"].severity=="high"
