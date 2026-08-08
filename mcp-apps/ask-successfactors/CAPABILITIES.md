# Nine-capability blueprint

## Scope

All nine capabilities are part of the production target. The two SAP MCP servers provide the authoritative operational facts; Microsoft 365 and governed platform services provide scheduling, memory, meetings, creation workflows, benchmarking, and audit.

| # | Capability | Primary implementation | SAP dependency | Required output | Production acceptance |
|---|---|---|---|---|---|
| 1 | Enterprise data query | Agent router plus both MCP servers | SuccessFactors and S/4HANA | Answer, source object, as-of time, filters, confidence, correlation ID | All six executive queries return permission-trimmed, cited results |
| 2 | Proactive recommendation | Scheduled/event trigger, KPI rules, notification policy | Both MCP servers | Material change, business impact, recommended next step, evidence | A threshold breach creates one deduplicated recommendation and records delivery |
| 3 | Evaluation engine | Deterministic policy/rules layer before narrative generation | Both MCP servers | Actual, target, variance, status, rule version | Replaying the same facts and rule version produces the same status |
| 4 | Briefing and synthesis | Microsoft 365 orchestration over mail, calendar, documents, memory, and SAP facts | Both MCP servers as needed | Executive brief with decisions, risks, actions, and citations | Pre-meeting brief contains only authorized and current evidence |
| 5 | Agent creation | Governed template catalog and approval workflow | Optional tool reuse from both servers | Draft agent specification, owner, data scope, tools, risk tier, approval | No agent is published without owner, security review, tests, and approval |
| 6 | Institutional memory | Approved SharePoint/knowledge store with retention and ACL trimming | Stores references, not unrestricted SAP extracts | Decision, context, owner, date, evidence links, supersession state | Successors can retrieve authorized decisions with provenance and retention applied |
| 7 | Meeting intelligence | Teams transcript/notes ingestion, action extraction, task synchronization | Both MCP servers for fact checks | Summary, decisions, actions, owners, due dates, unresolved questions | Consent, transcript access, action confirmation, and write-back are verified |
| 8 | Peer benchmarking | Approved benchmark dataset and normalization service | S/4HANA metrics provide internal comparison values | Internal metric, peer cohort, percentile, period, methodology, caveats | Every benchmark names cohort, period, currency/unit normalization, and license |
| 9 | Decision traceability | Unified audit sink with correlation IDs and retention | Both MCP calls emit audit metadata | User, purpose, tool, filters, sources, response hash, decision link | An auditor can reconstruct a decision without exposing secrets or excess personal data |

## Capability behavior

### 1. Enterprise data query

- Route workforce questions to SuccessFactors and finance questions to S/4HANA.
- Call both servers only for a cross-domain question, such as revenue per employee.
- Preserve source-level access controls; never broaden access in the agent.
- Label sampled, incomplete, stale, or failed data explicitly.

### 2. Proactive recommendation

- Evaluate only the six approved KPIs initially.
- Trigger on a material threshold, trend, forecast breach, or owner-defined event.
- Deduplicate by metric, organization, period, rule version, and breach state.
- Require executive confirmation before any downstream write or workflow action.

### 3. Evaluation engine

- Keep calculations deterministic and versioned outside the language model.
- Return actual, target, absolute variance, percentage variance, and status.
- Record the rule version and input snapshot identifiers in the audit event.
- Use the language model to explain results, not to invent calculations.

### 4. Briefing and synthesis

- Combine calendar context, approved documents, institutional memory, and live SAP facts.
- Separate fact, inference, recommendation, and unresolved question.
- Include citations next to material claims.
- Apply a freshness window appropriate to each source.

### 5. Agent creation

- Create a draft from an approved template; do not permit autonomous publication.
- Require a named business owner, technical owner, permitted users, data classification, tool allowlist, and lifecycle dates.
- Run security, privacy, quality, and red-team checks before approval.
- Record every approval and deployment version.

### 6. Institutional memory

- Store concise decision records rather than unrestricted conversation transcripts.
- Retain provenance links to the source brief, meeting, and SAP correlation IDs.
- Honor source ACLs, legal holds, retention, deletion, and supersession.
- Prevent one executive's private material from becoming organization-wide memory.

### 7. Meeting intelligence

- Confirm recording/transcription policy and participant notice.
- Extract proposed actions, then require confirmation before creating tasks.
- Resolve each person and date explicitly; do not guess owners or deadlines.
- Link the meeting record to the resulting decision and action audit entries.

### 8. Peer benchmarking

- Use only licensed, approved, versioned benchmark data.
- Normalize currency, period, organization size, industry, geography, and accounting basis.
- Suppress cohorts too small to protect peer confidentiality.
- Present methodology and caveats with every comparison.

### 9. Decision traceability

- Generate one correlation ID at the user request and propagate it through both MCP servers and downstream workflows.
- Log authorization context, purpose, tool name, safe filter summary, source identifiers, latency, outcome, and response hash.
- Never log passwords, tokens, full prompts containing personal data, or unrestricted result rows.
- Link final decisions to supporting evidence and later superseding decisions.

## Ownership model

| Role | Accountability |
|---|---|
| Executive sponsor | Outcomes, acceptable risk, and adoption |
| Product owner | Capability scope and prioritization |
| SuccessFactors owner | OData entities, RBP, data quality, and workforce semantics |
| S/4HANA finance owner | CDS/OData services, PFCG roles, ledger and currency semantics |
| Microsoft 365 owner | Copilot, Teams, Graph, SharePoint, and Purview configuration |
| Security and privacy | Identity, secrets, PDPL, logging, retention, and review |
| Audit/compliance | Traceability schema, evidence retention, and control testing |
