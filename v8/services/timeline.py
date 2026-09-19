import re
from datetime import date
from v8.core.models import Document, TimelineEvent

MONTHS = {
    "janeiro":1,"fevereiro":2,"marco":3,"março":3,"abril":4,"maio":5,"junho":6,
    "julho":7,"agosto":8,"setembro":9,"outubro":10,"novembro":11,"dezembro":12,
}

LABELS = {
    "pedido_reequilibrio":"Pedido de reequilíbrio / manifestação inicial",
    "ata_registro_precos":"Ata de Registro de Preços",
    "pregao":"Pregão / processo licitatório",
    "edital":"Edital",
    "termo_referencia":"Termo de Referência",
    "contrato":"Contrato",
    "empenho":"Nota de Empenho",
    "ordem_fornecimento":"Ordem / autorização de fornecimento",
    "oficio":"Ofício / comunicação",
    "relatorio_tecnico":"Relatório técnico",
    "parecer_tecnico":"Parecer técnico",
    "notificacao":"Notificação",
    "intimacao":"Intimação",
    "defesa":"Defesa administrativa",
    "parecer_juridico":"Parecer jurídico",
    "relatorio_conclusivo":"Relatório conclusivo",
    "decisao":"Decisão / despacho",
    "recurso":"Recurso administrativo",
}

EXCLUDED_TYPES = {"movimentacao_1doc", "unclassified"}

def _iso_from_parts(day: int, month: int, year: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None

def extract_document_date(doc: Document) -> tuple[str | None, str]:
    # 1) Campo formal "Data:" no próprio documento/protocolo.
    for page in sorted(doc.page_texts):
        text = doc.page_texts[page]
        m = re.search(r"(?im)^\s*Data\s*:\s*(\d{2})/(\d{2})/(\d{4})", text)
        if m:
            iso = _iso_from_parts(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if iso:
                return iso, "document"

    # 2) Fecho formal: "Francisco Beltrão, 21 de outubro de 2025".
    tail = doc.text[-2500:]
    m = re.search(
        r"(?i)\b(\d{1,2})\s+de\s+(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+(\d{4})\b",
        tail,
    )
    if m:
        month_name = m.group(2).lower().replace("ç","c")
        month = MONTHS.get(month_name) or MONTHS.get(m.group(2).lower())
        if month:
            iso = _iso_from_parts(int(m.group(1)), month, int(m.group(3)))
            if iso:
                return iso, "document"

    return None, "unknown"

def build_timeline(documents: list[Document]) -> list[TimelineEvent]:
    events = []
    ordered = sorted(documents, key=lambda d: (d.file, d.page_start))
    previous: Document | None = None

    for doc in ordered:
        if doc.type in EXCLUDED_TYPES:
            previous = doc
            continue

        event_date, source = extract_document_date(doc)

        # Em sistemas como 1Doc, o envelope imediatamente anterior costuma conter
        # a data de juntada/encaminhamento do anexo. Usamos essa data apenas como
        # fallback e deixamos explícito que veio do envelope.
        if not event_date and previous and previous.type == "movimentacao_1doc":
            prev_date, _ = extract_document_date(previous)
            if prev_date and previous.file == doc.file and previous.page_end < doc.page_start:
                event_date = prev_date
                source = "envelope"

        events.append(
            TimelineEvent(
                sequence=len(events)+1,
                label=LABELS.get(doc.type, doc.type.replace("_"," ").title()),
                type=doc.type,
                document_id=doc.id,
                page=doc.page_start,
                date=event_date,
                date_source=source if event_date else "unknown",
                confidence=doc.confidence,
                title=doc.title,
            )
        )
        previous = doc

    return events
