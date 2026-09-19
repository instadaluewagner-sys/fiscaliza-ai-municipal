FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-por tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY app_v33.py /app/app_v33.py
COPY rc1_patch.py /app/rc1_patch.py
COPY profile_pimenta_bueno.py /app/profile_pimenta_bueno.py

RUN pip install --no-cache-dir fastapi uvicorn pymupdf python-multipart reportlab pytesseract pillow

ENV PORT=8000
ENV OCR_LANG=por+eng
ENV PYTHONUNBUFFERED=1

CMD ["sh","-c","uvicorn rc1_patch:app --host 0.0.0.0 --port ${PORT:-8000}"]
