import re
import unicodedata
from v8.core.models import Document

def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value).strip().lower()

# A V8 separa "peça autônoma" de mera menção.
# Regras fortes trabalham por LINHA de cabeçalho, evitando classificar um documento
# inteiro porque o corpo apenas mencionou "contrato", "defesa" ou "notificação".
LINE_HEADER_RULES = [
    ("ata_registro_precos", r"^\s*ATA\s+DE\s+REGISTRO\s+DE\s+PRE[CÇ]OS\b", 0.995),
    ("pedido_reequilibrio", r"^\s*(?:PEDIDO|REQUERIMENTO)\s+DE\s+REEQUIL[IÍ]BRIO\s+ECON[ÔO]MICO[- ]FINANCEIRO\b", 0.995),
    ("parecer_juridico", r"^\s*PARECER\s+JUR[IÍ]DICO\b", 0.995),
    ("parecer_tecnico", r"^\s*PARECER\s+T[EÉ]CNICO\b", 0.995),
    ("relatorio_conclusivo", r"^\s*RELAT[ÓO]RIO\s+CONCLUSIVO\b", 0.995),
    ("relatorio_tecnico", r"^\s*RELAT[ÓO]RIO\s+T[EÉ]CNICO\b", 0.99),
    ("notificacao", r"^\s*NOTIFICA[CÇ][AÃ]O(?:\s+EXTRAJUDICIAL)?\b", 0.995),
    ("intimacao", r"^\s*INTIMA[CÇ][AÃ]O\b", 0.99),
    ("defesa", r"^\s*(?:ASSUNTO\s*:\s*)?DEFESA\s+ADMINISTRATIVA\b", 0.995),
    ("recurso", r"^\s*(?:ASSUNTO\s*:\s*)?RECURSO\s+ADMINISTRATIVO\b", 0.995),
    ("decisao", r"^\s*(?:DECIS[AÃ]O\s+ADMINISTRATIVA|DESPACHO\s+(?:N[ºO.]?\s*)?[A-Z0-9./-]+)\b", 0.99),
    ("contrato", r"^\s*CONTRATO\s+(?:ADMINISTRATIVO|DE\s+FORNECIMENTO|DE\s+PRESTA[CÇ][AÃ]O|N[ºO.])\b", 0.99),
    ("empenho", r"^\s*NOTA\s+DE\s+EMPENHO\b", 0.995),
    ("ordem_fornecimento", r"^\s*(?:ORDEM|AUTORIZA[CÇ][AÃ]O)\s+DE\s+FORNECIMENTO\b", 0.995),
    ("termo_referencia", r"^\s*TERMO\s+DE\s+REFER[EÊ]NCIA\b", 0.995),
    ("edital", r"^\s*EDITAL(?:\s+DE)?\b", 0.98),
    ("pregao", r"^\s*PREG[AÃ]O\s+ELETR[ÔO]NICO\b", 0.98),
    ("oficio", r"^\s*OF[IÍ]CIO(?:\s+N[ºO.]?)?\b", 0.97),
]

PROTOCOL_MARKERS = (
    re.compile(r"^\s*1Doc\s*:\s*", re.I),
    re.compile(r"^\s*Protocolo(?:\s+\d+\s*[-–])?\s*[0-9.]+/\d{4}", re.I),
)
PERFORMATIVE_INTIMATION = re.compile(
    r"\bintim[oa]\s+(?:a\s+)?(?:empresa|contratada|interessad[oa]|servidor[a]?)\b",
    re.I,
)
ATTACHMENT_LINE = re.compile(r"^\s*Anexos?\s*:\s*$", re.I)
PDF_FILENAME = re.compile(r"\b[^\s]+\.pdf\b", re.I)

def _clean_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in (text or "").splitlines() if line.strip()]

def _is_protocol_page(lines: list[str]) -> bool:
    if not lines:
        return False
    first = lines[:14]
    joined = "\n".join(first)
    has_1doc = any(rx.search(line) for line in first for rx in PROTOCOL_MARKERS)
    has_routing = bool(re.search(r"(?mi)^(?:De|Para|Data)\s*:", joined))
    return has_1doc and has_routing

def _has_attachment(lines: list[str]) -> bool:
    for i, line in enumerate(lines[:35]):
        if ATTACHMENT_LINE.match(line):
            tail = " ".join(lines[i + 1:i + 5])
            return bool(PDF_FILENAME.search(tail))
    return False

def _find_strong_header(lines: list[str]):
    # Até 35 linhas: permite timbre/cabeçalho institucional antes do título,
    # mas não deixa menções do corpo decidirem o tipo da peça.
    for index, line in enumerate(lines[:35]):
        for doc_type, pattern, confidence in LINE_HEADER_RULES:
            if re.search(pattern, line, flags=re.I):
                # Página de protocolo que apenas registra "Defesa Administrativa"
                # e anexa o PDF não é a própria defesa. O anexo começará na página seguinte.
                if (
                    doc_type in {"defesa", "recurso"}
                    and _is_protocol_page(lines)
                    and _has_attachment(lines)
                    and not re.match(r"(?i)^\s*ASSUNTO\s*:", line)
                ):
                    continue
                return doc_type, line[:220], confidence, index
    return None

def detect_header(text: str):
    lines = _clean_lines(text)
    if not lines:
        return None

    strong = _find_strong_header(lines)
    if strong:
        doc_type, title, confidence, _ = strong
        return doc_type, title, confidence

    compact = " ".join(lines[:45])

    # Algumas intimações do 1Doc são o próprio ato e não têm título formal:
    # "Com fundamento ..., intimo a empresa ... para que, no prazo..."
    if _is_protocol_page(lines) and PERFORMATIVE_INTIMATION.search(compact):
        sentence = next((x for x in lines if PERFORMATIVE_INTIMATION.search(x)), "Intimação")
        return "intimacao", sentence[:220], 0.97

    # Página de movimentação/encaminhamento: separa envelope do documento anexado.
    if _is_protocol_page(lines):
        title = next((x for x in lines[:8] if x.lower().startswith("protocolo")), lines[0])
        return "movimentacao_1doc", title[:220], 0.96

    # Página de verificação de assinatura permanece ligada à peça anterior,
    # por isso não cria cabeçalho novo.
    if any("verificação das assinaturas" in norm(x) or "verificacao das assinaturas" in norm(x) for x in lines[:8]):
        return None

    return None

def _new_document(counter: int, page: dict, detected) -> dict:
    if detected:
        dtype, title, confidence = detected
    else:
        dtype, title, confidence = "unclassified", f"Documento iniciado na página {page['page']}", 0.35
    return {
        "id": f"DOC-{counter:03d}",
        "file": page["file"],
        "type": dtype,
        "title": title,
        "page_start": page["page"],
        "page_end": page["page"],
        "pages": [page["page"]],
        "page_texts": {page["page"]: page["text"]},
        "confidence": confidence,
        "text": page["text"],
    }

def segment_documents(pages: list[dict]) -> list[Document]:
    documents = []
    current = None
    counter = 0

    for page in pages:
        detected = detect_header(page["text"])
        file_changed = current is not None and page["file"] != current["file"]

        starts_new = current is None or file_changed
        if current is not None and detected and not file_changed:
            dtype, title, _ = detected

            # Um cabeçalho forte/protocolo inicia uma nova peça. A exceção é quando
            # páginas sucessivas repetem exatamente o mesmo título/tipo.
            same_type = dtype == current["type"]
            same_title = norm(title)[:120] == norm(current["title"])[:120]
            if not (same_type and same_title):
                starts_new = True

        if starts_new:
            if current:
                documents.append(Document(**current))
            counter += 1
            current = _new_document(counter, page, detected)
        else:
            current["page_end"] = page["page"]
            current["pages"].append(page["page"])
            current["page_texts"][page["page"]] = page["text"]
            current["text"] += "\n\n" + page["text"]

    if current:
        documents.append(Document(**current))
    return documents
