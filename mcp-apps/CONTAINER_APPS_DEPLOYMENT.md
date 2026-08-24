# Deploying Copilot Studio MCP Servers to Azure Container Apps

This guide explains how to build container images for **SF (SuccessFactors)**, **SAP S/4HANA**, **SAC (SAP Analytics Cloud)**, and **Facilitator**, and deploy them separately to **Azure Container Apps (ACA)**.

---

## 1. Architecture Overview

| MCP Service | Directory | Default Port | Internal Target Port | Health Check Route | MCP Protocol / Transport |
|---|---|---|---|---|---|
| **SF (SuccessFactors)** | `mcp-apps/ask-successfactors` | `8082` | `8082` | `GET /health` | HTTP / Streamable SSE |
| **SAP S/4HANA** | `mcp-apps/ask-s4hana` | `8083` | `8083` | `GET /health` | HTTP / Streamable SSE |
| **SAC (Analytics Cloud)** | `mcp-apps/ask-sac` | `8084` | `8084` | `GET /health` | HTTP JSON-RPC / REST |
| **Facilitator** | `mcp-apps/ask-facilitator` | `8080` | `8080` | `GET /health` | HTTP / Streamable SSE |

---

## 2. Quick Start: Build All Images

To build all 4 images locally with Docker:

```bash
cd mcp-apps
./build_all_images.sh
```

To build and tag for your Azure Container Registry (ACR):

```bash
cd mcp-apps
./build_all_images.sh <your_acr_name>.azurecr.io latest
```

---

## 3. Pushing to Azure Container Registry (ACR)

```bash
# Login to Azure Container Registry
az acr login --name <your_acr_name>

# Tag and push images
docker push <your_acr_name>.azurecr.io/velora-mcp-sf:latest
docker push <your_acr_name>.azurecr.io/velora-mcp-s4hana:latest
docker push <your_acr_name>.azurecr.io/velora-mcp-sac:latest
docker push <your_acr_name>.azurecr.io/velora-mcp-facilitator:latest
```

---

## 4. Deploying to Azure Container Apps (Automated Script)

Run the included deployment script:

```bash
cd mcp-apps
ACR_NAME=<your_acr_name> \
RESOURCE_GROUP=rg-copilot-studio-mcp \
LOCATION=eastus \
./deploy-azure-containerapps.sh
```

---

## 5. Configuration & Environment Variables

### 1. SF (SuccessFactors MCP) - `velora-mcp-sf`
- **Target Port**: `8082`
- **Ingress**: External HTTP / HTTPS
- **Environment Variables**:
  - `SF_API_URL`: SuccessFactors OData API base URL (e.g., `https://apisalesdemo4.successfactors.com/odata/v2`)
  - `SF_COMPANY_ID`: Company ID
  - `SF_USERNAME`: SF technical user or API user
  - `SF_PASSWORD`: SF password / secret
  - `ALLOW_ANONYMOUS`: `"true"` (or set `MCP_API_KEY` for bearer authentication)
  - `ALLOWED_HOSTS`: `"*"`
  - `CORS_ORIGINS`: `"*"`
  - `PORT`: `8082`

### 2. SAP S/4HANA MCP - `velora-mcp-s4hana`
- **Target Port**: `8083`
- **Ingress**: External HTTP / HTTPS
- **Environment Variables**:
  - `S4_API_URL`: S/4HANA API Gateway URL
  - `S4_AUTH_MODE`: `oauth` or `basic`
  - `S4_TOKEN_URL`: OAuth token endpoint (if using OAuth)
  - `S4_CLIENT_ID`: OAuth Client ID
  - `S4_CLIENT_SECRET`: OAuth Client Secret
  - `S4_USERNAME`: Basic auth username (if using basic)
  - `S4_PASSWORD`: Basic auth password (if using basic)
  - `ALLOW_ANONYMOUS`: `"true"` (or `MCP_API_KEY`)
  - `ALLOWED_HOSTS`: `"*"`
  - `CORS_ORIGINS`: `"*"`
  - `PORT`: `8083`

### 3. SAC (SAP Analytics Cloud MCP) - `velora-mcp-sac`
- **Target Port**: `8084`
- **Ingress**: External HTTP / HTTPS
- **Environment Variables**:
  - `SAC_TENANT_URL`: SAP Analytics Cloud tenant URL
  - `SAC_AUTH_MODE`: `oauth`
  - `SAC_TOKEN_URL`: SAC OAuth token URL
  - `SAC_CLIENT_ID`: SAC OAuth Client ID
  - `SAC_CLIENT_SECRET`: SAC OAuth Client Secret
  - `ALLOW_ANONYMOUS`: `"true"`
  - `ALLOWED_HOSTS`: `"*"`
  - `CORS_ORIGINS`: `"*"`
  - `PORT`: `8084`

### 4. Facilitator MCP - `velora-mcp-facilitator`
- **Target Port**: `8080`
- **Ingress**: External HTTP / HTTPS
- **Environment Variables**:
  - `ALLOW_ANONYMOUS`: `"true"`
  - `ALLOWED_HOSTS`: `"*"`
  - `CORS_ORIGINS`: `"*"`
  - `PORT`: `8080`

---

## 6. Verification and Health Probes

Once deployed in Azure Container Apps, verify health checks for each service:

```bash
# SF Health Check
curl https://velora-mcp-sf.<unique-id>.<region>.azurecontainerapps.io/health

# S/4HANA Health Check
curl https://velora-mcp-s4hana.<unique-id>.<region>.azurecontainerapps.io/health

# SAC Health Check
curl https://velora-mcp-sac.<unique-id>.<region>.azurecontainerapps.io/health

# Facilitator Health Check
curl https://velora-mcp-facilitator.<unique-id>.<region>.azurecontainerapps.io/health
```

Expected response for each: `{"status": "ok", ...}` with HTTP 200.
