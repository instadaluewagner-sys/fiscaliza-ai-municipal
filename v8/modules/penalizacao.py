import re
import unicodedata
from v8.core.models import AnalysisResult, ChecklistItem, Document, PageRef, PendingItem, ProcessProfile, StageResult
from v8.services.evidence import evidence_from_document
from v8.services.timeline import build_timeline
from v8.services.quality import validate_analysis_integrity

def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value).strip().lower()

def docs_by_type(documents: list[Document]) -> dict[str, list[Document]]:
    out = {}
    for doc in documents:
        out.setdefault(doc.type, []).append(doc)
    return out

def find_first(text: str, patterns: list[str]):
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.I)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return None

def _iter_doc_pages(doc: Document):
    if doc.page_texts:
        for page in sorted(doc.page_texts):
            yield page, doc.page_texts[page]
    else:
        yield doc.page_start, doc.text


def _find_sourced(
    documents: list[Document],
    patterns: list[str],
    preferred_types: tuple[str, ...] | None = None,
    fallback_all: bool = True,
):
    preferred = [
        d for d in documents
        if not preferred_types or d.type in preferred_types
    ]
    ordered = preferred[:]
    if fallback_all:
        ordered += [d for d in documents if d not in preferred]

    for doc in ordered:
        for page, text in _iter_doc_pages(doc):
            for pattern in patterns:
                m = re.search(pattern, text, flags=re.I)
                if m:
                    value = re.sub(r"\s+", " ", m.group(1)).strip(" \t\n:;,.–—-")
                    if value:
                        return value, PageRef(
                            file=doc.file,
                            page=page,
                            document_id=doc.id,
                        )
    return None, None


def _find_all_identifiers(
    documents: list[Document],
    pattern: str,
    preferred_types: tuple[str, ...],
) -> tuple[list[str], PageRef | None]:
    values = []
    first_source = None
    for doc in documents:
        if doc.type not in preferred_types:
            continue
        for page, text in _iter_doc_pages(doc):
            for m in re.finditer(pattern, text, flags=re.I):
                value = re.sub(r"\s+", " ", m.group(1)).strip(" \t\n:;,.–—-")
                if value and value not in values:
                    values.append(value)
                    if first_source is None:
                        first_source = PageRef(file=doc.file, page=page, document_id=doc.id)
    return values, first_source


def _safe_quantity_sourced(documents: list[Document]):
    patterns = [
        r"(?:quantidade\s+total|quantidade\s+contratada|total\s+contratado)\s*[:.-]?\s*(\d{1,7}\s+(?:kits?|unidades?|itens?|caixas?|frascos?|equipamentos?)(?:\s+de\s+[^.,;\n]{2,80})?)",
        r"(?:objeto|fornecimento|aquisi[cç][aã]o)\s+(?:de\s+)?(\d{1,7}\s+(?:kits?|unidades?|itens?|caixas?|frascos?|equipamentos?)(?:\s+de\s+[^.,;\n]{2,80})?)",
    ]
    return _find_sourced(
        documents,
        patterns,
        preferred_types=("contrato","ata_registro_precos","empenho","ordem_fornecimento","termo_referencia"),
        fallback_all=False,
    )


def build_profile(documents: list[Document]) -> ProcessProfile:
    sources: dict[str, PageRef] = {}

    process_number, src = _find_sourced(
        documents,
        [r"Processo Administrativo de Penaliza[cç][aã]o\s*(?:n[ºo.]?)?\s*[:.-]?\s*([0-9./-]+)"],
    )
    if src:
        sources["process_number"] = src

    origin_process, src = _find_sourced(
        documents,
        [
            r"(?:Processo|Protocolo)\s+(?:de\s+origem\s+)?(?:n[ºo.]?)?\s*[:.-]?\s*([0-9][0-9./-]{2,})",
            r"\bPROCESSO\s+N[ºO.]?\s*[:.-]\s*([0-9][0-9./-]{2,})",
        ],
    )
    if src:
        sources["origin_process"] = src

    preferred_contractual = (
        "contrato","ata_registro_precos","empenho","ordem_fornecimento",
        "termo_referencia","notificacao","decisao","defesa"
    )

    company, src = _find_sourced(
        documents,
        [
            r"(?:Empresa|Contratada|Interessada)\s*[:.-]\s*([^\n]{3,120})",
            r"\bempresa\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9][A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 .&-]{4,100}(?:LTDA|S/A|EIRELI))\b",
        ],
        preferred_types=preferred_contractual,
    )
    if src:
        sources["company"] = src

    cnpj, src = _find_sourced(
        documents,
        [r"\bCNPJ(?:/MF)?\s*[:.-]?\s*([0-9./-]{14,20})"],
        preferred_types=preferred_contractual,
    )
    if src:
        sources["cnpj"] = src

    pregao, src = _find_sourced(
        documents,
        [r"\bPreg[aã]o(?:\s+Eletr[oô]nico)?\s*(?:n[ºo.]?|n[uú]mero)?\s*[:.-]?\s*([0-9./-]+)"],
        preferred_types=("pregao","edital","contrato","ata_registro_precos","notificacao","decisao"),
    )
    if src:
        sources["pregao"] = src

    ata, src = _find_sourced(
        documents,
        [r"\bAta\s+de\s+Registro\s+de\s+Pre[cç]os\s*(?:n[ºo.]?|n[uú]mero)?\s*[:.-]?\s*([0-9./-]+)"],
        preferred_types=("ata_registro_precos","contrato","ordem_fornecimento","notificacao"),
    )
    if src:
        sources["ata"] = src

    contrato, src = _find_sourced(
        documents,
        [
            r"\bContrato(?:\s+Administrativo|\s+de\s+Fornecimento(?:\s+de\s+Mercadorias)?)?\s*(?:n[ºo.]?|n[uú]mero)?\s*[:.-]?\s*([0-9./-]+)"
        ],
        preferred_types=("contrato","notificacao","decisao","parecer_juridico","defesa"),
    )
    if src:
        sources["contrato"] = src

    empenhos, src = _find_all_identifiers(
        documents,
        r"\b(?:Nota\s+de\s+Empenho|Empenho)\s*(?:n[ºo.]?|n[uú]mero)?\s*[:.-]?\s*([0-9./-]+)",
        preferred_types=("empenho","contrato","ordem_fornecimento","relatorio_tecnico","notificacao"),
    )
    if src:
        sources["empenhos"] = src

    object_description, src = _find_sourced(
        documents,
        [
            r"Objeto(?:\s+do\s+Contrato)?\s*[:.-]\s*([^\n]{5,180})",
            r"\btem\s+por\s+objeto\s+(?:o\s+)?([^\n.]{5,180})",
        ],
        preferred_types=("contrato","ata_registro_precos","termo_referencia","notificacao","decisao"),
    )
    if src:
        sources["object_description"] = src

    quantity, src = _safe_quantity_sourced(documents)
    if src:
        sources["quantity"] = src

    return ProcessProfile(
        process_number=process_number,
        origin_process=origin_process,
        company=company,
        cnpj=cnpj,
        pregao=pregao,
        ata=ata,
        contrato=contrato,
        empenhos=empenhos,
        object_description=object_description,
        quantity=quantity,
        sources=sources,
    )

def item(key: str, label: str, status: str, reason: str, docs=None) -> ChecklistItem:
    docs = docs or []
    return ChecklistItem(
        key=key,
        label=label,
        status=status,
        reason=reason,
        document_ids=[d.id for d in docs],
        pages=sorted({p for d in docs for p in d.pages}),
    )

def build_checklist(documents: list[Document], stage: StageResult | None = None) -> list[ChecklistItem]:
    by = docs_by_type(documents)
    all_text = norm("\n".join(d.text for d in documents))

    mentions_pregao = bool(re.search(r"\bpregao(?: eletronico)?\b", all_text))
    mentions_arp = "ata de registro de precos" in all_text or bool(re.search(r"\barp\b", all_text))
    mentions_empenho = "nota de empenho" in all_text or bool(re.search(r"\bempenhos?\b", all_text))
    mentions_ordem = "ordem de fornecimento" in all_text or "autorizacao de fornecimento" in all_text

    result = [
        item(
            "pregao",
            "Pregão / processo licitatório",
            "located" if by.get("pregao") else ("inconclusive" if mentions_pregao else "not_found"),
            "Peça autônoma localizada." if by.get("pregao") else (
                "Há referência ao pregão nos autos, mas a peça autônoma não foi segmentada."
                if mentions_pregao else "Não foi localizada referência suficiente ao procedimento licitatório."
            ),
            by.get("pregao"),
        ),
        item(
            "ata",
            "Ata de Registro de Preços",
            "located" if by.get("ata_registro_precos") else ("inconclusive" if mentions_arp else "not_applicable"),
            "Peça autônoma localizada." if by.get("ata_registro_precos") else (
                "Há referência a ARP/Ata; conferir se a Ata integra os autos."
                if mentions_arp else "Não há evidência suficiente de contratação via Ata de Registro de Preços."
            ),
            by.get("ata_registro_precos"),
        ),
        item(
            "contrato",
            "Contrato / instrumento equivalente",
            "located" if by.get("contrato") else "inconclusive",
            "Peça autônoma localizada." if by.get("contrato") else "Contrato formal não foi segmentado; conferir se o instrumento é substituído por empenho/ordem ou se está apenas referenciado.",
            by.get("contrato"),
        ),
        item(
            "empenho",
            "Nota de Empenho",
            "located" if by.get("empenho") else ("inconclusive" if mentions_empenho else "not_found"),
            "Peça autônoma localizada." if by.get("empenho") else (
                "Há menção a empenho(s), mas a Nota de Empenho não foi segmentada como peça autônoma."
                if mentions_empenho else "Não foi localizada Nota de Empenho nem referência segura a empenho."
            ),
            by.get("empenho"),
        ),
        item(
            "ordem",
            "Ordem / autorização de fornecimento",
            "located" if by.get("ordem_fornecimento") else ("inconclusive" if mentions_ordem else "not_applicable"),
            "Peça autônoma localizada." if by.get("ordem_fornecimento") else (
                "Há referência à ordem/autorização de fornecimento; conferir a peça."
                if mentions_ordem else "Não há evidência suficiente de que este instrumento seja aplicável ao caso."
            ),
            by.get("ordem_fornecimento"),
        ),
        item(
            "apuracao",
            "Relatório técnico / comunicação do fato",
            "located" if (by.get("relatorio_tecnico") or by.get("oficio")) else "not_found",
            "Elemento autônomo de apuração localizado." if (by.get("relatorio_tecnico") or by.get("oficio")) else "É necessário elemento que descreva o fato e a execução contratual.",
            (by.get("relatorio_tecnico") or []) + (by.get("oficio") or []),
        ),
        item(
            "notificacao",
            "Notificação / intimação do PAS",
            "located" if (by.get("notificacao") or by.get("intimacao")) else "not_found",
            "Ato de ciência/contraditório localizado." if (by.get("notificacao") or by.get("intimacao")) else "Não foi localizado ato de ciência/abertura do contraditório.",
            (by.get("notificacao") or []) + (by.get("intimacao") or []),
        ),
        item(
            "defesa",
            "Defesa / manifestação no PAS",
            "located" if by.get("defesa") else "inconclusive",
            "Peça autônoma de defesa localizada." if by.get("defesa") else "A ausência pode significar prazo em curso, revelia ou fase ainda não alcançada.",
            by.get("defesa"),
        ),
        item(
            "parecer_tecnico",
            "Parecer / análise técnica",
            "located" if (by.get("parecer_tecnico") or by.get("relatorio_tecnico")) else "inconclusive",
            "Análise técnica localizada." if (by.get("parecer_tecnico") or by.get("relatorio_tecnico")) else "A necessidade e suficiência da análise técnica dependem da instrução e do caso concreto.",
            (by.get("parecer_tecnico") or []) + (by.get("relatorio_tecnico") or []),
        ),
        item(
            "parecer_juridico",
            "Parecer jurídico",
            "located" if by.get("parecer_juridico") else "inconclusive",
            "Parecer jurídico localizado." if by.get("parecer_juridico") else "Conferir se o fluxo municipal exige manifestação jurídica nesta fase.",
            by.get("parecer_juridico"),
        ),
        item(
            "relatorio_conclusivo",
            "Relatório conclusivo da comissão",
            "located" if by.get("relatorio_conclusivo") else "not_found",
            "Relatório conclusivo localizado." if by.get("relatorio_conclusivo") else "Peça não localizada.",
            by.get("relatorio_conclusivo"),
        ),
        item(
            "decisao",
            "Decisão sancionadora",
            "located" if by.get("decisao") else "not_found",
            "Decisão localizada." if by.get("decisao") else "Decisão sancionadora não localizada.",
            by.get("decisao"),
        ),
        item(
            "recurso",
            "Recurso / ciência da decisão",
            "located" if by.get("recurso") else "inconclusive",
            "Recurso localizado." if by.get("recurso") else "A aplicabilidade depende de decisão e abertura da fase recursal.",
            by.get("recurso"),
        ),
    ]

    if not stage:
        return result

    rows = {row.key: row for row in result}

    def set_state(key: str, status: str, reason: str, clear_sources: bool = False):
        row = rows.get(key)
        if not row:
            return
        row.status = status
        row.reason = reason
        if clear_sources:
            row.document_ids = []
            row.pages = []

    # Aplicabilidade por fase. Itens de etapas futuras não viram "pendência".
    if stage.key in {"triagem", "apuracao_inicial"}:
        for key, reason in {
            "notificacao":"Contraditório ainda não é exigível antes da instauração.",
            "defesa":"Defesa pertence a etapa futura.",
            "parecer_tecnico":"Análise técnica sancionadora depende da instauração e da instrução.",
            "parecer_juridico":"Manifestação jurídica sancionadora depende do rito e da fase.",
            "relatorio_conclusivo":"Relatório conclusivo pertence a etapa futura.",
            "decisao":"Decisão sancionadora pertence a etapa futura.",
            "recurso":"Fase recursal ainda não iniciada.",
        }.items():
            set_state(key, "not_applicable", reason, clear_sources=True)

    elif stage.key == "instaurado":
        set_state("notificacao","not_found","Processo instaurado sem ato de notificação/intimação do PAS localizado.",True)
        for key, reason in {
            "defesa":"Defesa ainda não é exigível antes da ciência da instauração.",
            "relatorio_conclusivo":"Relatório conclusivo pertence a etapa posterior à instrução.",
            "decisao":"Decisão sancionadora pertence a etapa posterior ao relatório conclusivo.",
            "recurso":"Fase recursal ainda não iniciada.",
        }.items():
            set_state(key,"not_applicable",reason,True)

    elif stage.key == "aguardando_defesa":
        set_state("defesa","inconclusive","Contraditório foi aberto, mas é necessário conferir se o prazo ainda está em curso, se houve defesa ou se ocorreu revelia.",False)
        for key, reason in {
            "relatorio_conclusivo":"Relatório conclusivo ainda depende do encerramento da fase de defesa/instrução.",
            "decisao":"Decisão sancionadora pertence a etapa posterior.",
            "recurso":"Fase recursal ainda não iniciada.",
        }.items():
            set_state(key,"not_applicable",reason,True)

    elif stage.key == "defesa_apresentada":
        set_state("relatorio_conclusivo","inconclusive","Defesa localizada; conferir necessidade de diligências e se a instrução já permite relatório conclusivo.",False)
        set_state("decisao","not_applicable","Decisão ainda depende da conclusão da instrução.",True)
        set_state("recurso","not_applicable","Fase recursal ainda não iniciada.",True)

    elif stage.key == "instrucao_pos_defesa":
        set_state("relatorio_conclusivo","not_found","Instrução pós-defesa identificada, mas o relatório conclusivo da comissão ainda não foi localizado.",True)
        set_state("decisao","not_applicable","Decisão depende do relatório conclusivo e do encaminhamento à autoridade.",True)
        set_state("recurso","not_applicable","Fase recursal ainda não iniciada.",True)

    elif stage.key == "relatorio_conclusivo":
        set_state("decisao","not_found","Relatório conclusivo localizado; decisão da autoridade competente ainda não foi localizada.",True)
        set_state("recurso","not_applicable","Fase recursal depende da decisão.",True)

    elif stage.key == "julgamento":
        set_state("recurso","inconclusive","Decisão sancionadora localizada; conferir ciência, prazo e eventual recurso.",False)

    if stage.key == "instauracao_sancionadora_autorizada":
        # O PDF analisado é o processo de origem. Atos nele existentes podem pertencer
        # à execução/extinção contratual e não preenchem artificialmente o futuro PAS.
        auth = item(
            "autorizacao_pas",
            "Decisão de origem que autoriza instaurar o PAS",
            "located",
            "Foi localizada decisão que autoriza a abertura de processo administrativo sancionador separado.",
            by.get("decisao"),
        )
        result.insert(6, auth)
        rows["autorizacao_pas"] = auth

        set_state(
            "notificacao",
            "not_applicable",
            "A notificação do PAS pertence à etapa seguinte, após a autuação/instauração. Notificações do processo de origem permanecem apenas como contexto.",
            True,
        )
        set_state(
            "defesa",
            "not_applicable",
            "A defesa sancionadora ainda não é exigível. Manifestações do processo de origem permanecem apenas como contexto probatório.",
            True,
        )
        set_state(
            "parecer_tecnico",
            "inconclusive",
            "Pareceres do processo de origem podem instruir o futuro PAS, mas a suficiência da instrução sancionadora deve ser conferida após a autuação.",
            False,
        )
        set_state(
            "parecer_juridico",
            "inconclusive",
            "Parecer jurídico do processo de origem pode subsidiar a instauração, mas não equivale automaticamente à análise final do PAS.",
            False,
        )
        set_state("relatorio_conclusivo","not_applicable","Relatório conclusivo da comissão sancionadora pertence a fase futura do PAS.",True)
        set_state("decisao","not_applicable","A decisão localizada é do processo de origem e não é decisão sancionadora final.",True)
        set_state("recurso","not_applicable","Fase recursal sancionadora ainda não iniciada.",True)

    return result


def build_pending_items(checklist: list[ChecklistItem], stage: StageResult) -> list[PendingItem]:
    critical_by_stage = {
        "instaurado": {"notificacao"},
        "instrucao_pos_defesa": {"relatorio_conclusivo"},
        "relatorio_conclusivo": {"decisao"},
    }
    critical = critical_by_stage.get(stage.key, set())
    pending: list[PendingItem] = []

    for row in checklist:
        if row.status == "not_found":
            pending.append(
                PendingItem(
                    key=row.key,
                    label=row.label,
                    kind="missing",
                    severity="high" if row.key in critical else "medium",
                    reason=row.reason,
                )
            )
        elif row.status == "inconclusive":
            pending.append(
                PendingItem(
                    key=row.key,
                    label=row.label,
                    kind="review",
                    severity="low",
                    reason=row.reason,
                )
            )

    pending.append(
        PendingItem(
            key="next_action",
            label=stage.label,
            kind="next_step",
            severity="medium",
            reason=stage.next_action,
        )
    )
    return pending

def _has_current_pas_context(documents: list[Document]) -> bool:
    heading_patterns = [
        r"processo administrativo de penalizacao\s*(?:n|no|nº|n\.)",
        r"processo administrativo sancionador\s*(?:n|no|nº|n\.)",
        r"notificacao.{0,100}instauracao.{0,120}processo administrativo",
        r"instaurad[oa].{0,120}processo administrativo (?:sancionador|de penalizacao)",
    ]
    for doc in documents:
        head = norm(doc.text[:1800])
        if any(re.search(p, head) for p in heading_patterns):
            return True
    return False


def determine_stage(documents: list[Document]) -> StageResult:
    by = docs_by_type(documents)
    all_text = norm("\n".join(d.text for d in documents))
    decision_texts = [norm(d.text) for d in by.get("decisao", [])]

    authorizes_new_pas = any(
        ("autorizo" in t or "autoriza" in t)
        and (
            "abertura de processo administrativo sancionador" in t
            or "instauracao de processo administrativo sancionador" in t
        )
        for t in decision_texts
    )

    final_sanction = any(
        any(k in t for k in [
            "aplico a sancao",
            "aplica-se a sancao",
            "aplico a penalidade",
            "multa",
            "impedimento de licitar",
            "declaracao de inidoneidade",
        ])
        and any(k in t for k in [
            "processo administrativo sancionador",
            "processo administrativo de penalizacao",
            "penalidade",
            "sancao",
        ])
        for t in decision_texts
    )

    current_pas = _has_current_pas_context(documents)

    # 1. Uma decisão do processo de origem que só AUTORIZA abrir um PAS
    # não pode ser tratada como julgamento sancionador, mesmo que haja defesa,
    # notificação ou recurso no processo contratual de origem.
    if authorizes_new_pas and not final_sanction and not current_pas:
        return StageResult(
            key="instauracao_sancionadora_autorizada",
            label="Instauração sancionadora autorizada",
            confidence=.97,
            rationale="Foi localizada decisão no processo de origem que autoriza a abertura de processo administrativo sancionador separado; isso não equivale a julgamento de penalidade.",
            next_action="Autuar/instaurar o processo sancionador, delimitar fatos e documentos de origem e então assegurar o contraditório conforme a norma aplicável.",
            suggested_draft="despacho_instauracao",
        )

    # 2. Recurso só caracteriza fase recursal sancionadora quando há decisão
    # sancionadora final ou contexto inequívoco do PAS.
    if by.get("recurso") and final_sanction:
        return StageResult(
            key="recurso",
            label="Fase recursal",
            confidence=.96,
            rationale="Recurso administrativo localizado após decisão sancionadora.",
            next_action="Analisar o recurso e conferir os efeitos da decisão recorrida.",
            suggested_draft="decisao_recurso",
        )

    if by.get("decisao") and final_sanction:
        return StageResult(
            key="julgamento",
            label="Julgamento sancionador identificado",
            confidence=.96,
            rationale="Decisão sancionadora com comando de aplicação de penalidade localizada.",
            next_action="Dar ciência da decisão, controlar eventual prazo recursal e registrar a sanção quando cabível.",
            suggested_draft="notificacao_decisao",
        )

    # 3. Os atos abaixo só são interpretados como fases do PAS quando o processo
    # analisado contém marcador inequívoco de que o PAS já existe.
    if current_pas:
        if by.get("relatorio_conclusivo"):
            return StageResult(
                key="relatorio_conclusivo",
                label="Relatório conclusivo elaborado",
                confidence=.95,
                rationale="Relatório conclusivo da comissão localizado no contexto do processo sancionador.",
                next_action="Encaminhar os autos à autoridade competente para julgamento.",
                suggested_draft="decisao",
            )
        if by.get("defesa") and (by.get("parecer_tecnico") or by.get("parecer_juridico") or by.get("relatorio_tecnico")):
            return StageResult(
                key="instrucao_pos_defesa",
                label="Instrução após defesa",
                confidence=.90,
                rationale="Defesa e elementos de análise posteriores estão presentes no processo sancionador.",
                next_action="Concluir a instrução e elaborar relatório conclusivo enfrentando os argumentos relevantes.",
                suggested_draft="relatorio_conclusivo",
            )
        if by.get("defesa"):
            return StageResult(
                key="defesa_apresentada",
                label="Defesa apresentada",
                confidence=.94,
                rationale="Peça autônoma de defesa localizada no processo sancionador.",
                next_action="Analisar a defesa, confrontar provas e realizar diligências se necessárias.",
                suggested_draft="despacho_diligencia",
            )
        if by.get("notificacao") or by.get("intimacao"):
            return StageResult(
                key="aguardando_defesa",
                label="Contraditório aberto",
                confidence=.90,
                rationale="Notificação/intimação de instauração localizada sem defesa autônoma identificada.",
                next_action="Controlar o prazo de defesa e certificar o decurso ou recebimento da manifestação.",
                suggested_draft="certidao_prazo",
            )
        return StageResult(
            key="instaurado",
            label="Processo sancionador instaurado",
            confidence=.88,
            rationale="Há marcador inequívoco de existência do processo sancionador, sem ato posterior de contraditório identificado.",
            next_action="Expedir notificação/intimação de instauração e abertura de prazo para defesa.",
            suggested_draft="notificacao_instauracao",
        )

    # 4. Sem contexto inequívoco de PAS, defesa/notificação podem pertencer ao
    # processo contratual de origem. Permanecemos em apuração/preparação.
    if by.get("relatorio_tecnico") or by.get("parecer_tecnico") or by.get("oficio") or by.get("notificacao") or by.get("defesa"):
        return StageResult(
            key="apuracao_inicial",
            label="Apuração / processo de origem",
            confidence=.84,
            rationale="Há documentos sobre execução, comunicação ou manifestação, mas não foi identificado processo sancionador já instaurado.",
            next_action="Conferir pressupostos, delimitar o fato e verificar se há decisão/competência para instaurar o processo sancionador.",
            suggested_draft="despacho_instauracao",
        )

    return StageResult(
        key="triagem",
        label="Triagem",
        confidence=.65,
        rationale="Elementos insuficientes para determinar fase sancionadora posterior.",
        next_action="Completar a instrução inicial e confirmar a origem do fato.",
        suggested_draft="despacho_diligencia",
    )

def build_evidence(documents: list[Document], stage: StageResult | None = None):
    evidence = []
    for doc in documents:
        z = norm(doc.text)
        if any(k in z for k in ["nao houve entrega","inexecucao"]):
            evidence.append(evidence_from_document(doc,"Execução/inexecução registrada",[r"n[aã]o houve entrega",r"inexecu[cç][aã]o"],.94))
        if doc.type == "defesa":
            fact = (
                "Defesa/manifestação localizada no processo de origem; não equivale à defesa do futuro PAS"
                if stage and stage.key == "instauracao_sancionadora_autorizada"
                else "Defesa administrativa apresentada"
            )
            evidence.append(evidence_from_document(doc,fact,[r"defesa",r"alega",r"requer"],.97))
        if doc.type == "decisao":
            fact = (
                "Decisão de origem que autoriza a abertura de processo sancionador separado"
                if stage and stage.key == "instauracao_sancionadora_autorizada"
                else "Decisão administrativa localizada"
            )
            evidence.append(evidence_from_document(doc,fact,[r"autoriz",r"decid",r"julgo",r"determino"],.95))
    return evidence[:12]

def analyze_penalizacao(documents: list[Document]) -> AnalysisResult:
    stage = determine_stage(documents)
    checklist = build_checklist(documents, stage)
    result = AnalysisResult(
        module="penalizacao",
        profile=build_profile(documents),
        documents=documents,
        checklist=checklist,
        evidence=build_evidence(documents, stage),
        timeline=build_timeline(documents),
        stage=stage,
        pending_items=build_pending_items(checklist, stage),
        warnings=[],
    )
    result.warnings = validate_analysis_integrity(result)
    return result
