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
        f"Processo Administrativo de Penalização: {p.process_number or '[NÚMERO — CONFERIR]'}",
        f"Processo/Protocolo de origem: {p.origin_process or '[ORIGEM — CONFERIR]'}",
        f"Pregão Eletrônico: {p.pregao or '[NÃO IDENTIFICADO COM SEGURANÇA]'}",
        f"Ata de Registro de Preços: {p.ata or '[NÃO IDENTIFICADA / CONFERIR APLICABILIDADE]'}",
        f"Contrato: {p.contrato or '[NÃO IDENTIFICADO COM SEGURANÇA]'}",
        f"Nota(s) de Empenho: {', '.join(p.empenhos) if p.empenhos else '[NÃO IDENTIFICADA(S) COM SEGURANÇA]'}",
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


def _legal_references(a: AnalysisResult) -> list[str]:
    import re
    refs = []
    text = "\n".join(doc.text for doc in a.documents)
    if re.search(r"Lei\s+(?:Federal\s+)?n?[º°.]?\s*14\.133(?:/|,\s*de\s*)2021", text, flags=re.I):
        refs.append("Lei Federal nº 14.133/2021")
    articles = []
    for m in re.finditer(r"\bart\.?\s*(\d{1,3}(?:-[A-Z])?)\b", text, flags=re.I):
        art = m.group(1)
        if art not in articles:
            articles.append(art)
    if refs and articles:
        refs[0] += " (arts. " + ", ".join(articles[:8]) + " identificados nos autos; conferir pertinência)"
    return refs


def _fact_paragraphs(a: AnalysisResult) -> list[str]:
    paragraphs = []
    p = a.profile
    if p.contrato or p.pregao or p.ata or p.empenhos:
        parts = []
        if p.pregao:
            parts.append(f"Pregão Eletrônico nº {p.pregao}")
        if p.ata:
            parts.append(f"Ata de Registro de Preços nº {p.ata}")
        if p.contrato:
            parts.append(f"Contrato nº {p.contrato}")
        if p.empenhos:
            parts.append("Nota(s) de Empenho nº " + ", ".join(p.empenhos))
        paragraphs.append(
            "Conforme consta nos autos, a contratação está relacionada a "
            + ", ".join(parts)
            + "."
        )

    if p.object_description:
        text = f"O objeto identificado nos autos consiste em {p.object_description.rstrip('.')}."
        if p.quantity:
            text += f" A quantidade identificada com suporte documental é {p.quantity}."
        paragraphs.append(text)

    for ev in a.evidence:
        if ev.key == "non_delivery":
            paragraphs.append(
                "Consta, ainda, registro de não entrega ou inexecução do objeto, "
                "circunstância que deverá ser apreciada em conjunto com os demais documentos, "
                "manifestações e provas produzidos durante a instrução."
            )

    if not paragraphs:
        paragraphs.append(
            "Os fatos que fundamentaram a instauração deverão ser descritos e conferidos "
            "diretamente nos documentos de origem antes da expedição desta notificação."
        )
    return paragraphs


def _notificacao_instauracao(a: AnalysisResult) -> str:
    p = a.profile
    origin = p.origin_process or "[PROCESSO/PROTOCOLO DE ORIGEM — CONFERIR]"
    pas = p.process_number or "[PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO — CONFERIR]"
    company = p.company or "[EMPRESA/INTERESSADO — CONFERIR]"
    cnpj = p.cnpj or "[CNPJ — CONFERIR]"
    refs = _legal_references(a)
    legal = "; ".join(refs) if refs else "[NORMAS E DISPOSITIVOS APLICÁVEIS — CONFERIR]"

    lines = [
        "NOTIFICAÇÃO EXTRAJUDICIAL Nº [NÚMERO]/[COMISSÃO OU UNIDADE]/[ÓRGÃO]/[MUNICÍPIO]",
        "",
        f"Processo/Protocolo de origem: nº {origin}",
        f"Processo Administrativo de Penalização: nº {pas}",
        f"Ata de Registro de Preços: nº {p.ata or '[NÃO IDENTIFICADA / CONFERIR APLICABILIDADE]'}",
        f"Pregão Eletrônico: nº {p.pregao or '[NÃO IDENTIFICADO COM SEGURANÇA]'}",
        f"Contrato: nº {p.contrato or '[NÃO IDENTIFICADO COM SEGURANÇA]'}",
        f"Nota(s) de Empenho: nº {', '.join(p.empenhos) if p.empenhos else '[NÃO IDENTIFICADA(S) COM SEGURANÇA]'}",
        f"Empresa: {company}",
        f"CNPJ: {cnpj}",
        "",
        "Assunto: Notificação de instauração de Processo Administrativo de Penalização e abertura de prazo para apresentação de defesa.",
        "",
        "[PREFEITURA/ÓRGÃO], pessoa jurídica de direito público interno, inscrita no CNPJ sob o nº [CNPJ DO ÓRGÃO], por intermédio de [COMISSÃO/UNIDADE COMPETENTE], representada neste ato por [NOME DO RESPONSÁVEL], [CARGO/FUNÇÃO], no uso das atribuições previstas em [NORMA DE COMPETÊNCIA] e [ATO DE DESIGNAÇÃO], NOTIFICA E INTIMA "
        + f"{company}, inscrita no CNPJ sob o nº {cnpj}, acerca da instauração do Processo Administrativo de Penalização nº {pas}, originado dos autos nº {origin}, destinado à apuração de possível descumprimento de obrigação relacionada à contratação identificada nesta notificação.",
        "",
        "A presente notificação possui caráter processual e não representa imputação definitiva de responsabilidade ou aplicação antecipada de penalidade. Sua finalidade é dar ciência dos fatos objeto de apuração e assegurar o exercício do contraditório e da ampla defesa.",
        "",
        "I — DOS FATOS E DA ORIGEM DA APURAÇÃO",
        "",
    ]
    for paragraph in _fact_paragraphs(a):
        lines += [paragraph, ""]

    lines += [
        "Os documentos constantes do processo deverão ser analisados em conjunto. Eventuais justificativas, manifestações e provas da empresa constituirão elementos relevantes para a instrução, sem produzir, isoladamente, conclusão automática quanto à existência ou inexistência de responsabilidade administrativa.",
        "",
        "II — DOS PONTOS A SEREM ESCLARECIDOS",
        "",
        "Na defesa, a empresa poderá esclarecer os fatos, demonstrar o cumprimento total ou parcial das obrigações, apresentar justificativas para eventual atraso, não entrega ou outra ocorrência, indicar as providências adotadas e juntar documentos capazes de comprovar suas alegações.",
        "",
        "Deverão ser especialmente considerados, quando pertinentes ao caso concreto, o nexo entre os fatos alegados e a obrigação contratual, a tempestividade das comunicações, as providências adotadas para viabilizar o cumprimento, a suficiência da documentação comprobatória e eventual impacto para a necessidade administrativa.",
        "",
        "III — DO ENQUADRAMENTO JURÍDICO PRELIMINAR",
        "",
        f"Foram identificadas nos autos referências jurídicas relacionadas ao procedimento: {legal}. A pertinência de cada dispositivo, bem como a norma municipal e as cláusulas específicas da contratação, deverá ser conferida antes da expedição.",
        "",
        "Os fatos poderão caracterizar, em tese, infração administrativa prevista na legislação aplicável e nos instrumentos da contratação. O enquadramento é preliminar e poderá ser mantido, alterado ou afastado após a análise da defesa e das provas produzidas, não representando decisão antecipada quanto à responsabilidade da empresa.",
        "",
        "IV — DAS EVENTUAIS CONSEQUÊNCIAS ADMINISTRATIVAS",
        "",
        "Caso, ao final da instrução e mediante decisão motivada da autoridade competente, seja reconhecida responsabilidade administrativa, somente poderá ser aplicada a consequência juridicamente cabível ao enquadramento definitivo, observados os limites legais, a norma local, as cláusulas da contratação e as circunstâncias efetivamente comprovadas.",
        "",
        "Na eventual análise de sanção deverão ser considerados os critérios legalmente aplicáveis ao caso, inclusive natureza e gravidade da conduta, peculiaridades concretas, circunstâncias agravantes ou atenuantes, danos eventualmente causados e os princípios da razoabilidade e da proporcionalidade, quando pertinentes.",
        "",
        "V — DO CONTRADITÓRIO, DA DEFESA E DAS PROVAS",
        "",
        "Fica a empresa NOTIFICADA E INTIMADA para apresentar defesa escrita e especificar as provas que pretenda produzir, no prazo de [PRAZO EM DIAS ÚTEIS — CONFERIR NORMA APLICÁVEL], contado na forma prevista na legislação e regulamentação do procedimento.",
        "",
        "A empresa poderá apresentar documentos, esclarecimentos, argumentos e provas pertinentes à elucidação dos fatos, especialmente aqueles relacionados ao cumprimento da obrigação, às justificativas apresentadas e às circunstâncias que possam ter impedido ou dificultado a execução contratual.",
        "",
        "As provas requeridas deverão ter sua pertinência indicada. Eventual indeferimento de prova deverá observar a norma aplicável e ser objeto de decisão fundamentada.",
        "",
        "VI — DA FORMA DE APRESENTAÇÃO",
        "",
        "A defesa e os respectivos documentos deverão ser encaminhados ao seguinte canal oficial: [E-MAIL/SISTEMA/PROTOCOLO OFICIAL — CONFERIR].",
        "",
        f"No campo destinado ao assunto deverá constar: DEFESA – PROCESSO ADMINISTRATIVO DE PENALIZAÇÃO Nº {pas} – {company}.",
        "",
        "VII — DO ACESSO AOS AUTOS",
        "",
        f"Deverá ser assegurado à empresa acesso aos documentos que fundamentam a instauração do Processo Administrativo de Penalização nº {pas}, mediante cópia integral dos autos ou forma equivalente de consulta admitida pelo órgão.",
        "",
        "VIII — DA AUSÊNCIA DE DEFESA",
        "",
        "A ausência de defesa no prazo estabelecido implicará o regular prosseguimento do procedimento, observadas exclusivamente as consequências previstas na legislação e na regulamentação aplicáveis. Não deverão ser acrescentados efeitos de revelia ou presunções que não estejam expressamente amparados pela norma do procedimento.",
        "",
        "IX — DAS PROVIDÊNCIAS POSTERIORES",
        "",
        "Apresentada a defesa, ou certificado o decurso do prazo, a unidade responsável deverá prosseguir com a instrução, apreciar os argumentos e as provas relevantes, realizar diligências quando necessárias e praticar os atos subsequentes previstos no rito aplicável.",
        "",
        "Concluída a instrução, será elaborado o ato técnico ou relatório cabível e os autos serão encaminhados à autoridade competente quando o rito assim exigir, preservando-se a motivação, o contraditório e a rastreabilidade dos elementos utilizados.",
        "",
        "[MUNICÍPIO/UF], [DATA].",
        "",
        "[NOME DO RESPONSÁVEL]",
        "[CARGO/FUNÇÃO]",
        "",
        "MINUTA ASSISTIDA — REVISÃO HUMANA OBRIGATÓRIA ANTES DA EXPEDIÇÃO.",
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
