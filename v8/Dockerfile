FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-por tesseract-ocr-eng && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY v8/requirements.txt /app/v8/requirements.txt
RUN pip install --no-cache-dir -r /app/v8/requirements.txt
COPY v8 /app/v8
ENV PYTHONUNBUFFERED=1
ENV OCR_LANG=por+eng
CMD ["sh","-c","uvicorn v8.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
