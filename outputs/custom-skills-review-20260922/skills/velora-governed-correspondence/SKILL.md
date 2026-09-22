---
name: velora-governed-correspondence
description: Prepare and execute approved Velora email, replies, meeting changes, and Teams communications.
---

# Reviewed executive correspondence

**Status:** Business skill specification for Velora One; not installed or deployed. Phase 2: Reuse productivity prepare/execute; quarantine legacy send paths.

Use this specification to implement or review the business behavior. It does not grant access to the listed tools. Bind these instructions to the actual configured Copilot tools/topics; saving a SKILL.md alone does not register them.

Read [the shared runtime contract](../../RUNTIME_CONTRACT.md) for transport, evidence, identity, and state-changing behavior. Finding IDs refer to [the source review](../../REVIEW.md).

## Example request

“Draft a follow-up to the finance team using the verified collections summary.”

## Required context

Exact recipients or directory-resolvable names, message/thread/event destination, content, and requested action. SAP-derived information must remain within the allowed destination policy.

## Existing tool bindings

`PREPARE_EMAIL`, `SEND_APPROVED_EMAIL`, `PREPARE_EMAIL_REPLY`, `SEND_APPROVED_EMAIL_REPLY`, `PREPARE_MEETING_CREATION`, `CREATE_APPROVED_MEETING`, `PREPARE_TEAMS_CHAT_MESSAGE`, `SEND_APPROVED_TEAMS_CHAT_MESSAGE`.

Uppercase names are `operation` values for the productivity `/handoff` API; other names are MCP tool names. Do not pass Python implementation function names to a connector that exposes only the operation router.

## Workflow

1. Resolve recipients and existing thread/event before drafting. Preserve requested intent and source provenance.
2. Use the Productivity Stage A preview. Show actual destination, subject/body or meeting changes, and exact attachments.
3. Wait for the product approval event, then execute Stage B with the original preview and token bound to actor, tenant, operation, and payload. A changed recipient or body requires a new preview.
4. Do not use Facilitator send_executive_email_via_graph until R01 is fixed. Do not use SEND_DAILY_BRIEFING_EMAIL until R02 is fixed; use its separate prepare and send-approved operations.
5. On uncertain provider outcome, reconcile the operation receipt before retry. A Graph acceptance receipt is not proof that a recipient read the message.

## Result

Unsent preview followed, only after approval, by a truthful provider outcome and reference. Keep secrets and confirmation tokens out of human-facing content.

## Engineering gaps

R01 weak confirmation; R02 immediate prepare-and-send path; R08 aliases. Verify audit fail-closed and idempotency behavior on deployed transport.

## Acceptance scenarios

- **Arbitrary nonempty approval string:** Reject before any provider call.
- **Body or recipient edited after preview:** Invalidate old approval and prepare a new preview.
- **Audit unavailable at execution:** No external mutation occurs.
- **Provider times out after acceptance:** Reconcile status; no blind duplicate send.

## Implementation anchors

- [mcp-apps/ask-productivity/productivity_mcp/tools_m365_writes.py](../../../../mcp-apps/ask-productivity/productivity_mcp/tools_m365_writes.py)
- [mcp-apps/ask-productivity/productivity_mcp/token_manager.py](../../../../mcp-apps/ask-productivity/productivity_mcp/token_manager.py)
- [mcp-apps/ask-productivity/productivity_mcp/operation_store.py](../../../../mcp-apps/ask-productivity/productivity_mcp/operation_store.py)
- [mcp-apps/ask-productivity/productivity_mcp/audit_client.py](../../../../mcp-apps/ask-productivity/productivity_mcp/audit_client.py)

Relevant existing test filenames: `test_m365_writes.py`, `test_two_step_pattern.py`, `test_governed_execution_boundary.py`, `test_operation_store_lifecycle.py`. These are evidence of unit coverage, not live deployment certification.
