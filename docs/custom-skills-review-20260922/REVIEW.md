# Velora One: code review and custom skill pack

Reviewed 22 September 2026. Source baseline: `4e5ffd29`, branch `feat/sf-prod-integration`. The working tree was clean before this review.

## Recommendation

Build twelve narrowly scoped business skills around the existing Velora One services. Start with verified workforce, Emiratisation, current cash exposure, budget reporting, executive attention, and meeting preparation. Add writes, vendor decisions, and cross-system briefs after the relevant defects are resolved; enable recurring delivery and audit exports last.

The main work is precise orchestration, truthful source handling, consistent tool registration, and repairing specific execution paths. It is not installing generic skills or adding a second conversational agent. The current instruction file explicitly keeps Velora One responsible for direct tool use.

This deliverable includes twelve individual SKILL.md specifications, exact existing tool bindings, implementation anchors, a shared runtime contract, a machine-readable catalogue, and 48 proposed acceptance scenarios. These are custom specifications, not live registrations or completed feature implementations.

## What was reviewed

- Agent instructions, declarative-agent actions, inline plugin schemas, and the distinction from dated Copilot Studio source backups.
- SuccessFactors metrics, scope/filter handling, consent/disclosure boundaries, card route, and tests.
- S4 report tools, field mappings, coverage/calculations, date limitations, and tests.
- Productivity router, Graph client paths, read/write envelopes, triage, briefings, meeting actions, approval tokens, operation storage, subscriptions, worker behavior, evidence/confidence contracts, and tests.
- Facilitator tool registration, placeholders, finance snapshot adapter, vendor scoring/history, decision manifests/export, and tests.
- SAC client, cache/tool registration and its small mocked test suite; card service routes/signing and tests; Docker/Compose, selected deployment configuration, and duplicated packaged modules.

The five Python service trees contain 189 Python source/test files excluding virtual environments, with significant duplicated Productivity/shared modules. A static inventory indexes 537 top-level symbols in the nonduplicated application packages. Counts describe inventory coverage; they do not mean every line received a manual security audit. The review follows the custom business-capability and exposure paths. It does not certify all upstream Power CAT solution code, third-party dependencies, or archived binaries.

No live tenant queries, email sends, deployments, agent publication, credential inspection, or runtime code fixes were performed. Installed package discovery, source permissions, current Dataverse policies, actual SAP schemas, SAC endpoint contracts, real export delivery, and cloud revision parity remain unverified.

## What the code actually supports

| Area | Source evidence | Practical boundary |
|---|---|---|
| Workforce | Headcount, joiners, leavers, attrition, trends, demographics, Emiratisation; confidentiality consent and disclosure handling | Aggregate paths are reusable; scoped attrition has a defect; historical active status is current-directory based |
| Finance | Seven exposed report/master-data tools: AR/AP ageing, budget consumption/transfers, customer/cost/profit-center masters | Read-only; current aging only; P&L is explicitly unsupported |
| Productivity | Mail/calendar/Planner reads and prepare/execute writes, triage, briefing variants, meeting-action tracking | Strong reusable primitives, with the Teams, approvals, immediate-send and operation-registry defects below |
| Proactive recommendations | Rule engine, completeness/unit/currency checks, hysteresis, recovery, outbox and feedback | Finance bridge packaging is broken; budget mapping intentionally blocked; an SF snapshot ingestion adapter was not established |
| Vendor decisions | Decimal scoring, comparability policy, institutional history, persisted decisions and hash/signature evidence | Structured inputs required; checked-in policy still needs actual business sign-off; plugin discovery is incomplete |
| Institutional memory | Scoped vendor-history repository plus separate SuccessFactors user-memory functions | General Facilitator memory lookup/sync are placeholders; raw chat ingestion is local JSONL, not a demonstrated enterprise knowledge graph |
| SAC | Three functions and credential-backed HTTP calls | Only three mocked tests; tenant/model endpoint compatibility is not established |
| Presentation | Workforce/native cards and a ten-template rendering service | Card rendering/ticket validation is not business authorization or proof of live tool wiring |

## Custom skill catalogue

| Skill | Rollout | Code-based status |
|---|---|---|
| [Workforce assurance](skills/velora-workforce-assurance/SKILL.md) | Phase 1 | Reuse aggregate tools; hold scoped attrition |
| [Emiratisation target watch](skills/velora-emiratisation-watch/SKILL.md) | Phase 1 | Reuse KPI; new scenario calculation and monitoring wiring |
| [Cash exposure and collections brief](skills/velora-cash-exposure/SKILL.md) | Phase 1 | Reuse reports; recommendation bridge blocked |
| [Budget consumption and movement explanation](skills/velora-budget-control/SKILL.md) | Phase 1 | Reuse reports; recommendation mapping deliberately blocked |
| [Executive attention and day plan](skills/velora-executive-attention/SKILL.md) | Phase 1 | Reuse triage; approvals and Teams coverage limited |
| [Meeting preparation dossier](skills/velora-meeting-dossier/SKILL.md) | Phase 1 | Reuse productivity briefing path |
| [Meeting decisions to owned actions](skills/velora-meeting-actions/SKILL.md) | Phase 2 | Reuse approval workflow; natural transcript extraction needs work |
| [Reviewed executive correspondence](skills/velora-governed-correspondence/SKILL.md) | Phase 2 | Reuse productivity prepare/execute; quarantine legacy send paths |
| [Subscribed briefings and action reminders](skills/velora-scheduled-briefings/SKILL.md) | Phase 3 | Reuse subscription/worker code; deployment validation required |
| [Evidence-backed vendor comparison](skills/velora-vendor-decision/SKILL.md) | Phase 2 | Implemented backend; plugin exposure and policy validation required |
| [Decision evidence retrieval and export](skills/velora-decision-evidence/SKILL.md) | Phase 3 | Hold external/redacted export pending repair |
| [Cross-system executive board brief](skills/velora-board-brief/SKILL.md) | Phase 2 | New orchestration over existing verified reads |

Phase numbers are dependency order, not time estimates or production-readiness labels. Each specification includes four concrete acceptance scenarios and its exact tool names.

## Findings that materially affect these skills

P1 = fix before enabling the affected behavior. P2 = fix the affected integration or capability contract before advertising it. All findings apply to the reviewed local code; they do not assert that the live deployment contains the same revision.

### R01 — P1: Facilitator email accepts an unverified confirmation string

**Evidence:** The sender checks only whether confirmation_token is nonempty before requesting a Graph token and sending. There is no signature, actor, payload, expiry, or single-use validation in this function. The native tool is registered; HTTP access remains subject to identity/policy gates. See [mcp-apps/ask-facilitator/facilitator_mcp/tools.py:261](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:261).

**Effect:** An authorized tool caller can submit an arbitrary string and bypass the intended preview approval boundary. The offline probe returned EMAIL_SENT with a fake approval string; both provider calls were mocked.

**Required change:** Route this tool through the existing Productivity prepare/execute service or remove it from exposure. Add negative tests for arbitrary, stale, wrong-actor, changed-payload, and replayed tokens.

**Affected skills:** Correspondence, meeting summaries.

### R02 — P1: Daily briefing convenience operation immediately executes its own preview

**Evidence:** send_daily_briefing_email calls prepare_daily_briefing_email and immediately feeds the generated token/preview to send_approved_daily_briefing_email. The public router exposes SEND_DAILY_BRIEFING_EMAIL. See [mcp-apps/ask-productivity/productivity_mcp/tools_m365_writes.py:1668](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/tools_m365_writes.py:1668).

**Effect:** No intermediate user review occurs. This conflicts with the checked-in agent instruction requiring a concrete preview and confirmation. Offline mocks confirmed one prepare followed by one send in the same call.

**Required change:** Expose the separate PREPARE_DAILY_BRIEFING_EMAIL and SEND_APPROVED_DAILY_BRIEFING_EMAIL operations; reserve recurring sending for explicitly approved subscriptions.

**Affected skills:** Briefings, correspondence.

### R03 — P1: Live Teams channel context ignores the requested team and channel

**Evidence:** get_channel_context calls search_teams_messages(query="*") in live mode. That search scans messages from at most five user chats and does not resolve the requested team/channel. See [mcp-apps/ask-productivity/productivity_mcp/m365_client.py:1426](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:1426).

**Effect:** A channel-specific answer can be grounded in unrelated chats. This is a scope/provenance defect, not evidence of cross-user access. The offline probe returned an unrelated chat for a specific channel request.

**Required change:** Resolve exact authorized team/channel IDs; query their message endpoint, preserve provenance and pagination, and test two distinct channels with different fixtures.

**Affected skills:** Executive attention, meeting dossiers, board briefs.

### R04 — P1: Live approvals are hard-coded as an empty list

**Evidence:** list_pending_approvals returns [] when is_live is true, without calling a provider. Briefing code consumes that result. See [mcp-apps/ask-productivity/productivity_mcp/m365_client.py:1655](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:1655).

**Effect:** The agent can wrongly report no pending approvals even though approvals were never checked. The offline probe confirms the unconditional empty result.

**Required change:** Implement an approved approvals source; until then return an unavailable capability and render that state rather than a zero count.

**Affected skills:** Executive attention, scheduled and board briefs.

### R05 — P1: Attrition mixes numerator and denominator scopes

**Evidence:** Headcount is filtered by company and business_unit, but aggregate_leavers is called with company only. UAE leavers are obtained from a date-filtered EmpEmployment fetch and counted without intersecting a company/business-unit leaver population; the UAE headcount denominator is scoped. See [mcp-apps/ask-successfactors/successfactors_mcp/successfactors_client.py:1338](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/successfactors_client.py:1338).

**Effect:** Business-unit overall attrition, and company/business-unit UAE attrition, can be overstated or otherwise inconsistent. Existing tests pass but do not establish cross-company numerator closure.

**Required change:** Define a period-effective authorized leaver population per company/business unit and apply it consistently to both numerator variants; add two-company/two-business-unit negative fixtures. Suppress affected rates until verified.

**Affected skills:** Workforce assurance, Emiratisation.

### R06 — P1: Finance snapshot bridge imports a package absent from its container

**Evidence:** generate_finance_snapshot imports s4hana_mcp.tools in-process. The Facilitator Dockerfile copies facilitator_mcp, productivity_mcp, and shared_mcp only; requirements do not install s4hana_mcp. The exception is converted into an EMPTY outage snapshot. See [mcp-apps/ask-facilitator/facilitator_mcp/finance_snapshot_service.py:99](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/finance_snapshot_service.py:99).

**Effect:** The normal packaged finance recommendation path cannot retrieve S4 data through this import. Unit tests inject s4_tool_override, which bypasses the packaging problem. The package-path probe confirms the missing import.

**Required change:** Choose an authenticated call to the deployed S4 service or deliberately package the adapter and its dependencies. Test the built container without overrides. Preserve company/identity/audit boundaries.

**Affected skills:** Cash recommendations, board briefs.

### R07 — P1: Payables recommendation wording describes a different measurement

**Evidence:** The PAYABLES snapshot uses overdue_exposure (or due-today plus the 1–30-days overdue bucket). The checked-in AP rule explanation describes obligations due within seven days. See [mcp-apps/ask-facilitator/facilitator_mcp/finance_snapshot_service.py:172](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/finance_snapshot_service.py:172).

**Effect:** Overdue liabilities are not the next-seven-days payable forecast. The recommendation can misstate a cash planning signal even when the source numbers are real. The production rule catalogue may differ and was not inspected.

**Required change:** Align the approved KPI definition, calculation, unit, time window, threshold, and wording. Add fixtures containing past-due, due-today, next-week, and later invoices.

**Affected skills:** Cash exposure and recommendations.

### R08 — P2: Productivity operation aliases and authorization registry drift

**Evidence:** The router defines 135 accepted operation strings, but 75 normalize to keys absent from the packaged static registry. This includes the main PREPARE_PLANNER_COMPLETION and COMPLETE_APPROVED_PLANNER_TASK operations. Static lookup precedes the administrator allowance. See [mcp-apps/ask-productivity/productivity_mcp/server.py:264](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/server.py:264).

**Effect:** Some implemented routes are always denied; adding Dataverse permissions alone cannot enable unregistered operations. Other missing strings are aliases whose canonical underscored form may work.

**Required change:** Define one canonical operation catalogue and derive routing, schema, alias mapping, permission registry, and plugin declarations from it. Keep default deny; do not bypass authorization to fix usability.

**Affected skills:** Task completion and multiple alias-triggered skills.

### R09 — P2: Meeting action extractor expects labelled notes

**Evidence:** Extraction recognizes Action:/Action Item: and a bracketed-list format. It does not parse general conversational commitments. See [mcp-apps/ask-productivity/productivity_mcp/meeting_actions.py:86](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/meeting_actions.py:86).

**Effect:** Ordinary speech can produce zero actions. The fixture “Alex: I will send the revised budget by Friday.” produced no actions. This limits the claimed transcript-to-actions capability.

**Required change:** Retain deterministic extraction for structured notes; add reviewed, source-span-backed extraction for free speech, including ambiguous owner and relative-date handling. Do not turn inferred commitments directly into tasks.

**Affected skills:** Meeting actions.

### R10 — P2: Checked-in Facilitator plugin omits implemented decision tools

**Evidence:** Nine native tool registrations are absent from the checked-in facilitator-plugin.json functions list, including vendor evaluation/history, finance snapshots, decision retrieval, export and verification. Six listed meeting/memory operations instead unconditionally return SOURCE_UNAVAILABLE. See [mcp-apps/ask-facilitator/facilitator_mcp/tools.py:616](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:616).

**Effect:** Existing Python implementation is not proof that the selected agent package can discover it. The live agent may have independent registrations; that state was not inspected.

**Required change:** Refresh the intended plugin/connector from actual schemas, expose only the chosen capability set, hide/redirect placeholders, and prove discovery through the actual agent.

**Affected skills:** Vendor decisions, decision evidence, meeting routing.

### R11 — P1: Redacted exports still generate unredacted CSV prices

**Evidence:** Redaction modifies manifest_dict, but generate_decision_csv receives the original manifest. It writes commercial_price/commercialPrice from the input snapshot. CSV/BUNDLE output can therefore retain prices while isRedacted is true. See [mcp-apps/ask-facilitator/facilitator_mcp/audit_export.py:500](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/audit_export.py:500).

**Effect:** An authorized auditor asking for a redacted export can receive commercial data that the requested redaction was meant to remove. This is a direct static data-flow finding; no live export was performed.

**Required change:** Apply a single validated redaction view consistently to JSON, CSV, returned content, and stored artifacts; define verifiable redaction semantics. Add assertions that a synthetic secret price is absent from every artifact.

**Affected skills:** Decision evidence exports.

### R12 — P1: Decision export audit liveness is a simulation flag only

**Evidence:** check_audit_logging_liveness only checks VELORA_SIMULATE_AUDIT_OUTAGE. It does not establish a real audit service health or durable audit acceptance before the export reports FINALIZED_EXPORT. See [mcp-apps/ask-facilitator/facilitator_mcp/audit_export.py:97](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/audit_export.py:97).

**Effect:** The claimed fail-closed audit behavior is not established for actual Dataverse/audit outages. Signature and local manifest persistence do not prove remote audit acceptance.

**Required change:** Use the durable audit transaction boundary, with a confirmed acceptance receipt and a recoverable export state; validate a real mocked provider outage rather than an environment flag alone.

**Affected skills:** Decision evidence exports.

## Additional architectural observations

1. **Separate maintained code from copied deployment code.** Facilitator embeds a second `productivity_mcp` package. Its server.py and briefing_service.py already differ from the primary package. A fix in one copy may not reach the other image. Package shared code once or establish a verified synchronization/build step.
2. **Unify the delivery description.** The top-level suite README and Compose file describe five services and omit the separate Productivity service. Other deployment scripts include Productivity and a worker. Worker schedules differ between the Bicep and shell deployment paths. This complicates repeatable skill installation.
3. **Fix contradictory tool descriptions.** The Facilitator guide’s prose requires review, while its step list says to disable review. Plugin descriptions still mention auto-dispatch. Match discovery descriptions to the actual approved execution flow.
4. **Do not treat local persistence as enterprise knowledge search.** `ingest_chat_to_knowledge_graph` appends raw prompt/response content into a process-level collection/local JSONL, ignores the persistence helper’s failure result, and reports success. No general searchable, permission-trimmed knowledge graph is established by this function. Avoid it for the proposed institutional-memory extension until scope, retention, provenance, durable commit, and retrieval are implemented.
5. **Keep authorization model claims accurate.** SF settings identify a maker/service credential model; some older documentation says source-delegated executive access. Confirm the actual route and source account entitlements rather than repeating the older claim.
6. **Keep unsupported product claims out of the new skills.** No verified peer-benchmark fetch/evaluation tool or natural-language create/edit/pause/retire agent lifecycle was found in the reviewed runtime. A peer benchmark entity and card template are groundwork, not an executable feature.

## Validation performed

All external Python socket connections were blocked; .env loading was disabled; tests ran in temporary working/state directories with synthetic configuration. Existing runtimes supplied test dependencies. Each test file was run in a separate process to reduce shared-module and environment contamination.

| Component | Existing tests passing after required fixture setup |
|---|---:|
| SuccessFactors | 96 |
| S4HANA | 41 |
| Productivity | 230 |
| Facilitator | 56 |
| SAC | 3 |
| Dynamic card service | 12 |
| **Total** | **438** |

This is not a claim that a single untouched test command passes. The SF virtual environment lacked pytest, and the S4 environment lacked the async plugin, so the existing Productivity environment was used. Productivity finance tests also required the Facilitator/S4 source paths. In file-isolated execution, two Productivity test files assumed MOCK_M365 and seeded fixtures supplied elsewhere: ten tests failed without that setup, then both files passed with explicit mock/seed setup. Preliminary globally mocked runs also interfered with audit/consent tests; final per-file runs removed those global overrides. Source tests were not changed.

Six additional offline probes confirmed the unchecked Facilitator confirmation string, immediate briefing send, wrong channel context, unqueried empty approvals, labelled-only action extraction, and missing Facilitator S4 import. These probes use mocks or local imports, not real provider calls. Static tracing additionally identifies attrition-scope, AP-definition, redaction, audit-liveness, and registry/plugin drift problems not covered by passing tests.

Evidence: [offline probes](evidence/offline-probes.json), [isolated test results](evidence/isolated-test-results.json), [explicit-fixture retests](evidence/explicit-fixture-retests.json), [source inventory](evidence/source-inventory.json), [router/registry gaps](evidence/router-registry-gaps.json), and [manifest gaps](evidence/manifest-gaps.json). The supplied [offline test runner](evidence/offline_test_runner.py) captures the isolation setup; run it with the existing Productivity Python environment and arguments SERVICE [TEST_FILENAME].

The 48 rows in [acceptance-scenarios.csv](acceptance-scenarios.csv) are new proposed behavior checks, explicitly marked PROPOSED_NOT_EXECUTED. They are separate from the 438 existing tests above. [Skill format, link, and binding validation](evidence/pack-validation.json) passed for all twelve specifications.

## Implementation order

1. **Repair exposed behavior first.** Address R01–R05 and R11–R12; use current supported read paths while holding affected operations. Keep permission checks intact.
2. **Make one capability catalogue authoritative.** Choose the intended live agent packaging surface. Align canonical operations, plugin schemas, static authorization registry, and actual connector discovery (R08/R10). Remove or redirect placeholders, and consolidate duplicated code.
3. **Ship Phase 1 read skills.** Workforce assurance, Emiratisation explanation, current cash exposure, budget reporting, attention/day planning, and meeting dossiers. Hide unsupported approvals/channel sections; suppress affected scoped rates.
4. **Ship Phase 2 workflows.** Add reviewed correspondence, structured meeting actions, vendor decisions, and the new board-brief composition. Repair finance bridge/measurement semantics (R06/R07); extend transcript extraction with source evidence (R09).
5. **Ship Phase 3 automation/evidence.** Prove worker deployment, scope-limited standing authorization, storage/recovery, duplicate suppression, real audit failure handling, redaction, and artifact delivery before recurring briefings and audit export.

Owners needed by role: agent/integration engineer for routing and manifests; SAP/HR data owners for metric definitions and scope; Microsoft 365 engineer for Graph and approvals; procurement owner for scoring policy; platform engineer for containers/worker/storage; audit owner for export/retention rules. This assigns responsibility, not fabricated people or delivery dates.

## Custom extensions to design after this pack

- **Institutional decision search:** permission-scoped retrieval of approved minutes, source documents, and previous decisions, with source version and retention. Reuse vendor institutional records where appropriate; replace the generic memory placeholders.
- **Peer comparison:** approved external dataset ingestion, cohort and period comparability, licensed-source provenance, and a real callable benchmark service before using the existing entity/card.
- **SAC strategy brief:** validate the actual tenant API/model contracts and resolve the current P&L/income-statement exclusion before expanding corporate KPI promises.
- **Travel-policy assistant:** grounded retrieval against the current approved SharePoint document, with section citations and policy version; a local PDF alone is not live permission-trimmed retrieval.
- **Natural-language agent lifecycle:** a new governed provisioning/edit/pause/retire workflow, not currently implemented by the reviewed business tools.

No new live capability has been enabled by this review. The deliverable is a concrete, source-grounded specification and implementation backlog for this exact agent.
