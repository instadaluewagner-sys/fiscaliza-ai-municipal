FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-por tesseract-ocr-eng \
    unzip coreutils gzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY .bundle /tmp/fiscaliza-bundle
RUN cat /tmp/fiscaliza-bundle/src0[0-3].b64 | tr -d '\n\r' | base64 -d > /tmp/fiscaliza-source.zip \
    && unzip -q /tmp/fiscaliza-source.zip -d /app \
    && gunzip -c /tmp/fiscaliza-bundle/app_v2.py.gz > /app/app_v2.py \
    && rm -rf /tmp/fiscaliza-bundle /tmp/fiscaliza-source.zip

RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir fastapi uvicorn pymupdf python-multipart reportlab

ENV PORT=8000
ENV OCR_LANG=por+eng
ENV PYTHONUNBUFFERED=1

CMD ["sh","-c","uvicorn app_v2:app --host 0.0.0.0 --port ${PORT:-8000}"]
