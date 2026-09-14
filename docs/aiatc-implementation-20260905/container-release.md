# SuccessFactors MCP — ACR image and Container Apps handover

The requested container image has been built and pushed into the existing Velora development Azure Container Registry. No running Azure Container App was created or updated. The current S/4HANA app was not changed.

## Exact release

- Registry: `azvelaiagentexecaidevcruaen.azurecr.io`
- Repository/tag: `velora-mcp-sf:aiatc-20260905-02`
- Immutable deployment reference: `azvelaiagentexecaidevcruaen.azurecr.io/velora-mcp-sf@sha256:af3e8effc487c391254aa8981b63771a907f07cc1a078a223da7df4ef1cdcee4`
- ACR build: `dgb`, Succeeded; finished 5 September 2026, 13:13 UTC / 17:13 UAE time.
- Platform: Linux AMD64; Python 3.11; application port 8082; runtime user 10001.
- Source base commit: `76511dcc51b9c58faced07d939b67127b066e8d9`, plus the current working-tree changes. This is not represented as a clean committed release.
- Earlier tag `aiatc-20260905-01` is superseded; use `02` and the digest above.
- Machine-readable evidence: `acr-build-result.json` and `container-smoke.log` in this folder.

## What changed

The previous Dockerfile did not include `deploy/copilot-workforce-card-openapi.json`, which the server reads during import. It is now copied explicitly. Pillow is now included in pyproject.toml, matching the existing requirements file; fonts are packaged so existing PNG charts work. The image runs as a non-root user with a writable log directory and a local health check. Build context uses an explicit allowlist and excludes environment files, caches, logs, tests and tenant reports.

The new `mcp-apps/ask-successfactors/deploy/build_image.sh` supports local AMD64 builds or a remote ACR build. It creates a restricted temporary source folder before uploading to Azure. It builds an image only; it does not deploy a Container App. Dependencies still include version ranges and the base tag is mutable; the recorded image digest fixes the actual release contents. A future release pipeline should resolve/lock dependencies and scan each candidate digest before promotion.

## Verification performed

The image was pulled back from ACR by digest and tested with dummy credentials and networking disabled. Checks passed: non-root user; required packaged OpenAPI file; no `/app/.env`; PNG chart generation; actual `python -m successfactors_mcp` startup; `/health` HTTP 200; protected route HTTP 401 without an API key; authenticated OpenAPI response; JSON connector MCP initialize and tools/list; mutating tools and the dedicated personal-info tool absent by default.

The existing SuccessFactors unittest suite completed **83 tests, OK**, inside the final image with test/manifest fixtures mounted read-only. It uses mocked or local fixture sources, not live SAP. The test process emitted an interpreter-shutdown async/logging cleanup warning after completion; the suite returned exit code 0. The first test attempt lacked manifest fixture mounts; the final run supplied them and passed. Full logs are retained. The live server process startup/shutdown smoke check also passed.

`containerapp.bicep` compiled successfully to `containerapp.arm.json`. Compilation validates template syntax/types; it is not an Azure deployment or connectivity test. No live employee query, email send, production Dataverse write or production cutover was performed.

## Container Apps deployment preparation

Use the separate SuccessFactors app with the existing environment if its networking is approved:

- Subscription: `subs-velora-agenticad` (`452b5b49-c61b-4991-a769-66ce6f37e1b1`).
- Resource group: `az-vel-agenticad-execai-dev-uaen-rg`.
- Environment: `agenticad-execai-dev-uaen-me-001`, UAE North.
- Existing app `agenticad-execai-dev-uaen-ca-001` runs S/4HANA; do not replace its image with SuccessFactors.

The template takes a new app name, existing environment ID, user-assigned identity ID, digest-pinned image, registry server, approved ingress/hostname configuration, SAP endpoint/company, approved Emiratisation target and Key Vault references. Choose the new app name with the infrastructure owner’s naming convention. It intentionally contains no SAP or Dataverse secrets and does not create role grants automatically.

The identity needs permission to pull this repository and read the specified Key Vault secrets. Use `AcrPull` where the registry's permission mode supports it, or the appropriate repository reader permission for an ABAC-enabled registry; verify registry mode before granting roles. Microsoft explains the distinction in its [ACR repository permissions documentation](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-rbac-abac-repository-permissions). Configure full HTTPS Key Vault secret URLs. The Dataverse client currently consumes `DATAVERSE_URL`, `AZURE_TENANT_ID`, `AZURE_CLIENT_ID` and `AZURE_CLIENT_SECRET`; managed identity for image pull does not automatically provide Dataverse application authentication. These configuration sources must match.

Required runtime secrets: MCP API key, SuccessFactors username/password, Dataverse application secret and a unique approval-signing secret. Required nonsecret settings: SAP HTTPS endpoint/company; Dataverse URL/tenant/application; approved target; public gateway base URL; precise allowed hosts. Set `ALLOW_ANONYMOUS=false`, `ENABLE_MUTATING_TOOLS=false`, `ENABLE_PERSONAL_INFO_TOOL=false`, and `ENFORCE_CONSENT_GATE=true`. The dedicated personal-info flag does not remove every other employee-level query tool; address the identity/consent findings in the main plan before general user exposure.

The template defaults to internal ingress. Copilot Studio must have an approved, actually reachable private/gateway connection; an internal Container App URL is not automatically reachable from Copilot Studio. If the design requires external ingress, use the authenticated approved gateway and verified caller enforcement, with admin paths excluded from ordinary executive access. Do not assume a shared API key supplies the executive’s identity.

Use one replica initially because MCP sessions, chart bytes and several caches are in memory. Prove session/asset behavior before horizontal scale-out. The template includes explicit startup/liveness/readiness HTTP probes. Today `/health` confirms the process responds, not that SAP/Dataverse are available; add dependency-aware readiness/operational checks as described in the main plan. Microsoft documents [managed-identity pulls](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity-image-pull), [Key Vault secret references](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets) and [probes](https://learn.microsoft.com/en-us/azure/container-apps/health-probes).

Before production: validate caller identity/admin isolation, raw-tool consent coverage, current source configuration, real Dataverse persistence, private DNS/TLS, source report reconciliation, connector authentication, source wording and chart delivery from the actual Teams channel. Existing source labels include test-tenant wording in some paths and must reflect the selected environment. The image is a tested packaging artifact; it does not implement the nine-capability roadmap or certify the application as production-ready.

For an update to an existing future SuccessFactors app, retain the previous revision/digest and environment configuration for rollback. Verify a candidate revision before traffic cutover. Changing a Key Vault value or registry tag does not substitute for a recorded, tested release. Record the final deployed revision, image digest and live verification run IDs in the evidence pack.
