# Codebase review after Graphify update — 9 September 2026

**Recommendation: NOT READY for AATC sign-off.** The updated graph improves review coverage; it does not establish implementation correctness. Fresh checks reproduce security and evidence-integrity defects, including a newly observed simulated email fallback and a release evaluation that passes despite a failed stage. The solution archive also contains literal credential values.

This review made no runtime source changes, deployments, credential revocations or business writes. It reviewed the current working tree, not an immutable release. All 349 inventoried authored source/configuration files retain their starting hashes at completion.

## Scope and verification

Graphify 0.9.56 extracted 312 code files into 3,423 nodes and 7,947 edges locally with no LLM processing. Authored inventory covers MCP services, shared security, provider clients, Adaptive Cards, evaluation pipeline, AgentReviewTool, PowerCAT package, CopilotStudioAccelerator, Power Platform definitions and deployment/workflow files. It excludes dependency trees, generated output, media and large downloads. Graph and authored inventories have different inclusion rules; query normalization also differs from raw graph counts. Graph edges guide inspection and are not proof of dynamic reachability.

125 authored Python files and 26 Python files inside Salesforce/ServiceNow sample archives parse successfully. 81 solution JSON/XML definitions parse successfully. Archived samples were inspected but were not established as deployed capabilities. Static parsing is not functional validation or a claim that every execution path was exercised.

Compared with the preceding review manifest, six common source/configuration files changed; 133 files were additionally inventoried, which does not imply they were newly added. The 17 previously tracked security-core module hashes were unchanged. See `changes-since-previous-review.json` and the source manifest for exact scope.

| Fresh suite | Pass | Fail |
|---|---:|---:|
| SuccessFactors | 96 | 0 |
| Productivity | 91 | 1 |
| S/4HANA | 37 | 0 |
| Facilitator | 20 | 0 |
| SAC | 3 | 0 |
| Adaptive Cards | 6 | 0 |
| Evaluation pipeline | 3 | 0 |
| Credential architecture | 2 | 5 |
| Cleanup transformation | 3 | 1 |
| **Total** | **261** | **7** |

The main application suites account for 256 passes and one failure. Productivity's failure is a network-dependent negative test encountering the offline network guard instead of its expected authentication wording; it does not demonstrate provider fallback. Architecture failures include a genuine anonymous-access manifest setting, two stale response expectations, an unsafe expectation that unconfigured audit logging may proceed, and a nonce test expecting consumption without requesting it. Cleanup tests operate on transformed temporary source; their failure is not independently a current provider execution result. Raw test reports preserve the distinctions.

Cards type checking and pipeline compilation pass. All six Bicep files compile. The .NET package builds with zero errors and one SDK compatibility warning. SAC's previous setup failures are resolved, using mocked provider responses. Explicit federated Dataverse mode still rejects a missing assertion in both clients, with no secret fallback.

Python tests ran with outbound sockets blocked, dotenv reads disabled and temporary state directories. Synthetic responses and security probes are local test evidence, not evidence of live provider delivery. Docker was unavailable, so container builds and image scans were not completed. No current live tenant/provider validation or Dataverse write/readback was performed. Prior cloud-access failures are not presented as fresh results.

## Highest-priority recommendations

### N01 — P1: Remove credentials from distributable artifacts and build contexts

`deploy/cre2f_VeloraExecutiveAgentPlatform.zip` contains `solution/env` with eight populated literal credential fields, including client secrets and SAP/SuccessFactors passwords. Values are excluded from this report and pack; their validity was not tested. Its bytes differ from the current local environment file. The current builder explicitly packages four root files, whereas this archive contains ten entries: the existing archive is not reproducible from that builder as inspected.

Regenerate the solution from an explicit allowlist, scan expanded archives, and prohibit environment files and credentials in packaging. If the archive has been shared or published, rotate the affected credentials and examine the distribution history. There is no evidence in this review establishing actual public exposure.

Productivity's Dockerfile uses `COPY . .` without a `.dockerignore`; the supplied image-build script uses the service directory containing a local `.env` as its context. Use selective copies and a clean context, then inspect the resulting image for secrets. Adding a Git ignore rule does not remove credentials from an existing ZIP or Docker build context.

Evidence: `credential-packaging-check.json`, `solution-archive-inventory.json`; source: `deploy/build_velora_executive_platform_solution.py:16`, `mcp-apps/ask-productivity/Dockerfile:8`, `mcp-apps/build_all_images.sh:52`.

### N02 — P1: Remove simulated email success and validate approval before provider access

`mcp-apps/ask-facilitator/facilitator_mcp/tools.py:254` checks only that a confirmation token is nonempty. Its exception paths now return `EMAIL_SENT_SIMULATED` / `GOVERNED_SIMULATION_FALLBACK`, inventing a message ID and link after provider failure. The fresh offline probe reproduces this using an invalid approval string and a synthetic provider failure. New connector operations expose this handler.

Fail closed with a truthful unavailable/denied result. Require signed, user/tenant/payload-bound, unexpired, durably single-use approval before any provider request. Never fabricate delivery evidence, including on the apparent successful path. Graph sendMail returns an empty 202 response, which means acceptance rather than completed delivery: [Microsoft sendMail contract](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0). Record acceptance separately and obtain a real provider-backed reference when claiming delivery.

Evidence: `security-probe-results.json`, `security_probes.py`. This directly prevents a “no mock or fallback data” attestation.

### N03 — P1: Make durable audit commit a prerequisite for every governed write

The audit probe still returns `BUFFERED` first and `ALREADY_COMMITTED` on retry without a provider commit. The same retry changes `may_proceed` from false to true. Separate buffered state from confirmed persistence; verify existing committed records before allowing an operation. Prove provider outage, duplicate request, restart and concurrent-replica behavior against the actual store.

Source: `mcp-apps/ask-successfactors/successfactors_mcp/dataverse_audit.py:855`. Evidence: `security-probe-results.json`.

### N04 — P1: Enforce identity, request binding and durable approval at actual runtime boundaries

The Facilitator MCP wrapper still reaches a non-admin handler without identity. Production identity accepts a configured test-secret token with an untrusted issuer; the reproduction requires that test flag/secret and is not proof it exists in deployment. Legacy gateway assertions still accept an altered route/body. PostgreSQL implements only preparation, lacks the remaining approval lifecycle, and has an argument mismatch with token creation that is caught while still issuing a token. Runtime confirmation/claim calls are absent.

Remove production test exceptions and legacy assertion acceptance. Enforce verified identities and roles across REST, MCP and workers; bind assertions to all request and identity fields. Implement and use an atomic shared approval lifecycle, failing closed on persistence errors. Card signing also needs mandatory configured keys and durable user/payload-bound replay protection when used to authorize actions.

Kill-switch and outbound-destination helpers remain referenced by tests rather than relevant runtime callers. Wire them into dispatch/provider boundaries and demonstrate denial with zero provider calls, including redirect and DNS failure cases.

Evidence: `security-probe-results.json`, `graphify-call-coverage.json`; source references and original finding detail remain in the preceding review linked below.

### N05 — P1: An incomplete evaluation must not pass the release gate

The new pipeline probe makes Stage B throw while Stage C returns 100. The result includes a Stage B error but reports overall score 100 and `passed: true`. Scoring only the available stage permits incomplete evidence to pass; the caller checks `scores.passed` without accounting for errors.

Require all mandatory stages to complete successfully before setting release pass. A partial advisory score may be shown with explicit INCOMPLETE status. Add outage, timeout, malformed response and skipped-stage cases to the gate tests.

Source: `agent-review-pipeline/src/evaluation/scoreCalculator.ts:73`, evaluation orchestrator and evaluator; evidence: `pipeline-gate-probe.json` and log.

### N06 — P1: Resolve configuration drift before removing remaining tokens

SuccessFactors `manifest.yml:13` explicitly enables anonymous access despite secure settings defaults. Four generated connector specifications lack declared authentication; this conflicts with secured runtime contracts unless authentication is configured separately. S/4HANA and SAC retain API-key ingress. Export the actual configured connector and verify both authorized success and unauthenticated rejection before asserting the migration is complete.

The current `deploy/solution/env` selects federated Dataverse authentication but contains no assertion source variables. Current SuccessFactors and Productivity local files do not select the Dataverse federation mode. These are local observations; deployment may inject other values. Creating federation trust alone is not evidence of a refreshable assertion or functioning database access. Bicep and shell settings also need alignment with the intended identity design.

Use one approved deployment contract. The worker exists, but shell deployment sets `REQUIRE_LIVE_DELIVERY=false`, masks failures with `|| true`, and needs verified storage mounts. Require live delivery, meaningful exit status and persistent storage. Remove obsolete credential paths only after proving their replacements and showing old credentials are rejected; approval-signing keys and workload assertions serve different purposes from provider client secrets.

Evidence: `local-auth-configuration.json`, `connector-auth-contracts.json`, architecture test reports.

### N07 — P1: Patch dependencies against fresh audits, then scan the release image

Production npm lockfile audits report one high affected package in the pipeline (`js-yaml`) and seven affected packages in Cards: four high (`@xmldom/xmldom`, `fast-uri`, `fastify`, `find-my-way`) and three moderate. These are affected-package counts, not counts of proven exploitable application vulnerabilities.

Installed Python audits flag `mcp==1.26.0` and `cryptography==46.0.3`. Existing cryptography constraints can exclude patched releases. Upgrade to compatible patched versions, update constraints/locks, rerun transport and crypto tests and rescan. MCP advisory applicability depends on enabled transports/features. Productivity's installed-package audit found zero packages and is inconclusive. The isolated review runtime's pytest finding is a test dependency, not a demonstrated production image dependency.

Primary advisory examples: [js-yaml](https://github.com/advisories/GHSA-2883-xcg3-v3hh), [xmldom](https://github.com/advisories/GHSA-8344-3jmq-59r6). Raw npm and Python audit JSON/logs in this pack preserve the current findings and fix versions. No image SBOM or deployed-image audit was completed.

### N08 — P1: Keep audit evidence private and map it to the reviewed release

`.github/workflows/deploy-pages.yml:30` uploads all of `docs`. Existing reviews and cloud backups under that directory could be published if committed and included in a Pages run. Public accessibility was not established. This fresh pack is therefore under `review-evidence`, outside that publication path.

Publish only an allowlisted public-site directory. Store redacted AATC evidence in an access-controlled location. Bind tests, scans and provider evidence to a frozen source revision and image digest; keep incomplete controls open. Require complete regression and security gates on runtime changes, including external pipeline templates whose effective execution was not established here.

## Previous findings: current disposition

The preceding [detailed review](../../docs/aatc-review-20260908/REVIEW.md) contains source references and the original R01–R17 definitions. The following is the current disposition, not a claim that source fixes have landed.

| ID | Current status |
|---|---|
| R01 | OPEN: buffered audit retry authorizes without commit; reproduced again. |
| R02 | OPEN: presence-only approval; new simulated-email regression compounds it. |
| R03 | OPEN: unauthenticated Facilitator wrapper reached in probe. |
| R04 | OPEN: production test-secret exception reproduced with required flag. |
| R05 | OPEN: legacy signature accepts altered request; replay state remains local. |
| R06 | OPEN: incomplete PostgreSQL lifecycle and missing execution integration. |
| R07 | OPEN: helper-only kill-switch/network controls; graph and source corroborate. |
| R08 | OPEN: hardcoded recipient resolution in live mode reproduced; availability fallback remains. |
| R09 | Local implicit secret fallback remains FIXED; live federation wiring and readback OPEN. Local mode settings differ from yesterday. |
| R10 | OPEN: connection health based on configuration presence, not successful provider authentication. |
| R11 | OPEN: shared-key ingress and caller-supplied organizational scope; include SAC migration contract. |
| R12 | OPEN: policy scope broadening and unconfigured seeded policy. |
| R13 | OPEN: channel-scope mismatch, nullable calendar field and token-refresh handling. |
| R14 | OPEN: advertised unavailable capabilities and unapproved budget mapping. A GLDetails setting does not implement a validated P&L workflow. |
| R15 | OPEN: fallback Card signing secret and non-durable, insufficiently bound replay state. |
| R16 | Earlier misleading headline/health script corrected; control reconciliation OPEN; new partial-evaluation false pass reproduced. |
| R17 | Facilitator shared-module Docker copy remains FIXED; worker exists; builds improve evidence, deployment/image/runtime controls remain unverified. |

## AATC completion sequence and acceptance evidence

1. Produce a reproducible credential-free release package and clean image context; handle rotation according to actual distribution history.
2. Close audit, approval, identity, simulated-data and release-gate defects. Negative tests must prove zero provider mutations; concurrent/restart tests must exercise durable stores.
3. Freeze the retained tool inventory and authentication contract. Remove unwanted tools consistently across implementation, registration, connector and agent publication. Current review did not remove tools or credentials.
4. Supply a refreshable federated assertion in the actual workload. Capture redacted token-exchange outcome, Dataverse row ID and matching readback/correlation ID, then prove expiry/refresh and denied permissions. Never attach raw tokens or secrets.
5. Run authorized live acceptance for every retained capability, including truthful outages, real source references, scope isolation, approval replay and provider-backed results. Obtain business reconciliation for financial calculations.
6. Record source revision, image digest, container scans, deployment configuration, identities, storage, gateway/egress controls and operational monitoring. Attach these and actual test IDs to the original 58 control IDs for owner sign-off.

The evidence pack establishes review findings and offline checks. It does not establish that all functionality works, that all runtime mock/fallback paths are removed, or that AATC is complete.
