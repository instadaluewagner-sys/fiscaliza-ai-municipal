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
    confidence: float = Field(ge=0, le=1)
    text: str

class ChecklistItem(BaseModel):
    key: str
    label: str
    status: Status
    reason: str
    document_ids: list[str] = []
    pages: list[int] = []

class Evidence(BaseModel):
    fact: str
    document_id: str
    page: int
    excerpt: str
    confidence: float = Field(ge=0, le=1)

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
    object_description: Optional[str] = None
    quantity: Optional[str] = None

class AnalysisResult(BaseModel):
    module: str
    profile: ProcessProfile
    documents: list[Document]
    checklist: list[ChecklistItem]
    evidence: list[Evidence]
    stage: StageResult
    warnings: list[str] = []
