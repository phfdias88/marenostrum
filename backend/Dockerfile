# Imagem slim para reduzir footprint na VPS pequena
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencias minimas para psycopg + build (removidas apos pip install)
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt \
 && apt-get purge -y gcc \
 && apt-get autoremove -y

COPY ./app ./app
COPY ./alembic ./alembic
COPY alembic.ini .
COPY entrypoint.sh .
# Scripts de ingestao/backfill e runners one-off vao pra imagem tambem.
# Antes ficavam de fora (so ./app era copiado), obrigando um `docker compose cp`
# manual pra /tmp em cada ingest — fragil sob pressao (ex: apuracao). Agora
# rodam direto: `docker compose exec api python scripts/<x>.py` ou
# `python backfill_runoff.py` com PYTHONPATH=/app (raiz do WORKDIR).
COPY ./scripts ./scripts
COPY backfill_runoff.py .
RUN chmod +x entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--loop", "uvloop", "--proxy-headers", "--forwarded-allow-ips=*"]
