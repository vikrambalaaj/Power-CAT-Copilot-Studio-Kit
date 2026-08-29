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

## Consent store (required)

The confidentiality consent gate is the first screen of every session. A decision is
written to `cre2f_botuserconsent` and every later session reads it back, so the user
is asked exactly once per notice version.

`cre2f_botuserconsent` is shared with the Copilot Studio flow *Check and Register Bot
Consent*. Both writers key on `cre2f_userobjectid`, so a consent granted through either
path is honoured by the other.

### Identity column

Both writers key on `cre2f_newcolumn`, the table's primary name column. Its *display*
name is "User ID", which is the trap that produced the original outage: the flow's
author saw "User ID" in the designer and wrote `cre2f_userid`, a column that does not
exist, so every run failed with `BadRequest` — surfaced by Copilot Studio as
`FlowActionBadGateway`.

A properly named `cre2f_userobjectid` column would be clearer, but creating it needs
schema-write privilege that the current maker account does not hold in this
environment. If that privilege becomes available, add the column, repoint both writers,
and change `CONSENT_IDENTITY_COLUMN` in `dataverse_audit.py`.

Columns written by the MCP server:

| Column | Value |
| --- | --- |
| `cre2f_newcolumn` | identity: Entra object id, or the email when no object id is supplied |
| `cre2f_channel` | originating channel, e.g. `copilot_studio` |
| `cre2f_consentdate` | decision timestamp |
| `cre2f_consentgranted` | `true` for ACCEPTED, `false` for DECLINED |
| `cre2f_consentversion` | notice version, e.g. `2026.1` |

### Connection

| Variable | Purpose |
| --- | --- |
| `DATAVERSE_URL` | e.g. `https://org4b098979.crm15.dynamics.com` |
| `AZURE_TENANT_ID` | Entra tenant of the Dataverse environment |
| `AZURE_CLIENT_ID` | App registration / application user |
| `AZURE_CLIENT_SECRET` | Client secret — set with `cf set-env`, never in `manifest.yml` |

Optional: `DATAVERSE_CONSENT_ENTITY_SET` (default `cre2f_botuserconsents`) and
`DATAVERSE_AUDIT_ENTITY_SET` (default `cre2f_veloraagentauditlogs`) for customised
collection names, and `DATAVERSE_CONSENT_CACHE_SECONDS` (default `300`).

Behaviour without them: the server still runs and still gates, but consent lives only
in the process buffer, so every restart and every additional instance re-prompts.

### Column projection

Dataverse rejects an entire insert that names any column the table does not have. Both
writes are therefore projected onto allowlists that mirror the live schema —
`CONSENT_COLUMNS` and `AUDIT_LOG_COLUMNS` in `dataverse_audit.py`. `cre2f_veloraagentauditlog`
exposes 19 writable custom columns and has no `cre2f_recordtype`, so the record type is
preserved as a `[TYPE]` prefix on `cre2f_auditdetail`. Widen either allowlist only after
the column exists and customisations are published.

Failure semantics are fail-closed: a consent write that Dataverse rejects returns
`status: FAILED` and the user stays blocked; an unreadable consent table re-prompts
rather than assuming consent.
