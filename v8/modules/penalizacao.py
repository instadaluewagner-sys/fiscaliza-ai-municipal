import re
import unicodedata
from v8.core.models import AnalysisResult, ChecklistItem, Document, ProcessProfile, StageResult
from v8.services.evidence import evidence_from_document

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

def build_profile(documents: list[Document]) -> ProcessProfile:
    text = "\n".join(d.text for d in documents)
    return ProcessProfile(
        process_number=find_first(text,[r"Processo Administrativo de Penaliza[cç][aã]o\s*(?:n[ºo.]?)?\s*[:.-]?\s*([0-9./-]+)"]),
        origin_process=find_first(text,[r"(?:Processo|Protocolo)\s+(?:de\s+origem\s+)?(?:n[ºo.]?)?\s*[:.-]?\s*([0-9./-]+)"]),
        company=find_first(text,[r"(?:Empresa|Contratada)\s*[:.-]\s*([^\n]{3,120})"]),
        cnpj=find_first(text,[r"\bCNPJ\s*[:.-]?\s*([0-9./-]{14,20})"]),
        object_description=find_first(text,[r"Objeto\s*[:.-]\s*([^\n]{5,180})"]),
        quantity=find_first(text,[r"\b(\d{1,7}\s+(?:kits?|unidades?|itens?|caixas?|frascos?|equipamentos?)(?:\s+de\s+[^.,;\n]{2,80})?)"]),
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

def build_checklist(documents: list[Document]) -> list[ChecklistItem]:
    by = docs_by_type(documents)
    all_text = norm("\n".join(d.text for d in documents))
    uses_arp = bool(by.get("ata_registro_precos")) or "ata de registro de precos" in all_text or bool(re.search(r"\barp\b", all_text))

    return [
        item("pregao","Pregão / processo licitatório","located" if by.get("pregao") else "not_found","Peça localizada." if by.get("pregao") else "Não localizado com segurança.",by.get("pregao")),
        item("ata","Ata de Registro de Preços","located" if by.get("ata_registro_precos") else ("not_found" if uses_arp else "not_applicable"),"A contratação indica uso de ARP." if uses_arp else "Não há evidência suficiente de contratação via ARP.",by.get("ata_registro_precos")),
        item("contrato","Contrato / instrumento equivalente","located" if by.get("contrato") else "inconclusive","Contrato formal não foi localizado; conferir se o instrumento é substituído por empenho/ordem.",by.get("contrato")),
        item("empenho","Nota de Empenho","located" if by.get("empenho") else "not_found","Peça de empenho esperada na instrução contratual.",by.get("empenho")),
        item("ordem","Ordem / autorização de fornecimento","located" if by.get("ordem_fornecimento") else "inconclusive","Pode ser dispensável conforme o instrumento da contratação.",by.get("ordem_fornecimento")),
        item("apuracao","Relatório técnico / comunicação do fato","located" if (by.get("relatorio_tecnico") or by.get("oficio")) else "not_found","É necessário elemento que descreva o fato e a execução.",(by.get("relatorio_tecnico") or [])+(by.get("oficio") or [])),
        item("notificacao","Notificação / intimação","located" if (by.get("notificacao") or by.get("intimacao")) else "not_found","Necessária para assegurar ciência e contraditório.",(by.get("notificacao") or [])+(by.get("intimacao") or [])),
        item("defesa","Defesa / manifestação","located" if by.get("defesa") else "inconclusive","A ausência pode significar prazo em curso ou revelia; conferir estágio.",by.get("defesa")),
        item("parecer_tecnico","Parecer / análise técnica","located" if (by.get("parecer_tecnico") or by.get("relatorio_tecnico")) else "inconclusive","A necessidade depende da instrução e da complexidade do caso.",(by.get("parecer_tecnico") or [])+(by.get("relatorio_tecnico") or [])),
        item("parecer_juridico","Parecer jurídico","located" if by.get("parecer_juridico") else "inconclusive","Conferir exigência no fluxo municipal aplicável.",by.get("parecer_juridico")),
        item("relatorio_conclusivo","Relatório conclusivo da comissão","located" if by.get("relatorio_conclusivo") else "not_found","Peça esperada antes do julgamento, quando a instrução estiver concluída.",by.get("relatorio_conclusivo")),
        item("decisao","Decisão administrativa","located" if by.get("decisao") else "not_found","A decisão encerra a fase de julgamento e orienta os atos posteriores.",by.get("decisao")),
        item("recurso","Recurso / ciência da decisão","located" if by.get("recurso") else "inconclusive","Somente aplicável após decisão e conforme prazo/fase recursal.",by.get("recurso")),
    ]

def determine_stage(documents: list[Document]) -> StageResult:
    by = docs_by_type(documents)
    all_text = norm("\n".join(d.text for d in documents))
    decision_texts = [norm(d.text) for d in by.get("decisao", [])]
    authorizes_new_pas = any(
        ("autorizo" in t or "autoriza" in t)
        and ("abertura de processo administrativo sancionador" in t or "instauracao de processo administrativo sancionador" in t)
        for t in decision_texts
    )
    final_sanction = any(
        any(k in t for k in ["aplico a sancao", "aplica-se a sancao", "multa", "impedimento de licitar", "declaracao de inidoneidade"])
        and any(k in t for k in ["processo administrativo sancionador", "processo administrativo de penalizacao", "penalidade"])
        for t in decision_texts
    )

    if by.get("recurso"):
        return StageResult(key="recurso",label="Fase recursal",confidence=.95,rationale="Recurso administrativo localizado.",next_action="Analisar o recurso e conferir os efeitos da decisão recorrida.",suggested_draft="decisao_recurso")
    if authorizes_new_pas and not final_sanction:
        return StageResult(
            key="instauracao_sancionadora_autorizada",
            label="Instauração sancionadora autorizada",
            confidence=.97,
            rationale="Foi localizada decisão no processo de origem que autoriza a abertura de processo administrativo sancionador separado; isso não equivale a julgamento de penalidade.",
            next_action="Autuar/instaurar o processo sancionador, delimitar fatos e documentos de origem e então assegurar o contraditório conforme a norma aplicável.",
            suggested_draft="despacho_instauracao",
        )
    if by.get("decisao") and final_sanction:
        return StageResult(key="julgamento",label="Julgamento sancionador identificado",confidence=.96,rationale="Decisão sancionadora com comando de aplicação de penalidade localizada.",next_action="Dar ciência da decisão, controlar eventual prazo recursal e registrar a sanção quando cabível.",suggested_draft="notificacao_decisao")
    if by.get("relatorio_conclusivo"):
        return StageResult(key="relatorio_conclusivo",label="Relatório conclusivo elaborado",confidence=.95,rationale="Relatório conclusivo da comissão localizado.",next_action="Encaminhar os autos à autoridade competente para julgamento.",suggested_draft="decisao")
    if by.get("defesa") and (by.get("parecer_tecnico") or by.get("parecer_juridico") or by.get("relatorio_tecnico")):
        return StageResult(key="instrucao_pos_defesa",label="Instrução após defesa",confidence=.90,rationale="Defesa e elementos de análise posteriores estão presentes.",next_action="Concluir a instrução e elaborar relatório conclusivo enfrentando os argumentos relevantes.",suggested_draft="relatorio_conclusivo")
    if by.get("defesa"):
        return StageResult(key="defesa_apresentada",label="Defesa apresentada",confidence=.94,rationale="Peça autônoma de defesa localizada.",next_action="Analisar a defesa, confrontar provas e realizar diligências se necessárias.",suggested_draft="despacho_diligencia")
    if by.get("notificacao") or by.get("intimacao"):
        return StageResult(key="aguardando_defesa",label="Contraditório aberto",confidence=.90,rationale="Notificação/intimação localizada sem defesa autônoma identificada.",next_action="Controlar o prazo de defesa e certificar o decurso ou recebimento da manifestação.",suggested_draft="certidao_prazo")
    if "instaur" in all_text:
        return StageResult(key="instaurado",label="Processo instaurado",confidence=.82,rationale="Há referência expressa à instauração, sem notificação autônoma identificada.",next_action="Expedir notificação/intimação de instauração e abertura de prazo para defesa.",suggested_draft="notificacao_instauracao")
    if by.get("relatorio_tecnico") or by.get("oficio"):
        return StageResult(key="apuracao_inicial",label="Apuração inicial",confidence=.82,rationale="Fato/execução documentados, sem instauração clara.",next_action="Conferir pressupostos e decidir sobre a instauração do processo de penalização.",suggested_draft="despacho_instauracao")
    return StageResult(key="triagem",label="Triagem",confidence=.65,rationale="Elementos insuficientes para determinar fase posterior.",next_action="Completar a instrução inicial e confirmar a origem do fato.",suggested_draft="despacho_diligencia")

def build_evidence(documents: list[Document]):
    evidence = []
    for doc in documents:
        z = norm(doc.text)
        if any(k in z for k in ["nao houve entrega","inexecucao"]):
            evidence.append(evidence_from_document(doc,"Execução/inexecução registrada",[r"n[aã]o houve entrega",r"inexecu[cç][aã]o"],.94))
        if doc.type == "defesa":
            evidence.append(evidence_from_document(doc,"Defesa administrativa apresentada",[r"defesa",r"alega",r"requer"],.97))
        if doc.type == "decisao":
            evidence.append(evidence_from_document(doc,"Decisão administrativa localizada",[r"decid",r"julgo",r"determino"],.95))
    return evidence[:12]

def analyze_penalizacao(documents: list[Document]) -> AnalysisResult:
    checklist = build_checklist(documents)
    stage = determine_stage(documents)
    return AnalysisResult(
        module="penalizacao",
        profile=build_profile(documents),
        documents=documents,
        checklist=checklist,
        evidence=build_evidence(documents),
        stage=stage,
        warnings=[],
    )
