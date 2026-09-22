---
name: velora-vendor-decision
description: Compare Velora vendor proposals using the existing approved-policy scoring engine and scoped institutional history.
---

# Evidence-backed vendor comparison

**Status:** Business skill specification for Velora One; not installed or deployed. Phase 2: Implemented backend; plugin exposure and policy validation required.

Use this specification to implement or review the business behavior. It does not grant access to the listed tools. Bind these instructions to the actual configured Copilot tools/topics; saving a SKILL.md alone does not register them.

Read [the shared runtime contract](../../RUNTIME_CONTRACT.md) for transport, evidence, identity, and state-changing behavior. Finding IDs refer to [the source review](../../REVIEW.md).

## Example request

“Compare these maintenance proposals using the approved procurement policy.”

## Required context

Candidate IDs and evidence-backed technical/commercial values, comparable scope/currency/tax/term, policy ID/version, and permitted institutional records.

## Existing tool bindings

`get_vendor_performance_history`, `evaluate_vendor_options`, `get_vendor_decision_record`.

Uppercase names are `operation` values for the productivity `/handoff` API; other names are MCP tool names. Do not pass Python implementation function names to a connector that exposes only the operation router.

## Workflow

1. Require cited input documents or explicitly supplied assessed scores. The backend scores structured candidates; document extraction is a separate proposed capability.
2. Load the existing policy by ID/version. The catalogue contains POLICY-VENDOR-PROC-V1; confirm that the business owner has approved this checked-in policy before release. Prompt text must not change its weights.
3. Reject incomparable currency/tax/term/scope or mandatory missing inputs according to policy. Do not invent technical scores from persuasive prose.
4. Compare baseline and history-informed results with exact Decimal contributions, eligibility, ties, and evidence gaps. New vendors without history should receive the policy’s explicit missing-history treatment.
5. Return the persisted decision ID for later retrieval. Do not place purchase orders, award contracts, or change SAP vendor records.

## Result

Comparable-input summary, ranked scores and contribution breakdown, history effect, missing evidence, policy/version, and persisted decision reference.

## Engineering gaps

R10: decision tools missing from the checked-in Facilitator plugin allowlist. Institutional history must contain verified scoped records; a class named Approved is not business sign-off.

## Acceptance scenarios

- **Two candidates use different currencies or tax bases:** No unsupported comparable ranking or winner.
- **Prompt asks to change policy weights for a preferred vendor:** Keep policy immutable and explain the approved-policy boundary.
- **Candidate lacks historical evidence:** Apply policy handling and disclose the gap.
- **Retrieve an old decision:** Return stored version rather than silently rescore against new evidence.

## Implementation anchors

- [mcp-apps/ask-facilitator/facilitator_mcp/vendor_evaluation.py](../../../../mcp-apps/ask-facilitator/facilitator_mcp/vendor_evaluation.py)
- [mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py](../../../../mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py)
- [mcp-apps/ask-facilitator/facilitator_mcp/institutional_memory.py](../../../../mcp-apps/ask-facilitator/facilitator_mcp/institutional_memory.py)
- [mcp-apps/ask-facilitator/facilitator_mcp/tools.py](../../../../mcp-apps/ask-facilitator/facilitator_mcp/tools.py)

Relevant existing test filenames: `test_vendor_evaluation.py`, `test_institutional_memory.py`, `test_decision_audit_export.py`. These are evidence of unit coverage, not live deployment certification.
