# SpareTwin API imajı. Derleme bağlamı repo kökü olmalı:
#   docker build -f backend/Dockerfile -t sparetwin-api .
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY backend/pyproject.toml backend/
COPY backend/sparetwin backend/sparetwin
RUN pip install ./backend

# Migrasyonlar imajın içinde: müşteri sunucusunda güncelleme = yeni imaj
COPY db db

RUN useradd --system --uid 10001 --home /app sparetwin \
 && mkdir -p /data/media && chown sparetwin /data/media
USER sparetwin

ENV MIGRATIONS_DIR=/app/db/migrations \
    SEED_DIR=/app/db/seed \
    STORAGE_LOCAL_DIR=/data/media

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

CMD ["uvicorn", "sparetwin.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
