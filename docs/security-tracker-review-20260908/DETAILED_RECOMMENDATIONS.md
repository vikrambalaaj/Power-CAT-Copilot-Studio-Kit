# Exec AI Agent security tracker: detailed fix recommendations

Review date: 8 September 2026. Scope: recommendation review and targeted current-source inspection, not implementation, penetration testing, or production verification.

## Decision

Use the workbook as the control baseline, but do not approve production on its present evidence. It contains 58 controls across two sheets: 28 AIDEV controls and 30 MCP controls. Three are marked In Progress (AIDEV-01, AIDEV-02, AIDEV-25); 55 are Not Started; none is marked complete. These are workbook statuses, not an independent measurement of implementation. The security-assessment vendor onboarding note is a dependency, not proof of completed testing.

The controls are broadly appropriate. They must be converted from requirements into owner-assigned changes with measurable acceptance evidence. The accompanying CONTROL_FIX_MATRIX.csv preserves every original requirement, owner, and status and adds a proposed action, work package, and closure test.

No application code or original workbook was modified in this review. Cloudflare, Quilr, MeshX, SAP, Entra, Copilot Studio, and Azure live configuration were not inspected. Architecture claims about them remain to be verified with their owners. Local source was changing between reviews; freeze a revision before implementation and retest rather than relying on historical line numbers.

## Important clarifications to the tracker

1. **Workload identity does not replace user authorization.** AIDEV-05 and AIDEV-07 must work together: dedicated service identities plus authenticated user context and downstream resource authorization. A broad service account must not turn a user-limited request into unrestricted access.
2. **Separate SAP/MeshX reads from M365 writes.** MCP-07 calls for read-only MeshX/SAP capabilities. AIDEV-06 and AIDEV-14 allow separately approved consequential operations. Keep SAP/MeshX modification tools absent; enable a distinct M365 write capability only after approved business scope and backend approval enforcement. A signed token alone is not evidence that a person confirmed the preview.
3. **Do not invent a universal gateway topology.** AIDEV-09/MCP-13 require a documented per-flow route. Establish which calls originate in customer-controlled Azure versus Microsoft-managed connectors. Verify which can traverse Quilr and Cloudflare and what each product inspects. Where a required route cannot be enforced, redesign, disable that integration, or obtain an explicit time-bound exception with compensating controls. Do not silently claim compliance.
4. **Do not block all private addresses.** MCP-14 should prevent access to unauthorized internal services and metadata endpoints while allowing explicitly approved private SAP/MeshX endpoints. Validate the destination after DNS resolution and redirects, as well as at the network boundary.
5. **Output controls are not authorization.** Redaction must follow source permission enforcement, field minimization, and retrieval filtering. Do not send unauthorized data to the model and rely on filtering afterward.
6. **Log evidence, not unrestricted content.** AIDEV-20's prompt/output logging must be reconciled with AIDEV-18/28. Default to safe event metadata, references, classification and versions. Store approved content evidence separately under access and retention controls. Avoid unhashed secrets and avoid treating a content hash as anonymization.
7. **Protect correlation without treating it as identity.** Generate a trusted internal trace ID at the boundary; retain any client ID separately as untrusted input. Propagate over authenticated channels. If a gateway assertion carries it, sign the relevant context. It never grants permission.
8. **Remove test bypasses from production authentication.** Test environment variables must not change production signature, issuer or audience validation. Inject test providers in tests instead.
9. **Avoid absolute detection claims.** Poisoned content and unsafe instructions cannot reliably be eliminated by a prompt or scanner. Combine detection with controls that block unauthorized effects even when detection misses an attack.

## Current source evidence: what to fix versus reverify

| Observation | Recommendation | Evidence |
|---|---|---|
| Productivity `/handoff` reads userObjectId/userEmail from the request; the inspected route has no auth dependency and its runner starts that app directly. | P1: bind all requests to verified identity before routing; test the deployed ingress separately. A helper module existing elsewhere does not secure this endpoint. | [server.py](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/server.py:103) |
| New shared identity code exists. It permits absent expiry, uses issuer prefix comparison, has environment-controlled test validation behavior, and relies on a configured public key rather than discovered rotating keys. | P1: replace custom token verification with a maintained verifier and strict configured claims. Do not claim a production exploit from test-only branches, but remove the deployment hazard. | [identity.py](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/shared_mcp/identity.py:112) |
| Gateway nonce state is process-local; the inspected canonical signature omits HTTP method, target route and body. | P1 if assertions are used: bind assertions to intended request/resource and use shared atomic replay control. Inspect all identity-module copies for drift. | [identity.py](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/shared_mcp/identity.py:269) |
| Facilitator REST routes now check identity and reject mutating GETs, but MCP tools are directly registered with handlers outside that REST wrapper. | P1: prove and enforce equivalent checks on MCP tools/call and every alias. This is a source-indicated coverage gap, not a new live exploit test. | [server.py](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/server.py:64) |
| SuccessFactors admin helper now verifies tokens/assertions first but retains configurable EasyAuth trust and a pytest-triggered trust branch. | Verify the perimeter; eliminate automatic test-environment trust in production modules. | [successfactors_server.py](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/successfactors_server.py:600) |
| Approval code now imports Path, rejects unmatched identity, requires a non-test signing secret, and references an operation store. | Reverify identity, confirmation, expiry, concurrent execution and restart behavior; do not repeat the earlier missing-import defect as current. | [token_manager.py](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/token_manager.py:13) |
| Operation store chooses a mounted/local path and enables SQLite WAL; its docstring claims cross-replica safety. | P1: use a supported network transactional store for separately hosted replicas. SQLite WAL requires processes on one host and does not support network filesystems. [SQLite documentation](https://sqlite.org/wal.html). | [operation_store.py](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/operation_store.py:119) |
| Audit worker now checks COMMITTED/ALREADY_COMMITTED; finance response and cards now recognize CONTRACT_MISMATCH. | Improvements present, not independently test-certified. Verify real commit evidence and full malformed/multi-currency cases before closure. | [background_logger.py](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/background_logger.py:228), [tools.py](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/tools.py:31) |

## Implementation work packages

P1 means required before the affected capability handles production data or actions. P2 means required before full control closure; it does not authorize insecure interim operation. Package priorities are proposed implementation sequencing, not workbook-assigned severity.

### WP01 — Architecture and threat model (P1)

Owners: AI Development, Velora IT, Cybersecurity, MeshX/SAP; Quilr and Cloudflare owners validate their boundaries.

Produce actual deployment and data-flow diagrams. Inventory Copilot Studio, every enabled model/provider (including Foundry only if used), connectors, Azure services, SAP, MeshX, gateways, storage, audit and monitoring. For each flow record origin, destination, processing location, protocol, token audience, executing identity, user-context mechanism, data classification, gateway policy and failure behavior. Document inbound and outbound paths separately.

Turn the threat model into abuse cases: forged executive identity, malicious email causing a send, cross-user cache retrieval, broader backend privileges, stolen session, tool-definition changes, gateway bypass, malicious pagination URL, audit outage and post-send timeout.

Deliver: architecture diagram, flow register, trust-boundary model, threat register and residual-risk owner. Acceptance: every enabled tool traces to an approved flow, policy and test; no unexplained source or sink remains. Dependencies: all later packages use this approved inventory, while obvious code defects can be corrected independently.

### WP02 — Identity, authorization and session isolation (P1)

Owners: AI Development and Velora IT identity administrators; MeshX/SAP implement downstream access rules.

Enforce authentication before REST routing and MCP dispatch. Use verified access-token claims: exact configured issuer and API audience, valid signature/algorithm, required expiry, applicable time checks, tenant and immutable user ID, allowed client and operation-specific permissions. Use a maintained JWT/OAuth library with bounded signing-key refresh. Do not accept ID tokens or Graph-audience tokens at the MCP API. Use `(tid, oid)` as the user key and distinguish delegated user from application identity. See [Microsoft claims validation](https://learn.microsoft.com/en-my/entra/identity-platform/claims-validation).

Reject conflicting body identity. Restrict every tool by purpose, user/service, tenant, object, record and field. A valid API key is not user authorization. Preserve user-limited access through supported delegation or explicit downstream entitlement mapping. Sessions require unpredictable IDs, authenticated binding, expiry and reauthorization; possession of a session is not login. MCP guidance also warns against token passthrough and session-based authentication; confirm the actual supported protocol version. [MCP security guidance](https://modelcontextprotocol.io/docs/draft/tutorials/security/security_best_practices).

Consolidate or reproducibly package duplicated identity modules. Remove test-triggered trust paths and hardcoded tenant/audience fallbacks. For any gateway assertion, bind audience, client, user, tenant, method, path, body hash, expiry and nonce; claim the nonce atomically only after signature validation.

Acceptance: absent/expired/wrong-audience/wrong-issuer tokens, issuer-prefix spoofing, missing expiry, wrong role, app-token-on-user-route, body substitution, session reuse and forged gateway assertions are denied before handlers. Run identical checks on REST aliases and MCP initialization/tool calls. Verify permitted users still work.

### WP03 — Tool permissions and human approval (P1)

Owners: AI Development, business/data owners, Velora IT.

Create a versioned tool matrix with immutable operation ID, schema, purpose, source, read/write category, roles, fields, destination constraints, approval rule and audit rule. Unknown tools and parameters fail closed. SAP/MeshX remain read-only; administrative and arbitrary-execution operations must not be discoverable or callable. Approved M365 writes use a separate policy and permission scope.

Persist an immutable preview containing the exact targets, content, attachments and operation. A trusted user confirmation must bind user/tenant, checksum, expiry and policy version. The model cannot approve its own proposal. Recheck permission immediately before execution. Do not execute changed payloads. Return generic denial and a fresh-preview path when necessary. Remove automatic-send and review-bypass behavior inconsistent with the approved scope.

Acceptance: changed recipient/body/target, expired approval, wrong user/tenant, model-generated confirmation and direct execute-without-confirmation produce zero provider calls. Show both successful approved execution and denied bypass attempts.

### WP04 — Durable approvals, replay and notification state (P1)

Owner: AI Development with platform/database owner.

Use a supported shared transactional service for operation and notification state. Prefer the existing approved enterprise database if it provides unique keys and conditional atomic transitions; explicitly prove Dataverse conditional-write behavior if chosen. Keep SQLite WAL only for supported single-host development use. Reject ephemeral/local storage fallback in production.

Track PREPARED, APPROVED, EXECUTING, SUCCEEDED, FAILED_BEFORE_SUBMISSION, OUTCOME_UNKNOWN and EXPIRED states with versions, stable IDs, lease ownership and provider evidence. The execution claim must be atomic across hosts. Validation alone must not consume approval. Store prior results for retries. Persist recommendation episode and cooldown state. A stale worker must not overwrite a newer owner. On an uncertain provider outcome, reconcile; do not simply let lease expiry cause a second send.

Acceptance: two separately hosted workers, container replacement, storage outage, stale lease, crash before submit, and crash after provider acceptance. Assert one logical action where provider guarantees permit, and safe unresolved state otherwise. Do not call a provider's acceptance response final delivery.

### WP05 — Network routing, TLS and SSRF (P1)

Owners: Cybersecurity network team, Quilr/Cloudflare owners, platform team, MeshX/SAP.

Build a per-flow route allowlist from WP01. Enforce origin access and outbound restrictions at the actual network/gateway layer, not just proxy environment variables. Verify the supported routing for Microsoft-managed connectors separately. Block unapproved direct origins, arbitrary URLs, unauthorized metadata addresses and redirect destinations. Allow only explicitly approved private endpoints where required. Check scheme, canonical host, port, DNS results and each redirect, including OData next links. Prevent credential forwarding to another origin.

Require valid certificate chains and hostnames; configure approved enterprise CAs rather than disabling TLS validation. Document gateway TLS termination and re-encryption. Test gateway outage behavior: protected operations must not fall back to an uninspected direct route.

Acceptance: permitted request succeeds through the approved path; direct-origin and egress-bypass attempts fail. Test redirect, DNS and private-address cases using authorized test endpoints. Deliver network policy exports and trace evidence, with explicit exceptions for unsupported routes rather than unsupported compliance claims.

### WP06 — Schemas, limits, encoding and safe errors (P1)

Owners: AI Development and MeshX/SAP.

Define strict request and response schemas per operation. Reject unknown fields, malformed JSON/JSON-RPC, unexpected MIME types, oversized/deep payloads, invalid ranges and unsupported fields. Compile filters from approved structured fields; do not accept raw arbitrary queries. Enforce limits before expensive parsing and downstream invocation.

Apply per-user/client/tool rate and concurrency limits, result-page/row/byte caps, maximum tool steps and overall deadlines. Coordinate retry budgets across layers; respect provider retry guidance and use jitter. Do not retry uncertain writes. Add circuit breakers and dependency isolation. Encode text for HTML/cards/exports and neutralize spreadsheet formulas only in appropriate text export fields. Return user-safe error codes and correlation references; keep stack traces restricted.

Acceptance: malformed requests never reach providers; large inputs fail within bounded resource use; repeated requests cannot bypass limits through a second replica; injected HTML/CSV content stays inert; user errors contain no internal exception details.

### WP07 — Prompt, retrieval, grounding and output protections (P1)

Owners: AI Development, data owners and Quilr.

Maintain one coherent instruction set: external emails, documents, tool descriptions and responses are data, not authority; use only approved tools; never infer permission from retrieved content; show truthful sources and limitations. Back these instructions with WP02/03 controls. Validate tool metadata and source provenance; quarantine unapproved changes and ingestion sources.

Filter retrieval by current source permissions before model context construction. Label source ID, version, retrieval time, classification and authorized evidence reference. Distinguish factual values from interpretation. Mark incomplete or conflicting data; preserve SOURCE_UNAVAILABLE for unimplemented integrations. Verify finance calculations reject malformed/missing required and nonfinite amounts without converting errors into zero, including every currency partition and text/card/structured output.

Apply minimization and output policy to all display and export surfaces, including streaming. If a control requires whole-response inspection, do not release restricted partial tokens first. Scanner decisions supplement, never replace, authorization. Acceptance: malicious emails, retrieved documents and tool metadata cannot trigger prohibited operations; unauthorized source content is absent from model context; factual claims trace to permitted real sources; missing providers produce no fabricated facts or destination links.

### WP08 — Data isolation, classification and retention (P1)

Owners: AI Development, data/privacy owners and platform team.

Inventory prompts, raw responses, source extracts, files, embeddings, caches, memory, approvals, audit, gateway/SOC copies and backups. Assign owner, purpose, classification, authorized identities, region, retention, deletion mechanism and legal-hold handling. Do not invent retention durations or infer residency solely from Azure region.

Partition storage and cache keys by tenant/user and relevant source, permission, session, agent and policy context. Recheck access after permissions change. Avoid caching personalized results globally. Limit fields, result volume and metadata before data reaches models or gateways. Use approved encryption and resource access controls. Test deletion propagation to derived stores and backup expiry; revoked access must not survive in old cache entries.

Acceptance: two users/tenants with overlapping request parameters cannot retrieve each other's data; permission revocation is enforced; retention jobs delete an approved synthetic record from every applicable copy and report exceptions.

### WP09 — Audit, correlation and SOC monitoring (P1)

Owners: AI Development, MeshX/SAP, CyberNxt SOC and Cybersecurity.

Use stable event IDs and a real durable commit contract. COMMITTED requires actual destination evidence; ALREADY_COMMITTED requires verification of the same event. Write approved-action intent durably before side effects, then retain provider outcome for reconciliation. Align the actual Dataverse schema with required event fields. Retain pending spool records until confirmed commitment; treat disk failure as failed acceptance.

Record authenticated user and service, internal correlation, model/agent/tool/policy versions, authorized source references, safe parameter metadata, decision, approval reference, volume, latency, outcome and error category. Exclude secrets and unnecessary content. Propagate trusted trace context over authenticated hops; preserve client-provided IDs separately.

Agree SOC event schema and alert runbooks for denied access, abnormal extraction, suspected injection, tool/config drift, gateway bypass, audit backlog and repeated failures. Acceptance: reconstruct a synthetic action end to end; BUFFERED never releases its spool; replay does not duplicate an event; confirm SOC receives and can act on each critical test alert.

### WP10 — Environment, identities, secrets and runtime hardening (P1)

Owners: AI Development, Velora IT, platform and MeshX/SAP teams.

Separate development/test/production identities, data stores, secrets, connections, endpoints and deployment privileges. Production must not accept test tokens, anonymous-mode switches, test signing defaults or sample data fallback. Use dedicated workload identities with least-privilege resource assignments. Prefer managed identity where the specific service supports it; independently verify Dataverse application-user binding and connector identity behavior.

Keep required credentials in the approved vault; retrieve securely, rotate and revoke with evidence. Scan current sources, history, images and packages; any discovered real credential requires owner-led rotation rather than only deletion from code. Use non-root supported images, minimal capabilities and writable directories, read-only root filesystems where feasible, restricted diagnostics and healthy shutdown.

Acceptance: production validation rejects unsafe config; a development principal cannot access production; identity permissions are limited to required operations; rotation works without fallback to embedded credentials; container configuration evidence matches the release image.

### WP11 — Release integrity and tool-change control (P1)

Owners: AI Development, platform team, MeshX/SAP.

Version prompts, tools/schemas, policies, connection mappings, model deployment choices and infrastructure alongside source. Protect branches, require independent review, restrict CI identities and production approval rights, scan dependencies/secrets/images, generate SBOMs and retain build provenance. Pin deployable artifact digests and lock dependencies, with an update process rather than permanent frozen versions.

Compare runtime tool discovery and configuration to an approved manifest. New or changed tools/scopes/mappings require approval and revalidation before use. Hashes demonstrate change, not semantic safety; tests must cover behavior too. Preserve compatibility with the actual MCP version.

Acceptance: an unauthorized schema or downstream mapping change is detected and blocked/quarantined; a critical release-gate failure prevents promotion; the deployed digest and configuration version can be traced to reviewed artifacts.

### WP12 — Kill switches, rollback and independent acceptance (P1)

Owners: Cybersecurity, Velora IT, AI Development, MeshX/SAP and the assessment vendor.

Provide global, per-tool and per-client disablement enforced immediately before business execution, including queued jobs and secondary routes. Define measurable disablement and recovery targets with owners; do not assume token revocation instantly stops every cached access token. Revoke associated privileges/credentials as appropriate, retain investigation evidence and reconcile in-flight actions. Rollback must restore a known-good compatible version without restoring excessive permissions or deleting unresolved operation state.

Run security tests in a dedicated environment using synthetic data and mocked/approved sinks. Vendor testing complements developer regression tests; onboarding must not delay basic negative tests. Include authentication/authorization, prompt injection, cross-user leakage, session replay, tool drift, SSRF, gateway bypass, fuzzing, throttling and failure recovery. Deliver reproducible cases and retest evidence, not just a vulnerability count.

Acceptance: disable one tool/client and prove it cannot execute through REST, MCP or workers while unrelated approved services remain usable; rehearse rollback and recovery; close every P1 with deployed evidence before production approval.

## Release sequence and tracker closure

1. Freeze a reviewable baseline and agree actual scope, route topology, identity contract and data classifications (WP01).
2. Close identity, tool-dispatch, approval, storage and routing blockers before production use (WP02–05).
3. Complete validation, isolation, grounding, audit and runtime defenses (WP06–10).
4. Enforce immutable promotion and operational recovery; perform independent acceptance (WP11–12).

Work can be developed in parallel by accountable teams, but dependent acceptance cannot be inferred from another package's unit tests. Do not assign arbitrary dates until platform/vendor dependencies and effort are agreed.

Add these fields to a copy of the tracker: applicability; accountable owner; implementation owner; work package; priority; current evidence; remaining gap; dependency; target date; test IDs; tested revision/environment; evidence link; reviewer; residual risk/exception owner and expiry. Keep implementation state separate from validation state. Suggested progression: Not assessed → Gap confirmed → Implemented → Tested locally → Verified in target environment → Accepted. Mark N/A only with approved rationale.

Every closure packet must include the exact control ID, configuration/code evidence, a positive test, a negative test, failure/recovery testing where relevant, date and deployed revision, and independent reviewer acceptance. A screenshot of a setting, a prompt rule, or successful health check is insufficient proof on its own.

## Copilot Studio configuration evidence to request

Export the agent's enabled channels, authentication, users/groups, tools and connection references, knowledge sources, autonomous triggers, DLP policies, publishing permissions and solution version. Check no alternate direct connector bypasses the intended policy. Configure supported data policies to restrict unauthenticated chat and unapproved connectors/knowledge sources; tenant capability and applicability must be verified. [Microsoft data-policy guidance](https://learn.microsoft.com/en-ca/microsoft-copilot-studio/admin-data-loss-prevention).

Separate platform controls from application controls: Copilot login does not prove backend authorization; DLP is not a substitute for network enforcement; agent instructions do not prove human confirmation; a service identity does not preserve user rights automatically.

## Handoff instruction for an implementation LLM

Implement the control matrix against a newly frozen source revision. Re-read current code and preserve unrelated edits. Work package by work package, deliver code/configuration/migrations and meaningful tests. Do not weaken authentication in test mode within production modules. Do not use SQLite WAL as a multi-host transaction store. Do not re-enable SAP/MeshX writes or P&L. Do not claim a gateway route, managed-identity capability, durable commit, or final delivery without supporting evidence. Prepare external configuration changes for the appropriate owner; no production deployment or live messages are authorized by this review. Return a control-to-change-to-test evidence matrix with unverified dependencies explicitly open.
