FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-por tesseract-ocr-eng \
    unzip coreutils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY .bundle /tmp/fiscaliza-bundle
RUN cat /tmp/fiscaliza-bundle/src*.b64 | tr -d '\n\r' | base64 -d > /tmp/fiscaliza-source.zip \
    && unzip -q /tmp/fiscaliza-source.zip -d /app \
    && rm -rf /tmp/fiscaliza-bundle /tmp/fiscaliza-source.zip

# Melhora a experiência da demonstração: após carregar um cenário,
# leva automaticamente a tela até os resultados.
RUN python -c "from pathlib import Path; p=Path('/app/app.py'); s=p.read_text(); old='result.innerHTML=h}'; new=\"result.innerHTML=h;setTimeout(()=>result.scrollIntoView({behavior:'smooth',block:'start'}),120)}\"; assert old in s; p.write_text(s.replace(old,new))"

RUN pip install --no-cache-dir -r requirements.txt

ENV PORT=8000
ENV OCR_LANG=por+eng
ENV PYTHONUNBUFFERED=1

CMD ["sh","-c","uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
