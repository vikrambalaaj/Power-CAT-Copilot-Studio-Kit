---
name: velora-meeting-actions
description: Extract reviewable Velora meeting commitments, create approved Planner tasks, and track provider-backed progress.
---

# Meeting decisions to owned actions

**Status:** Business skill specification for Velora One; not installed or deployed. Phase 2: Reuse approval workflow; natural transcript extraction needs work.

Use this specification to implement or review the business behavior. It does not grant access to the listed tools. Bind these instructions to the actual configured Copilot tools/topics; saving a SKILL.md alone does not register them.

Read [the shared runtime contract](../../RUNTIME_CONTRACT.md) for transport, evidence, identity, and state-changing behavior. Finding IDs refer to [the source review](../../REVIEW.md).

## Example request

“Turn these approved meeting actions into Planner tasks and show their status.”

## Required context

Meeting ID, source version, authorized transcript/notes, exact plan and bucket, source-backed owners and deadlines.

## Existing tool bindings

`PREPARE_MEETING_ACTIONS`, `CREATE_APPROVED_MEETING_ACTIONS`, `GET_MEETING_ACTION_TRACKER`.

Uppercase names are `operation` values for the productivity `/handoff` API; other names are MCP tool names. Do not pass Python implementation function names to a connector that exposes only the operation router.

## Workflow

1. Fetch authorized meeting evidence; distinguish calendar event IDs from onlineMeeting IDs. Preserve source version for deduplication.
2. The current extractor handles labelled lines such as Action:, Owner:, Due:. It is not general conversational minutes extraction. For free speech, prepare a proposed structured extraction with exact evidence spans and user review, then pass approved structured notes.
3. Retain UNASSIGNED, DATE_REQUIRED, or AMBIGUOUS states. Resolve owners through the directory; never manufacture identities or dates.
4. PREPARE_MEETING_ACTIONS creates a preview. Submit unchanged previewDetails and its confirmationToken only after the product’s explicit approval event.
5. Read provider-backed status after creation; duplicate retries must not create new tasks. Automatic reminders require a separately approved subscription. Task completion operations remain blocked by R08.

## Result

Reviewable table of action, source evidence, owner, deadline, eligibility, and target; after approval, provider task receipts and current tracker state.

## Engineering gaps

R09 free-form transcript extraction; R08 completion operations absent from authorization registry. Live multi-worker retry and partial-creation recovery must be proven.

## Acceptance scenarios

- **Action missing owner or deadline:** Show unresolved fields and do not create that action’s task.
- **Plain conversational commitment without Action label:** Do not treat zero parser matches as no actions; explain extraction limitation.
- **Same approved meeting/source retried:** Return existing task mapping without duplicates.
- **Provider task completed after creation:** Tracker reflects completion and suppresses further reminders.

## Implementation anchors

- [mcp-apps/ask-productivity/productivity_mcp/meeting_actions.py](../../../../mcp-apps/ask-productivity/productivity_mcp/meeting_actions.py)
- [mcp-apps/ask-productivity/productivity_mcp/tools_m365_writes.py](../../../../mcp-apps/ask-productivity/productivity_mcp/tools_m365_writes.py)
- [mcp-apps/ask-productivity/productivity_mcp/tools_m365_reads.py](../../../../mcp-apps/ask-productivity/productivity_mcp/tools_m365_reads.py)
- [mcp-apps/ask-productivity/productivity_mcp/server.py](../../../../mcp-apps/ask-productivity/productivity_mcp/server.py)

Relevant existing test filenames: `test_meeting_actions.py`, `test_governed_execution_boundary.py`, `test_two_step_pattern.py`. These are evidence of unit coverage, not live deployment certification.
