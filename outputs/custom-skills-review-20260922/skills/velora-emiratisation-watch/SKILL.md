---
name: velora-emiratisation-watch
description: Explain Velora aggregate Emiratisation, target gaps, and clearly labelled workforce scenarios.
---

# Emiratisation target watch

**Status:** Business skill specification for Velora One; not installed or deployed. Phase 1: Reuse KPI; new scenario calculation and monitoring wiring.

Use this specification to implement or review the business behavior. It does not grant access to the listed tools. Bind these instructions to the actual configured Copilot tools/topics; saving a SKILL.md alone does not register them.

Read [the shared runtime contract](../../RUNTIME_CONTRACT.md) for transport, evidence, identity, and state-changing behavior. Finding IDs refer to [the source review](../../REVIEW.md).

## Example request

“How far are we from the configured Emiratisation target?”

## Required context

Company, as-of date, approved internal target returned by the provider, scenario type, and eligibility rules. This is an internal target analysis, not a legal compliance determination.

## Existing tool bindings

`sf__get_emiratisation_kpi`, `sf__get_headcount`.

Uppercase names are `operation` values for the productivity `/handoff` API; other names are MCP tool names. Do not pass Python implementation function names to a connector that exposes only the operation router.

## Workflow

1. Read active eligible headcount N, UAE National count U, unmapped count, and target T from the same provider result. Never invent a statutory target or adopt the default 40% as a legal requirement.
2. Explain percentage-point gap using provider output. State that unmapped nationality remains in the eligible denominator in the current implementation, and is separately reported.
3. If explicitly requested, compute an illustrative fixed-headcount replacement gap as max(0, ceil(T*N-U)); compute an additional-hire-only scenario as max(0, ceil((T*N-U)/(1-T))) for 0<=T<1. Here T is a fraction; require N>0 and valid counts. Treat T=1 separately. These are proposed deterministic calculations, not existing tools.
4. State historical limitations: EmpJob can use the requested date while active status and nationality retrieval are not fully historical. Scheduled monitoring requires a verified SF snapshot adapter and approved rule configuration; no adapter was established in this review.

## Result

Active UAE/eligible counts, configured target, current ratio, percentage-point gap, unmapped count, source date, and optional labelled scenario assumptions.

## Engineering gaps

No verified SuccessFactors-to-recommendation snapshot adapter identified. Do not enable automatic interventions or employee-level nationality disclosure.

## Acceptance scenarios

- **Target omitted:** Use only the configured provider target and label it internal.
- **Synthetic N=100 U=30 T=40%:** Fixed-headcount scenario needs 10 replacements; additional-hire-only scenario needs 17 hires.
- **Unmapped nationality exists:** Report uncertainty and do not classify unknown records as non-UAE.
- **Request historical or individual nationality:** State the historical limitation; retain aggregate confidentiality boundary.

## Implementation anchors

- [mcp-apps/ask-successfactors/successfactors_mcp/successfactors_client.py](../../../../mcp-apps/ask-successfactors/successfactors_mcp/successfactors_client.py)
- [mcp-apps/ask-successfactors/successfactors_mcp/successfactors_settings.py](../../../../mcp-apps/ask-successfactors/successfactors_mcp/successfactors_settings.py)
- [mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py](../../../../mcp-apps/ask-productivity/productivity_mcp/recommendation_engine.py)

Relevant existing test filenames: `test_app.py`, `test_policy_and_drilldown.py`. These are evidence of unit coverage, not live deployment certification.
