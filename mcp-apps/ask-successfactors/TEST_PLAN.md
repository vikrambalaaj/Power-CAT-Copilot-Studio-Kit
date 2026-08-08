# Production acceptance test plan

## Six-query functional acceptance

| Query | Required tests |
|---|---|
| Headcount | Active/inactive boundary, effective date, multiple job records, filters, total versus breakdown reconciliation, unauthorized organization |
| Emiratisation | Approved denominator, aggregate numerator, target comparison, zero denominator, small-group suppression, unauthorized organization |
| Receivables | Aging boundaries, key date, partial payment, dispute/block status, currency conversion, unauthorized company code |
| Payables | Aging boundaries, due-soon horizon, payment block, special items, currency conversion, unauthorized supplier/company code |
| P&L | Ledger, fiscal period, hierarchy, actual/plan/version, currency type, closed/open period, subtotal reconciliation |
| Budget variance | Missing budget, zero budget, favorable sign convention, plan version, driver materiality, subtotal reconciliation |

## Nine-capability acceptance

1. **Enterprise query:** each query returns a source, as-of time, filters, quality state, and correlation ID.
2. **Proactive recommendation:** one material breach generates one deduplicated notification; recovery closes or updates it without duplicates.
3. **Evaluation engine:** fixed facts plus fixed rule version produce identical scores and statuses across repeated runs.
4. **Briefing and synthesis:** a pre-meeting brief separates facts, inferences, recommendations, and open questions with citations.
5. **Agent creation:** an unauthorized user cannot create or publish; an approved draft passes owner, scope, risk, and test gates before publication.
6. **Institutional memory:** authorized decisions are retrievable with provenance; denied and expired content remains unavailable.
7. **Meeting intelligence:** consent, transcript authorization, decision extraction, action confirmation, owner resolution, and task write-back work end to end.
8. **Peer benchmarking:** cohort, period, normalization, methodology, licensing, and small-cohort suppression appear in every answer.
9. **Decision traceability:** an auditor can reconstruct tool calls, evidence, rule versions, approvals, final decision, and supersession from the correlation ID.

## Security and privacy tests

- Reject missing, invalid, expired, and cross-environment MCP credentials.
- Reject disallowed hosts, origins, schemes, redirects, methods, entities, expansions, and oversized filters.
- Confirm SSRF defenses and egress allowlists.
- Verify RBP and PFCG denials with real negative-role test users.
- Confirm secrets and tokens never appear in errors, telemetry, traces, files, or packages.
- Confirm employee, customer, and supplier fields are minimized and redacted in logs.
- Validate PDPL aggregation and small-group suppression.
- Test prompt injection in SAP text, documents, emails, meetings, and benchmark content.
- Confirm write-capable workflows require confirmation, idempotency, and approval.

## Resilience tests

- SuccessFactors unavailable while S/4HANA remains available, and the reverse.
- Timeout, throttling, malformed JSON, partial page, stale cache, duplicate event, and lost response.
- Cache disabled, miss, hit, TTL expiry, bounded eviction, mutation isolation, error bypass, simultaneous-miss coalescing, effective-identity separation, and successful-write invalidation.
- Currency, fiscal calendar, timezone, and daylight-saving boundaries.
- Audit sink unavailable without silently losing the business response or audit event.
- Retry behavior does not duplicate notifications, tasks, approvals, or decisions.

## Scheduled prompt tests

- Each recurrence observes `Asia/Dubai`, configured workdays, quiet hours, holidays, and daylight/timezone conversion.
- The target executive comes from `VELORA_EXECUTIVE_USER_ID`; no personal identifier is embedded in source or trigger definitions.
- Replaying a trigger with the same deduplication key does not produce a second message.
- Unknown prompt IDs and malformed trigger payloads are rejected.
- Missing Calendar, Email, Teams, Planner, To Do, memory, or SAP access is disclosed instead of fabricated.
- Daily, midday, end-of-day, and weekly outputs use the matching card and retain text fallback.
- Scheduled runs never send email, create tasks, modify meetings, or update SAP.
- Teams delivery failures retry safely and produce an operator alert after the configured limit.

## Executive acceptance scenarios

- “What is total headcount and Emiratisation status today?”
- “Show receivables aging and the three largest material exposures.”
- “What payments fall due in the next 30 days?”
- “Summarize P&L versus last period and explain supported movements.”
- “Where are we over budget, and which returned dimensions support the variance?”
- “Prepare my meeting brief using current SAP facts and relevant prior decisions.”
- “Alert me only when an approved KPI breaches its materiality threshold.”
- “Compare our approved metric with the licensed peer cohort and explain the methodology.”
- “Show the evidence and approvals behind this decision.”

## Exit criterion

Production coverage is achieved only when all mandatory tests pass, residual risks are accepted by named owners, both MCP servers are independently operable, and the published agent package checksum matches the approved release artifact.
