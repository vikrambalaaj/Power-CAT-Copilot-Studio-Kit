# Scheduled prompts and proactive delivery

## Outcome

Four versioned prompts are scheduled in `Asia/Dubai` by default:

| Prompt | Default schedule | Output |
|---|---|---|
| Daily plan | Weekdays 07:30 | Priorities, meetings, preparation, decisions, conflicts |
| Midday follow-ups | Weekdays 13:00 | Open, overdue, blocked, and newly assigned follow-ups |
| End-of-day | Weekdays 17:30 | Completed work, carry-forward actions, tomorrow preparation |
| Weekly executive brief | Monday 08:00 | SAP KPIs, decisions, risks, actions, and weekly priorities |

Edit [scheduled-prompts.json](automation/scheduled-prompts.json) to change the defaults before creating the flows.

## Copilot Studio configuration

Create one recurrence event trigger per enabled schedule, with generative orchestration enabled. The trigger flow must:

1. Read `VELORA_EXECUTIVE_USER_ID` from an environment variable; never hard-code a personal address or user ID in source.
2. Generate the deduplication key from the schedule definition and stop if that key was already delivered successfully.
3. Retrieve authorized Planner and Microsoft To Do tasks because those sources are not native capabilities in the declarative-agent manifest.
4. Send a payload conforming to [trigger-payload.schema.json](automation/trigger-payload.schema.json) to the agent.
5. Instruct the agent to run exactly the matching versioned prompt.
6. Post the resulting text and Adaptive Card as the Copilot Studio agent to the executive's personal Teams chat.
7. Store only delivery metadata: prompt ID, target user ID, local date, correlation ID, outcome, and response hash.
8. Retry transient failures with backoff while preserving the same deduplication key.

## Trigger payload example

```json
{
  "eventType": "velora.scheduled-prompt",
  "promptId": "daily-plan",
  "targetUserId": "<environment variable value>",
  "scheduledAt": "2026-08-10T03:30:00Z",
  "localDate": "2026-08-10",
  "timeZone": "Asia/Dubai",
  "deduplicationKey": "daily-plan:<user>:2026-08-10",
  "plannerTasks": [],
  "toDoTasks": [],
  "deliveryChannel": "teams_personal_chat"
}
```

## Safety boundaries

- A scheduled run may read, evaluate, summarize, and post the approved brief to the configured executive.
- It may draft email or Teams follow-ups but must not send them automatically.
- `EmailActions` supervised send still requires confirmation in an interactive Copilot conversation.
- Do not use the agent maker's mailbox or SAP access as if it were the executive's authorization context.
- Apply quiet hours, absence handling, holiday calendars, retention, DLP, and tenant billing limits.
- Disable a schedule after repeated authorization failures rather than sending an incomplete or fabricated brief.

## Deployment checklist

- Confirm the target executive and timezone.
- Confirm recurrence times and working days.
- Approve the prompt texts and data sources.
- Configure Planner and To Do connections under the approved identity model.
- Configure the Teams proactive-message connection and agent installation for the recipient.
- Test each trigger in Copilot Studio before publishing.
- Verify deduplication, retries, audit records, and failure alerts.
- Obtain explicit approval before enabling production schedules.
