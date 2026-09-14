# New development review — 7 September 2026

**Verdict: not ready for completion or Azure-only production sign-off.** Currency handling and presentation have improved, but the new admin check still grants administrator rights by default. Previously reproduced financial, transport and recommendation defects remain. The inspected Azure deployment does not cover the full application.

The requirement is now explicit: **all runtime services, scheduled jobs, persistent queues, audit records and evidence must be Azure-hosted, with no dependency on a local workstation or a container's writable filesystem for durable state.** ACR stores images; Container Apps or another approved Azure service runs workloads. Dataverse remains an approved managed business-record store from the original design; source SAP/Microsoft 365 systems remain external integrations. Review files and test scratch files are development artifacts, not a production architecture.

## 1. New access-control defect remains a release blocker

The new `_extract_and_verify_admin_roles` helper returns Velora_Admin when headers are missing **or when the role header is empty**. A caller can also supply x-user-roles directly; the helper does not verify a signed identity. The new route-level admin checks therefore do not establish trusted authorization.

Offline reproduction:

| Request headers | Returned roles |
|---|---|
| Empty headers | Velora_Admin |
| x-user-roles: Velora_Admin | Velora_Admin |
| x-user-roles: Executive | Executive |

This is not a finding that anonymous internet traffic bypasses every outer authentication layer. It is a finding that the role decision itself grants admin to missing role information and trusts caller-supplied roles. A shared service key must not implicitly grant administrator privileges.

**Required correction:** deny absent/unverified roles, bind permissions to trusted identity, restrict direct-service access where relying on a gateway, and test both missing-role and forged-role cases. Do not introduce test-only permissive fallbacks in production helpers.

Source: [admin role helper:598](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/successfactors_server.py:598). This is the code deciding whether the caller may manage enterprise connections. [Executed role probe](/Users/vikrambala/copilotstudio/docs/aiatc-review-20260907/admin-role-probe.json).

## 2. Actual Azure observations

Read-only checks of resource group `az-vel-agenticad-execai-dev-uaen-rg` and registry `azvelaiagentexecaidevcruaen` returned:

| Item | Observed state | Implication |
|---|---|---|
| ACR repositories | velora-mcp-s4hana and velora-mcp-sf only | No evidence here of images for Productivity, Facilitator, SAC or scheduled workers. |
| Container Apps | One app: agenticad-execai-dev-uaen-ca-001 | No evidence here that all five services run in Container Apps. |
| Running image reference | velora-mcp-s4hana:1.1.7 | Tag reference; no evidence tying its image content to the latest reviewed working tree. |
| Latest ready revision | agenticad-execai-dev-uaen-ca-001--0000022 | A ready revision exists; business-flow readiness was not tested. |
| Ingress | External | Approved perimeter/gateway/user authorization must be verified. |
| Managed identity | None | The requested managed-identity-based access model is not established on this app. |
| Mounted volumes | None | No durable filesystem mount is demonstrated for local-file queues/evidence. |

These observations are limited to the inspected resource group and registry. They do not prove that no other Azure resources exist elsewhere. No deployment, secret provisioning or business call was performed.

[Azure observation record](/Users/vikrambala/copilotstudio/docs/aiatc-review-20260907/AZURE_OBSERVATIONS.json).

## 3. Azure-only deployment requirement is not met

| Current dependency | Why it remains a gap | Required production outcome |
|---|---|---|
| Recommendation files under /tmp/velora_outbox | Container-local files are the default queue, recommendation and episode store. | Azure-hosted durable state and queue with atomic claims, restart/replacement recovery and retry reconciliation. |
| SF audit spool under the process user's home directory | A home-directory path does not establish managed persistent Azure storage. | Durable Azure audit ingestion with unique event IDs and confirmed sink acknowledgement. |
| Facilitator JSONL records under the process user's home directory | Local files and constructed links do not prove records were saved in the named institutional repository. | Approved Azure/Dataverse institutional records with ACL, retention, versions and real evidence references. |
| General deployment script | Creates only SF, S4 and SAC; its heading mentions Productivity but no corresponding create operation exists; Facilitator/worker absent. | Complete release inventory and deployment definitions for every runtime component. |
| General deployment defaults | Uses mutable latest tag, external ingress, broad hosts and a QAS S4 URL. | Tested immutable digests, production source configuration, managed identities/secrets and approved network controls. |
| SF Bicep template | Has useful managed identity, Key Vault references and probes, but covers SF only and defines no durable queue/storage integration. | Equivalent verified controls and operational configuration for all services. |

Sources: [recommendation storage:214](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py:214), [SF spool:41](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/background_logger.py:41), [Facilitator storage:46](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:46), [general deployment script](/Users/vikrambala/copilotstudio/mcp-apps/deploy-azure-containerapps.sh), [SF template](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/deploy/containerapp.bicep). These files show where runtime state is kept and which components a deployment would create.

## 4. Previously identified defects rechecked

Independent offline probes still reproduced the following:

| Finding | Current result | Existing action/test mapping |
|---|---|---|
| Numeric SAP amount precision | 9007199254740993.01 read as 9007199254740994.0 | A01 / T01 |
| Invalid money | Invalid amount becomes 0.00 | A01 / T02 |
| Serializer string collision | CustomerName __EXACT_DEC_123__ becomes numeric 123 | A01 / T03 |
| Budget source keys | Valid distinct movement items and consumption periods rejected as conflicts | A02 / T07–T08 |
| Exact service root | Sibling root ending 0001evil accepted | A02 / T24 |
| Streamable MCP | Initialize returns HTTP 500 | A04 / T18 |
| Partial recommendations | PARTIAL snapshot emits a recommendation despite requires_complete | A06 / T33 |
| Delivery assurance | Sender result ERROR with no receipt becomes DELIVERED, even with live-delivery gate enabled | A07 / T40 |
| Named institutional destination | Loop save reports success and constructs link without a provider write | A12 / T59 |

The exact-field multi-currency checks now succeed across all four reports. Recommendation details also recover in the simple single-process restart probe. Preserve those improvements while fixing remaining cases.

[Executed probe results](/Users/vikrambala/copilotstudio/docs/aiatc-review-20260907/probe-results.json). Each probe uses synthetic data and local mocks; none calls SAP or sends a message.

## 5. Detailed audit-log acceptance requirements

The existing audit schema/spool is a foundation, not yet sufficient evidence of complete governed logging. A production run must record, in an access-controlled Azure/Dataverse destination:

- Stable event ID, correlation/run ID, tenant, trusted requesting identity and executing service identity.
- Requested capability/action, organization/record scope, authorization and consent decision, and explicit denial reason where applicable.
- Source system/report, safe filters, measurement/retrieval/update times, completeness and quality limitations.
- Applied configuration, policy, KPI/rubric/rule version, approved preview and approval reference where relevant.
- Start, completion/error, retry and recovery events; provider acceptance/result and actual object/receipt reference; unknown outcomes must remain unknown.
- Immutable or versioned decision evidence sufficient to explain the answer in plain language, without recording credentials or unnecessary personal data.
- Retention/access policy, operational alerts on logging failures, replay/reconciliation evidence and recoverability after container replacement.

For a multi-event turn, each event must survive independently; turn_id alone is not a sufficient event key. A local buffer acknowledgement is not a Dataverse commit. A received HTTP request is not proof of completed business work.

**Required proof:** one normal read, denied read, approved write, failed write, retry, duplicate request and recovery scenario traced from Copilot through service/source to durable audit evidence. Inspect the deployed logging configuration and resulting records; code labels alone are insufficient.

## 6. Test results and release sequence

Reran the two changed service suites in offline isolation:

- S4: **29/29 passed** — [log](/Users/vikrambala/copilotstudio/docs/aiatc-review-20260907/ask-s4hana-tests.log).
- SuccessFactors: **85/85 passed** — [log](/Users/vikrambala/copilotstudio/docs/aiatc-review-20260907/ask-successfactors-tests.log).

The independent probes above expose gaps outside those test assertions. The other three service suites were not rerun in this incremental review; their earlier results remain in the full review. No live Finance reconciliation, actual Copilot acceptance, image scan, load test or deployment rollback was executed in this turn.

Recommended order for the authorized development team:

1. Fix the admin default/identity boundary and financial/transport defects.
2. Enforce recommendation input quality and truthful provider-result handling.
3. Replace runtime-local durable state with approved Azure-hosted stores/queues; wire audit ingestion and recovery.
4. Create complete image/deployment definitions for all services and workers, including immutable digest references, identities, secrets, network controls, diagnostics, health checks and rollback.
5. Import/verify Dataverse components and executable flows; finish agent lifecycle, meeting, evaluation and benchmark business flows.
6. Execute the 78-case test catalog plus the Azure-only checks below; complete source-owner reconciliation and Copilot acceptance before sign-off.

The existing [22-action / 78-test tracker](/Users/vikrambala/copilotstudio/docs/aiatc-review-20260906/AIATC_Pending_Actions_and_Test_Cases_06Sep2026.xlsx) remains the base handover. Add these release checks:

| Check | Expected evidence |
|---|---|
| Complete Azure inventory | Every service/worker has an ACR digest and named running Azure resource; no workstation scheduler or runtime dependency. |
| No local persistent state | Delete/replace a container and all disposable disk contents; pending work, audit and institutional records remain intact in Azure. |
| Managed identities and secret references | Each app accesses only its approved resources; no baked-in secret; unauthorized identity denied. |
| Admin role negative tests | Missing, blank and forged role headers never grant admin privileges. |
| End-to-end audit | All required event fields and real outcomes retrievable for success/denial/error/retry/recovery, with no secrets in logs. |
| Revision traceability | Deployed digest is the tested artifact and source revision; health checks, rollback and business smoke results retained. |

This review was completed on **7 September 2026**. It is a review and handover update, not a deployment completion claim.
