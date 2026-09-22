---
name: velora-decision-evidence
description: Retrieve and verify Velora vendor decision evidence and prepare authorized audit exports.
---

# Decision evidence retrieval and export

**Status:** Business skill specification for Velora One; not installed or deployed. Phase 3: Hold external/redacted export pending repair.

Use this specification to implement or review the business behavior. It does not grant access to the listed tools. Bind these instructions to the actual configured Copilot tools/topics; saving a SKILL.md alone does not register them.

Read [the shared runtime contract](../../RUNTIME_CONTRACT.md) for transport, evidence, identity, and state-changing behavior. Finding IDs refer to [the source review](../../REVIEW.md).

## Example request

“Show the evidence and scoring behind this vendor decision.”

## Required context

Existing decision ID/version, authorized tenant/role, requested format, redaction scope, and export lifetime.

## Existing tool bindings

`get_vendor_decision_record`, `export_decision_trail`, `verify_decision_manifest`.

Uppercase names are `operation` values for the productivity `/handoff` API; other names are MCP tool names. Do not pass Python implementation function names to a connector that exposes only the operation router.

## Workflow

1. Retrieve the persisted decision/version. Verify actor authorization through the server boundary; do not accept roles or tenant identity supplied by the prompt.
2. Preserve input snapshot, policy snapshot, exact score trace, sources, and hash/signature metadata. Never describe these as hidden model reasoning.
3. Hold redacted CSV/BUNDLE export until R11 is fixed. Current JSON redactions do not sanitize the CSV generated from the original manifest.
4. Require actual durable audit acceptance and a governed artifact retrieval path before offering external downloadable exports. Current liveness gate only observes a simulation environment flag.
5. Report verification outcome accurately; signature/hash checks are technical evidence and do not establish regulatory compliance.

## Result

Decision reference, policy version, source/evaluation trace, verification result, and only a genuinely authorized artifact reference.

## Engineering gaps

R11 redaction leakage; R12 audit liveness not an actual health/commit check; R10 plugin exposure. Local artifact paths/tokens are not automatically user-accessible download links.

## Acceptance scenarios

- **Request commercial-price redaction in CSV/BUNDLE:** No price appears anywhere in the selected artifact; block until repaired.
- **Unauthorized role or different tenant:** Deny before retrieving/exporting protected evidence.
- **Manifest content changed after signing:** Verification reports invalid rather than success.
- **Real audit persistence unavailable:** Do not claim audited export success based only on a simulation flag.

## Implementation anchors

- [mcp-apps/ask-facilitator/facilitator_mcp/audit_export.py](../../../../mcp-apps/ask-facilitator/facilitator_mcp/audit_export.py)
- [mcp-apps/ask-facilitator/facilitator_mcp/decision_audit.py](../../../../mcp-apps/ask-facilitator/facilitator_mcp/decision_audit.py)
- [mcp-apps/ask-facilitator/facilitator_mcp/server.py](../../../../mcp-apps/ask-facilitator/facilitator_mcp/server.py)

Relevant existing test filenames: `test_decision_audit_export.py`, `test_review_transport_authorization.py`. These are evidence of unit coverage, not live deployment certification.
