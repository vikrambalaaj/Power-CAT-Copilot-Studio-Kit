# Velora Platform - Production Deployment & Acceptance Runbook

This runbook guides DevOps, Security, and Engineering teams through the deployment, configuration, and verification of the remediated Velora Executive AI Platform services on Azure Container Apps.

---

## 1. Scope & Architecture Summary

The Velora Executive AI Platform provides autonomous executive intelligence and governed productivity actions across five MCP microservices and one scheduled worker:

1. **SuccessFactors MCP (`velora-mcp-sf`)**: HR & headcount analytics (Port 8082).
2. **S/4HANA Finance MCP (`velora-mcp-s4hana`)**: Financial aging & receivables (Port 8083). P&L is excluded.
3. **Analytics Cloud MCP (`velora-mcp-sac`)**: Executive margin & commercial performance (Port 8084).
4. **Productivity MCP (`velora-mcp-productivity`)**: M365 two-step writes, outbox, and approval state machine (Port 8080).
5. **Facilitator MCP (`velora-mcp-facilitator`)**: Context memory & briefing facilitation (Port 8085).
6. **Scheduled Worker (`velora-scheduled-worker`)**: Finite Container Apps Job running background outbox sweeps and lease reconciliation.

---

## 2. Pre-Deployment Prerequisites

Before executing the deployment script, verify that the following infrastructure and identity components are provisioned in Azure:

### 2.1 Azure Infrastructure
- **Resource Group**: `rg-copilot-studio-mcp` in `uaenorth` (or approved region).
- **Container Apps Environment**: `cae-copilot-studio` configured with internal or custom VNet ingress.
- **Azure Container Registry (ACR)**: ACR instance containing immutable image digests for the release (`@sha256:...`).
- **Azure Storage Account**: Standard LRS V2 with Azure Files share `velorastate`.
  - Environment storage link: `az containerapp env storage set ... --access-mode ReadWrite`.
- **Azure Key Vault**: `kv-velora-prod` with Managed Identity access policies or Azure RBAC (`Key Vault Secrets User`).

### 2.2 Microsoft Entra ID & App Registrations
1. **Inbound MCP Audience**:
   - Application Registration: `api://velora-copilot-mcp`.
   - Exposed API Scopes: `M365.ExecutiveWrite`, `Finance.Read`, `HR.Read`.
   - App Roles: `Velora_Admin`, `Velora_Executive`.
2. **Outbound Microsoft Graph (Delegated / Managed Identity)**:
   - Required delegated Graph permissions: `Mail.Send`, `Calendars.ReadWrite`, `Tasks.ReadWrite`, `Chat.ReadWrite`.
   - Admin consent granted.
3. **Microsoft Dataverse Application User**:
   - Register Application User corresponding to the Managed Identity in the target Dataverse environment (`velora-prod.crm.dynamics.com`).
   - Assign security role granting `Create`, `Read`, `Append`, and `AppendTo` on the `cre2f_veloraagentauditlogs` table.

---

## 3. Configuration & Secrets Mapping

Populate secrets in Azure Key Vault before deployment:

| Key Vault Secret Name | Purpose | Consuming Service |
|---|---|---|
| `velora-sf-api-key` | Inter-service API key | `velora-mcp-sf` |
| `velora-sf-password` | SAP SF Basic Auth password | `velora-mcp-sf` |
| `velora-s4-api-key` | Inter-service API key | `velora-mcp-s4hana` |
| `velora-s4-password` | SAP S/4 Basic Auth password | `velora-mcp-s4hana` |
| `velora-sac-api-key` | Inter-service API key | `velora-mcp-sac` |
| `velora-sac-client-secret` | SAC OAuth2 Client Secret | `velora-mcp-sac` |
| `velora-productivity-api-key` | Inter-service API key | `velora-mcp-productivity` |
| `velora-m365-client-secret` | Entra ID App Client Secret | `velora-mcp-productivity` |
| `velora-facilitator-api-key` | Inter-service API key | `velora-mcp-facilitator` |

---

## 4. Step-by-Step Deployment Execution

Execute the authoritative deployment script using immutable image digests:

```bash
# 1. Authenticate to Azure
az login --identity # or az login with authorized SPN

# 2. Export deployment environment parameters
export RESOURCE_GROUP="rg-copilot-studio-mcp"
export LOCATION="uaenorth"
export ENVIRONMENT_NAME="cae-copilot-studio"
export ACR_NAME="acrveloraprod"
export TAG="@sha256:7f8e8a71b..."  # Replace with immutable image digest
export KEY_VAULT_NAME="kv-velora-prod"
export USER_ASSIGNED_IDENTITY_NAME="id-velora-mcp-prod"
export STORAGE_ACCOUNT_NAME="stveloramcpprod"
export STORAGE_SHARE_NAME="velorastate"
export ENTRA_TENANT_ID="<your-tenant-uuid>"
export ENTRA_INBOUND_AUDIENCE="api://velora-copilot-mcp"

# 3. Execute authoritative deployment script
cd mcp-apps
chmod +x deploy-azure-containerapps.sh
./deploy-azure-containerapps.sh
```

---

## 5. Post-Deployment Acceptance Verification Checklist

Execute these verifications after container deployment:

### Check 1: Health Endpoints (Unauthenticated)
Verify that public health probes respond with `HTTP 200 OK` and contain no secret details:
```bash
curl -I https://velora-mcp-productivity.internal.../healthz
curl -I https://velora-mcp-s4hana.internal.../healthz
curl -I https://velora-mcp-sf.internal.../healthz
curl -I https://velora-mcp-facilitator.internal.../healthz
```

### Check 2: Unauthenticated Business Route Rejection
Verify that business routes fail closed when no bearer token is provided:
```bash
curl -i -X POST https://velora-mcp-productivity.internal.../mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "prepare_email"}}'
# Expected: HTTP 401 Unauthorized (Empty/Missing Bearer Token)
```

### Check 3: Forged Identity Rejection
Verify that supplying a forged `x-ms-client-principal` header without a valid gateway signature is rejected:
```bash
curl -i -X POST https://velora-mcp-sf.internal.../admin/policies \
  -H "x-ms-client-principal: eyJjbGFpbXMiOiBbeyJ0eXAiOiAibmFtZSIsICJ2YWwiOiAiYXR0YWNrZXIifV19"
# Expected: HTTP 401 Unauthorized (Untrusted gateway assertion rejected)
```

### Check 4: Cross-Instance Approval Replay Protection
1. Execute `prepare_email` using a valid user token. Obtain `confirmationToken`.
2. Execute `send_approved_email` once. Expected: `SUCCESS`.
3. Immediately retry `send_approved_email` with the same token against a second replica.
   - Expected: Safe idempotent response returning the original `externalObjectId`, without generating a second email.

### Check 5: Facilitator GET Mutation Protection
Verify that HTTP GET requests cannot trigger email sends:
```bash
curl -i -X GET https://velora-mcp-facilitator.internal.../api/send_executive_email
# Expected: HTTP 405 Method Not Allowed
```

### Check 6: Scheduled Worker Finite Execution
Check Container Apps Job execution history:
```bash
az containerapp job execution list \
  --name "velora-scheduled-worker" \
  --resource-group "rg-copilot-studio-mcp" \
  --output table
# Expected: Status = Succeeded, Duration < 30 seconds, ExitCode = 0
```

---

## 6. Incident Response & Troubleshooting

### Problem: Governed writes return `FAIL_CLOSED_BLOCKED`
- **Root Cause**: The Dataverse compliance audit destination is offline or unreachable, and the service is operating in strict fail-closed mode (`STRICT_FAIL_CLOSED_AUDIT=1`).
- **Remediation**: Check Dataverse environment availability and verify that the Managed Identity's application-user mapping in Dataverse has not expired or lost role assignments.

### Problem: Notification delivery in `RECONCILING` status
- **Root Cause**: A worker node encountered a network timeout or crashed after initiating an email send to Microsoft Graph.
- **Remediation**: Inspect Microsoft Graph Message Tracking / Outbox for the recipient. If the email was received, execute the outbox reconciliation CLI to mark `DELIVERED`. If not received, clear the reconciliation lock to re-queue. Do NOT manually resend blindly.
