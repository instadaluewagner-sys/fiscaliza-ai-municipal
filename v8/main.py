import io
import os
import time
import uuid
import json
import hashlib
from pathlib import Path
from typing import List

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from v8.modules.penalizacao import analyze_penalizacao
from v8.services.document_segmenter import segment_documents
from v8.services.demo import build_demo_pdf
from v8.services.drafts import generate_draft
from v8.services.pdf_reader import extract_pages
from v8.services.report import build_audit_payload, build_pdf_report

BASE_DIR = Path(__file__).resolve().parent
SESSION_TTL_SECONDS = int(os.getenv("V8_SESSION_TTL_SECONDS", "1800"))
MAX_PDF_BYTES = int(os.getenv("V8_MAX_PDF_BYTES", str(30 * 1024 * 1024)))
MAX_TOTAL_UPLOAD_BYTES = int(os.getenv("V8_MAX_TOTAL_UPLOAD_BYTES", str(60 * 1024 * 1024)))
MAX_FILES = int(os.getenv("V8_MAX_FILES", "5"))
MAX_TOTAL_PAGES = int(os.getenv("V8_MAX_TOTAL_PAGES", "600"))
MAX_TOTAL_OCR_PAGES = int(os.getenv("V8_MAX_TOTAL_OCR_PAGES", "200"))
V8_ANALYSES: dict[str, dict] = {}

app = FastAPI(title="Fiscaliza.AI V8", version="8.0.0-rc.1")

if (BASE_DIR / "static").exists():
    app.mount("/v8-static", StaticFiles(directory=BASE_DIR / "static"), name="v8-static")


@app.middleware("http")
async def sensitive_no_store(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/v8/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


def cleanup_sessions() -> None:
    now = time.time()
    expired = [
        analysis_id
        for analysis_id, item in V8_ANALYSES.items()
        if now - item["created_at"] > SESSION_TTL_SECONDS
    ]
    for analysis_id in expired:
        V8_ANALYSES.pop(analysis_id, None)


def get_session(analysis_id: str) -> dict:
    cleanup_sessions()
    item = V8_ANALYSES.get(analysis_id)
    if not item:
        raise HTTPException(404, "Análise expirada, excluída ou inexistente.")
    return item


@app.get("/api/v8/demo.pdf")
def demo_pdf():
    data = build_demo_pdf()
    headers = {
        "Content-Disposition": 'inline; filename="fiscaliza-v8-processo-modelo.pdf"',
        "Cache-Control": "no-store",
    }
    return Response(content=data, media_type="application/pdf", headers=headers)


@app.get("/api/v8/health")
def health():
    cleanup_sessions()
    return {
        "ok": True,
        "version": app.version,
        "status": "release-candidate",
        "temporary_sessions": len(V8_ANALYSES),
        "session_ttl_seconds": SESSION_TTL_SECONDS,
        "max_pdf_bytes": MAX_PDF_BYTES,
        "max_total_upload_bytes": MAX_TOTAL_UPLOAD_BYTES,
        "max_files": MAX_FILES,
        "max_total_pages": MAX_TOTAL_PAGES,
        "max_total_ocr_pages": MAX_TOTAL_OCR_PAGES,
    }


@app.post("/api/v8/analyze")
async def analyze(module: str = "penalizacao", files: List[UploadFile] = File(...)):
    cleanup_sessions()
    if module != "penalizacao":
        raise HTTPException(400, "Na V8 RC, apenas Penalização contratual está habilitada.")

    invalid_files = [
        Path(upload.filename or "arquivo").name
        for upload in files
        if not (upload.filename or "").lower().endswith(".pdf")
    ]
    if invalid_files:
        raise HTTPException(
            400,
            "A V8 aceita somente arquivos PDF. Remova: " + ", ".join(invalid_files[:5]),
        )

    pdf_uploads = list(files)
    if len(pdf_uploads) > MAX_FILES:
        raise HTTPException(
            413,
            f"Envie no máximo {MAX_FILES} PDFs por análise.",
        )

    pages = []
    ocr_pages = 0
    names = []
    stored_files = []
    total_upload_bytes = 0

    for file_index, upload in enumerate(pdf_uploads):
        filename = Path(upload.filename or "processo.pdf").name
        filename = "".join(ch for ch in filename if ch >= " " and ch not in {'"', "\r", "\n"}) or "processo.pdf"
        if not filename.lower().endswith(".pdf"):
            continue
        data = await upload.read(MAX_PDF_BYTES + 1)
        total_upload_bytes += len(data)
        if total_upload_bytes > MAX_TOTAL_UPLOAD_BYTES:
            raise HTTPException(
                413,
                f"O conjunto de arquivos excede o limite de {MAX_TOTAL_UPLOAD_BYTES // (1024 * 1024)} MB por análise.",
            )
        if len(data) > MAX_PDF_BYTES:
            raise HTTPException(
                413,
                f"O arquivo '{filename}' excede o limite de {MAX_PDF_BYTES // (1024 * 1024)} MB por PDF.",
            )
        try:
            extracted, ocr_count = await run_in_threadpool(extract_pages, data, filename)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if len(pages) + len(extracted) > MAX_TOTAL_PAGES:
            raise HTTPException(
                413,
                f"O conjunto de arquivos excede o limite de {MAX_TOTAL_PAGES} páginas por análise.",
            )
        if ocr_pages + ocr_count > MAX_TOTAL_OCR_PAGES:
            raise HTTPException(
                413,
                f"O conjunto de arquivos exige OCR em mais de {MAX_TOTAL_OCR_PAGES} páginas. "
                "Divida o processo em lotes menores ou envie PDFs com camada de texto.",
            )

        file_id = f"ARQ-{file_index+1:02d}"
        for page in extracted:
            page["file_index"] = file_index
            page["file_id"] = file_id

        pages.extend(extracted)
        ocr_pages += ocr_count
        names.append(filename)
        stored_files.append({
            "file_id": file_id,
            "filename": filename,
            "bytes": data,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
        })

    if not pages:
        raise HTTPException(400, "Envie pelo menos um PDF válido.")

    documents = segment_documents(pages)
    result = analyze_penalizacao(documents)
    analysis_id = uuid.uuid4().hex

    V8_ANALYSES[analysis_id] = {
        "created_at": time.time(),
        "module": module,
        "files": stored_files,
        "pages": pages,
        "documents": documents,
        "analysis": result,
        "ocr_pages": ocr_pages,
    }

    return {
        "analysis_id": analysis_id,
        "version": app.version,
        "files": [
            {
                "file_id": item["file_id"],
                "filename": item["filename"],
                "sha256": item["sha256"],
                "size_bytes": item["size_bytes"],
            }
            for item in stored_files
        ],
        "pages": len(pages),
        "ocr_pages": ocr_pages,
        "analysis": result.model_dump(),
    }


@app.get("/api/v8/analysis/{analysis_id}")
def read_analysis(analysis_id: str):
    item = get_session(analysis_id)
    result = item["analysis"]
    return {
        "analysis_id": analysis_id,
        "module": item["module"],
        "created_at": item["created_at"],
        "analysis": result.model_dump(),
    }


@app.get("/api/v8/file/{analysis_id}/{file_index}")
def read_original_pdf(analysis_id: str, file_index: int):
    item = get_session(analysis_id)
    files = item["files"]
    if file_index < 0 or file_index >= len(files):
        raise HTTPException(404, "Arquivo não encontrado nesta análise.")
    source = files[file_index]
    headers = {
        "Content-Disposition": f'inline; filename="{source["filename"].replace(chr(34), "")}"',
        "Cache-Control": "no-store",
    }
    return StreamingResponse(io.BytesIO(source["bytes"]), media_type="application/pdf", headers=headers)


@app.get("/api/v8/document/{analysis_id}/{document_id}")
def read_document(analysis_id: str, document_id: str):
    item = get_session(analysis_id)
    doc = next((d for d in item["documents"] if d.id == document_id), None)
    if not doc:
        raise HTTPException(404, "Documento não encontrado nesta análise.")

    file_index = doc.file_index
    if file_index is None:
        file_index = next(
            (i for i, source in enumerate(item["files"]) if source["filename"] == doc.file),
            None,
        )
    return {
        "analysis_id": analysis_id,
        "document": doc.model_dump(exclude={"text", "page_texts"}),
        "file_index": file_index,
        "viewer_url": (
            f"/api/v8/file/{analysis_id}/{file_index}#page={doc.page_start}"
            if file_index is not None
            else None
        ),
    }


@app.get("/api/v8/draft/{analysis_id}")
def read_stage_draft(analysis_id: str, kind: str | None = None):
    item = get_session(analysis_id)
    try:
        draft = generate_draft(item["analysis"], kind)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return draft.model_dump()


@app.get("/api/v8/report/{analysis_id}.json")
def read_audit_json(analysis_id: str):
    item = get_session(analysis_id)
    payload = build_audit_payload(
        analysis_id=analysis_id,
        analysis=item["analysis"],
        source_files=item["files"],
        page_count=len(item["pages"]),
        ocr_pages=item.get("ocr_pages", 0),
    )
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    headers = {
        "Content-Disposition": f'attachment; filename="fiscaliza-v8-{analysis_id[:8]}.json"',
        "Cache-Control": "no-store",
    }
    return Response(content=data, media_type="application/json; charset=utf-8", headers=headers)


@app.get("/api/v8/report/{analysis_id}.pdf")
def read_audit_pdf(analysis_id: str):
    item = get_session(analysis_id)
    data = build_pdf_report(
        analysis_id=analysis_id,
        analysis=item["analysis"],
        source_files=item["files"],
        page_count=len(item["pages"]),
        ocr_pages=item.get("ocr_pages", 0),
    )
    headers = {
        "Content-Disposition": f'attachment; filename="fiscaliza-v8-{analysis_id[:8]}.pdf"',
        "Cache-Control": "no-store",
    }
    return Response(content=data, media_type="application/pdf", headers=headers)


@app.delete("/api/v8/analysis/{analysis_id}")
def delete_analysis(analysis_id: str):
    existed = V8_ANALYSES.pop(analysis_id, None) is not None
    return {"deleted": existed, "analysis_id": analysis_id}


@app.get("/", response_class=HTMLResponse)
def index():
    path = BASE_DIR / "templates" / "index.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "<h1>Fiscaliza.AI V8</h1><p>Arquitetura paralela em construção.</p>"
