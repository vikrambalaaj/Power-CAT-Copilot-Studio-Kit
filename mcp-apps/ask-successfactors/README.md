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

### Dataverse audit write contract

Use the table logical name `cre2f_veloraagentauditlog` and logical column names in the `create_record.item` object. Display names such as `Audit Detail` are invalid JSON properties for the Dataverse MCP operation; use `cre2f_auditdetail`. The approved properties are `cre2f_agentname`, `cre2f_auditdetail`, `cre2f_dataclassification`, `cre2f_demodata`, `cre2f_environment`, `cre2f_eventtime`, `cre2f_newcolumn`, `cre2f_operation`, `cre2f_outcome`, `cre2f_resultcount`, `cre2f_sourcesystem`, and `cre2f_toolname`. Audit writes are non-blocking and audit diagnostics must not appear in the business response.

## Recommended Copilot Studio and Dataverse sandbox path

Use a Power Platform **sandbox environment with Dataverse** for development and user acceptance testing. Dataverse MCP does not require a production environment. Promote the tested solution to a separate production environment only when it is ready for live users.

Recommended lifecycle:

| Stage | Power Platform environment | Data and MCP connection |
|---|---|---|
| Development | Sandbox | Synthetic or approved test data through the sandbox Dataverse MCP server |
| User acceptance testing | Separate sandbox, when available | Sanitized UAT data through the UAT Dataverse MCP server |
| Live operation | Production, non-default | Production-approved data through the production Dataverse MCP server |

Keep the agent, Dataverse tables, connections, security roles, and MCP server aligned within the same lifecycle environment. Do not connect a production agent to sandbox data or a sandbox agent to production data.

> **Scope:** This is the fastest path for an MVP when the available data is in Dataverse. It does not activate the SAP clients in this repository. The SAP-backed design still requires deployed SuccessFactors and S/4HANA MCP servers, SAP credentials, service/entity configuration, and an approved identity model.

### 1. Confirm licensing and capacity

1. Assign each maker a Microsoft Copilot Studio user license in the Microsoft 365 admin center.
2. Allocate Copilot Studio capacity through prepaid Copilot Credits or an approved pay-as-you-go plan.
3. Sign out and back in after a new license is assigned.
4. Do not rely on a trial for production: a trial supports creating and testing agents but does not provide the normal production publishing entitlement.

Microsoft guidance: [Get access to Copilot Studio](https://learn.microsoft.com/en-us/microsoft-copilot-studio/requirements-licensing-subscriptions).

### 2. Create or request the sandbox

A Power Platform administrator normally performs these steps:

1. In the [Power Platform admin center](https://admin.powerplatform.microsoft.com), open **Manage > Environments** and select **New**.
2. Set the type to **Sandbox**, choose the organization's approved region, and provide a clear development/testing purpose.
3. Set **Add a Dataverse data store** to **Yes**.
4. Configure the Dataverse language and base currency.
5. Associate a Microsoft Entra security group containing only approved makers, administrators, and testers.
6. Save and wait for provisioning to finish.

Environment creation normally requires available Dataverse capacity. A sandbox is persistent and intended for nonproduction development and testing; unlike a trial, it does not expire after 30 days. Sandboxes also support copy and reset operations. Reset permanently deletes the sandbox contents.

Microsoft guidance: [Manage sandbox environments](https://learn.microsoft.com/en-us/power-platform/admin/sandbox-environments) and [Work with Power Platform environments in Copilot Studio](https://learn.microsoft.com/en-us/microsoft-copilot-studio/environments-first-run-experience).

If the sandbox was copied from production, review and disable or redirect flows, email, webhooks, custom connectors, and other external integrations before leaving administration mode. Prefer synthetic or sanitized data for development.

### 3. Assign access and Dataverse roles

Membership in the environment security group permits the user to enter the environment, but it does not grant access to Dataverse records. Assign at least one Dataverse security role to every user.

Recommended maker roles:

- **Basic User** for normal Dataverse access.
- **Environment Maker** for creating Power Platform resources.
- **Agent author** for creating Copilot Studio agents in the environment.
- **System Customizer** when the maker must create tables or columns, customize solutions, or export/import agents.

Use **System Administrator** only for administrators. For testers, create a least-privilege role that grants read access only to the approved business tables.

Assign roles from **Power Platform admin center > Manage > Environments > [sandbox] > Settings > Users + permissions > Users > Manage security roles**.

Microsoft guidance: [Assign security roles](https://learn.microsoft.com/en-us/power-platform/admin/assign-security-roles) and [Control environment access with security groups](https://learn.microsoft.com/en-us/power-platform/admin/control-user-access).

#### Troubleshoot roles assigned through a group

Seeing a role on a group does not by itself prove that a particular user inherits it. Verify all of the following:

1. The Dataverse team type is **Microsoft Entra ID Security Group** or **Microsoft Entra ID Office Group**, not only an environment access group.
2. The team's **Microsoft Entra Object ID** matches the intended Entra group exactly.
3. The required roles, such as **System Customizer** and **Bot Author** or the tenant's current agent-maker role, are assigned to that Dataverse group team.
4. The maker's exact sign-in account is a member of the linked Entra group. A direct membership is the simplest option when troubleshooting nested-group or synchronization issues.
5. The team's membership type includes the maker's Entra user type and placement: member, guest, or owner.
6. After a membership change, the maker signs out, signs back in, and opens the environment so Dataverse can derive group-team membership at run time.
7. Recheck the user's effective Dataverse privileges. Creating tables requires the `prvCreateEntity` privilege; a visible group-role assignment is not sufficient if this effective privilege is still absent.

For the fastest diagnostic workaround, assign **System Customizer** directly to the maker's Dataverse user. If direct assignment works, correct the Entra membership or Dataverse group-team mapping before removing the temporary direct assignment. Microsoft guidance: [Manage Microsoft Entra group teams](https://learn.microsoft.com/en-us/power-platform/admin/manage-group-teams).

### 4. Verify the environment in both portals

1. Open [Power Apps](https://make.powerapps.com) and select the sandbox from the environment picker.
2. Confirm access to **Solutions**, **Tables**, and **Connections**.
3. Open [Copilot Studio](https://copilotstudio.microsoft.com) and select the same sandbox.
4. Confirm that **Agents > New agent** is available.

If the environment is missing from Copilot Studio, confirm that it has a Dataverse database, uses a supported region, includes the user in its security group, and assigns the user an appropriate Dataverse role. Do not build the agent in the Microsoft 365 Copilot Chat environment; Microsoft reserves that environment for billing management rather than full Copilot Studio authoring.

### 5. Create a solution before creating components

In the sandbox, create an unmanaged solution such as `Velora Executive Agent`. Create or edit the agent, tables, flows, connection references, environment variables, and security roles in this solution context.

Creating the agent in solution context helps new topics, tools, flows, MCP connections, and other dependencies remain attached to the solution. Before every export, select the agent and use **Advanced > Add required objects**.

Microsoft guidance: [Agents missing components in a solution](https://learn.microsoft.com/en-us/troubleshoot/power-platform/copilot-studio/lifecycle-management/agents-solution-mapping).

### 6. Create an aggregate Dataverse data model

For a safe MVP, use aggregate metrics instead of employee-level HR records. A single `Executive Metric` table can contain:

| Column | Suggested type |
|---|---|
| Metric Name | Primary text |
| Metric Code | Text |
| Domain | Choice: Workforce, Finance |
| Company Code | Text |
| Department | Text |
| Category | Text |
| Period End | Date |
| Metric Value | Decimal |
| Unit | Choice: Count, Percent, Currency |
| Currency | Text |
| Target Value | Decimal |
| Status | Choice: On Track, At Risk, Off Track |
| Source System | Text |
| As Of | Date and time |
| Is Demo Data | Yes/No |

Load synthetic records for headcount, Emiratisation, receivables aging, payables aging, P&L, and budget variance. Set `Is Demo Data` to `Yes` and label the source clearly. Do not copy production personal data into the sandbox without privacy and security approval.

Create a `Velora Executive Agent Reader` role that grants organization-level **Read** on approved aggregate tables and no create, update, delete, assign, or share privileges. Test with this role rather than a System Administrator account.

### 7. Enable and connect Dataverse MCP

The Microsoft Copilot Studio client for Dataverse MCP is enabled by default in supported environments, but an administrator should verify it:

1. In Power Platform admin center, open **Manage > Environments > [sandbox] > Settings > Product > Features**.
2. Find **Dataverse Model Context Protocol**.
3. Turn on **Allow MCP clients to interact with Dataverse MCP server**.
4. Save the setting.

A Power Platform administrator is required to change this setting. A Managed Environment is required only for advanced connector-policy management, not for ordinary Copilot Studio access to Dataverse MCP.

Microsoft guidance: [Configure the Dataverse MCP server](https://learn.microsoft.com/en-us/power-apps/maker/data-platform/data-platform-mcp-disable).

Connect it to the agent:

1. In Copilot Studio, select the sandbox and open the agent.
2. Enable generative orchestration.
3. Under **Settings > Security > Authentication**, select **Authenticate with Microsoft**.
4. Open **Tools > Add a tool > Model Context Protocol**.
5. Select **Dataverse MCP Server**, create a Dataverse connection if prompted, and select **Add to agent**.
6. Edit the connected server and review its individual tools.

Microsoft guidance: [Connect Dataverse MCP to Copilot Studio](https://learn.microsoft.com/en-us/power-apps/maker/data-platform/data-platform-mcp-copilot-studio).

### 8. Apply a read-only MCP policy

For the first release:

- Enable metadata description and approved search/read-query functions.
- Disable create, update, and delete functions.
- Restrict the agent instructions to approved aggregate tables.
- Use user authentication so Dataverse applies the current user's security roles.
- Do not depend only on instructions for authorization; Dataverse roles are the enforcement boundary.

Recommended agent rules:

1. Use only approved aggregate Dataverse tables.
2. Never invent, estimate, or silently substitute values.
3. Clearly label demo data.
4. State period, as-of time, source, and currency where applicable.
5. Respect the current user's Dataverse permissions.
6. Never create, update, or delete Dataverse records.
7. Never reveal names, personal identifiers, email addresses, salaries, or employee-level HR records.
8. Return Emiratisation results only as aggregates.
9. Keep workforce and finance sources separate in cross-domain answers.

### 9. Test in the sandbox

Start with connectivity tests:

- `Show the Dataverse tables I can access.`
- `Describe the Executive Metric table.`
- `How many Executive Metric records can I access?`

Then test business behavior:

- `What is the latest total headcount?`
- `Show headcount by department.`
- `What is the Emiratisation ratio versus target?`
- `Show receivables aging in AED.`
- `Compare actual spending against budget.`
- `Summarize revenue and operating cost.`

Finally, use a nonadministrator test account to verify that restricted tables remain unavailable, writes are blocked, and requests for personal employee data are refused. Publish inside the sandbox and repeat the tests in a new conversation because authentication and published-agent changes do not affect the existing live version until republished.

### 10. Promote the tested solution

Use a separate, non-default production environment for live agents:

1. Add required objects to the sandbox solution and increment its version.
2. Export a managed solution for production, or deploy it through Power Platform Pipelines.
3. Import it into the production environment.
4. Create or bind production connection references and environment-variable values.
5. Verify that the production Dataverse MCP Server is enabled and connected in production.
6. Load only production-approved data.
7. Reassign production security roles and repeat tests using normal user accounts.
8. Publish the production agent and release it to a controlled pilot group before wider rollout.

Power Platform Pipelines can enforce ordered deployment through test and production stages and validate missing dependencies. Microsoft guidance: [Run pipelines in Power Platform](https://learn.microsoft.com/en-us/power-platform/alm/run-pipeline).

### Dataverse MCP readiness checklist

- Copilot Studio user license assigned.
- Copilot Studio capacity or pay-as-you-go configured.
- Sandbox environment created with Dataverse.
- Approved Microsoft Entra security group associated with the sandbox.
- Maker and tester Dataverse roles assigned.
- Unmanaged development solution created.
- Aggregate test table and synthetic data prepared.
- Dataverse MCP enabled for Copilot Studio.
- Agent uses generative orchestration and Microsoft authentication.
- Write-capable MCP tools disabled.
- Functional and negative authorization tests pass using a nonadministrator account.
- Production deployment uses a separate production environment and production connection.

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
