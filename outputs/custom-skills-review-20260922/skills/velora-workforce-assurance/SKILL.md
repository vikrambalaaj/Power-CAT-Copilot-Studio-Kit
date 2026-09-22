---
name: velora-workforce-assurance
description: Answer Velora workforce size, movement, composition, and reconciliation questions using SuccessFactors aggregates.
---

# Workforce assurance

**Status:** Business skill specification for Velora One; not installed or deployed. Phase 1: Reuse aggregate tools; hold scoped attrition.

Use this specification to implement or review the business behavior. It does not grant access to the listed tools. Bind these instructions to the actual configured Copilot tools/topics; saving a SKILL.md alone does not register them.

Read [the shared runtime contract](../../RUNTIME_CONTRACT.md) for transport, evidence, identity, and state-changing behavior. Finding IDs refer to [the source review](../../REVIEW.md).

## Example request

“Explain headcount and net growth for Ground Operations this quarter.”

## Required context

Company, department/division/business unit where supported, exact period, and requested metric. Use verified caller identity and the existing confidentiality-consent gate.

## Existing tool bindings

`sf__get_headcount`, `sf__get_joiners`, `sf__get_leavers`, `sf__get_joiners_leavers_trend`, `sf__get_workforce_demographics`, `sf__get_attrition`.

Uppercase names are `operation` values for the productivity `/handoff` API; other names are MCP tool names. Do not pass Python implementation function names to a connector that exposes only the operation router.

## Workflow

1. Resolve metric and supported filters before calling the verified workforce card endpoint or the corresponding MCP function. Some movement tools only accept company; do not imply department-level filtering when the function lacks that parameter.
2. Keep total workforce and active workforce distinct. Reconcile distinct people rather than count EmpJob history rows. Preserve unknown demographic classifications.
3. For a movement summary, use identical start/end dates and company for joiners and leavers. Label attrition as period leavers/current active headcount, not annualized.
4. Hold business-unit attrition and company-scoped UAE attrition until numerator/denominator scope is repaired (R05). Do not silently return an organization-wide number for a narrower request.

## Result

Metric, value, exact scope, period/as-of date, definition, completeness/warnings, and actual source. Native workforce card where supported; otherwise a small table.

## Engineering gaps

R05: scoped attrition is inconsistent. The card API and native MCP routes both need end-to-end connector validation. Historical active status is not a complete historical snapshot.

## Acceptance scenarios

- **Multiple EmpJob rows for the same employee:** Distinct headcount reconciles and duplicate job rows do not inflate it.
- **Ask for business-unit attrition before R05 is fixed:** Explain that this scoped rate cannot be verified; do not substitute a company-wide numerator.
- **Missing nationality or gender mapping:** Show unknown/unclassified counts separately.
- **Consent absent or source returns partial data:** Respect the backend gate; show partial scope explicitly and never fabricate totals.

## Implementation anchors

- [mcp-apps/ask-successfactors/successfactors_mcp/successfactors_tools.py](../../../../mcp-apps/ask-successfactors/successfactors_mcp/successfactors_tools.py)
- [mcp-apps/ask-successfactors/successfactors_mcp/successfactors_client.py](../../../../mcp-apps/ask-successfactors/successfactors_mcp/successfactors_client.py)
- [mcp-apps/ask-successfactors/successfactors_mcp/successfactors_server.py](../../../../mcp-apps/ask-successfactors/successfactors_mcp/successfactors_server.py)

Relevant existing test filenames: `test_app.py`, `test_leavers_attrition_trend.py`, `test_policy_and_drilldown.py`. These are evidence of unit coverage, not live deployment certification.
