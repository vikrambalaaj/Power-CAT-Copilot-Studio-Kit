---
name: velora-cash-exposure
description: Summarize Velora receivables, payables, and overdue collections exposure from the supported S/4HANA reports.
---

# Cash exposure and collections brief

**Status:** Business skill specification for Velora One; not installed or deployed. Phase 1: Reuse reports; recommendation bridge blocked.

Use this specification to implement or review the business behavior. It does not grant access to the listed tools. Bind these instructions to the actual configured Copilot tools/topics; saving a SKILL.md alone does not register them.

Read [the shared runtime contract](../../RUNTIME_CONTRACT.md) for transport, evidence, identity, and state-changing behavior. Finding IDs refer to [the source review](../../REVIEW.md).

## Example request

“Show today’s AR over 90 days and overdue supplier exposure for company 1000.”

## Required context

Authorized company code, current key date, currency, customer/supplier and optional profit-center or segment filters.

## Existing tool bindings

`s4__get_receivables_aging`, `s4__get_payables_aging`, `s4__get_customer_master`.

Uppercase names are `operation` values for the productivity `/handoff` API; other names are MCP tool names. Do not pass Python implementation function names to a connector that exposes only the operation router.

## Workflow

1. Resolve names with supported master data when needed and retain source identifiers internally. Default company 1000 only within existing entitlement configuration.
2. Use the supported current-date aging tools. Reject historical/future key dates with the existing truthful unsupported response.
3. For AR over 90 days use bucket_91_180 plus bucket_over_180. Keep signed balances, credit balances, gross debit, and overdue exposure distinct.
4. Partition currencies; never add AED and USD without an approved conversion source. Confirm coverage.completionState before using an aggregate for a recommendation.
5. Describe AP overdue exposure as overdue exposure. It does not mean payable within the next seven days. Hold automated recommendations until R06 and R07 are repaired.

## Result

Separate AR/AP exposure tables, aging buckets, currency, company, key date, coverage, and proposed follow-up priorities grounded in returned rows.

## Engineering gaps

R06: finance bridge cannot import S4 code in its packaged container. R07: AP rule text mismatches its measurement. No SAP payment, credit-freeze, or collections write tool should be inferred.

## Acceptance scenarios

- **Synthetic AR 91–180=1.2m and over-180=1.3m; gross=10m:** Over-90 exposure is 2.5m, not gross receivables.
- **Two currencies returned:** Keep separate totals and show no unsupported combined amount.
- **Yesterday’s key date requested:** Report historical aging unavailable rather than relabel current data.
- **Incomplete source or AP overdue snapshot:** No complete recommendation; never call the AP snapshot next-seven-days cash needs.

## Implementation anchors

- [mcp-apps/ask-s4hana/s4hana_mcp/tools.py](../../../../mcp-apps/ask-s4hana/s4hana_mcp/tools.py)
- [mcp-apps/ask-s4hana/s4hana_mcp/report_calculations.py](../../../../mcp-apps/ask-s4hana/s4hana_mcp/report_calculations.py)
- [mcp-apps/ask-s4hana/s4hana_mcp/contracts.py](../../../../mcp-apps/ask-s4hana/s4hana_mcp/contracts.py)
- [mcp-apps/ask-facilitator/facilitator_mcp/finance_snapshot_service.py](../../../../mcp-apps/ask-facilitator/facilitator_mcp/finance_snapshot_service.py)

Relevant existing test filenames: `test_app.py`, `test_financial_error_propagation.py`, `test_review_company_boundary.py`. These are evidence of unit coverage, not live deployment certification.
