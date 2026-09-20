FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY productivity_mcp/ productivity_mcp/
COPY shared_mcp/ shared_mcp/
COPY run_server.py .
COPY productivity-connector-swagger.json .

ENV PORT=8080
EXPOSE 8080

CMD ["python", "run_server.py"]
