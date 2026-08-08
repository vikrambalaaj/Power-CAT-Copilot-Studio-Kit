# Velora Executive Agent for Teams and Microsoft 365 Copilot

The target solution uses all nine executive-agent capabilities and exactly two SAP MCP servers:

1. **SuccessFactors MCP** for headcount and Emiratisation.
2. **S/4HANA MCP** for receivables, payables, P&L, and budget variance.

The repository implements both SAP MCP servers and connects both plugin manifests to one Copilot declarative agent. Microsoft 365 tenant integrations, an approved benchmark source, the governed agent-creation workflow, and end-to-end audit integration still require tenant configuration before all nine capabilities can be declared production-ready.

## Documentation

- [Capability blueprint](CAPABILITIES.md): ownership, behavior, controls, and acceptance criteria for all nine capabilities.
- [Architecture](ARCHITECTURE.md): two-MCP topology, identity boundaries, orchestration, and data flow.
- [MCP contracts](MCP_CONTRACTS.md): the six executive SAP queries and normalized response envelopes.
- [Deployment](DEPLOYMENT.md): environments, configuration, release gates, and rollout sequence.
- [Test plan](TEST_PLAN.md): functional, security, privacy, resilience, and executive acceptance tests.
- [Copilot experience](COPILOT_EXPERIENCE.md): conversation design, response contract, cards, and failure behavior.
- [Scheduled automation](AUTOMATION.md): versioned daily prompts, recurrence triggers, proactive Teams delivery, and safety controls.

## Required user experience

The executive asks one question in Microsoft 365 Copilot or Teams. The agent chooses the correct MCP server, returns a permission-trimmed answer, cites the system and business object, states freshness and confidence, and records a correlation ID for audit. Cross-domain questions may call both servers, but the answer must preserve each source separately.

## Local verification

1. Copy `.env.example` to `.env` and replace every placeholder.
2. Install the project with `pip install -e .`.
3. Start it with `python -m successfactors_mcp`.
4. Check `http://localhost:8082/health`.

The MCP endpoint is `http://localhost:8082/mcp`. It requires `X-API-Key: <MCP_API_KEY>` or `Authorization: Bearer <MCP_API_KEY>`. Anonymous mode is available only when `ALLOW_ANONYMOUS=true` is explicitly set for local development.

Write operations and arbitrary OData queries are disabled by default. Set `ENABLE_MUTATING_TOOLS=true` only after adding appropriate change controls and confirmation behavior.

## Deploy the MCP server

The included `manifest.yml` can be used with Cloud Foundry. Set secrets after pushing the application; do not put them in `manifest.yml`:

```text
cf set-env sf-hcm-mcp-server SF_API_URL "https://<tenant-api-host>/odata/v2"
cf set-env sf-hcm-mcp-server SF_COMPANY_ID "<company-id>"
cf set-env sf-hcm-mcp-server SF_USERNAME "<api-user>"
cf set-env sf-hcm-mcp-server SF_PASSWORD "<secret>"
cf set-env sf-hcm-mcp-server MCP_API_KEY "<long-random-secret>"
cf set-env sf-hcm-mcp-server SF_EMIRATI_FILTER "<tenant-specific OData filter>"
cf restage sf-hcm-mcp-server
```

Update `ALLOWED_HOSTS` and `MCP_GATEWAY_URL` if the deployed hostname differs from the checked-in hostname. The server must be reachable over HTTPS from Microsoft 365.

## Configure Copilot authentication

Production MCP plugins should not use anonymous authentication. Create an API-key authentication registration in the Microsoft 365 plugin vault that sends the same secret as `MCP_API_KEY` in the `X-API-Key` header. Record the resulting reference ID.

Regenerate the app manifests with the deployed URL and vault reference:

```text
MCP_GATEWAY_URL="https://your-mcp-host.example.com" \
MCP_PLUGIN_AUTH_TYPE="ApiKeyPluginVault" \
MCP_PLUGIN_AUTH_REFERENCE_ID="your-vault-reference-id" \
PUBLISHER_CONTACT_EMAIL="support@example.com" \
python deploy/regen_manifests.py
```

## Build and upload the Teams/Copilot package

```text
MCP_PLUGIN_AUTH_REFERENCE_ID="<successfactors-vault-reference>" \
python deploy/regen_manifests.py

S4_PLUGIN_AUTH_REFERENCE_ID="<s4hana-vault-reference>" \
python ../ask-s4hana/deploy/generate_plugin.py

python deploy/build_agent_package.py
```

This creates `velora-hcm-agent.zip`. Upload that ZIP through Teams Admin Center for an organizational deployment, or use Microsoft 365 Agents Toolkit to provision and publish it. The ZIP contains one Copilot declarative agent, two Remote MCP plugin manifests, tool descriptions, instructions, and the required icons.

Before uploading, replace both plugin-vault references with the values created in your tenant. The build command refuses to create a package while either placeholder remains.

## Data behavior

- Tool results are returned as MCP `structuredContent` plus JSON text.
- No demonstration headcount or compliance values are substituted for failed requests.
- Emiratisation requires a tenant-specific `SF_EMIRATI_FILTER` and is returned only as an aggregate.
- File logging is off by default and redacts common personal identifiers when explicitly enabled.
- Access to SuccessFactors uses the configured service account and its RBP permissions; the app does not claim end-user delegation.
- Successful read queries use a bounded, permission-scoped cache by default. See [Caching](CACHE.md) for freshness, invalidation, and tuning.

## Production completion rule

Do not label the solution as covering all nine capabilities until every acceptance test in [TEST_PLAN.md](TEST_PLAN.md) passes and every row in [CAPABILITIES.md](CAPABILITIES.md) has an accountable owner. In particular, the current SuccessFactors service-account model is not equivalent to the executive's own SAP identity; delegated identity or a formally approved service-account authorization model must be selected and documented.
