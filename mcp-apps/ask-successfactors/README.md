# Velora HCM Agent for Teams and Microsoft 365 Copilot

This project contains a secured remote MCP server for SAP SuccessFactors and a Microsoft 365 app package containing a declarative agent.

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
python deploy/build_agent_package.py
```

This creates `velora-hcm-agent.zip`. Upload that ZIP through Teams Admin Center for an organizational deployment, or use Microsoft 365 Agents Toolkit to provision and publish it. The ZIP contains the Teams/Microsoft 365 manifest, declarative-agent manifest, MCP plugin manifest, tool descriptions, instructions, and the required icons.

Before uploading, replace the plugin-vault reference with the value created in your tenant. The build command refuses to create a package while that placeholder remains.

## Data behavior

- Tool results are returned as MCP `structuredContent` plus JSON text.
- No demonstration headcount or compliance values are substituted for failed requests.
- Emiratisation requires a tenant-specific `SF_EMIRATI_FILTER` and is returned only as an aggregate.
- File logging is off by default and redacts common personal identifiers when explicitly enabled.
- Access to SuccessFactors uses the configured service account and its RBP permissions; the app does not claim end-user delegation.
