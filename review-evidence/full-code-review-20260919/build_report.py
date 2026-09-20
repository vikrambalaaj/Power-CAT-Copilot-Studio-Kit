from pathlib import Path
import json,subprocess,collections,hashlib,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).parent
F=[]
def add(id,priority,title,locations,evidence,problem,impact,steps,tests,depends=(),confidence='Confirmed in offline reproduction'):
 F.append(dict(id=id,priority=priority,title=title,locations=[{'path':p,'line':n} for p,n in locations],evidence=evidence,confidence=confidence,problem=problem,impact_and_limits=impact,implementation_steps=steps,acceptance_tests=tests,depends_on=list(depends)))
add('F01','P1','Bind all tenant, role, scope, and actor fields to verified identity',
 [('mcp-apps/ask-facilitator/facilitator_mcp/server.py',169),('mcp-apps/ask-facilitator/facilitator_mcp/tools.py',557),('mcp-apps/ask-productivity/productivity_mcp/server.py',584)],
 ['python-probes.json: facilitator_rest_identity_forwarding / facilitator_export_default_role','productivity-probes.json'],
 'Facilitator authenticates the caller, then forwards arbitrary request arguments to handlers, including tenant_id, caller_roles, caller_entity_scopes, actor_object_id and db_path. Its export wrapper defaults a caller with no supplied role to AUDITOR. Productivity similarly accepts tenantId and callerRole for recommendation and automation operations instead of using the verified identity. The offline requests used a valid synthetic ordinary-user JWT; the handlers received another tenant and elevated roles. The export wrapper supplied AUDITOR on its own.',
 'An authenticated caller can cross the intended authorization boundary, select other business partitions, or manufacture audit attribution. Provider/storage calls were intercepted, so this proves the unsafe dispatch boundary rather than an actual production disclosure. An upstream gateway alone does not repair request-body trust unless it independently enforces every argument.',
 ['Create one immutable server-side ExecutionContext containing verified tenant, subject, principal type, allowed roles, resource scopes and correlation ID. Pass it explicitly through REST, MCP and internal dispatch.',
  'Remove security-sensitive arguments and filesystem paths from public tool schemas. Reject a supplied tenant/actor/scope that conflicts with context; do not silently accept it. Resolve storage and signing configuration only from server configuration.',
  'Replace callerRole="WORKLOAD_AUTHORIZED" and caller_roles or ["AUDITOR"] with authorization decisions from context. Separate workload-only KPI ingestion from executive read operations; require the configured application permission for ingestion.',
  'Derive audit actor and tenant from context. Apply resource-level checks again in repository/service methods so alternate transports cannot bypass them. Define explicit mapping if a business tenant identifier differs from the Entra tenant; do not use an arbitrary body value or hardcoded default.',
  'Apply the same boundary to subscription prepare/confirm/revoke, meeting actions, feedback summaries and historical decision reads. Update copied Productivity modules inside Facilitator until shared packaging is consolidated.'],
 ['Ordinary user supplying another tenant, AUDITOR, administrative scopes, actor IDs or db_path receives 403/422 before any provider/storage invocation.',
  'An ordinary user with no role cannot export; a genuinely authorized auditor can export only permitted decisions.',
  'A valid user JWT cannot execute workload-only KPI ingestion. A valid workload identity with the required application permission can.',
  'REST and native MCP produce equivalent allow/deny outcomes; recorded audit identities match verified claims.'])
add('F02','P1','Remove gateway signature downgrade and authenticate the user email',
 [('mcp-apps/ask-productivity/shared_mcp/identity.py',355),('mcp-apps/ask-productivity/shared_mcp/identity.py',365),('mcp-apps/ask-productivity/shared_mcp/identity.py',380)],
 ['gateway-probes.json'],
 'x-gateway-user-email is used as the verified display email but is absent from both signed canonical strings. If verification of the method/path/body-bound signature fails, the implementation still accepts the legacy identity-only signature, even when the caller provided an actual request method, path and body. A valid synthetic legacy assertion continued to verify after the email was changed from Alice to Bob and a different operation/body was supplied. Nonce consumption is also held in a process-local dictionary.',
 'A party able to alter or replay an otherwise valid gateway assertion may change mailbox attribution or reuse it for a different request. This does not prove that an attacker can generate a signature without a key or intercept production traffic. Multiple replicas/restarts additionally defeat a process-local nonce barrier.',
 ['Define a versioned canonical payload including tenant, subject, email (or derive email exclusively from the signed principal), audience, roles, HTTP method, normalized path, body SHA-256, timestamp and nonce.',
  'Verify against the actual request bytes and routing context, not caller-declared method/path/hash headers. Remove legacy fallback on endpoints requiring request binding; migrate gateway and backend together with an explicit short compatibility window if existing clients require it.',
  'Require a configured tenant/audience allowlist for gateway assertions, and validate finite timestamps and bounded freshness.',
  'Consume the nonce only after successful verification using a shared atomic store with expiry. Bind its namespace to issuer/tenant; fail closed on store failure.',
  'Update all four shared_mcp/identity.py copies and gateway generation code/contracts together.'],
 ['Changing email, roles, tenant, subject, method, path or body without re-signing fails.',
  'A legacy signature fails on a request-bound endpoint; a valid new-format assertion succeeds.',
  'Two processes racing the same signed nonce yield one acceptance; restart does not make a consumed assertion valid.',
  'An invalid signature does not reserve a nonce and cannot block a later valid request.'])
add('F03','P1','Protect the native Facilitator MCP transport',
 [('mcp-apps/ask-facilitator/facilitator_mcp/server.py',69),('mcp-apps/ask-facilitator/facilitator_mcp/server.py',189)],
 ['python-probes.json: facilitator_unauthenticated_mcp_initialize / facilitator_unauthenticated_mcp_tool'],
 'Authentication lives in individual REST handlers. create_app mounts the native MCP transport without an authentication layer, and registered wrappers check only the kill switch and, for one tool, a process environment role. With ALLOW_ANONYMOUS=false, unauthenticated MCP initialize returned 200 and a tools/call reached tool dispatch. The tested tool then failed because of the separate schema defect in F12.',
 'REST rejection does not establish native MCP protection. Sensitive native tool execution was not demonstrated because the current wrappers also have broken schemas. Fixing those schemas without first fixing authentication would expose the missing boundary more directly.',
 ['Put authentication in ASGI/MCP middleware covering initialize, tools/list and tools/call, with health as an explicit public exception.',
  'Store verified context per request/session and verify session ownership on subsequent requests. Do not let one authenticated session become a bearer substitute for a different user.',
  'Replace MCP_CALLER_ROLE authorization with the request context and resource policies from F01. Apply tenant/client-scoped kill-switch checks before business work.',
  'Return appropriate transport-level 401/403 responses and advertise the chosen authentication mechanism consistently in connectors.',
  'Complete F12 only together with these transport protections.'],
 ['No-credential initialize/list/call is rejected when authentication is required.',
  'A valid principal can initialize and invoke an allowed tool; an unauthorized principal cannot invoke admin tools.',
  'Reusing another principal’s MCP session identifier fails.',
  'A global or tenant-scoped kill switch blocks both REST and MCP.'],depends=('F01','F02'),confidence='Confirmed unauthenticated initialization/dispatch; sensitive native execution not demonstrated')
add('F04','P1','Bind SuccessFactors memory and consent to the caller',
 [('mcp-apps/ask-successfactors/successfactors_mcp/successfactors_server.py',567),('mcp-apps/ask-successfactors/successfactors_mcp/successfactors_server.py',589),('mcp-apps/ask-successfactors/successfactors_mcp/consent_gate.py',43)],
 ['sf-probes.json'],
 'Memory and consent endpoints accept user_object_id/user_email from query/body after only shared API-key authentication. The consent tool decorator also uses caller-supplied user fields. The probe supplied a different user and reached the memory/consent providers. Additionally, accepted="false" becomes True because bool(nonempty_string) is true.',
 'Possession of an integration API key is not proof of the end user’s identity. It can be used to select another memory partition or record consent for another person. The provider was mocked; no real consent or user history was changed.',
 ['Require verified delegated identity or a signed gateway assertion on user-specific endpoints. Treat API keys as service authentication only, not user identity.',
  'Derive memory partition and consent subject from verified claims; reject conflicting parameters and remove unsigned x-user-email/user-object-id fallback from MCP argument injection.',
  'Use a strict boolean request schema for accepted. Reject strings, numbers, missing mandatory fields and stale/unknown notice versions.',
  'Apply consent checks consistently to user-sensitive REST and native tools; preserve explicitly authorized administrative access as a separate audited operation.',
  'Record actor, subject, tenant, notice version, timestamp and request correlation separately so an administrator cannot appear to be the consenting user.'],
 ['An API key alone cannot recall another person’s memory or record consent.',
  'Changing user_object_id/user_email under a valid user token yields 403 and no provider call.',
  'Boolean false records rejection; string "false" is rejected as invalid input.',
  'Valid consent succeeds for the authenticated subject, and memory access respects the effective consent policy.'],depends=('F01','F02'))
add('F05','P1','Authorize the S/4HANA query scope itself',
 [('mcp-apps/ask-s4hana/s4hana_mcp/server.py',121),('mcp-apps/ask-s4hana/s4hana_mcp/tools.py',295)],
 ['s4-probes.json'],
 'The middleware checks an optional x-organization-scope header against a hardcoded set but does not bind it to the query’s company_code. A request with header scope 1000 and company_code 9999 reached client.query with CompanyCode=9999. The synthetic provider returned an error after the boundary, explaining the final HTTP 400; authorization had already failed to stop the provider invocation.',
 'A shared backend SAP identity may have broader permissions than an individual executive. The current header check does not enforce executive-to-company entitlement. Live SAP permissions might limit the impact, but were not verified.',
 ['Resolve allowed company codes, business entities and finance dimensions from verified context and a server-controlled entitlement mapping.',
  'Normalize aliases before authorization, then validate every requested company/entity/funds-management scope against that mapping before query, metadata retrieval or cache lookup.',
  'Remove reliance on an unsigned optional scope header. Require explicit authorized scope or a safe server-derived default.',
  'Include effective tenant/principal authorization scope in cache keys whenever the provider credential can see broader data.',
  'Apply the same rule across aging, budget, P&L, master-data, aliases and native MCP routes.'],
 ['Allowed header plus forbidden company code produces 403 and zero query calls.',
  'Omitting the scope header does not bypass resource authorization.',
  'All aliases and transports enforce the same company boundary.',
  'An authorized request succeeds without changing the financial calculations.'],depends=('F01','F17'))
add('F06','P1','Eliminate known production signing keys',
 [('mcp-apps/dynamic-adaptive-card-service/Dockerfile',16),('mcp-apps/dynamic-adaptive-card-service/src/security/idempotency-signer.ts',48),('mcp-apps/ask-facilitator/facilitator_mcp/decision_audit.py',113)],
 ['node-probes.json: production_accepts_missing_signing_secret','python-probes.json: audit_production_uses_default_key'],
 'The Cards image embeds a literal signing secret. Its constructor also falls back to a known development secret in production unless an extra REQUIRE_EXPLICIT_SIGNING_SECRET flag is enabled. Decision audit signing always falls back to a source-code constant when its environment key is missing. Both missing-secret production paths were reproduced. Secret values are intentionally omitted here.',
 'Any installation relying on these known defaults cannot use the signature as evidence of trusted issuance. The deployment script can override the Cards image value with a vault secret, so this is not evidence that the live deployment uses the default. The code and image remain unsafe defaults.',
 ['Remove the Dockerfile secret and all automatic known-key production fallbacks. Use one environment-mode contract; production must fail startup/readiness without valid key configuration.',
  'Provision dedicated keys for card tickets, gateway assertions and audit signing. Add key IDs/versions and verification rules for controlled rotation; do not allow clients to choose verification keys for a trusted-verification operation.',
  'For audit evidence requiring independent verification, use an asymmetric signing service/key custody boundary and publish the corresponding trusted public-key metadata. Merely printing a KMS-like key ID does not establish managed custody.',
  'Determine whether deployed artifacts or issued tokens used defaults. If so, coordinate key rotation and invalidation with the owner; preserve old audit artifacts and explicitly mark their trust status rather than silently re-signing history.',
  'Keep test keys explicit and confined to test setup. Regenerate images and pin their digests after the fix.'],
 ['Production startup fails with missing, empty or known development keys.',
  'A properly provisioned production key signs/verifies successfully; a default-key token fails.',
  'Wrong key ID/version and client-supplied signing keys cannot make a forged audit artifact trusted.',
  'Image configuration and layers do not contain embedded signing secrets.'])
add('F07','P1','Make card validation enforce identity, approved content and finite expiry',
 [('mcp-apps/dynamic-adaptive-card-service/src/index.ts',35),('mcp-apps/dynamic-adaptive-card-service/src/index.ts',78),('mcp-apps/dynamic-adaptive-card-service/src/security/idempotency-signer.ts',95)],
 ['node-probes.json: anonymous_render / unbound_submission'],
 'The render and validation endpoints have no authentication hook. Tickets sign only session/template/action/time fields, and validation echoes arbitrary submittedData without comparing it with the issued operation. An anonymous render request using ttlSeconds="not-a-number" produced a signed string expiresAt; its numerical expiry comparison does not reject it. Validation then returned valid=true for a different session and changed amount.',
 'This endpoint currently proves only consumption of a token, not authorization of the submitted business action. No provider action is executed by this service in the probe; the risk becomes a business-action bypass if a downstream caller treats valid=true as approval. Invalid expiry and public issuance are directly confirmed regardless.',
 ['Authenticate issuance and submission, with explicit authorization for the intended user/session/tenant. Add body schemas with strict types, bounded sizes and a finite integer TTL within the approved maximum.',
  'Issue tickets for a server-stored operation ID/version and canonical approved-payload hash, plus tenant, subject, intended action and audience. Never trust a caller-selected session alone.',
  'Separate editable form fields from fixed approved action fields; validate permitted edits against a server-side schema and reject changed recipients, amounts or action identifiers unless a new preview is approved.',
  'Validate all signed fields before consumption, including finite issuedAt/expiresAt, expiry ordering, algorithm/version and operation state. Consume atomically with the operation transition using F08.',
  'Make the downstream execution boundary independently enforce approval and idempotency. Add retention/expiry cleanup for consumed records and bounded request rates to prevent unbounded disk growth.'],
 ['Anonymous issuance/submission is denied; valid authorized issuance and submission succeed.',
  'String, negative, fractional, infinite-equivalent or excessive TTL is rejected before signing.',
  'Changed identity/session/action or fixed business fields fails validation and cannot dispatch.',
  'Expired, malformed, replayed and concurrently submitted tickets are rejected appropriately; storage failure fails closed.'],depends=('F06','F08'))
add('F08','P1','Use genuinely shared durable state across API, workers and replicas',
 [('mcp-apps/deploy-azure-containerapps.sh',329),('mcp-apps/deploy-azure-containerapps.sh',359),('mcp-apps/ask-productivity/productivity_mcp/subscription_service.py',26),('mcp-apps/ask-productivity/productivity_mcp/business_repository.py',323),('mcp-apps/ask-productivity/deploy/containerapp.bicep',198)],
 ['node-probes.json: two_replicas_local_storage','source-manifest.json'],
 'The shell deployment registers environment storage, then sets mount-looking environment paths without adding app/job volume mounts. Cards ignores DATABASE_URL and uses files; two isolated process storage directories both consumed the same signed ticket. Subscriptions independently default to /tmp/velora_subscriptions.db. The Bicep worker sets VELORA_SUBSCRIPTION_DB on its mount, but the API container does not set the same variable. Business records remain SQLite regardless of DATABASE_URL; their path resolution also ignores FACILITATOR_STORAGE_DIR/AZURE_STORAGE_MOUNT_PATH.',
 'API and worker can see different subscriptions, replicas can accept duplicate tickets, and container replacement can lose state. These are source/deployment-contract defects; live volume attachment was not inspected. Simply pointing SQLite WAL at a network share is not a safe general repair: SQLite documents that WAL requires processes on the same host.',
 ['Choose PostgreSQL as the shared authoritative store already supported by this deployment. Implement adapters for subscriptions/run history, business records/decisions and card consumption, not only operations/outbox.',
  'Use tenant-scoped unique constraints and atomic transitions. Store consumed operation/ticket IDs, expiry and approval hash with the corresponding operation state; give all API replicas and jobs the same database/schema configuration.',
  'Reconcile Bicep and shell deployment from one maintained definition. If file storage remains for artifacts, define actual volumes and volumeMounts on every relevant app/job and verify mounted paths at startup.',
  'Create a migration that inventories every existing SQLite/file location, backs up data, exports rows, preserves IDs/tenants/approval state, imports transactionally and compares row counts/checksums. Pause scheduling during cutover to avoid two active stores.',
  'Remove fallback to private local storage in production. Keep SQLite only for explicit local/test operation. Do not store WAL databases on Azure Files as a multi-host substitute for PostgreSQL.',
  'Add a deployment acceptance check proving an API-created subscription is visible to the worker and a ticket claimed on one replica is rejected on another and after restart.'],
 ['Two independent processes sharing the database yield one successful ticket/operation claim.',
  'API creates/confirms a subscription; a separate worker reads that exact record and version.',
  'Container replacement preserves subscriptions, decisions, nonce/approval barriers and pending work.',
  'A database outage makes business mutations fail closed; no silent /tmp fallback.',
  'Migration preserves record counts and immutable evidence hashes; rollback cannot dispatch the same pending occurrence twice.'])
add('F09','P1','Create provider clients for each subscription owner',
 [('mcp-apps/ask-productivity/productivity_mcp/worker.py',237),('mcp-apps/ask-productivity/productivity_mcp/worker.py',120),('mcp-apps/ask-productivity/productivity_mcp/worker.py',149)],
 ['python-probes.json: worker_cross_mailbox'],
 'run_worker_pass constructs one Microsoft365Client from its user_email and passes it to every subscription. Passing sub.mailbox to the briefing formatter does not change the client’s mailbox. In the synthetic two-user test, Alice’s data was sent to Alice and then to Bob.',
 'A multi-executive worker can disclose the wrong mailbox’s content and send under the wrong mailbox context. The probe used a fake provider/briefing formatter; no email was sent. The real provider client builds mailbox URLs from its own user_email, so the mismatch is present in the executable path.',
 ['Introduce a provider-client factory taking the verified subscription tenant and authorized owner/mailbox. Construct or retrieve an appropriately scoped client separately for each subscription.',
  'Check current standing authorization, owner/mailbox binding, subscription version, recipients and allowed data scope before collecting content and again before dispatch.',
  'Use that same scoped context for calendar selection, briefing generation, attachments, send and receipt/audit recording. Cache only by tenant/subject/mailbox/permission context.',
  'For outbox records, select the provider context from each authorized delivery record instead of one process-wide default mailbox.',
  'Remove hardcoded executive mailbox defaults from unattended execution and fail clearly when the required mailbox mapping is absent.'],
 ['Two executives with disjoint mail/calendar data receive only their own authorized information.',
  'Revoked or mismatched mailbox permissions prevent reading and sending.',
  'Audit sender, source mailbox, owner and recipients reflect the actual scoped provider client.',
  'Outbox delivery for different tenants never shares a default executive context.'],depends=('F01','F08'))
add('F10','P1','Reconcile uncertain subscription sends instead of blindly reclaiming them',
 [('mcp-apps/ask-productivity/productivity_mcp/worker.py',149),('mcp-apps/ask-productivity/productivity_mcp/worker.py',167),('mcp-apps/ask-productivity/productivity_mcp/subscription_service.py',328),('mcp-apps/ask-productivity/productivity_mcp/subscription_service.py',367)],
 ['python-probes.json: subscription_after_send_before_receipt_crash'],
 'The worker sends to the provider before writing the receipt or SUCCESS state. A crash after provider acceptance leaves an ordinary CLAIMED row without a receipt. After ten minutes that row is reclaimed and can send again. The probe reproduced that persisted state and successful reclaim. Completion updates are keyed only by run_key, so an old worker can also overwrite a newer claim’s outcome.',
 'Atomic initial claims fix simultaneous starts but not the crash window between an external effect and local commit. A timeout cannot prove that no email was accepted. The probe simulated the persisted crash state rather than sending real mail.',
 ['Route subscriptions through the existing durable outbox abstraction, extending it where needed, instead of calling execute_send_email directly from the scheduler.',
  'Persist a stable operation ID, content hash, recipients, provider correlation identifier and SUBMITTING state before the external call. Record confirmed receipts afterward.',
  'Treat expired SUBMITTING states as UNKNOWN/RECONCILIATION_REQUIRED, not automatically resendable. Reconcile with provider evidence or require an operator decision when the provider cannot safely prove non-submission.',
  'Use lease tokens/execution IDs and conditional updates for renew/complete/fail. A stale worker must not complete a newer worker’s lease.',
  'Recheck revocation/expiry immediately before send, classify permanent vs retryable failures, and bound retries. Preserve an append-only event trail for every attempt.'],
 ['Crash before submission can retry safely; crash after acceptance does not blindly resend.',
  'Provider timeout with unknown outcome enters reconciliation, not immediate retry.',
  'Stale completion cannot overwrite a new lease.',
  'A revoked subscription cannot send after a long briefing-generation delay.',
  'Duplicate/late receipts attach to one occurrence and do not create a second delivery.'],depends=('F08','F09'))
add('F11','P1','Stop labeling caller-provided evaluation inputs as verified evidence',
 [('mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py',169),('mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py',293)],
 ['python-probes.json: vendor_unverified_input_result'],
 'Vendor evaluation manufactures DOC-TECH-<vendor> and DOC-COMM-<vendor> references when none are provided, then describes the inputs as certified/formal evidence and emits HIGH/AUTHORITATIVE/VERIFIED confidence. A candidate containing only caller-provided numbers produced a successful recommendation and those evidence attributes without fetching a source document.',
 'Deterministic arithmetic can still be based on unverified or fabricated facts. Signing the resulting manifest proves neither the existence nor correctness of the cited documents. The reproduction demonstrates incorrect evidence attribution, not a claim about any actual supplier.',
 ['Require source references that resolve through an authorized evidence repository before a proposal can be classified as verified. Check document existence, tenant/scope, version/hash, provenance and relevant period.',
  'Represent raw user input as USER_PROVIDED/UNVERIFIED and distinguish it from extracted, reviewed or provider-verified facts. Do not invent a source record ID or certify a document that was not retrieved.',
  'Compute confidence using evidence availability, freshness, completeness and comparability. If a policy requires verified evidence, return an explicit blocked/insufficient-evidence result instead of an authoritative recommendation.',
  'Persist the exact evidence snapshots and input hashes used for scoring. Ensure every material claim resolves to a real, authorized source and that source limitations are preserved in exports.',
  'Review already stored decisions for generated references. Mark affected records’ verification status through a versioned correction; preserve the historical record and signature.'],
 ['Bare numbers with no source return unverified/blocked results and no fabricated source IDs.',
  'Missing, inaccessible, stale or hash-mismatched source documents cannot yield HIGH verified confidence.',
  'A complete authorized evidence fixture produces the expected score and traceable claim-level citations.',
  'Correcting evidence creates a new decision version and does not overwrite the prior audit record.'],depends=('F01','F06','F08'))
add('F12','P1','Repair native tool signatures and async ingestion',
 [('mcp-apps/ask-facilitator/facilitator_mcp/server.py',69),('mcp-apps/ask-facilitator/facilitator_mcp/server.py',178),('mcp-apps/ask-facilitator/facilitator_mcp/tools.py',451),('mcp-apps/ask-facilitator/facilitator_mcp/tools.py',465)],
 ['python-probes.json: facilitator_native_tool_schema / facilitator_sync_async_ingestion','undefined-names.json'],
 'The wrapper replaces typed handler signatures with *args/**kwargs without preserving __wrapped__/__signature__. FastMCP advertises required string args and kwargs even for the no-argument guide. Calling it forwards those artificial arguments and fails. Separately, the synchronous ingestion wrapper invokes asyncio.run while the REST handler is already running an event loop, producing HTTP 500. Decimal is missing from tools.py imports; Tuple is missing in both copied tools_m365_writes.py modules, which can break runtime type-hint inspection.',
 'Passing unit tests of direct functions does not prove native tool usability. The current REST ingestion failure is reproduced. Fixing the signature may expose the missing type imports or the native auth gap, so these repairs must be coordinated.',
 ['Preserve typed handler signatures with functools.wraps or explicit typed adapter functions. Resolve annotations in the original module namespace, and import every referenced annotation type.',
  'Make ingest_vendor_performance_record async and await ingest_institutional_record directly. Avoid asyncio.run anywhere on an already-running ASGI/MCP event loop.',
  'For genuinely synchronous blocking handlers, use a bounded thread pool or an async implementation rather than executing them directly on the event loop.',
  'Generate public tool schemas only from the permitted business arguments after F01 strips internal context/configuration parameters.',
  'Add transport-level contract tests using the exact runtime dependency version selected by the deployable package.'],
 ['Guide has an empty argument schema; ingestion exposes its actual typed business fields, not args/kwargs.',
  'Authorized native list/call and REST ingestion both work with realistic inputs.',
  'typing.get_type_hints succeeds on exported handlers and undefined-name checks pass.',
  'A slow synchronous handler does not block unrelated health/tool requests.'],depends=('F01','F03','F16'))
add('F13','P1','Implement the MCP protocol advertised by the SAC plugin',
 [('mcp-apps/ask-sac/sac_mcp/server.py',64),('mcp-apps/ask-successfactors/agent/appPackage/sac-plugin.json',133)],
 ['sac-probes.json'],
 'The plugin declares RemoteMCPServer and points to /mcp, but the SAC server treats body.method as a business tool name. A properly shaped initialize request with the configured API key returned 404: Tool initialize not found. The endpoint is a custom REST dispatcher rather than the advertised native MCP interface.',
 'A native MCP client cannot complete discovery and establish normal tool invocation against this endpoint. REST-specific SAC tests pass because they exercise a different contract. Live Copilot connection behavior was not tested.',
 ['Choose one supported integration contract: implement a real FastMCP Streamable HTTP server and register the SAC tools, or change the packaged integration to an OpenAPI REST runtime that actually matches these endpoints.',
  'For MCP, support initialize, initialized notification, tools/list and tools/call, correct content negotiation, protocol versions, session handling and errors through the SDK.',
  'Apply F17’s authentication contract to the chosen transport. Keep health separate and public only if intended.',
  'Generate the plugin/connector artifacts from the same contract and rebuild packaged agent ZIPs.',
  'Perform a real client handshake using the release image before declaring integration complete.'],
 ['Authenticated initialize succeeds with protocol/server capabilities; unauthenticated initialize is rejected.',
  'tools/list advertises all three SAC tools with accurate schemas.',
  'tools/call returns a protocol-compliant result; invalid tools/arguments return protocol errors.',
  'The packaged plugin connects in the target client using the configured auth method.'],depends=('F16','F17'))
add('F14','P2','Validate evaluation-model output before computing a passing score',
 [('agent-review-pipeline/src/evaluation/predictV2Client.ts',132),('agent-review-pipeline/src/evaluation/predictV2Client.ts',160),('agent-review-pipeline/src/evaluation/scoreCalculator.ts',52)],
 ['node-probes.json: pipeline_malformed_success'],
 'Stage B and C validate only that arrays exist. Individual records and criterion IDs are not validated. A mocked Stage B with a nameless passing pattern and Stage C with an unknown High-severity issue produced overallScore=100, passed=true and no errors. Unknown issue IDs match none of the configured criteria, so they subtract no points.',
 'The earlier mandatory-stage failure defect is repaired, but malformed or semantically invalid successful model output can still pass. LLM responses are untrusted data and require a complete contract before scoring.',
 ['Define strict runtime schemas for both model responses, including required pattern names/IDs, boolean Status, known criterion IDs/severities and bounded strings/arrays.',
  'Validate evaluation coverage against a versioned required-criteria set. Reject unknown IDs, duplicates, omitted required criteria and empty evaluations unless an explicit documented not-applicable policy applies.',
  'Distinguish transport completion, schema validation and mandatory-criteria coverage. Only all three allow a mandatory stage to be marked completed.',
  'Retain deterministic scoring as the authority; do not trust a model-provided compliancePercentage in place of validated criteria. Treat invalid responses as failed evaluation with a clear error, not an empty issue list.',
  'Add adversarial successful-response fixtures alongside the existing outage tests.'],
 ['The nameless-pattern/unknown-issue reproduction fails the gate.',
  'Unknown IDs, string booleans, missing fields, duplicates and incomplete coverage return explicit validation failures.',
  'Valid complete all-pass and mixed-result fixtures retain their expected deterministic scores.',
  'A remote outage with passing local patterns still fails, preserving the earlier fix.'])
add('F15','P2','Make the advertised CI quality gate actually fail the workflow',
 [('agent-review-pipeline/src/evaluate.ts',95),('agent-review-pipeline/action.yml',121),('agent-review-pipeline/.github/workflows/agent-review.yml',28)],
 ['pipeline-empty-gate.json'],
 'evaluate.ts writes passed=false for an empty evaluation then exits 0. Normal failed evaluations also reach the end without a failing exit status. The composite action exposes passed as an output but has no final enforcement step, and the supplied example workflow never checks it. An empty evaluation was reproduced with processExitCode=0 and passed=false.',
 'Consumers that correctly inspect passed can enforce their own policy. The supplied action/workflow, however, can show success despite a failed quality result, so branch protection based only on job success will not enforce the described gate.',
 ['Define explicit report-only vs enforce-gate behavior, with enforcement enabled for the documented deployment gate.',
  'Write/upload the report and send the configured result callback before the final enforcement step so failures remain reviewable.',
  'Fail the job when the evaluation is missing, invalid, has no evaluatable agents, or reports any mandatory failure. Preserve passed=false JSON for downstream consumers.',
  'Pass workflow inputs such as threshold through environment variables/argv rather than interpolating them directly into shell source; keep the current numeric range validation.',
  'Place the runnable workflow/action at the intended repository locations or document the external-action layout clearly; the current nested example is not itself a root GitHub workflow.'],
 ['An empty/failed evaluation uploads evidence and leaves a failing gate check.',
  'A valid passing evaluation succeeds.',
  'Report-only mode, if retained, is explicit and cannot accidentally satisfy a deployment gate.',
  'Quotes/newlines/shell syntax in threshold input are rejected as data and cannot execute shell code.'],depends=('F14',))
add('F16','P1','Regenerate incompatible Python lockfiles and align package dependencies',
 [('mcp-apps/ask-productivity/requirements.txt',3),('mcp-apps/ask-productivity/uv.lock',1),('mcp-apps/ask-facilitator/pyproject.toml',7),('mcp-apps/ask-s4hana/uv.lock',1),('mcp-apps/ask-successfactors/uv.lock',1)],
 ['python-lock-versions.json','uv-lock-check.log','runtime-install.log','clean-install-results.json'],
 'All four committed uv lockfiles still select mcp 2.2.0 while current service manifests require mcp<2. The isolated S/4HANA uv lock --check --offline failed because the lock needs updating. Docker requirements resolve separately, so a passing requirements-based test run does not validate uv-based installation. Facilitator’s project metadata also omits direct dependencies present in requirements.txt, including cryptography and PyJWT.',
 'Different installation paths can select incompatible SDK APIs or fail locked installation altogether. This is a reproducible packaging inconsistency, not evidence that every deployed image has the wrong SDK. The fresh combined review environment resolved mcp 1.30.0 and passed the recorded tests.',
 ['Choose the supported SDK line based on the runtime import/transport contract; keep the current <2 constraint until an explicit, tested SDK migration is undertaken.',
  'Align pyproject.toml and production requirements for every service. Declare direct dependencies explicitly instead of relying on unrelated services or accidental transitive dependencies.',
  'Regenerate all four uv locks from the corrected manifests and test uv sync --locked in clean, service-specific environments.',
  'Make the production Docker installation consume the same authoritative resolved dependency set, or automatically verify equivalence in CI.',
  'Run each service’s import/startup and transport contract tests from its own build context; do not use sibling source or a union of all service dependencies to establish deployability.'],
 ['All four lock checks succeed without rewriting files.',
  'Each clean service environment imports and starts using only declared dependencies.',
  'Docker and locked developer/CI installations report the expected SDK version and pass REST/MCP contracts.',
  'No upgrade reintroduces previously fixed dependency advisories; record exact resolved versions.'])
add('F17','P1','Make plugin, Swagger and server authentication contracts agree',
 [('mcp-apps/ask-successfactors/agent/appPackage/productivity-plugin.json',25),('mcp-apps/ask-successfactors/agent/appPackage/sac-plugin.json',195),('mcp-apps/ask-s4hana/s4-connector-swagger.json',19),('mcp-apps/ask-s4hana/s4hana_mcp/server.py',104),('mcp-apps/ask-sac/sac_mcp/server.py',19)],
 ['source-manifest.json'],
 'Packaged runtimes declare auth type None for Productivity, Facilitator, SuccessFactors, SAC and S/4HANA. Current servers require credentials on their protected routes. S/4HANA and SAC Swagger now instruct callers to supply a JWT Bearer token, but their middleware compares the bearer string directly to MCP_API_KEY rather than verifying a JWT. Productivity/Facilitator accept verified JWT/gateway identity instead. These are different wire contracts.',
 'A directly connected client following the checked-in artifacts can receive 401 or tempt a deployment to enable anonymous access to make discovery work. A separately configured gateway could supply credentials, but no such live configuration was verified.',
 ['Write an explicit per-service contract for transport, service authentication, end-user identity, issuer/audience, credential headers and scopes. Choose user OAuth or signed gateway context for user-specific operations.',
  'For any intentionally API-key-only internal service, describe and configure the actual API-key mechanism accurately; do not label an opaque key as a verified JWT.',
  'Generate Swagger, plugin manifests and packaged connector definitions from the contract. Remove None authentication from protected direct runtimes or document and test the complete gateway boundary.',
  'Keep backend authorization from F01/F04/F05 even when the client supplies service credentials.',
  'Test the generated artifacts with the release image and target client, including credential expiry/rotation and negative access tests.'],
 ['Each packaged integration completes authorized discovery and a harmless tool call.',
  'The same request without credentials receives 401.',
  'A wrong audience or role is rejected by user-aware services; an opaque API key is never treated as a user principal.',
  'No integration requires ALLOW_ANONYMOUS=true to function.'],depends=('F01','F02'),confidence='Confirmed static contract mismatch; live gateway/client configuration unverified')
add('F18','P2','Preserve numeric zero in KPI snapshot parsing',
 [('mcp-apps/ask-productivity/productivity_mcp/tools_recommendations.py',83),('mcp-apps/ask-facilitator/productivity_mcp/tools_recommendations.py',83)],
 ['zero-probes.json'],
 'snapshot.get("value") or snapshot.get("metric_value") treats a legitimate numeric zero as missing. A snapshot containing value=0 returned VALIDATION_ERROR: Missing required metric value. If the alias contains another value, zero can be silently replaced by that value.',
 'Zero balances, zero variance and zero counts are valid business measurements. Discarding them can suppress recommendations or misstate inputs. This is separate from the earlier S/4HANA numeric-zero alias repair, which should not be reported as still broken.',
 ['Select aliases using explicit key presence/None checks, not truthiness. Define how conflicting canonical and alias values are handled, preferably rejecting disagreement.',
  'Parse numeric values as Decimal, preserve zero and negative values where the KPI contract allows them, and reject bool/nonfinite values explicitly.',
  'Search other financial/evidence serializers for the same alias pattern, including CSV fields, and fix only locations where zero/false/empty has defined meaning.',
  'Update both maintained copies and centralize the parsing helper if appropriate.'],
 ['Numeric 0, string "0" and Decimal zero are accepted consistently.',
  'Missing/None follows the explicit alias policy; conflicting fields do not silently change the value.',
  'NaN, infinity, booleans and invalid strings are rejected.',
  'A zero-valued snapshot reaches the correct rule evaluation with a preserved source record.'])
add('F19','P2','Require explicit business inputs instead of fabricated meeting and recipient defaults',
 [('mcp-apps/ask-productivity/productivity_mcp/server.py',241),('mcp-apps/ask-productivity/productivity_mcp/server.py',286),('mcp-apps/ask-productivity/productivity_mcp/tools_m365_writes.py',584)],
 ['source-manifest.json'],
 'PREPARE_MEETING_CREATION fills missing times with 27 August 2026 and missing attendees with a leadership address. PREPARE_EMAIL supplies a finance-leadership recipient when none is given. The meeting preparation path proceeds to availability and approval-token generation with these values instead of identifying missing required inputs.',
 'A malformed or underspecified LLM request can produce a convincing preview for the wrong people or an obsolete date. The two-step approval mechanism still exists; this finding does not claim these defaults immediately send messages.',
 ['Create operation-specific request models with required recipients, times and target identifiers; return field-level validation errors when essential values are absent.',
  'Normalize timezone-aware dates and require end > start. Apply an explicit policy for past meeting creation rather than a fixed historical fallback.',
  'Resolve recipients from explicit user-approved names/addresses and require clarification for ambiguity. Never manufacture a distribution list as the target of an underspecified write.',
  'Keep any sample data inside examples/tests, not live handoff defaults. Regenerate the operation schemas exposed to the model.'],
 ['Missing recipients or meeting times returns a validation result before provider or approval-token work.',
  'Ambiguous names remain unresolved until the user selects a target.',
  'Invalid ranges/timezones are rejected; valid explicit inputs produce the expected preview.',
  'Approval signs precisely the preview shown, including normalized times and recipients.'],confidence='Confirmed source behavior; live write not exercised')
add('F20','P2','Finish or explicitly disable advertised scheduled automation kinds',
 [('mcp-apps/ask-productivity/productivity_mcp/worker.py',120),('mcp-apps/ask-productivity/productivity_mcp/worker.py',139),('mcp-apps/ask-productivity/productivity_mcp/worker.py',228),('mcp-apps/ask-productivity/productivity_mcp/schedule_engine.py',189),('mcp-apps/ask-productivity/productivity_mcp/meeting_actions.py',794)],
 ['source-manifest.json'],
 'The scheduler recognizes ACTION_REMINDER as due, but the worker supports only MORNING, PRE_MEETING and EOD, then marks other kinds FAILED. The reminder evaluator exists separately and is not wired into worker dispatch. The worker also drains recommendations already in the outbox but does not acquire fresh KPI snapshots or call the recommendation scan, so it does not by itself implement autonomous fresh-data scanning.',
 'These are implementation-completeness gaps in the checked-in scheduled path. Another external orchestrator might trigger KPI ingestion, but none was verified. Existing benchmark suppression should remain until real comparable data is implemented; do not fabricate a benchmark to close this task.',
 ['Publish one supported-kind registry shared by subscription creation, scheduling and dispatch. Reject unsupported kinds during preparation until implemented.',
  'Wire meeting reminders through the durable outbox, using current task status, deadline version, approved recipient and a deterministic occurrence key. Re-read completion immediately before sending.',
  'For autonomous KPI scans, add a scheduled provider acquisition -> validated snapshot -> rule evaluation -> durable notification path with one trace and explicit standing authorization.',
  'Record errors and partial/missing sources truthfully. Keep unsupported benchmarking and other future capabilities visibly unavailable until their evidence contracts are implemented.',
  'Cover multiple simultaneous due events and missed-run/quiet-hours behavior instead of stopping forever on the first already-executed pre-meeting event.'],
 ['Unsupported subscription kinds cannot be confirmed as active.',
  'A due incomplete action generates one reminder; completed/revoked actions generate none.',
  'A changed verified KPI crosses a rule threshold and produces one attributed notification; an unchanged scan produces none.',
  'Two due pre-meeting events are each considered even if one occurrence already executed.',
  'Provider outages produce observable pending/failed work, not fabricated successful recommendations.'],depends=('F08','F09','F10','F18'),confidence='Confirmed static call-path gap; external scheduling unverified')
add('F21','P2','Make anonymous development access explicitly local and impossible in production',
 [('mcp-apps/docker-compose.yml',12),('mcp-apps/ask-facilitator/facilitator_mcp/server.py',127),('mcp-apps/ask-s4hana/s4hana_mcp/server.py',104),('mcp-apps/ask-sac/sac_mcp/server.py',19)],
 ['source-manifest.json'],
 'Compose publishes ports on all host interfaces while enabling ALLOW_ANONYMOUS=true and wildcard hosts/origins for the Python services. S/4HANA, SAC and SuccessFactors honor the anonymous flag without a production-mode prohibition. Facilitator’s REST prohibition checks ENVIRONMENT/NODE_ENV but not VELORA_ENV, unlike its updated JWT verifier.',
 'A local-development setting can expose business endpoints to the surrounding network or remain enabled in a production deployment. This is a configuration-dependent risk; production anonymous exposure was not measured.',
 ['Create an explicit local development profile with loopback-only published ports, restricted origins and synthetic/test data configuration.',
  'Centralize environment-mode parsing and use it consistently across services. Production must refuse startup if anonymous business access or test-token mode is enabled.',
  'Use authenticated defaults in shared deployment files. Leave only approved health/probe endpoints public.',
  'Document the difference between internal network reachability, service authentication and user authorization; internal ingress alone is not evidence of executive permission enforcement.'],
 ['Production combined with ALLOW_ANONYMOUS=true fails startup across all services and supported environment variable names.',
  'Local dev ports bind only to loopback unless the developer explicitly opts into a separate network exposure profile.',
  'Public health works while business routes reject missing credentials.',
  'Wildcard origin/host settings cannot silently enter the production profile.'],depends=('F03','F17'),confidence='Confirmed unsafe checked-in development defaults; production exposure unverified')
add('F22','P1','Provision the approval key required by Productivity writes',
 [('mcp-apps/ask-productivity/productivity_mcp/token_manager.py',28),('mcp-apps/ask-productivity/deploy/containerapp.bicep',73),('mcp-apps/deploy-azure-containerapps.sh',303)],
 ['source-manifest.json'],
 'Productivity’s token manager correctly requires VELORA_APPROVAL_HMAC_SECRET outside test mode. Neither the Productivity app’s Bicep environment nor its shell deployment binds that secret. Existing tests run with explicit test settings, so they do not establish deployable preparation/confirmation. The worker also needs a consistent approval-verification configuration when it uses those token flows.',
 'A new deployment using only the checked-in definitions can pass health checks yet fail PREPARE operations when approval signing is first needed. A manually configured live secret could mask the defect; the live environment was not inspected.',
 ['Add a dedicated approval-key secret parameter/reference to the Productivity deployment and bind VELORA_APPROVAL_HMAC_SECRET consistently to all components that issue or verify those approvals.',
  'Keep the key separate from OAuth client secrets and Cards/gateway signing keys. Coordinate key IDs and rotation for outstanding approvals; never restore a known fallback.',
  'Add startup/readiness validation for required approval configuration without exposing values. Make health distinguish process liveness from readiness to perform configured capabilities.',
  'Add a clean deployment configuration test and a prepare/confirm test using an explicitly provisioned synthetic key.'],
 ['A clean production configuration fails readiness when the approval key is absent.',
  'With the key reference present, prepare creates a token and the matching authorized confirm verifies it across instances.',
  'Wrong/rotated keys follow the defined outstanding-token policy, and secret values never appear in logs or artifacts.',
  'Both Bicep and shell deployment produce equivalent required bindings.'],depends=('F06','F08'),confidence='Confirmed deployment/source configuration mismatch; live secret override unverified')
metadata=json.loads((OUT/'review-metadata.json').read_text())
counts=collections.Counter(f['priority'] for f in F)
(OUT/'findings.json').write_text(json.dumps({'reviewed_revision':metadata['revision'],'date':'2026-09-19','findings':F},indent=2))
def source_link(loc):
 return f"[{loc['path']}:{loc['line']}]({ROOT / loc['path']}:{loc['line']})"
intro=f'''# Code review and implementation handoff — 19 September 2026

Reviewed commit: `{metadata['revision']}`. Repository: `{ROOT}`.

**The code needs fixes before a broad production-readiness sign-off.** This review identifies {len(F)} actionable repair tasks: {counts['P1']} P1 tasks and {counts['P2']} P2 tasks. The most consequential are request-controlled authorization context, incomplete gateway request signing, user/mailbox isolation, unsafe signing defaults, and inconsistent durable state. “Anonymous” was interpreted to include unauthenticated access as well as anomalies and bugs.

All **414 existing tests passed**. Additional independent probes still reproduced the defects described below. Passing those tests is useful regression evidence, but does not cover the missing authorization, multi-instance and crash-recovery paths.

This is an analysis and handoff. **No application source fixes, provider business writes, messages, pushes or deployments were performed.** The authored-source manifest was compared at the end: no recorded authored files changed. One Vitest cache file under tracked node_modules was changed by the test tool and restored to its initial committed bytes.

## How to give this to another model

Give the model access to this repository and start with [NEXT_MODEL_PROMPT.md](NEXT_MODEL_PROMPT.md), this report and [findings.json](findings.json). The accompanying evidence includes synthetic reproductions, test logs and a source-hash manifest. The code repository is required; the handoff ZIP does not contain the full application or dependency trees.

Each task below states the actual defect, its limits, concrete changes and completion tests. A task is not closed just because its old unit tests pass, its manifest changed, or a happy-path demo works. Keep the finding IDs in the implementation summary so closure remains traceable.

## Scope and depth

- Inventoried **{metadata['tracked_files']:,} tracked files**, including **{metadata['tracked_dependency_files']:,} files inside node_modules**. Third-party code was assessed through package metadata/installation/audits rather than claimed as a manual line-by-line review.
- Hashed **449 authored source/configuration files** across application services, shared modules, tests, TypeScript projects, deployment scripts, agent artifacts and Power Platform package material. Parsed all **193 authored Python files** in that inventory successfully.
- Reviewed authentication and dispatch boundaries deeply across Facilitator, Productivity, SuccessFactors, S/4HANA, SAC and Cards. Traced scheduled execution, approval consumption, evidence construction, storage selection, SDK packaging and the evaluation gate. Reviewed C# package helpers, deployment configuration and frontend/card validation at a static level.
- Inventoried **12 tracked ZIP archives**, with 705 source members including repeated snapshots/copies; parsed embedded Python sources without syntax errors. No archive member named exactly `.env` was found. This is not a comprehensive secret scan or proof that arbitrary embedded files contain no secrets.
- Parsed **145 authored JSON/XML files**. Two package files use non-strict JSON syntax (comment/preamble or trailing comma). They are recorded in structured-file-checks.json, not promoted to confirmed defects without establishing the package tool’s accepted syntax.
- Historical review folders and generated/media assets were not treated as current executable source. Existing prior findings were rechecked against this commit. This is repository-wide inventory/static coverage plus targeted deep review and tests, **not a claim that every line/path or every archived package was manually executed**.

## Fresh verification

| Check | Result |
|---|---:|
| SuccessFactors Python suite | 96 passed |
| Productivity Python suite | 201 passed |
| S/4HANA Python suite | 39 passed |
| Facilitator Python suite | 53 passed |
| SAC Python suite | 3 passed |
| Credential architecture | 7 passed |
| Cleanup | 4 passed |
| Cards | 8 passed |
| Evaluation pipeline | 3 passed |
| **Existing tests total** | **414 passed; zero failed/skipped** |
| Authored Python syntax | 193 parsed; zero syntax errors |
| TypeScript builds | Cards and pipeline passed in temporary copies |
| Clean npm installations | Both passed with lifecycle scripts disabled |
| Bicep templates | All six compiled successfully |
| S/4HANA uv lock check | Failed: lockfile requires update |
| Python static undefined names | Decimal and Tuple imports missing; see F12 |
| Production npm advisory checks | Unavailable: registry returned HTTP 503 twice per project |
| Fresh Python dependency audit | No production package flagged in the combined review environment; one unique test-only pytest advisory, duplicated in audit response |

Python tests ran with provider credentials removed, dotenv loading disabled, outbound socket connections blocked and temporary state paths. Productivity’s existing finance tests required its documented sibling workspace import mode; this is not a clean standalone-image proof. Facilitator tests ran from its own service directory. The review environment is a union of service requirements; clean service-specific dependency isolation is still required by F16. It resolved mcp 1.30.0, cryptography 50.0.1 and PyJWT 2.14.0; see review-runtime.txt for the full set.

The Python audit is limited to that resolved environment, not every committed lockfile or image. The reported pytest 8.4.2 advisory is development/test-only; requirements-test.txt currently excludes the audit-reported 9.0.3 fix. Evaluate a test-runner upgrade with plugin compatibility. Do not reuse the old review’s production vulnerability totals as current findings. npm audit failed, so there is no fresh clean npm security result.

No live SAP, Graph, Dataverse, Copilot client, real PostgreSQL migration/concurrency, container image build, .NET build, deployment parity or retained-audit-storage behavior was verified in this run. Synthetic provider-boundary probes do not establish production exploitation. All six Bicep templates compiled successfully; details are in bicep-build.json. Compilation does not verify a deployment or its runtime configuration.

## Findings index

P1 = address before deploying the affected capability; P2 = repair for correctness, integration or safe operation. Priorities describe the affected path and prerequisites, not an assertion that every issue is exploitable by an unauthenticated internet caller.

| ID | Priority | Repair task | Evidence level |
|---|---|---|---|
'''
for f in F:intro+=f"| {f['id']} | {f['priority']} | {f['title']} | {'Offline reproduction' if f['confidence'].startswith('Confirmed in offline') else f['confidence']} |\n"
intro+='''
## Implementation order

1. **Restore a reproducible baseline:** F16, then keep the existing 414 tests green. Add negative boundary and transport tests before fixing the relevant paths.
2. **Secure identity and approvals:** F01–F07, F17, F21 and F22. Pair native schema repairs (F12) with MCP authentication (F03). Do not fix tool reachability while leaving its authorization gap exposed.
3. **Unify persistence and scheduling:** F08 before F09/F10. Coordinate storage migration, client scoping and crash recovery; a local-directory change alone cannot close these tasks.
4. **Repair evidence and numbers:** F11, F18 and F19; preserve old records with explicit corrections rather than silently rewriting history.
5. **Complete integrations and gates:** F13–F15 and F20, then exercise generated artifacts and the deployed-container contracts in an authorized staging environment.

The identities, shared storage and signing contracts are cross-cutting decisions. Decide them once, write them down, and apply them to every transport and copied service module.

## Detailed repair specifications

'''
sections=[]
for f in F:
 s=f"### {f['id']} — {f['priority']}: {f['title']}\n\n"
 s+='**Locations:** '+ '; '.join(source_link(l) for l in f['locations'])+'.\n\n'
 s+='**Evidence:** '+ '; '.join(f'`{e}`' for e in f['evidence'])+'.\n\n'
 s+='**Confidence:** '+f['confidence']+'.\n\n'
 s+='**What is wrong.** '+f['problem']+'\n\n'
 s+='**Impact and limits.** '+f['impact_and_limits']+'\n\n'
 s+='**Implementation steps**\n\n'+'\n'.join(f'{i}. {x}' for i,x in enumerate(f['implementation_steps'],1))+'\n\n'
 s+='**Acceptance tests**\n\n'+'\n'.join('- '+x for x in f['acceptance_tests'])+'\n\n'
 if f['depends_on']:s+='**Dependencies:** '+', '.join(f['depends_on'])+'.\n\n'
 if f['id']=='F08':s+='SQLite explicitly documents the same-host limitation for WAL: [SQLite WAL documentation](https://sqlite.org/wal.html). This supports the recommendation to use a database server for state shared by different container hosts.\n\n'
 if f['id']=='F03':s+='Use the chosen MCP transport’s authentication facilities consistently; see [MCP authorization specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization). The defect above is established by the repository’s own intended auth behavior and the probe.\n\n'
 if f['id']=='F15':s+='GitHub recommends passing untrusted values through intermediate environment variables to reduce script-injection risk: [GitHub secure-use reference](https://docs.github.com/en/actions/reference/security/secure-use).\n\n'
 sections.append(s)
appendix='''## Improvements already present — preserve these

- S/4HANA no longer lists /schema as a public authentication exception; do not repeat the old metadata finding as unchanged.
- The evaluation orchestrator now tracks mandatory-stage completion and prevents a failed remote stage being disguised by local checks. F14 concerns a different malformed-success case.
- Cards rejects extra token segments and uses exclusive file creation plus closed failure behavior for consumption writes. F08 concerns actual storage topology across replicas; F06 records a newer production-secret regression.
- Compose now requires an explicit Cards signing secret. The Dockerfile and signer fallback still need F06.
- Productivity includes the PostgreSQL driver, and Facilitator includes the copied Productivity package and logger. They still need dependency/install-path and state-store alignment.
- Expired subscription rows can now be reclaimed. F10 concerns uncertain external effects and stale lease ownership, not the old inability to reclaim any row.
- The npm manifests/locks now support clean installation. Fresh advisory results were unavailable and should remain an open check.
- The reviewed shared JWT verifier now recognizes VELORA_ENV=production and respects an explicit expected audience. F02 and F21 identify different remaining inconsistencies.

## Additional maintenance and assurance work

1. **Remove maintained-copy drift.** copy-drift.json currently identifies one differing Productivity module: briefing_service.py in Facilitator. The other shared identity/worker fixes are currently aligned; do not repeat the old claim that worker.py/subscription_service.py copies still differ. Package common modules from a single maintained source or enforce a generated-copy hash check in CI.
2. **Stop treating tracked dependencies as the maintained application.** There are over thirteen thousand node_modules files under version control. Remove dependency trees in a dedicated cleanup only after the clean-install and packaging workflows are proven; do not mix that large change with security repairs. Keep intentionally committed action build output under an explicit reproducible policy.
3. **Expand test depth where the failures occurred.** Add a transport/auth matrix, two-user/two-tenant fixtures, real PostgreSQL tests with independent processes, and crash injection around external-send boundaries. Existing tests are valuable but heavily exercise direct functions and local stores.
4. **Verify packaged artifacts and runtime capabilities.** Rebuild agent/solution packages after fixes and compare their schemas, authentication, operation IDs and image digests with the source revision. A mockup or generated card is not evidence that a live workflow is implemented.
5. **Audit claims require operational evidence.** Hash/signature checks and metadata labels alone do not establish independently enforced immutability or retention. Validate key custody, write permissions, access controls and retention behavior in the configured storage before making compliance claims. No legal certification is provided by this review.

## Completion evidence required from the implementing model

For each F-ID, supply: files changed, root cause removed, regression test added, test result, remaining environmental dependency and closure status. Preserve one source revision and image digest per acceptance run. Treat “fixed in code”, “verified offline” and “verified in staging” as separate statements.

The final staging exercise should demonstrate: authenticated discovery and read per service; rejection of anonymous and wrong-tenant calls; an authorized preview/confirm with one provider effect; the same operation rejected on replay and after restart; two executives receiving correctly isolated briefings; safely reconciled interrupted delivery; verified source-backed evaluation; and a deliberately failed review causing a failing CI gate.

## Evidence files

- `findings.json`: structured repair specifications, source locations and dependencies.
- `source-manifest.json`, `review-metadata.json`: reviewed revision, source hashes, scope and drift check.
- `python-probes.json`, `gateway-probes.json`, `productivity-probes.json`, `sf-probes.json`, `s4-probes.json`, `sac-probes.json`, `zero-probes.json`, `node-probes.json`, `pipeline-empty-gate.json`: synthetic reproductions.
- `probes.py`, `additional_probes.py`, `node-probes.mjs`: executable reproductions. They intentionally capture current defective behavior; implementation regression tests must assert the corrected contract.
- `test-summary.json`, `check-exits.json`, suite logs/XML: 414-test baseline.
- `review-runtime.txt`, `runtime-install.log`: exact review dependencies and installation log.
- `python-lock-versions.json`, `uv-lock-check.log`, `clean-install-results.json`: packaging evidence.
- `python-audit.json` and npm audit JSON files: audit results/errors, with limitations above.
- `syntax.json`, `undefined-names.json`, `structured-file-checks.json`, `archive-inventory.json`, `copy-drift.json`: static coverage and artifact inventory.

Review evidence does not include environment-file contents, production tokens or live private provider records. Values appearing in probe inputs are synthetic. The reviewed code itself contains hardcoded example/default identifiers; their presence in source references should not be mistaken for proof of a real deployed configuration.
'''
(OUT/'REVIEW_AND_FIX_PLAN.md').write_text(intro+''.join(sections)+appendix)
prompt=f'''# Implementation request for the next model

Review baseline: `{metadata['revision']}` in the copilotstudio repository.

Implement the repairs described in `review-evidence/full-code-review-20260919/REVIEW_AND_FIX_PLAN.md` and `findings.json`. Read those files and the cited current source before editing. If HEAD differs from the baseline, revalidate each finding against the current code and identify already-fixed items rather than applying stale changes.

The review produced 22 repair tasks ({counts['P1']} P1, {counts['P2']} P2) despite all 414 existing tests passing. Your goal is to correct the demonstrated behavior and meet each task’s acceptance tests, not merely preserve the old passing count. Use the saved synthetic probes as reproductions; convert them into proper regression tests that expect the secure/correct behavior.

## Required approach

1. Inspect applicable repository instructions and working-tree changes. Preserve unrelated user work. Establish a clean, reproducible service-specific dependency baseline; resolve F16’s lockfiles before assuming a combined test environment proves deployment packaging.
2. Create a finding-by-finding checklist. Implement small coherent changes in the order in the report, keeping security context, token format and storage contracts consistent across services.
3. Prioritize F01–F07 and F17/F21/F22. In particular, do not make native Facilitator tools callable by fixing their schema while leaving authentication absent. Derive tenant, actor, roles, mailbox and scopes from verified identity. Remove public filesystem/signing-key control and permissive audit/workload defaults.
4. Complete F08’s shared-state design before closing replay/scheduling findings. The source already supports PostgreSQL for some stores, but subscriptions/business records/card tickets are separate stores. Migrate each required store explicitly; preserve data and prove cross-process behavior. Do not solve multi-replica persistence by pointing SQLite WAL at a network share.
5. Fix F09/F10 with per-owner clients and a durable send/reconciliation state machine. A provider timeout or expired claim is not proof that no message was sent. Use lease ownership checks; do not implement blind retries after uncertain submission.
6. Fix F11/F18/F19 without inventing source documents, confidence, recipients, dates or business values. Keep raw user input distinct from verified provider evidence and preserve numeric zero.
7. Finish the SAC transport, plugin authentication, CI failure behavior and scheduling capability contracts. Disable unsupported automation at creation time until implemented.
8. Keep current working protections: explicit mandatory-stage failure, cryptographic JWT validation, production test-key prohibition, exact token structure, closed storage failures, governed two-step writes and metadata authentication. Do not bypass controls to make tests or integrations pass.

## Tests and verification

- Run the existing suites and add the per-finding acceptance tests from findings.json.
- Use synthetic isolated test data. Block real business/provider writes during local tests, remove provider credentials from test subprocesses and disable dotenv reads.
- Test REST and native MCP over their transport boundary, not just direct function calls. Include initialize/list/call, valid credentials, missing credentials, wrong user/tenant/role/scope and session ownership.
- Use two independent processes for replay/claim tests and a real disposable PostgreSQL instance for store contracts. Exercise crashes before submission, after provider acceptance and before local completion; inject storage failures.
- Clean-install each service from its own declared dependencies and test the actual container build context. Regenerate locks and generated agent/connector artifacts consistently.
- Rerun dependency audits. npm audit was unavailable during the review; do not mark it clean from the old error JSON. Record production and test-only findings separately.
- Distinguish local tests from staging acceptance. Do not claim deployed parity, live provider success or retained-audit-storage guarantees without evidence from those environments.

## Scope and deliverables

Perform code fixes, migrations, configuration changes and local/disposable test work. Produce a deployment/rotation plan for external environment changes, including invalidation of any historically used default keys; do not silently deploy, send business messages or rewrite historical audit records as part of this code repair request.

Deliver:

1. The implementation and necessary regression tests.
2. Updated service/package/plugin configuration and reproducible dependency locks.
3. Any required data migration, rollback/cutover instructions and operator steps for keys/environment provisioning.
4. A closure table for **every F01–F22**: status, files changed, tests/evidence, and any remaining environment-dependent check.
5. A concise summary of residual risks and exactly what was not verified.

If a finding no longer applies, document the current source/test evidence. Do not silently drop it. If a fix depends on a business policy decision (for example permitted data scopes or retention), implement the configurable enforcement contract and clearly identify the policy values that the owner must supply.
'''
(OUT/'NEXT_MODEL_PROMPT.md').write_text(prompt)
(OUT/'README.md').write_text('# Review handoff\n\nStart with [REVIEW_AND_FIX_PLAN.md](REVIEW_AND_FIX_PLAN.md). Give [NEXT_MODEL_PROMPT.md](NEXT_MODEL_PROMPT.md) and [findings.json](findings.json) to the model implementing the fixes.\n\n'+f'Reviewed revision: `{metadata["revision"]}`. {len(F)} tasks; 414 existing tests passed; additional probes reproduce outstanding defects. No application source fixes were made.\n')
print(json.dumps({'findings':len(F),'priorities':counts,'report_words':len((intro+''.join(sections)+appendix).split())},indent=2))
