"""Perfil normativo inicial do Fiscaliza.AI para Pimenta Bueno/RO.

Esta camada separa regras jurídicas/documentais da interface e do motor.
A versão PB-2026-v1 deve ser revisada quando houver alteração normativa.
"""

PROFILE = {
    "id": "pimenta_bueno_ro",
    "label": "Pimenta Bueno/RO",
    "version": "PB-2026-v1",
    "review_notice": (
        "Parametrização normativa municipal. A vigência, incidência e interpretação "
        "jurídica devem ser conferidas por revisão humana antes de decisão administrativa."
    ),
}

PROCEDURES = {
    "pregao_bens": "Pregão — aquisição de bens",
    "pregao_servicos": "Pregão — contratação de serviços",
    "pregao_srp": "Pregão — Sistema de Registro de Preços",
    "concorrencia": "Concorrência",
    "dispensa_srp": "Dispensa — Sistema de Registro de Preços",
    "contratacao_direta": "Contratação direta / inexigibilidade",
    "execucao_contratual": "Execução contratual",
    "outro": "Procedimento não classificado",
}

PLANEJAMENTO_CONTROLS = [
    {
        "id": "dod",
        "label": "DOD — Documento Oficial de Demanda",
        "aliases": ["Documento de Formalização da Demanda", "DFD"],
        "responsible": "Secretaria de Origem",
        "nature": "Obrigatório no fluxo parametrizado",
        "criticality": "alta",
        "applies_to": ["pregao_bens", "pregao_servicos", "concorrencia"],
        "foundation": "Decreto Regulamentar nº 442/2025 — fluxos municipais de contratação",
        "absence_action": "Solicitar conferência da peça de formalização da demanda; não concluir irregularidade automaticamente.",
    },
    {
        "id": "etp",
        "label": "ETP — Estudo Técnico Preliminar",
        "aliases": [],
        "responsible": "Secretaria de Origem / unidade administrativa",
        "nature": "Obrigatório ou condicional conforme o procedimento",
        "criticality": "alta",
        "applies_to": ["pregao_bens", "pregao_servicos", "pregao_srp", "concorrencia", "dispensa_srp"],
        "foundation": "Decreto Regulamentar nº 442/2025 — fluxos municipais de contratação",
        "absence_action": "Verificar o tipo de procedimento e a hipótese de dispensa do ETP antes de apontar pendência definitiva.",
    },
    {
        "id": "tr",
        "label": "Termo de Referência / Projeto Básico",
        "aliases": [],
        "responsible": "Secretaria de Origem; no SRP, conferir a atribuição específica da SUPEL",
        "nature": "Documento estruturante",
        "criticality": "alta",
        "applies_to": ["pregao_bens", "pregao_servicos", "pregao_srp", "concorrencia", "dispensa_srp", "contratacao_direta"],
        "foundation": "Decreto Regulamentar nº 442/2025 — fluxos municipais de contratação",
        "absence_action": "Sinalizar ausência para conferência e impedir conclusão automática de regularidade documental.",
    },
    {
        "id": "pesquisa_precos",
        "label": "Pesquisa de preços / orçamento estimado",
        "aliases": [],
        "responsible": "SUPEL, conforme o fluxo municipal parametrizado",
        "nature": "Elemento de estimativa da contratação",
        "criticality": "alta",
        "applies_to": ["pregao_bens", "pregao_servicos", "pregao_srp", "concorrencia", "dispensa_srp", "contratacao_direta"],
        "foundation": "Decreto Regulamentar nº 386/2023 e Decreto Regulamentar nº 442/2025",
        "absence_action": "Sinalizar para conferência das fontes, metodologia, objeto, quantitativos e compatibilidade com o TR.",
    },
    {
        "id": "riscos",
        "label": "Análise / mapa / matriz de riscos",
        "aliases": [],
        "responsible": "Secretaria de Origem / unidade administrativa",
        "nature": "Controle de planejamento conforme o fluxo aplicável",
        "criticality": "media",
        "applies_to": ["pregao_bens", "pregao_servicos", "pregao_srp", "concorrencia"],
        "foundation": "Decreto Regulamentar nº 442/2025 — fluxos municipais de contratação",
        "absence_action": "Verificar incidência no procedimento concreto e registrar necessidade de conferência humana.",
    },
    {
        "id": "autorizacao",
        "label": "Autorização / aprovação do planejamento",
        "aliases": [],
        "responsible": "Autoridade competente",
        "nature": "Ato de prosseguimento conforme o fluxo",
        "criticality": "alta",
        "applies_to": ["pregao_bens", "pregao_servicos", "pregao_srp", "concorrencia", "dispensa_srp", "contratacao_direta"],
        "foundation": "Decreto Regulamentar nº 442/2025 — fluxo municipal aplicável",
        "absence_action": "Sinalizar para conferência do ato de autorização/prosseguimento, sem presumir invalidade.",
    },
]


FORMALIZACAO_CONTROLS = [
    {
        "id": "conferencia_fase_preparatoria",
        "label": "Conferência da fase preparatória / atesto de conformidade",
        "aliases": ["Declaração de conformidade", "Atesto de conformidade"],
        "responsible": "SUPEL",
        "nature": "Controle prévio da instrução antes da fase externa",
        "criticality": "alta",
        "applies_to": ["pregao_bens", "pregao_servicos", "pregao_srp", "concorrencia"],
        "foundation": "Decreto Regulamentar nº 442/2025 — fluxos municipais de contratação",
        "absence_action": "Conferir se houve validação formal da fase preparatória pela unidade competente antes do prosseguimento.",
    },
    {
        "id": "edital",
        "label": "Edital / instrumento convocatório",
        "aliases": ["Minuta de edital"],
        "responsible": "SUPEL",
        "nature": "Instrumento da seleção quando houver licitação",
        "criticality": "alta",
        "applies_to": ["pregao_bens", "pregao_servicos", "pregao_srp", "concorrencia"],
        "foundation": "Decreto Regulamentar nº 442/2025 e Lei nº 14.133/2021",
        "absence_action": "Verificar o tipo de contratação; em procedimento competitivo, conferir a existência do instrumento convocatório aplicável.",
    },
    {
        "id": "parecer_pgm",
        "label": "Controle prévio de legalidade / parecer jurídico",
        "aliases": ["Parecer da PGM", "Análise jurídica"],
        "responsible": "Procuradoria-Geral do Município — PGM",
        "nature": "Controle jurídico prévio conforme o fluxo municipal",
        "criticality": "alta",
        "applies_to": ["pregao_bens", "pregao_servicos", "pregao_srp", "concorrencia", "contratacao_direta"],
        "foundation": "Decreto Regulamentar nº 442/2025 — fluxos municipais de contratação; Lei nº 14.133/2021",
        "absence_action": "Sinalizar para conferência do controle prévio de legalidade e de eventual hipótese normativa de dispensa da análise.",
    },
    {
        "id": "autorizacao_abertura",
        "label": "Autorização de abertura / prosseguimento",
        "aliases": ["Autorização da autoridade competente"],
        "responsible": "Gabinete / autoridade competente, conforme o fluxo",
        "nature": "Ato de autorização para prosseguimento",
        "criticality": "alta",
        "applies_to": ["pregao_bens", "pregao_servicos", "pregao_srp", "concorrencia", "contratacao_direta"],
        "foundation": "Decreto Regulamentar nº 442/2025 — fluxo municipal aplicável",
        "absence_action": "Conferir o ato de autorização da autoridade competente antes do avanço da contratação.",
    },
    {
        "id": "fase_externa",
        "label": "Fase externa — propostas, sessão, julgamento e habilitação",
        "aliases": ["Ata da sessão", "Proposta vencedora", "Resultado da sessão"],
        "responsible": "SUPEL / agente de contratação",
        "nature": "Conjunto documental da seleção competitiva",
        "criticality": "alta",
        "applies_to": ["pregao_bens", "pregao_servicos", "pregao_srp", "concorrencia"],
        "foundation": "Decreto Regulamentar nº 442/2025 — fluxos municipais de contratação; Lei nº 14.133/2021",
        "absence_action": "Conferir os registros da fase externa, inclusive proposta, julgamento, habilitação e resultado.",
    },
    {
        "id": "manifestacao_cgm",
        "label": "Manifestação da CGM anterior à homologação",
        "aliases": ["Controle Interno", "Manifestação da Controladoria"],
        "responsible": "Controladoria-Geral do Município — CGM",
        "nature": "Controle interno anterior à homologação, conforme o fluxo parametrizado",
        "criticality": "alta",
        "applies_to": ["pregao_bens", "pregao_servicos", "pregao_srp", "concorrencia"],
        "foundation": "Decreto Regulamentar nº 442/2025 — art. 12-A, §2º e fluxos municipais",
        "absence_action": "Sinalizar para conferência da manifestação do controle interno antes da homologação, sem concluir nulidade automaticamente.",
    },
    {
        "id": "adjudicacao_homologacao",
        "label": "Adjudicação e homologação",
        "aliases": ["Homologação", "Adjudicação"],
        "responsible": "Autoridade competente",
        "nature": "Ato conclusivo da seleção competitiva",
        "criticality": "alta",
        "applies_to": ["pregao_bens", "pregao_servicos", "pregao_srp", "concorrencia"],
        "foundation": "Decreto Regulamentar nº 442/2025 — fluxos municipais de contratação; Lei nº 14.133/2021",
        "absence_action": "Conferir a conclusão da fase externa e a competência da autoridade responsável pelo ato.",
    },
    {
        "id": "empenho",
        "label": "Pedido de empenho / Nota de Empenho",
        "aliases": ["Nota de Empenho", "Empenho"],
        "responsible": "Secretaria de Origem / Contabilidade, conforme o fluxo",
        "nature": "Formalização orçamentária da despesa",
        "criticality": "alta",
        "applies_to": ["pregao_bens", "pregao_servicos", "pregao_srp", "concorrencia", "contratacao_direta"],
        "foundation": "Decreto Regulamentar nº 442/2025 — fluxo municipal aplicável",
        "absence_action": "Conferir a emissão do empenho ou instrumento orçamentário pertinente antes da execução da despesa.",
    },
    {
        "id": "contrato",
        "label": "Contrato ou instrumento equivalente",
        "aliases": ["Instrumento contratual"],
        "responsible": "PGM / unidade competente pela formalização",
        "nature": "Instrumento da contratação quando exigível",
        "criticality": "alta",
        "applies_to": ["pregao_bens", "pregao_servicos", "pregao_srp", "concorrencia", "contratacao_direta"],
        "foundation": "Decreto Regulamentar nº 442/2025 — fluxos municipais de contratação; Lei nº 14.133/2021",
        "absence_action": "Verificar se o caso admite instrumento equivalente; se não, sinalizar ausência do contrato para conferência.",
    },
    {
        "id": "designacao_fiscal_gestor",
        "label": "Designação de fiscal e gestor",
        "aliases": ["Portaria de fiscal", "Portaria de gestor"],
        "responsible": "Secretaria requisitante / autoridade competente",
        "nature": "Designação para acompanhamento da execução",
        "criticality": "alta",
        "applies_to": ["pregao_bens", "pregao_servicos", "pregao_srp", "concorrencia", "contratacao_direta"],
        "foundation": "Decreto Municipal nº 6.287/2022, Decreto Regulamentar nº 442/2025 e Lei nº 14.133/2021, art. 117",
        "absence_action": "Sinalizar para conferência da designação formal dos responsáveis pelo acompanhamento da contratação.",
    },
    {
        "id": "publicacao_registro",
        "label": "Publicação / registro da contratação",
        "aliases": ["Publicação do contrato", "Extrato do contrato"],
        "responsible": "PGM / unidade responsável pela formalização",
        "nature": "Publicidade e registro do instrumento conforme o fluxo",
        "criticality": "alta",
        "applies_to": ["pregao_bens", "pregao_servicos", "pregao_srp", "concorrencia", "contratacao_direta"],
        "foundation": "Decreto Regulamentar nº 442/2025 e Lei nº 14.133/2021",
        "absence_action": "Conferir a publicação e o registro exigíveis para o instrumento utilizado.",
    },
]


FISCALIZACAO_CONTROLS = [
    {
        "id": "contrato_vigente",
        "label": "Contrato / instrumento vigente",
        "aliases": ["Instrumento contratual", "Ata de Registro de Preços", "Nota de Empenho"],
        "responsible": "Unidade gestora / fiscalização",
        "nature": "Base documental da execução",
        "criticality": "alta",
        "foundation": "Lei nº 14.133/2021, arts. 115 e seguintes; Decreto Municipal nº 6.287/2022",
        "absence_action": "Conferir o instrumento que fundamenta a execução antes de avaliar obrigações, prazos ou descumprimentos.",
    },
    {
        "id": "designacao",
        "label": "Designação formal de fiscal e gestor",
        "aliases": ["Portaria de designação", "Fiscal do contrato", "Gestor do contrato"],
        "responsible": "Autoridade competente / Secretaria requisitante",
        "nature": "Designação dos responsáveis pelo acompanhamento",
        "criticality": "alta",
        "foundation": "Lei nº 14.133/2021, art. 117; Decreto Municipal nº 6.287/2022",
        "absence_action": "Sinalizar para conferência da designação formal dos agentes responsáveis pela gestão e fiscalização.",
    },
    {
        "id": "ordem_execucao",
        "label": "Ordem de serviço / fornecimento ou autorização de execução",
        "aliases": ["Ordem de Serviço", "Ordem de Fornecimento", "Autorização de execução"],
        "responsible": "Unidade gestora / autoridade competente",
        "nature": "Condicional ao instrumento e à forma de início da execução",
        "criticality": "media",
        "foundation": "Contrato e fluxo administrativo aplicável à execução",
        "absence_action": "Verificar se o contrato exige ordem formal para início; se não exigir, tratar o controle como não aplicável.",
    },
    {
        "id": "acompanhamento",
        "label": "Registro de acompanhamento / relatório de fiscalização",
        "aliases": ["Relatório de execução", "Relatório de fiscalização"],
        "responsible": "Fiscal do contrato",
        "nature": "Registro da execução e das ocorrências relevantes",
        "criticality": "alta",
        "foundation": "Lei nº 14.133/2021, art. 117; Decreto Municipal nº 6.287/2022",
        "absence_action": "Sinalizar a necessidade de conferir os registros do fiscal sobre a execução contratual.",
    },
    {
        "id": "medicao_atesto",
        "label": "Medição / atesto da execução",
        "aliases": ["Boletim de medição", "Atesto", "Medição"],
        "responsible": "Fiscal / gestor, conforme a atribuição aplicável",
        "nature": "Comprovação da parcela efetivamente executada",
        "criticality": "alta",
        "foundation": "Lei nº 14.133/2021 e Decreto Municipal nº 6.287/2022",
        "absence_action": "Conferir a comprovação da execução antes de qualquer liquidação ou pagamento relacionado.",
    },
    {
        "id": "recebimento",
        "label": "Recebimento provisório/definitivo ou aceite",
        "aliases": ["Termo de recebimento", "Aceite"],
        "responsible": "Fiscal / comissão / unidade competente, conforme o objeto",
        "nature": "Controle de recebimento conforme a natureza do objeto",
        "criticality": "alta",
        "foundation": "Lei nº 14.133/2021, art. 140; contrato e regulamento aplicável",
        "absence_action": "Verificar qual forma de recebimento é exigível para o objeto e registrar a necessidade de conferência.",
    },
    {
        "id": "ocorrencia",
        "label": "Registro de ocorrência / não conformidade",
        "aliases": ["Ocorrência", "Não conformidade"],
        "responsible": "Fiscal do contrato",
        "nature": "Condicional — aplicável quando houver falha, atraso ou desconformidade",
        "criticality": "alta",
        "foundation": "Lei nº 14.133/2021, art. 117; Decreto Municipal nº 6.287/2022",
        "absence_action": "Se houver indícios de falha na execução, conferir o registro formal da ocorrência; na ausência de falha, tratar como não aplicável.",
    },
    {
        "id": "notificacao",
        "label": "Notificação / comunicação à contratada",
        "aliases": ["Notificação de ocorrência", "Comunicação à contratada"],
        "responsible": "Fiscal / gestor / unidade competente",
        "nature": "Condicional — quando a ocorrência exigir ciência e providência da contratada",
        "criticality": "alta",
        "foundation": "Decreto Regulamentar nº 442/2025 — fluxos de execução; Lei nº 14.133/2021",
        "absence_action": "Havendo ocorrência relevante, conferir se a contratada foi formalmente cientificada e recebeu prazo/providência compatível.",
    },
    {
        "id": "providencia",
        "label": "Providência, manifestação ou regularização registrada",
        "aliases": ["Manifestação da contratada", "Plano de correção", "Regularização"],
        "responsible": "Contratada e fiscalização",
        "nature": "Condicional — resposta e acompanhamento da ocorrência",
        "criticality": "alta",
        "foundation": "Decreto Municipal nº 6.287/2022 e fluxo administrativo da contratação",
        "absence_action": "Conferir se a ocorrência teve tratamento, manifestação e registro do resultado da providência adotada.",
    },
    {
        "id": "encaminhamento_penalizacao",
        "label": "Encaminhamento para providência superior / penalização",
        "aliases": ["Encaminhamento para penalização", "Remessa à Comissão de Penalização"],
        "responsible": "Fiscal / gestor / autoridade competente",
        "nature": "Condicional — somente quando a falha não for solucionada ou houver possível infração",
        "criticality": "alta",
        "foundation": "Decreto Regulamentar nº 442/2025 e Decreto Regulamentar nº 405/2023",
        "absence_action": "Somente exigir encaminhamento quando os autos indicarem falha não solucionada ou possível infração; não presumir necessidade de sanção.",
    },
]


ALTERATION_TYPES = {
    "prorrogacao": "Prorrogação contratual",
    "reajuste": "Reajuste em sentido estrito",
    "repactuacao": "Repactuação",
    "reequilibrio": "Restabelecimento do equilíbrio econômico-financeiro",
    "acrescimo_supressao": "Acréscimo / supressão quantitativa",
    "apostilamento": "Apostilamento",
    "outra": "Outra alteração contratual",
}

ALTERACOES_CONTROLS = [
    {
        "id": "contrato_vigente",
        "label": "Contrato vigente e alterações anteriores",
        "responsible": "Unidade gestora / fiscalização",
        "nature": "Base obrigatória para identificar a situação contratual vigente",
        "criticality": "alta",
        "applies_to": ["prorrogacao","reajuste","repactuacao","reequilibrio","acrescimo_supressao","apostilamento","outra"],
        "foundation": "Lei nº 14.133/2021, arts. 124 a 136",
        "absence_action": "Conferir o contrato e aditivos/apostilas anteriores antes de avaliar qualquer alteração.",
    },
    {
        "id": "pedido_justificativa",
        "label": "Pedido e justificativa da alteração",
        "responsible": "Unidade gestora e/ou contratada, conforme a origem do pleito",
        "nature": "Motivação e delimitação do pedido",
        "criticality": "alta",
        "applies_to": ["prorrogacao","reajuste","repactuacao","reequilibrio","acrescimo_supressao","outra"],
        "foundation": "Lei nº 14.133/2021, art. 124",
        "absence_action": "Sinalizar ausência da motivação do pedido e exigir conferência antes de prosseguir.",
    },
    {
        "id": "relatorio_execucao",
        "label": "Relatório da fiscalização sobre a execução",
        "responsible": "Fiscal / gestor do contrato",
        "nature": "Subsídio técnico sobre execução, cumprimento e interesse na alteração",
        "criticality": "media",
        "applies_to": ["prorrogacao","reequilibrio","acrescimo_supressao","outra"],
        "foundation": "Lei nº 14.133/2021, art. 117; Decreto Municipal nº 6.287/2022",
        "absence_action": "Conferir a situação de execução e eventual manifestação do fiscal/gestor.",
    },
    {
        "id": "vantajosidade",
        "label": "Demonstração de interesse público / vantajosidade",
        "responsible": "Unidade gestora",
        "nature": "Controle especialmente relevante para prorrogação e alterações com reflexo econômico",
        "criticality": "alta",
        "applies_to": ["prorrogacao","reequilibrio","acrescimo_supressao","outra"],
        "foundation": "Lei nº 14.133/2021 e motivação administrativa do caso concreto",
        "absence_action": "Conferir se a alteração preserva o interesse público e se a motivação demonstra sua vantagem ou necessidade.",
    },
    {
        "id": "memoria_calculo",
        "label": "Planilha / memória de cálculo / comprovação econômica",
        "responsible": "Contratada e/ou unidade técnica",
        "nature": "Demonstração do impacto econômico da alteração",
        "criticality": "alta",
        "applies_to": ["reajuste","repactuacao","reequilibrio","acrescimo_supressao"],
        "foundation": "Lei nº 14.133/2021, arts. 124, 130, 134 e 135, conforme a hipótese",
        "absence_action": "Sinalizar ausência da memória de cálculo ou comprovação econômica pertinente ao tipo de alteração.",
    },
    {
        "id": "indice_data_base",
        "label": "Índice contratual, data-base e interregno",
        "responsible": "Unidade técnica / gestão contratual",
        "nature": "Específico do reajuste em sentido estrito",
        "criticality": "alta",
        "applies_to": ["reajuste"],
        "foundation": "Lei nº 14.133/2021, art. 92, §§ 3º e 4º",
        "absence_action": "Conferir índice previsto no contrato, data-base e interregno aplicável.",
    },
    {
        "id": "repactuacao_custos",
        "label": "Planilha de custos e instrumento coletivo da repactuação",
        "responsible": "Contratada / unidade técnica",
        "nature": "Específico de serviços contínuos com dedicação exclusiva ou predominância de mão de obra",
        "criticality": "alta",
        "applies_to": ["repactuacao"],
        "foundation": "Lei nº 14.133/2021, art. 135, especialmente § 6º",
        "absence_action": "Conferir demonstração analítica dos custos e acordo, convenção ou sentença normativa pertinente.",
    },
    {
        "id": "fato_superveniente_nexo",
        "label": "Fato superveniente, prova e nexo com o desequilíbrio",
        "responsible": "Requerente e unidade técnica",
        "nature": "Específico do restabelecimento do equilíbrio econômico-financeiro",
        "criticality": "alta",
        "applies_to": ["reequilibrio"],
        "foundation": "Lei nº 14.133/2021, art. 124, II, d, e arts. 130 e 131",
        "absence_action": "Conferir o evento alegado, sua superveniência, a alocação de riscos e o nexo econômico com o contrato.",
    },
    {
        "id": "matriz_riscos",
        "label": "Conferência da matriz de riscos / alocação do evento",
        "responsible": "Unidade técnica / gestão contratual",
        "nature": "Condicional — relevante quando houver matriz de riscos ou alocação contratual do evento",
        "criticality": "alta",
        "applies_to": ["reequilibrio"],
        "foundation": "Lei nº 14.133/2021, arts. 22 e 103 e disciplina do equilíbrio contratual",
        "absence_action": "Verificar se existe matriz de riscos e se o evento alegado foi alocado a uma das partes.",
    },
    {
        "id": "limites_quantitativos",
        "label": "Cálculo dos limites de acréscimo / supressão e preservação do objeto",
        "responsible": "Unidade técnica / gestão contratual",
        "nature": "Específico de alteração quantitativa",
        "criticality": "alta",
        "applies_to": ["acrescimo_supressao"],
        "foundation": "Lei nº 14.133/2021, arts. 125 e 126",
        "absence_action": "Conferir percentuais, base de cálculo e se a alteração não transfigura o objeto contratado.",
    },
    {
        "id": "dotacao",
        "label": "Dotação / disponibilidade orçamentária para o impacto financeiro",
        "responsible": "Unidade orçamentária",
        "nature": "Condicional — exigível quando houver aumento ou reflexo financeiro a suportar",
        "criticality": "alta",
        "applies_to": ["prorrogacao","repactuacao","reequilibrio","acrescimo_supressao","outra"],
        "foundation": "Legislação orçamentária e instrução da despesa; Lei nº 14.133/2021",
        "absence_action": "Havendo impacto financeiro, conferir a disponibilidade orçamentária correspondente.",
    },
    {
        "id": "analise_tecnica",
        "label": "Análise técnica do pedido",
        "responsible": "Unidade gestora / área técnica",
        "nature": "Exame da hipótese, documentação e reflexos da alteração",
        "criticality": "alta",
        "applies_to": ["prorrogacao","reajuste","repactuacao","reequilibrio","acrescimo_supressao","outra"],
        "foundation": "Lei nº 14.133/2021, arts. 123 e 124 e seguintes",
        "absence_action": "Sinalizar para conferência da manifestação técnica que instrui a decisão.",
    },
    {
        "id": "parecer_juridico",
        "label": "Análise / parecer jurídico quando cabível",
        "responsible": "PGM / unidade jurídica competente",
        "nature": "Controle jurídico conforme a hipótese e o fluxo aplicável",
        "criticality": "alta",
        "applies_to": ["prorrogacao","repactuacao","reequilibrio","acrescimo_supressao","outra"],
        "foundation": "Lei nº 14.133/2021 e fluxo jurídico-administrativo aplicável",
        "absence_action": "Conferir a incidência do controle jurídico no caso concreto antes de concluir pela suficiência da instrução.",
    },
    {
        "id": "decisao",
        "label": "Decisão motivada sobre a alteração",
        "responsible": "Autoridade competente",
        "nature": "Conclusão administrativa do pedido",
        "criticality": "alta",
        "applies_to": ["prorrogacao","reajuste","repactuacao","reequilibrio","acrescimo_supressao","apostilamento","outra"],
        "foundation": "Lei nº 14.133/2021, art. 123 e disciplina específica da alteração",
        "absence_action": "Sinalizar ausência de decisão expressa e motivada sobre a solicitação ou alteração.",
    },
    {
        "id": "formalizacao",
        "label": "Termo aditivo ou apostila compatível com a hipótese",
        "responsible": "Unidade competente pela formalização contratual",
        "nature": "Forma de registro da alteração conforme sua natureza",
        "criticality": "alta",
        "applies_to": ["prorrogacao","reajuste","repactuacao","reequilibrio","acrescimo_supressao","apostilamento","outra"],
        "foundation": "Lei nº 14.133/2021, arts. 132 e 136",
        "absence_action": "Conferir se a hipótese exige termo aditivo ou admite simples apostila e se o instrumento utilizado é compatível.",
    },
]


def classify_alteration_type(text_normalized: str) -> str:
    """Classifica a alteração sem misturar institutos jurídicos distintos."""
    z = text_normalized or ""
    if "repactuacao" in z or "dedicacao exclusiva de mao de obra" in z or "convencao coletiva" in z:
        return "repactuacao"
    if "reequilibrio" in z or "restabelecimento do equilibrio" in z or "equilibrio economico financeiro" in z:
        return "reequilibrio"
    if "acrescimo" in z or "supressao" in z or "alteracao quantitativa" in z:
        return "acrescimo_supressao"
    if "reajuste" in z or "indice de reajustamento" in z:
        return "reajuste"
    if "prorrogacao" in z or "prorrogar" in z:
        return "prorrogacao"
    if "apostila" in z or "apostilamento" in z:
        return "apostilamento"
    return "outra"


def classify_planning_procedure(text_normalized: str) -> str:
    """Classificação conservadora; 'outro' é preferível a inferência frágil."""
    z = text_normalized or ""
    if "inexigibilidade" in z:
        return "contratacao_direta"
    if "dispensa" in z and ("registro de precos" in z or "srp" in z):
        return "dispensa_srp"
    if "dispensa" in z:
        return "contratacao_direta"
    if "concorrencia" in z:
        return "concorrencia"
    if ("registro de precos" in z or "sistema de registro de precos" in z or " srp " in f" {z} ") and "pregao" in z:
        return "pregao_srp"
    if "pregao" in z:
        service_terms = ["servico", "servicos", "prestacao continuada", "mao de obra"]
        if any(t in z for t in service_terms):
            return "pregao_servicos"
        return "pregao_bens"
    return "outro"
