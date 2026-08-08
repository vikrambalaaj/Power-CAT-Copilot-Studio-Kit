FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
COPY s4hana_mcp/ s4hana_mcp/

RUN pip install --no-cache-dir hatchling && pip install --no-cache-dir .

EXPOSE 8083

CMD ["python", "-m", "s4hana_mcp"]
