# Live Cloud Backup & Restoration Runbook: Velora Agents & Dataverse Solutions

**Created**: 2026-09-07T12:59:36Z  
**Source Environment**: `Velora-AgenticAD-Dev` (ID: `b152cae8-d51e-ef06-9b0a-12ff9d89dc53`)  
**Dataverse URL**: `https://org4b098979.crm15.dynamics.com/`  
**Authenticated Operator**: `balaadm@velora.ae`  
**Git Base Revision**: `76511dcc51b9c58faced07d939b67127b066e8d9`  

---

## 1. Verified Cloud Backup Archive Inventory

| Archive / Artifact | Type | SHA-256 Checksum | Contents & Components |
|---|---|---|---|
| `cre2f_VeloraExecutiveAgentPlatform.zip` | Dataverse Solution (Unmanaged) | `b18a54e4a407b22da2097722149a7b0c4887187e9534def34475e44d6e0d24c3` | `cre2f_veloraagentauditlog` (Table), `cre2f_botuserconsent` (Table), `cre2f_veloradatadisclosurepolicy` (Table) |
| `veloraProductivityApi_1788000763691.zip` | Dataverse Solution (Unmanaged) | `b74a269e1724406ae9741e34a9ffc740d2054b6b4fd2d4d81b51576d30b992f9` | `cre2f_5Fvelora-20productivity-20api` (Custom Connector) |
| `APEmailAIAutomation.zip` | Dataverse Solution (Unmanaged) | `2c363e2b0c3614a57c3947fcc4c16b9d73adcbf7d4ffde4646ad0f22ebe3bdb1` | Email automation workflows and connection references |
| `velora-one-live-agent-backup.zip` | Live Agent Clone (Full Workspace) | `9ade400fee625d46c2441988e33ac0d70f7d3ad1a5502e19cdfaa8f239c20829` | Bot `8bf961c8-f496-f111-b8db-7ced8dac2bdc` full workspace: 15 actions, 34 topics, knowledge attachments, settings, connection references |
| `velora-productivity-agent-live-agent-backup.zip` | Live Agent Clone (Full Workspace) | `f26b93302e83756470267749f32eed1f1d0762b011a6a44a6ab3a957b7d9a625` | Bot `bf52d31c-b1a2-f111-b8dd-7ced8dac2bdc` full workspace: 10 actions, 13 topics, connection references, settings |

Integrity status for all 5 archives: `zip -T OK`.

---

## 2. Identified Component IDs

- **Velora One Bot ID**: `8bf961c8-f496-f111-b8db-7ced8dac2bdc` (Schema name: `new_VeloraExecutiveAgent`)
- **Velora Productivity Agent Bot ID**: `bf52d31c-b1a2-f111-b8dd-7ced8dac2bdc` (Schema name: `cre2f_VeloraProductivityAgent`)
- **Connected Child Agent Component ID in Velora One**: `820157fd-efe3-4498-8e8b-50feb0cff82b`
- **Dataverse Organization ID**: `4b098979-ea1e-450f-bb64-c8c347f485db`
- **Tenant ID**: `7d167021-f5e9-4331-9b75-d44d55a1ce9b`

---

## 3. Step-by-Step Restoration Procedure

In the event that a restoration to an authorized development or recovery environment is required:

### Step 3.1: Authenticate Power Platform CLI
```bash
pac auth create --deviceCode --environment <TARGET_ENV_ID_OR_URL>
pac auth select --name <PROFILE_NAME>
```

### Step 3.2: Import Core Dataverse Solutions in Order
The foundational platform tables and connectors must be imported prior to pushing agent configurations:
```bash
# 1. Import Dataverse Platform Tables (Audit, Consent, Disclosure)
pac solution import --path cre2f_VeloraExecutiveAgentPlatform.zip --async

# 2. Import Productivity API Custom Connector
pac solution import --path veloraProductivityApi_1788000763691.zip --async

# 3. Import Email Automation Solution
pac solution import --path APEmailAIAutomation.zip --async
```

### Step 3.3: Restore Agent Workspaces
Extract the cloned workspaces and push to target Copilot Studio:
```bash
# Unzip workspaces
unzip velora-one-live-agent-backup.zip
unzip velora-productivity-agent-live-agent-backup.zip

# Push agents into target environment
cd "velora-one-clone/Velora One"
pac copilot push

cd "../../velora-productivity-agent-clone/Velora Productivity Agent"
pac copilot push
```

### Step 3.4: Rebind Connection References
In Power Apps / Copilot Studio for the restored environment:
1. Open **Solutions** -> select each imported solution.
2. Under **Connection References**, rebind:
   - `Office 365 Outlook` -> Bind to target user/service connection.
   - `Microsoft Dataverse` -> Bind to current environment connection.
   - `shared_workiqmail` / `shared_workiqcalendar` / `shared_workiqteams` -> Authenticate M365 user credentials.
   - `shared_cre2f-5fvelora-20productivity-20api` -> Bind Entra client credentials with delegated OBO token exchange.

### Step 3.5: Republish Agents
```bash
pac copilot publish --bot 8bf961c8-f496-f111-b8db-7ced8dac2bdc
pac copilot publish --bot bf52d31c-b1a2-f111-b8dd-7ced8dac2bdc
```
Verify Teams and M365 channel settings.
