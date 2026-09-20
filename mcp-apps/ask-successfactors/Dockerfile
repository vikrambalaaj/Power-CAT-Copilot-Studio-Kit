FROM python:3.11-slim

ARG SOURCE_REVISION=unknown
LABEL org.opencontainers.image.title="Velora SuccessFactors MCP" \
      org.opencontainers.image.revision=$SOURCE_REVISION

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt* ./
COPY successfactors_mcp/ successfactors_mcp/
COPY shared_mcp/ shared_mcp/
COPY deploy/copilot-workforce-card-openapi.json deploy/copilot-workforce-card-openapi.json

RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir . && \
    useradd --uid 10001 --create-home appuser && \
    mkdir -p /app/logs && chown appuser:appuser /app/logs

EXPOSE 8082

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8082 \
    SF_API_URL=https://api22.sapsf.com/odata/v2 \
    SF_COMPANY_ID=etihadairp \
    SF_USERNAME=SFAI \
    SF_PASSWORD=Userpassword@2026 \
    ALLOW_ANONYMOUS=false \
    ALLOWED_HOSTS=* \
    CORS_ORIGINS=*

USER 10001:10001

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8082/health', timeout=4)"

CMD ["python", "-m", "successfactors_mcp"]
