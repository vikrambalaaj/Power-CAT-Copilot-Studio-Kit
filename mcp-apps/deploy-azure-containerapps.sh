#!/bin/bash
set -e

# ==============================================================================
# Azure Container Apps Deployment Script for Velora Copilot Studio MCP Servers
# Services:
#   1. SF (SuccessFactors MCP)      -> Port 8082
#   2. SAP S/4HANA (Finance MCP)    -> Port 8083
#   3. SAC (Analytics Cloud MCP)    -> Port 8084
#   4. Productivity MCP / Handoff   -> Port 8080
# ==============================================================================

# Configuration variables (customize or export as env variables)
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-copilot-studio-mcp}"
LOCATION="${LOCATION:-uaenorth}"
ENVIRONMENT_NAME="${ENVIRONMENT_NAME:-cae-copilot-studio}"
ACR_NAME="${ACR_NAME:-}"
TAG="${TAG:-latest}"
KEY_VAULT_NAME="${KEY_VAULT_NAME:-kv-velora-prod}"

if [ -z "$ACR_NAME" ]; then
    echo "ERROR: Please specify your Azure Container Registry name via ACR_NAME."
    echo "Usage: ACR_NAME=<your_acr_name> ./deploy-azure-containerapps.sh"
    exit 1
fi

ACR_LOGIN_SERVER="${ACR_NAME}.azurecr.io"

echo "=========================================================="
echo "Deploying to Azure Container Apps"
echo "Resource Group: $RESOURCE_GROUP"
echo "Location:       $LOCATION"
echo "Environment:    $ENVIRONMENT_NAME"
echo "Registry:       $ACR_LOGIN_SERVER"
echo "Tag:            $TAG"
echo "=========================================================="

# 1. Create Resource Group if not exists
echo ""
echo "--> [Step 1] Ensuring Resource Group exists..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output table

# 2. Create Container Apps Environment if not exists
echo ""
echo "--> [Step 2] Ensuring Container Apps Managed Environment exists..."
az containerapp env create \
    --name "$ENVIRONMENT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --output table || true

# 3. Deploy SF (SuccessFactors) Container App
echo ""
echo "--> [Step 3] Deploying SuccessFactors MCP Container App..."
az containerapp create \
    --name "velora-mcp-sf" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT_NAME" \
    --image "${ACR_LOGIN_SERVER}/velora-mcp-sf:${TAG}" \
    --registry-server "$ACR_LOGIN_SERVER" \
    --target-port 8082 \
    --ingress external \
    --cpu 0.5 --memory 1.0Gi \
    --min-replicas 1 --max-replicas 3 \
    --secrets \
        mcp-api-key="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-sf-api-key" \
        sf-password="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-sf-password" \
    --env-vars \
        ALLOWED_HOSTS="*" \
        ALLOW_ANONYMOUS="false" \
        CORS_ORIGINS="*" \
        PORT="8082" \
        MCP_API_KEY="secretref:mcp-api-key" \
        SF_PASSWORD="secretref:sf-password" \
        SF_USERNAME="SFAI" \
        SF_COMPANY_ID="etihadairp" \
        SF_API_URL="https://api22.sapsf.com/odata/v2" \
        ENABLE_MUTATING_TOOLS="false" \
        ENABLE_PERSONAL_INFO_TOOL="false" \
    --output table

# 4. Deploy SAP S/4HANA Container App
echo ""
echo "--> [Step 4] Deploying SAP S/4HANA MCP Container App..."
az containerapp create \
    --name "velora-mcp-s4hana" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT_NAME" \
    --image "${ACR_LOGIN_SERVER}/velora-mcp-s4hana:${TAG}" \
    --registry-server "$ACR_LOGIN_SERVER" \
    --target-port 8083 \
    --ingress external \
    --cpu 0.5 --memory 1.0Gi \
    --min-replicas 1 --max-replicas 3 \
    --secrets \
        mcp-api-key="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-s4-api-key" \
        s4-password="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-s4-password" \
    --env-vars \
        ALLOWED_HOSTS="*" \
        ALLOW_ANONYMOUS="false" \
        CORS_ORIGINS="*" \
        PORT="8083" \
        MCP_API_KEY="secretref:mcp-api-key" \
        S4_AUTH_MODE="basic" \
        S4_USERNAME="xbhaskarraj" \
        S4_PASSWORD="secretref:s4-password" \
        S4_API_URL="https://fioriqas.velora.ae/sap/opu/odata4/sap/zfi_sbn_ageingdata_srv/srvd_a2x/sap/zfi_sdf_ageingdata_srv/0001" \
        S4_VERIFY_TLS="true" \
    --output table

# 5. Deploy SAC (SAP Analytics Cloud) Container App
echo ""
echo "--> [Step 5] Deploying SAP Analytics Cloud (SAC) MCP Container App..."
az containerapp create \
    --name "velora-mcp-sac" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT_NAME" \
    --image "${ACR_LOGIN_SERVER}/velora-mcp-sac:${TAG}" \
    --registry-server "$ACR_LOGIN_SERVER" \
    --target-port 8084 \
    --ingress external \
    --cpu 0.5 --memory 1.0Gi \
    --min-replicas 1 --max-replicas 3 \
    --secrets \
        mcp-api-key="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-sac-api-key" \
        sac-client-secret="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-sac-client-secret" \
    --env-vars \
        ALLOWED_HOSTS="*" \
        ALLOW_ANONYMOUS="false" \
        DEMO_MODE="false" \
        CORS_ORIGINS="*" \
        PORT="8084" \
        MCP_API_KEY="secretref:mcp-api-key" \
        SAC_AUTH_MODE="oauth" \
        SAC_CLIENT_ID="velora-sac-client" \
        SAC_CLIENT_SECRET="secretref:sac-client-secret" \
    --output table

echo ""
echo "=========================================================="
echo "Deployment completed successfully with Key Vault secret references!"
echo "=========================================================="
