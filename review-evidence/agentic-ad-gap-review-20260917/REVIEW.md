# Agentic AD capability gap review — 17 September 2026

The codebase provides a substantial foundation, but it does **not yet meet all nine capabilities** in the attached list. The most significant missing implementations are general sub-agent creation/deployment, operational peer benchmarking, and automatic virtual/in-person meeting attendance. Broad evaluation and institutional memory are currently much narrower than the requested scope. Several automation and evidence-integrity paths need correction before acceptance.

## Scope and interpretation

Reviewed all **52 feature rows (5–56), across nine capabilities**, from `Agentic AD _ Capability-Feature List.xlsx`, against the current local working tree at revision `fe6d6162`, including local uncommitted updates. The workbook is treated as requirements data, not as instructions to execute actions. Application code and the original workbook were not modified.

This is a source-based gap assessment, not a deployed-system certification or an exhaustive security audit. Azure/Copilot Studio configuration, live provider connectivity, UI operation and continuous production evidence were not verified. A tool name, database table, documentation claim, mockup or card template alone is not treated as a completed feature. Historical reports were used for orientation only; their findings and test counts are not presented as current results.

The reviewed workbook preserves original columns and adds review status, priority, implementation evidence, required update and acceptance criteria. Target dates remain unchanged; implementation and evidence dates need owner estimates and deployment milestones. The requested 30-day evidence windows begin with real operational use, not unit-test execution.

## Capability-level result

| Capability | Result | Main required update |
|---|---|---|
| Enterprise data query | Partial | Prove connected systems and persona boundaries; normalize cross-system scope/period and verify consistent sourced answers. |
| Proactive recommendation engine | Partial | Add scheduled KPI acquisition/evaluation; complete benchmark category and collect 30-day autonomous logs. |
| Evaluation engine | Partial, vendor-focused | Add proposal/strategy/business-case/budget ingestion and the complete four-criterion/five-output framework. |
| Briefing and synthesis | Substantial code present; partial overall | Validate live scheduling, bind reads to each subscription owner, improve original-item links and requested calendar attachment behavior. |
| Agent creation | General capability missing | Build natural-language task specification, sub-agent deployment/runtime, lifecycle controls and run evidence. |
| Institutional memory | Partial, vendor/chat-focused | Index and retrieve executive meetings, emails, documents and decisions with original context and source permissions. |
| Meeting intelligence | Partial | Add automatic attendance/capture, complete minutes circulation and connect reminder generation to the worker. |
| Peer benchmarking | Storage/template foundation only | Integrate peer datasets; implement cohort/KPI normalization, comparisons, confidence and delivery. |
| Decision traceability | Partial | Cover all decision types, bind authenticated identity, show expandable explanation and enforce independent audit integrity. |

## Priority corrections verified in current code

1. **P0 — Facilitator identity and access are not consistently bound at dispatch.** The REST handler authenticates, then forwards request arguments to handlers without replacing tenant, role, entity-scope and actor fields with verified values. Vendor history accepts caller roles/scopes, and audit export defaults missing roles to AUDITOR. Derive these values server-side for REST and MCP; remove privileged defaults and test cross-tenant/cross-role denials. References: `ask-facilitator/facilitator_mcp/server.py:128–192`, `tools.py:492–577`. This is a source-confirmed boundary concern; no live exploit was attempted.
2. **P0 — Evaluation provenance and confidence can overstate supplied evidence.** `decision_service.py:172–211` creates fallback document references from vendor IDs; `:309–350` assigns HIGH / AUTHORITATIVE / VERIFIED to supplied scores and prices. These values are not evidence of a fetched, verified original. Require real document/snapshot references, label user assertions accurately and derive confidence from evidence quality.
3. **P0 — Signed logs are not yet tamper-proof.** `decision_audit.py:32,113` retains a known fallback signing key. Evidence mutation controls in `business_repository.py` are application-level SQLite guards; no immutable retention policy was found in the reviewed storage deployment definition. Require managed signing keys, fail-closed configuration, independent retention/access enforcement and verification of deletion/alteration resistance. Hashes alone are insufficient.
4. **P1 — Autonomous recommendations lack a wired scheduled scan.** `worker.py:192` reconciles and sends the outbox, then generates briefing subscriptions. It does not call KPI acquisition or `scan_and_evaluate_snapshots` (`recommendation_engine.py:1391`). Add provider refresh → validated snapshot → rule evaluation → durable alert → receipt, all under one scheduled execution trace.
5. **P1 — Meeting reminders are not dispatched by the worker.** `schedule_engine.py` recognizes ACTION_REMINDER and `meeting_actions.py:794` builds reminders, but `worker.py:120–148` supports only morning/pre-meeting/EOD and rejects other kinds. Connect reminders to the durable outbox with completion rechecks and scoped recipients.
6. **P1 — Scheduled briefing reads can use the wrong executive mailbox.** `run_worker_pass` constructs one Microsoft365Client using its `user_email`, then reuses it for every subscription. Passing `sub.mailbox` into the briefing formatter does not recreate the provider client. Construct a client from each authorized subscription identity; test two executives with disjoint mail/calendar content and verify no cross-user leakage.
7. **P1 — Benchmark recommendations are intentionally suppressed.** `recommendation_engine.py:1162` skips BENCHMARK. A peer schema and card exist, but source acquisition, comparable cohorts and executable comparison/delivery tools were not found. Keep the suppression until real comparability is implemented.
8. **P1 — Expandable explanation is not wired in the provided decision card.** `adaptive-cards/decision-trace.json` contains metadata but no expansion action or displayed rationale/confidence. Connect it to the stored decision record and render criteria, calculations, sources, caveats and concise rationale. The requirement can be met with an auditable explanation; it does not require disclosure of private model chain of thought.

Recent improvements are present: Facilitator now includes its Productivity dependency folder in the Dockerfile; Productivity declares the PostgreSQL driver; the worker now claims subscription runs before sending, checks supported channels and propagates the live-delivery flag. These earlier review concerns should not simply be repeated as unfixed. Their end-to-end production behavior still needs validation. The business-record repository factory still selects SQLite, so do not assume the PostgreSQL operations/outbox migration also covers institutional records and decisions.

## Suggested update sequence and completion evidence

| Order | Work package / suggested owner | Completion criteria |
|---|---|---|
| 1 | Identity, evidence truthfulness and immutable audit — platform/security + backend | Verified identity controls every decision/export; no fabricated sources or confidence; key/retention configuration fails closed; negative authorization and tamper tests pass. |
| 2 | Finish existing automation — M365/backend | Per-executive provider clients, KPI scan scheduler, meeting-reminder dispatch, reliable receipts and restart recovery; real scheduled brief/alert samples. |
| 3 | Connected-query acceptance — integration/data owners | Entity-by-system security matrix; sourced cross-system question; fixed-snapshot paraphrase checks; access logs with one correlation ID. |
| 4 | General evaluation + memory — business policy/data/backend | Ingest all required evaluation document classes; approved strategic/fiscal/peer/history criteria; complete output schema; permission-aware historical retrieval. |
| 5 | Peer benchmarking — data owner + analytics/backend | Approved domestic/international source inventory; matched definitions, units, currency, period and cohort; consistent comparisons and visible confidence. |
| 6 | Sub-agent creation — agent-platform/product | Natural-language request creates a governed deployed sub-agent; edit/pause/resume/retire works; scheduled and triggered runs are logged. |
| 7 | Meeting capture and completion — collaboration integration/product | Virtual and in-person capture paths; accurate minutes circulated with named owners/deadlines; unified tracker and reminders stop on closure. |
| 8 | Executive presentation + evidence pack — UI/QA/program owner | Source/confidence/expandable rationale visible in actual client; demonstrations, exports and real 30-day recommendation/evaluation logs assembled. |

Start the 30-day recommendation/evaluation evidence collection as soon as the corresponding corrected live paths are deployed, while the remaining capability work proceeds. Assign an implementation owner, acceptance owner, dependency and target date to each work package. Do not populate dates from the document as commitments where none were provided.

## Verification performed and limits

- Read the original workbook and matched every feature row to source-based evidence and an explicit acceptance criterion.
- Inspected executable service handlers, worker paths, storage/contracts, policy calculations, identity flow, packaged agent instructions and card definitions. Searched authored application code for benchmarking, sub-agent lifecycle, attendance and automated ingestion paths.
- Static AST checks confirm the current worker has no calls to KPI scan or meeting reminder evaluation. JSON inspection confirms the provided decision card has no actions. All matrix source references were checked for existing files and valid line numbers. Source hashes are retained for the cited files.
- Attempted the existing isolated schedule test runner with network blocked and provider credentials removed; collection could not start because the bundled runtime lacks `pydantic_settings`. **No fresh passing-test count is claimed.** The review did not install dependencies, send mail, query live providers, deploy services or alter application source.
- Workbook output was reopened to verify 52 annotated feature rows and unchanged original cell values. See `validation.json` and `source-hashes.json` for review evidence.

## Detailed feature matrix

Statuses: **Present - validate** = core path found, live acceptance outstanding; **Partial** = material requirement gaps; **Missing** = required executable path not found in reviewed source. These are not percentage-complete estimates.

### Row 5 — ENTERPRISE DATA QUERY / Connection to enterprise systems

**Partial · P1**

Existing: S/4HANA, SuccessFactors, SAC and M365 adapters.

Update: Confirm entity-specific systems and DMS/data-lake coverage; do not equate configured plugins with verified connections.

Acceptance: Authenticated system inventory, ownership/security matrix and a sourced cross-system demo.

Evidence: [mcp-apps/ask-s4hana/s4hana_mcp/tools.py:283](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/tools.py:283); [mcp-apps/ask-sac/sac_mcp/client.py:1](/Users/vikrambala/copilotstudio/mcp-apps/ask-sac/sac_mcp/client.py:1); [mcp-apps/ask-productivity/productivity_mcp/m365_client.py:1](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:1)

### Row 6 — ENTERPRISE DATA QUERY / Natural language querying

**Partial · P1**

Existing: Agent instructions route natural language to registered business tools.

Update: Add repeatable intent-to-query checks, permission tests and consolidated answers across adapters.

Acceptance: Paraphrased executive questions return the correct scoped query, values, period and sources.

Evidence: [mcp-apps/ask-successfactors/agent/appPackage/instruction.txt:2](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/agent/appPackage/instruction.txt:2); [mcp-apps/ask-productivity/productivity_mcp/server.py:1](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/server.py:1)

### Row 7 — ENTERPRISE DATA QUERY / Cross system querying

**Partial · P1**

Existing: Multiple plugins are packaged in the executive agent.

Update: Verify joins and consistent entity, period, currency and authorization across systems; no general cross-system query coordinator established.

Acceptance: Demonstrate budget versus actual by division using actual source calls and one correlation trace.

Evidence: [mcp-apps/ask-successfactors/agent/appPackage/declarativeAgent.json:1](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/agent/appPackage/declarativeAgent.json:1); [mcp-apps/ask-successfactors/agent/appPackage/instruction.txt:7](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/agent/appPackage/instruction.txt:7)

### Row 8 — ENTERPRISE DATA QUERY / Source transparency

**Partial · P0**

Existing: M365 evidence envelopes and source instructions exist.

Update: Require verified claim-level sources throughout; evaluation generates fallback document IDs without fetching proof.

Acceptance: Every material fact links to a real source/snapshot; absent evidence is explicitly unverified.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/evidence_contracts.py:87](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/evidence_contracts.py:87); [mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py:172](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py:172)

### Row 9 — ENTERPRISE DATA QUERY / Permissions / Access

**Partial · P0**

Existing: Verified identity, consent and role/scope mechanisms exist.

Update: Bind Facilitator tenant, actor, roles and scopes to verified identity; REST currently forwards body arguments to handlers.

Acceptance: Cross-role and cross-tenant negative tests fail closed through REST and MCP transports.

Evidence: [mcp-apps/ask-facilitator/facilitator_mcp/server.py:128](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/server.py:128); [mcp-apps/ask-facilitator/facilitator_mcp/tools.py:492](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:492); [mcp-apps/ask-facilitator/facilitator_mcp/tools.py:557](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:557)

### Row 10 — ENTERPRISE DATA QUERY / Output consistency

**Partial · P1**

Existing: Deterministic calculations and versioned rules exist.

Update: Add paraphrase regression tests with pinned source snapshots and reporting periods; changing live facts can legitimately change answers.

Acceptance: Same scope, period, source version and policy produce equal material facts across phrasings.

Evidence: [mcp-apps/ask-s4hana/s4hana_mcp/report_calculations.py:1](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/report_calculations.py:1); [mcp-apps/ask-facilitator/facilitator_mcp/vendor_evaluation.py:302](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/vendor_evaluation.py:302)

### Row 11 — ENTERPRISE DATA QUERY / Audit logs

**Partial · P1**

Existing: Dataverse audit clients and correlation fields exist.

Update: Verify durable read-call logging across SAP, SAC, M365 and consolidated requests; collect source-access exports.

Acceptance: Trace a cross-system request from user identity to each provider call and retained source snapshot.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/audit_client.py:1](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/audit_client.py:1); [mcp-apps/ask-productivity/productivity_mcp/tools_m365_reads.py:26](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/tools_m365_reads.py:26)

### Row 12 — PROACTIVE RECOMMENDATION ENGINE / Connection to internal and external data

**Partial · P1**

Existing: KPI snapshots, rules and scan helper exist.

Update: Wire scheduled source refresh into evaluation; worker only dispatches outbox and briefing subscriptions. Add approved external signals where required.

Acceptance: A scheduled run fetches fresh internal/external inputs and records evaluated sources without a user prompt.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/worker.py:192](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/worker.py:192); [mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py:1391](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py:1391)

### Row 13 — PROACTIVE RECOMMENDATION ENGINE / Automated recommendations

**Partial · P1**

Existing: Threshold rules generate recommendations from supplied snapshots.

Update: Schedule KPI acquisition and evaluation, not only notification dispatch.

Acceptance: A changed source KPI autonomously creates and delivers an alert; retain 30 consecutive days of real logs.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/tools_recommendations.py:66](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/tools_recommendations.py:66); [mcp-apps/ask-productivity/productivity_mcp/worker.py:192](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/worker.py:192)

### Row 14 — PROACTIVE RECOMMENDATION ENGINE / Recommendation categorizations

**Partial · P1**

Existing: Risk/opportunity categories supported.

Update: BENCHMARK rules are deliberately skipped until comparable data exists; constrain categories to agreed business taxonomy.

Acceptance: Risk, opportunity and benchmark scenarios produce correctly categorized sourced alerts.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py:1158](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py:1158)

### Row 15 — PROACTIVE RECOMMENDATION ENGINE / Notification mechanism

**Present - validate · P1**

Existing: Durable notification outbox and email dispatch are implemented.

Update: Prove scheduled delivery, correct recipient and recovery in the deployed environment; email meets one permitted channel.

Acceptance: Live alert email/feed plus provider receipt, deduplication and restart recovery evidence.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py:1411](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py:1411); [mcp-apps/ask-productivity/productivity_mcp/worker.py:192](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/worker.py:192)

### Row 16 — PROACTIVE RECOMMENDATION ENGINE / Feedback mechanism

**Present - validate · P2**

Existing: Per-alert useful/not useful feedback, type, identity and persistence logic.

Update: Verify executive UI wiring and evidence export.

Acceptance: Executive submits a rating; record remains associated with original alert, category and identity.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/feedback_service.py:96](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/feedback_service.py:96); [mcp-apps/ask-productivity/productivity_mcp/server.py:1](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/server.py:1)

### Row 17 — PROACTIVE RECOMMENDATION ENGINE / Source transparency

**Partial · P1**

Existing: Recommendations carry claims, sources and confidence.

Update: Verify source rendering and prevent unverified supplied snapshots being treated as provider evidence.

Acceptance: Alert displays original KPI source, reporting period, scope and freshness.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/tools_recommendations.py:66](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/tools_recommendations.py:66)

### Row 18 — PROACTIVE RECOMMENDATION ENGINE / Audit logs

**Partial · P1**

Existing: Recommendation/outbox history and subscription run records exist.

Update: Include scheduled scan executions, workload identity and fresh input lineage; export real autonomous history.

Acceptance: 30-day categorized recommendation log links source acquisition, evaluation and delivery timestamps.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py:930](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py:930); [mcp-apps/ask-productivity/productivity_mcp/subscription_service.py:424](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/subscription_service.py:424)

### Row 19 — EVALUATION ENGINE / Evaluation scope

**Partial · P1**

Existing: Structured vendor-option evaluation exists.

Update: Add document ingestion and evaluation for strategies, business cases, budget submissions and expenditure requests.

Acceptance: Evaluate representative documents from each requested class with linked extracted evidence.

Evidence: [mcp-apps/ask-facilitator/facilitator_mcp/vendor_evaluation.py:155](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/vendor_evaluation.py:155); [mcp-apps/ask-facilitator/facilitator_mcp/tools.py:509](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:509)

### Row 20 — EVALUATION ENGINE / Evaluation framework

**Partial · P1**

Existing: Approved vendor policy scores technical, commercial and historical performance.

Update: Add explicit strategic priorities, fiscal impact and comparable peer benchmarks across evaluation types.

Acceptance: Versioned framework covers all four criteria and records missing inputs explicitly.

Evidence: [mcp-apps/ask-facilitator/facilitator_mcp/vendor_evaluation.py:81](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/vendor_evaluation.py:81)

### Row 21 — EVALUATION ENGINE / Output structure

**Partial · P1**

Existing: Vendor rankings, weighted scores, claims and rationale are returned.

Update: Add complete alignment score, fiscal impact, comparable cases, risks and executive questions schema.

Acceptance: Every evaluation exposes all five required sections, using unavailable states where evidence is absent.

Evidence: [mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py:405](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py:405)

### Row 22 — EVALUATION ENGINE / Output consistency

**Partial · P1**

Existing: Deterministic vendor scoring and historical decision retrieval.

Update: Extend repeatability to broader evaluation scope and fixed evidence/policy versions.

Acceptance: Repeated and paraphrased evaluations of frozen inputs produce consistent scores and facts.

Evidence: [mcp-apps/ask-facilitator/facilitator_mcp/vendor_evaluation.py:302](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/vendor_evaluation.py:302); [mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py:549](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py:549)

### Row 23 — EVALUATION ENGINE / Confidence level

**Partial · P0**

Existing: Confidence framework and evaluation confidence fields exist.

Update: Remove automatic HIGH/VERIFIED assumptions for caller-supplied technical and commercial facts; verify display in executive UI.

Acceptance: Missing/unverified/stale inputs lower confidence; executive can inspect evidence-based reasons.

Evidence: [mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py:309](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py:309); [mcp-apps/ask-productivity/productivity_mcp/confidence_policy.py:44](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/confidence_policy.py:44)

### Row 24 — EVALUATION ENGINE / Audit logs

**Partial · P1**

Existing: Vendor decision persistence and signed export.

Update: Extend logs to all evaluation types and collect actual usage history.

Acceptance: 30-day evaluation log with repeated-case evidence, policy versions, input snapshots and outcomes.

Evidence: [mcp-apps/ask-facilitator/facilitator_mcp/decision_audit.py:152](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/decision_audit.py:152); [mcp-apps/ask-facilitator/facilitator_mcp/audit_export.py:465](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/audit_export.py:465)

### Row 25 — BRIEFING AND SYNTHESIS / Sync with Executive's emails and other platforms

**Partial · P1**

Existing: Calendar, mail, Teams, Planner and transcript read code.

Update: Verify per-executive mailbox binding and relevant file retrieval; instructions alone do not prove SharePoint/DMS integration.

Acceptance: Authenticated executive-specific calendar, inbox and file examples with permission-denial cases.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/m365_client.py:1](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:1); [mcp-apps/ask-successfactors/agent/appPackage/instruction.txt:35](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/agent/appPackage/instruction.txt:35)

### Row 26 — BRIEFING AND SYNTHESIS / Automated briefs

**Present - validate · P1**

Existing: Morning, pre-meeting, EOD synthesis and inbox triage; worker subscription dispatch.

Update: Validate configuration and deployed schedule, and resolve worker mailbox issue before multi-executive rollout.

Acceptance: Real pre-meeting and EOD artifacts are created automatically at configured times.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/briefing_service.py:48](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/briefing_service.py:48); [mcp-apps/ask-productivity/productivity_mcp/worker.py:37](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/worker.py:37)

### Row 27 — BRIEFING AND SYNTHESIS / Automated delivery of briefs

**Partial · P1**

Existing: Email briefs and configurable pre-meeting lead time.

Update: Calendar attachment/night-before invite workflow not found. EOD email is implemented but requires live acceptance.

Acceptance: Demonstrate requested invite attachment/night-before behavior or formally accept scheduled EOD email delivery.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/schedule_engine.py:149](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/schedule_engine.py:149); [mcp-apps/ask-productivity/productivity_mcp/worker.py:153](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/worker.py:153)

### Row 28 — BRIEFING AND SYNTHESIS / Source transparency

**Partial · P1**

Existing: Briefings contain source collections and attributed claims.

Update: Ensure links resolve to underlying emails/events/documents, not just generic Graph API collection endpoints.

Acceptance: Open underlying evidence from the executive briefing with the same access permissions.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/briefing_service.py:80](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/briefing_service.py:80)

### Row 29 — BRIEFING AND SYNTHESIS / Audit logs

**Present - validate · P1**

Existing: Subscription run history captures content hash, scheduled occurrence and provider receipt.

Update: Export real generation/delivery timing and distinguish provider acceptance from final inbox delivery.

Acceptance: Scheduled-versus-actual generation and delivery evidence for pre-meeting and EOD runs.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/worker.py:167](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/worker.py:167); [mcp-apps/ask-productivity/productivity_mcp/subscription_service.py:424](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/subscription_service.py:424)

### Row 30 — AGENT CREATION / Natural language interface

**Partial · P1**

Existing: Natural-language agent can expose fixed automation subscription tools.

Update: Add recurring-task interpretation into a validated executable sub-agent specification.

Acceptance: Executive describes a new recurring task and receives an editable agent specification.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/server.py:508](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/server.py:508); [mcp-apps/ask-productivity/productivity_mcp/evidence_contracts.py:44](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/evidence_contracts.py:44)

### Row 31 — AGENT CREATION / Sub-agent creation

**Missing · P1**

Existing: Fixed briefing subscriptions are a reusable foundation.

Update: No general build/deploy/maintain sub-agent runtime found; current executive instructions explicitly avoid child agents.

Acceptance: A natural-language request creates and deploys a versioned sub-agent without developer intervention.

Evidence: [mcp-apps/ask-successfactors/agent/appPackage/instruction.txt:2](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/agent/appPackage/instruction.txt:2); [mcp-apps/ask-productivity/productivity_mcp/subscription_service.py:80](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/subscription_service.py:80)

### Row 32 — AGENT CREATION / Autonomous working of sub-agent

**Partial · P1**

Existing: Worker runs predefined scheduled briefing kinds.

Update: Add generic sub-agent job execution and event triggers with scoped authorization, retries and telemetry.

Acceptance: Newly created agent completes a scheduled and an event-triggered run autonomously.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/worker.py:120](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/worker.py:120); [mcp-apps/ask-productivity/productivity_mcp/evidence_contracts.py:44](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/evidence_contracts.py:44)

### Row 33 — AGENT CREATION / Control over sub-agents' lifecycle

**Partial · P1**

Existing: Prepare/confirm/revoke subscription operations.

Update: Implement agent edit, pause, resume and retire UI/API plus versioned authorization changes.

Acceptance: Executive changes schedule/task, pauses it, resumes it and retires it; no runs occur while paused/retired.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/subscription_service.py:80](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/subscription_service.py:80); [mcp-apps/ask-productivity/productivity_mcp/subscription_service.py:228](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/subscription_service.py:228)

### Row 34 — AGENT CREATION / Audit logs

**Partial · P1**

Existing: Subscription records preserve authorization and configuration.

Update: Add actual sub-agent creation, deployment and lifecycle audit records.

Acceptance: Trace executive request to deployed agent ID, version and authorization.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/evidence_contracts.py:198](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/evidence_contracts.py:198); [mcp-apps/ask-productivity/productivity_mcp/subscription_service.py:80](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/subscription_service.py:80)

### Row 35 — AGENT CREATION / Sub-agent logs

**Partial · P1**

Existing: Subscription run history exists.

Update: Add sub-agent run inputs, outputs, success/failure and external action receipts.

Acceptance: Export successful and failed runs for an executive-created sub-agent.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/subscription_service.py:424](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/subscription_service.py:424)

### Row 36 — INSTITUTIONAL MEMORY / Memory build up

**Partial · P1**

Existing: Vendor institutional records and explicit chat JSONL ingestion.

Update: Add permission-aware ingestion/indexing of meetings, decisions, documents and email; no comprehensive indexer found.

Acceptance: New content becomes searchable with provenance, context and applicable retention/deletion controls.

Evidence: [mcp-apps/ask-facilitator/facilitator_mcp/institutional_memory.py:138](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/institutional_memory.py:138); [mcp-apps/ask-facilitator/facilitator_mcp/tools.py:191](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:191)

### Row 37 — INSTITUTIONAL MEMORY / Use of institutional memory

**Partial · P1**

Existing: Vendor history retrieval supports original evidence, time coverage and scope.

Update: Generalize retrieval to executive topics, participants, decisions and outcomes across all content types.

Acceptance: Historical query retrieves original participants, rationale, outcome and accessible supporting documents.

Evidence: [mcp-apps/ask-facilitator/facilitator_mcp/institutional_memory.py:347](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/institutional_memory.py:347)

### Row 38 — INSTITUTIONAL MEMORY / Source transparency

**Partial · P1**

Existing: Vendor records retain source_doc_ref and source hashes.

Update: Provide retrievable original documents for general memory and verify links/ACLs.

Acceptance: Executive opens authorized originals; revoked documents disappear from retrieval.

Evidence: [mcp-apps/ask-facilitator/facilitator_mcp/institutional_memory.py:138](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/institutional_memory.py:138)

### Row 39 — INSTITUTIONAL MEMORY / Audit logs

**Partial · P1**

Existing: Vendor decisions retain consulted institutional evidence.

Update: Log general memory retrieval IDs, versions and contribution to a concise decision rationale.

Acceptance: Export a trace showing which historical records informed the answer; no private internal chain of thought needed.

Evidence: [mcp-apps/ask-facilitator/facilitator_mcp/decision_audit.py:152](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/decision_audit.py:152); [mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py:213](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py:213)

### Row 40 — MEETING INTELLIGENCE / Meeting attendance (virtual)

**Missing · P1**

Existing: Existing transcript retrieval is available.

Update: No automatic virtual meeting join/attendance implementation found.

Acceptance: Meeting invite triggers permitted attendance and produces usable captured meeting evidence.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/m365_client.py:1317](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:1317)

### Row 41 — MEETING INTELLIGENCE / Meeting attendance (in-person)

**Missing · P1**

Existing: User-supplied transcript/notes path is available.

Update: No in-person audio capture, transcription or meeting participation integration found.

Acceptance: Approved in-person capture creates speaker-attributed transcript and traceable minutes.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/server.py:922](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/server.py:922); [mcp-apps/ask-productivity/productivity_mcp/meeting_actions.py:84](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/meeting_actions.py:84)

### Row 42 — MEETING INTELLIGENCE / Generates & circulates minutes

**Partial · P1**

Existing: Action extraction, owner resolution, approved Planner tasks and summary-email draft tools.

Update: Complete accurate minutes generation and circulation; Facilitator calendar workflow currently returns SOURCE_UNAVAILABLE.

Acceptance: Transcript/notes produce reviewed minutes, decisions, named owners and deadlines, then receipt-backed circulation.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/meeting_actions.py:84](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/meeting_actions.py:84); [mcp-apps/ask-facilitator/facilitator_mcp/tools.py:176](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:176); [mcp-apps/ask-facilitator/facilitator_mcp/tools.py:369](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:369)

### Row 43 — MEETING INTELLIGENCE / Autonomous follow up

**Partial · P1**

Existing: Reminder evaluator checks Planner status and due dates.

Update: Wire evaluator into scheduled dispatch; ACTION_REMINDER is schedulable but unsupported by worker dispatch switch.

Acceptance: Autonomous nudges occur before/after deadline, deduplicate and stop on completion.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/meeting_actions.py:794](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/meeting_actions.py:794); [mcp-apps/ask-productivity/productivity_mcp/schedule_engine.py:192](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/schedule_engine.py:192); [mcp-apps/ask-productivity/productivity_mcp/worker.py:140](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/worker.py:140)

### Row 44 — MEETING INTELLIGENCE / Live action tracker

**Present - validate · P1**

Existing: Live tracker reads mapped meeting actions and synchronizes Planner completion.

Update: Prove coverage of all in-scope meetings and correct access boundaries.

Acceptance: Tracker shows owners, deadlines, overdue state and provider-updated completion across meetings.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/meeting_actions.py:657](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/meeting_actions.py:657); [mcp-apps/ask-productivity/productivity_mcp/tools_m365_reads.py:1606](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/tools_m365_reads.py:1606)

### Row 45 — PEER BENCHMARKING / Internal and external data connectivity

**Missing · P1**

Existing: PeerBenchmarkRecord storage schema exists.

Update: No functioning peer-data acquisition/comparability service or external benchmark source integration found.

Acceptance: Integrated approved peer datasets with source inventory, dates, units and cohort definitions.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/business_repository.py:232](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/business_repository.py:232); [mcp-apps/ask-productivity/productivity_mcp/business_repository.py:1601](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/business_repository.py:1601)

### Row 46 — PEER BENCHMARKING / Comparison with peers

**Missing · P1**

Existing: Peer storage fields and card template exist.

Update: Build KPI/cohort selection, normalization and comparison calculation service.

Acceptance: Internal KPI compared with valid matched peer cohort and period; incomparable data rejected.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/business_repository.py:232](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/business_repository.py:232); [mcp-apps/ask-successfactors/agent/appPackage/adaptive-cards/peer-benchmark.json:1](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/agent/appPackage/adaptive-cards/peer-benchmark.json:1)

### Row 47 — PEER BENCHMARKING / Source transparency

**Partial · P1**

Existing: Benchmark datasource field and generic EvidenceSource contract.

Update: Populate verified per-datapoint peer provenance and render it.

Acceptance: Each internal/peer value exposes a retrievable source, period and transformation history.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/business_repository.py:232](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/business_repository.py:232); [mcp-apps/ask-productivity/productivity_mcp/evidence_contracts.py:87](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/evidence_contracts.py:87)

### Row 48 — PEER BENCHMARKING / Confidence level

**Partial · P1**

Existing: Reusable comparability-aware confidence framework.

Update: Apply it to real peer values; storage/template alone does not establish confidence.

Acceptance: Confidence reflects peer freshness, coverage and comparability with visible reasons.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/confidence_policy.py:44](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/confidence_policy.py:44)

### Row 49 — PEER BENCHMARKING / Delivery mode

**Missing · P1**

Existing: Generic worker/outbox could be reused.

Update: Add on-demand benchmark tool and/or scheduled benchmark service; benchmark recommendation branch currently skips execution.

Acceptance: A real on-demand or automatic benchmark request returns a sourced comparison.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py:1162](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py:1162)

### Row 50 — PEER BENCHMARKING / Output consistency

**Missing · P1**

Existing: Version field exists on benchmark storage.

Update: Build deterministic comparison over immutable KPI/peer snapshots and frozen definitions.

Acceptance: Same KPI, cohort, period and dataset version always produce identical comparison facts.

Evidence: [mcp-apps/ask-productivity/productivity_mcp/business_repository.py:232](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/business_repository.py:232)

### Row 51 — DECISION TRACEABILITY / Cross-capability application

**Partial · P1**

Existing: Vendor decision manifests and recommendation evidence contracts.

Update: Apply one trace/export contract across recommendations, general evaluations and peer benchmarking.

Acceptance: A sample from each capability can be reconstructed from an export.

Evidence: [mcp-apps/ask-facilitator/facilitator_mcp/decision_audit.py:152](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/decision_audit.py:152); [mcp-apps/ask-productivity/productivity_mcp/evidence_contracts.py:157](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/evidence_contracts.py:157)

### Row 52 — DECISION TRACEABILITY / Expandable reasoning chain

**Partial · P1**

Existing: Vendor concise rationale/calculation trace; decision card exists.

Update: Wire an expandable executive explanation panel; current decision card has only metadata and no expand action.

Acceptance: Executive expands Why this result to see criteria, calculations, evidence and limitations in plain language.

Evidence: [mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py:405](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py:405); [mcp-apps/ask-successfactors/agent/appPackage/adaptive-cards/decision-trace.json:1](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/agent/appPackage/adaptive-cards/decision-trace.json:1)

### Row 53 — DECISION TRACEABILITY / Source transparency

**Partial · P0**

Existing: Claim source references and decision manifests.

Update: Reject fabricated fallback document references; standardize source display across all decision-producing tools.

Acceptance: Every decision fact is traceable to an actual original or retained provider snapshot.

Evidence: [mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py:172](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py:172); [mcp-apps/ask-productivity/productivity_mcp/evidence_contracts.py:87](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/evidence_contracts.py:87)

### Row 54 — DECISION TRACEABILITY / Confidence level

**Partial · P0**

Existing: Versioned confidence model with source reliability/comparability factors.

Update: Evaluate confidence from evidence rather than unconditional HIGH/VERIFIED values, and show it per material point.

Acceptance: Missing, stale and incomparable evidence demonstrably changes displayed confidence.

Evidence: [mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py:309](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py:309); [mcp-apps/ask-productivity/productivity_mcp/confidence_policy.py:44](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/confidence_policy.py:44)

### Row 55 — DECISION TRACEABILITY / Audit trail and decision metadata

**Partial · P0**

Existing: Vendor manifests contain actor, policy, input snapshots, rationale and export.

Update: Bind actor/tenant/roles to verified identity; extend signed exports across capabilities with actual agent/model versions.

Acceptance: Auditor reconstructs identity, input versions, contributors, rationale and outcome without caller-controlled attribution.

Evidence: [mcp-apps/ask-facilitator/facilitator_mcp/server.py:182](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/server.py:182); [mcp-apps/ask-facilitator/facilitator_mcp/decision_audit.py:58](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/decision_audit.py:58); [mcp-apps/ask-facilitator/facilitator_mcp/audit_export.py:465](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/audit_export.py:465)

### Row 56 — DECISION TRACEABILITY / Integrity of audit logs

**Partial · P0**

Existing: Hash/signature verification and application-level mutation guards.

Update: Remove fallback signing secret; use managed key custody and independently enforced immutable retention. SQLite/application checks do not make logs tamper-proof.

Acceptance: Alteration/deletion attempts by app and storage administrators are prevented or independently detected; key rotation and retention verified.

Evidence: [mcp-apps/ask-facilitator/facilitator_mcp/decision_audit.py:32](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/decision_audit.py:32); [mcp-apps/ask-facilitator/facilitator_mcp/decision_audit.py:113](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/decision_audit.py:113); [mcp-apps/ask-productivity/productivity_mcp/business_repository.py:1760](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/business_repository.py:1760)

