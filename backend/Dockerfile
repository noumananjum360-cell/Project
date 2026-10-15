FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
# Optional extra CA bundle for TLS-intercepting corporate proxies, provided as a
# BuildKit secret (never stored in the image): --secret id=extra_ca,src=/path/ca.crt
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi; \
    pip install -r requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

# Non-root user; persistent data (vectors, optional uploads) lives in /data (mount a volume).
RUN useradd --create-home --uid 10001 bidgenie \
    && mkdir -p /data/chroma /data/faiss /data/uploads \
    && chown -R bidgenie:bidgenie /data
USER bidgenie

ENV CHROMA_PERSIST_DIRECTORY=/data/chroma \
    FAISS_INDEX_DIRECTORY=/data/faiss \
    UPLOAD_DIRECTORY=/data/uploads

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
