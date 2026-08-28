FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt* ./
COPY s4hana_mcp/ s4hana_mcp/

RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir .

EXPOSE 8083

ENV PYTHONUNBUFFERED=1 \
    PORT=8083 \
    ALLOW_ANONYMOUS=true \
    ALLOWED_HOSTS=* \
    CORS_ORIGINS=*

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://127.0.0.1:${PORT:-8083}/health || exit 1

CMD ["python", "-m", "s4hana_mcp"]

