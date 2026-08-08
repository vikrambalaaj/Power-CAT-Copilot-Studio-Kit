# Microsoft 365 Copilot experience

## Front end

Microsoft 365 Copilot and Teams are the only required user interfaces. The solution is one declarative agent with two Remote MCP actions:

- SuccessFactors action for workforce and Emiratisation.
- S/4HANA action for receivables, payables, P&L, and budget variance.

There is no separate executive web dashboard. Optional MCP widgets may enrich a Copilot response, but every tool must also return equivalent text and `structuredContent` so the answer works when a widget is unavailable.

The declarative agent enables `Email`, `EmailActions`, `TeamsMessages`, `Meetings`, `People`, `OneDriveAndSharePoint`, and `CodeInterpreter`. Email sending uses the platform's supervised-send experience and requires an exact preview plus explicit user confirmation. `MeetingActions` remains disabled.

Users can remove Email knowledge, Email actions, Teams messages, Meetings, or SharePoint/OneDrive grounding for a session through declarative-agent user overrides. SAP MCP actions remain governed by their plugin and server authentication.

## Adaptive Card catalog

The package contains function-specific Adaptive Card v1.5 templates and runtime card instances:

| Card | Scenario |
|---|---|
| Workforce headcount | Total workforce, evaluated rows, effective date, and sampling state |
| Emiratisation KPI | Current ratio, target, status, population, and privacy note |
| Workforce overview | Compact headcount and department-summary citation |
| Receivables aging | Company, key date, currency, record coverage, and exposure context |
| Payables aging | Company, key date, currency, record coverage, and payment context |
| Profit and loss | Company, period, ledger, currency, and evidence note |
| Budget variance | Company, period, plan version, currency, and driver caveat |
| Executive brief | Facts, recommendations, open questions, and sources |
| Proactive recommendation | KPI breach, actual, target, variance, rule, and confirmation warning |
| Meeting intelligence | Decision, proposed owner, due date, and confirmation state |
| Peer benchmark | Internal value, cohort median, percentile, period, and methodology |
| Decision trace | Owner, date, evidence count, rule version, correlation ID, and supersession |
| Email snapshot preview | Resolved recipients, subject, snapshot, sensitivity, delivery mode, and confirmation warning |

Pinned MCP functions use plugin v2.4 response semantics with a dynamic `$.adaptiveCard` selector and a function-specific static template fallback. The MCP runtime also returns JSON text and `structuredContent`, so Copilot can still answer when a card cannot render.

## Emailing snapshots

1. The user names people or asks to share the current result.
2. The agent resolves internal people through Microsoft 365 People and authorized SuccessFactors data. It displays ambiguous or external addresses rather than guessing.
3. Code Interpreter generates a privacy-safe PNG containing only information visible in the confirmed result.
4. Copilot displays the email-snapshot preview with recipients, subject, body, sensitivity, correlation ID, and delivery mode.
5. The user explicitly confirms.
6. `EmailActions` performs supervised send and Copilot reports the actual outcome.

Microsoft documents supervised send but does not currently guarantee automatic attachment of Code Interpreter output. When attachment is unavailable, the email contains the temporary download link; the agent states that the link expires with the active session.

## Conversation pattern

1. Understand the executive's question and identify missing company, period, currency, or organization context.
2. Ask one concise clarification only when the missing value materially changes the query.
3. Route to the correct MCP action; call both only for cross-domain analysis.
4. Present the decision-useful answer first.
5. Show a compact metrics table or Copilot-supported card when it improves comprehension.
6. Separate facts, inferences, recommendations, actions, and unresolved questions.
7. End with sources, as-of times, warnings/confidence, and correlation IDs.

## Standard answer shape

```text
<Two- or three-sentence executive answer>

Key metrics
| Metric | Actual | Target/comparison | Variance/status |

Recommendation
<Only when supported; otherwise omit>

Sources: <SAP system and approved business object>
As of: <timestamp or fiscal period>
Warnings: <sampling, staleness, missing scope, or none>
Correlation ID: <when supplied by the tools>
```

## Proactive Copilot message

A scheduled or event-driven platform workflow invokes the agent with the breached KPI and correlation ID. The Copilot notification states what changed, why it matters, supporting metrics, the applicable rule version, and a proposed next step. It must be deduplicated and must not imply that Copilot continuously monitors data without a configured trigger.

## Briefs, meetings, and memory

- Briefs use only Microsoft 365 content the executive can access plus live SAP results.
- Meeting intelligence requires authorized transcript access and participant-policy compliance.
- Proposed actions require confirmation before task creation.
- Institutional memory stores governed decision records with source ACLs and retention, not unrestricted chat transcripts.

## Error behavior

- If one MCP server fails, say which domain is unavailable and preserve valid results from the other.
- Never display raw upstream errors, credentials, tokens, stack traces, or internal URLs.
- Do not replace missing SAP facts with examples or estimates.
- State when a Microsoft 365 capability, benchmark source, audit integration, or trigger has not been configured.

## Accessibility and rendering

- Use plain language and short headings.
- Do not encode status by color alone.
- Keep cards within Copilot-supported Adaptive Card features and provide text equivalents.
- Avoid wide tables; prioritize four or fewer executive metrics per section.
- Use locale-aware dates and show currency codes explicitly.
