# AIATC repository re-review — 6 September 2026

**Verdict: improvements are present, but the previous issues are not all fixed. Do not mark the implementation complete or ready for acceptance sign-off.** Some corrections introduce new financial and recovery defects. This report supersedes the previous review's status observations, while retaining its original requirements.

Reviewed the current working tree, current S/4 tests, new recommendation engine/tests, Microsoft 365 connector, SF audit spool/admin paths, Facilitator changes, Dataverse XML and actual solution ZIP. Ran 23 S/4 tests and 5 recommendation tests: all 28 pass. Additional offline probes reproduce the failures below. No application edits, deployments, live SAP queries or external messages were performed. No supplied SAP password was used. This is not certification of the live Azure or Dataverse environment.

## Confirmed improvements

- Ordinary Decimal-containing results now pass through the tested REST/custom MCP routes without the previous serialization TypeError. However, conversion to float loses precision: see F04.
- Camel-case aliases and legacy variance routing work in the new local tests.
- Changed/duplicate SAP-client continuation parameters and the previous sibling-path-prefix example are rejected; omitted SAP client is restored.
- Unsupported future dates are rejected using Dubai's date. Legacy cost-center requests and companies other than 1000 are rejected instead of silently broadened. Blank version handling was added. The 1000 mapping remains hardcoded rather than Dataverse-approved.
- Unexpected top-level JSON collection shapes now produce CONTRACT_MISMATCH.
- Single-currency budget consumption now emits CONFIGURATION_REQUIRED and reduced confidence.
- Unknown source update time is left unknown rather than replaced with retrieval time.
- The public custom MCP discovery lists the four reports and excludes P&L.
- Facilitator's missing asyncio import and stale operating-profit phrase were corrected. Its underlying hardcoded briefing figures and simulated storage remain.
- The actual solution ZIP now contains 11 entities, including eight new source/KPI/recommendation/evidence entities. A recommendation module and file-spooling code now exist. Their presence does not establish a functioning end-to-end workflow.

## Remaining and newly introduced findings

### F01 — AR still combines different currencies; budget multi-currency reports crash — high

The currency helper omits **CompanyCodeCurrency**, the exact AR field in the supplied SAP payload. The new test instead uses a generic `Currency` field. With CompanyCodeCurrency USD 100 and AED 100, the calculator returns one 200 total, currency UNSPECIFIED, and is_multi_currency=false. Text still defaults to AED. Single-currency AP USD responses can also be labelled AED when the user omits currency because display logic reads the request rather than the calculated source currency.

Budget calculators now return by_currency for mixed currencies, but the text builder still indexes single-currency keys. Offline tool calls reproduce `KeyError: total_movement_amount` for transfers and `KeyError: raw_budget` for consumption.

Evidence: [currency helper:10](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/report_calculations.py:10), [display currency:91](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/tools.py:91), [transfer summary:180](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/tools.py:180), [consumption summary:204](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/tools.py:204).

Required: use exact per-entity currency fields and one consistent single/multi-currency output contract across calculations, text and cards. Test with the supplied field names, not invented replacements.

### F02 — Budget deduplication drops legitimate amounts and contradicts the breakdown — high

The new budget key is hardcoded to FMA, funds center, commitment item, fiscal year and version. Only the first amount at that key contributes to the headline budget, without checking whether later amounts represent separate periods, entries or changes. Funds-center detail still sums every amount.

Reproduced: rows with amounts 100 and 200 at the same key produce **headline budget 100, funds-center budget 300**. Even repeated 100/100 produces headline 100 and detail 200. No Finance-approved grain is loaded, so keeping the first record is not an established accounting rule.

Evidence: [budget key:278](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/report_calculations.py:278), [detail sum:302](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/report_calculations.py:302).

Required: implement approved measure/grain semantics and reconcile headline/detail from the same validated inputs. Block ambiguous business totals until configuration is approved.

### F03 — Normal document line items are rejected as conflicting snapshots — high

The new duplicate detector uses the document number without the line item, company or fiscal year. Two valid rows of AccountingDocument 0001, items 001 and 002, are treated as conflicting versions and stop collection after the first row. Conversely, repeating the identical line twice is accepted and both rows are summed as complete.

Evidence: [document key:326](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/client.py:326).

Required: use metadata-confirmed composite entity keys. Distinguish different lines, identical duplicate lines, and conflicting versions of the same complete key.

### F04 — Serialization now changes exact monetary values — high

The response conversion uses float(Decimal). Offline reproduction: `9007199254740993.01` becomes JSON `9007199254740994.0`. Parsing source JSON directly to Decimal is an improvement, but converting back to float at the response boundary defeats exact preservation. Invalid/missing monetary fields can still become zero and nonfinite values are not rejected reliably.

Evidence: [to_jsonable_data:48](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/contracts.py:48), [SafeJSONResponse:40](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/server.py:40).

Required: exact decimal serialization, validated finite source amounts and contract-error handling. Add tests that cannot pass through binary floating-point rounding unnoticed.

### F05 — Full-report retrieval and approved endpoint enforcement remain incomplete — high

The client still sends `$top`, now hardcoded through an undeclared s4_page_size fallback of 500. Changing the visible top to 500 does not make it a server paging preference; a source that honors it as the total query limit can stop before the full report. A missing count still permits false full-report confidence. The total deadline is checked between pages, but request/retry timeouts are not limited to the remaining deadline.

Base URL validation has regressed: any host ending `.velora.ae` is accepted, including QAS with Production settings. Offline validation accepted `https://fioriqas.velora.ae/anything`. The current server main also no longer runs the earlier startup configuration validation. Continuation validation is improved, but permits child paths below the expected entity and does not establish an exact normalized entity contract.

Evidence: [endpoint validation:80](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/client.py:80), [query limit:407](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/client.py:407), [startup:416](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/server.py:416).

Required: exact approved roots/entities, enforced production/QAS separation, full-input collection independent of detail size, and a real bounded report deadline.

### F06 — User scope, evidence and transport completeness are still unproven — high

S/4 still checks a shared API key without verified executive-to-organization entitlement enforcement. SF administrative routes still supply the hardcoded Velora_Admin role. High confidence and “Complete reconciled report” remain based on collection coverage, without Finance reconciliation. Randomized evidence references are not persisted snapshots or resolvable evidence records. Source/card/text confidence and limitations remain inconsistent.

FastMCP is instantiated and tools registered, but create_app no longer mounts its streamable HTTP app/lifespan. Only the custom JSON endpoint is served. Handwritten schemas, Python registrations and the separate core-report list remain separate sources of truth. Removing the FastMCP route is not verification that all supported transports work. Existing `/tools/...` REST paths were also removed from route construction.

Evidence: [API-key middleware:70](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/server.py:70), [app construction:397](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/server.py:397), [confidence:482](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/client.py:482), [SF admin:603](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/successfactors_server.py:603).

### F07 — Graph authentication failure can still become simulated success — high

Live write branches were added, but read methods still return module sample lists even when live credentials are configured. Token acquisition returns None on failure and write methods fall through to simulation. An offline check forced live mode and a failed token result: execute_send_email returned SENT with MOCK_SIMULATED. The outer write tool discards that receipt and reports SUCCESS / “Email successfully sent.” This can falsely confirm a real action.

The new sendMail branch also uses a request-id as a message-id and constructs an Outlook item URL from it; that is not verified object evidence. Attachments are not included in the live payload. Planner creation does not use the requested bucket, description or priority and passes plan_name directly as planId without resolving a real plan identifier.

Evidence: [token acquisition:189](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:189), [sample reads:275](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:275), [email:348](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:348), [outer success:201](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/tools_m365_writes.py:201), [Planner:570](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:570).

Required: explicit demo-only simulation, fail closed on live authentication failure, real reads and identifier resolution, faithful action payloads and truthful receipts propagated through every layer.

### F08 — Recommendation restart recovery fails; rule governance is incomplete — high

The new module persists delivery records but keeps recommendation details only in memory. Recreated the engine using the same outbox directory: one delivery recovered, zero recommendations recovered. Dispatch then marked the pending item FAILED with “Recommendation record not found.” Restart also loses breach/deduplication state. Default storage is /tmp; the inspected deployment artifacts do not establish persistent storage or replica-safe claims.

The evaluator does not enforce effective_from/effective_to, currency/unit compatibility or cooldown. An expired rule denominated in AED emitted a recommendation for a USD snapshot in an offline probe. Default seed rules are active. No production scanner/server import or Dataverse rule loader was found outside this module/tests.

Dispatch marks a returned simulated send as DELIVERED; reproduced with a fake receipt explicitly marked simulated=true. This does not meet a real delivery acceptance gate.

Evidence: [memory-only recommendations:298](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py:298), [rule selection:318](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py:318), [restart failure:435](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py:435), [delivery claim:457](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py:457).

Required: durable recommendations/snapshots/breach state, approved Dataverse-loaded rule versions, validity/unit/currency/freshness checks, restart-safe and replica-safe delivery, and actual scheduler/source integration.

### F09 — SF audit spool requeues already committed records — high

Commit markers are appended as separate persisted=true lines. Recovery independently queues every earlier persisted=false line and never applies the later commit marker to it. A file with one pending record followed by its commit marker requeued that already committed record on restart. Recovery also rebuilds only a subset of audit fields; default storage is /tmp.

Evidence: [spool recovery:68](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/background_logger.py:68).

Required: replay the log into final per-record state before enqueueing, preserve complete audit payloads, use durable storage and validated persistence acknowledgements, and prove restart/replacement/multi-replica behavior.

### F10 — AIATC workflows and deployable solution coverage remain partial — high

The eight new packaged entities are sourcecatalog, kpidefinition, kpirecommendationrule, kpisnapshot, recommendation, recommendationfeedback, notificationdelivery and decisionevidence. This corrects the prior absence finding. It does not prove successful Dataverse import, correct relationships/keys/security, live rule loading or workflow execution.

audit_cloud_flows.json is now included in the ZIP, but retains design-style values such as manual_or_agent_call and Dataverse_QueryRows. Copying that file into the ZIP does not establish registered executable solution workflows. No import or run was performed in this review.

Permanent institutional-record, proposal-evaluation and peer-benchmark entities are still absent from the inspected package. Facilitator still returns fixed briefing facts and stores knowledge/Loop records in process lists. The original all-nine end-to-end gaps are not closed.

Evidence: [packager:13](/Users/vikrambala/copilotstudio/deploy/build_velora_executive_platform_solution.py:13), [current XML](/Users/vikrambala/copilotstudio/deploy/solution/customizations.xml), [flow design:32](/Users/vikrambala/copilotstudio/deploy/solution/audit_cloud_flows.json:32), [Facilitator storage:337](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:337).

## Disposition of every previous finding

| Previous finding | Current disposition |
|---|---|
| R01 HTTP serialization crash | Original simple case fixed; precision regression and multi-currency failures remain. |
| R02 currency mixing | Not fixed for exact AR fields; presentation still wrong; budget multi-currency crashes. |
| R03 budget semantics/configuration | Configuration status improved; unapproved grain and inconsistent totals remain. |
| R04 continuations | Prior explicit examples fixed; exact endpoint/entity enforcement remains incomplete. |
| R05 full-report collection | Not closed; top cap remains and incorrect duplicate logic added. |
| R06 organization/date/filter handling | Dates and rejection paths improved; hardcoded company 1000 mapping remains, no approved mapping service. |
| R07 identity/scope | Not fixed in inspected service paths. |
| R08 monetary/source contract | Top-level shape/direct Decimal parsing improved; output precision, field validation and invalid amounts remain. |
| R09 source assurance | Unknown update time fixed; confidence, immutable evidence and output parity incomplete. |
| R10 transport/discovery | Custom aliases/four-report discovery improved; FastMCP serving and contract parity not closed. |
| R11 M365/Facilitator simulation | Live write branches added; sample reads, false-success fallback and simulated Facilitator remain. |
| R12 Dataverse/orchestration | Tables/module/spool added; operational integration, reliable recovery and full-nine workflows incomplete. |

## Nine AIATC capabilities

| Capability | Current review conclusion |
|---|---|
| Agent creation | Self-service governed create/edit/pause/retire lifecycle still not demonstrated. |
| Brief synthesis | Sample reads/fixed briefs remain; reliable scheduled sourced delivery not established. |
| Decision traceability | More schema/spooling exists; identity, evidence and restart correctness remain blockers. |
| Enterprise query | S/4 finance correctness and scope defects remain; no live source reconciliation performed. |
| Institutional memory | Short-term SF memory and simulated Facilitator storage remain; permanent governed records not demonstrated. |
| Meeting intelligence | Missing-import fix confirmed; real transcript-to-reviewed-action-to-task-to-closure flow not established. |
| Proactive recommendations | New prototype and schema exist; integration/governance/restart/delivery defects block completion. |
| Evaluation | Operational proposal evaluation service and deployed rubric/result model not demonstrated. |
| Peer benchmarking | Approved data/cohort/method and operational persisted comparison pipeline not demonstrated. |

## Acceptance and next steps

The 23 S/4 tests and 5 recommendation tests passed locally. Their limits matter: the AR currency test uses Currency instead of CompanyCodeCurrency; the budget test checks headline deduplication without reconciling detail or distinct entries; the outbox restart test reloads delivery records without proving post-restart delivery. Therefore these passes do not close C01–C30, and C31/C32 remain unexecuted live acceptance gates.

Prioritize F01–F05 financial correctness, F07 false-success prevention, F08/F09 reliable recovery, then F06 trusted scope/evidence and F10 end-to-end integration. Preserve the genuine fixes. Re-test with exact supplied payload fields and realistic multi-line documents, and use complete restart-through-delivery scenarios. P&L remains excluded.

Review boundary: no full rerun of unchanged SF, SAC, Facilitator or legacy Productivity suites; no deployment/tenant certification. Current code was inspected directly and the targeted checks above were executed, rather than accepting another agent's completion labels.
