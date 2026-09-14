# Velora Agentic AD — why texecutable architecture handoff

Review baseline: 14 September 2026. Requirements source: [meeting minutes](</Users/vikrambala/velor/Velora_ MoM _ Agentic AD _ 1009.docx>), meeting dated 10 September 2026. Repository: `/Users/vikrambala/copilotstudio`; HEAD `f1f9a1bb51fcef4c538db4a8c705937ab5c702f3` plus existing working-tree changes. Use `source-manifest.json` for reviewed file hashes. Implement against the current verified files, not against a reconstructed clean HEAD.

## 1. Scope and evidence discipline

Deliver the live SAP S/4HANA and M365 Phase 1 capabilities, with a decision-oriented demonstration joining attribution, confidence, explainability, institutional memory and an exportable audit trail. Prepare evidence for the September 24 review; the recorded Phase 1 target is September 30. The minutes do not specify the next meeting's timezone. Do not infer that business scopes or configurations were approved merely because a demonstration was discussed.

Treat the minutes as business requirements. They do not authorize this model to send invitations, emails, reminders, change tenant permissions, or deploy code. The original request was to produce implementation instructions. A subsequent implementing model must operate within its user's authorization. Do not implement in-person meeting capture as a mandatory Phase 1 requirement: document it in the roadmap unless separately agreed. Do not extend Phase 1 into unrelated HR, SAC, Salesforce, or ServiceNow features merely because those directories exist.

This review traced relevant source and local solution definitions. It did not inspect the current published Copilot configuration, tenant permissions, live source contents, live schemas or deployed images. Fifteen existing recommendation/outbox tests passed freshly with network blocked and temporary state; see `offline-tests.txt`. These tests use fixtures and are not live delivery evidence. The bundled document Python runtime lacked the full application test dependencies, so no full service regression claim is made. Prior reviews were used as leads; the defects listed below were checked in current source. Historical security findings not independently verified here must be rechecked before being treated as current.

Use these states in the implementation ledger: `NOT_STARTED`, `IN_PROGRESS`, `IMPLEMENTED_OFFLINE`, `BLOCKED_INPUT`, `BLOCKED_ENVIRONMENT`, `LIVE_VERIFIED`, `BUSINESS_ACCEPTED`. Never collapse them into a single green “done.” A package may be implemented offline while live proof remains blocked.

## 2. Requirements to implement

Paragraph IDs below are the zero-based paragraph indices in the supplied DOCX, including blank paragraphs. They provide stable references for this document version.

| ID | Minutes | Required outcome | Packages |
|---|---|---|---|
| R01 | P19, P22–24 | Live SAP/M365 selected use cases; consistent source attribution and permission-aware outputs across prompts | W01, W02, W04, W05, W15, W16 |
| R02 | P27–30 | Morning brief at 07:00; on-demand and email pre-meeting briefs including remaining meetings; end-of-day digest; configurable CEO preferences; evidence of automatic operation even if later disabled | W05, W07, W15, W16 |
| R03 | P33–35 | Ranked attention items across inbox, calendar and meetings with contextual priority scores and score factors | W05, W06, W15 |
| R04 | P38–42 | Meaningful categorized recommendations and alerts; useful/not-useful feedback; scope and sources aligned with CEO Office | W08, W09, W14, W15 |
| R05 | P45–48 | Visible confidence for each material data point, evaluation, suggestion or recommendation; evidence-based framework | W01, W06–W08, W11, W14, W15 |
| R06 | P51–53 | Expandable plain-language decision explanation; vendor evaluation illustrates criteria and weights; sources/confidence/rationale on one screen | W01, W11, W15 |
| R07 | P56–60 | Exportable decision reconstruction with identity, provenance, rationale, attribution and integrity; demonstrate tamper/deletion resistance | W03, W04, W12, W16 |
| R08 | P63–65 | Show how prior vendor performance changes or supports current evaluation; explicitly identify available history and gaps | W10, W11, W15, W16 |
| R09 | P68–70 | Teams meeting intelligence with live action tracker, named owners, due dates and automatic deadline follow-ups | W05, W07, W13, W15, W16 |
| R10 | P69 | In-person meeting capture is a documented roadmap item if not completed for Phase 1 | W13, W16 |
| R11 | P74–75 | Agree peer benchmarking scope with CEO; implement agreed scope or present explicit pending scope/status | W14, W16 |
| R12 | P79–81 | Prepare next-review scenarios and evidence; complete remaining capabilities with truthful status | W00–W16 |

## 3. Verified entry points and gaps

These are local code observations, not assertions about the deployed service. “Not found” means not found in the inspected authored MCP Python/TypeScript and deployment source, not that no external implementation could exist.

| Evidence | Verified entry point | What must guide implementation |
|---|---|---|
| E01 | [M365 client](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:550), `summarize_priority_mail` | Filters Graph messages by `importance eq 'high'`; no cross-source score. |
| E02 | [M365 client](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:898), `get_daily_briefing`, `plan_my_day` at 1037 | Fixed business focus statements, sample-ID overdue condition, fixed focus blocks; calendar call unbounded to today. |
| E03 | [Read tools](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/tools_m365_reads.py:734), `get_daily_executive_briefing` | Fixed warning counts; fallback still returns `SUCCESS`. Envelope timestamp is generation time. |
| E04 | [Models](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/models.py:12), `ReadToolEnvelope`, `HandoffResponse`; [router](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/server.py:140) | Read envelope has one source string, no per-claim confidence. Handoff responses omit some source/warning fields. Preserve new metadata through the whole route. |
| E05 | [Recommendation engine](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py:68), `KPIRecommendationRule`, `KPISnapshot`, `RecommendationEngine.evaluate_snapshot` at 989 | Thresholds/categories/hysteresis/outbox exist. New recommendations hardcode `High`; default rules are active; `rules or DEFAULT_RULES` re-enables defaults for an empty list. |
| E06 | [Notification dispatch](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py:1137), `_enqueue_notification`, `dispatch_outbox`; [worker](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/worker.py:27) | Recipient defaults are hardcoded. Worker only reconciles/dispatches; no source scan or briefing scheduler. Acceptance is marked delivered and can invent a fallback reference. |
| E07 | [Facilitator tools](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:130) | Calendar/history/sync/workflow/briefing/notebook handlers return `SOURCE_UNAVAILABLE`. `ingest_chat_to_knowledge_graph` stores a process list/JSONL, asserts broad access/source defaults, ignores append failure. No verified enterprise memory retrieval in this path. |
| E08 | [Facilitator email](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:254), `send_executive_email_via_graph` | Presence-only confirmation; generated IDs even on success; exceptions return simulated sent status. Guide/policy instructions contradict one another. |
| E09 | [Productivity email](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:1332), `execute_send_email` | Treats Graph request ID as message ID and constructs an item link. An HTTP request identifier is not a mailbox item identifier. |
| E10 | [Approval token](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/token_manager.py:101), `create_approval_token`; [store](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/operation_store.py:495), `PostgresOperationStore` | Token creation catches persistence failure and still returns token. PostgreSQL only implements prepare and expects `ttl_seconds`, while caller supplies `expiry_minutes`; SQLite has fuller lifecycle. |
| E11 | [Productivity audit](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/dataverse_audit.py:623), `create_audit_record`; [SF audit](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/dataverse_audit.py:842) | Buffered entries enter duplicate indexes later treated as already committed. [audit wrapper](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/audit_client.py:42) returns IDs as audit status and reports queued reconciliation without demonstrating a durable queue in this method. |
| E12 | [Facilitator server](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/server.py:66), `_wrap_tool_handler`; [identity](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/shared_mcp/identity.py:298), `verify_gateway_assertion` | MCP wrapper lacks ordinary-tool identity enforcement; legacy signature fallback exists. Kill-switch/network helpers exist but source search did not find runtime integration outside their definitions/tests. |
| E13 | [S4 source metadata](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/client.py:534); [contracts](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/contracts.py:96) | Source/coverage/report confidence already exist; reuse them. `evidenceRef` can be a generated identifier with no durable resolver. Confidence is report-level, based largely on extraction completeness. |
| E14 | [S4 tools](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/tools.py:423), `s4__get_budget_consumption`; [calculations](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/report_calculations.py) | Budget mapping explicitly unapproved. AR/AP aging calculation exists. Do not use open-payable balances as evidence of vendor delivery quality. |
| E15 | [Memory service](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/memory_service.py:73), `MemoryService` | User-partitioned 30-day interaction summaries exist. This is not multi-year vendor-performance history. Avoid importing the HR server into the new decision path. |
| E16 | [Solution XML](/Users/vikrambala/copilotstudio/deploy/solution/customizations.xml:5235); see `verified-local-schema.csv` | Local definitions include sourcecatalog, kpidefinition, kpirecommendationrule, kpisnapshot, recommendation, recommendationfeedback, notificationdelivery, decisionevidence, institutionalrecord, proposalevaluation, peerbenchmark. Runtime feedback/vendor/benchmark implementations were not found. |
| E17 | [Audit flow JSON](/Users/vikrambala/copilotstudio/deploy/solution/audit_cloud_flows.json:1); [builder](/Users/vikrambala/copilotstudio/deploy/build_velora_executive_platform_solution.py:13) | Flow JSON refers to columns absent in local audit-table XML. Packing this JSON as a root ZIP file does not prove it imports as an executable solution-aware flow. |
| E18 | [Card service](/Users/vikrambala/copilotstudio/mcp-apps/dynamic-adaptive-card-service/src/index.ts:23); [template registry](/Users/vikrambala/copilotstudio/mcp-apps/dynamic-adaptive-card-service/src/engine/template-registry.ts:8) | Generic templates and render endpoint exist. `/templates` returns a fixed list; adding a file alone will not update discovery. |
| E19 | [Card signer](/Users/vikrambala/copilotstudio/mcp-apps/dynamic-adaptive-card-service/src/security/idempotency-signer.ts:12) | Default signing key, process-local replay set, no user/resource/payload binding. Card validation is not a business authorization boundary. |
| E20 | [Deployment script](/Users/vikrambala/copilotstudio/mcp-apps/deploy-azure-containerapps.sh:283); [Productivity Bicep](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/deploy/containerapp.bicep:56) | Scheduled worker configured every 15 minutes and `REQUIRE_LIVE_DELIVERY=false`; app storage mount does not establish correct worker storage. |
| E21 | [Agent instructions](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/agent/appPackage/instruction.txt:1); [connector generator](/Users/vikrambala/copilotstudio/deploy/generate_connectors_swagger.py:1) | Child instruction forbids SAP calls; parent owns SAP. Descriptions advertise capabilities beyond inspected live paths. Preserve or explicitly revise that ownership boundary. |
| E22 | [Evaluation score](/Users/vikrambala/copilotstudio/agent-review-pipeline/src/evaluation/scoreCalculator.ts:67); [Pages workflow](/Users/vikrambala/copilotstudio/.github/workflows/deploy-pages.yml:30) | Partial available stage can pass; Pages publishes all `docs`. Keep private implementation/evidence artifacts outside that path. |

## 4. Architecture decisions for implementation

These are design instructions from this handoff, not claims that they were approved in the minutes.

1. Retain existing service boundaries. Productivity owns M365 retrieval, triage, briefing composition, meeting actions and delivery execution. S4 owns finance retrieval/calculation. Facilitator owns cross-system decision orchestration and institutional context. Cards renders validated output. Copilot routes and presents; it must not independently invent/recalculate financial or decision scores.
2. Keep `RecommendationEngine` as the deterministic evaluator in its current package. Add a workload-authenticated snapshot-ingestion boundary: Facilitator/source orchestration obtains verified S4 snapshots and sends normalized evidence to the evaluator. The Productivity conversational child must not directly query SAP, consistent with its current instruction. A normal user handoff must not accept arbitrary KPI values as authoritative source snapshots.
3. Use Dataverse for business records/policies/feedback/decision records, extending existing tables after metadata verification. Use the existing PostgreSQL direction for shared approval/outbox/schedule transactional state; finish it rather than running multi-replica SQLite on a file share. Keep SQLite only as an explicitly local/test implementation. Implement a reconciliation path between operational state and business/audit records; do not pretend two stores form one transaction.
4. Use one versioned evidence contract across services. Initially define it in Productivity `models.py` and export a JSON schema artifact consumed at the other service boundaries. Pure common contract/score code may become a small installable shared package if needed; do not create further divergent copies of `shared_mcp`. Any such packaging change must be tested inside each service image.
5. Separate interactive approval from standing authorization for scheduled briefs/reminders. An approved subscription may authorize a narrowly scoped repeated send; a clock trigger or service identity alone does not. Default subscriptions to disabled, preserve per-send approval elsewhere, and never “solve” scheduling by disabling confirmation globally.
6. Implement summaries as recorded evidence-to-rule explanations. Capture observable calculation inputs and outputs, not private chain-of-thought. A confidence label is an evidence-quality assessment, not a calibrated probability unless calibration has actually been established.

### Exact path conventions for the package instructions

When a package lists a bare module filename, resolve it using the owning service below. A file labeled NEW is to be created; all other entry points are verified in the evidence table. Do not search unrelated backups or dependency folders for similarly named modules.

| Owner | Runtime module directory | Test directory |
|---|---|---|
| Productivity | `/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/` | `/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/test/` |
| Facilitator | `/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/` | `/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/test/` |
| S4 | `/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/` | `/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/test/` |
| Cards | `/Users/vikrambala/copilotstudio/mcp-apps/dynamic-adaptive-card-service/src/` | `/Users/vikrambala/copilotstudio/mcp-apps/dynamic-adaptive-card-service/test/` |

Facilitator new tool handlers must be explicitly registered in its existing server/TOOL_SPECS. Productivity's current exposed route is the handoff router; a new module is not automatically a REST/MCP tool. For workload-only operations, define a distinct authenticated internal route rather than routing them through a user-body identity path. Preserve typed schema and authorization in each transport.

### Common contracts — NEW version 1

Add these contracts before feature-specific implementations. Exact language-level class names below are **NEW**. Generate schemas; make unknown fields fail validation on mutation/configuration requests. Preserve compatibility of existing read fields through explicit adapters, not silent reinterpretation.

| Contract | Required fields and invariants |
|---|---|
| `ExecutionContext` | `tenantId`, authenticated `actorObjectId`, `actorType` USER/WORKLOAD, `onBehalfOfUserObjectId` when applicable, authorized organization scopes, correlation/conversation/turn IDs, policy version. Populate from trusted server context, never trusting body identity alone. |
| `EvidenceSource` | `sourceId`, system, business title, provider record ID or protected snapshot reference, nullable real URL, `retrievedAt`, nullable `sourceUpdatedAt`, measurement period, scope, currency/unit where relevant, coverage, limitations, classification, access-scope reference, content hash and version. Missing source update time stays null. Generated evidence IDs must resolve to persisted records. |
| `MaterialClaim` | `claimId`, kind FACT/EVALUATION/SUGGESTION/RECOMMENDATION/BENCHMARK, text, optional typed value/unit/currency, nonempty evidence source references for factual assertions, `derivedFromClaimIds`, calculation/policy version, confidence assessment, limitations. Suggestions may cite contributing facts; distinguish proposed action from observed fact. |
| `ConfidenceAssessment` | label HIGH/MEDIUM/LOW/UNASSESSED; framework version; source reliability, corroboration, timeliness, completeness, comparability factors with observed evidence, short reason, limiting factors. Percent is optional and disabled until a validated framework exists. Unknown factors are explicit; no automatic maximum for “SAP.” |
| `EvidenceEnvelope` | `schemaVersion`, operation status, `resultSummary`, typed result, `claims`, `sources`, warnings, missing source statuses, correlation ID, `audit={status,recordId}`, generated time. Add this information to `HandoffResponse`; map legacy status/source fields consistently. |
| `DecisionRecord` | decision ID/version, use case, evaluated options, criteria/weights/directions, input snapshot IDs, baseline score, memory contributions, final score/rank, tie/missing-data policy, selected/recommended option or no-decision result, claims, concise rationale, policy/code versions, authenticated actor, audit manifest reference. |
| `AttentionItem` | stable item ID/type, source record references, title, required attention/action, nullable deadline and its evidence, verified related meeting IDs, factor scores/contributions, total score, rank, scoring version, missing factors, claim confidence. Deterministic tie ordering. |
| `AutomationSubscription` | subscription ID/version, tenant/owner, actual authorized mailbox/sender/recipients, kind MORNING/PRE_MEETING/EOD/ACTION_REMINDER, timezone/local schedule, meeting filters/lead time/horizon, channel, enabled flag, validity, authorizer/time, allowed data scope, last/next run, quiet/missed-run policy. Never assume recipient from code default. |
| `DeliveryReceipt` | actual provider status, nullable request ID, nullable message/item ID, nullable verified URL, accepted time, optional independent delivery observation, simulation flag, failure category. Request IDs and application-generated operation IDs are not message IDs. |

**Confidence v1 design:** implement a configurable conservative rule policy, not LLM self-rating. `UNASSESSED` when no valid assessment can be made. `LOW` when evidence is stale beyond its approved source SLA, materially incomplete, conflicting without resolution, or benchmark definitions are noncomparable. `HIGH` only when required inputs are verified, sufficiently complete/fresh, applicable definitions agree, and required corroboration is satisfied; authoritative internal single-source facts can qualify where policy does not require multiple sources. Otherwise `MEDIUM`. Derived decision confidence cannot exceed the weakest material input required to support the recommendation, and missing mandatory decision inputs block recommendation. A source SLA or reliability policy not yet approved must not silently become an invented business policy. Use explicitly labeled test policies for offline tests. Show factor reasons next to the assessed claim.

## 5. External inputs — implement explicit gates

Create **NEW** `review-evidence/mom-implementation-inputs.md`. Record each item as supplied/verified/pending, evidence reference, owner role and affected package. The following are unresolved in the supplied minutes/code; do not ask for all of them before starting independent work.

| Input | Responsible role to identify | Required artifact / blocked live work |
|---|---|---|
| I01 | CEO Office | Briefing timezone, working days, 07:00 morning confirmation, EOD time, horizon, selected/all meetings, lead time, recipient/sender and channel; W07 activation. Repo default Asia/Dubai is a proposal, not CEO approval. |
| I02 | CEO Office | Priority rubric, business criticality rules, important sender identities/groups, weights, risk/deadline interpretation; W06 business acceptance. |
| I03 | Finance + CEO Office | KPI definitions, organization scope, currency, thresholds, risk/opportunity categories, allowed source catalogue, owners; W08 active rules. Existing seeded thresholds are not approval evidence. |
| I04 | Procurement + CEO Office | Real vendor comparison, criteria/weightings, comparable commercial basis, technical scores, historical performance records and permission scope; W10–W11 live decision. |
| I05 | CEO + data owner | Peer cohort, metrics, periods, definitions, permitted/licensed external/internal sources, refresh requirements; W14 live benchmarking. |
| I06 | Tenant/platform administrator | Verified Graph permissions, mailbox scope, workload identities, Dataverse entity metadata/roles, PostgreSQL connection mechanism, real published agent export and deployed image inventory; live integration gates. |
| I07 | Records/security owner | History activation date, retention/legal-hold/access policy, append-only evidence retention and signing-key custody; W10/W12 live integrity acceptance. |
| I08 | Meeting owner + tenant administrator | Authorized Teams transcript/notes source, Planner plan/bucket, directory owner resolution, reminder/escalation rules and standing authorization; W13 live tracking. |

## 6. Ordered work packages

Implement W00–W16 in order. A package blocked on external input must still complete its independent contract, adapter, tests and disabled configuration. Do not activate a dependent feature using invented input. Each package ends with the ledger checkpoint described in `START_HERE.md`.

### W00 — Establish the exact baseline and retained capability inventory

**Dependencies:** none. **Requirements:** all. **Read:** E04, E07, E17, E20–E22 and applicable repository instructions.

1. Compare current files to `source-manifest.json`. Capture current branch, HEAD and scoped working-tree diff metadata without credential values. Identify simultaneous changes before editing overlapping files. Do not auto-stash/reset the user's work.
2. Enumerate actual route -> operation -> handler -> provider -> persistence -> UI mappings for retained capabilities. Record supported, stubbed, test-only and externally hosted/unverified separately. Include both REST and MCP registrations, not merely tool descriptions.
3. Identify the editable parent Copilot source. The child `instruction.txt` is not the complete parent. If only backups/ZIPs exist, inspect inventory read-only, identify authoritative export/version and obtain a fresh authorized export before modifying publication. Do not edit a backup and call it deployed.
4. Create the implementation ledger and input register. Record W01–W16 dependencies and acceptance IDs. Treat I01–I08 as gates only for work that needs them.
5. Create an isolated test environment from service dependency manifests. Keep credentials/dotenv off and state temporary. The Productivity `pyproject.toml` references a missing README at this baseline: resolve packaging metadata if the build fails; do not mask failure. Capture actual interpreter/library versions. Do not reuse historic test counts as baseline results.

**Acceptance T00:** every retained operation has a mapped handler and owning service, with absent implementations labeled; source diff is preserved; no business writes occur; test environment cannot contact live providers.

### W01 — Add evidence contracts and confidence assessment

**Dependencies:** W00. **Requirements:** R01, R05, R06, R07. **Read:** E03, E04, E13, E16, E18.

**Edit:** Productivity `models.py`, `tools_m365_reads.py`, `server.py`; S4 `contracts.py`, `client.py`, `tools.py`, `adaptive_cards.py`. **NEW:** Productivity `evidence_contracts.py`, `confidence_policy.py`, `test/test_evidence_contract.py`, `test/test_confidence_policy.py`. Use `models.py` to re-export shared models if contracts are split into the new file. Do not maintain conflicting definitions.

1. Implement Common Contracts v1. Preserve exact Decimal finance values using a documented JSON serialization convention; do not convert money through binary floats. Keep a single deterministic canonical encoding for hashing.
2. Add `claims` and `sources` to every retained material-result path, including partial/error paths. Never drop them when constructing `HandoffResponse`. Source references must resolve within the response or protected persisted evidence store. A bare “SAP S/4HANA” label is insufficient attribution for a decision.
3. Implement confidence v1 as a pure, clock-injected function. Validate required policy configuration and record framework version. Keep priority, confidence and vendor suitability score as separate fields and labels.
4. Adapt existing S4 source/coverage/quality without losing record/page counts, count-verification status or limitations. Preserve `sourceUpdatedTime=null`; retrieval time cannot establish source freshness. Replace unresolvable generated evidence references with resolvable evidence IDs once W03 persistence is available.
5. Model source outage independently from an empty successful query. `PARTIAL` must enumerate missing sources/coverage; access-denied results must not disclose unauthorized titles or records. Unknown evidence returns a gap, never a fabricated citation.
6. Validate final narrative against material claims: amounts, dates, score labels and recommendation must correspond to structured values. Prefer templated deterministic narrative for numeric/decision statements. Reject or omit unsupported generated statements.

**Acceptance T01:** a two-source response maps each claim to the correct source; unknown timestamp stays null; stale/partial/conflicting inputs lower confidence; a perfect extraction cannot override a stale source; a derived recommendation reflects limiting inputs; source/claim/correlation metadata survives the full handoff; JSON round-trip preserves finance values.

### W02 — Remove misleading success and business facts from runtime

**Dependencies:** W01. **Requirements:** R01, R02, R03, R07. **Read:** E02, E03, E07–E09, E21.

**Edit:** Productivity `m365_client.py`, `tools_m365_reads.py`, `tools_m365_writes.py`; Facilitator `tools.py`; affected tests and tool descriptions.

1. Remove fixed Emiratisation/receivables/approval statements, sample-task overdue conditions, static focus slots, invented warnings and default business recipients from active paths. Keep synthetic datasets inside explicit test fixtures only. Do not use sample-data cleanup scripts without inspecting the proposed diff.
2. Derive overdue from actual due time and incomplete status. Derive focus slots from timezone-normalized occupied calendar intervals and configured working hours. Mark tentative proposed focus time as a proposal. If the required configuration/source is missing, return a gap.
3. Make `get_daily_executive_briefing` return `PARTIAL` when any required section fails; preserve per-source status. Remove the success message for a total outage. Optional unavailable sections must be identified as optional in configuration.
4. Replace Facilitator's exception-based simulated sent responses with truthful denied/error/unavailable responses. Prevent all provider calls for an invalid/missing approval. Until W04 establishes a safe shared execution path, make this sender unavailable or route to a verified governed sender; do not retain an alternate bypass.
5. Correct all email receipts: Graph sendMail acceptance is `ACCEPTED`/`SUBMITTED`; message ID/URL remain null unless obtained from the provider as real item metadata. Never use `request-id` or generated `GRAPH-MSG`, `FAC-MSG`, `ref-*` identifiers to construct mailbox links. Update callers and tests that currently expect a fabricated successful delivery.
6. Keep real `SOURCE_UNAVAILABLE` stubs truthful until implemented. Fix contradictory Facilitator guide steps and `ready_for_auto_send` descriptions so they match approved policy modes. Do not make advertised unsupported capabilities look implemented by changing prompts alone.

**Acceptance T02:** provider failure never returns sent/delivered/simulated success; no fixed business claim appears in a live response; empty inbox has zero real items; late/failed source is explicit; receipt without provider item ID has no item link; changing fixture due date changes overdue status.

### W03 — Finish durable persistence and reconcile Dataverse schema

**Dependencies:** W01. **Requirements:** R04, R07–R09, R11. **Read:** E05, E06, E10, E11, E16, E17.

**Edit:** Productivity `operation_store.py`, `recommendation_engine.py`, both existing `dataverse_audit.py` implementations only where retained; deployment/schema tooling. **NEW:** Productivity `business_repository.py`, `postgres_outbox_store.py`, versioned migrations under `/Users/vikrambala/copilotstudio/deploy/migrations/mom20260910/`.

1. Export actual Dataverse metadata read-only when authorized: LogicalName, EntitySetName, attribute types/lengths, relationships, alternate keys, ownership, field security, row permissions. Compare to `verified-local-schema.csv`. Do not derive plural EntitySetName by string manipulation. Record proposed columns separately from deployed columns.
2. Reuse existing business tables. Their names do not guarantee their fields are appropriate: inspect whether a purported lookup is actually text; do not send `@odata.bind` until metadata supports it. Add migration-backed tenant/scope, policy/version, evidence reference and concurrency fields where missing.
3. Implement repositories for source catalogues, KPI definitions/rules/snapshots, recommendations, feedback, institutional records, decision evidence and benchmarks. Validate object ownership on every read/write; bound queries and handle paging/throttling. Add stable tenant-qualified unique keys and optimistic concurrency.
4. Define one storage interface for approval lifecycle: prepare, approve, reject/revoke, claim, mark submission, complete, fail-before-submit, outcome-unknown, retrieve and expire. Finish the PostgreSQL implementation, reconcile `expiry_minutes` versus `ttl_seconds`, add migrations/indexes and avoid storing bearer approval tokens as raw database lookup keys. Store a token hash plus server-side opaque operation ID.
5. Implement shared PostgreSQL outbox/subscription/run state. Retain local SQLite as a test adapter. Persist recommendation state, recovered/continuing updates, cooldowns and breach episodes; current in-memory cooldown and update paths require attention. Make recommendation event + outbox enqueue atomic in the chosen operational store, then mirror/reconcile Dataverse by durable IDs. Define authoritative state and recovery order explicitly.
6. Repair buffered-audit handling in both retained clients. A local buffer cannot populate a confirmed-commit index. `ALREADY_COMMITTED` requires durable record lookup with matching event/tenant/payload. An arbitrary 412 is not automatically a verified duplicate. Return an actual commit status and record ID separately. Implement an actual durable reconciliation queue before reporting queued status.
7. Compare `audit_cloud_flows.json` column references with real metadata. Either package executable flows using the platform's supported solution format or remove them from claimed runtime dependencies and use the actual application audit path. A JSON file in a ZIP is not acceptance evidence.
8. Write additive migration, preflight, rollback and recovery instructions. Do not delete prior audit/history rows to make schema migrations pass. Verify code can tolerate the expand/migrate transition before final cutover.

**Acceptance T03:** repeat migration is safe; metadata mismatch fails preflight; two separate processes contend for one shared operation/outbox row with one winner; restart preserves state; two tenants cannot collide/read one another; buffered audit retry still denies governed writes; Dataverse mirror failure leaves a recoverable pending record, not a false commit.

### W04 — Enforce authenticated, approved execution at all boundaries

**Dependencies:** W02, W03. **Requirements:** R01, R02, R07, R09. **Read:** E08, E10–E12, E19, E20.

**Edit:** Productivity `server.py`, `token_manager.py`, `tools_m365_writes.py`, `worker.py`; Facilitator `server.py`, `tools.py`; retained shared identity helpers; Card signer/integration.

1. Verify issuer, audience, tenant, expiry and authorized caller identity at REST, MCP and worker boundaries. Bind request method/path/body hash where gateway assertions are used. Reject legacy unsigned/unbound identity paths for production. Verify user-to-mailbox and organization-scope authorization before provider access; app permissions are not automatically executive delegated consent.
2. Remove production test-token exceptions and anonymous bypass modes from retained deployment contracts. Ordinary MCP handlers need the same authorization as REST. A body-supplied role or `__caller_role__` must not grant administration. Internal trusted calls should receive explicit verified context, not reach a public helper's “no raw request” branch.
3. Connect kill-switch checks at dispatch and immediately before provider mutation. Apply verified outbound destination restrictions in actual clients, including redirects/pagination links. Test denial at the handler-to-provider boundary, not just the helper function.
4. Bind approvals to actual tenant, user, operation, preview hash, policy version, expiry and durable operation ID. Never issue usable approval when preparation persistence fails. Changing recipient/body/destination/schedule invalidates existing approval.
5. Extend the explicit `ALLOWED_OPERATION_MAPPINGS` / `normalize_operation_type` allowlist in `operation_store.py` for the new approved subscription and meeting-action operation types; do not disable unknown-operation rejection. Use the durable lifecycle from W03 in every retained email/meeting/Teams/Planner write: validate -> approve -> atomically claim -> commit audit start -> mark submitting -> provider -> persist outcome/audit. If failure is after possible provider acceptance, move to outcome-unknown/reconciliation; do not automatically resubmit.
6. Support standing authorization for W07/W13 as its own typed policy record with bounded recipients, resources, schedules, expiry and revocation. Check it on every run. The worker records its workload identity and the authorizing user/policy; never impersonate a user by substituting an email string.
7. Keep Card ticket UX replay protection separate from business approval. Either bind Card tickets to user/tenant/action/resource/payload with shared replay storage, or use them only as UX hints and enforce full authorization in the business endpoint. Remove fallback production signing key. Forged client fields must not change server-side approved data.

**Acceptance T04:** unauthenticated REST/MCP denied; foreign tenant/user/payload/expired/replayed approvals denied before any provider call; preparation/audit outage produces zero mutations; two replicas with one approval produce one submission; ambiguous send is not resent; revoked standing authorization prevents the next run; kill switch blocks actual handler calls.

### W05 — Correct M365 source adapters and retrieval completeness

**Dependencies:** W01, W04. **Requirements:** R01–R03, R09. **Read:** E01–E04, E09, E21.

**Edit:** Productivity `m365_client.py`, `tools_m365_reads.py`, `models.py`, route parameter mappings. **NEW tests:** `test_graph_read_contracts.py`.

1. Implement bounded, explicit date windows. Use calendarView for occurrences/exceptions in the requested interval; calculate today's boundaries in the configured user timezone, then send unambiguous offsets. Do not retrieve `/events` and label everything “today.” Treat `onlineMeeting=null` safely and preserve meeting cancellation/response/recurrence metadata.
2. Honor supplied mail lookback, unread flag, maximum results and time filters end to end. Existing `search_mail(date_from=...)` does not apply that value in the inspected query. Retain actual Graph `webLink`, IDs, received/modified times, importance, read/flag state, sender identity and necessary body excerpt with privacy controls.
3. Follow authorized provider next links with loop/host/page/row bounds. Record truncation, missing pages, count semantics and 429/retry-after outcomes. Never silently score only the first page as the complete inbox. Apply query parameters that are supported together by the actual provider endpoint; validate against official documentation during implementation.
4. Preserve Planner task IDs, assignee directory IDs, due/start timestamps, percentComplete, plan/bucket IDs and concurrency metadata. Resolve display names from directory evidence. Do not guess owner from a task title or manufacture a task link. Preserve a real source ID when a deep link is unavailable.
5. Implement meeting-to-context joins using verified IDs/references and bounded related mail/meeting notes. A similar subject alone is not a confirmed relationship; label uncertain candidates and require a verified match before merging factual evidence.
6. Isolate source errors by section. Replace unsupported Work IQ/approval retrieval claims with clearly unavailable sections unless an actual configured adapter is found and verified. Never require an unsupported optional section to trigger invented fallback data.

**Acceptance T05:** local-midnight boundary, recurrent meeting, null onlineMeeting, canceled event, unread filtering, multiple pages, page cap, 403, 429 and timeout all have truthful outputs; tasks overdue by timestamp are identified even when title lacks “overdue”; foreign mailbox/plan denied; references resolve to the returned provider IDs.

### W06 — Build contextual inbox/calendar attention scoring

**Dependencies:** W01, W05; I02 for business activation. **Requirements:** R03, R05.

**NEW:** Productivity `triage_engine.py`, `test/test_triage_engine.py`; proposed operation `GET_EXECUTIVE_ATTENTION`. **Edit:** read tools, models/router and published connector in W15.

1. Normalize mail, meeting/calendar items and supported meeting-derived actions into `AttentionItem`. Consider all retrieved candidate messages in the agreed lookback, including normal-importance mail. Collapse duplicate thread references only with a recorded relationship; preserve source IDs.
2. Implement a versioned rubric with factors `businessCriticality`, `senderImportance`, `deadlineProximity`, `riskSeverity`, each 0–5, sourced from approved mappings or verified extracted evidence. Do not derive executive rank from a name alone. Source-provided importance can contribute but is not the whole rubric.
3. Compute `priorityScore = round_half_up(100 * sum(weight_i * factor_i / 5))`, with Decimal weights summing exactly to 1. Reject negative weights, invalid factor ranges and absent mandatory configuration. Do not invent production weights. A synthetic test rubric with four 0.25 weights is acceptable only in tests.
4. For unknown optional factors, show unknown, use the configured missing-factor policy, and keep the denominator fixed unless the approved rubric explicitly says otherwise. Do not silently renormalize and inflate the score. If mandatory factors are missing, return unscored/needs review. Record coverage/limitations independently of priority.
5. Infer a deadline only from a cited explicit statement or authoritative task/calendar field; ambiguous “soon” is unknown. Normalize dates with timezone. A model-extracted deadline must preserve the supporting excerpt/location and be flagged inferred until validated.
6. Sort score descending, then earlier known deadline, then stable item ID. Return factor values, weighted contributions, why attention is required, proposed next action and separate confidence. Do not send replies or change calendars during triage.
7. Extend `summarize_priority_mail` as a compatibility view or route to the new engine; retain `plan_my_day` as scheduling composition rather than falsely claiming it is scored triage.

**Acceptance T06:** a normal-importance message with verified imminent critical deadline can outrank high-importance routine mail; equal inputs/config/time give equal score/order; missing deadline is not fabricated; zero candidates produces empty list; malicious email instructions cannot change weights or actions; for test factors 5/4/3/2 and equal test weights score is 70; priority 100 may still have LOW evidence confidence.

### W07 — Implement briefing variants and governed scheduling

**Dependencies:** W03–W06; I01/I06 for activation. **Requirements:** R02, R05.

**Edit:** Productivity briefing read/write functions, `worker.py`, delivery engine, deployment job definition. **NEW:** `briefing_service.py`, `subscription_service.py`, `schedule_engine.py`, tests `test_briefing_variants.py`, `test_schedule_engine.py`.

1. Implement three compositions over W05/W06 data: MORNING (today/upcoming horizon, calendar preparation, tasks, unread attention items and sources); PRE_MEETING (specific event or remaining eligible meetings); EOD (observed completions, outstanding decisions/actions and next-day items). Do not label a message sent as a task completed or claim accomplishments absent source evidence.
2. Use the same composition for on-demand view and email content, with the same evidence IDs and policy version. Render a brief snapshot before preparing a send; execution must send the approved snapshot, not regenerate unseen content under the same token.
3. Add validated subscriptions with I01 fields, draft/approved/enabled/revoked states and scoped standing authorization from W04. Default disabled. Implement all/selected meeting filters, lead time and horizon. Missing EOD time is configuration-required, not an invented 17:00 commitment.
4. Extend the finite worker to identify due subscription runs, generate briefs, persist a run + outbox record and dispatch under policy. Separate scheduling, composition and submission states. Use run key `(tenant, subscriptionId, subscriptionVersion, scheduledOccurrence)`; pre-meeting occurrence additionally identifies the real event occurrence. A rerun must not send twice.
5. Handle overlapping workers, missed run catch-up, time changes, canceled/rescheduled meetings and expired authorization explicitly. Record local scheduled time and UTC execution time. Do not send canceled-event briefs or flood missed runs after downtime; require configured catch-up policy.
6. Use the existing Azure Container Apps job direction. Add/update an actual Bicep job definition with pinned image digest, workload identity, shared state access, nonzero failure exit and one-minute scheduler tick as an engineering default. Do not rely on the current every-15-minute outbox-only job to prove 07:00 dispatch. No SLA guaranteeing exact receipt at 07:00 is implied; measure trigger/submission delay separately.
7. Container Apps cron uses UTC. If I01 confirms Asia/Dubai, 07:00 local is 03:00 UTC; a fixed morning-only job can use that mapping. Prefer timezone-aware subscription evaluation for mixed schedules rather than separate manually guessed conversions. Store evidence of an authorized enabled run and later disabled configuration without deleting its run history.

**Acceptance T07:** one morning run at configured local time; all/selected/remaining meetings behave correctly; canceled event excluded; EOD cites observed changes; retries/restart do not duplicate send; missing section remains PARTIAL; preview matches sent content hash; revoked/disabled subscription causes zero sends; authorized live test records job execution ID, policy version, provider acceptance and independently observed receipt where delivery is claimed.

### W08 — Connect live finance snapshots to meaningful recommendations

**Dependencies:** W01, W03–W05; I03 for active rules. **Requirements:** R04, R05.

**Edit:** existing `RecommendationEngine`, `KPISnapshot`, rule persistence; S4 source/calculation adapters; Facilitator orchestration. **NEW:** Facilitator `finance_snapshot_service.py`; Productivity `tools_recommendations.py`; internal operation `EVALUATE_VERIFIED_KPI_SNAPSHOT` and read operation `LIST_RECOMMENDATIONS`.

1. Load approved/effective rules and KPI definitions from the business repository. Empty rule list means no evaluation. Remove automatic fallback to active seed rules. Existing AED thresholds/company scope are examples until I03 establishes approval.
2. Build an authenticated S4 -> snapshot adapter. Map each KPI to the exact existing calculation field(s), business definition, currency, scope, measurement date, completeness and source record hash. For AR overdue beyond 90 days, verify the approved definition against aging bucket boundaries; do not feed total receivables merely because the KPI code says RECEIVABLES. Retain credit/sign policy. Do not enable budget recommendations while the code still reports unapproved mapping.
3. Orchestration calls the S4 tool with authorized scope and persists a snapshot/evidence record. The internal snapshot endpoint accepts only a verified workload with matching source/evidence permissions; the user-facing request cannot choose arbitrary input values or mark their completeness trusted.
4. Produce observation, business implication, suggested action, category, severity, priority, rule/version and supporting claims. Restrict category to `RISK`, `OPPORTUNITY`, `RECOMMENDATION`, `BENCHMARK`; no benchmark without W14 comparable data. Avoid the current hardcoded “Risk threshold breach” impact for every category.
5. Evaluate confidence with W01, including freshness and complete extraction. Distinguish underlying observed balance confidence from the confidence in a proposed action. Reject nonfinite values, incompatible units/currencies, invalid effective dates and unsupported scopes.
6. Persist continuing-breach updates, recovery, episode and cooldown transitions before returning them. Test all supported comparators, including OUTSIDE_RANGE recovery. Notification destinations must come from the authorized subscription/policy, never `_enqueue_notification` defaults.
7. Add a scheduled scan phase separate from outbox dispatch. Deduplicate by approved rule/version/scope/period/episode and keep evidence for every evaluated snapshot, including no recommendation. Do not execute proposed SAP business actions; these use cases are read/decision support.

**Acceptance T08:** fixture S4 records produce independently calculated snapshot and categorized recommendation; source outage/partial data/unapproved mapping cannot trigger a confident complete recommendation; complete new breach emits one alert; continued breach emits no duplicate; recovery survives restart; expired rule does not run; empty approved rules yields no defaults; authorized live AR/AP result reconciles to the same source scope/currency/as-of.

### W09 — Implement per-recommendation feedback

**Dependencies:** W03, W04, W08. **Requirements:** R04.

**NEW:** Productivity `feedback_service.py`, `test/test_recommendation_feedback.py`; operation `RECORD_RECOMMENDATION_FEEDBACK`. **Reuse:** local `cre2f_recommendationfeedback` fields after actual metadata validation.

1. Add useful/not-useful and optional reason/comment controls for every alert/recommendation. Acknowledging/dismissing is a separate lifecycle action, not automatically useful/not-useful feedback.
2. Request includes recommendation ID/version, useful boolean, allowlisted feedback type, bounded comment and idempotency ID. Derive reviewer/tenant from authenticated context. Reject nonvisible recommendations and cross-tenant references.
3. Persist feedback, recommendation version, actor/time, correlation and audit reference; verify readback before confirming save. Handle duplicate clicks deterministically. If edits are permitted, version feedback events; do not silently overwrite audit history.
4. Return updated feedback state to the card. If persistence fails, show unsaved/retry status. Do not change original recommendation evidence or score.
5. Provide aggregate usefulness counts by rule/version for review, subject to access policy. Store feedback for later improvement. Do not automatically retrain models or alter thresholds/weights: the minutes place that goal in the longer term. Proposed policy changes need versioned review/approval.

**Acceptance T09:** useful and not-useful each persist against the right recommendation; duplicate click creates one logical feedback; a second user cannot impersonate reviewer or access another tenant; outage never reports saved; feedback leaves original decision/evidence immutable; card reflects readback state.

### W10 — Implement bounded institutional memory for vendor history

**Dependencies:** W01, W03, W04; I04/I07 for history. **Requirements:** R08.

**Edit:** Facilitator `tools.py` memory stubs; reuse repository, not its global JSONL list. **NEW:** Facilitator `institutional_memory.py`, `test/test_institutional_memory.py`; operations `INGEST_INSTITUTIONAL_RECORD` and `GET_VENDOR_HISTORY`.

1. Keep user conversation memory separate from approved institutional facts. Do not reinterpret prior model text as vendor-performance truth. Reuse useful partition/summary patterns from SF `MemoryService` without inheriting its fixed 30-day horizon for enterprise history.
2. Define vendor-history record with actual canonical vendor ID, legal entity/subsidiary, contract/project reference, performance period, metric/event definition, value/severity, source record/URL/hash, owner, approval/verification status, access scope, retention and provenance. Add missing schema fields through W03 migrations; do not assume `institutionalrecord.summary` is a structured performance table.
3. Provide explicit authorized ingestion from actual available source records. For historical import, preserve original event date separately from ingestion date, deduplicate source/version, validate schema, log rejected rows and require access/retention policy. If no history predating activation exists, say so; never fill years with sample facts.
4. Retrieve by verified vendor identity and authorized entity scope. Similar vendor names require a confirmed mapping; do not merge suppliers or subsidiaries automatically. Filter before retrieval/result assembly, and invalidate/recheck cached access after role changes.
5. Return bounded relevant events with original evidence, temporal coverage, gaps and conflicting records. Absence of a complaint is not a clean performance record. Stale/superseded facts are visible as such and excluded where policy requires.
6. Treat embedded record/email/document instructions as untrusted text. Retrieved content cannot alter evaluation weights, grant access, send messages or become a tool instruction. Escape rendered content and record why a memory item was selected using source fields and match rules.

**Acceptance T10:** actual imported record retains original date/hash/source; duplicate import is idempotent; same-name vendors stay separate; another subsidiary's restricted records never appear; empty history is explicit; later permission revocation takes effect; prompt-injection text cannot modify the evaluation policy.

### W11 — Implement the combined vendor decision demonstration

**Dependencies:** W01, W03, W04, W10; I04. **Requirements:** R05, R06, R08; audit export follows in W12.

**NEW:** Facilitator `decision_service.py`, `vendor_evaluation.py`, `test/test_vendor_evaluation.py`; operation `EVALUATE_VENDOR_OPTIONS`. **Reuse:** `cre2f_decisionevidence`; use `cre2f_proposalevaluation` only if its verified schema fits, otherwise extend/create a dedicated versioned decision aggregate through W03. Its current investment fields are not a ready vendor scorecard.

1. Accept approved evaluation policy ID/version plus authorized candidate/source references. Load weights, criteria, units, higher/lower-is-better direction, mandatory eligibility checks, normalization, commercial comparability basis, minimum coverage and tie policy from the approved policy. Do not let arbitrary prompt text overwrite approved weightings.
2. Resolve current technical/commercial evidence and permitted historical performance via W10. SAP payables can establish financial obligations; they cannot establish supplier technical competence or delivery performance without a supported data source.
3. Validate comparable scope/currency/tax/term/period before scoring price. No implicit currency conversion or “cheapest is best.” Missing mandatory data produces `CONFIGURATION_REQUIRED`/`INSUFFICIENT_EVIDENCE` and no winner; use a separately labeled incomplete evaluation for review.
4. Compute deterministic criterion scores and weighted contributions in Decimal. For normalized 0–100 criteria with weights summing 1, final score is the sum of contributions. The approved policy defines how history enters; never secretly add an arbitrary penalty. Snapshot all inputs and policy versions.
5. Produce baseline current-evidence evaluation and history-informed evaluation using the SAME approved comparison method. If history is an extra factor, the policy must define the baseline treatment explicitly; do not silently renormalize weights. Show contribution deltas, rank changes or unchanged ranking and why. Do not force a winner flip for demonstration.
6. Persist the decision/version with alternatives, facts, claims, confidence, evidence IDs and a concise explanation: criteria favoring each option, decisive differences, material limitations, history influence and what missing evidence could change the result. This is auditable rationale, not hidden model reasoning.
7. Output one card-ready `DecisionRecord` with main recommendation, per-claim confidence, source links/references, expandable criteria/contributions/history and export action. Re-querying a historical decision displays its saved version; a new evaluation creates a new version and does not overwrite the original.

**Acceptance T11:** independent hand calculation matches score/contributions; all equal candidates obey tie policy; missing critical technical/commercial evidence prevents winner; approved history influence produces exactly the calculated delta; irrelevant history contributes zero; text/card uses same saved result; a historical decision can be reconstructed without fresh LLM evaluation. Use synthetic named test fixtures offline; use only approved real vendor data in the live demonstration.

### W12 — Make the decision trail exportable and tamper evident

**Dependencies:** W03, W04, W11; I06/I07 for platform proof. **Requirements:** R07.

**NEW:** Facilitator `decision_audit.py`, `audit_export.py`, `test/test_decision_audit_export.py`; operation `EXPORT_DECISION_TRAIL`; additive evidence retention/signing infrastructure under deployment migrations/templates.

1. Assemble decision/claim/evidence/identity/rationale/policy/code-version records into a decision manifest. Store original approved inputs or access-controlled snapshots sufficient to reconstruct the calculations; hashes and summaries alone cannot reconstruct missing inputs. Keep confidential source content in restricted evidence storage and only safe references/summaries in general audit logs.
2. Record actor and workload identities distinctly, authorization scope/policy, tools called, statuses, timestamps, correlation, claim-to-source mappings, input snapshots, formulas/weights, intermediate contributions, final result, confidence factors, feedback linkage and actual provider receipts if any.
3. Canonicalize each immutable record and compute SHA-256; include manifest record counts/IDs and signed root hash. Keep signing keys outside the application data store and record key ID/algorithm/version; use a standard platform signing service/library. Anchor manifests in retention-protected storage with access separation. A checksum stored next to an editable row is not sufficient tamper resistance.
4. Use append-only evidence events and superseding corrections. Make the application's role unable to update/delete finalized evidence; reviewers receive read/export permissions only as authorized. Document administrator/retention limitations honestly. Never claim “cannot ever be deleted” solely from an app role without delete privileges.
5. Implement export as an authorized, bounded job returning protected artifact reference/status. Produce machine-readable JSON + manifest and a readable CSV/XLSX view. JSON is authoritative for exact numeric values and nested evidence; spreadsheet cells must be protected against formula injection. Do not place private exports in public docs/Pages or return permanent unrestricted links.
6. Implement a standalone verifier: hashes/signature, expected record membership/count, source-reference closure, decision formulas/contributions, actor and policy references. Verification reports unresolved evidence/authorization without inventing content. Distinguish modified/missing records from an authorized redacted export whose redactions are declared.
7. If Purview export/integration is chosen, implement and verify its supported ingestion contract separately. The minutes allow Excel or another platform; do not call a CSV “Purview integrated.” Store the selected target and actual evidence in the input register.
8. Demonstrate live prevention with an authorized test record and actual app-role update/delete denial, plus offline tamper detection by editing/deleting/reordering exported copies. Preserve original evidence. Do not run destructive production tampering as a test.

**Acceptance T12:** auditor export reconstructs W11 decision from saved data; same inputs give same deterministic result; changed contribution/removed record/bad signature is detected; app role cannot update/delete final test evidence; unauthorized actor cannot export; logging outage cannot authorize governed mutation; evidence artifact links are restricted and expired access is denied.

### W13 — Implement meeting actions and automatic deadline follow-up

**Dependencies:** W03–W05, W07, W10; I08. **Requirements:** R09, R10.

**Edit:** Facilitator `process_calendar_meeting_workflow` and summary tools; Productivity Graph reads/Planner writes. **NEW:** Productivity `meeting_actions.py`, `test/test_meeting_actions.py`; operations `GET_MEETING_ACTION_TRACKER`, `PREPARE_MEETING_ACTIONS`, `CREATE_APPROVED_MEETING_ACTIONS`.

1. First establish the actual Teams notes/transcript source and meeting-ID mapping. The inspected Facilitator workflow is a stub despite the minutes describing a demonstration. Do not assume calendar event ID equals onlineMeeting ID. Validate actual Graph permissions, tenant transcript settings and available transcript/notes content.
2. Retrieve available authorized transcript/notes, preserving meeting ID, source/version and excerpt/timestamp references. Extract proposed action/title, named owner evidence, deadline evidence and originating decision. Missing owner/date remains `UNASSIGNED`/`DATE_REQUIRED`; never invent names or dates.
3. Resolve named owners to actual directory object IDs with ambiguous matches requiring review. Validate Planner plan/bucket membership and write permission. Prepare a preview of action list before creating/updating tasks through W04. Keep proposal extraction separate from task commitment.
4. Persist `meetingId + sourceVersion + extractedActionId` to actual Planner task ID, owner/due/status, evidence and audit IDs. Add a dedicated mapping entity through W03 if the existing institutional record's text action list cannot support this relationship.
5. Show a live tracker from provider reads with title, named owner, absolute due date/timezone, current percentComplete/status, overdue calculation, source meeting and real task reference. Include last successful refresh and stale/outage status. Do not use a static HTML mockup as proof.
6. Add reminder subscriptions to W07 using approved rules for due-soon/overdue, cadence, recipients and escalation. Re-read task status/due date before sending; suppress completed, reassigned or canceled tasks. Deduplicate `(taskId, policyVersion, deadlineVersion, reminderWindow, recipient)` and record provider acceptance.
7. Handle task concurrent changes using actual provider concurrency contract; do not overwrite an owner's update with stale extraction. Retries cannot create duplicate Planner tasks. Store human corrections as new versions.
8. Produce an in-person meeting roadmap with capture/transcription source, consent/access requirements, owner/date resolution, review, task linking and follow-up flow. Label unsupported capture distinctly; do not present it as complete Phase 1.

**Acceptance T13:** real notes produce reviewable actions with cited owner/date evidence; absent owner/date blocks commitment only for that action; approval creates one actual task; tracker reflects provider owner/date/completion changes; automatic reminder follows configured deadline rule; completed task gets no reminder; transcript denied/absent reports unavailable rather than fabricated minutes.

### W14 — Implement peer benchmarking only with a defined comparison contract

**Dependencies:** W01, W03, W04; I05. **Requirements:** R04, R05, R11.

**NEW:** Facilitator `benchmark_service.py`, `test/test_benchmark_service.py`; operation `GET_PEER_BENCHMARK`. **Reuse:** `cre2f_peerbenchmark` after schema validation/extension.

1. Register approved cohort, metric definition/version, peer membership, observation period, unit/currency, normalization basis, permitted sources/licensing, refresh SLA, minimum sample size and owner. Keep disabled if scope/data-source approval is absent.
2. Implement only the actual approved provider/import adapter; no hardcoded peer industry numbers, scraped arbitrary averages or LLM-estimated competitor facts. Imported evidence must identify provider document/data version and the authorized usage.
3. Compare internal KPI from verified S4/source contract with peer observations only after metric/period/unit/definition checks. Return `NOT_COMPARABLE` when mismatched; disclose known adjustments with formula/source. Do not silently treat subsidiary and consolidated values as peers.
4. Calculate sample size, median/quartiles and internal delta with an explicit versioned quantile convention. If provider supplies aggregate quartiles, preserve them as provider statistics rather than recomputing nonexistent raw observations. Percent delta is null with explanation when baseline is zero; no divide-by-zero substitution.
5. Produce BENCHMARK claims and conservative comparability-aware confidence. Identify whether an observed difference supports an opportunity/risk or is simply a comparison; do not invent causal explanations.
6. If I05 remains pending, deliver the tested disabled adapter interface/configuration screen and a concrete missing-input status for the September review. Do not mark live benchmarking complete.

**Acceptance T14:** known fixture statistics match chosen quantile method; mixed period/unit/definition blocks comparison; zero baseline handled; stale data lowers confidence; small cohort obeys minimum policy; missing licensed source returns configuration/unavailable; live result cites approved source/version.

### W15 — Wire tools, connectors and executive UI without losing evidence

**Dependencies:** corresponding completed feature packages W01–W14. **Requirements:** R01–R09, R11.

**Edit:** Productivity `server.py`, models, `productivity-connector-swagger.json`, child `agent/appPackage/productivity-plugin.json` and `instruction.txt`; Facilitator `TOOL_SPECS`/server/connector generation; actual parent export identified in W00; Card service registry, evaluator, fallback generator, sanitizer, server and templates.

1. Register each new operation from the registry below in its owning service only after handler/tests exist. Define request/response schemas including evidence and error statuses; do not keep an untyped `{}` response hiding claim metadata. Add authentication declarations consistent with actual runtime/connector configuration and tests.
2. Make the source of connector truth explicit. The generator currently covers selected specs; do not assume it creates Productivity's connector. Either extend generation with tested mapping or maintain the existing source file deliberately. Compare generated spec -> runtime routes -> plugin declarations -> parent tool references.
3. Add **NEW** Card templates `executive-attention-card.json`, `executive-briefing-card.json`, `recommendation-card.json`, `vendor-decision-card.json`, `meeting-actions-card.json`, `benchmark-card.json` under the existing Card `src/templates` directory. Use existing registry loading, but change `/templates` discovery to report actual registered templates. Ensure templates copy into the built image.
4. Show score/category/confidence on each material item; group sources and expandable recorded rationale/history on the decision screen. UI displays unknown/unavailable explicitly. “Why” expands saved factors/contributions, not live-generated hidden reasoning. Export button uses W12; feedback buttons use W09; write controls use W04.
5. Bind actions to server-side resource version and verified identity. A valid Card signature does not authorize changing a foreign recommendation, recipient or decision. Handle stale card/expired approval with refresh/re-preview.
6. Preserve existing 15KB Card validation budget and host compatibility tests. Bound content, paginate or fetch protected detail on demand. Update Markdown fallback to show the same material facts, confidence, sources, limitations and action availability. Never silently discard low-confidence caveats to fit a card.
7. Update agent instructions to route triage to scored attention, briefs to the correct composition, finance to S4, vendor/benchmark/memory to Facilitator and delivery to governed Productivity. Require rendered values to use structured results. Remove claims for unavailable features and avoid broadening to unsupported sources by prompt.
8. Validate the actual published execution surface after authorized import/publication: Teams or Copilot user session with real tool invocation and source data. JSON screenshots alone do not prove buttons, sources, identity or export work.

**Acceptance T15:** discovery lists only implemented exposed tools; end-to-end route preserves sources/confidence/rationale/correlation; actual card expands and exports; feedback persists; another user's action is denied; Markdown fallback retains material limitations; package/connector import validates without missing operations; live channel renders under retained size/version constraints.

### W16 — Verify, package and demonstrate completion honestly

**Dependencies:** all in-scope packages; unresolved business/tenant gates remain explicit. **Requirements:** all.

1. Run affected service suites after each package and full retained-scope integration/regression before release. Fix tests that currently assert sample approvals, fixed business figures or simulated delivery; replace them with real behavioral invariants and isolated provider fixtures. Do not reduce required assertions merely to obtain green results.
2. Fix the evaluation pipeline's mandatory-stage handling: missing/failed/timed-out/malformed required stage means INCOMPLETE and `passed=false`; advisory partial score can remain separate. Verify the orchestrator and actual caller use the gate. Add fail-path tests.
3. Produce clean reproducible packages/images from explicit allowlists. Inspect expanded archives and image contexts for secrets/environment files. The current builder's allowlist is not proof that older archives are clean. Do not print secrets in evidence. If an actual credential exposure is discovered, record affected artifact/key name and route remediation to the authorized owner; never silently distribute it.
4. Compile the touched Python/TypeScript and deployment definitions, verify container startup/imports/template availability, run relevant dependency/image scans against the final release, and attach actual results. No pinned patched versions are supplied here; verify current advisories and compatibility during implementation.
5. Correct deployment drift: actual workload identities, verified Dataverse auth/refresh, PostgreSQL/shared storage, job permissions, disabled mock paths, live-required receipt semantics, endpoint authentication and meaningful job failure status. Build configuration from one recorded release contract. Do not use `|| true` to report a failed provision/deploy as successful.
6. Collect authorized live evidence for the scenarios below. Record source revision plus working-tree manifest, image digest, solution/agent version, UTC/local timestamps, authenticated actor/scope, provider IDs, test assertions and artifacts. A `/health` response is service availability, not source/permission correctness.
7. Demonstrate recovery: source outage, audit outage, failed scheduler run, duplicate approval, worker restart, revoked subscription, evidence tamper copy and restricted-role delete attempt against test evidence. Ensure the UI reports real status throughout.
8. Package a concise runbook covering start/stop/subscription disable, policy changes, failed-run queue, unknown provider outcome reconciliation, rollback and evidence retrieval. Record owner role for every still-open input; do not assign named people based solely on attendance in the minutes.
9. Keep confidential evidence out of `/Users/vikrambala/copilotstudio/docs` while the Pages workflow publishes that whole directory. Use an access-controlled handoff repository/location. Do not publish or email any artifact without action-specific authorization.
10. Mark a requirement BUSINESS_ACCEPTED only when its tests, live evidence and relevant owner acceptance are linked. Explicitly report benchmark scope and in-person roadmap status. The handoff does not guarantee September deadlines; report dependency/scope risk without claiming missing work complete.

**Acceptance T16:** no failed/omitted mandatory test can pass release; final artifact matches test/source/image identities; complete scenario pack with real evidence; remaining blocked features plainly visible; no runtime test fixtures or fabricated receipts in live results.

## 7. NEW operation registry and service routing

These names are proposed additions, not existing tool names. Implement one canonical operation with explicit aliases only for verified compatibility. Interactive operations carry verified user context; internal snapshot operations carry scoped workload context. Export/ingest/feedback are authenticated stateful operations even where no external email is sent.

| Proposed operation | Owner / proposed handler module | Input | Output / permission |
|---|---|---|---|
| GET_EXECUTIVE_ATTENTION | Productivity / triage_engine + read wrapper | lookback/window, maximum items, policy ID | ranked AttentionItems; authorized executive sources only |
| GET_PRE_MEETING_BRIEF | Productivity / briefing_service | event ID or remaining-today selection, subscription/policy ID | evidence brief, no send |
| GET_END_OF_DAY_DIGEST | Productivity / briefing_service | local date/timezone, policy ID | evidence digest, no send |
| PREPARE_AUTOMATION_SUBSCRIPTION | Productivity / subscription_service | proposed bounded subscription | preview + approval ID; no activation |
| CONFIRM_AUTOMATION_SUBSCRIPTION | Productivity / subscription_service | approval token/ID | approved policy version; enable only as explicitly previewed |
| REVOKE_AUTOMATION_SUBSCRIPTION | Productivity / subscription_service | subscription ID/version | revoked; owner/admin only, auditable/idempotent |
| EVALUATE_VERIFIED_KPI_SNAPSHOT | Productivity / tools_recommendations | trusted persisted snapshot/evidence IDs | recommendations; workload-only, cannot trust user KPI values |
| LIST_RECOMMENDATIONS | Productivity / tools_recommendations | authorized filters/paging | recommendation records with evidence and feedback state |
| RECORD_RECOMMENDATION_FEEDBACK | Productivity / feedback_service | recommendation ID/version, useful, reason, idempotency key | saved feedback ID/status; authenticated visible-resource owner/reviewer |
| INGEST_INSTITUTIONAL_RECORD | Facilitator / institutional_memory | approved source/import reference, record schema | persisted evidence/history ID; authorized ingestor |
| GET_VENDOR_HISTORY | Facilitator / institutional_memory | canonical vendor ID and permitted scope/period | evidence-bearing history and gaps |
| EVALUATE_VENDOR_OPTIONS | Facilitator / decision_service | candidate/source IDs, approved policy version | saved DecisionRecord; scoped user permission |
| EXPORT_DECISION_TRAIL | Facilitator / audit_export | decision ID/version, format | protected export job/artifact; auditor/authorized reader |
| GET_MEETING_ACTION_TRACKER | Productivity / meeting_actions | meeting or authorized tracker scope | provider-refreshed owner/due/status rows |
| PREPARE_MEETING_ACTIONS | Productivity / meeting_actions | meeting source/version + extracted proposals | reviewable list; no task creation |
| CREATE_APPROVED_MEETING_ACTIONS | Productivity / meeting_actions | approved preview/token | provider task IDs and mapping evidence |
| GET_PEER_BENCHMARK | Facilitator / benchmark_service | approved cohort/metric/period | comparable benchmark or explicit pending/incomparable result |

Extend the existing `GET_DAILY_EXECUTIVE_BRIEFING`, daily email prepare/send and Planner prepare/execute paths where applicable instead of exposing duplicate behaviors with inconsistent policy. All newly listed mutation requests use POST or the corresponding authenticated MCP action, never side-effecting GET.

## 8. Demonstration and acceptance run order

Use a dedicated authorized test mailbox/meeting/plan and approved finance/vendor scope. Never put real fixture-recipient defaults into production configuration.

| Demo | Exact demonstration | Evidence to retain | Pass boundary |
|---|---|---|---|
| D01 | Query live AR/AP, then a paraphrase for same snapshot/scope | raw protected source snapshot, calculation, claims/sources, UI output | same numeric result and evidence; claim confidence visible; no cross-currency addition |
| D02 | Ranked attention across normal/high-importance mail and meeting deadlines | source IDs, rubric/version, factor contributions, ordering | ranking is contextual and reproducible; unknown factors explicit |
| D03 | Morning/pre-meeting/EOD; automatic authorized test run then disabled subscription | config approval, job/run ID, content hash, provider acceptance, independent receipt if claimed | one submission, correct local window, sources present; disabling preserves prior evidence |
| D04 | Approved finance breach then continuing/recovery; useful/not-useful feedback | rule/snapshot/episode/outbox/feedback records | categorized actionable insight; correct confidence; no duplicate alert; saved feedback |
| D05 | Vendor decision with current data, then same policy with approved history | candidate/criteria/weights, snapshots, contributions, score delta, card, decision versions | history influence shown truthfully; every material claim attributed/confidence assessed |
| D06 | Export D05 and independently verify; tampered copy; app-role deletion attempt on test evidence | export manifest/signature, verifier result, denied update/delete evidence | reconstructible original, tampered copy rejected, role restriction demonstrated |
| D07 | Teams note action -> approved task -> live tracker -> configured due reminder -> completion | transcript/notes refs, owner identity, task readback, reminder run, completion refresh | named owner/date reflect source/provider; no reminder after completion |
| D08 | Approved peer comparison, or explicit pending-scope walkthrough | approved metric/cohort/source and calculations, or I05 status | no invented benchmark; comparisons only when definitions are compatible |

For each demo add negative tests (403/unavailable/stale/partial) and the exact source/channel observations. Offline fixtures prove code behavior only; real provider demonstrations prove integration only for their actual exercised scope. Together with owner acceptance they support requirement completion.

## 9. Documentation constraints checked against primary sources

Verify these contracts again if the implementation date or provider API version changes. Do not extrapolate tenant permissions from generic API support.

- Graph sendMail returns empty `202 Accepted`; it does not establish completed delivery or supply a message item ID. Keep acceptance and delivery evidence separate. [Microsoft sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0).
- Use a time-bounded calendarView request for calendar occurrences in the intended window, and handle continuation as documented. [Microsoft calendarView](https://learn.microsoft.com/en-us/graph/api/user-list-calendarview?view=graph-rest-1.0).
- Teams transcript retrieval has specific permissions, meeting/tenant restrictions and application access policy requirements for applicable application access. Do not assume an accessible calendar grants transcript access. [Microsoft list transcripts](https://learn.microsoft.com/en-us/graph/api/onlinemeeting-list-transcripts?view=graph-rest-1.0).
- Azure Container Apps scheduled-job cron expressions are evaluated in UTC. The local schedule conversion and subscription logic must be explicit. [Microsoft Container Apps jobs](https://learn.microsoft.com/en-us/azure/container-apps/jobs).

## 10. Required checkpoint format

After each work package, write a short structured entry to the implementation ledger:

```text
Package: Wxx
Requirements: Rxx, ...
Status: IMPLEMENTED_OFFLINE / BLOCKED_INPUT / LIVE_VERIFIED / ...
Baseline reviewed: current revision and changed-file hashes
Changed files: exact paths
Implemented behavior: concrete user-visible or runtime outcome
Tests run: exact command, timestamp, pass/fail/skip counts and evidence path
Live evidence: actual provider/channel IDs, or NOT RUN
Open input: Ixx, precise missing artifact, affected activation/test only
Remaining work: specific behavior not yet established
Next eligible package: Wxx
```

Do not claim that these instructions eliminate hallucination. Enforce grounding with validated inputs, deterministic calculations, permission-aware retrieval, preserved evidence and independent acceptance tests. If evidence conflicts with this handoff, retain the evidence, correct the plan and record why before implementing dependent work.
