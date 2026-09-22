---
name: velora-meeting-dossier
description: Prepare a source-grounded Velora meeting dossier from an exact calendar event and authorized related information.
---

# Meeting preparation dossier

**Status:** Business skill specification for Velora One; not installed or deployed. Phase 1: Reuse productivity briefing path.

Use this specification to implement or review the business behavior. It does not grant access to the listed tools. Bind these instructions to the actual configured Copilot tools/topics; saving a SKILL.md alone does not register them.

Read [the shared runtime contract](../../RUNTIME_CONTRACT.md) for transport, evidence, identity, and state-changing behavior. Finding IDs refer to [the source review](../../REVIEW.md).

## Example request

“Prepare me for my next finance review.”

## Required context

Exact calendar event ID or enough subject/time context to resolve it, timezone, lead time, and requested business focus.

## Existing tool bindings

`LIST_CALENDAR_EVENTS`, `GET_MEETING_DETAILS`, `GET_MEETING_CONTEXT`, `GET_PRE_MEETING_BRIEF`, `SEARCH_MAIL`, `LIST_PLAN_TASKS`.

Uppercase names are `operation` values for the productivity `/handoff` API; other names are MCP tool names. Do not pass Python implementation function names to a connector that exposes only the operation router.

## Workflow

1. Resolve the intended event and canceled/recurring status. Disambiguate multiple matches instead of combining unrelated meetings.
2. Use GET_PRE_MEETING_BRIEF and GET_MEETING_CONTEXT from Productivity. The similarly named Facilitator generate_pre_meeting_briefing is a placeholder.
3. Use actual attendee and agenda fields, related email evidence, and Planner commitments. Mark approximate content matches as uncertain.
4. Include SAP figures only via an additional explicit finance/workforce query with scope and period preserved. Meeting text alone cannot establish current SAP values.
5. A missing transcript or restricted meeting is a missing source, not evidence that nothing was decided.

## Result

Purpose, verified attendees, agenda, outstanding commitments, relevant facts with sources, and suggested questions clearly distinguished from facts.

## Engineering gaps

Exact end-to-end calendar/transcript permissions require live validation. R03 limits Teams channel context. Facilitator meeting wrappers should be hidden or redirected.

## Acceptance scenarios

- **Two finance reviews on the calendar:** Resolve exact meeting before creating a dossier.
- **Recurring event canceled:** Skip the canceled occurrence without removing valid later occurrences.
- **Relevant email includes an old SAP figure:** Label historical email content; do not call it today’s ERP balance.
- **Transcript permission denied:** Use available event/context and explicitly mark missing transcript.

## Implementation anchors

- [mcp-apps/ask-productivity/productivity_mcp/briefing_service.py](../../../../mcp-apps/ask-productivity/productivity_mcp/briefing_service.py)
- [mcp-apps/ask-productivity/productivity_mcp/tools_m365_reads.py](../../../../mcp-apps/ask-productivity/productivity_mcp/tools_m365_reads.py)
- [mcp-apps/ask-productivity/productivity_mcp/m365_client.py](../../../../mcp-apps/ask-productivity/productivity_mcp/m365_client.py)

Relevant existing test filenames: `test_graph_read_contracts.py`, `test_briefing_variants.py`, `test_daily_briefing.py`. These are evidence of unit coverage, not live deployment certification.
