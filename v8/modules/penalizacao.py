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


def _source_weight(doc_type: str) -> int:
    return {
        "contrato": 12,
        "ata_registro_precos": 11,
        "empenho": 11,
        "ordem_fornecimento": 10,
        "termo_referencia": 10,
        "notificacao": 10,
        "decisao": 9,
        "defesa": 8,
        "parecer_juridico": 8,
        "parecer_tecnico": 7,
        "relatorio_tecnico": 7,
        "oficio": 6,
        "pregao": 10,
        "edital": 9,
        "movimentacao_1doc": 2,
        "unclassified": 1,
    }.get(doc_type, 4)


def _page_ref(doc: Document, page: int) -> PageRef:
    return PageRef(file=doc.file, page=page, document_id=doc.id)


def _candidate_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", norm(value))


def _clean_company(value: str) -> str | None:
    value = re.sub(r"[\x00-\x1f\x7f]+", " ", value or "")
    value = re.sub(r"\s+", " ", value).strip(" \t\n:;,.–—-")
    value = re.sub(r"(?i)^\s*(?:a\s+|à\s+)?empresa\s+", "", value).strip()
    value = re.split(
        r"(?i)\b(?:CNPJ|CPF|Objeto|Contrato|Preg[aã]o|Ata\s+de\s+Registro|Assinado\s+por|Representante|Endere[cç]o|Telefone|E-?mail)\b",
        value,
        maxsplit=1,
    )[0].strip(" \t\n:;,.–—-")
    if len(value) < 4:
        return None
    bad = norm(value)
    if any(x in bad for x in [
        "assinado por",
        "verificacao das assinaturas",
        "verificação das assinaturas",
        "pessoa:",
        "responsavel:",
        "responsável:",
    ]):
        return None
    if re.fullmatch(r"[\d ./-]+", value):
        return None
    return value[:140]


def _collect_company_candidates(documents: list[Document]):
    candidates: dict[str, dict] = {}
    field_rx = re.compile(
        r"(?im)^\s*(INTERESSAD[AO]|CONTRATAD[AO]|NOTIFICAD[AO]|EMPRESA)\s*[:\-]\s*([^\n]{3,180})"
    )
    paired_rx = re.compile(
        r"(?i)\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9][A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 .&'/-]{3,120}?"
        r"(?:LTDA\.?|EIRELI|S/?A\.?|ME|EPP))\s*,?\s*(?:inscrit[ao]\s+no\s+)?CNPJ\b"
    )
    label_bonus = {
        "interessada": 8, "interessado": 8,
        "contratada": 8, "contratado": 8,
        "notificada": 8, "notificado": 8,
        "empresa": 5,
    }

    def add(value: str, doc: Document, page: int, bonus: int):
        cleaned = _clean_company(value)
        if not cleaned:
            return
        key = _candidate_key(cleaned)
        if not key:
            return
        score = _source_weight(doc.type) + bonus
        if re.search(r"(?i)\b(?:LTDA|EIRELI|S/?A|ME|EPP)\b", cleaned):
            score += 4
        item = candidates.setdefault(key, {
            "value": cleaned,
            "score": 0,
            "sources": [],
            "doc_ids": set(),
        })
        item["score"] += score
        item["sources"].append(_page_ref(doc, page))
        item["doc_ids"].add(doc.id)

    for doc in documents:
        for page, text in _iter_doc_pages(doc):
            for m in field_rx.finditer(text):
                add(m.group(2), doc, page, label_bonus.get(norm(m.group(1)), 4))
            for m in paired_rx.finditer(text):
                add(m.group(1), doc, page, 10)

    for item in candidates.values():
        item["score"] += 3 * len(item["doc_ids"])
    return candidates


def _select_candidate(candidates: dict[str, dict]):
    if not candidates:
        return None, None, [], []
    ranked = sorted(candidates.values(), key=lambda x: (x["score"], len(x["doc_ids"])), reverse=True)
    best = ranked[0]
    conflicts = [x["value"] for x in ranked[1:] if _candidate_key(x["value"]) != _candidate_key(best["value"])]
    conflict_sources = [x["sources"][0] for x in ranked[1:] if x["sources"]]
    return best["value"], best["sources"][0], conflicts, conflict_sources


def _format_cnpj(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 14:
        return value.strip()
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def _valid_cnpj(value: str) -> bool:
    digits = [int(x) for x in re.sub(r"\D", "", value or "")]
    if len(digits) != 14 or len(set(digits)) == 1:
        return False

    def digit(base, weights):
        remainder = sum(n * w for n, w in zip(base, weights)) % 11
        return 0 if remainder < 2 else 11 - remainder

    d1 = digit(digits[:12], [5,4,3,2,9,8,7,6,5,4,3,2])
    d2 = digit(digits[:12] + [d1], [6,5,4,3,2,9,8,7,6,5,4,3,2])
    return digits[12] == d1 and digits[13] == d2


def _collect_cnpj_candidates(documents: list[Document], company: str | None):
    candidates: dict[str, dict] = {}
    rx = re.compile(r"\b(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})\b")
    company_tokens = [
        token for token in re.findall(r"[A-Za-zÀ-ÿ0-9]+", company or "")
        if len(token) >= 5 and norm(token) not in {"comercio","empresa","ltda","eireli"}
    ][:4]

    for doc in documents:
        for page, text in _iter_doc_pages(doc):
            for m in rx.finditer(text):
                value = _format_cnpj(m.group(1))
                key = re.sub(r"\D", "", value)
                before = text[max(0,m.start()-240):m.start()]
                context = text[max(0,m.start()-320):min(len(text),m.end()+220)]
                z = norm(context)
                z_before = norm(before)

                company_positions = [
                    z_before.rfind(norm(token))
                    for token in company_tokens
                    if norm(token) in z_before
                ]
                company_pos = max(company_positions) if company_positions else -1
                government_positions = [
                    z_before.rfind(marker)
                    for marker in ["municipio", "prefeitura", "contratante", "procuradoria"]
                    if marker in z_before
                ]
                government_pos = max(government_positions) if government_positions else -1

                # O CNPJ é associado ao fornecedor quando o nome do fornecedor é
                # a entidade mais próxima ANTES do número. Isso evita atribuir ao
                # contratado o CNPJ do Município em contratos com as duas partes.
                paired = company_pos >= 0 and company_pos > government_pos
                explicit_supplier = paired and any(
                    marker in z
                    for marker in [
                        "inscrita no cnpj",
                        "inscrito no cnpj",
                        "contratada",
                        "interessada",
                        "notificado",
                        "notificada",
                        "empresa",
                    ]
                )

                score = _source_weight(doc.type)
                if _valid_cnpj(value):
                    score += 25
                else:
                    score -= 25
                if "inscrita no cnpj" in z or "inscrito no cnpj" in z:
                    score += 10
                if explicit_supplier:
                    score += 20
                elif paired:
                    score += 10

                item = candidates.setdefault(key, {
                    "value": value,
                    "score": 0,
                    "sources": [],
                    "doc_ids": set(),
                    "paired_sources": [],
                    "paired_doc_ids": set(),
                    "valid": _valid_cnpj(value),
                })
                item["score"] += score
                source = _page_ref(doc, page)
                item["sources"].append(source)
                item["doc_ids"].add(doc.id)
                if paired:
                    item["paired_sources"].append(source)
                    item["paired_doc_ids"].add(doc.id)

    for item in candidates.values():
        item["score"] += 3 * len(item["doc_ids"])
        item["score"] += 8 * len(item["paired_doc_ids"])
    return candidates


def _select_cnpj_candidate(candidates: dict[str, dict]):
    if not candidates:
        return None, None, [], []

    values = list(candidates.values())
    paired_valid = [x for x in values if x["paired_sources"] and x["valid"]]
    paired_any = [x for x in values if x["paired_sources"]]
    valid_any = [x for x in values if x["valid"]]

    # Para identificar o CNPJ da empresa, vínculo textual com a empresa tem
    # precedência sobre CNPJs de prefeitura, procuradoria ou outros participantes.
    pool = paired_valid or paired_any or valid_any or values
    ranked = sorted(
        pool,
        key=lambda x: (
            bool(x["valid"]),
            len(x["paired_doc_ids"]),
            x["score"],
            len(x["doc_ids"]),
        ),
        reverse=True,
    )
    best = ranked[0]
    source_pool = best["paired_sources"] or best["sources"]
    source = source_pool[0] if source_pool else None

    # Divergência só inclui outro CNPJ plausivelmente associado à MESMA empresa.
    # CNPJ do Município ou de terceiros não vira "conflito cadastral" do fornecedor.
    conflict_pool = paired_any if paired_any else pool
    conflicts = []
    conflict_sources = []
    for item in sorted(conflict_pool, key=lambda x: x["score"], reverse=True):
        if item["value"] == best["value"]:
            continue
        conflicts.append(item["value"])
        refs = item["paired_sources"] or item["sources"]
        if refs:
            conflict_sources.append(refs[0])
    return best["value"], source, conflicts, conflict_sources

def _find_sourced(
    documents: list[Document],
    patterns: list[str],
    preferred_types: tuple[str, ...] | None = None,
    fallback_all: bool = True,
):
    preferred = [d for d in documents if not preferred_types or d.type in preferred_types]
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
                        return value, _page_ref(doc, page)
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
                        first_source = _page_ref(doc, page)
    return values, first_source


def _safe_quantity_sourced(documents: list[Document]):
    safe_types = ("contrato","ata_registro_precos","empenho","ordem_fornecimento","termo_referencia")
    safe_docs = [d for d in documents if d.type in safe_types]
    patterns = [
        r"(?:quantidade\s+total|quantidade\s+contratada|total\s+contratado)\s*[:.-]?\s*(\d{1,7}\s+(?:kits?|unidades?|itens?|caixas?|frascos?|equipamentos?)(?:\s+de\s+[^.,;\n]{2,80})?)",
        r"(?:objeto|fornecimento|aquisi[cç][aã]o)\s+(?:de\s+)?(\d{1,7}\s+(?:kits?|unidades?|itens?|caixas?|frascos?|equipamentos?)(?:\s+de\s+[^.,;\n]{2,80})?)",
    ]
    for pattern in patterns:
        for doc in safe_docs:
            for page, text in _iter_doc_pages(doc):
                m = re.search(pattern, text, flags=re.I)
                if m:
                    value = re.sub(r"\s+", " ", m.group(1)).strip(" \t\n:;,.–—-")
                    if value:
                        return value, _page_ref(doc, page)
    return None, None


def build_profile(documents: list[Document]) -> ProcessProfile:
    sources: dict[str, PageRef] = {}
    conflicts: dict[str, list[str]] = {}
    conflict_sources: dict[str, list[PageRef]] = {}

    process_number, src = _find_sourced(
        documents,
        [
            r"Processo\s+Administrativo\s+(?:de\s+Penaliza[cç][aã]o|Sancionador)\s*(?:n\s*[º°o.]*)?\s*[:.-]?\s*(\d{1,8}(?:[-.]\d+)?/\d{4})"
        ],
    )
    if src:
        sources["process_number"] = src

    origin_process, src = _find_sourced(
        documents,
        [
            r"(?:Processo|Protocolo)\s+(?:de\s+origem\s+)?(?:n\s*[º°o.]*)?\s*[:.-]?\s*(\d[\d.-]*/\d{4})",
            r"\bPROCESSO\s+N\s*[º°O.]*\s*[:.-]\s*(\d[\d.-]*/\d{4})",
        ],
    )
    if origin_process and process_number and _candidate_key(origin_process) == _candidate_key(process_number):
        origin_process = None
        src = None
    if src:
        sources["origin_process"] = src

    company_candidates = _collect_company_candidates(documents)
    company, src, company_conflicts, company_conflict_sources = _select_candidate(company_candidates)
    if src:
        sources["company"] = src
    if company_conflicts:
        conflicts["company"] = company_conflicts
        conflict_sources["company"] = company_conflict_sources

    cnpj_candidates = _collect_cnpj_candidates(documents, company)
    cnpj, src, cnpj_conflicts, cnpj_conflict_sources = _select_cnpj_candidate(cnpj_candidates)
    if src:
        sources["cnpj"] = src
    if cnpj_conflicts:
        conflicts["cnpj"] = cnpj_conflicts
        conflict_sources["cnpj"] = cnpj_conflict_sources

    id_pattern = r"(\d{1,8}/\d{4})"

    pregao, src = _find_sourced(
        documents,
        [r"\bPreg[aã]o(?:\s+Eletr[oô]nico)?\s*(?:n\s*[º°o.]*|n[uú]mero)?\s*[:.-]?\s*" + id_pattern],
        preferred_types=("pregao","edital","contrato","ata_registro_precos","notificacao","decisao"),
    )
    if src:
        sources["pregao"] = src

    ata, src = _find_sourced(
        documents,
        [r"\bAta\s+de\s+Registro\s+de\s+Pre[cç]os\s*(?:n\s*[º°o.]*|n[uú]mero)?\s*[:.-]?\s*" + id_pattern],
        preferred_types=("ata_registro_precos","contrato","ordem_fornecimento","notificacao"),
    )
    if src:
        sources["ata"] = src

    contrato, src = _find_sourced(
        documents,
        [
            r"\bContrato(?:\s+Administrativo|\s+de\s+Fornecimento(?:\s+de\s+Mercadorias)?)?\s*(?:n\s*[º°o.]*|n[uú]mero)?\s*[:.-]?\s*" + id_pattern
        ],
        preferred_types=("contrato","notificacao","decisao","parecer_juridico","defesa"),
    )
    if src:
        sources["contrato"] = src

    empenhos, src = _find_all_identifiers(
        documents,
        r"\b(?:Nota\s+de\s+Empenho|Empenho)\s*(?:n\s*[º°o.]*|n[uú]mero)?\s*[:.-]?\s*" + id_pattern,
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
        conflicts=conflicts,
        conflict_sources=conflict_sources,
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
            "Decisão final do PAS",
            "located" if by.get("decisao") else "not_found",
            "Peça classificada como decisão localizada." if by.get("decisao") else "Decisão final do PAS não localizada.",
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
            "decisao":"Decisão final do PAS pertence a etapa futura.",
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
        set_state("recurso","inconclusive","Decisão final do PAS localizada; conferir ciência, prazo e eventual recurso.",False)

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


def _has_sanction_command(text: str) -> bool:
    negative = [
        r"deixo\s+de\s+aplicar.{0,80}(?:sancao|penalidade|multa)",
        r"nao\s+aplic(?:o|ar).{0,80}(?:sancao|penalidade|multa)",
        r"afast[oa].{0,80}(?:sancao|penalidade|multa)",
    ]
    if any(re.search(p, text) for p in negative):
        return False
    positive = [
        r"(?:decido.{0,80})?aplic(?:o|ar|a-se).{0,80}(?:sancao|penalidade|multa|advertencia|impedimento|inidoneidade)",
        r"fica\s+aplicada.{0,80}(?:sancao|penalidade|multa|advertencia)",
        r"imponho.{0,80}(?:sancao|penalidade|multa|advertencia|impedimento)",
        r"declar(?:o|ar).{0,80}(?:suspensao|impedimento|inidoneidade)",
        r"declaro.{0,40}inidone",
    ]
    return any(re.search(p, text) for p in positive)


def _has_final_no_sanction_command(text: str) -> bool:
    patterns = [
        r"julgo.{0,80}(?:improcedente|insubsistente)",
        r"deixo\s+de\s+aplicar.{0,80}(?:sancao|penalidade|multa)",
        r"decido.{0,100}(?:pelo\s+)?arquivamento",
        r"determino.{0,100}(?:o\s+)?arquivamento",
        r"absolv(?:o|er)",
    ]
    return any(re.search(p, text) for p in patterns)


def determine_stage(documents: list[Document]) -> StageResult:
    by = docs_by_type(documents)
    all_text = norm("\n".join(d.text for d in documents))
    decision_texts = [norm(d.text) for d in by.get("decisao", [])]
    current_pas = _has_current_pas_context(documents)

    authorizes_new_pas = any(
        ("autorizo" in t or "autoriza" in t)
        and (
            "abertura de processo administrativo sancionador" in t
            or "instauracao de processo administrativo sancionador" in t
        )
        for t in decision_texts
    )

    final_sanction = any(_has_sanction_command(t) for t in decision_texts)
    final_no_sanction = current_pas and any(
        _has_final_no_sanction_command(t)
        for t in decision_texts
    )
    final_decision = final_sanction or final_no_sanction

    # 1. Uma decisão do processo de origem que só AUTORIZA abrir um PAS
    # não pode ser tratada como julgamento sancionador, mesmo que haja defesa,
    # notificação ou recurso no processo contratual de origem.
    if authorizes_new_pas and not final_decision and not current_pas:
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
    if by.get("recurso") and final_decision:
        return StageResult(
            key="recurso",
            label="Fase recursal",
            confidence=.96,
            rationale="Recurso administrativo localizado após decisão final no processo sancionador.",
            next_action="Analisar o recurso e conferir os efeitos da decisão recorrida.",
            suggested_draft="decisao_recurso",
        )

    if by.get("decisao") and final_decision:
        return StageResult(
            key="julgamento",
            label="Julgamento do PAS identificado",
            confidence=.96,
            rationale=(
                "Decisão final com comando de aplicação de sanção localizada."
                if final_sanction
                else "Decisão final sem aplicação de sanção localizada no processo sancionador."
            ),
            next_action="Dar ciência da decisão, controlar eventual prazo recursal e registrar a sanção somente quando cabível.",
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
    used_keys = set()

    def add_once(
        key: str,
        category: str,
        fact: str,
        types: tuple[str, ...],
        patterns: list[str],
        confidence: float,
    ):
        if key in used_keys:
            return
        regs = [re.compile(p, re.I) for p in patterns]
        type_rank = {doc_type: i for i, doc_type in enumerate(types)}
        ordered = sorted(
            [d for d in documents if d.type in types],
            key=lambda d: (type_rank.get(d.type, 999), d.page_start),
        )
        for doc in ordered:
            if any(rx.search(doc.text or "") for rx in regs):
                evidence.append(
                    evidence_from_document(
                        doc,
                        fact,
                        patterns,
                        confidence,
                        key=key,
                        category=category,
                    )
                )
                used_keys.add(key)
                return

    add_once(
        "non_delivery",
        "fact",
        "Há registro de não entrega/inexecução do objeto",
        ("relatorio_tecnico","parecer_tecnico","oficio","notificacao","decisao"),
        [
            r"n[aã]o\s+(?:houve|ocorreu)\s+(?:a\s+)?entrega",
            r"n[aã]o\s+(?:realizou|realizaram|efetuou|efetuaram)\s+(?:(?:a[s]?|nenhuma|qualquer)\s+)?entrega",
            r"n[aã]o\s+entreg(?:ou|aram)",
            r"nenhuma[\s\S]{0,20}entrega",
            r"n[aã]o[\s\S]{0,40}realiz(?:ou|aram)[\s\S]{0,50}entrega",
            r"realiz(?:ou|aram)[\s\S]{0,30}nenhuma[\s\S]{0,20}entrega",
            r"aus[eê]ncia[\s\S]{0,20}de[\s\S]{0,20}(?:entrega|execu[cç][aã]o)",
            r"inexecu[cç][aã]o(?:\s+total|\s+parcial)?",
        ],
        .96,
    )

    add_once(
        "defense_deadline",
        "procedural",
        "Foi localizado ato que abre prazo para apresentação de defesa",
        ("intimacao","notificacao"),
        [
            r"prazo\s+de\s+\d+\s*(?:\([^)]+\)\s*)?dias?\s+[uú]teis?.{0,180}defesa",
            r"defesa.{0,180}prazo\s+de\s+\d+\s*(?:\([^)]+\)\s*)?dias?\s+[uú]teis?",
            r"apresent(?:e|ar)\s+(?:sua\s+)?defesa",
        ],
        .98,
    )

    if any(d.type == "defesa" for d in documents):
        fact = (
            "Defesa/manifestação localizada no processo de origem; não equivale à defesa do futuro PAS"
            if stage and stage.key == "instauracao_sancionadora_autorizada"
            else "Defesa administrativa apresentada"
        )
        add_once(
            "defense_submitted",
            "defense",
            fact,
            ("defesa",),
            [r"defesa\s+administrativa",r"raz[oõ]es\s+de\s+defesa",r"\bdefesa\b"],
            .98,
        )

    if any(d.type == "parecer_juridico" for d in documents):
        add_once(
            "legal_opinion",
            "legal",
            "Parecer jurídico localizado nos autos",
            ("parecer_juridico",),
            [r"parecer\s+jur[ií]dico"],
            .98,
        )

    if stage and stage.key == "instauracao_sancionadora_autorizada":
        add_once(
            "origin_pas_authorization",
            "decision",
            "Decisão do processo de origem autoriza a abertura de processo administrativo sancionador separado",
            ("decisao",),
            [
                r"autoriz[oa].{0,120}abertura\s+de\s+processo\s+administrativo\s+sancionador",
                r"autoriz[oa].{0,120}instaura[cç][aã]o\s+de\s+processo\s+administrativo\s+sancionador",
            ],
            .99,
        )
    elif stage and stage.key in {"julgamento","recurso"}:
        add_once(
            "final_decision",
            "decision",
            "Decisão final do processo sancionador localizada",
            ("decisao",),
            [
                r"aplic(?:o|ar|a-se).{0,80}(?:san[cç][aã]o|penalidade|multa|advert[eê]ncia|impedimento|inidoneidade)",
                r"fica\s+aplicada.{0,80}(?:san[cç][aã]o|penalidade|multa|advert[eê]ncia)",
                r"declar(?:o|ar).{0,80}(?:suspens[aã]o|impedimento|inidoneidade)",
                r"deixo\s+de\s+aplicar.{0,80}(?:san[cç][aã]o|penalidade|multa)",
                r"julgo.{0,80}(?:improcedente|insubsistente)",
                r"(?:decido|determino).{0,100}(?:o\s+)?arquivamento",
                r"absolv(?:o|er)",
            ],
            .99,
        )
    else:
        add_once(
            "administrative_decision",
            "decision",
            "Decisão ou despacho administrativo localizado",
            ("decisao",),
            [r"decis[aã]o\s+administrativa",r"despacho\s+n"],
            .94,
        )

    return evidence[:16]


def _attach_stage_sources(stage: StageResult, evidence, documents: list[Document]) -> StageResult:
    by_id = {d.id: d for d in documents}
    preferred_keys = {
        "instauracao_sancionadora_autorizada": ["origin_pas_authorization"],
        "aguardando_defesa": ["defense_deadline"],
        "defesa_apresentada": ["defense_submitted"],
        "instrucao_pos_defesa": ["defense_submitted", "legal_opinion"],
        "julgamento": ["final_decision"],
        "recurso": ["final_decision"],
    }.get(stage.key, [])

    refs = []
    seen = set()
    for key in preferred_keys:
        for ev in evidence:
            if ev.key != key:
                continue
            doc = by_id.get(ev.document_id)
            ref = PageRef(
                file=doc.file if doc else "",
                page=ev.page,
                document_id=ev.document_id,
            )
            token = (ref.document_id, ref.page)
            if token not in seen:
                seen.add(token)
                refs.append(ref)

    if not refs:
        fallback_types = {
            "instaurado": ("oficio", "notificacao", "intimacao"),
            "relatorio_conclusivo": ("relatorio_conclusivo",),
            "apuracao_inicial": ("parecer_tecnico", "relatorio_tecnico", "oficio"),
        }.get(stage.key, ())
        for doc_type in fallback_types:
            for doc in documents:
                if doc.type != doc_type:
                    continue
                ref = PageRef(file=doc.file, page=doc.page_start, document_id=doc.id)
                token = (ref.document_id, ref.page)
                if token not in seen:
                    seen.add(token)
                    refs.append(ref)
                    break
            if refs:
                break

    stage.sources = refs[:3]
    return stage


def analyze_penalizacao(documents: list[Document]) -> AnalysisResult:
    stage = determine_stage(documents)
    checklist = build_checklist(documents, stage)
    evidence = build_evidence(documents, stage)
    stage = _attach_stage_sources(stage, evidence, documents)
    result = AnalysisResult(
        module="penalizacao",
        profile=build_profile(documents),
        documents=documents,
        checklist=checklist,
        evidence=evidence,
        timeline=build_timeline(documents),
        stage=stage,
        pending_items=build_pending_items(checklist, stage),
        warnings=[],
    )
    result.warnings = validate_analysis_integrity(result)
    return result
