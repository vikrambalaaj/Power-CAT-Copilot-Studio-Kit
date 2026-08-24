FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt ./
COPY sac_mcp/ sac_mcp/

RUN pip install --no-cache-dir setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir .

EXPOSE 8084

ENV PYTHONUNBUFFERED=1 \
    PORT=8084

CMD ["python", "-m", "sac_mcp"]
