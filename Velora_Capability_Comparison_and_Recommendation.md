# Velora Executive AI Agent
## Capability coverage comparison and delivery recommendation

**Prepared:** 26 August 2026  
**Scope compared:** Original Velora requirement; Velora internal delivery as at 21 August 2026; Velora longer-term direction; Protiviti proposal; MeshX SOW

## 1. Executive conclusion

Velora's internal team appears closest to the required **30 September 2026 issuance/go-live date** because it already has meaningful functionality in production or in build. Based on the 21 August weekly update, five capabilities are demonstrably covered (C1, C2, C4, C6 and C7), C3 is in progress, C9 is partial, and C5/C8 are described as next-phase items even though Sprint 3 work was planned. The weekly update's headline says “six covered”; however, its C3 detail says the structured evaluation build was still under way. For decision-making, this report therefore treats C3 as **on track, not yet complete**.

Protiviti offers the broadest **end-to-end contractual design**: it claims all nine capabilities plus discovery, architecture, ALM, testing, UAT, evidence, security integration, handover and hypercare. Its most useful incremental contribution is not duplicating C1/C2/C4/C6/C7, but closing or independently assuring C3, C5, C8 and C9 and strengthening test/evidence/handover. However, the proposal's stated schedule—build complete at end September, issuance at end October and 30-day logs at end November—does **not** match Velora's SOR milestones of build by end August, executive issuance by end September and logs by end October.

MeshX is not a full alternative agent implementation. It provides a governed data/MCP backend for **3–5 predefined CEO questions**, with data-product metadata, RBAC, source attribution and lineage. It directly supports C1 and the data/audit portion of C9; it does not cover the other seven capabilities and explicitly excludes the Copilot Studio agent. MeshX's strongest incremental value is a governed semantic/data-product layer (359 existing data products and 438 coded business rules), data-product-level access control, and lineage—not broader coverage of the nine capabilities.

The vendor proposals are presently **architecturally inconsistent**:

- Protiviti makes SharePoint, Fabric/OneLake, Azure AI Search and SAP OData core to Phase 1, and describes MeshX integration as fast-follow.
- MeshX states that Phase 1 routes exclusively through MeshX Foundation via MCP and excludes SharePoint, M365 and all non-Foundation sources.
- Protiviti plans end-September build completion and end-October issuance; MeshX commits to an integrated production go-live on 30 September.

These are not wording differences. They change the source-of-truth, integration contract, testing plan, security model and acceptance criteria. A joint solution should not be awarded until one signed architecture, milestone baseline and RACI supersedes the conflicting statements.

## 2. Baseline: the nine original capability metrics

| ID | Original capability | Minimum Phase 1 metric / acceptance bar |
|---|---|---|
| C1 | Enterprise Data Query | Query at least one approved enterprise system or representative dataset; enforce existing permissions. |
| C2 | Proactive Recommendation Engine | Generate proactive risks/opportunities/recommendations; retain recommendation examples and a 30-day log by end October 2026. |
| C3 | Evaluation Engine | Evaluate proposals, strategies, budgets or expenditure against agreed criteria; retain examples and a 30-day interaction log. |
| C4 | Briefing & Synthesis | Produce an executive brief/digest/synthesis with source references. |
| C5 | Agent Creation | Executive creates recurring-task sub-agents in natural language without IT involvement, with edit/pause/retire controls and creation logs. |
| C6 | Institutional Memory | Approved meetings and/or documents searchable from go-live; email indexing is not mandatory for Phase 1. |
| C7 | Meeting Intelligence | Ingest and summarise approved notes/minutes; manual upload is sufficient for Phase 1. |
| C8 | Peer Benchmarking | Benchmark against at least one approved peer/source. |
| C9 | Decision Traceability | Material recommendations carry reasoning, sources and confidence where applicable; secured logs and CSV export are required. |

Cross-capability acceptance also requires source/fact versus synthesis separation, auditable logs, least-privilege access, UAT/evidence packs, deployment readiness and handover documentation.

## 3. Coverage comparison

**Status meaning:** Complete = evidenced as live/covered; On track = in build with a dated plan; Partial = only part of the acceptance metric is met; Target = intended longer-term outcome without a validated delivery commitment in the supplied documents; Claimed = vendor proposal commitment, not delivered evidence.

| Cap. | Velora internal—current (21 Aug) | Velora internal—long-term direction | Protiviti proposal | MeshX SOW | Incremental interpretation |
|---|---|---|---|---|---|
| C1 | **Complete.** Six SAP queries live: headcount, Emiratisation, receivables, payables, P&L and budget variance, with delegated identity. | **Target.** Extend governed enterprise data through SAP BDC/BTP and use AI Foundry where orchestration is needed. Exact post-September datasets and dates are not defined in the supplied baseline. | **Claimed full.** SharePoint/OneLake RAG, SAP OData via Logic Apps/APIM, Entra trimming and Purview labels. Representative-data fallback allowed. | **Claimed constrained full.** Foundation MCP for agreed 3–5 questions; data products, schema, metadata, lineage and data-product RBAC. | Protiviti adds source breadth and a formal RAG/lakehouse pattern but duplicates a working SAP path. MeshX adds the clearest semantic lineage and governed-data layer, but only for a narrow question set. |
| C2 | **Complete.** Daily scan live on six KPIs; reasoning/sources/confidence written to C9 log. | **Target.** Enrich signals and recommendations using BDC/Foundry. | **Claimed full.** Foundry skill scheduled through Power Automate over internal and Bing-grounded signals; feeds 30-day log. | **Not covered.** | Protiviti can add broader internal/external signals and reusable skill packaging, but the Phase 1 minimum is already live internally. |
| C3 | **On track, not complete.** Structured evaluation was under way in Sprint 3; 28 August code freeze forecast. | **Target.** Broader evaluation criteria and datasets through BDC/Foundry. | **Claimed full.** Foundry skill scoring submissions against executive criteria on lakehouse data. | **Not covered.** | Protiviti provides a credible fallback/independent build for a remaining internal delivery item. This is one of its stronger incremental areas. |
| C4 | **Complete.** Executive inbox connected for briefs, digests and pre-meeting synthesis. | **Target.** Broader sources, automation and personalisation. | **Claimed full.** Foundry briefing skill with citations through Outlook/Teams. | **Not covered.** | Mainly duplicate Phase 1 coverage; possible value from formalised citations, templates and QA. |
| C5 | **Deferred / gated.** Weekly update labels it next phase; governed executive-journey build was due to start 24 August. Full interpretation depends on PMO confirmation that creation is “without IT involvement.” | **Target full.** Governed natural-language creation with lifecycle controls after governance is settled. | **Claimed full.** Copilot Studio maker natural-language create/edit/pause/retire, with Dataverse event logging. | **Not covered.** | Protiviti covers more than the current internal state, but it does not remove the underlying PMO/governance interpretation or tenant-control decision. Contract acceptance must test the executive experience, not merely maker functionality. |
| C6 | **Complete.** Approved notes, transcripts and documents searchable; chat memory persists across sessions. | **Target.** Broader institutional corpus, retention and lifecycle controls. | **Claimed full.** SharePoint/OneLake indexed in Azure AI Search from go-live; email indexing excluded. | **Not covered for MVP.** Foundation could host document products later, but this is not contracted. | Protiviti adds an enterprise search/index architecture but may duplicate the internal search/memory solution and introduce another index/lakehouse to operate. |
| C7 | **Complete and deeper than the minimum.** Delegated Graph transcript capture, Facilitator MCP, recap-to-library and action-chaser flows. | **Target.** Broader meeting channels/automation subject to privacy governance. | **Claimed full at minimum.** Teams transcript via Graph or manual upload; live telephony/non-Teams join excluded. | **Not covered.** | Internal scope is already richer than Protiviti's stated Phase 1 bar. |
| C8 | **Deferred / in planned build.** Weekly update labels it next phase; peer/source selected and a grounded Sprint 3 topic planned. | **Target full.** Deeper multi-source peer benchmarking through approved sources and BDC/Foundry. | **Claimed full at minimum.** Foundry benchmarking skill against at least one approved external source; Velora pays/approves the source. Expanded benchmarking is later phase. | **Not covered.** | Protiviti covers more than the evidenced current state, but only to the same one-source minimum that the internal plan targets. It is a useful assurance/fallback area, not a materially richer Phase 1 outcome. |
| C9 | **Partial.** Dataverse audit store and SAP Read-Access Log are live; Purview access and ADD reporting format remain open. | **Target full.** Dual audit, confirmed evidence schema, CSV/export and expanded governance controls. | **Claimed full.** Dataverse spine, reasoning/source/confidence, encryption/hashing and CSV export. Purview/Defender configuration remains a Velora dependency. | **Partial / enabling.** Source and data-domain attribution, lineage, identity/audit logging of who queried what and when. Agent reasoning/confidence and end-to-end ADAA evidence remain outside MeshX's scope. | Protiviti most clearly strengthens end-to-end evidence engineering and export, but cannot remove Velora's Purview/security dependency. MeshX provides deeper data lineage than either current build or Protiviti explicitly guarantees, but not full decision traceability. |

### Quantified view

| Scope | Full/complete | In progress or partial | Deferred/not covered | Important qualification |
|---|---:|---:|---:|---|
| Velora current, evidenced 21 Aug | 5 | 2 | 2 | Weekly headline says six covered, but C3 text says still in build. |
| Velora long-term | 9 target | — | — | Direction is stated, but a capability-by-capability delivery baseline, dates and acceptance evidence were not supplied. |
| Protiviti | 9 claimed | — | — | Proposal commitment, not delivered evidence; timeline is one month later than the SOR for issuance/logs. |
| MeshX | 1 constrained (C1) | 1 enabling/partial (C9) | 7 | C1 is limited to 3–5 predefined questions; Copilot agent and seven capabilities are outside scope. |

## 4. What Protiviti covers beyond Velora internal

Protiviti's genuinely incremental contribution is concentrated in the following areas:

1. **C5 end-to-end design claim:** natural-language agent creation plus edit/pause/retire and Dataverse lifecycle logging. Velora's internal implementation is gated/deferred.
2. **C8 committed MVP implementation:** a defined Foundry benchmarking skill against one approved source. Velora has a source and planned build, but no completed evidence in the 21 August update.
3. **C3 delivery assurance:** a dedicated evaluation skill and an alternative team if the internal Sprint 3 item slips.
4. **C9 evidence engineering:** structured traceability, field-level protection, CSV export and capability-level evidence preparation. This strengthens delivery discipline even though the Dataverse spine already exists internally.
5. **Independent delivery controls:** one-week discovery, traceability matrix, parallel agent/data workstreams, formal SIT/UAT, negative-path and access-control testing, defect management, handover/runbooks and hypercare.
6. **Broader Microsoft data/search pattern:** SharePoint + Fabric/OneLake + AI Search alongside SAP. This may be valuable for scale, but is a new operational footprint unless Velora confirms these services are already provisioned, populated, governed and supported.

Protiviti does **not** clearly cover more in C1, C2, C4, C6 or C7 at the Phase 1 acceptance level; most of that scope duplicates functions already live or in a more advanced internal form. It also does not resolve the external blockers on the critical path: PMO interpretation for C5, Purview/Defender provisioning, SAP/data access, approvals, and final ADAA format.

## 5. What MeshX covers beyond Protiviti and Velora internal

MeshX is deeper in a narrow data-governance layer:

- A ready catalogue of **359 data products and 438 coded business rules**.
- Explicit data-product schema, metadata and endpoint documentation for the agent consumer.
- Source and data-domain attribution plus lineage returned through MCP.
- RBAC enforced at data-product level, with Entra/OAuth and least privilege.
- A measurable accuracy test for 3–5 agreed CEO questions.
- Fixed-price, milestone-linked responsibility for the MCP/data layer, including a runbook.

This can be strategically useful if Velora wants Foundation to become the governed semantic contract between AI agents and enterprise data. It is not broader business-capability coverage. It should be described as **data foundation and C1/C9 enablement**, not “coverage of the nine capabilities.”

Against the current internal design, MeshX also creates a decision: should the working SAP-direct MCP route remain the system path, be replaced by Foundation, or operate in parallel? Running both without a clear source-of-truth and ownership model risks duplicated integration, inconsistent answers, extra audit reconciliation and avoidable support cost.

## 6. Resource and bandwidth implications

### Velora internal critical bandwidth

The weekly update states that September is reserved for system test, UAT, deployment and evidence, with no float for build work that slips. Velora should protect, at minimum:

- A single accountable product owner / decision-maker for scope and acceptance.
- Copilot/agent engineering capacity for C3/C5/C8 and defect correction.
- SAP/BTP/integration capacity for OData and private-network cutover.
- Security/identity capacity for Purview, Defender, Entra, privacy and CISO sign-off.
- QA/UAT lead plus CEO/proxy testing slots.
- Evidence/governance owner for C9 schema, 30-day logs and ADAA packaging.
- Release/operations owner for ALM, monitoring, runbooks and post-go-live support.

The highest risk is not raw developer capacity; it is **decision and specialist availability at the same time** during late August and September.

### Protiviti impact

Protiviti proposes five roles: an onsite Program Director (~80 hours), offshore Solution/Technical Architect, Copilot Studio/Agent Developer, Integration & Data Engineer and QA Analyst. This adds useful specialist concurrency but still requires Velora to provide environments, SAP/SharePoint/MeshX access, Purview/Defender configuration, weekly IT/Cyber/SAP/PMO availability, three-working-day reviews and UAT/business validation.

If Protiviti is asked to rebuild all nine capabilities rather than close gaps, Velora will absorb significant architecture review, data mapping, security, testing and reconciliation overhead while the internal team is trying to deploy its own build. A full parallel build is therefore likely to **increase** Velora bandwidth pressure before it reduces delivery risk.

### MeshX impact

MeshX prices 86 person-days: Platform/DevOps Engineer 20, Data Architect 12, Data Engineer 20, Security Engineer 4, Program Manager 20 and CTO/TAM 10. The Program Manager plus CTO/TAM allocation is 30 of 86 days, indicating a coordination-heavy workstream. MeshX additionally depends on Velora for production infrastructure, CISO approval, Entra registrations/admin consent, data-owner approvals, licensing, UAT and CEO/proxy availability. Its SOW flags the infrastructure lead's three-week absence and zero schedule float. Optional two-week hypercare is excluded from the AED 413,000 MVP price.

### Combined-vendor impact

A Protiviti + MeshX delivery requires one integrated product backlog, one architecture, one test calendar, one defect taxonomy, one RACI and one acceptance authority. Without these, Velora becomes the integration manager between two conflicting contracts. A dedicated Velora integration lead/architect and PM is therefore mandatory if both vendors are used.

## 7. Recommended commercial/delivery options

### Option 1 — Internal-led completion with targeted assurance (recommended)

Keep the existing SAP-direct Microsoft agent as the Phase 1 production path. Protect the internal team through September and buy only targeted external support for:

- independent readiness assessment of the nine acceptance tests;
- C3/C5/C8 finishing support if dated checkpoints slip;
- C9 evidence schema, CSV export and ADAA pack;
- security/negative-path testing, UAT management and operational handover.

This preserves the delivered investment, minimises architecture change near go-live and directs external spend to the actual gaps.

**Go/no-go checkpoints:** confirm C3 smoke test, written C5 interpretation/fallback, C8 one-source demo, private-path test, and C9 CSV export by a single executive gate no later than the end-August code freeze. Any failed checkpoint activates pre-agreed vendor support.

### Option 2 — Protiviti as gap-closure and assurance partner

Renegotiate Protiviti's scope away from a second full build. Limit it to C3, C5, C8, C9 plus independent SIT/UAT/evidence/handover. Require reuse of the live internal SAP/BTP/Dataverse components unless an architecture board approves a change. Remove Fabric/OneLake/AI Search from the critical path unless Velora proves those services are already production-ready and strategically chosen.

Contractually correct the dates to the SOR baseline and link payment to capability evidence, not component completion. Require named resource availability and effort by role; the current proposal provides role structure but not a complete effort/capacity schedule.

### Option 3 — MeshX as a controlled strategic data pilot

Use MeshX only if Velora has made a strategic decision that Foundation will be the governed data-product layer for future agents. Treat the 3–5 CEO questions as a parallel controlled pilot or a clearly defined C1 subset, not as the whole Phase 1 solution. Define whether Foundation replaces or complements SAP-direct MCP, and benchmark accuracy, latency, access trimming, lineage and operating cost against the live route.

Do not represent this option as nine-capability completion. Add mandatory hypercare and future data-product maintenance terms if it is to become production-critical.

### Option 4 — Combined Protiviti + MeshX end-to-end build

Proceed only after a joint contract addendum resolves:

1. exclusive Foundation routing versus Protiviti's SharePoint/OneLake/SAP architecture;
2. 30 September go-live versus Protiviti's end-October issuance;
3. source-of-truth and data-quality ownership;
4. MCP connector specification, environments and security responsibility;
5. end-to-end C9 ownership for reasoning, confidence, lineage and CSV evidence;
6. integrated testing, defect attribution, acceptance and hypercare;
7. consequences if one party's dependency delays the other.

This is the highest-cost and highest-coordination option and is not recommended for the September deadline unless Velora deliberately replaces the internal route.

## 8. Immediate clarification requests

Before award or scope confirmation, Velora should obtain written answers to the following:

1. **Milestone baseline:** confirm the authoritative dates are build by 31 August, issuance/go-live by 30 September, and 30-day logs by 31 October 2026. (“31 September” is not a valid calendar date.)
2. **Current truth:** revalidate the 21 August status as of 26 August, particularly C3, C5, C8, OData/private networking and Purview.
3. **Long-term architecture:** approve whether SAP BDC/BTP, Fabric/OneLake, MeshX Foundation, or a defined combination is the target data plane.
4. **Vendor integration contradiction:** require Protiviti and MeshX to submit one signed architecture and schedule if positioned as a joint solution.
5. **C5 acceptance:** get PMO confirmation of what “without IT involvement” permits and test the CEO experience, lifecycle controls and audit events.
6. **C9 acceptance:** define the minimum evidence schema and identify which party owns reasoning/confidence, data lineage, platform audit, CSV export and final ADAA pack.
7. **Resource commitment:** obtain named availability by week from internal teams and vendors, including Velora security, SAP, data owners, QA/UAT and CEO/proxy time.
8. **Operations:** price mandatory hypercare and ongoing support for every production-critical layer; MeshX hypercare and Protiviti BAU managed service are not included in the stated MVP scopes.

## 9. Source basis and limitations

- **Velora Statement of Requirements v1.0**, 20 July 2026: original nine capabilities, MVP metrics, milestones, supplier resource requirements, acceptance criteria and evidence matrix (pp. 3–9).
- **Velora AgenticAD Weekly Update**, week ending 21 August 2026: internal status, architecture, schedule, prerequisites, RAID and capacity position.
- **Protiviti Technical Proposal**: capability traceability and architecture (pp. 11, 33–38), approach and testing (pp. 29–31, 46–50), assumptions/dependencies (pp. 53–55, 69), team (pp. 57–58), and stated milestones (pp. 2, 5, 7, 15, 50).
- **MeshX SOW**, 16 August 2026: fixed C1/C9-enabling scope, 3–5-question acceptance, exclusions, milestones, responsibilities, dependencies, AED 413,000 price and 86-day resource estimate.
- **Colleague capability comparison**, 26 August 2026: used as a reference and cross-check only. Its conclusions were independently reassessed against the underlying source documents.

This is a document-based scope assessment, not a technical verification of the live environments. “Complete” for Velora reflects the supplied weekly update; “claimed” for vendors reflects proposal/SOW language and should not be treated as delivered evidence.
