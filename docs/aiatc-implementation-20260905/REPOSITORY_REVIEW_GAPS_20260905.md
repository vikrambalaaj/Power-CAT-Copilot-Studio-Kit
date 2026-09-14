# Independent repository review — AIATC and S/4HANA

Reviewed 5 September 2026 against the current working tree, the supplied other-agent status report, and the model-ready implementation plan. **The implementation is not complete and is not ready for acceptance sign-off.** The 16 existing S/4 unit tests pass, but additional offline checks reproduce failures those tests do not cover. Several reported PASS gates also substitute easier conditions for the original acceptance requirements.

This review changed no application code, deployed nothing, used no supplied SAP password and contacted no live business service. HTTP probes used local Starlette clients or httpx MockTransport. Existing environment/deployment state was not independently certified. Findings apply to the inspected working tree, including uncommitted changes; they are not a statement about which revision is running in Azure.

## 1. Highest-priority findings

### R01 — Report responses fail at the HTTP boundary (high)

Calculations retain Python Decimal values inside structuredContent. REST and the custom JSON MCP handler pass those values directly to JSONResponse. With a mocked successful SAP result, `/s4__get_receivables_aging` returns HTTP 500: `Object of type Decimal is not JSON serializable`. A direct JSONResponse check reproduces the same failure. The custom MCP response uses the same serialization pattern and catches failures as protocol errors.

Evidence: [server.py:211](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/server.py:211), [server.py:313](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/server.py:313), [tools.py:29](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/tools.py:29).

Required correction: retain Decimal internally, serialize monetary values explicitly and consistently at every transport boundary, and exercise successful calls through REST, custom MCP and FastMCP. Direct handler tests are insufficient.

### R02 — Different currencies are added together and labelled AED (high)

When currency is omitted, no currency filter is sent, but tools set the output currency to AED. Calculators do not partition by source currency. An offline fixture with USD 100 and AED 100 returns a combined 200 labelled AED. This affects all four report families. The existing currency test checks only explicitly supplied currency filters.

Evidence: [tools.py:207](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/tools.py:207), [tools.py:216](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/tools.py:216), [report_calculations.py:10](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/report_calculations.py:10).

Required correction: return separate source-currency totals or require an approved currency scope. Do not infer currency or perform conversions without a defined rate source and date.

### R03 — Budget interpretation and configuration are unfinished (high)

Consumption blindly adds BudgetAmountInFMACrcy across rows, including repeated budget values on different transaction references. Grouping those sums by FundsCenter does not establish an additive grain. A two-row fixture with the same 100 budget produces 200. There is no approved value-type/statistical/sign/overlap mapping. The tool always calls `mapping_approved=False`, yet the response status remains COMPLETE with High confidence and “Complete reconciled report.” CONFIGURATION_REQUIRED exists as an enum but is not emitted here. No Dataverse rule lookup makes the approved path operational.

Evidence: [report_calculations.py:182](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/report_calculations.py:182), [tools.py:335](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/tools.py:335), [client.py:380](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/client.py:380).

Required correction: implement versioned Finance-approved mappings and grain validation; withhold unverified aggregate business metrics, communicate configuration-required state consistently, and test repeated budgets and overlapping measures.

### R04 — Continuations can change SAP client or escape the exact service path (high)

The next-link validator checks origin and a simple path prefix, but not sap-client, entity or a path-segment boundary. Offline checks accepted both a link with `sap-client=200` and a sibling path beginning `0001evil/`. On subsequent pages current_params is emptied, so a next link omitting the client does not preserve client 100.

Evidence: [client.py:134](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/client.py:134), [client.py:271](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/client.py:271).

Required correction: validate the normalized exact approved service/entity path and exactly one approved SAP client before forwarding credentials. Cover changed, missing and duplicate client parameters, relative links, and sibling service paths.

### R05 — Full-report coverage is not implemented reliably (high)

`query` sends the visible detail limit as OData `$top`. Following next links cannot retrieve beyond a server's total `$top` limit. With a missing count and a terminal limited response, the client declares the returned rows the total and reports COMPLETE/High. The actual request loop also computes unused row keys; it does not detect conflicting duplicate records or a changed snapshot. The timeout is per request, not a total report deadline, and no retry loop is implemented.

Evidence: [client.py:307](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/client.py:307), [client.py:251](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/client.py:251).

Required correction: separate report collection from displayed detail, establish trustworthy terminal coverage, validate composite source keys/snapshot consistency, and bound total elapsed time and transient retries. Never describe an unreconciled limited extract as a complete report.

### R06 — Organization and legacy-filter handling silently changes the request (high)

The legacy variance adapter treats CompanyCode as FinancialManagementArea without an approved mapping and silently discards cost_center. An offline call for company 2000 and COST01 produces company/FMA 2000 filters with no cost-center restriction. An explicitly blank BudgetVersion is also dropped, so it cannot select the blank-version records in the supplied payload. Future key dates are accepted but not applied to the source, allowing today's result to be labelled with a future requested period. The configured report timezone is not used by date.today().

Evidence: [tools.py:339](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/tools.py:339), [field_mappings.py:185](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/field_mappings.py:185), [tools.py:39](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/tools.py:39).

Required correction: resolve approved organization mappings or reject unsupported filters; preserve the distinction between omitted and blank values; reject unsupported future dates as well as unsupported historical dates.

### R07 — User-level scope enforcement is not demonstrated (high)

S/4 middleware validates a shared API key. Tool handlers accept organization filters without a verified user-to-organization entitlement lookup. A fixed service credential does not prove the requesting executive may see every record accessible to that credential. No repository evidence establishes the asserted gateway enforcement. SuccessFactors admin handlers also still pass a hardcoded Velora_Admin role to administrative services.

Evidence: [S/4 server.py:45](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/server.py:45), [SuccessFactors server.py:603](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/successfactors_server.py:603).

Required correction: implement or provide verifiable evidence for trusted identity and approved scope enforcement, including direct-service access restrictions. Test forged identity and unauthorized organization requests, not just missing API keys.

### R08 — Monetary and source contracts are dictionaries without validation (high)

contracts.py supplies an enum and helper dictionaries, not validated request/response models. Source JSON is decoded using response.json(), so numeric monetary literals pass through floating-point parsing before Decimal conversion. Invalid or absent amounts become zero via safe_decimal. A malformed success response with an unexpected JSON shape was reproduced as EMPTY rather than CONTRACT_MISMATCH. Source field types, required keys and metadata are not validated.

Evidence: [contracts.py:23](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/contracts.py:23), [client.py:218](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/client.py:218).

Required correction: validate EDM/source contracts, parse monetary numeric literals directly to Decimal, reject invalid/nonfinite amounts, and distinguish missing/invalid data from genuine zero and empty reports.

### R09 — Source freshness and business assurance are overstated (high)

sourceUpdatedTime falls back to retrieval time even when SAP did not provide an update time. evidenceRef is a generic report label, not an immutable run evidence reference. High confidence is assigned from row coverage alone; no Finance reconciliation establishes the claim. Cards and text do not consistently show source time, limitations and confidence. Credit treatment is described as Finance policy without a loaded approved policy. A valid cache hit retains its stored time, which is useful, but source outage/cache behavior lacks the claimed acceptance test.

Evidence: [contracts.py:86](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/contracts.py:86), [adaptive_cards.py:130](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/adaptive_cards.py:130).

Required correction: leave unknown update time unknown; distinguish retrieval time, measurement date and source update; store a retrievable evidence snapshot; carry business limitations into every output surface.

### R10 — Transport compatibility and discovery remain inconsistent (medium)

The registered `/getReceivablesAging` alias returns 404 because lookup expects the canonical tool name. Custom MCP rejects the legacy budget-variance tool as not found, although a Python adapter and a REST route exist. Names are derived from TOOL_SPECS, but schemas are separately handwritten in server.py and omit handler fields such as correlation_id. Seven tools are exposed: four reports plus three master-data tools; this is not an exactly-four-tool surface. The four report names are present and P&L is absent from discovery.

Evidence: [server.py:172](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/server.py:172), [server.py:73](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/server.py:73), [tools.py:449](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/tools.py:449).

Required correction: resolve aliases explicitly, define legacy behavior consistently, and generate validated schemas from one contract. Confirm whether master-data tools are separately approved and configure their endpoints accordingly.

### R11 — Microsoft 365 and Facilitator still return simulated business results (high)

Productivity's read/write tools instantiate Microsoft365Client, whose mail and calendar reads use module lists. Sending email inserts into a list and returns SENT; Planner creation appends a fabricated task and returns CREATED. Adding tenant credentials will not turn these functions into Graph calls. Daily briefing dispatch uses that same simulated sender. Facilitator creates fixed SAP briefing figures, saves knowledge nodes and Loop records to in-memory lists, and constructs links while reporting successful storage. Its REST handler also references asyncio without a module-level import.

Evidence: [M365 reads:215](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:215), [M365 email:288](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:288), [Planner:376](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:376), [Facilitator:337](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:337), [briefing:379](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:379), [Loop:438](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:438), [REST:80](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/server.py:80).

Required correction: implement live approved connectors and truthful unavailable/demo states, real persisted records and provider receipts. End-to-end tests must verify the actual destination objects, not merely returned status strings. Remove stale fabricated operating-profit facts from the Facilitator briefing as part of the P&L scope cleanup.

### R12 — Dataverse recommendation and durable orchestration work remains design-only (high)

The packaged customizations contain exactly three entities: BotUserConsent, VeloraAgentAuditLog and VeloraDataDisclosurePolicy. KPI definitions/rules/snapshots, durable scans/delivery outbox, institutional records, evaluation rubrics/results and peer observations are not in that package. No corresponding operational recommendation scanner was found in the inspected services. The proposed flow JSON is not included by the solution packager. SuccessFactors background audit logging uses an in-process asyncio.Queue, not a durable outbox.

Evidence: [customizations.xml](/Users/vikrambala/copilotstudio/deploy/solution/customizations.xml), [packager:13](/Users/vikrambala/copilotstudio/deploy/build_velora_executive_platform_solution.py:13), [background logger:32](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/background_logger.py:32).

Required correction: build the planned tables and runtime workflows, package actual deployable components, and prove restart recovery, duplicate suppression, immutable evidence and delivery receipts. Arithmetic helpers are not a proactive recommendation engine.

## 2. Corrected nine-capability tracker

| Capability | Repository-supported status | Work still required |
|---|---|---|
| Agent creation | Partial foundation; self-service lifecycle not demonstrated | Approved creation boundary, persisted/versioned definitions, edit/pause/retire, authorization and lifecycle UAT. Templates alone do not implement this. |
| Brief synthesis | Prototype paths with sample/simulated inputs and delivery | Live scoped calendar/mail/source reads, grounded synthesis, night-before/EOD scheduling, durable runs and verified delivery. See R11. |
| Decision traceability | Partial audit foundation; durable architecture remains proposed | Trustworthy user identity, immutable source/rule snapshots, durable outbox, real packaged flows, export/reconciliation and required Purview verification. See R07/R09/R12. |
| Enterprise query | Partial; S/4 runtime/data defects remain | R01–R10; SF authorization/consent verification; source-owner reconciliation. SAC has an HTTP path, but this review does not certify its live endpoint contracts. |
| Institutional memory | Short-term memory and simulated long-term storage | SF memory still queries 30 days; implement permanent approved records, access control, retention, ingestion, versioning and successor access. See R11/R12. |
| Meeting intelligence | Prototype/design, not merely awaiting permissions | Real transcript ingestion, reviewed decisions/actions, real Planner creation, reminders, closure, durable Loop/approved storage and verified source links. |
| Proactive recommendations | Design plus report arithmetic, not engine-complete | Dataverse rule/version approval, semantic mapping, scheduler, snapshots, breach state, deduplication, delivery/retry/feedback and actual 30-day evidence. |
| Evaluation | Designed; operational service not demonstrated | Approved rubrics, extraction/evidence handling, versioned deterministic scoring, persisted results and labeled evaluation cases. |
| Peer benchmarking | Designed; operational storage/pipeline not demonstrated | Approved dataset/cohort/method, deployable tables, import/normalization, comparability checks, sourced outputs and UAT. |

The absence of proposed tables from the local package does not prove they do not exist in a separately managed tenant. An environment export and runtime evidence would be needed to establish that.

## 3. Corrected S/4 acceptance gates

PASS below means a narrow local check passed, not live acceptance certification. PARTIAL means useful code exists but the full original gate is unproven. GAP means a concrete missing behavior or contradictory result was found.

| Gate | Review status | Evidence and remaining issue |
|---|---|---|
| C01 | PARTIAL | Correct production defaults and four entity names; actual four-service reconciliation absent; continuation client invariant fails. |
| C02 | PARTIAL | Defaults normalized; QAS validation exists, but tests do not verify the asserted production request behavior comprehensively. |
| C03 | PARTIAL | API-key test passes and source 401/403 branches exist; full missing/bad/denied source credential cases not tested. |
| C04 | PASS, narrow | Explicit AR/AP/consumption currency filter names verified. Omitted/mixed currency still fails R02. |
| C05 | GAP | Company-to-FMA guess and ignored cost center violate original no-guessing requirement. |
| C06 | GAP | Visible top limits the source report; no real transport multi-page test in the 16-test suite. |
| C07 | PARTIAL | nextLink loop exists; missing count plus limited terminal response can report false completeness. |
| C08 | GAP | Repeated-link detection exists, but conflicting duplicate keys/mid-read changes are not checked. Original gate covered all three. |
| C09 | GAP | Other-origin test passes; changed client and sibling-prefix service path are accepted. |
| C10 | GAP | Decimal string helper tested; source numeric decoding, invalid amounts and validated identifiers not adequately covered. |
| C11 | PASS, narrow | Listed age boundaries and bucket reconciliation pass synthetic unit test. |
| C12 | PARTIAL | Missing DaysOverdue enters unaged; full missing/invalid due-date and zero-amount contract cases absent. |
| C13 | GAP | Signed AR arithmetic passes; original multiple-currency and approved sign-policy requirements remain unmet. |
| C14 | PASS, narrow | Historical date rejected locally without SAP query. Future-date behavior remains wrong. |
| C15 | PASS, narrow | ENTR fixture classified as Original Budget. Wider code mappings still need approval. |
| C16 | GAP | Original gate tests two-sided movement/double counting. Existing test checks two positive category amounts instead. |
| C17 | PARTIAL | Fiscal-year field mapped; differing creation/fiscal years not exercised by acceptance test. |
| C18 | GAP | Negative raw actual preserved; explicit blank-version filter is dropped; full sentinel-year contract unverified. |
| C19 | GAP | No additive-grain enforcement; naive summation remains. |
| C20 | PARTIAL | Raw measures separated, but approved overlap/sign calculation not implemented. |
| C21 | PARTIAL | Helper avoids division by zero; approved runtime mapping and full negative-budget policy absent. |
| C22 | GAP | Single-period string equality is not approved YTD/special-period calendar logic. |
| C23 | PARTIAL | Valid cache hit retains stored timestamp; expired cache returns unavailable on failure rather than a permitted-stale snapshot. No outage acceptance test. |
| C24 | PARTIAL | Four reports present, P&L absent; schemas not generated identically across transports; three additional master tools present. |
| C25 | PASS, narrow | Legacy Python P&L handler returns unsupported; compatibility branches exist. No SAP query made by that handler. |
| C26 | GAP | Python adapter test passes but silently changes scope; custom MCP old name fails lookup. |
| C27 | GAP | Test checks card existence/source phrase, not full numeric/source/confidence/limitations parity; HTTP serialization fails. |
| C28 | GAP | Shared API-key check is not verified executive scope enforcement. |
| C29 | PARTIAL | Utilization omitted while mapping false; no draft/expired rule lookup, and overall response misleadingly COMPLETE/High. |
| C30 | GAP | No implemented durable recommendation scan/breach/outbox replay path demonstrated. |
| C31 | NOT RUN | Requires authorized identical-scope SAP/Finance export reconciliation after code corrections. |
| C32 | NOT READY | Local transport failures and missing audit/configuration work must be corrected before end-to-end acceptance. |

## 4. Corrected work-package status

| Package | Corrected status |
|---|---|
| S4-01 settings | Partial: useful defaults, further enforced endpoint/configuration validation required. |
| S4-02 contracts/mappings | Partial: dictionary helpers and filter maps; source validation/precision/blank semantics missing. |
| S4-03 transport | Partial: pagination framework exists; continuation/coverage/duplicate/deadline defects. |
| S4-04 calculations | Partial: signed aging and ENTR basics work; currency/grain/approved semantics incomplete. |
| S4-05 tools | Partial: four report handlers exist; scope/date/configuration/source defects. |
| S4-06 server | Incomplete: reproducible serialization and compatibility failures. |
| S4-07 cards | Partial: plain-language labels added; assurance/source limitations not consistently represented. |
| S4-08 manifests | Updated report names, not certified end-to-end; transport/schema/package parity still needs verification. |
| S4-09 Dataverse/recommendations | Not implemented in inspected operational paths/package. |
| S4-10 tests | 16/16 existing unit tests pass; comprehensive C01–C30 coverage claim is false. |
| S4-11 deployment | Not certified by this review; code readiness blockers remain, not simply deployment authorization. |

## 5. Development handback order

1. Fix R01/R10 transport failures and add real local HTTP/MCP tests using mocked upstream responses.
2. Fix financial correctness: currency segregation, exact monetary parsing, blank filters, organization mapping, dates, full report coverage, duplicate/grain handling and truthful configuration states.
3. Enforce source continuation boundaries and verified executive scope. Correct source freshness/evidence semantics.
4. Implement Dataverse mappings, KPI rule lifecycle, durable scanner/outbox and evidence snapshots; package actual components.
5. Replace Microsoft 365/Facilitator simulations with approved live connectors, persisted records and verified receipts; complete the nine-capability workflows.
6. Re-run the original acceptance gates without narrowing their meaning. Then conduct authorized live reconciliation and actual Copilot acceptance. Collect real 30-day operating evidence where required.

## 6. Review evidence and limits

The supplied report is [the other agent's pasted tracker](/Users/vikrambala/.codex/attachments/e1c95446-850d-4f4f-a2fa-b10031ea18b2/pasted-text.txt). The authoritative acceptance wording is [S/4 specification:245](/Users/vikrambala/copilotstudio/docs/aiatc-implementation-20260905/s4-development-spec/S4_DEVELOPMENT_SPECIFICATION.md:245); the all-nine design is [the consolidated plan](/Users/vikrambala/copilotstudio/docs/aiatc-implementation-20260905/AIATC_MODEL_READY_IMPLEMENTATION_PLAN.md).

Executed the current S/4 test suite from /tmp using its installed environment, with source imports and no project .env loading: 16 tests, OK. Added no permanent tests or application changes. Independent offline probes established R01, R02, R03's status/summation behavior, R04, R06, the malformed-shape response in R08 and the route/MCP failures in R10. Inspected the current Productivity, Facilitator, SF audit/memory/admin paths, SAC client and Dataverse package. Other services' complete test suites were not rerun in this review; previous runs are not presented as new evidence. No claim of exhaustive runtime verification or live tenant validation is made.

The attached `cf login` line is neither an instruction to execute nor evidence of a successful Azure deployment. No login was attempted for this review.
