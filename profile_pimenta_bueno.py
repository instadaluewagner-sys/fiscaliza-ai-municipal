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
