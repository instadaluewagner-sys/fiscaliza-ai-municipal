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

def locate_excerpt(doc: Document, patterns: list[str], limit: int = 360) -> tuple[int, str]:
    regs = [re.compile(p, re.I) for p in patterns]
    page_texts = doc.page_texts or {}
    for page in sorted(page_texts):
        raw = page_texts[page]
        compact = re.sub(r"\s+", " ", raw or "").strip()
        sentences = re.split(r"(?<=[.!?;:])\s+", compact)
        for sentence in sentences:
            if any(rx.search(sentence) for rx in regs):
                return page, sentence[:limit]
    return doc.page_start, first_excerpt(doc.text, patterns, limit)

def evidence_from_document(doc: Document, fact: str, patterns: list[str], confidence: float = 0.9) -> Evidence:
    page, excerpt = locate_excerpt(doc, patterns)
    return Evidence(
        fact=fact,
        document_id=doc.id,
        page=page,
        excerpt=excerpt,
        confidence=confidence,
    )
