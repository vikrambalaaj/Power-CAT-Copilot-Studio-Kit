# Repository review — 15 September 2026

## Conclusion

**Everything is not yet updated or ready for sign-off.** Today's S/4HANA changes are in local revision `91e70e04d16e9a413cc75fedb3afffe071dab13b`, but deployment, packaging, dependencies, tests, and several runtime behaviors remain inconsistent.

The local `feat/sf-prod-integration` branch is **15 commits ahead and zero behind** the freshly fetched GitHub `fork/feat/sf-prod-integration` branch (`b3b96b028f021caa11614fa324262e06d17a3f2e`). This establishes that those commits have not reached that tracking branch. It does not establish Azure DevOps or deployed-image state.

## Scope and evidence

- Repository-wide authored-file inventory and static validation, with targeted manual review of runtime boundaries, recent changes, calculations, deployment, packaging, and earlier findings.
- 376 authored source/configuration files hashed; all retain their starting hashes. Dependency trees, generated output, historical evidence, downloads, and media were excluded from this authored inventory. The repository also tracks 13,201 files under dependency directories; these were assessed through dependency audits, not a manual review of every dependency line.
- 164 authored Python files parsed successfully. Another 26 Python files in the Salesforce and ServiceNow sample ZIPs parsed successfully; these samples were not live-tested.
- 74 JSON and 67 XML definitions passed strict parsing. Two package JSON files use comments/trailing commas and do not pass strict JSON parsing; this alone is not a confirmed application defect because the package tooling may support those extensions.
- Python tests ran in an isolated review environment, with provider credentials removed, dotenv reads disabled, and outbound connections blocked. Productivity and Facilitator needed sibling source directories added for the final workspace-level test runs. Their initial standalone collection failures are preserved separately.
- Both TypeScript projects built. All six Bicep templates compiled. Docker's daemon was unavailable; no container build, image scan, or live provider/deployment verification was performed.
- The .NET package built successfully in an isolated copy after restoring packages and selecting the installed .NET Framework 4.7.2 reference assemblies. It emitted one PowerApps SDK compatibility warning and zero errors. Initial attempts using stale restore assets/default reference discovery failed; all logs are retained, with the successful outcome in `dotnet-build-restored.log`.
- This is a review, not a certification that every execution path or packaged Power Platform behavior has been exercised. No application fixes, pushes, deployments, or provider business writes were performed.

## Findings requiring action

### F01 — P1: Facilitator's deployable package cannot import its new dependencies

[institutional_memory.py:29](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/institutional_memory.py:29) imports `productivity_mcp.business_repository`; other new Facilitator modules also import Productivity. It additionally imports `shared_mcp.logger`, which is absent from Facilitator's shared directory. [Dockerfile:12](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/Dockerfile:12) copies only Facilitator, its own shared directory, and the entry point. Its requirements do not install the missing project.

Standalone test collection reproduces `ModuleNotFoundError: productivity_mcp` in all five Facilitator test modules. Adding sibling source and Productivity's shared modules permits 53 tests to pass, but that does not repair the container. Package the actual shared dependencies and verify startup from the same context used to build the release.

### F02 — P1: S/4HANA metadata access bypasses authentication

[server.py:96](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/server.py:96) explicitly exempts `/schema` and paths beginning with `/schema` from the authentication middleware. [server.py:325](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/server.py:325) then uses the configured SAP identity to retrieve and return metadata.

The offline reproduction sets anonymous access false and an API key, then sends no credentials: `/mcp/tools` returns 401 while `/schema` returns 200 and makes one mocked authenticated provider request. Require authorization before metadata retrieval and handle upstream failures explicitly. Evidence: `probes.json`.

### F03 — P1: Approval-card tokens can be consumed repeatedly

[idempotency-signer.ts:57](/Users/vikrambala/copilotstudio/mcp-apps/dynamic-adaptive-card-service/src/security/idempotency-signer.ts:57) reads only the first two dot-separated segments, but records the entire supplied string as the consumed token. Adding `.extra` preserves the valid signature while changing the replay key.

The fresh probe accepts the original token, rejects its exact replay, and accepts two suffixed replays. A fresh signer instance also accepts the same token because consumption is held only in memory. Reject noncanonical token structure and atomically persist consumption using a signed stable identifier. Evidence: `node-probes.json`.

### F04 — P1: The evaluation gate passes incomplete evaluations

[scoreCalculator.ts:73](/Users/vikrambala/copilotstudio/agent-review-pipeline/src/evaluation/scoreCalculator.ts:73) uses the available stage as the complete score when another stage is absent. The orchestrator records stage errors without making them a release failure.

Fresh probes with either Stage B or Stage C missing return `overallScore: 100` and `passed: true`. The existing three tests pass partly because one explicitly expects this behavior. Require successful completion of mandatory stages before passing the gate. Evidence: `node-probes.json`, `pipeline-tests.log`.

### F05 — P1: Production dependency vulnerabilities remain unresolved

Fresh production npm audits report **one high affected package** in the pipeline (`js-yaml`) and **seven affected packages** in Cards (four high, three moderate). The isolated Python environment flags production packages `mcp==1.26.0` and `cryptography==46.0.3`, plus the test-only package `pytest==8.4.2`. The Python report contains duplicated advisory IDs, so its raw 21-entry total should not be presented as 21 distinct vulnerabilities.

SuccessFactors and Productivity constrain cryptography to `<46.0.4`, excluding the fixes reported by the audit. Update constraints and lockfiles together, then rerun transport, cryptographic, and application checks. Audit findings establish affected versions, not exploitation in this deployment. The pipeline's installed js-yaml is 4.3.1; the maintainer identifies 4.3.2 as a fixed version for its high CPU-exhaustion issue. [Maintainer advisory](https://github.com/nodeca/js-yaml/security/advisories/GHSA-2883-xcg3-v3hh). Also see [cryptography's advisory](https://github.com/pyca/cryptography/security/advisories/GHSA-537c-gmf6-5ccf).

Evidence: `pipeline-npm-audit.json`, `cards-npm-audit.json`, `python-audit.json`, and both `*-outdated.json` files.

### F06 — P1: PostgreSQL support is missing its production driver dependency

[operation_store.py:649](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/operation_store.py:649) and `postgres_outbox_store.py:38` import `psycopg2`. Neither [requirements.txt](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/requirements.txt) nor the project dependency list declares it. The Dockerfile installs only requirements.txt.

When PostgreSQL is selected in a clean image, the store cannot obtain a connection. Add the matching driver and exercise the real PostgreSQL lifecycle, including concurrent workers and restart recovery. Workspace tests using SQLite do not validate that deployment path.

### F07 — P1: Productivity's image context includes a local environment file

[Dockerfile:8](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/Dockerfile:8) uses `COPY . .`. The service directory contains `.env` and has no `.dockerignore`. A build from this working directory therefore copies that environment file into the image. This review did not inspect or disclose its values or establish that any image was distributed.

Use selective source copies and an explicit context exclusion. The previously identified solution ZIP issue is improved: the current platform ZIP contains four entries and no environment file. That correction does not fix the separate Docker context.

### F08 — P1: Card production startup and generated output are not aligned

[idempotency-signer.ts:16](/Users/vikrambala/copilotstudio/mcp-apps/dynamic-adaptive-card-service/src/security/idempotency-signer.ts:16) requires `TOKEN_SIGNING_SECRET` in production, but [docker-compose.yml:75](/Users/vikrambala/copilotstudio/mcp-apps/docker-compose.yml:75) sets production mode without supplying it. The documented Compose setup therefore cannot start this service as supplied.

The committed `dist/security/idempotency-signer.js` is also older than its source and lacks that production check. A fresh TypeScript build changed it; the exact difference is preserved in `tracked-build-drift.patch`. `npm start` uses that committed output unless the project is rebuilt. Supply the production secret through deployment configuration and make generated output reproducible.

### F09 — P2: Budget summary silently ignores supplied filters

[tools.py:401](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/tools.py:401) discards financial-management-area, commitment-item, budget-version, and company-code filters for `BudgetConsumSummary`, although the handler still accepts them.

The fresh probe supplies all four and observes an empty provider filter dictionary. This can answer a narrowed request with a broader dataset. Implement supported summary mappings or explicitly reject unsupported filters before querying; do not silently omit them. Evidence: `probes.json`.

### F10 — P2: Budget field fallback overwrites valid numeric zeroes

[report_calculations.py:421](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/report_calculations.py:421) selects monetary aliases with `or`. A valid numeric zero in the preferred field is therefore replaced by a populated alternative field.

The probe supplies preferred budget and actual values of zero with alternate values 999 and 100. The calculated totals become 999 and 100. Choose aliases by explicit presence/non-null rules and validate conflicting values. Evidence: `probes.json`.

### F11 — P2: Workforce tenure crosses reporting boundaries too early

[policy_engine.py:189](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/policy_engine.py:189) rounds tenure to one decimal before [group classification:202](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/policy_engine.py:202). On 15 September 2026, an employee hired on 1 October 2025 is classified as `1–3 years`, before their first anniversary.

The existing `test_tenure_group_demographics` fails with that case. Use exact dates or unrounded duration for classification, reserving rounding for display.

### F12 — P2: Connector, deployment, and version alignment is incomplete

- S/4HANA's Swagger now declares API-key security and points to the Azure Container Apps endpoint. Its runtime discovery excludes Budget Transfers and P&L and uses BudgetConsumSummary. These updates are present.
- Productivity, Facilitator, and SAC connector Swagger files still omit security declarations. A live connector could have separately configured authentication; that was not inspected. Their generated files alone do not provision it.
- [.github/workflows/deploy-s4-acr.yml:15](/Users/vikrambala/copilotstudio/.github/workflows/deploy-s4-acr.yml:15) still advertises a tag input that the build ignores and publishes hard-coded `1.1.6` tags. The S/4 project reports 1.3.0, health/Swagger report 2.0.0, and the recent deployment commit mentions 1.2.4. Define one release-to-image mapping.
- The deployment shell reads `ENTRA_INBOUND_AUDIENCE`, while the shared verifier reads `API_AUDIENCE` or `ENTRA_CLIENT_ID`; reconcile the contract and provision it explicitly.
- The local branch has not been pushed to its GitHub tracking branch. No assertion is made about current cloud deployment parity.

## Additional concerns identified during manual review

- Scheduled subscriptions check whether a run exists, send the email, and only then record the run. These are separate operations in `worker.py:81–146`; two workers can both pass the check, and a crash after sending permits another send. The durable outbox's concurrency tests do not establish safety of this separate subscription path. Route subscription delivery through an atomic claim/reconciliation flow.
- The worker passes `require_live_delivery` to the notification outbox, but does not pass it into subscription delivery or inspect the email receipt there. Non-email subscription channels also reach SUCCESS recording without a channel dispatch. These paths need explicit receipt/channel validation.
- The shared identity verifier still permits a configured test signing secret and test issuer without an environment restriction. This review established the source condition, not that a production deployment enables it.
- GitHub Pages still publishes the whole `docs` directory, including review material and backups. Restrict publication to an approved public directory. Actual public accessibility was not established.
- Local Git configuration contains a credential-bearing Azure DevOps remote URL. No value is included here. Use a credential manager and avoid embedding credentials in remote URLs.

## Fresh test results

| Suite | Passed | Failed | Notes |
|---|---:|---:|---|
| SuccessFactors | 94 | 2 | Tenure bug; stale audit expectation |
| Productivity | 196 | 1 | Workspace imports required; offline network guard changes expected error wording |
| S/4HANA | 39 | 0 | New probes reveal gaps outside existing tests |
| Facilitator | 53 | 0 | Workspace imports required; standalone image dependency gap remains |
| SAC | 3 | 0 | Mocked provider tests |
| Adaptive Cards | 6 | 0 | Replay probe exposes an untested path |
| Evaluation pipeline | 3 | 0 | Existing tests permit incomplete-stage passing |
| Credential architecture | 2 | 5 | Manifest mismatch and stale/unsafe test expectations |
| Cleanup transformation | 3 | 1 | Static transformation assertion fails |
| **Total after resolving workspace test imports** | **399** | **9** | **408 checks** |

Initial standalone collection also produced five Facilitator errors and one Productivity error; these are not double-counted in the table. Raw initial and workspace reports are retained.

The SuccessFactors audit test expects a buffered retry to become ALREADY_COMMITTED without a provider commit. The current BUFFERED result is safer; update that test rather than reintroduce the previous audit defect. The Productivity failure is the offline harness rejecting a network request, not evidence that a live authentication failure produced a simulated success. Architecture failures likewise include message-text mismatches, an unsafe expectation that buffered writes proceed, and a token test not requesting consumption; not every failing assertion is a production defect.

## Completion priorities

1. Fix deployable dependency packaging, metadata authorization, token replay protection, and incomplete evaluation passing.
2. Patch dependencies, supply deployment settings, and align source, generated files, connector exports, and image versions.
3. Correct budget filters/zero handling and tenure classification; update stale tests without weakening controls.
4. Verify subscription concurrency and real PostgreSQL behavior, then build and scan clean release images.
5. Push the approved release and verify authenticated live behavior and deployed image digests against that revision.

See `source-manifest.json`, `revision-status.json`, `test-summary.json`, `artifact-review.json`, dependency audits, build logs, and reproduction scripts for supporting evidence. The source remains unchanged; these review artifacts are the only intended workspace additions.
