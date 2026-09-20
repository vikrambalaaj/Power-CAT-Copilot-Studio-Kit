#!/bin/bash
set -e

# ==============================================================================
# Azure Container Apps Deployment Script for Velora Copilot Studio MCP Suite
# Production Release Inventory:
#   1. SF (SuccessFactors MCP)          -> Port 8082 (Internal)
#   2. SAP S/4HANA (Finance MCP)        -> Port 8083 (Internal)
#   3. SAC (Analytics Cloud MCP)        -> Port 8084 (Internal)
#   4. Productivity MCP / Outbox        -> Port 8080 (Internal)
#   5. Facilitator MCP / Memory         -> Port 8085 (Internal)
#   6. Adaptive Card MCP/service        -> Port 8086 (External)
#   7. Scheduled Worker Job             -> Container Apps Job (Periodic scanner/reconciliation)
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source immutable digests if present
if [ -f "${SCRIPT_DIR}/image-digests.env" ]; then
    echo "Loading immutable image digests from image-digests.env..."
    # shellcheck source=/dev/null
    source "${SCRIPT_DIR}/image-digests.env"
fi

# Configuration variables (customize or export as env variables)
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-copilot-studio-mcp}"
LOCATION="${LOCATION:-uaenorth}"
ENVIRONMENT_NAME="${ENVIRONMENT_NAME:-cae-copilot-studio}"
ACR_NAME="${ACR_NAME:-}"
TAG="${TAG:-1.2.0}"
KEY_VAULT_NAME="${KEY_VAULT_NAME:-kv-velora-prod}"
USER_ASSIGNED_IDENTITY_NAME="${USER_ASSIGNED_IDENTITY_NAME:-id-velora-mcp-prod}"
STORAGE_ACCOUNT_NAME="${STORAGE_ACCOUNT_NAME:-stveloramcpprod}"
STORAGE_SHARE_NAME="${STORAGE_SHARE_NAME:-velorastate}"
MOUNT_PATH="${MOUNT_PATH:-/mnt/velora}"
POSTGRES_SERVER_NAME="${POSTGRES_SERVER_NAME:-psql-velora-prod}"
POSTGRES_DB_NAME="${POSTGRES_DB_NAME:-veloradb}"
POSTGRES_ADMIN_USER="${POSTGRES_ADMIN_USER:-veloraadmin}"

# Approved network perimeter defaults (no wildcard * in production)
APPROVED_ALLOWED_HOSTS="${ALLOWED_HOSTS:-fiori.velora.ae,api22.sapsf.com,teams.microsoft.com,copilotstudio.microsoft.com,*.azurecontainerapps.io,localhost}"
APPROVED_CORS_ORIGINS="${CORS_ORIGINS:-https://teams.microsoft.com,https://copilotstudio.microsoft.com,https://fiori.velora.ae}"
S4_PROD_URL="https://fiori.velora.ae/sap/opu/odata4/sap/zfi_sbn_ageingdata_srv/srvd_a2x/sap/zfi_sdf_ageingdata_srv/0001"

# Audience separation: Inbound API audience != outbound Graph/Dataverse audience
ENTRA_TENANT_ID="${ENTRA_TENANT_ID:-7d167021-f5e9-4331-9b75-d44d55a1ce9b}"
ENTRA_INBOUND_AUDIENCE="${ENTRA_INBOUND_AUDIENCE:-api://velora-copilot-mcp}"
GRAPH_RESOURCE_AUDIENCE="https://graph.microsoft.com"
DATAVERSE_HOST="${DATAVERSE_HOST:-org.crm.dynamics.com}"
DATAVERSE_RESOURCE_AUDIENCE="https://${DATAVERSE_HOST}"

# Prerequisite validations
command -v az >/dev/null 2>&1 || { echo "ERROR: Azure CLI ('az') is required but not installed."; exit 1; }

if [ -z "$ACR_NAME" ]; then
    echo "ERROR: Please specify your Azure Container Registry name via ACR_NAME."
    echo "Usage: ACR_NAME=<your_acr_name> ./deploy-azure-containerapps.sh"
    exit 1
fi

ACR_LOGIN_SERVER="${ACR_NAME}.azurecr.io"

# Resolve image reference: per-image immutable digest > explicit ref > tag
get_image_for() {
    local img_name="$1"
    local var_name
    var_name=$(echo "${img_name}" | tr '[:lower:]' '[:upper:]' | tr '-' '_')_DIGEST
    local digest_val="${!var_name}"

    if [ -n "$digest_val" ]; then
        if [[ "$digest_val" == *"@"* ]]; then
            echo "$digest_val"
        else
            echo "${ACR_LOGIN_SERVER}/${img_name}@${digest_val}"
        fi
        return 0
    fi

    local override_ref_var
    override_ref_var=$(echo "${img_name}" | tr '[:lower:]' '[:upper:]' | tr '-' '_')_IMAGE_REF
    local explicit_ref="${!override_ref_var}"
    if [ -n "$explicit_ref" ]; then
        echo "$explicit_ref"
        return 0
    fi

    if [[ "$TAG" == sha256:* ]]; then
        echo "${ACR_LOGIN_SERVER}/${img_name}@${TAG}"
    elif [[ "$TAG" == @sha256:* ]]; then
        echo "${ACR_LOGIN_SERVER}/${img_name}${TAG}"
    else
        echo "${ACR_LOGIN_SERVER}/${img_name}:${TAG}"
    fi
}

echo "=========================================================="
echo "Deploying Velora MCP Services & Card Service to Azure Container Apps"
echo "Resource Group:    $RESOURCE_GROUP"
echo "Location:          $LOCATION"
echo "Environment:       $ENVIRONMENT_NAME"
echo "Registry:          $ACR_LOGIN_SERVER"
echo "Default Tag:       $TAG"
echo "Key Vault:         $KEY_VAULT_NAME"
echo "Identity:          $USER_ASSIGNED_IDENTITY_NAME"
echo "Durable Mount:     $STORAGE_SHARE_NAME -> $MOUNT_PATH"
echo "Inbound Audience:  $ENTRA_INBOUND_AUDIENCE"
echo "Outbound Graph:    $GRAPH_RESOURCE_AUDIENCE"
echo "Outbound DV:       $DATAVERSE_RESOURCE_AUDIENCE"
echo "=========================================================="

# 1. Create Resource Group if not exists
echo ""
echo "--> [Step 1] Ensuring Resource Group exists..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output table

# 2. Ensure Managed Identity exists
echo ""
echo "--> [Step 2] Ensuring User-Assigned Managed Identity exists..."
az identity create --name "$USER_ASSIGNED_IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" --location "$LOCATION" --output table || true
IDENTITY_ID=$(az identity show --name "$USER_ASSIGNED_IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" --query id -o tsv)
IDENTITY_PRINCIPAL_ID=$(az identity show --name "$USER_ASSIGNED_IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" --query principalId -o tsv)

# 2b. Ensure Key Vault exists and grant permissions to Managed Identity
echo ""
echo "--> [Step 2b] Ensuring Key Vault exists and configuring Managed Identity access..."
az keyvault create \
    --name "$KEY_VAULT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --enable-rbac-authorization false \
    --output table || true

az keyvault set-policy \
    --name "$KEY_VAULT_NAME" \
    --object-id "$IDENTITY_PRINCIPAL_ID" \
    --secret-permissions get list \
    --output table || true

# 3. Create Container Apps Managed Environment if not exists
echo ""
echo "--> [Step 3] Ensuring Container Apps Managed Environment exists..."
az containerapp env create \
    --name "$ENVIRONMENT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --output table || true

# 4. Ensure Durable Azure Storage & Environment Mount exist
echo ""
echo "--> [Step 4] Ensuring Durable Azure Files Storage Share & Environment Mount exist..."
az storage account create \
    --name "$STORAGE_ACCOUNT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --sku Standard_LRS \
    --kind StorageV2 \
    --min-tls-version TLS1_2 \
    --output table || true

STORAGE_KEY=$(az storage account keys list --account-name "$STORAGE_ACCOUNT_NAME" --resource-group "$RESOURCE_GROUP" --query '[0].value' -o tsv)
az storage share create --name "$STORAGE_SHARE_NAME" --account-name "$STORAGE_ACCOUNT_NAME" --account-key "$STORAGE_KEY" --output table || true

# Link storage to Container Apps environment
az containerapp env storage set \
    --name "$ENVIRONMENT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --storage-name "$STORAGE_SHARE_NAME" \
    --azure-file-account-name "$STORAGE_ACCOUNT_NAME" \
    --azure-file-account-key "$STORAGE_KEY" \
    --azure-file-share-name "$STORAGE_SHARE_NAME" \
    --access-mode ReadWrite \
    --output table || true

# 4b. Ensure PostgreSQL Flexible Server / Database secret exists
echo ""
echo "--> [Step 4b] Ensuring PostgreSQL Flexible Server & Database URL configuration..."
DATABASE_URL_SECRET=$(az keyvault secret show --vault-name "$KEY_VAULT_NAME" --name "velora-database-url" --query value -o tsv 2>/dev/null || true)
if [ -z "$DATABASE_URL_SECRET" ]; then
    echo "Notice: Initializing velora-database-url placeholder secret in Key Vault..."
    az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name "velora-database-url" \
        --value "postgresql://${POSTGRES_ADMIN_USER}@${POSTGRES_SERVER_NAME}:${POSTGRES_ADMIN_PASSWORD:-ChangeMeSecurely!}@${POSTGRES_SERVER_NAME}.postgres.database.azure.com:5432/${POSTGRES_DB_NAME}?sslmode=require" \
        --output none || true
fi

# 5. Deploy SF (SuccessFactors) Container App (Port 8082, Internal)
echo ""
echo "--> [Step 5] Deploying SuccessFactors MCP Container App (Port 8082, Internal)..."
az containerapp create \
    --name "velora-mcp-sf" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT_NAME" \
    --image "$(get_image_for velora-mcp-sf)" \
    --registry-server "$ACR_LOGIN_SERVER" \
    --user-assigned "$IDENTITY_ID" \
    --target-port 8082 \
    --ingress internal \
    --cpu 0.5 --memory 1.0Gi \
    --min-replicas 1 --max-replicas 2 \
    --secrets \
        mcp-api-key="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-sf-api-key,identityref:${IDENTITY_ID}" \
        sf-password="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-sf-password,identityref:${IDENTITY_ID}" \
    --env-vars \
        ALLOWED_HOSTS="$APPROVED_ALLOWED_HOSTS" \
        ALLOW_ANONYMOUS="false" \
        CORS_ORIGINS="$APPROVED_CORS_ORIGINS" \
        PORT="8082" \
        MCP_API_KEY="secretref:mcp-api-key" \
        SF_PASSWORD="secretref:sf-password" \
        SF_USERNAME="SFAI" \
        SF_COMPANY_ID="etihadairp" \
        SF_API_URL="https://api22.sapsf.com/odata/v2" \
        ENABLE_MUTATING_TOOLS="false" \
        ENABLE_PERSONAL_INFO_TOOL="false" \
        ENFORCE_CONSENT_GATE="true" \
        ENTRA_TENANT_ID="$ENTRA_TENANT_ID" \
        ENTRA_INBOUND_AUDIENCE="$ENTRA_INBOUND_AUDIENCE" \
        AZURE_STORAGE_MOUNT_PATH="${MOUNT_PATH}/sf" \
    --output table

# 6. Deploy SAP S/4HANA Container App (Port 8083, Internal)
echo ""
echo "--> [Step 6] Deploying SAP S/4HANA MCP Container App (Port 8083, Internal)..."
az containerapp create \
    --name "velora-mcp-s4hana" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT_NAME" \
    --image "$(get_image_for velora-mcp-s4hana)" \
    --registry-server "$ACR_LOGIN_SERVER" \
    --user-assigned "$IDENTITY_ID" \
    --target-port 8083 \
    --ingress internal \
    --cpu 0.5 --memory 1.0Gi \
    --min-replicas 1 --max-replicas 2 \
    --secrets \
        mcp-api-key="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-s4-api-key,identityref:${IDENTITY_ID}" \
        s4-password="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-s4-password,identityref:${IDENTITY_ID}" \
    --env-vars \
        ALLOWED_HOSTS="$APPROVED_ALLOWED_HOSTS" \
        ALLOW_ANONYMOUS="false" \
        CORS_ORIGINS="$APPROVED_CORS_ORIGINS" \
        PORT="8083" \
        MCP_API_KEY="secretref:mcp-api-key" \
        S4_AUTH_MODE="basic" \
        S4_USERNAME="xbhaskarraj" \
        S4_PASSWORD="secretref:s4-password" \
        S4_API_URL="$S4_PROD_URL" \
        S4_AR_ENTITY="ARageingData" \
        S4_AP_ENTITY="APageingData" \
        S4_BUDGET_TRANSFER_ENTITY="BudgetTransfer" \
        S4_BUDGET_CONSUMPTION_ENTITY="BudgetConsumSummary" \
        S4_SAP_CLIENT="100" \
        S4_VERIFY_TLS="true" \
        ENTRA_TENANT_ID="$ENTRA_TENANT_ID" \
        ENTRA_INBOUND_AUDIENCE="$ENTRA_INBOUND_AUDIENCE" \
        AZURE_STORAGE_MOUNT_PATH="${MOUNT_PATH}/s4" \
    --output table

# 7. Deploy SAC (SAP Analytics Cloud) Container App (Port 8084, Internal)
echo ""
echo "--> [Step 7] Deploying SAP Analytics Cloud (SAC) MCP Container App (Port 8084, Internal)..."
az containerapp create \
    --name "velora-mcp-sac" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT_NAME" \
    --image "$(get_image_for velora-mcp-sac)" \
    --registry-server "$ACR_LOGIN_SERVER" \
    --user-assigned "$IDENTITY_ID" \
    --target-port 8084 \
    --ingress internal \
    --cpu 0.5 --memory 1.0Gi \
    --min-replicas 1 --max-replicas 2 \
    --secrets \
        mcp-api-key="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-sac-api-key,identityref:${IDENTITY_ID}" \
        sac-client-secret="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-sac-client-secret,identityref:${IDENTITY_ID}" \
    --env-vars \
        ALLOWED_HOSTS="$APPROVED_ALLOWED_HOSTS" \
        ALLOW_ANONYMOUS="false" \
        DEMO_MODE="false" \
        CORS_ORIGINS="$APPROVED_CORS_ORIGINS" \
        PORT="8084" \
        MCP_API_KEY="secretref:mcp-api-key" \
        SAC_AUTH_MODE="oauth" \
        SAC_CLIENT_ID="velora-sac-client" \
        SAC_CLIENT_SECRET="secretref:sac-client-secret" \
        ENTRA_TENANT_ID="$ENTRA_TENANT_ID" \
        ENTRA_INBOUND_AUDIENCE="$ENTRA_INBOUND_AUDIENCE" \
    --output table

# 8. Deploy Productivity MCP Container App (Port 8080, Internal, Durable Outbox Mount)
echo ""
echo "--> [Step 8] Deploying Productivity MCP Container App (Port 8080, Internal)..."
az containerapp create \
    --name "velora-mcp-productivity" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT_NAME" \
    --image "$(get_image_for velora-mcp-productivity)" \
    --registry-server "$ACR_LOGIN_SERVER" \
    --user-assigned "$IDENTITY_ID" \
    --target-port 8080 \
    --ingress internal \
    --cpu 0.5 --memory 1.0Gi \
    --min-replicas 1 --max-replicas 2 \
    --secrets \
        mcp-api-key="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-productivity-api-key,identityref:${IDENTITY_ID}" \
        m365-client-secret="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-m365-client-secret,identityref:${IDENTITY_ID}" \
        database-url="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-database-url,identityref:${IDENTITY_ID}" \
        approval-hmac-secret="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-approval-hmac-secret,identityref:${IDENTITY_ID}" \
    --env-vars \
        ALLOWED_HOSTS="$APPROVED_ALLOWED_HOSTS" \
        ALLOW_ANONYMOUS="false" \
        PORT="8080" \
        MCP_API_KEY="secretref:mcp-api-key" \
        M365_CLIENT_ID="${M365_CLIENT_ID:-}" \
        M365_CLIENT_SECRET="secretref:m365-client-secret" \
        M365_TENANT_ID="${M365_TENANT_ID:-$ENTRA_TENANT_ID}" \
        AZURE_CLIENT_ID="${M365_CLIENT_ID:-}" \
        AZURE_CLIENT_SECRET="secretref:m365-client-secret" \
        AZURE_TENANT_ID="${M365_TENANT_ID:-$ENTRA_TENANT_ID}" \
        DATABASE_URL="secretref:database-url" \
        VELORA_APPROVAL_HMAC_SECRET="secretref:approval-hmac-secret" \
        ENTRA_TENANT_ID="$ENTRA_TENANT_ID" \
        ENTRA_INBOUND_AUDIENCE="$ENTRA_INBOUND_AUDIENCE" \
        API_AUDIENCE="$ENTRA_INBOUND_AUDIENCE" \
        VELORA_OUTBOX_DIR="${MOUNT_PATH}/outbox" \
        AZURE_STORAGE_MOUNT_PATH="${MOUNT_PATH}/outbox" \
    --output table

# 9. Deploy Facilitator MCP Container App (Port 8085, Internal, Durable Memory Mount)
echo ""
echo "--> [Step 9] Deploying Facilitator MCP Container App (Port 8085, Internal)..."
az containerapp create \
    --name "velora-mcp-facilitator" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT_NAME" \
    --image "$(get_image_for velora-mcp-facilitator)" \
    --registry-server "$ACR_LOGIN_SERVER" \
    --user-assigned "$IDENTITY_ID" \
    --target-port 8085 \
    --ingress internal \
    --cpu 0.5 --memory 1.0Gi \
    --min-replicas 1 --max-replicas 2 \
    --secrets \
        mcp-api-key="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-facilitator-api-key,identityref:${IDENTITY_ID}" \
        database-url="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-database-url,identityref:${IDENTITY_ID}" \
    --env-vars \
        ALLOWED_HOSTS="$APPROVED_ALLOWED_HOSTS" \
        ALLOW_ANONYMOUS="false" \
        PORT="8085" \
        MCP_API_KEY="secretref:mcp-api-key" \
        DATABASE_URL="secretref:database-url" \
        ENTRA_TENANT_ID="$ENTRA_TENANT_ID" \
        ENTRA_INBOUND_AUDIENCE="$ENTRA_INBOUND_AUDIENCE" \
        API_AUDIENCE="$ENTRA_INBOUND_AUDIENCE" \
        FACILITATOR_STORAGE_DIR="${MOUNT_PATH}/facilitator" \
        AZURE_STORAGE_MOUNT_PATH="${MOUNT_PATH}/facilitator" \
    --output table

# 10. Deploy Dynamic Adaptive Card Service (Port 8086, External Ingress, Shared Durable Idempotency)
echo ""
echo "--> [Step 10] Deploying Dynamic Adaptive Card Service (Port 8086, External Ingress)..."
az containerapp create \
    --name "velora-mcp-card-service" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT_NAME" \
    --image "$(get_image_for velora-mcp-card-service)" \
    --registry-server "$ACR_LOGIN_SERVER" \
    --user-assigned "$IDENTITY_ID" \
    --target-port 8086 \
    --ingress external \
    --cpu 0.5 --memory 1.0Gi \
    --min-replicas 1 --max-replicas 3 \
    --secrets \
        signing-secret="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-card-signing-secret,identityref:${IDENTITY_ID}" \
        database-url="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-database-url,identityref:${IDENTITY_ID}" \
    --env-vars \
        PORT="8086" \
        NODE_ENV="production" \
        ALLOWED_HOSTS="$APPROVED_ALLOWED_HOSTS" \
        CORS_ORIGINS="$APPROVED_CORS_ORIGINS" \
        TOKEN_SIGNING_SECRET="secretref:signing-secret" \
        DATABASE_URL="secretref:database-url" \
        AZURE_STORAGE_MOUNT_PATH="${MOUNT_PATH}/cards" \
        IDEMPOTENCY_STORAGE_DIR="${MOUNT_PATH}/cards/idempotency" \
    --output table

# 11. Deploy Scheduled Worker (Azure Container Apps Job for finite background outbox & reconciliation)
echo ""
echo "--> [Step 11] Deploying Scheduled Worker Job (Finite Entry Point)..."
az containerapp job create \
    --name "velora-scheduled-worker" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT_NAME" \
    --trigger-type "Schedule" \
    --cron-expression "*/15 * * * *" \
    --image "$(get_image_for velora-mcp-productivity)" \
    --registry-server "$ACR_LOGIN_SERVER" \
    --user-assigned "$IDENTITY_ID" \
    --cpu 0.5 --memory 1.0Gi \
    --command "python" \
    --args "-m" "productivity_mcp.worker" \
    --secrets \
        database-url="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-database-url,identityref:${IDENTITY_ID}" \
        m365-client-secret="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-m365-client-secret,identityref:${IDENTITY_ID}" \
        approval-hmac-secret="keyvaultref:${KEY_VAULT_NAME}/secrets/velora-approval-hmac-secret,identityref:${IDENTITY_ID}" \
    --env-vars \
        VELORA_OUTBOX_DIR="${MOUNT_PATH}/outbox" \
        AZURE_STORAGE_MOUNT_PATH="${MOUNT_PATH}/outbox" \
        DATABASE_URL="secretref:database-url" \
        VELORA_APPROVAL_HMAC_SECRET="secretref:approval-hmac-secret" \
        AZURE_CLIENT_ID="${M365_CLIENT_ID:-}" \
        AZURE_CLIENT_SECRET="secretref:m365-client-secret" \
        AZURE_TENANT_ID="${M365_TENANT_ID:-$ENTRA_TENANT_ID}" \
        REQUIRE_LIVE_DELIVERY="false" \
        RUN_PERIODIC_OUTBOX_SWEEP="true" \
    --output table

echo ""
echo "=========================================================="
echo "All 6 Velora MCP/Card Services and Scheduled Worker deployed!"
echo "Target Ports Verified:"
echo " - SuccessFactors MCP:    Port 8082 (Internal)"
echo " - SAP S/4HANA MCP:       Port 8083 (Internal)"
echo " - SAC Analytics MCP:     Port 8084 (Internal)"
echo " - Productivity MCP:      Port 8080 (Internal)"
echo " - Facilitator MCP:       Port 8085 (Internal)"
echo " - Adaptive Card Service: Port 8086 (External)"
echo " - Scheduled Worker Job:  Container Apps Job (Cron */15 * * * *)"
echo "=========================================================="
