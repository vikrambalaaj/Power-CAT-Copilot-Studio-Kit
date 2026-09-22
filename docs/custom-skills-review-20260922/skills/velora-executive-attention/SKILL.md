---
name: velora-executive-attention
description: Prioritize Velora executive email, calendar, and Planner obligations with evidence-backed reasons.
---

# Executive attention and day plan

**Status:** Business skill specification for Velora One; not installed or deployed. Phase 1: Reuse triage; approvals and Teams coverage limited.

Use this specification to implement or review the business behavior. It does not grant access to the listed tools. Bind these instructions to the actual configured Copilot tools/topics; saving a SKILL.md alone does not register them.

Read [the shared runtime contract](../../RUNTIME_CONTRACT.md) for transport, evidence, identity, and state-changing behavior. Finding IDs refer to [the source review](../../REVIEW.md).

## Example request

“What needs my attention today, and what can wait?”

## Required context

Authenticated mailbox, local timezone, lookback window, result limit, and approved triage rubric if available.

## Existing tool bindings

`GET_EXECUTIVE_ATTENTION`, `PLAN_MY_DAY`, `GET_DAILY_EXECUTIVE_BRIEFING`, `SEARCH_MAIL`, `LIST_CALENDAR_EVENTS`, `FIND_OVERDUE_TASKS`.

Uppercase names are `operation` values for the productivity `/handoff` API; other names are MCP tool names. Do not pass Python implementation function names to a connector that exposes only the operation router.

## Workflow

1. Call canonical uppercase operations through the configured productivity /handoff connector. Identity and tenant come from the verified request, not prompt text.
2. Ground urgency in actual sender, dates, task status, meeting timing, and returned scoring reasons; distinguish ranked recommendations from retrieved commitments.
3. Keep current local-day boundaries consistent. Exclude canceled meetings and clearly identify partial pages or failed sources.
4. Treat pending approvals as unavailable until a real approvals provider is implemented (R04). A live empty list in current code is not evidence of no approvals.
5. Do not use current GET_CHANNEL_CONTEXT as exact channel evidence (R03), and do not claim the chat search covers all Teams channels.

## Result

A short ranked attention list with reason, deadline, owner when verified, source link when returned, and explicit missing sections.

## Engineering gaps

R03 Teams scope; R04 approvals placeholder; R08 operation alias registry drift. Use only canonical operation names present in registry.

## Acceptance scenarios

- **Cancelled meeting and completed task in source:** Neither becomes an urgent outstanding commitment.
- **Approvals implementation returns live empty list:** Say approvals could not be verified; do not say no approvals pending.
- **Mailbox source unavailable but calendar succeeds:** Return calendar findings and identify mailbox failure.
- **Priority item has no due date:** Do not invent a deadline from its ranking.

## Implementation anchors

- [mcp-apps/ask-productivity/productivity_mcp/server.py](../../../../mcp-apps/ask-productivity/productivity_mcp/server.py)
- [mcp-apps/ask-productivity/productivity_mcp/tools_m365_reads.py](../../../../mcp-apps/ask-productivity/productivity_mcp/tools_m365_reads.py)
- [mcp-apps/ask-productivity/productivity_mcp/triage_engine.py](../../../../mcp-apps/ask-productivity/productivity_mcp/triage_engine.py)
- [mcp-apps/ask-productivity/productivity_mcp/m365_client.py](../../../../mcp-apps/ask-productivity/productivity_mcp/m365_client.py)

Relevant existing test filenames: `test_triage_engine.py`, `test_daily_briefing.py`, `test_graph_read_contracts.py`. These are evidence of unit coverage, not live deployment certification.
