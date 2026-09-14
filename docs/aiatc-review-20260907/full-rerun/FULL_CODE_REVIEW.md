# Full AIATC code review rerun — 7 September 2026

**Verdict: improvements verified, but not ready for production or Azure-only completion sign-off.** This report supersedes the earlier same-day findings only where it explicitly records a recheck. It is a review, not an implementation or deployment.

The reviewed state is the current working tree on top of commit `76511dcc51b9c58faced07d939b67127b066e8d9`. Uncommitted and untracked application changes were included. Nine of the 60 runtime files in the earlier source inventory changed. The current inventory syntax-checks 88 Python files, including tests and supporting scripts (24,904 lines); this count is not a claim of manual line-by-line review of all repository content. Review scope covers the five AIATC MCP services, shared approval/audit paths, deployment definitions, Dataverse solution artifacts, the dynamic card service and review-pipeline tests. Vendor dependencies, unrelated accelerator products and historical generated assets were not exhaustively audited.

No production code was edited. No cloud resources were changed, no SAP credential was used and no email/message was sent. Independent Python probes and service tests used synthetic data, isolated temporary state and blocked network connections. Azure queries were read-only. Build/test tools generated their normal development outputs.

## Test and validation results

| Suite | Result |
|---|---|
| S4 | 29 passed |
| SuccessFactors | 85 passed |
| Productivity | 48 passed, 1 failed |
| Facilitator | 13 passed |
| SAC | 3 passed |
| Dynamic card service | 6 passed |
| Agent review pipeline | 3 passed; TypeScript build passed |
| Total automated tests | **187 passed / 188 run** |
| Bicep templates | **6/6 compiled without diagnostics** |
| Python syntax inventory | **88 files parsed** |

The Productivity failure is the existing network-dependent authentication test described in R18. Passing suites do not cover the independent defects below. Compilation verifies template syntax/types, not deployment success, access permissions or business behavior. No live SAP/Finance reconciliation, Copilot acceptance, Dataverse import, destructive recovery, penetration/load test, image vulnerability scan or rollback was executed.

## Earlier fixes verified today

| Earlier finding | Current evidence |
|---|---|
| Numeric SAP precision loss | Synthetic 9007199254740993.01 survives parsing exactly. |
| Decimal marker collision | Ordinary `__EXACT_DEC_123__` string remains a string. |
| Budget movement items merged | Two distinct supplied BudgetChangeDocumentItem values now survive. |
| Consumption periods merged | Two distinct FinMgmtAreaPeriod values now survive. |
| Sibling service root accepted | Root ending `0001evil` now rejected. |
| Streamable MCP initialization failed | Initialization now returns HTTP 200. |
| Partial snapshot recommendations | requires_complete now blocks PARTIAL snapshots. |
| Provider error marked delivered | ERROR without receipt now yields FAILED and zero deliveries. |
| Empty role defaults to administrator | Empty roles and plain unverified role headers now return no roles; forged principal remains R02. |
| Failed institutional file write claimed success | Failed file write now returns STORAGE_FAILED; successful file write still falsely claims Loop, R08. |
| Multi-currency calculations | Four report helpers partition currencies in synthetic checks. Budget consumption now says CONFIGURATION_REQUIRED. |
| Azure deployment definitions absent | Five service templates plus shared storage now exist and compile. Actual wiring and deployed coverage remain R04/R05/R15. |

P&L remains excluded from S4 tool discovery and its legacy callable returns UNSUPPORTED_OPERATION. Do not add it back. MCP discovery still exposes seven tools including three master-data tools; confirm these additional tools are deliberately approved and aligned with the Copilot connector contract.

The invalid-money calculator now detects an error, but the complete user-facing result still reports zero balances (R01). This partial fix is not closed.

## Pending actions and tests

Priority P1 means resolve before production sign-off; P2 means incomplete functionality or verification that must be resolved for the claimed full capability scope. Each source link points to the code responsible, with the business consequence explained below. Acceptance tests are proposed unless the verification line explicitly states a probe was executed.

### R01 — P1: Invalid finance data still displayed as zero

The calculator now detects invalid money, but the report remains COMPLETE and formats null totals as AED 0.00. The complete tool probe reproduced this with OpenAmount=not-money.

**Required action:** Propagate invalid calculation status to the report, text and card; suppress totals and identify the source-quality failure. Apply the same rule to each currency group.

**Acceptance test:** Supply invalid, missing and nonfinite amounts in single/multiple currencies. Expect CONTRACT_MISMATCH or explicit unavailable amounts, never a successful zero balance.

**Evidence:** Reproduced. [Relevant code](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/tools.py:109) — this is where the behavior described above is implemented or configured.

### R02 — P1: Admin authorization trusts a forged principal header

Missing roles and plain role headers are now rejected, but a caller-created base64 x-ms-client-principal still returns Velora_Admin. This helper has no evidence that EasyAuth supplied the header.

**Required action:** Establish a verified identity boundary and deny caller-supplied principal headers; validate issuer/audience and configured algorithms for tokens. Prove direct service access cannot bypass the trusted gateway.

**Acceptance test:** Send missing roles, forged base64 principal, wrong issuer/audience and a valid authorized identity through the deployed boundary. Only the authorized identity may administer connections.

**Evidence:** Reproduced helper; deployed perimeter unverified. [Relevant code](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/successfactors_server.py:610) — this is where the behavior described above is implemented or configured.

### R03 — P1: Audit acknowledgement can discard uncommitted records

The worker ignores the sink result and writes a persisted marker. A BUFFERED fake sink was counted persisted. The real Dataverse client also catches non-consent remote failures, buffers in memory, and returns SUCCESS. A restart can therefore lose the only recoverable audit event.

**Required action:** Return an explicit durable commit result from Dataverse; acknowledge only confirmed commits, retain failed events and reconcile with stable event IDs. Treat spool write failures as failed durable acceptance.

**Acceptance test:** Simulate Dataverse outage then container replacement. Pending events must replay exactly once; no persisted marker until the sink confirms an actual row.

**Evidence:** Reproduced worker; real client verified by source. [Relevant code](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/background_logger.py:215) — this is where the behavior described above is implemented or configured.

### R04 — P1: Scheduled worker starts the HTTP server instead of processing work

The job uses the Productivity image without a command override. Its Docker command starts run_server.py, which starts Uvicorn. RUN_PERIODIC_OUTBOX_SWEEP has no consumer in application code, and no production caller of RecommendationEngine was found.

**Required action:** Add a bounded worker entry point, load approved Dataverse rules, fetch source snapshots, dispatch/reconcile and exit with a meaningful status. Wire the job to that command and required identities/configuration.

**Acceptance test:** Trigger a job against synthetic source/sink adapters in Azure. Confirm a rule loads, an item is processed, audit is committed and the execution exits successfully.

**Evidence:** Static trace. [Relevant code](/Users/vikrambala/copilotstudio/mcp-apps/deploy-azure-containerapps.sh:251) — this is where the behavior described above is implemented or configured.

### R05 — P1: Deployment script names storage paths without mounting them

The script registers environment storage but provides no app/job volume or volumeMount definitions. Setting /mnt/velora environment paths does not attach Azure Files. Separate Bicep templates do define mounts, but this script does not deploy those templates.

**Required action:** Use one tested deployment path with actual volume bindings, valid full Key Vault secret URLs, per-image digests and registry/resource permissions. Fail the release on prerequisite/job errors rather than printing verified success after ignored failures.

**Acceptance test:** Inspect each deployed revision for volume bindings, replace its container, and verify queued work and evidence survive. Deliberately fail a prerequisite and require a failed release result.

**Evidence:** Static trace; templates compile. [Relevant code](/Users/vikrambala/copilotstudio/mcp-apps/deploy-azure-containerapps.sh:205) — this is where the behavior described above is implemented or configured.

### R06 — P1: Two instances can deliver the same notification

Two engines loaded the same pending file and each sent the notification through a fake provider: two sends. The CLAIMED state is eligible again and state/claims are in memory. Azure Files alone does not add distributed ownership. Templates allow two replicas.

**Required action:** Use an Azure queue/store with atomic claims, leases and provider idempotency/reconciliation. Make state transitions durable and conflict-safe; persist episodes and cooldown updates consistently.

**Acceptance test:** Start two consumers on one pending item, crash one after provider acceptance, and retry. Assert one logical delivery and recoverable outcome with no lost work.

**Evidence:** Reproduced with two instances and fake sender. [Relevant code](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py:328) — this is where the behavior described above is implemented or configured.

### R07 — P1: Approval validation permits empty identity and restart replay

A valid token is accepted when both presented identity fields are empty. Recreating the manager accepts the consumed token again. A built-in fallback signing key also remains in source.

**Required action:** Require trusted nonempty user/tenant identity, compare it to the approved preview, require a configured secret, and atomically consume approval/idempotency state in a durable shared store.

**Acceptance test:** Reject empty identity, conflicting identity, wrong tenant and missing secret. Repeat a token after restart and across two replicas; the operation must execute once.

**Evidence:** Reproduced helper; route binding needs end-to-end test. [Relevant code](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/token_manager.py:172) — this is where the behavior described above is implemented or configured.

### R08 — P1: Loop save still reports a provider operation that never occurred

A failed local write now returns STORAGE_FAILED, which is an improvement. A successful JSONL write still returns SAVED_TO_LOOP_NOTEBOOK with constructed Loop and OneNote links without a provider call.

**Required action:** Persist to the named supported destination and retain its real object ID/link, or accurately describe the Azure institutional store actually used. Implement permissions, versioning and retention there.

**Acceptance test:** Let the filesystem write succeed while the named provider is unavailable. Do not claim a Loop save. Verify a successful provider write returns an existing accessible object.

**Evidence:** Reproduced successful filesystem path. [Relevant code](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:498) — this is where the behavior described above is implemented or configured.

### R09 — P1: Executive briefing presents fixed numbers as sourced facts

The briefing function returns fixed workforce, receivables and margin values and labels them synthesized across connectors. No connector fetch occurs in that function.

**Required action:** Replace fixed facts with authorized source results and plain-language provenance, retrieval time and completeness. With unavailable data, clearly state the unavailable section.

**Acceptance test:** Change synthetic connector values and verify the briefing changes. Disconnect a source and assert no fixed fallback facts or ready claim.

**Evidence:** Static trace. [Relevant code](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:420) — this is where the behavior described above is implemented or configured.

### R10 — P1: Facilitator has no service authentication enforcement

The app registers tools and CORS but no API-key or user authorization middleware. An unauthenticated guide tool request returned HTTP 200. Deployment sets MCP_API_KEY and ALLOW_ANONYMOUS, but this server does not read/enforce them. The same dispatcher serves business tools.

**Required action:** Enforce service authentication and trusted caller authorization before every business handler; keep health checks narrowly exempt and protect write operations with approval.

**Acceptance test:** Call read/write routes and MCP with no key, wrong key and unauthorized user; reject before invoking a mocked business handler. Test valid authorized access separately.

**Evidence:** Safe guide route reproduced; business routes reviewed, not invoked. [Relevant code](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/server.py:91) — this is where the behavior described above is implemented or configured.

### R11 — P1: Source keys still omit distinguishing line fields

Budget movement item and consumption period fixes work. AR/AP key still omits LedgerGLLineItem; the key probe collides for two such lines. Consumption key still omits supplied ReferenceDocument/Year/Item/Type fields. Actual SAP metadata must settle the complete keys.

**Required action:** Use entity-specific metadata-confirmed keys and preserve distinct reference/ledger lines. Reconcile counts and totals with Finance before sign-off.

**Acceptance test:** Use identical document/item values with different ledger lines and identical budget scope/period with different reference documents. Verify both valid rows survive or a truthful metadata issue blocks calculation.

**Evidence:** Ledger collision reproduced; consumption verified by source. [Relevant code](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/client.py:105) — this is where the behavior described above is implemented or configured.

### R12 — P2: Several Microsoft 365 reads still use local collections

Mail thread, priority/follow-up mail, meeting detail, chat/channel context and task-detail helpers still read process collections. Live credentials do not turn these helpers into provider reads. Calendar parsing also assumes onlineMeeting is a dictionary.

**Required action:** Finish live provider implementations with identity scope, paging, null-safe contracts and honest unavailable responses; keep fixtures explicit and isolated from production.

**Acceptance test:** With live mode and mocked Graph, return multiple pages, null onlineMeeting and nonempty thread/task details. Assert correct results and no local fixture fallback.

**Evidence:** Static trace. [Relevant code](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:367) — this is where the behavior described above is implemented or configured.

### R13 — P2: Budget approval cannot be supplied at runtime

Budget consumption now truthfully returns CONFIGURATION_REQUIRED, but mapping_approved=False is hardcoded. No configured approved calculation mapping can make this report production ready.

**Required action:** Load a versioned Finance-approved mapping and additive grain from the approved configuration store, preserve source lineage and fail closed when approval is missing.

**Acceptance test:** Run approved and unapproved mapping versions with known budget/commitment/actual rows. Verify source-owner totals and visible version/approval provenance.

**Evidence:** Configuration-required status reproduced. [Relevant code](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/tools.py:439) — this is where the behavior described above is implemented or configured.

### R14 — P1: Detailed durable audit fields are dropped in the live projection

The live audit projection preserves a small set of columns and a text record-type prefix; invocation, approval/idempotency and other rich evidence fields are not persisted as modeled. Alternate-key checks also rely on process sets.

**Required action:** Align actual Dataverse schema, payload and unique keys with the required event contract. Persist trusted identity, event/run IDs, policy/rule versions, source/filter/quality, approval reference and provider outcome without secrets.

**Acceptance test:** Read actual durable rows for approved/denied/failed/retried operations after restart; verify all required fields, distinct same-turn events and cross-replica uniqueness.

**Evidence:** Static trace. [Relevant code](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/dataverse_audit.py:303) — this is where the behavior described above is implemented or configured.

### R15 — P1: Azure deployment coverage still does not demonstrate completion

Fresh read-only inventory of the specified group still shows one S4 app, external ingress, identity None and no volumes. The specified registry still has only S4 and SF repositories. This does not cover all services/workers or connect the deployed tag to this working tree.

**Required action:** Build, scan and test immutable artifacts for every required runtime; deploy approved Azure resources and retain digest/revision/identity/storage/diagnostic evidence. Include dynamic card service if used.

**Acceptance test:** Compare release inventory to Azure resources and ACR digests; exercise health, authorized smoke, storage recovery and rollback. Check other groups explicitly if used.

**Evidence:** Fresh Azure observation; limited group/registry scope. [Relevant code](/Users/vikrambala/copilotstudio/mcp-apps/deploy-azure-containerapps.sh:1) — this is where the behavior described above is implemented or configured.

### R16 — P2: Capability and flow completion remains unproven

The solution contains an empty Workflows element. Flow JSON is a definition artifact, not proof of imported executable flows. No complete runtime path was established for governed agent lifecycle, proposal rubrics or approved peer benchmarks.

**Required action:** Complete/import the executable components, connect the nine capability flows and retain acceptance evidence. Distinguish implemented code, deployed configuration and business acceptance.

**Acceptance test:** Exercise each workbook capability end to end with approved sources and audit evidence, including successor access, transcript approval/tasks/reminders and rubric/benchmark provenance.

**Evidence:** Repository evidence gap; tenant import not tested. [Relevant code](/Users/vikrambala/copilotstudio/deploy/solution/customizations.xml:8101) — this is where the behavior described above is implemented or configured.

### R17 — P2: Card submission tokens lack durable and user-bound validation

The card signer has a built-in fallback secret and process-local consumed-token set. The submission route accepts submittedData without binding its content to an approved preview or authenticated user.

**Required action:** If this service authorizes actions, require configured signing material, trusted user/session/preview binding and durable atomic replay control; ensure downstream actions reauthorize independently.

**Acceptance test:** Change submittedData, present a token under another identity and replay after restart. Reject unauthorized changes and duplicate actions.

**Evidence:** Static trace; six existing card tests pass. [Relevant code](/Users/vikrambala/copilotstudio/mcp-apps/dynamic-adaptive-card-service/src/security/idempotency-signer.ts:11) — this is where the behavior described above is implemented or configured.

### R18 — P2: Authentication-failure test depends on real networking

The isolated test expects authentication wording but attempts networking and instead receives OFFLINE_REVIEW_NETWORK_BLOCKED. This is a test isolation defect; it is not proof that a failed live token request falls back to simulation.

**Required action:** Mock the token provider with a representative authentication failure and assert no business provider or mock-success path runs.

**Acceptance test:** Run the test with networking disabled; it must pass and verify fail-closed behavior.

**Evidence:** Reproduced existing test failure. [Relevant code](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/test/test_m365_writes.py:221) — this is where the behavior described above is implemented or configured.

## Current Azure evidence

Fresh queries on 7 September 2026 against `az-vel-agenticad-execai-dev-uaen-rg` and `azvelaiagentexecaidevcruaen` show:

- One Container App: `agenticad-execai-dev-uaen-ca-001`, ready revision `agenticad-execai-dev-uaen-ca-001--0000022`.
- Image reference `azvelaiagentexecaidevcruaen.azurecr.io/velora-mcp-s4hana:1.1.7`.
- External ingress, identity type `None`, volumes `[]`.
- ACR repositories: `velora-mcp-s4hana` and `velora-mcp-sf`.

These results are limited to the specified group/registry. They do not establish absence elsewhere. A ready revision is not proof that the newly reviewed changes are deployed. No image digest/source correspondence was verified.

Azure Files needs both environment storage and container volume bindings; a path variable alone does not establish persistence. The new Bicep templates contain those bindings, while the shell deployment path omits them. [Microsoft storage mount documentation](https://learn.microsoft.com/en-us/azure/container-apps/storage-mounts).

A scheduled Container Apps job must run the intended finite workload. Here the image's default command starts the HTTP server and the sweep variable has no handler. Use a real worker command with completion/retry evidence. [Microsoft jobs documentation](https://learn.microsoft.com/en-us/azure/container-apps/jobs).

SF's mount setting is also ambiguous: `AZURE_STORAGE_MOUNT_PATH` is treated as the entire spool filename, whereas the Bicep value ends in `/sf` and other services treat similar settings as directories. Define a directory and append a fixed spool filename; require actual Azure persistence in production rather than silently falling back to home or temporary directories. Shared files alone do not solve multi-instance transactions, audit commit assurance or record permissions.

## Capability acceptance still required

| Workbook capability | Remaining sign-off evidence |
|---|---|
| Agent creation/lifecycle | Governed create/change/disable/version/rollback and authorized owner controls. |
| Brief synthesis | Live facts, unavailable-source handling, actual Azure nightly/EOD schedules and truthful delivery receipt. |
| Decision traceability | Durable decisions with source/rule/approval versions, alternatives and record permissions. |
| Enterprise query | Authorized live data, complete paging, exact finance amounts and nontechnical source explanations. |
| Institutional memory | Actual governed destination, durable retrieval, successor access and retention distinct from 30-day chat memory. |
| Meeting intelligence | Real transcript ingestion, review approval, task creation, reminders and closure linked to evidence. |
| Proactive recommendations | Dataverse rule loading, real worker wiring, completeness and multi-instance delivery controls. |
| Proposal evaluation | Approved versioned rubric, reproducible scoring and source-linked rationale. |
| Peer benchmarking | Approved ADAA data, comparable periods/definitions, permitted access and cited provenance. |

Treat source explanation as part of every result: name the business record/report, explain what it measures, show its period and retrieval time, state completeness and any calculation/rule used, and provide an authorized source reference. A fixed “Source: SAP” label is not evidence that a source was fetched.

## Release sequence

1. Resolve identity, approval, invalid-result presentation and audit-commit findings.
2. Complete real provider paths and source-based briefings; approve Finance mappings and complete row keys.
3. Connect Dataverse configuration and a finite Azure worker to durable atomic queues/state; verify duplicate/restart behavior.
4. Use one complete deployment path with tested per-service immutable digests, actual mounts, identities, valid secret references, diagnostics and truthful failure reporting.
5. Run the action-specific tests, the existing 78-case capability catalog and owner-reviewed end-to-end Azure/Copilot acceptance. Capture audit evidence before closing each action.

## Evidence files

- `source-inventory.csv`: current file hashes and syntax results.
- `changed-since-full-review.json`: changed runtime files against the earlier baseline.
- `*-tests.log`: individual automated test output.
- `probe-results.json`: financial, transport, recommendation and failed-storage checks.
- `security-and-durability-probes.json`: identity, approval, successful-file-write, audit and duplicate-send checks.
- `bicep-validation.json`: six template compilation results.
- `azure-apps.json` / `acr-repositories.json`: fresh read-only Azure results.
- `pending-actions-and-tests.csv`: 18 current actions with acceptance tests and verification status.

The earlier 78-case catalog remains a useful broader acceptance plan; its cases were not all executed in this rerun and should not be marked passed from these unit-test totals.
