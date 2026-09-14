# Entra ID & Authentication Change Matrix: Velora One Single-Agent Migration

**Date**: 2026-09-07T13:07:00Z  
**Target Environment**: `Velora-AgenticAD-Dev` (`b152cae8-d51e-ef06-9b0a-12ff9d89dc53`)  
**Dataverse Organization ID**: `4b098979-ea1e-450f-bb64-c8c347f485db`  
**Tenant ID**: `7d167021-f5e9-4331-9b75-d44d55a1ce9b`  
**Authoritative Operator**: `balaadm@velora.ae`  

---

## 1. Authentication Governance Principles

1. **No Implicit Token Passing**: Single-agent consolidation inside Copilot Studio does **not** automatically pass the Teams SSO token into every downstream connector or custom API.
2. **Delegated vs Application Identity**: Interactive user operations must never execute via `client_credentials` (application permissions) pretending to represent a user. All user data reads/writes must use delegated user tokens with verified claims (`oid`, `tid`, `sub`, `scp`).
3. **Custom Connector OBO Pattern**: For the retained Azure Productivity API, user requests are authenticated via Entra ID access tokens issued for the API audience. Downstream calls to Microsoft Graph use the RFC 8693 On-Behalf-Of (OBO) flow, trimmed strictly to the operation's required scopes.
4. **Separation of Audit Identity**: Dataverse audit logging writes run under a restricted Dataverse application user with table-level permissions (`cre2f_veloraagentauditlog`), independent of end-user interactive tokens.

---

## 2. Entra Application Registration & Connection Matrix

| Registration / Connection | Actual ID / URI | Existing Configuration | Required Migration Change | Rationale & Justification | Owner | Validation Evidence |
|---|---|---|---|---|---|---|
| **Velora One SSO & Teams Channel App** | Bot App ID: `8bf961c8-f496-f111-b8db-7ced8dac2bdc` | `Integrated` authentication mode; `Always` trigger; Security Group `59f978fe-ff65-4397-9a50-08fe27cb2b87`; Teams preauthorized clients `1fec8e78-bce4-4aaf-ab1b-5451cc387264` (Desktop/Mobile) & `5e3ce6c0-2b1f-4285-8d4b-75ee78787346` (Web). | **RETAIN UNCHANGED**. Verify `access_as_user` scope and redirect URIs. Do not delete or recreate. | Ensures uninterrupted SSO for executive users in Microsoft Teams and M365 Copilot channels. | Identity Admin / Bala Admin | Verified in `settings.mcs.yml` and Copilot Studio Security settings. |
| **Velora Productivity API Resource App** | Client ID: `5d178cb2-251e-436c-b2ec-5f36021d2cf8` | Configured in `ask-productivity/manifest.yml` and `ask-facilitator/manifest.yml`. Previously used `client_credentials` Graph token fallback. | **REFACTOR BACKEND AUTH**. Disallow global app-only Graph token. Require bearer JWT validation at `/api/` endpoints (`iss`, `aud`, `exp`, `scp`). Implement delegated OBO flow for Graph calls. | Prevents unauthorized cross-user mailbox access and ensures strict entitlement boundary. | Backend Lead / Aziz ADM | Code inspection of `mcp-apps/ask-productivity/run_server.py`. |
| **Dataverse Audit Service Principal** | Service Principal in Tenant `7d167021-f5e9-4331-9b75-d44d55a1ce9b` | Configured via `DATAVERSE_CLIENT_SECRET_REF` for server-to-server writes to `cre2f_veloraagentauditlogs`. | **RESTRICT ROLE ASSIGNMENT**. Bind to a custom Dataverse Security Role granting only `Create`, `Read`, `Append`, `AppendTo` on table `cre2f_veloraagentauditlog`. | Guarantees principle of least privilege; prevents central logging credentials from having unrestricted CRM read/write access. | Power Platform Admin | Dataverse solution `cre2f_VeloraExecutiveAgentPlatform`. |
| **Work IQ Mail (Preview)** | Connection Reference: `shared_a365outlookmailmcp` | Direct connection reference in Velora One and Velora Productivity Agent. | **REBIND TO VELORA ONE DIRECT**. Remove child agent routing; bind direct to Velora One authoring canvas. | Enables Velora One to query user emails directly under delegated user context without child agent hop. | Copilot Studio Maker | Live tool inspection in Velora One `actions/MailMCP-WorkIQMailPreview.mcs.yml`. |
| **Work IQ Calendar (Preview)** | Connection Reference: `shared_a365outlookcalendarmcp` | Direct connection reference in Velora One. Available to Velora One; status Enabled (`On`). | **RETAIN DIRECT BINDING**. Keep direct tool binding in Velora One. Remove duplicate child agent route. | Preserves calendar reading, agenda prep, and overlap detection directly in Velora One. | Copilot Studio Maker | Live tool inspection in Velora One `actions/CalendarMCP-WorkIQCalendarPreview.mcs.yml`. |
| **Work IQ Teams (Preview)** | Connection Reference: `shared_a365teamsmcp` | Configured in Velora One connection references; previously assigned to child agent. | **ENABLE DIRECT ON VELORA ONE**. Switch availability from child agent to Velora One. | Enables direct mention and message search in Teams without conversational delegation. | Copilot Studio Maker | Live tool inspection in Velora One `connectionreferences.mcs.yml`. |
| **Microsoft Planner** | Connection Reference: `shared_planner` | Configured in Velora One connection references; previously assigned to child agent. | **ENABLE DIRECT ON VELORA ONE**. Bind `List my tasks`, `Update a task (V2)`, `Create a task` directly to Velora One. | Enables Velora One to manage user tasks and checklist action items directly. | Copilot Studio Maker | Live tool inspection in Velora One `connectionreferences.mcs.yml`. |
| **Work IQ OneDrive & SharePoint** | Connection References: `shared_workiqonedrive`, `shared_workiqsharepoint` | Configured in Velora One connection references; previously assigned to child agent. | **ENABLE DIRECT ON VELORA ONE**. Switch availability from child agent to Velora One. | Provides direct document search and policy discovery with permission-trimmed results. | Copilot Studio Maker | Live tool inspection in Velora One `connectionreferences.mcs.yml`. |
| **Velora Productivity Agent Connection** | Component ID: `820157fd-efe3-4498-8e8b-50feb0cff82b` | Connected child agent entry in Velora One (`agents/Agent`). | **REMOVE CONNECTION & RETIRE**. Detach child connection in Velora One draft; delete child agent after replacement verification. | Consolidates architecture into a single conversational agent per handoff mandate. | Copilot Studio Maker | Cloned agent definition `agents/Agent/agent.mcs.yml`. |

---

## 3. Microsoft Graph Delegated Scope Requirements

For the retained custom Productivity API calling Microsoft Graph via OBO:

| Graph Delegated Scope | Minimum Operation Justification | Trigger / Flow | Governed Control |
|---|---|---|---|
| `Mail.Read` | Read unread, high-importance emails for daily morning brief. | T01, T02, T04 | Delegated read only; no draft or message modification. |
| `Mail.ReadWrite` | Compose and save unsent email draft in user's Drafts folder. | T09 | State machine `PREPARED`; draft preview displayed; **no automated dispatch**. |
| `Mail.Send` | Send email on behalf of user. | Explicit approved write | **Strict State Machine**: `AWAITING_APPROVAL` -> explicit user confirmation with token -> `APPROVED` -> single execution. |
| `Calendars.Read` | Read user schedule, calculate meeting overlaps, meeting prep. | T01, T03, T05, T06 | Delegated read only; no event modification. |
| `Calendars.ReadWrite` | Schedule meetings or update calendar events. | T11 | **Strict State Machine**: Preview presented -> explicit confirmation -> single execution with duplicate suppression. |
| `Tasks.ReadWrite` | Read Planner/To Do tasks and update status for checklist/wrap-up. | T07, T13, T15 | Delegated read and status update; validated owner and dates. |
| `Files.Read.All` | Search OneDrive and SharePoint for authorized enterprise documents. | T10, T14 | Permission-trimmed read only; never broad file write. |

---

## 4. Connection Status & Troubleshooting Protocol

1. **Connection Status Diagnostics**:
   - `Connected`: Valid user token present and active.
   - `Expired / Reauthentication Required`: Refresh token expired or Conditional Access evaluation triggered. Prompt user with actionable sign-in button (Topic: `Signin`).
   - `Missing`: Required connector connection not established. Surface friendly setup instructions; do not fabricate data.
   - `Access Denied`: Resource-level 403 Forbidden. Return honest business message that user lacks permissions for target mailbox/file.
2. **No Mock Fallback Rule**:
   - Under no circumstances will mock, simulated, or demo data be substituted for an unauthenticated or expired connection.
