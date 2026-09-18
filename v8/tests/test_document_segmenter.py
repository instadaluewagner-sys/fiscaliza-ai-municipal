from v8.services.document_segmenter import detect_header, segment_documents
from v8.modules.penalizacao import analyze_penalizacao


def page(n, text, file="processo.pdf"):
    return {"file": file, "page": n, "text": text, "ocr": False}


def test_pedido_reequilibrio_com_mencoes_nao_vira_contrato_ou_defesa():
    pages=[
        page(1, """
AO MUNICÍPIO
PEDIDO DE REEQUILÍBRIO ECONÔMICO-FINANCEIRO,
CUMULADO COM PEDIDO DE EMISSÃO DE EMPENHOS E PEDIDO SUCESSIVO DE RESCISÃO AMIGÁVEL
Contrato n.º 308/2025 – Pregão Eletrônico n.º 90025/2025
Em resposta à Notificação Extrajudicial recebida, a contratada apresentou justificativa.
"""),
        page(2, """
II – DO DIREITO
O Contrato nº 308/2025 prevê revisão contratual.
A empresa sustenta que não cabem penalidades.
"""),
    ]
    docs=segment_documents(pages)
    assert len(docs)==1
    assert docs[0].type=="pedido_reequilibrio"
    assert docs[0].pages==[1,2]


def test_wrapper_1doc_que_so_encaminha_anexo_nao_e_a_peca():
    pages=[
        page(36, """
1Doc: Protocolo 7- 15.566/2025 36/67
De: Wlademir C.
Para: Representante: ASSESTE COMERCIO DE EXTINTORES LTDA
Data: 10/09/2025 às 16:38:28
Encaminhamento de notificação, solicito que a empresa verifique o prazo.
Anexos:
NOTIFICACAO_EXTRAJUDICIAL_ASSESTE_COM_DE_EXTINTORES_LTDA.pdf
"""),
        page(37, """
MUNICÍPIO DE FRANCISCO BELTRÃO
NOTIFICANTE: MUNICÍPIO DE FRANCISCO BELTRÃO
NOTIFICADO: ASSESTE COMERCIO DE EXTINTORES LTDA
NOTIFICAÇÃO EXTRAJUDICIAL
Assunto: Notificação para início imediato das entregas.
"""),
        page(38, """
Em razão do parecer técnico exarado nos autos, a contratada fica NOTIFICADA.
Prazo para providências conforme o contrato.
"""),
    ]
    docs=segment_documents(pages)
    assert [d.type for d in docs]==["movimentacao_1doc","notificacao"]
    assert docs[1].pages==[37,38]


def test_intimacao_1doc_performativa_e_reconhecida_sem_titulo():
    detected=detect_header("""
1Doc: Protocolo 10- 15.566/2025 49/67
De: Marcelo C.
Para: Representante: ASSESTE COMERCIO DE EXTINTORES LTDA
Data: 07/10/2025 às 09:20:46
Com fundamento no Parecer Jurídico nº 1079/2025, intimo a empresa ASSESTE COMÉRCIO DE EXTINTORES LTDA
para que, no prazo de 5 (cinco) dias úteis, apresente sua defesa.
""")
    assert detected is not None
    assert detected[0]=="intimacao"


def test_wrapper_de_defesa_com_anexo_nao_e_a_defesa():
    pages=[
        page(50, """
1Doc: Protocolo 11- 15.566/2025 50/67
De: ASSESTE COMERCIO DE EXTINTORES LTDA
Para: Envolvidos internos acompanhando
Data: 08/10/2025 às 11:58:59
Defesa Administrativa – Processo nº 15566/2025 – Contrato nº 308/2025
Anexos:
Defesa_Asseste_10_2025.pdf
"""),
        page(51, """
Excelentíssimo(a) Senhor(a) Prefeito(a)
Assunto: Defesa Administrativa – Processo nº 15566/2025 – Contrato nº 308/2025
I – SÍNTESE DOS FATOS
A empresa apresenta suas razões.
"""),
        page(52, """
II – DO MÉRITO
A contratada sustenta que houve fato superveniente.
"""),
    ]
    docs=segment_documents(pages)
    assert [d.type for d in docs]==["movimentacao_1doc","defesa"]
    assert docs[1].pages==[51,52]


def test_despacho_que_autoriza_pas_e_identificado_como_decisao_mas_estagio_nao_e_julgamento():
    pages=[
        page(59, """
MUNICÍPIO DE FRANCISCO BELTRÃO
DESPACHO Nº 693/2025
PROCESSO N.º: 15566/2025
INTERESSADA: ASSESTE COMÉRCIO DE EXTINTORES LTDA
ASSUNTO: EXTINÇÃO CONTRATUAL UNILATERAL
Assim, DEFIRO a extinção unilateral do Contrato nº 308/2025 e autorizo a abertura de
processo administrativo sancionador, a ser conduzido por Comissão Especial, para apuração
de eventuais responsabilidades, assegurando-se o contraditório e a ampla defesa.
""")
    ]
    docs=segment_documents(pages)
    assert docs[0].type=="decisao"
    result=analyze_penalizacao(docs)
    assert result.stage.key=="instauracao_sancionadora_autorizada"
    assert result.stage.suggested_draft=="despacho_instauracao"


def test_simulacao_logistica_60_unidades_nao_vira_quantidade_contratada():
    pages=[
        page(1, """
PEDIDO DE REEQUILÍBRIO ECONÔMICO-FINANCEIRO
Contrato nº 308/2025.
Estimativa de custos logísticos por unidade (média de 60 unidades por viagem).
Dividido por 60 extintores: R$ 40,38/unidade.
""")
    ]
    docs=segment_documents(pages)
    result=analyze_penalizacao(docs)
    assert result.profile.quantity is None


def test_quantidade_explicita_em_contrato_e_aceita():
    pages=[
        page(1, """
CONTRATO ADMINISTRATIVO Nº 140/2026
Objeto: fornecimento de 500 kits de higiene bucal para unidades municipais.
Quantidade total: 500 kits de higiene bucal.
""")
    ]
    docs=segment_documents(pages)
    result=analyze_penalizacao(docs)
    assert result.profile.quantity is not None
    assert result.profile.quantity.startswith("500 kits")


def test_rotulo_notificacao_isolado_no_corpo_nao_cria_documento():
    pages=[
        page(1, """
PEDIDO DE REEQUILÍBRIO ECONÔMICO-FINANCEIRO
Contrato nº 308/2025
Resposta à
Notificação
Extrajudicial recebida anteriormente.
A empresa apresenta pedido de revisão dos valores.
""")
    ]
    docs=segment_documents(pages)
    assert len(docs)==1
    assert docs[0].type=="pedido_reequilibrio"


def test_pagina_n_de_total_preserva_parecer_mesmo_com_contrato_citado():
    pages=[
        page(1, """
MUNICÍPIO
PARECER JURÍDICO Nº 100/2026
Página 1 de 3
Análise jurídica do caso.
"""),
        page(2, """
MUNICÍPIO
Página 2 de 3
CONTRATO ADMINISTRATIVO Nº 140/2026
A cláusula contratual é transcrita apenas para análise.
"""),
        page(3, """
MUNICÍPIO
Página 3 de 3
Conclusão do parecer.
"""),
    ]
    docs=segment_documents(pages)
    assert len(docs)==1
    assert docs[0].type=="parecer_juridico"
    assert docs[0].pages==[1,2,3]


def test_perfil_contratual_traz_identificadores_e_fontes():
    pages=[
        page(1, """
ATA DE REGISTRO DE PREÇOS Nº 083/2026
Pregão Eletrônico nº 071/2026
Empresa: EMPRESA MODELO LTDA
CNPJ: 00.000.000/0000-00
Objeto: fornecimento de 500 kits de higiene bucal.
"""),
        page(2, """
CONTRATO ADMINISTRATIVO Nº 140/2026
Pregão Eletrônico nº 071/2026
Contratada: EMPRESA MODELO LTDA
Objeto do Contrato: fornecimento de 500 kits de higiene bucal.
Quantidade total: 500 kits de higiene bucal.
"""),
        page(3, """
NOTA DE EMPENHO Nº 1450/2026
Contrato nº 140/2026.
"""),
    ]
    docs=segment_documents(pages)
    result=analyze_penalizacao(docs)
    p=result.profile

    assert p.ata=="083/2026"
    assert p.pregao=="071/2026"
    assert p.contrato=="140/2026"
    assert "1450/2026" in p.empenhos
    assert p.quantity.startswith("500 kits")
    assert p.sources["ata"].document_id is not None
    assert p.sources["ata"].page==1
    assert p.sources["contrato"].page==2
    assert p.sources["empenhos"].page==3
    assert p.sources["quantity"].page==2


def test_wrapper_1doc_de_despacho_com_anexo_nao_e_a_decisao():
    pages=[
        page(59, """
1Doc: Protocolo 14- 15.566/2025 59/67
De: Gabinete
Para: Envolvidos internos
Data: 21/10/2025 às 10:00:00
Despacho com parecer jurídico favorável para extinção unilateral do Contrato nº 308/2025.
Anexos:
Despacho_693_2025.pdf
"""),
        page(60, """
MUNICÍPIO DE FRANCISCO BELTRÃO
DESPACHO Nº 693/2025
PROCESSO N.º: 15566/2025
INTERESSADA: ASSESTE COMÉRCIO DE EXTINTORES LTDA
DEFIRO a extinção unilateral e autorizo a abertura de processo administrativo sancionador.
"""),
        page(61, """
VERIFICAÇÃO DAS ASSINATURAS
Código para verificação do documento assinado.
"""),
    ]
    docs=segment_documents(pages)
    assert [d.type for d in docs]==["movimentacao_1doc","decisao"]
    assert docs[1].pages==[60,61]


def test_cnpj_valido_e_contextual_prevalece_e_divergencia_e_preservada():
    pages=[
        page(1, """
PEDIDO DE REEQUILÍBRIO ECONÔMICO-FINANCEIRO
ASSESTE COMÉRCIO DE EXTINTORES LTDA
CNPJ 82.253.642/0001-57
Contrato nº 308/2025.
"""),
        page(2, """
NOTIFICAÇÃO EXTRAJUDICIAL
NOTIFICADO: ASSESTE COMÉRCIO DE EXTINTORES LTDA, inscrita no CNPJ 82.253.642/0001-67
Contrato nº 308/2025.
"""),
        page(3, """
VERIFICAÇÃO DAS ASSINATURAS
ASSESTE COMÉRCIO DE EXTINTORES LTDA - CNPJ 82.253.642/0001-67
"""),
    ]
    docs=segment_documents(pages)
    result=analyze_penalizacao(docs)
    p=result.profile
    assert p.cnpj=="82.253.642/0001-67"
    assert "82.253.642/0001-57" in p.conflicts.get("cnpj",[])
    assert p.sources["cnpj"].page in {2,3}


def test_empresa_nao_e_substituida_por_texto_de_assinatura():
    pages=[
        page(1, """
VERIFICAÇÃO DAS ASSINATURAS
Empresa: Assinado por 1 pessoa: PAULO DE BARCELOS MEDEIROS
"""),
        page(2, """
PARECER JURÍDICO Nº 100/2026
INTERESSADA: ASSESTE COMÉRCIO DE EXTINTORES LTDA
CNPJ: 82.253.642/0001-67
"""),
    ]
    docs=segment_documents(pages)
    p=analyze_penalizacao(docs).profile
    assert p.company=="ASSESTE COMÉRCIO DE EXTINTORES LTDA"


def test_numero_de_contrato_exige_identificador_com_ano():
    pages=[
        page(1, """
PARECER JURÍDICO Nº 100/2026
A cláusula 9 do Contrato estabelece o prazo.
Contrato nº 308/2025.
""")
    ]
    docs=segment_documents(pages)
    p=analyze_penalizacao(docs).profile
    assert p.contrato=="308/2025"


def test_cnpj_do_contratante_nao_vira_conflito_do_fornecedor():
    pages=[
        page(1, """
CONTRATO DE FORNECIMENTO DE MERCADORIAS Nº 308/2025
O MUNICÍPIO DE EXEMPLO, inscrito no CNPJ 77.816.510/0001-66, doravante CONTRATANTE,
e, de outro lado, ASSESTE COMÉRCIO DE EXTINTORES LTDA, inscrita no CNPJ 82.253.642/0001-67,
doravante CONTRATADA, celebram o presente contrato.
"""),
        page(2, """
NOTIFICAÇÃO EXTRAJUDICIAL
NOTIFICADO: ASSESTE COMÉRCIO DE EXTINTORES LTDA
CNPJ: 82.253.642/0001-67
"""),
    ]
    p=analyze_penalizacao(segment_documents(pages)).profile
    assert p.cnpj=="82.253.642/0001-67"
    assert "77.816.510/0001-66" not in p.conflicts.get("cnpj",[])
