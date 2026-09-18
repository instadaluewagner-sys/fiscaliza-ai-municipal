import re
from v8.core.models import Document, Evidence

def first_excerpt(text: str, patterns: list[str], limit: int = 360) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    sentences = re.split(r"(?<=[.!?;:])\s+", compact)
    regs = [re.compile(p, re.I) for p in patterns]
    for sentence in sentences:
        if any(rx.search(sentence) for rx in regs):
            return sentence[:limit]
    return compact[:limit]

def evidence_from_document(doc: Document, fact: str, patterns: list[str], confidence: float = 0.9) -> Evidence:
    return Evidence(
        fact=fact,
        document_id=doc.id,
        page=doc.page_start,
        excerpt=first_excerpt(doc.text, patterns),
        confidence=confidence,
    )
