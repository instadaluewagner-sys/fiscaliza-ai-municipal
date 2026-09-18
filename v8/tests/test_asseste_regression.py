from v8.modules.penalizacao import analyze_penalizacao
from v8.services.document_segmenter import segment_documents


def p(page, text):
    return {"file":"asseste-publico.pdf","page":page,"text":text,"ocr":False}


def test_fluxo_asseste_reduzido_mantem_pecas_e_estagio_corretos():
    pages=[
        p(1, """
AO MUNICÍPIO DE FRANCISCO BELTRÃO - PR
Ref.: Pedido de Reequilíbrio Econômico-Financeiro
Contrato n.º 308/2025 – Pregão Eletrônico n.º 90025/2025
PEDIDO DE REEQUILÍBRIO ECONÔMICO-FINANCEIRO,
CUMULADO COM PEDIDO DE EMISSÃO DE EMPENHOS E PEDIDO SUCESSIVO DE RESCISÃO AMIGÁVEL
Em resposta à Notificação Extrajudicial recebida, a contratada apresentou justificativa.
"""),
        p(34, """
1Doc: Protocolo 6- 15.566/2025 34/67
De: LUIZ V. - SMA-GM-EL
Para: Envolvidos internos acompanhando
Data: 09/09/2025 às 16:46:29
PARECER TÉCNICO – ANÁLISE DO PEDIDO DE REEQUILÍBRIO ECONÔMICO-FINANCEIRO
Contrato n.º 308/2025 – Pregão Eletrônico n.º 90025/2025 Empresa: ASSESTE COMÉRCIO DE EXTINTORES LTDA
A empresa não realizou as entregas.
"""),
        p(36, """
1Doc: Protocolo 7- 15.566/2025 36/67
De: Wlademir C.
Para: Representante: ASSESTE COMERCIO DE EXTINTORES LTDA
Data: 10/09/2025 às 16:38:28
Encaminhamento de notificação, solicito que a empresa verifique o prazo.
Anexos:
NOTIFICACAO_EXTRAJUDICIAL_ASSESTE_COM_DE_EXTINTORES_LTDA.pdf
"""),
        p(37, """
MUNICÍPIO DE FRANCISCO BELTRÃO
NOTIFICANTE: MUNICÍPIO DE FRANCISCO BELTRÃO
NOTIFICADO: ASSESTE COMERCIO DE EXTINTORES LTDA
Objeto do Contrato: O objeto do presente contrato é o fornecimento de extintores de incêndio, placas de identificação e demais materiais de combate a incêndios.
Processo Licitatório: Pregão Eletrônico 90025/2025
NOTIFICAÇÃO EXTRAJUDICIAL
Assunto: Notificação para início imediato das entregas e resposta ao indeferimento do pedido de reequilíbrio.
"""),
        p(41, """
1Doc: Protocolo 9- 15.566/2025 41/67
De: Camila B. - GP-PGM-JEA
Para: GP-AGD - Assessoria de Gabinete
Data: 06/10/2025 às 21:07:31
Segue parecer jurídico.
Anexos:
Parecer_n_1079_2025_Prot_15566_Extincao_unilateral_nova_lei_Asseste_extintores_penalidades.pdf
"""),
        p(42, """
MUNICÍPIO DE FRANCISCO BELTRÃO
PROCURADORIA-GERAL DO MUNICÍPIO
PARECER JURÍDICO N.º 1079/2025
PROTOCOLO Nº : 15566/2025
INTERESSADA : ASSESTE COMÉRCIO DE EXTINTORES LTDA
ASSUNTO : EXTINÇÃO CONTRATUAL UNILATERAL
Trata-se de pedido de rescisão do Contrato nº 308/2025.
"""),
        p(49, """
1Doc: Protocolo 10- 15.566/2025 49/67
De: Marcelo C. - SMA-LC-ALT
Para: Representante: ASSESTE COMERCIO DE EXTINTORES LTDA
Data: 07/10/2025 às 09:20:46
Com fundamento no Parecer Jurídico nº 1079/2025, intimo a empresa ASSESTE COMÉRCIO DE EXTINTORES LTDA
para que, no prazo de 5 (cinco) dias úteis, apresente sua defesa.
"""),
        p(50, """
1Doc: Protocolo 11- 15.566/2025 50/67
De: ASSESTE COMERCIO DE EXTINTORES LTDA
Para: Envolvidos internos acompanhando
Data: 08/10/2025 às 11:58:59
Defesa Administrativa – Processo nº 15566/2025 – Contrato nº 308/2025
Anexos:
Defesa_Asseste_10_2025.pdf
"""),
        p(51, """
Excelentíssimo(a) Senhor(a) Prefeito(a) do Município de Francisco Beltrão/PR
Assunto: Defesa Administrativa – Processo nº 15566/2025 – Contrato nº 308/2025
I – SÍNTESE DOS FATOS
A empresa Asseste Comércio de Extintores Ltda. apresenta sua defesa.
"""),
        p(59, """
MUNICÍPIO DE FRANCISCO BELTRÃO
DESPACHO Nº 693/2025
PROCESSO N.º: 15566/2025
INTERESSADA: ASSESTE COMÉRCIO DE EXTINTORES LTDA
ASSUNTO: EXTINÇÃO CONTRATUAL UNILATERAL
Assim, DEFIRO a extinção unilateral do Contrato nº 308/2025 e autorizo a abertura de
processo administrativo sancionador, a ser conduzido por Comissão Especial, para apuração
de eventuais responsabilidades, assegurando-se o contraditório e a ampla defesa.
"""),
    ]

    docs=segment_documents(pages)
    types=[d.type for d in docs]

    assert types==[
        "pedido_reequilibrio",
        "parecer_tecnico",
        "movimentacao_1doc",
        "notificacao",
        "movimentacao_1doc",
        "parecer_juridico",
        "intimacao",
        "movimentacao_1doc",
        "defesa",
        "decisao",
    ]

    result=analyze_penalizacao(docs)
    assert result.stage.key=="instauracao_sancionadora_autorizada"
    assert result.stage.suggested_draft=="despacho_instauracao"
    assert result.profile.quantity is None

    rows={x.key:x for x in result.checklist}
    assert rows["autorizacao_pas"].status=="located"
    assert rows["defesa"].status=="not_applicable"
    assert rows["decisao"].status=="not_applicable"

    facts=[e.fact.lower() for e in result.evidence]
    assert any("processo de origem" in fact for fact in facts)
