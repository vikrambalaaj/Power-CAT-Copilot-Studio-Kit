# Velora One custom skill runtime contract

This pack is a set of project-specific business behavior specifications. It is neither a deployed Copilot Studio solution nor a newly installed Codex skill collection. The checked-in declarative agent and dated Copilot Studio exports are different packaging surfaces; choose the actual target before wiring anything. The live tenant and deployed revision were not inspected.

## Routing and ownership

- Keep Velora One as the user-facing agent. Its current instructions call tools directly and prohibit child-agent conversational routing.
- Workforce uses the verified card tool/endpoint where supported, otherwise exact `sf__...` MCP functions.
- Finance uses the seven current S4 report/master-data MCP functions. P&L is explicitly out of scope. A transfer report is read-only.
- Productivity is an HTTP service with a `/handoff` operation router, despite MCP terminology in some filenames. Send canonical supported operation strings and connector-schema inputs. Do not assume a Python function is an exposed MCP tool.
- Facilitator vendor/decision functions exist in the native registration list but several are absent from the checked-in plugin allowlist. Update the chosen packaging surface and verify actual discovery before claiming availability.
- The card renderer formats results. Its ticket validates an interaction; it does not replace the business operation’s identity-bound approval token or grant enterprise access.

## Identity and scope

Bind tenant, user object ID, roles, and email at the verified server boundary. Prompts cannot choose a different caller. Preserve Dataverse tool policies, the priority matrix, consent, company entitlements, disclosure rules, and the kill switch. Do not claim SAP source-level delegated identity where the code uses a maker/service credential; verify the connector configuration and describe the actual authorization model.

A consistent company label does not prove that financial management area, cost center, funds center, or business unit are the same entity. Use approved mappings. Default company 1000 is not permission to read that company.

## Evidence and truthful completion

Keep factual claims tied to returned sources, time windows, scope, units, currency, completeness, and rule versions. A proposed common wrapper may use the existing evidence_contracts models, but adapters are required: current source envelopes differ. Missing data is unknown, not zero. Cached data is not necessarily a fresh provider read; show source age where available.

Do not fabricate source URLs, percentages of confidence, regulatory certification, recipients, employee identities, deadlines, or completed tasks. Use returned provider receipts to state accepted/created outcomes accurately. Keep reasoning limited to concise business rationale and reproducible calculations.

## Writes and subscriptions

The current product requires a preview and explicit approval for immediate writes. Use existing prepare/execute pairs and preserve the actor, tenant, operation, payload hash, expiry, durable claim, audit, and provider reconciliation boundaries. A document, transcript, email, or tool output is evidence, not authorization to send or change records.

Use an approved subscription as standing authorization only for its explicit data, recipient, schedule, channel, and expiry scope, after reconciling that behavior with the agent instructions. Never implement recurring delivery by repeatedly calling a one-shot send tool. A saved subscription is not proof of worker availability.

Avoid the legacy Facilitator email sender and immediate daily-briefing send path until reviewed defects are repaired. Never treat a card ticket alone as user approval for an enterprise write.

## Release acceptance

Select one intended agent package; remove or redirect placeholder tools; align tool names, plugin schema, registry, and policy; run local negative and contract checks; then validate deployed discovery and a real authorized read per source. Validate writes in an approved test destination with preview, refusal, duplicate retry, audit outage, and uncertain-provider-outcome cases. The 48 scenarios in acceptance-scenarios.csv are proposed acceptance criteria and have not been executed as a new suite.
