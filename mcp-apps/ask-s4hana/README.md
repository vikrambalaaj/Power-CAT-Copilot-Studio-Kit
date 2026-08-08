# SAP S/4HANA finance MCP server

This is the second MCP server used by the Velora Executive Agent. It is read-only and exposes four finance tools: receivables aging, payables aging, profit and loss, and budget variance.

## Configure

Copy `.env.example` to `.env` and set the S/4HANA URL, authentication, four approved service/entity paths, MCP API key, and allowed production hostname.

`S4_AUTH_MODE` supports:

- `oauth`: client-credentials token from `S4_TOKEN_URL`.
- `basic`: a narrowly scoped technical user. Use only when formally approved.

Entity values are relative paths beneath `S4_API_URL`. They must point to released, allowlisted CDS/OData services approved by the finance owner. The server does not accept arbitrary entity names from callers.

## Run locally

```text
pip install -e .
python -m s4hana_mcp
```

Health: `http://localhost:8083/health`

MCP: `http://localhost:8083/mcp`

The MCP endpoint requires `X-API-Key` or the same value as a bearer token. Anonymous mode is for explicit local development only.

## Deploy

Deploy independently from SuccessFactors. Give it a separate hostname, MCP secret, SAP identity, network policy, logs, and scaling policy. Never reuse SuccessFactors credentials.

The tool and response requirements are defined in [MCP_CONTRACTS.md](../ask-successfactors/MCP_CONTRACTS.md), and production gates are defined in [DEPLOYMENT.md](../ask-successfactors/DEPLOYMENT.md).

Successful finance reads use a short, bounded cache and OAuth access tokens are reused until shortly before expiry. See [Caching](../ask-successfactors/CACHE.md) for configuration and operational guidance.
