# Deploying Copilot Studio MCP Servers & Services to Azure Container Apps

This guide explains how to build container images for all 6 services (**SuccessFactors**, **SAP S/4HANA**, **SAC**, **Productivity**, **Facilitator**, and **Dynamic Adaptive Card Service**) and the **Productivity Scheduled Worker**, deploying them to **Azure Container Apps (ACA)**.

---

## 1. Production Architecture Overview

| Service / Container App | Directory | Target Port | Ingress | Health Check Route | Protocol / Storage |
|---|---|---|---|---|---|
| **SF (SuccessFactors)** (`velora-mcp-sf`) | `mcp-apps/ask-successfactors` | `8082` | Internal | `GET /health` | HTTP / Streamable SSE, Key Vault secrets |
| **SAP S/4HANA** (`velora-mcp-s4hana`) | `mcp-apps/ask-s4hana` | `8083` | Internal | `GET /health` | HTTP / Streamable SSE, TLS verified |
| **SAC (Analytics Cloud)** (`velora-mcp-sac`) | `mcp-apps/ask-sac` | `8084` | Internal | `GET /health` | HTTP JSON-RPC / REST, OAuth client |
| **Productivity MCP** (`velora-mcp-productivity`) | `mcp-apps/ask-productivity` | `8080` | Internal | `GET /health` | HTTP / Streamable SSE, PostgreSQL outbox |
| **Facilitator MCP** (`velora-mcp-facilitator`) | `mcp-apps/ask-facilitator` | `8085` | Internal | `GET /health` | HTTP / Streamable SSE, Durable memory |
| **Dynamic Adaptive Card Service** (`velora-mcp-card-service`) | `mcp-apps/dynamic-adaptive-card-service` | `8086` | External | `GET /health` | Fastify REST, Shared durable idempotency |
| **Scheduled Worker Job** (`velora-scheduled-worker`) | `mcp-apps/ask-productivity` | N/A | None | CLI entrypoint | Finite cron job `*/15 * * * *`, lease recovery |

---

## 2. Quick Start: Build All 6 Images

To build all 6 images locally with Docker:

```bash
cd mcp-apps
./build_all_images.sh
```

To build and tag for your Azure Container Registry (ACR):

```bash
cd mcp-apps
./build_all_images.sh <your_acr_name>.azurecr.io v1.2.0
```

---

## 3. Pushing to Azure Container Registry (ACR) with Immutable Digests

Production deployments require immutable image digests (`@sha256:...`) rather than mutable tags (`:latest`).

```bash
# Login to Azure Container Registry
az acr login --name <your_acr_name>

# Build, push, and capture immutable sha256 digests automatically
./build_all_images.sh <your_acr_name>.azurecr.io v1.2.0 --push
```

This generates `mcp-apps/image-digests.env` recording the exact immutable digest for each container:

```bash
source mcp-apps/image-digests.env
```

---

## 4. Deploying to Azure Container Apps (Automated Script)

Run the deployment script with your target ACR, Key Vault, and Azure configuration:

```bash
cd mcp-apps
ACR_NAME=<your_acr_name> \
RESOURCE_GROUP=rg-copilot-studio-mcp \
LOCATION=uaenorth \
ENVIRONMENT_NAME=cae-copilot-studio \
KEY_VAULT_NAME=kv-velora-prod \
USER_ASSIGNED_IDENTITY_NAME=id-velora-mcp-prod \
STORAGE_ACCOUNT_NAME=stveloramcpprod \
STORAGE_SHARE_NAME=velorastate \
./deploy-azure-containerapps.sh
```

---

## 5. Verification and Health Probes

Once deployed in Azure Container Apps, verify health check endpoints for each service:

```bash
# 1. SF Health Check (Port 8082)
curl -s http://velora-mcp-sf:8082/health

# 2. S/4HANA Health Check (Port 8083)
curl -s http://velora-mcp-s4hana:8083/health

# 3. SAC Health Check (Port 8084)
curl -s http://velora-mcp-sac:8084/health

# 4. Productivity Health Check (Port 8080)
curl -s http://velora-mcp-productivity:8080/health

# 5. Facilitator Health Check (Port 8085)
curl -s http://velora-mcp-facilitator:8085/health

# 6. Adaptive Card Service Health Check (Port 8086, External Ingress)
curl -s https://velora-mcp-card-service.<environment-id>.<region>.azurecontainerapps.io/health

# 7. Adaptive Card Template Discovery & Validation
curl -s https://velora-mcp-card-service.<environment-id>.<region>.azurecontainerapps.io/templates
```

Expected response for each health endpoint: `{"status": "ok", ...}` with HTTP 200.
