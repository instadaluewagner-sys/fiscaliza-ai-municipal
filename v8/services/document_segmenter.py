import re
import unicodedata
from v8.core.models import Document

def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value).strip().lower()

HEADER_RULES = [
    ("ata_registro_precos", r"\bata\s+de\s+registro\s+de\s+pre[cç]os\b", 0.99),
    ("pregao", r"\bpreg[aã]o(?:\s+eletr[oô]nico)?\b", 0.94),
    ("edital", r"\bedital\b", 0.92),
    ("termo_referencia", r"\btermo\s+de\s+refer[eê]ncia\b", 0.96),
    ("contrato", r"\bcontrato(?:\s+administrativo)?\b", 0.95),
    ("empenho", r"\bnota\s+de\s+empenho\b", 0.98),
    ("ordem_fornecimento", r"\b(?:ordem|autoriza[cç][aã]o)\s+de\s+fornecimento\b", 0.98),
    ("oficio", r"\bof[ií]cio\b", 0.92),
    ("relatorio_conclusivo", r"\brelat[oó]rio\s+conclusivo\b", 0.99),
    ("relatorio_tecnico", r"\brelat[oó]rio\s+t[eé]cnico\b", 0.98),
    ("notificacao", r"\bnotifica[cç][aã]o(?:\s+extrajudicial)?\b", 0.98),
    ("intimacao", r"\bintima[cç][aã]o\b", 0.96),
    ("defesa", r"\b(?:defesa\s+administrativa|defesa\s+pr[eé]via|raz[oõ]es\s+de\s+defesa)\b", 0.99),
    ("parecer_juridico", r"\bparecer\s+jur[ií]dico\b", 0.99),
    ("parecer_tecnico", r"\bparecer\s+t[eé]cnico\b", 0.98),
    ("recurso", r"\brecurso\s+administrativo\b", 0.98),
    ("decisao", r"\b(?:decis[aã]o\s+administrativa|despacho)\b", 0.93),
]

NUMBERED_TITLE = re.compile(r"(?i)\b(?:n[ºo.]?|n[uú]mero)\s*[:.-]?\s*[A-Z0-9./-]{2,}")

def detect_header(text: str):
    raw = re.sub(r"\s+", " ", text or "").strip()
    head = raw[:1800]
    for doc_type, pattern, confidence in HEADER_RULES:
        if re.search(pattern, head, flags=re.I):
            title = head[:220].strip()
            if NUMBERED_TITLE.search(head[:500]):
                confidence = min(1.0, confidence + 0.01)
            return doc_type, title, confidence
    return None

def segment_documents(pages: list[dict]) -> list[Document]:
    documents = []
    current = None
    counter = 0

    for page in pages:
        detected = detect_header(page["text"])
        starts_new = current is None
        if current is not None and detected:
            dtype, title, _ = detected
            if dtype != current["type"] or norm(title)[:100] != norm(current["title"])[:100]:
                starts_new = True

        if starts_new:
            if current:
                documents.append(Document(**current))
            counter += 1
            if detected:
                dtype, title, confidence = detected
            else:
                dtype, title, confidence = "unclassified", f"Documento iniciado na página {page['page']}", 0.45
            current = {
                "id": f"DOC-{counter:03d}",
                "file": page["file"],
                "type": dtype,
                "title": title,
                "page_start": page["page"],
                "page_end": page["page"],
                "pages": [page["page"]],
                "confidence": confidence,
                "text": page["text"],
            }
        else:
            current["page_end"] = page["page"]
            current["pages"].append(page["page"])
            current["text"] += "\n\n" + page["text"]

    if current:
        documents.append(Document(**current))
    return documents
