---
name: velora-board-brief
description: Assemble a concise Velora leadership brief combining workforce, supported finance, and actual executive commitments.
---

# Cross-system executive board brief

**Status:** Business skill specification for Velora One; not installed or deployed. Phase 2: New orchestration over existing verified reads.

Use this specification to implement or review the business behavior. It does not grant access to the listed tools. Bind these instructions to the actual configured Copilot tools/topics; saving a SKILL.md alone does not register them.

Read [the shared runtime contract](../../RUNTIME_CONTRACT.md) for transport, evidence, identity, and state-changing behavior. Finding IDs refer to [the source review](../../REVIEW.md).

## Example request

“Prepare a board brief on workforce, cash exposure, budget, and open actions.”

## Required context

Audience, exact company and time windows, requested sections, and disclosure level. Specify current versus historical source limitations.

## Existing tool bindings

`sf__get_headcount`, `sf__get_emiratisation_kpi`, `s4__get_receivables_aging`, `s4__get_payables_aging`, `s4__get_budget_consumption`, `GET_MEETING_ACTION_TRACKER`, `LIST_RECOMMENDATIONS`.

Uppercase names are `operation` values for the productivity `/handoff` API; other names are MCP tool names. Do not pass Python implementation function names to a connector that exposes only the operation router.

## Workflow

1. Invoke configured tools directly within the Velora One conversation, consistent with existing agent instructions. A /handoff API call is a backend request and need not create a child conversational agent.
2. Build one section per independently verified domain. Keep source-specific timestamps visible; do not claim all figures describe the same historical snapshot when they do not.
3. Separate measured facts, deterministic calculations, proposed decisions, and missing data. Confidence must reflect the weakest supporting evidence for each combined claim.
4. Use existing recommendations only if their measurement, source, policy version, completeness, and currency are consistent; do not invent causation between cash and headcount movements.
5. Keep P&L out of scope under current agent instructions. Add SAC KPIs only after endpoint/model validation and an explicit routing decision. Provide an in-chat brief; PDF/PPT generation would be new engineering.

## Result

Executive summary; workforce, cash, budget, and actions sections; proposed decisions; source/period notes; and gaps. No invented consolidated confidence percentage.

## Engineering gaps

New orchestration/evidence assembly required. Depends on component blockers R03–R12. P&L remains explicitly excluded; peer benchmarks lack an executable provider/tool path.

## Acceptance scenarios

- **One domain fails:** Return verified sections with a missing-domain notice.
- **Finance is current while workforce query is historical:** Label the periods separately; no false common as-of date.
- **User asks for P&L within the pack:** State existing out-of-scope policy rather than invent an S4 report.
- **Sources show correlation but no causal evidence:** Present co-occurrence and proposed investigation, not a proven cause.

## Implementation anchors

- [mcp-apps/ask-productivity/productivity_mcp/evidence_contracts.py](../../../../mcp-apps/ask-productivity/productivity_mcp/evidence_contracts.py)
- [mcp-apps/ask-productivity/productivity_mcp/confidence_policy.py](../../../../mcp-apps/ask-productivity/productivity_mcp/confidence_policy.py)
- [mcp-apps/ask-productivity/productivity_mcp/tools_m365_reads.py](../../../../mcp-apps/ask-productivity/productivity_mcp/tools_m365_reads.py)
- [mcp-apps/ask-s4hana/s4hana_mcp/tools.py](../../../../mcp-apps/ask-s4hana/s4hana_mcp/tools.py)
- [mcp-apps/ask-successfactors/successfactors_mcp/successfactors_tools.py](../../../../mcp-apps/ask-successfactors/successfactors_mcp/successfactors_tools.py)

Relevant existing test filenames: `test_evidence_contract.py`, `test_confidence_policy.py`, `test_finance_recommendations.py`. These are evidence of unit coverage, not live deployment certification.
