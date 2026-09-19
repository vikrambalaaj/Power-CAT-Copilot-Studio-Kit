FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY facilitator_mcp/ facilitator_mcp/
COPY productivity_mcp/ productivity_mcp/
COPY shared_mcp/ shared_mcp/
COPY run_server.py .

EXPOSE 8085

ENV PYTHONUNBUFFERED=1 \
    PORT=8085 \
    ALLOWED_HOSTS=* \
    CORS_ORIGINS=*

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:${PORT:-8085}/health || exit 1

CMD ["python", "-m", "facilitator_mcp"]
