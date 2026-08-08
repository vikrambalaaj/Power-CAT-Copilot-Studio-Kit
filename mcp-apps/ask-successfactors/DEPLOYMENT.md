# Deployment and rollout

## Environments

Use separate development, test, and production deployments for each MCP server. Each deployment needs its own hostname, API authentication registration, SAP identity, secret store entries, telemetry destination, and allowlist.

| Configuration class | SuccessFactors MCP | S/4HANA MCP |
|---|---|---|
| Base URL | SuccessFactors OData v2 tenant URL | S/4HANA released OData/CDS base URL |
| SAP identity | Delegated mapping or scoped HCM service identity | Delegated mapping or scoped finance service identity |
| MCP authentication | Independent API-key/vault or supported OAuth registration | Independent API-key/vault or supported OAuth registration |
| Authorization | RBP | PFCG and CDS/DCL |
| Tool allowlist | Headcount and Emiratisation plus approved drill-down | Four finance query tools only |
| Network | HTTPS, hostname allowlist, egress allowlist | HTTPS, hostname allowlist, egress allowlist |

## Release sequence

1. Finance approves the released S/4HANA services, dimensions, ledgers, currencies, and calculation definitions.
2. HR approves the SuccessFactors entities, active-headcount definition, Emiratisation filter, aggregation threshold, and RBP scope.
3. Security selects the identity model for each server and provisions independent secrets.
4. Deploy the implemented `ask-successfactors` and `ask-s4hana` servers privately to development and verify health, authentication, authorization, and audit propagation.
5. Register both MCP endpoints in the Microsoft 365 plugin vault.
6. Add both plugin manifests to the single Velora declarative agent.
7. Configure Microsoft 365 memory, meeting, briefing, benchmark, recommendation, and agent-governance services.
8. Create the recurrence event triggers and proactive Teams delivery described in `AUTOMATION.md`, using the executive user ID from an environment variable.
9. Run the complete test plan with synthetic and authorized non-production data.
10. Pilot with named executives, monitor false recommendations and authorization denials, then obtain production approval.
11. Build a fresh agent package from source and publish through the approved Microsoft 365 process.

Configure and load-test the bounded caches as described in `CACHE.md`. Keep finance TTLs shorter than workforce TTLs, verify cache metadata in responses, and confirm a successful SuccessFactors write invalidates all local HCM read entries.

## Production gates

- Both MCP endpoints use HTTPS and reject anonymous requests.
- No credentials or tenant data exist in source, images, ZIP files, manifests, or logs.
- Tool manifests expose only the six approved read tools.
- Delegated identity is verified, or the approved service-identity control is documented accurately.
- Small-group privacy suppression is active for Emiratisation and benchmarks.
- PFCG/RBP negative authorization tests pass.
- Cache keys preserve the effective identity and complete normalized query; error responses are not cached.
- Correlation IDs join the agent, both MCP servers, SAP calls, notifications, meetings, memory, and decisions.
- Retention, legal hold, deletion, and data-subject processes are approved.
- Rollback disables either MCP independently without taking down the other.

## Operational ownership

Maintain a runbook containing service owners, support hours, escalation contacts, certificate and secret expiry, SAP service dependencies, rate limits, recovery objectives, dashboards, alert thresholds, and rollback commands. Review access and tool allowlists quarterly and after every material SAP role or service change.

## Package rule

Do not reuse local ZIP artifacts. Generate the package only after production URLs and vault references are injected, scan its contents for secrets, verify that both plugin manifests are present, and archive its checksum with the release approval.
