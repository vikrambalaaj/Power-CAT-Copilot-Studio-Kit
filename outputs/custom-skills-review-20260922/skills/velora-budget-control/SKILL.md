---
name: velora-budget-control
description: Explain Velora budget, commitments, actuals, available balance, and specific budget movements.
---

# Budget consumption and movement explanation

**Status:** Business skill specification for Velora One; not installed or deployed. Phase 1: Reuse reports; recommendation mapping deliberately blocked.

Use this specification to implement or review the business behavior. It does not grant access to the listed tools. Bind these instructions to the actual configured Copilot tools/topics; saving a SKILL.md alone does not register them.

Read [the shared runtime contract](../../RUNTIME_CONTRACT.md) for transport, evidence, identity, and state-changing behavior. Finding IDs refer to [the source review](../../REVIEW.md).

## Example request

“Explain budget consumption for this funds center and show the transfer documents behind it.”

## Required context

Financial management area, funds center, commitment item, fiscal year, period, version, and currency; map company to FMA using approved mappings rather than assuming equivalence.

## Existing tool bindings

`s4__get_budget_consumption`, `s4__get_budget_transfers`, `s4__get_cost_center_master`.

Uppercase names are `operation` values for the productivity `/handoff` API; other names are MCP tool names. Do not pass Python implementation function names to a connector that exposes only the operation router.

## Workflow

1. Use BudgetConsumSummary via s4__get_budget_consumption for totals and available balance. Preserve the provider’s calculation components and sign conventions.
2. Only use BudgetTransfer via s4__get_budget_transfers when the user requests movements, transfers, supplements, or returns. Its records are not a substitute for consumption totals.
3. Keep fiscal period, BudgetPeriod, funds center, cost center, and financial management area distinct; report unsupported filters.
4. Treat recommendations as blocked while the finance snapshot service returns unapproved_mapping. Do not infer permission to transfer funds from the read-only transfer report.

## Result

Budget/actual/commitment/available summary with currency and fiscal scope, followed by requested movement evidence and source coverage.

## Engineering gaps

Budget recommendation mapping is explicitly unapproved in the adapter. No budget transfer execution is implemented by the exposed S4 report tools.

## Acceptance scenarios

- **Overall budget question:** Call consumption summary first, not transfer history.
- **Movement drilldown:** Return requested transfer documents without double-counting into summary totals.
- **Budget alert requested while mapping is unapproved:** Report blocked configuration and create no recommendation.
- **Funds-center and cost-center names resemble each other:** Use verified mappings or ask for the intended entity; do not substitute.

## Implementation anchors

- [mcp-apps/ask-s4hana/s4hana_mcp/tools.py](../../../../mcp-apps/ask-s4hana/s4hana_mcp/tools.py)
- [mcp-apps/ask-s4hana/s4hana_mcp/field_mappings.py](../../../../mcp-apps/ask-s4hana/s4hana_mcp/field_mappings.py)
- [mcp-apps/ask-s4hana/s4hana_mcp/report_calculations.py](../../../../mcp-apps/ask-s4hana/s4hana_mcp/report_calculations.py)
- [mcp-apps/ask-facilitator/facilitator_mcp/finance_snapshot_service.py](../../../../mcp-apps/ask-facilitator/facilitator_mcp/finance_snapshot_service.py)

Relevant existing test filenames: `test_app.py`, `test_reviewer_findings.py`, `test_finance_recommendations.py`. These are evidence of unit coverage, not live deployment certification.
