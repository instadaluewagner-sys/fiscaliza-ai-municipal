from pathlib import Path
from typing import List
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from v8.modules.penalizacao import analyze_penalizacao
from v8.services.document_segmenter import segment_documents
from v8.services.pdf_reader import extract_pages

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Fiscaliza.AI V8", version="8.0.0-alpha.1")

if (BASE_DIR / "static").exists():
    app.mount("/v8-static", StaticFiles(directory=BASE_DIR / "static"), name="v8-static")

@app.get("/api/v8/health")
def health():
    return {"ok": True, "version": app.version, "status": "parallel-rebuild"}

@app.post("/api/v8/analyze")
async def analyze(module: str = "penalizacao", files: List[UploadFile] = File(...)):
    if module != "penalizacao":
        raise HTTPException(400, "Na V8 alpha, apenas Penalização está habilitada para validação.")
    pages = []
    ocr_pages = 0
    names = []
    for upload in files:
        if not (upload.filename or "").lower().endswith(".pdf"):
            continue
        try:
            extracted, ocr_count = extract_pages(await upload.read(), upload.filename)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        pages.extend(extracted)
        ocr_pages += ocr_count
        names.append(upload.filename)
    if not pages:
        raise HTTPException(400, "Envie pelo menos um PDF válido.")

    documents = segment_documents(pages)
    result = analyze_penalizacao(documents)
    return {
        "version": app.version,
        "files": names,
        "pages": len(pages),
        "ocr_pages": ocr_pages,
        "analysis": result.model_dump(),
    }

@app.get("/", response_class=HTMLResponse)
def index():
    path = BASE_DIR / "templates" / "index.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "<h1>Fiscaliza.AI V8</h1><p>Arquitetura paralela em construção.</p>"
