# Velora One: single-agent implementation handoff

Prepared 7 September 2026. This is an execution specification for the next developer/model, not a declaration that the migration is complete.

## 1. Objective and boundaries

Keep **Velora One** as the sole conversational agent. Move the required productivity tools and orchestration into Velora One, then remove its connection to **Velora Productivity Agent** and delete that separate agent after a verified cloud backup and successful replacement tests. Preserve useful Productivity API/MCP services and audit records: a backend service is not a conversational agent.

All production custom services run in Azure; their container images live in ACR and execute in Azure Container Apps. Copilot Studio and Microsoft-managed connectors remain Microsoft-managed services; they are not deployed into ACR. No production localhost endpoints, local disk persistence, SAP Cloud Foundry endpoints, or simulated business responses. P&L is out of scope. Do not send emails, post messages, or create meetings during validation without explicit authorization for the exact external action.

Do not change the production agent's model merely because a cheaper coding model is used for this implementation.

## 2. Verified starting position

Observed directly in Copilot Studio on 7 September 2026:

- Environment: `Velora-AgenticAD-Dev`, ID `b152cae8-d51e-ef06-9b0a-12ff9d89dc53`.
- Velora One ID: `8bf961c8-f496-f111-b8db-7ced8dac2bdc`.
- Both Velora One and Velora Productivity Agent exist. Velora One has an actual connected-agent entry for Productivity; its component ID is `820157fd-efe3-4498-8e8b-50feb0cff82b`. This is not evidence that a particular conversation invoked it.
- Velora One already lists Work IQ Calendar, Work IQ Mail and Dataverse MCP tools. The overview is not the complete tool inventory.
- The overview shows published 31 August 2026 and one warning. Investigate the warning; do not dismiss it or change the model to hide it.
- Live instructions contain contradictory appended sections: one requires the verified workforce card, another requires aggregate MCP calls; one says calendar is unavailable, another routes to calendar. P&L is still explicitly routed. Sources are discouraged even though the business requirement requires them. The displayed instruction text ends mid-sentence, so check the editor's complete value and length.
- Repository parent plugin uses OpenAPI `HandleParentHandoff` against a Cloud Foundry URL with authentication `None`. The backend `/handoff` is operation dispatch, not by itself an agent-to-agent conversation. Do not confuse this package with the verified live connected-agent configuration.
- Earlier source review found app-only Graph authentication and mock collections. Recheck current code: the workspace is being edited concurrently and historical findings are not current proof.

Completed backup: `docs/single-agent-backup-20260907T123646Z/agent-source-backup.zip`, 42 files, integrity checked; hashes in adjacent `manifest.json`. **This is repository source only, not a restorable live Copilot Studio export. No live agent was changed, published or deleted during this preparation.**

## 3. Work in checkpoints

Maintain `execution-status.md` with each checkpoint marked NOT STARTED, DONE, FAILED or BLOCKED, evidence path, timestamp and next action. Re-read current files before edits and preserve unrelated changes. Do not represent plans, configuration checks or authentication prompts as successful business tests.

### A. Inventory and restore-ready backup

1. Read repository guidance. Record Git revision and the affected working-tree changes. Never export `.env` values, tokens or client secrets into reports.
2. In the verified environment, inspect both agents' complete instructions, topics, tools, connections, connected agents, knowledge, channels, authentication, sharing, triggers and evaluation profiles.
3. Build `tool-migration.csv` with capability, current agent, tool/operation, connection reference, authentication mode, read/write scope, destination, dependent topic, and validation case. Identify duplicate direct-tool and connected-agent routes.
4. Use Power Platform Solutions to export both agents with required components and dependencies. Include custom connectors, connection references, topics and agent components; record dependencies that require separate export. Do not assume connection secrets or signed-in sessions are included.
5. Save exported ZIPs, export version, environment and component IDs, export completion evidence and SHA-256 checksums in an approved backup location. Keep runtime data separate from source backups.
6. Validate archive integrity and inventory. Prefer a restore/import test in an authorized non-production environment; report explicitly if restore has not been tested. Write import order, connection-rebinding, sharing and republish steps.
7. Do not delete the child while this cloud export is absent or incomplete. A screenshot or repository ZIP is insufficient.

### B. Choose one route per capability

Use Velora One -> direct tool/MCP -> data source. Do not introduce a new conversational child.

| Capability | Preferred direct route | Required behavior |
|---|---|---|
| Email | Existing Work IQ Mail if its actual operations fit | Read/search; draft preview; send only through an explicitly approved action |
| Calendar | Existing Work IQ Calendar | Schedule reads and preparation; approved changes only |
| Teams | Existing Work IQ Teams if available and configured | Authorized mentions, messages and channel files |
| Tasks | Verified Planner/To Do connector or delegated API | Real tasks and due dates; no fabricated task store |
| Files and policies | Verified OneDrive/SharePoint tools | Permission-trimmed retrieval and business-readable sources |
| Daily plan/brief/checklist/wrap-up | Velora One combines direct tool results | Consistent user and date window, honest partial results |
| Custom workflows, approvals, audit | Retained Azure Productivity API where needed | Validated identity, durable state, explicit operation results |
| Workforce | Existing verified workforce-card route | Preserve established definitions; remove conflicting aggregate routing |
| Finance | Verified S4 service | AR ageing, AP ageing, budget transfer and budget consumption only |

Compare actual operation coverage before choosing managed versus custom routes. Do not keep both as interchangeable fallbacks: that can produce duplicate writes and different user permissions. Missing capabilities must be added and tested, or reported unavailable.

### C. Authentication and the earlier IT request

1. Retain the existing Velora One SSO registration and verify its actual Teams channel application ID, API URI, token exchange scope, redirect configuration and tenant. Do not infer these solely from the bot record ID.
2. Single-agent consolidation does not pass an SSO token automatically into every tool. Inspect each managed connector's own authentication and required connection. Existing admin consent on a custom app does not automatically consent Microsoft-managed Work IQ applications.
3. For custom APIs receiving user data: validate signed Entra access tokens, issuer, audience, expiry, tenant and delegated scope. Derive user identity from validated claims, never from a model-supplied email or object ID.
4. If the custom API calls Graph for that user, implement delegated on-behalf-of exchange and permission-trimmed Graph access. Do not use client-credentials Graph access as proof of the user's entitlement.
5. If using Microsoft's custom-connector OBO pattern, configure the API resource app and connector client as documented. Request only Graph scopes required by the selected operations. Mail sending, meeting changes and Teams posting require separate justified write permissions. Read-only file search does not justify broad file/site writes.
6. Retain API/connector registrations that the backend still needs. Remove only child-agent-specific credentials or grants after dependency verification; deleting the agent does not justify deleting shared applications.
7. For service audit writes, use a restricted Dataverse application user with suitable table privileges; do not grant unrestricted CRM access to each user-facing app merely for logging.
8. Record each connection as connected, expired, missing or untested. Admin consent does not remove MFA, Conditional Access or initial connection requirements. Evaluation needs a supported authenticated test profile with working connections.

Deliver `entra-changes.md`: actual registration name/ID, existing configuration, exact change, reason, owner and validation evidence. Never present proposed registration names as existing resources.

### D. Replace conflicting agent instructions

Export the original complete instructions first. Produce one coherent instruction set below the platform limit; do not append another policy block.

The replacement must require:

- Velora One owns the conversation and invokes configured tools directly. No Productivity child delegation.
- Fresh, authorized results for current data; no mock, example, remembered or public values substituted for enterprise data.
- One consistent reporting window and signed-in user across combined productivity requests. Resolve timezone from supported user settings; clarify only when required.
- For ordinary workforce aggregates use the existing verified card operation; preserve metric definitions, completeness and privacy rules. Use other workforce operations only for their verified supported scope.
- Finance includes only AR, AP, budget transfers and consumption. P&L requests receive a clear out-of-scope response; remove P&L tool exposure and topic references where present.
- Daily plan: retrieve schedule, priority mail and tasks, then synthesize priorities. Checklist: use retrieved items or explicitly supplied user context; label suggestions separately from retrieved tasks.
- Draft reply: locate the intended person/thread; clarify ambiguous recipients, then prepare an unsent draft. Do not treat missing permission to send as inability to compose a draft.
- Wrap-up: use verified completed activity and open items; do not turn meetings attended into claimed achievements. Produce an unsent draft.
- Every data-bearing response includes a short business source and reporting period, for example “Source: your Outlook calendar — today.” Only cite sources actually retrieved; avoid endpoints, IDs and raw errors in business responses.
- Partial results stay visible with missing portions named in business language. Never claim an action completed without its provider confirmation.
- Writes require a concrete preview, exact target, user confirmation and backend enforcement. Retries must not duplicate actions.
- Audit records contain required structured operation evidence, not secrets, hidden reasoning or unnecessary personal content. Be honest if recording failed.

Save the exact replacement text in `VELORA_ONE_INSTRUCTIONS.txt`; review and test before publication. Remove stale source-package instructions too, so the next deployment does not restore old routing.

### E. Azure runtime and controls

1. Inventory actual Azure resource groups, ACR images, Container Apps, jobs, identities, ingress, revisions and storage. Historical inventory is not deployment evidence.
2. Build custom services in ACR/approved Azure CI. Deploy immutable image digests into Container Apps. Replace old Cloud Foundry URLs in deployed connectors and source packages with verified Azure endpoints.
3. Require authentication on productivity endpoints; use managed identity/Key Vault for backend secrets and restricted permissions. No secrets in images or connector descriptions.
4. Persist approvals, idempotency keys, job state and audit/outbox records in an appropriate Azure/Dataverse store. No in-memory-only success or local SQLite/files as production truth.
5. For scheduled jobs, verify the job invokes the intended command, actually runs, and has its required configuration and durable storage. Deploying an HTTP server as a job is not successful scheduling.
6. Record UTC time, validated actor, operation, source system, request correlation, approval reference, target reference with appropriate minimization, provider receipt, result status and failure category. Bind approval to the user and exact normalized operation, expire it, and consume it atomically. Audit writes must survive restart.
7. Remove runtime seeded business data and simulated success branches. Keep synthetic fixtures isolated in tests; never delete legitimate Dataverse business records because they look like examples. Any cloud data cleanup needs an exact reviewed inventory and backup.
8. For writes, fail safely if required authorization/approval/audit reservation cannot be persisted. If the provider succeeds but final audit persistence fails, retain recovery evidence and reconcile; never blindly resend.

### F. Stage, verify, publish, then remove the child

1. Add missing direct tools to Velora One; bind verified connections and permissions.
2. Replace conflicting instructions and topic routes. Keep the backed-up child available for rollback while validating the parent.
3. Detach the connected-agent route in the draft after direct tools are ready. Run regression tests and inspect traces: there must be no child invocation.
4. Publish the validated single-agent configuration. Confirm the target Teams/M365 channel is using that version and repeat authenticated smoke tests there.
5. Delete only the verified Velora Productivity Agent after backup and replacement validation. Follow platform requirements for destructive confirmation if presented. Preserve backend services, shared connectors, registrations, source systems and audit history.
6. Verify the agent list, parent connected-agent list, topics and runtime traces. Remove obsolete child packaging/build references from active deployment paths after backing them up. Check that no pipeline recreates the child.
7. If essential replacements fail, record a blocked migration and retain the child until fixed. Never claim “working fine” solely because deletion succeeded.

## 4. Required test evidence

For every case record environment, published revision, timestamp, test user role, input, expected outcome, actual outcome, tool trace, provider evidence and audit correlation. Redact private content from reports. General-quality grades are supplementary, not business acceptance.

| ID | Test | Acceptance |
|---|---|---|
| T01 | Plan my day | Real calendar/mail/tasks combined; user/timezone consistent; no child call |
| T02 | Daily morning brief | Verified priorities with sources and period |
| T03 | Today's work and schedule | Actual schedule and tasks; no invented activity |
| T04 | Urgent unread emails | Matches authorized mailbox results |
| T05 | Meeting preparation | Actual meetings and retrieved context |
| T06 | Overlapping/back-to-back meetings | Correct times, timezone and overlap calculation |
| T07 | Planner/To Do due this week | Correct owner and date boundary; honest source coverage |
| T08 | Leadership mentions | Authorized Teams evidence; no unsupported leadership inference |
| T09 | Draft reply to Ahmed | Correct thread or clarification; unsent preview; no send call |
| T10 | Travel policies | Real authorized documents with sources |
| T11 | Schedule with Sarah | Resolve identity and time, preview; no creation before approval |
| T12 | Waiting approvals | Real approval source or explicit unavailable status |
| T13 | Rest-of-day checklist | Grounded actionable list; suggestions distinguished |
| T14 | Executive Committee deck | Authorized file and correct date window |
| T15 | End-of-day wrap-up | Verified achievements/open items, unsent draft |
| T16 | Missing/expired connection | Honest partial result and actionable sign-in guidance; graded blocked, not completed |
| T17 | Two users, different mailboxes | No cross-user data or token leakage |
| T18 | Forged identity, wrong tenant/audience, expired token | Rejected before data access |
| T19 | Changed recipient/body after approval; replay; restart | Stale/replayed approval rejected; no duplicate action |
| T20 | Audit outage/provider timeout/retry | Durable recovery and accurate outcome; no duplicate writes |
| T21 | SF headcount/joiners/leavers/attrition | Preserved definitions, consistent window, fresh route and source |
| T22 | AR/AP/budget transfers/consumption | Real mapped fields, currencies and reporting dates; no P&L routing |
| T23 | Service restart and scheduled job | State survives; intended job executes with recorded outcome |
| T24 | No-data and upstream failures | No runtime fixtures, fake receipts or invented values |
| T25 | Published-channel single-agent trace | Direct tools only; child absent after deletion |
| T26 | Backup restoration | Import dependencies, rebind connections and restore routing successfully, or explicitly mark untested |

Re-run the original 15 evaluation utterances with supported authenticated connections. Categorize failures as authentication, routing, data retrieval, reasoning, approval, audit or infrastructure. Do not label every failure a false failure or promise 100% because consent was granted.

## 5. Deliverables and completion gate

Deliver cloud backup ZIPs/checksums and restore instructions; tool-migration.csv; exact agent instruction text; Entra change matrix; source diff; Azure image digests/revisions; test results; deletion evidence; and an as-is report separating completed, blocked and untested items.

Completion requires verified backup, one published conversational agent, no remaining child dependency, real authorized data, functioning selected capabilities, Azure-hosted custom runtimes, durable controls/audit and evidenced regression results. If broader AIATC capabilities remain incomplete, list them individually; this consolidation does not by itself complete the entire capability tracker.

## 6. Suggested implementation model and working method

Use **GPT-5.4 mini with High reasoning** for bounded implementation checkpoints, tests, configuration editing and report generation. This is a cost-conscious coding-model recommendation, not a guarantee of correctness or a recommendation to replace Velora One's runtime model. Use the current stronger reviewer for a final focused review of authentication, approval integrity, backup/deletion readiness and evidence.

Give the implementing model this file plus access to the repository and approved cloud tools. Ask it to execute one checkpoint at a time, update the status ledger, and show changed files and real validation evidence. Avoid repeatedly loading the entire historical conversation. Escalate unresolved identity/authorization design to the reviewer instead of guessing.

Official references:
- Model: https://developers.openai.com/api/docs/models/gpt-5.4-mini
- Backup: https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-solutions-import-export
- Connector OBO: https://learn.microsoft.com/en-us/microsoft-copilot-studio/advanced-custom-connector-on-behalf-of
- Teams SSO: https://learn.microsoft.com/en-us/microsoft-copilot-studio/configure-sso-teams
- Connections: https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-connections
- Evaluation: https://learn.microsoft.com/en-us/microsoft-copilot-studio/analytics-agent-evaluation-results

Recheck Microsoft documentation before changing live authentication; product support and host-specific requirements can change.
