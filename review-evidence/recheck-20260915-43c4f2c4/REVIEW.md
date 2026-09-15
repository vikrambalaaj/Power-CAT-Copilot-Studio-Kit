# Remediation recheck — 15 September 2026

## Result

**Not all fixed. All 408 existing tests now pass, but independent reproductions still demonstrate release-blocking defects.**

Reviewed revision: `43c4f2c4f0661ceaf8244f56a225ed9a1e0d2dda`, whose commit message claims F01–F12 are resolved. The fresh tests support the 408-pass claim; they do not support complete closure of the findings.

No application source changes, pushes, deployments, or provider business writes were performed. Python tests used fresh, isolated dependencies, removed provider credentials, disabled dotenv loading, and blocked outbound connections. Reproduction inputs and provider responses were synthetic.

## What is verified fixed

- **F01 packaging:** Facilitator now includes Productivity modules and the missing logger. All 53 Facilitator tests pass without sibling workspace imports. A separate environment containing only Facilitator's declared requirements successfully imports its server. A container startup was not performed.
- **F02 metadata authentication:** Unauthenticated `/schema` now returns 401, with zero mocked SAP requests.
- **F06 PostgreSQL driver declaration:** Productivity now declares `psycopg2-binary`. Actual PostgreSQL integration and recovery remain unverified.
- **F07 build-context inclusion:** Productivity uses selective source copies and a `.dockerignore` excluding environment files.
- **F09 filter loss:** All four previously discarded filters now reach the client. Whether the live BudgetConsumSummary entity supports these exact field names still needs provider-schema validation.
- **F10 numeric zero:** The original budget/actual alias reproduction now preserves both values as zero.
- **F11 tenure:** The workforce-tenure regression test passes after classification was changed to use unrounded duration.
- The original extra-segment card replay and same-process signer replay are rejected. A completely absent evaluation stage no longer passes the score calculator. These are partial fixes, with remaining failures below.
- Card generated JavaScript matches its source after the build. The image workflow now honors the tag input. Connector files contain security declarations, and Pages stages selected public content.

## Remaining blockers

### R01 — P1: A failed Stage B still passes when local patterns exist

[evaluationOrchestrator.ts:78](/Users/vikrambala/copilotstudio/agent-review-pipeline/src/evaluation/evaluationOrchestrator.ts:78) constructs a Stage B result from local patterns after the remote Stage B call fails. The new score calculator treats that constructed result as a completed mandatory stage.

The fresh end-to-end orchestrator probe forces Stage B to throw, supplies one passing local check, and returns a successful Stage C response. Result: `errors` contains the Stage B outage, but `passed=true` and score is 100.

**Fix:** Track mandatory stage completion separately from advisory/local results and make stage errors prevent release pass. Evidence: `additional-node-probes.json`.

### R02 — P1: Card replay storage fails open and remains non-atomic

[idempotency-signer.ts:46](/Users/vikrambala/copilotstudio/mcp-apps/dynamic-adaptive-card-service/src/security/idempotency-signer.ts:46) catches storage failures and still accepts the token. Two fresh processes using an unwritable/nonexistent-parent storage path both accept the same token; no consumed-token file is created.

The implementation also uses a separate file read/check/write without an atomic claim, and defaults to container-local `/tmp`. A static shared Set only shares state within one process. It does not provide the required multi-replica guarantee.

**Fix:** Require successful atomic consumption in a durable shared store before acceptance. Fail closed when the store is unavailable. Evidence: `additional-node-probes.json`.

### R03 — P1: Production configuration still permits test keys; audience checks broadened

[identity.py:145](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/shared_mcp/identity.py:145) recognizes `ENVIRONMENT` and `NODE_ENV`, but ignores `VELORA_ENV`, which this application uses for production behavior elsewhere.

With `VELORA_ENV=production` and a configured synthetic test key, the verifier accepts a synthetic HS256 token with a test issuer. This proves the conditional code defect, not that the live deployment has a test key configured.

The audience change also accepts the union of the explicit expected audience, environment values, and the default. A token for the default audience is accepted even when the caller explicitly requires a different audience.

**Fix:** Use one production-mode contract, reject test credentials in that mode, and make an explicitly required audience authoritative. Evidence: `additional-python-probes.json`.

### R04 — P1: Dependency changes are incomplete and clean pipeline installation fails

The pipeline's package manifest requires js-yaml `^4.3.2`, but its lockfile and installed package remain at 4.3.1. A clean-install dry run against an isolated copy fails with an out-of-sync lockfile error. The current TypeScript build passes using the already installed dependencies; it is not proof that clean CI installation works.

Fresh production npm audits still report one high affected pipeline package and seven affected Cards packages (four high, three moderate). A fresh Python environment still flags `mcp==1.26.0`; pytest 8.4.2 is a separate test-only finding. Freshly resolved cryptography no longer triggers an audit finding, but the SuccessFactors lock still records 46.0.3. Productivity's uv lock records MCP 2.2.0 while its Docker requirements pin 1.26.0.

**Fix:** Update manifests and all corresponding locks, perform clean installations, then rerun audits and transport tests. Do not treat changing only a minimum version as a complete dependency upgrade. Evidence: `dependency-alignment.json`, `pipeline-clean-install.log`, `*-audit.json`. The js-yaml maintainer identifies 4.3.2 as the fix for the observed affected version: [advisory](https://github.com/nodeca/js-yaml/security/advisories/GHSA-2883-xcg3-v3hh). See also [MCP's maintained advisories](https://github.com/modelcontextprotocol/python-sdk/security/advisories).

### R05 — P1: Compose now supplies a publicly known production signing secret

[docker-compose.yml:79](/Users/vikrambala/copilotstudio/mcp-apps/docker-compose.yml:79) supplies a literal fallback signing secret when the environment variable is absent. That avoids the original startup failure by defeating the intended production-secret requirement.

**Fix:** Require an explicitly provisioned secret, with no known fallback. The value is deliberately not reproduced in this report.

### R06 — P2: Expired subscription claims cannot be recovered

[subscription_service.py:293](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/subscription_service.py:293) changes an old claim to `EXPIRED_CLAIM` and says it is eligible again. `claim_subscription_run` then attempts a new INSERT using the same primary key. The existing row prevents the new claim.

The reproduction returns `firstClaimed=true`, `alreadyExecutedAfterExpiry=false`, and `retryClaimed=false`. A worker that crashes before sending can therefore strand that scheduled occurrence.

**Fix:** Implement an atomic state transition for expired pre-submission claims. Reconcile potentially submitted messages before retrying so recovery does not introduce duplicate sends. Evidence: `additional-python-probes.json`.

### R07 — P2: New connector security declarations do not match all runtime contracts

Productivity and Facilitator Swagger now declare `x-api-key`, but their protected handlers extract a verified bearer/gateway identity. For example, [Productivity server:177](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/server.py:177) and [Facilitator server:110](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/server.py:110) call `extract_verified_identity`, whose header extraction does not recognize an API key as a user identity.

**Fix:** Export the authentication mechanism the backend actually accepts, then verify authorized success and unauthenticated rejection in the target connector. An API-key declaration alone does not complete this migration. A separately configured live gateway could change the integration behavior; none was verified here.

## Additional consistency observations

- The copied Productivity `worker.py` and `subscription_service.py` inside Facilitator differ from the newly fixed originals. These copies retain the previous logic; prevent future drift by packaging shared code from one maintained source. Successful server import does not establish equivalent behavior of every copied module.
- The new credential-manifest test uses a broad password/secret substring condition. Passing it does not establish a comprehensive secret scan.
- The freshly fetched GitHub tracking branch is still **16 commits behind local HEAD**; local is zero commits behind it. No claim is made about Azure DevOps or cloud deployment state.

## Fresh verification results

| Check | Result |
|---|---:|
| SuccessFactors | 96 passed |
| Productivity | 197 passed |
| S/4HANA | 39 passed |
| Facilitator | 53 passed |
| SAC | 3 passed |
| Credential architecture | 7 passed |
| Cleanup | 4 passed |
| Adaptive Cards | 6 passed |
| Evaluation pipeline | 3 passed |
| **Existing test total** | **408 passed, zero failed/skipped** |
| TypeScript builds | Both passed using installed packages |
| Clean pipeline installation | Failed: manifest/lock mismatch |
| Authored Python syntax | 189 files parsed; zero errors |
| Facilitator clean dependency import | Passed |
| Docker build/image scan | Not performed: daemon unavailable |
| Live provider, PostgreSQL, and deployment parity | Not verified |

Productivity tests still use the sibling workspace import mode because their finance tests import Facilitator. The separate Facilitator test and clean-import checks do not use that workaround.

The earlier .NET and Bicep build checks were not repeated: their sources did not change in the remediation commit. Their previous results are historical build evidence, not new deployed-environment verification.

## Next action

Close R01–R05 before claiming the release is ready, then complete subscription recovery and connector integration verification. Add regression coverage for the new reproductions so a 408-pass result cannot conceal these paths. Publish only after clean installs, container validation, and live acceptance are tied to the reviewed revision.
