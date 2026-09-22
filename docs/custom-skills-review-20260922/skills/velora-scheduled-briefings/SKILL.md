---
name: velora-scheduled-briefings
description: Configure explicit Velora briefing or meeting-action reminder subscriptions and explain their delivery state.
---

# Subscribed briefings and action reminders

**Status:** Business skill specification for Velora One; not installed or deployed. Phase 3: Reuse subscription/worker code; deployment validation required.

Use this specification to implement or review the business behavior. It does not grant access to the listed tools. Bind these instructions to the actual configured Copilot tools/topics; saving a SKILL.md alone does not register them.

Read [the shared runtime contract](../../RUNTIME_CONTRACT.md) for transport, evidence, identity, and state-changing behavior. Finding IDs refer to [the source review](../../REVIEW.md).

## Example request

“Send an approved daily briefing to my mailbox at 08:00 Dubai time.”

## Required context

Subscription kind, mailbox, recipients, timezone/local schedule or lead time, channel, valid-until, allowed data scope, and quiet/missed-run policy.

## Existing tool bindings

`PREPARE_AUTOMATION_SUBSCRIPTION`, `CONFIRM_AUTOMATION_SUBSCRIPTION`, `REVOKE_AUTOMATION_SUBSCRIPTION`.

Uppercase names are `operation` values for the productivity `/handoff` API; other names are MCP tool names. Do not pass Python implementation function names to a connector that exposes only the operation router.

## Workflow

1. Prepare the full subscription and show its scope, recipients, schedule, expiry, and allowed data. Require approval before activation.
2. Use the existing finite worker and durable run-key claims; a saved subscription alone does not establish that a worker is deployed or sending.
3. Current worker dispatch supports EMAIL. Reject or explain unsupported channels rather than promising Teams delivery.
4. Honor revocation, expiry, quiet hours, missed-run behavior, and completed-task suppression. Bind each run to the owner’s mailbox context.
5. Resolve the documented conflict between always-per-action confirmation and approved standing subscriptions before enablement; keep user authorization as the product’s explicit recorded subscription.

## Result

Subscription preview, then confirmed subscription ID/status and next eligible schedule if computed; later provider-backed delivery/failure history.

## Engineering gaps

Validate scheduler deployment, database/shared storage, workload identity, Graph permissions, and restart/retry behavior. Deployment scripts use different worker cadences; pick one release configuration.

## Acceptance scenarios

- **Subscription revoked before next run:** No delivery after revocation.
- **Two workers claim same due run:** At most one provider submission.
- **Teams channel requested:** Explain current EMAIL-only dispatch support.
- **User approves a daily mailbox briefing:** Record exact scope and schedule; no unrelated recipients or data scopes are added.

## Implementation anchors

- [mcp-apps/ask-productivity/productivity_mcp/subscription_service.py](../../../../mcp-apps/ask-productivity/productivity_mcp/subscription_service.py)
- [mcp-apps/ask-productivity/productivity_mcp/schedule_engine.py](../../../../mcp-apps/ask-productivity/productivity_mcp/schedule_engine.py)
- [mcp-apps/ask-productivity/productivity_mcp/worker.py](../../../../mcp-apps/ask-productivity/productivity_mcp/worker.py)
- [mcp-apps/ask-productivity/productivity_mcp/standing_authorization.py](../../../../mcp-apps/ask-productivity/productivity_mcp/standing_authorization.py)

Relevant existing test filenames: `test_briefing_variants.py`, `test_schedule_engine.py`, `test_review_worker_failures.py`, `test_notification_claims.py`. These are evidence of unit coverage, not live deployment certification.
