from typing import Literal, Optional
from pydantic import BaseModel, Field

Status = Literal["located", "not_found", "not_applicable", "inconclusive"]

class PageRef(BaseModel):
    file: str
    page: int
    document_id: Optional[str] = None

class Document(BaseModel):
    id: str
    file: str
    type: str
    title: str
    page_start: int
    page_end: int
    pages: list[int]
    page_texts: dict[int, str] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    text: str

class ChecklistItem(BaseModel):
    key: str
    label: str
    status: Status
    reason: str
    document_ids: list[str] = Field(default_factory=list)
    pages: list[int] = Field(default_factory=list)

class PendingItem(BaseModel):
    key: str
    label: str
    kind: Literal["missing", "review", "next_step"]
    severity: Literal["high", "medium", "low"]
    reason: str

class Evidence(BaseModel):
    fact: str
    document_id: str
    page: int
    excerpt: str
    confidence: float = Field(ge=0, le=1)

class TimelineEvent(BaseModel):
    sequence: int
    label: str
    type: str
    document_id: str
    page: int
    date: Optional[str] = None
    date_source: Literal["document", "envelope", "unknown"] = "unknown"
    confidence: float = Field(ge=0, le=1)
    title: str

class StageResult(BaseModel):
    key: str
    label: str
    confidence: float = Field(ge=0, le=1)
    rationale: str
    next_action: str
    suggested_draft: str

class ProcessProfile(BaseModel):
    process_number: Optional[str] = None
    origin_process: Optional[str] = None
    company: Optional[str] = None
    cnpj: Optional[str] = None
    pregao: Optional[str] = None
    ata: Optional[str] = None
    contrato: Optional[str] = None
    empenhos: list[str] = Field(default_factory=list)
    object_description: Optional[str] = None
    quantity: Optional[str] = None
    sources: dict[str, PageRef] = Field(default_factory=dict)

class AnalysisResult(BaseModel):
    module: str
    profile: ProcessProfile
    documents: list[Document]
    checklist: list[ChecklistItem]
    evidence: list[Evidence]
    timeline: list[TimelineEvent] = Field(default_factory=list)
    stage: StageResult
    pending_items: list[PendingItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DraftResult(BaseModel):
    kind: str
    title: str
    stage_key: str
    text: str
    source_document_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
