from v8.core.models import AnalysisResult, DraftResult

ALLOWED_DRAFTS_BY_STAGE = {
    "triagem": {"despacho_diligencia"},
    "apuracao_inicial": {"despacho_instauracao", "despacho_diligencia"},
    "instaurado": {"notificacao_instauracao"},
    "instauracao_sancionadora_autorizada": {"despacho_instauracao"},
    "aguardando_defesa": {"certidao_prazo"},
    "defesa_apresentada": {"despacho_diligencia"},
    "instrucao_pos_defesa": {"relatorio_conclusivo"},
    "relatorio_conclusivo": {"decisao"},
    "julgamento": {"notificacao_decisao"},
    "recurso": {"decisao_recurso"},
}


def _profile_lines(a: AnalysisResult) -> list[str]:
    p = a.profile
    return [
        f"Processo: {p.process_number or p.origin_process or '[NÚMERO — CONFERIR]'}",
        f"Empresa/Interessado: {p.company or '[NÃO IDENTIFICADO COM SEGURANÇA]'}",
        f"CNPJ: {p.cnpj or '[NÃO IDENTIFICADO COM SEGURANÇA]'}",
        f"Objeto: {p.object_description or '[OBJETO — CONFERIR NOS AUTOS]'}",
        f"Quantidade: {p.quantity or '[QUANTIDADE NÃO IDENTIFICADA COM SEGURANÇA]'}",
    ]


def _source_ids(a: AnalysisResult) -> list[str]:
    ids = []
    for ev in a.evidence:
        if ev.document_id not in ids:
            ids.append(ev.document_id)
    if not ids:
        ids = [d.id for d in a.documents[:5]]
    return ids[:8]


def _header(title: str, a: AnalysisResult) -> list[str]:
    return [
        title,
        "",
        *_profile_lines(a),
        "",
        "MINUTA ASSISTIDA — REVISÃO HUMANA OBRIGATÓRIA",
        "",
    ]


def _despacho_instauracao(a: AnalysisResult) -> str:
    lines = _header("MINUTA — DESPACHO DE INSTAURAÇÃO", a)
    if a.stage.key == "instauracao_sancionadora_autorizada":
        lines += [
            "I — CONTEXTO",
            "",
            "Conforme os elementos do processo de origem, foi localizada decisão que autoriza a abertura de processo administrativo sancionador separado para apuração de eventual responsabilidade contratual.",
            "",
            "A presente providência não representa reconhecimento antecipado de responsabilidade nem aplicação de sanção.",
            "",
            "II — PROVIDÊNCIAS",
            "",
            "1. Autue-se processo administrativo sancionador próprio, vinculado ao processo de origem acima identificado.",
            "2. Delimitem-se os fatos e as obrigações contratuais que serão objeto de apuração.",
            "3. Trasladem-se ou vinculem-se ao novo processo os documentos essenciais do processo de origem, com preservação de sua rastreabilidade.",
            "4. Identifique-se a norma municipal de competência e o rito aplicável ao procedimento sancionador.",
            "5. Após a autuação e conferência dos elementos mínimos, providencie-se a notificação/intimação da empresa para exercício do contraditório e da ampla defesa, na forma da norma aplicável.",
            "",
            "III — OBSERVAÇÃO",
            "",
            "As manifestações, defesas e decisões existentes no processo de origem devem ser consideradas como elementos contextuais e probatórios, sem serem automaticamente tratadas como atos do novo processo sancionador.",
        ]
    else:
        lines += [
            "Considerando os elementos constantes dos autos e a necessidade de apuração formal dos fatos, determino a instauração do procedimento cabível, sem antecipação de juízo quanto à responsabilidade.",
            "",
            "Providencie-se a delimitação dos fatos, a identificação dos documentos essenciais e a adoção dos atos de ciência e contraditório previstos na norma aplicável.",
        ]
    return "\n".join(lines)


def _notificacao_instauracao(a: AnalysisResult) -> str:
    lines = _header("MINUTA — NOTIFICAÇÃO DE INSTAURAÇÃO E ABERTURA DE PRAZO PARA DEFESA", a)
    lines += [
        "A empresa/interessado fica NOTIFICADA(O) acerca da instauração do procedimento administrativo destinado à apuração dos fatos descritos nos autos.",
        "",
        "Esta notificação possui natureza processual e não representa imputação definitiva de responsabilidade ou aplicação antecipada de sanção.",
        "",
        "Fica assegurado o direito de apresentar defesa escrita, documentos e requerer provas pertinentes no prazo previsto na norma aplicável.",
        "",
        "Prazo: [CONFERIR PRAZO NA NORMA APLICÁVEL]",
        "Canal oficial para protocolo: [CONFERIR]",
        "",
        "Deverá ser disponibilizado acesso aos documentos que fundamentam a instauração.",
    ]
    return "\n".join(lines)


def _certidao_prazo(a: AnalysisResult) -> str:
    return "\n".join(_header("MINUTA — CERTIDÃO DE CONTROLE DE PRAZO", a) + [
        "Certifico, para fins de instrução, que a notificação/intimação foi expedida e que o prazo para manifestação deverá ser conferido a partir da forma de ciência efetivamente comprovada nos autos.",
        "",
        "Data da ciência: [CONFERIR]",
        "Prazo aplicável: [CONFERIR NORMA]",
        "Data final: [CALCULAR APÓS CONFIRMAÇÃO DA CIÊNCIA]",
        "Manifestação recebida: [SIM/NÃO — CONFERIR]",
    ])


def _despacho_diligencia(a: AnalysisResult) -> str:
    return "\n".join(_header("MINUTA — DESPACHO DE DILIGÊNCIA", a) + [
        "Considerando a necessidade de completar a instrução antes da conclusão do procedimento, determino a realização das seguintes diligências:",
        "",
        "1. [INDICAR DOCUMENTO/INFORMAÇÃO A SER OBTIDA]",
        "2. [INDICAR UNIDADE OU RESPONSÁVEL]",
        "3. [INDICAR PRAZO E FORMA DE CUMPRIMENTO]",
        "",
        "Após o cumprimento, retornem os autos para análise.",
    ])


def _relatorio_conclusivo(a: AnalysisResult) -> str:
    return "\n".join(_header("MINUTA — RELATÓRIO CONCLUSIVO", a) + [
        "I — SÍNTESE DO PROCEDIMENTO",
        "",
        "[RESUMIR A INSTAURAÇÃO, A CIÊNCIA, A DEFESA E AS DILIGÊNCIAS REALIZADAS.]",
        "",
        "II — FATOS E EVIDÊNCIAS",
        "",
        "[ENFRENTAR OS FATOS COM INDICAÇÃO DO DOCUMENTO E DA PÁGINA.]",
        "",
        "III — DEFESA E ARGUMENTOS RELEVANTES",
        "",
        "[ANALISAR EXPRESSAMENTE OS ARGUMENTOS E PROVAS DA DEFESA.]",
        "",
        "IV — ENQUADRAMENTO",
        "",
        "[CONFERIR NORMA, TIPIFICAÇÃO E EVENTUAIS ELEMENTOS DE DOSIMETRIA.]",
        "",
        "V — CONCLUSÃO",
        "",
        "[APRESENTAR CONCLUSÃO MOTIVADA, SEM SUBSTITUIR A DECISÃO DA AUTORIDADE COMPETENTE.]",
    ])


def _decisao(a: AnalysisResult) -> str:
    return "\n".join(_header("MINUTA — DECISÃO ADMINISTRATIVA", a) + [
        "Vistos e examinados os autos.",
        "",
        "Considerando a instrução, o relatório conclusivo e as manifestações constantes do processo, passa-se à decisão.",
        "",
        "[EXAMINAR FATOS, DEFESA, PROVAS, FUNDAMENTO JURÍDICO E, SE CABÍVEL, DOSIMETRIA.]",
        "",
        "DECIDO:",
        "",
        "[INSERIR DECISÃO MOTIVADA DA AUTORIDADE COMPETENTE.]",
    ])


def _notificacao_decisao(a: AnalysisResult) -> str:
    return "\n".join(_header("MINUTA — NOTIFICAÇÃO DE DECISÃO", a) + [
        "Fica a parte interessada NOTIFICADA da decisão proferida no procedimento acima identificado.",
        "",
        "Síntese da decisão: [INSERIR CONTEÚDO DA DECISÃO, SEM ALTERAR SEU SENTIDO.]",
        "",
        "Prazo e forma de eventual recurso: [CONFERIR NORMA APLICÁVEL]",
        "Canal oficial: [CONFERIR]",
    ])


def _decisao_recurso(a: AnalysisResult) -> str:
    return "\n".join(_header("MINUTA — DECISÃO EM RECURSO", a) + [
        "I — RELATÓRIO",
        "",
        "[RESUMIR A DECISÃO RECORRIDA E AS RAZÕES RECURSAIS.]",
        "",
        "II — FUNDAMENTAÇÃO",
        "",
        "[ANALISAR OS ARGUMENTOS DO RECURSO E AS PROVAS PERTINENTES.]",
        "",
        "III — DECISÃO",
        "",
        "[DECIDIR O RECURSO DE FORMA MOTIVADA.]",
    ])


BUILDERS = {
    "despacho_instauracao": ("Despacho de instauração", _despacho_instauracao),
    "notificacao_instauracao": ("Notificação de instauração", _notificacao_instauracao),
    "certidao_prazo": ("Certidão de controle de prazo", _certidao_prazo),
    "despacho_diligencia": ("Despacho de diligência", _despacho_diligencia),
    "relatorio_conclusivo": ("Relatório conclusivo", _relatorio_conclusivo),
    "decisao": ("Decisão administrativa", _decisao),
    "notificacao_decisao": ("Notificação de decisão", _notificacao_decisao),
    "decisao_recurso": ("Decisão em recurso", _decisao_recurso),
}


def generate_draft(a: AnalysisResult, kind: str | None = None) -> DraftResult:
    stage_key = a.stage.key
    requested = kind or a.stage.suggested_draft
    allowed = ALLOWED_DRAFTS_BY_STAGE.get(stage_key, set())

    if requested not in allowed:
        raise ValueError(
            f"A minuta '{requested}' não é compatível com o estágio '{stage_key}'. "
            f"Permitidas: {', '.join(sorted(allowed)) or 'nenhuma'}."
        )
    if requested not in BUILDERS:
        raise ValueError("Tipo de minuta ainda não implementado na V8.")

    title, builder = BUILDERS[requested]
    warnings = [
        "Conferir competência, rito, prazo e normas municipais antes da expedição.",
        "A minuta não substitui revisão jurídica ou decisão da autoridade competente.",
    ]
    return DraftResult(
        kind=requested,
        title=title,
        stage_key=stage_key,
        text=builder(a),
        source_document_ids=_source_ids(a),
        warnings=warnings,
    )
