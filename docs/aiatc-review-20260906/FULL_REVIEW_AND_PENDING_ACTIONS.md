# AIATC full implementation review and test handover

Review date: **6 September 2026**. This is the current review; the folder date also reflects today. Scope: the five application services, their cross-service source/identity/audit behavior, the nine AIATC capabilities, the four approved S/4 reports and the solution/deployment artifacts relevant to those flows. **P&L remains excluded.**

**Conclusion: the code has improved substantially, but it is not ready to be signed off as fully implemented.** Several previous defects are fixed. Important financial, transport, recommendation, identity and end-to-end workflow gaps remain. Table definitions, connector branches and local unit tests are useful evidence of progress, but do not establish a working business capability.

## Deliverables

- [Excel action and test tracker](/Users/vikrambala/copilotstudio/docs/aiatc-review-20260906/AIATC_Pending_Actions_and_Test_Cases_06Sep2026.xlsx): 22 prioritized actions and 78 proposed test cases, with owners, dependencies, fixtures, steps, expected results and evidence/result columns.
- [Pending actions CSV](/Users/vikrambala/copilotstudio/docs/aiatc-review-20260906/pending-actions.csv).
- [Proposed test cases CSV](/Users/vikrambala/copilotstudio/docs/aiatc-review-20260906/proposed-test-cases.csv).
- [Executed offline probe results](/Users/vikrambala/copilotstudio/docs/aiatc-review-20260906/offline-probe-results.json).
- [Source inventory with hashes](/Users/vikrambala/copilotstudio/docs/aiatc-review-20260906/reviewed-source-inventory.csv): 60 Python files / 19,434 lines parsed in the five service packages. Parsing is a syntax/inventory check, not proof that every execution path was tested.

The 78 proposed cases are **not recorded as executed**. Some narrower behaviors were exercised by existing tests or independent probes; those results are identified separately below. Live execution, external messages, tenant configuration changes and deployments were not performed. Application code was not modified by this review.

## Current verification results

Tests were run in temporary working directories with project credential files excluded, environment values cleared and external socket connections blocked. This prevents a test from accidentally using the live SAP or Microsoft 365 account. Existing local fixture tests still ran.

| Service | Executed | Passed | Remaining result | Evidence |
|---|---:|---:|---|---|
| S/4HANA | 29 | 29 | Unit/fixture scope only | [Log](/Users/vikrambala/copilotstudio/docs/aiatc-review-20260906/ask-s4hana-offline-tests.log) |
| SuccessFactors | 85 | 85 | Unit/fixture scope only | [Log](/Users/vikrambala/copilotstudio/docs/aiatc-review-20260906/ask-successfactors-offline-tests.log) |
| Productivity, including recommendations | 49 | 48 | One auth test attempted network and failed its expected-error wording under the offline guard | [Log](/Users/vikrambala/copilotstudio/docs/aiatc-review-20260906/ask-productivity-offline-tests.log) |
| Facilitator | 13 | 13 | Fixture/local-storage scope only | [Log](/Users/vikrambala/copilotstudio/docs/aiatc-review-20260906/ask-facilitator-offline-tests.log) |
| SAC | 3 | 3 | Fixture/demo scope only | [Log](/Users/vikrambala/copilotstudio/docs/aiatc-review-20260906/ask-sac-offline-tests.log) |
| **Total** | **179** | **178** | **No live acceptance certification** | |

The failed Productivity test does not prove live authentication succeeds incorrectly. It proves this supposed unit test depends on an external call instead of a controlled mocked authentication response. T49 specifies the deterministic replacement test; no test implementation was changed here.

## Improvements confirmed since the earlier reviews

- AR now recognizes CompanyCodeCurrency; the independent exact-field multi-currency checks returned partitioned results for all four reports without the earlier budget summary crashes.
- Full collection no longer sends the visible detail limit as OData `$top`. Missing source count reduces confidence rather than claiming verified count reconciliation.
- Production QAS host rejection, supported date checks, blank-version handling and alias routes have improved.
- Single-currency budget configuration state is explicit. Headline and funds-center raw sums now use the same inputs. This fixes their internal inconsistency, but not the need to establish which rows are additive.
- Recommendation details now reload along with delivery records. The prior missing-recommendation-on-restart defect no longer reproduces in the simple recovery probe.
- SF recovery now processes commit markers and reconstructs audit payloads. Same-turn multiple-event and real persistent-storage cases still need attention.
- More M365 read/write branches exist; live authentication errors no longer deliberately fall through to the previous mock-send path. Email preparation now attempts to obtain a real draft item ID; some fallback paths remain problematic.
- The current solution ZIP has **14 entity definitions**, including institutionalrecord, proposalevaluation and peerbenchmark. The flow JSON now contains more concrete trigger/action definitions. Successful import, registered executable workflows, security and runtime integration remain to be demonstrated.

## Release-blocking findings and pending work

### 1. Financial precision is still lost when SAP sends numeric JSON

**Observed:** a mocked source amount `9007199254740993.01` was read as `9007199254740994.0`. The output serializer can preserve an existing Decimal, but the current source parser first uses ordinary json.loads without Decimal parsing. The serializer also changes a literal customer-name string `__EXACT_DEC_123__` into numeric 123. Invalid monetary input still becomes zero in calculations.

**Business impact:** amounts and source text can change silently while a report appears valid.

**Action A01; tests T01–T05:** preserve exact source numbers at ingestion and serialization, reject invalid required amounts and avoid string-marker replacement. Validate actual source currency fields and all presentation surfaces.

Source explanation: these are the functions that read SAP's reply and turn it into the user's answer. [Source parser:337](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/client.py:337), [serializer:40](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/server.py:40), [amount helper](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/contracts.py:26).

### 2. Budget source keys still reject legitimate line items and periods

**Observed:** two BudgetChangeDocumentItem values on one document were treated as conflicting versions and only one survived. Two consumption rows with different FinMgmtAreaPeriod values were also treated as conflicting. The key builder uses BudgetDocumentItem/FiscalPeriod rather than the actual supplied fields in these paths, and misses other source key components.

**Business impact:** a legitimate report can stop early or omit entries. Internal raw-sum consistency cannot repair missing input records.

**Actions A02/A03; tests T06–T17 and T22–T25:** obtain the actual SAP metadata keys, validate full compound keys, and implement Finance-approved additive grain, signs, value-type/overlap and organization/fiscal mappings. Repeated raw budget amounts must not be accepted as approved business budget simply because they sum consistently.

Source explanation: this function decides whether two SAP rows are separate business entries or copies of the same entry. [Key builder:105](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/client.py:105), [budget calculations](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/report_calculations.py:236).

### 3. Streamable MCP still fails and the served contracts disagree

**Observed:** POST `/streamable/mcp` initialize returned HTTP 500 inside a local TestClient lifespan. The parent application mounts the MCP app without wiring its lifespan. FastMCP lists seven tools; custom MCP lists the four reports. The current base URL validator also accepted the sibling service path ending `0001evil` because it checks a prefix rather than an exact path boundary.

**Business impact:** a connector can appear configured while the actual Copilot transport fails, or different connection methods expose different tools.

**Actions A04/A02; tests T18–T25:** exercise the real app lifecycle, unify the contract, validate exact endpoints and schemas, and preserve clear unsupported P&L behavior. Do not close transport work using only direct Python handler tests.

Source explanation: this code connects the report tools to the routes that Copilot actually calls. [Mount/app lifecycle:451](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/server.py:451), [approved path check:95](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/client.py:95).

### 4. Recommendation quality and delivery checks remain unsafe

**Observed:** a PARTIAL snapshot produced a recommendation even with requires_complete=true. The flag remains on the model but is not checked by the current evaluator. A fake sender returning only `status=ERROR` was marked DELIVERED even with require_live_delivery=true. The current gate checks simulation, not actual successful submission/receipt evidence. No operational Dataverse rule loader or scheduled scanner invocation was found outside the module/tests.

**Business impact:** an executive can receive advice from incomplete data, while failed delivery is recorded as successful.

**Actions A06/A07; tests T33–T43:** enforce completeness/freshness/approval, fail closed for invalid dates or missing units/currency, load published rule versions, persist complete evidence/breach state, and make delivery acceptance explicit. A provider accepting a message is not proof of final recipient delivery. File records require atomic claims and durable deployment storage; simple single-process restart recovery does not prove multi-replica correctness.

Source explanation: these functions decide when a KPI deserves an alert and whether the alert was actually sent. [Rule evaluation:373](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py:373), [delivery:527](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py:527).

### 5. Verified executive permissions and durable write approvals are incomplete

**Code finding:** S/4/SAC shared keys do not themselves establish which executive may see a company or mailbox. SF admin paths still supply Velora_Admin directly. Facilitator's REST routes do not show equivalent authentication enforcement. User-provided identity must not become authority without a trusted gateway/session binding. If enforcement exists externally, it needs deployment evidence and direct-route tests.

Productivity still contains a default approval signing secret and process-local consumed nonces. Existing audit idempotency is a useful second layer, but does not replace testing atomic cross-replica approval and provider-outcome reconciliation.

**Actions A05/A10/A21; tests T27–T32, T54–T56 and T78:** test unauthorized, forged, replayed, unconsented and overbroad calls across every transport. Validate the deployed perimeter rather than assuming it.

Source explanation: these paths decide who can access information and whether a write was truly approved. [SF admin:603](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/successfactors_server.py:603), [approval manager:15](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/token_manager.py:15), [Facilitator routes](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/server.py:94), [SF consent gate](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/consent_gate.py:28).

### 6. Microsoft 365 integration is still a mixture of live and local behavior

**Code finding:** live branches have been added, but mail-thread, priority/follow-up, meeting-detail, chat/channel-context and task-detail paths still use local lists. Graph paging is incomplete. Calendar mapping dereferences onlineMeeting without handling a null value. Some failed Teams/Planner reads can reach fixture fallback. A live list result therefore does not guarantee that its follow-up detail query reads the same provider object.

For writes, a string attachment is encoded as the string itself rather than resolved file/document content. The draft-failure/sendMail fallback still constructs an item link using request-id. Planner resolution can continue with an unresolved plan name or missing bucket.

**Actions A08/A09; tests T44–T53:** verify every advertised operation, actual object content, errors, paging, optional fields and identifiers. Use approved test mailboxes/plans for live tests; do not send external messages merely to verify a code review.

Source explanation: these functions fetch emails/meetings/tasks and perform the requested changes. [Mail detail:367](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:367), [calendar:376](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:376), [email payload:524](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:524).

### 7. Briefing and institutional-memory success claims are still stronger than the work performed

**Observed/code finding:** Facilitator still generates fixed workforce/AR/margin facts without fetching those sources. Local storage now exists, but its errors are swallowed. The Loop exporter constructs a link and returns SAVED_TO_LOOP_NOTEBOOK without a Loop provider call. An offline invocation with local append suppressed still returned that success state. Local persistence is not proof of storage in the named destination.

**Actions A12/A16/A17; tests T59–T60 and T65–T69:** build sourced briefs, real approved records and verified destination references; implement review-to-task-to-reminder-to-closure. Define ACL, retention, successor access and handling of missing transcripts/source facts.

Source explanation: these functions create meeting briefs and report where meeting records were saved. [Fixed briefing:418](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:418), [storage helper:68](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:68), [Loop exporter:470](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:470).

### 8. Durable audit, evidence and Dataverse workflows need integration proof

**Code finding:** SF spool recovery uses turn_id as its state key. Multiple audit event types can share a turn, so they need distinct event identities. Spool-write errors are logged but enqueue can continue; real persistence acknowledgement and container-replacement storage must be verified.

The solution ZIP now contains 14 entities and a revised flow file. That is progress beyond the previous review. It does not prove clean-environment import, executable flow registration, correct alternate keys/relationships/security or operational use of those tables. Current Python service searches do not establish implemented proposal/benchmark/agent-lifecycle workflows merely because their tables exist.

Productivity's sourceAsOf is still set to request time; source freshness and retrieval time should be separate. Saved historical evidence must be retrievable, immutable where required and access controlled.

**Actions A11/A13/A14; tests T26, T57–T64:** verify immutable evidence, persistence failure, same-turn events, clean import and actual flow execution.

Source explanation: these files determine whether decisions can later be explained and whether claimed stored records/flows actually exist. [Audit recovery:69](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/background_logger.py:69), [source timestamp:30](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/tools_m365_reads.py:30), [solution packager](/Users/vikrambala/copilotstudio/deploy/build_velora_executive_platform_solution.py:13), [current flow definitions](/Users/vikrambala/copilotstudio/deploy/solution/audit_cloud_flows.json).

## All nine AIATC capabilities: current disposition

| Capability | Current assessment | Pending actions | Main acceptance cases |
|---|---|---|---|
| Agent creation | Existing agent packages are a foundation; governed self-service lifecycle not demonstrated | A05, A13, A15 | T65, T27–T29 |
| Brief synthesis | Partial: some live source branches, but fixed briefs and incomplete scheduling/delivery | A07–A09, A11, A16 | T44–T51, T66–T67 |
| Decision traceability | Partial audit/evidence schema and spool; reliable scope/recovery/export not complete | A05, A10–A14 | T54–T64 |
| Enterprise query | Real service foundations; S4 correctness/transport gaps and live SF/SAC reconciliation remain | A01–A05, A08, A21–A22 | T01–T32, T72–T75 |
| Institutional memory | Local persistence and table exist; permanent governed provider-backed flow not established | A11–A14 | T58–T64 |
| Meeting intelligence | Partial tools; full transcript/review/task/reminder/closure flow not established | A08–A12, A17 | T48–T60, T68–T69 |
| Proactive recommendations | Engine and schema exist; eligibility/delivery/integration blockers remain | A03, A06–A07, A13 | T33–T43, T77 |
| Evaluation | Table foundation; approved rubric/extraction/scoring/history pipeline not demonstrated | A11, A13, A18 | T70 |
| Peer benchmarking | Table foundation; approved dataset/comparability method and runtime flow not demonstrated | A11, A13, A19 | T71 |

No capability should receive a blanket “done” label solely from this local review. Conversely, lack of local evidence is not proof that a separately managed tenant feature does not exist; supply an environment export/run receipt to establish it.

## How to execute the test plan

1. **Offline correctness and contract gate:** run proposed financial/transport/identity/negative tests with exact supplied SAP fields and mocked upstream HTTP. Include the currently reproduced failures. Make all unit tests independent of the internet. Preserve raw payloads, expected results and response bodies.
2. **Persistence and integration gate:** use a dedicated approved test environment to verify Dataverse import, rule approval, atomic claims, restart/replacement, actual provider objects and shared-storage behavior. Inject timeout, disk-full and ambiguous-send failures.
3. **Business acceptance gate:** Finance reconciles all four S4 reports to approved exports using identical dates, currency, scope and definitions; HR validates SF metrics; SAC owner validates model/story outputs; PMO validates lifecycle, meetings, evaluation and benchmarking.
4. **Copilot and release gate:** execute the real natural-language flow from tool selection through source, response and audit. Test cards and text, positive and denied cases. Verify the deployed image digest/configuration, readiness, permissions, durable storage and rollback. Collect the actual required 30-day recommendation operating evidence rather than substituting simulated dates.

For each case, fill in **actual result, evidence/run ID, defect ID and reviewer**. Evidence should identify the tested code/image revision, configuration/rule version, source scope/time, expected and actual results, audit ID and provider receipt where applicable. Use redacted synthetic data for offline cases; keep restricted live evidence in its approved repository.

**Completion rule:** close P1 defects first; complete P2 capabilities required by the mandate; obtain business-owner sign-off for source definitions and acceptance evidence. Do not turn unexecuted cases green or describe staging package creation as successful production deployment.

## Business decisions needed in parallel

- **Finance:** entity keys, budget additive grain/sign/value-type mappings, organization hierarchy, fiscal periods, approved KPI thresholds and reconciliation tolerance.
- **PMO/executive office:** self-service agent boundary, meeting review/action policy, recipient/schedule rules and proposal rubrics.
- **HR:** workforce/attrition definitions, effective-date policy and permitted employee drilldown.
- **Records/data owners:** approved storage, access/retention/successor rules, peer dataset/cohort/method and SAC source contracts.
- **Platform owner:** target test environment, trusted identity boundary, durable storage, secret references and release evidence.

The original [consolidated implementation plan](/Users/vikrambala/copilotstudio/docs/aiatc-implementation-20260905/AIATC_MODEL_READY_IMPLEMENTATION_PLAN.md) remains the design reference. Use this review and today's tracker for current pending work; earlier status reports are historical.
