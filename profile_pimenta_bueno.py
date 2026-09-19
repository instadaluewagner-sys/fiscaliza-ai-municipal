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
