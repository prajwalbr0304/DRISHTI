# DRISHTI ML / analytics service
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# psycopg2-binary ships its own libpq; no build toolchain needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code + SQL migrations (NO secrets baked in; config comes from env).
COPY app ./app
COPY sql ./sql

# Run as non-root.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8080

# DATABASE_URL is supplied at runtime via env (compose / orchestrator), never here.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health').getcode()==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
