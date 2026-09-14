# Velora Agentic AD — executable architecture handoff

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
