FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt* ./
COPY successfactors_mcp/ successfactors_mcp/
COPY shared_mcp/ shared_mcp/

RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir .

EXPOSE 8082

ENV PYTHONUNBUFFERED=1 \
    PORT=8082

CMD ["python", "-m", "successfactors_mcp"]
