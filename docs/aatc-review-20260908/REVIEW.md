# AATC engineering review — 8 September 2026

**Decision: NOT READY for AATC completion or production sign-off.** Security changes are present, but several are incomplete, not connected to runtime execution, or contradicted by reproducible behavior. Real provider operation and federated Dataverse write/readback have not been verified.

## Scope and evidence standard

Reviewed the current dirty working tree, focusing on SuccessFactors, Productivity, Facilitator, S/4HANA, their shared identity/security code, audit logging, approval storage, provider clients, deployment files, and the 58-control security tracker. Also ran the SAC, Adaptive Card, and agent-review pipeline suites. Inspected 121 Python files for syntax; all parsed. The initial source inventory contains 222 file hashes. Existing user changes were retained; no commit, deployment, credential revocation, email, or external business mutation was performed. An external change added `s4_pl_entity = "GLDetails"` to S/4HANA settings during the review; it was preserved and the S/4HANA suite was rerun. Freeze a reviewed revision before release: this working tree is not immutable.

This is an engineering source review and offline regression/reproduction exercise, not a penetration test or a certification that every capability works. Test fixtures and mocked provider responses are explicitly test evidence, never evidence of live data or provider delivery. Source findings are distinguished below from reproduced behavior and configuration observations.

## Changes made during this review

1. **Removed secret fallback from explicit federated Dataverse authentication**, in both Productivity and SuccessFactors. A missing/unreadable assertion now raises an error before a token request, even if an old client secret is present. Added four regression tests: missing assertion cannot use a secret, and refreshed access tokens use a rotated assertion file without sending a client secret.
2. **Removed fabricated integration evidence** from `deploy/test_all_live_systems_and_audit.py`. It now performs limited read-only HTTP health checks, labels business execution and database writes/readback `NOT_RUN`, and returns an incomplete sign-off exit code even when health is good. Two evidence-integrity tests pass. Its existing service URLs still need confirmation against current deployment; this script was not run against those live URLs during review.
3. **Included `shared_mcp` in the Facilitator Dockerfile.** The server imports its identity module, but the previous container recipe omitted that directory. Local source import is covered by the Facilitator suite; an actual container build/deployment remains unverified.
4. **Protected `deploy/solution/env` from accidental Git inclusion.** No secret values were included in this evidence pack.
5. **Removed the unsupported “100% implemented and verified” headline** from the deployment control matrix and added a warning that its earlier row claims require reconciliation. The new control matrix preserves the original tracker IDs and requirements.

The federation change is intentionally fail-closed: the inspected local federation configuration will not log successfully until a real, refreshable assertion source is supplied. This is not a deployment or an assertion that logging is now operational.

## Fresh test results

| Suite | Passed | Failed | Meaning |
|---|---:|---:|---|
| SuccessFactors, final | 96 | 0 | Includes two new federation tests; offline only |
| Productivity, final | 91 | 1 | Includes two new federation tests; existing auth-failure test depends on networking |
| S/4HANA | 37 | 0 | Existing offline suite; does not establish SAP reconciliation |
| Facilitator | 20 | 0 | Existing suite does not exercise all auth/approval bypasses |
| SAC | 0 | 3 | Tests still access removed `SACSettings.demo_mode` |
| Adaptive Card service | 6 | 0 | Does not establish user-bound/durable ticket replay protection |
| Agent-review pipeline | 3 | 0 | Includes its TypeScript build |
| Evidence integrity | 2 | 0 | Health checks cannot claim business/audit verification |
| **Total** | **255** | **4** | **259 executed tests; not live acceptance** |

The Productivity failure is `test_f07_fail_closed_on_live_auth_failure`: the test attempts real networking with invalid credentials and expects “authentication”; the offline guard raises `OFFLINE_REVIEW_NETWORK_BLOCKED`. Fix the test to inject a representative failed token response and assert zero business calls. This failure is not evidence of a successful mock fallback. SAC's three failures occur in setup before testing live functionality.

Used an isolated Python 3.11 environment, installed declared requirements with pytest 8.4.2 and pytest-asyncio, disabled dotenv configuration reads for the final suites, blocked outbound sockets, and redirected test storage to temporary directories. An initial SuccessFactors run lacked pytest-asyncio; it was superseded after correcting the harness. Resolved dependencies are recorded separately. These are freshly resolved dependencies, not proof of deployed image contents or an SBOM vulnerability scan.

## Findings requiring closure

### R01 — P1: Buffered audit retry can authorize an unaudited write (OPEN, reproduced)

[Dataverse audit](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/dataverse_audit.py:855) checks an in-memory alternate-key set and returns `ALREADY_COMMITTED`. The unconfigured branch adds buffered records to that same set. The probe produces `BUFFERED` on first create and `ALREADY_COMMITTED` on retry without a provider call. More seriously, the first `start_write_transaction_fail_closed` returns `may_proceed=false`, while retrying the same invocation returns `may_proceed=true` without durable storage.

Keep buffered and committed state separate. Only provider-confirmed persistence may authorize a write. Prove failure/retry/restart and cross-replica uniqueness with real durable records. Do not use a generic HTTP 412 as proof of a matching committed business event without verification.

### R02 — P1: Facilitator checks presence, not validity, of approval (OPEN, reproduced)

[Email handler](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/tools.py:263) only rejects an empty confirmation token. With `confirmation_token='not-a-valid-approval'`, the offline probe reaches the provider token-request boundary. No email was sent.

Verify trusted user confirmation, signature, identity, tenant, exact recipients/content, expiry, and durable single-use state before provider access. Test arbitrary tokens, edited content, wrong user, and replay; all must produce zero provider calls. The environment switch that disables confirmation also needs removal or an explicitly separate governed capability.

### R03 — P1: Facilitator MCP lacks equivalent authenticated dispatch (OPEN, reproduced at wrapper)

[Registered tool wrapper](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/server.py:63) invokes non-admin handlers without verifying request identity. Admin behavior trusts `__caller_role__`/`MCP_CALLER_ROLE`, not a request-bound verified principal. A harmless wrapped handler was reached without identity. REST checks do not prove MCP tools/call is protected. REST additionally permits an `ALLOW_ANONYMOUS` bypass.

Authenticate and authorize at the actual ASGI/MCP dispatch boundary and bind tool arguments to the verified principal. Exercise MCP initialization, discovery and tool calls, REST aliases, missing/invalid credentials and wrong-role callers. No live endpoint exploit was attempted.

### R04 — P1: Production authentication still accepts test-key exceptions (OPEN, reproduced)

[Shared identity](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/shared_mcp/identity.py:144) reads `TEST_JWT_SECRET` in production. With that variable and `VELORA_ENV=production`, a synthetic HS256 token with an untrusted issuer containing “test” was accepted. This requires deployment of the test secret; the probe does not claim that the live service has it configured.

Remove environment-triggered test validation from production authentication, use injected test verifiers, enforce exact configured claims and asymmetric algorithms, and reject production test flags. Apply consistently to all four copied identity modules. Approval-token signing also retains test-environment secret defaults in `token_manager.py`.

### R05 — P1: Legacy gateway signatures bypass request binding (OPEN, reproduced)

[Gateway verifier](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/shared_mcp/identity.py:346) accepts the legacy signature when verification of the method/path/body-bound signature fails. A valid legacy assertion was accepted with a changed route and body. Nonces remain process-local. User email is not included directly in the signed canonical fields.

Remove legacy acceptance, require request-bound assertions and authenticated identity fields, and claim nonces atomically in a shared store. Verify mutated method/path/body/email, concurrent replay, restart, and multi-replica behavior.

### R06 — P1: PostgreSQL approval store is incomplete and not connected to execution (OPEN, source/interface probe)

[PostgreSQL store](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/operation_store.py:495) implements only `prepare_operation`; it lacks the five lifecycle methods present on the SQLite store. Its argument is `ttl_seconds`, while [token creation](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/token_manager.py:147) passes `expiry_minutes`, catches the resulting exception, and still returns a token. Confirmation/claim/completion methods have no runtime callers outside their definitions. Token verification uses local nonce state instead.

Implement the complete shared transaction interface, fail closed on persistence failure, and connect confirmation and execution to atomic stored state. Prove two concurrent workers cannot execute one approved operation. SQLite WAL cannot provide the claimed multi-host semantics; see [SQLite WAL documentation](https://www.sqlite.org/wal.html).

### R07 — P1: Network and kill-switch helpers are not enforcement (OPEN, source)

The new `shared_mcp/network_security.py` and `kill_switch.py` exist in four services but are referenced only by their definitions and unit tests, not runtime dispatch/provider clients. The network helper also permits approved-host DNS-resolution failure through an “offline DNS fallback.” Passing helper tests cannot demonstrate execution-time disablement or protected outbound traffic.

Wire checks into every relevant REST/MCP/worker/provider boundary, remove DNS failure allowance, and test actual requests while switches are active. Verify transport-level destination enforcement and redirects, not only a preflight DNS lookup. Validate legitimate private SAP destinations explicitly.

### R08 — P1: Live recipient resolution still uses hardcoded business identities (OPEN, reproduced)

[Recipient resolver](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:400) uses the built-in directory and shorthand mappings even with live mode enabled. The offline probe resolved a hardcoded employee without any Graph request. [Availability](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:676) also selects the local calendar whenever live credentials are absent, without requiring explicit mock mode.

Use verified provider directory/availability responses; when unavailable, return an explicit unavailable/unresolved result. Keep fixtures in tests and reject mock flags in deployed configuration. Test production mode with missing credentials and with a provider directory that contradicts the old fixture.

### R09 — P1: Federated logging configuration is not complete (LOCAL FALLBACK FIXED; live evidence OPEN)

`deploy/solution/env` and SuccessFactors `.env` select `FederatedCredential` but contain no assertion/token-file variable. Several client-secret aliases remain populated. Productivity `.env` does not select a Dataverse federation mode. These observations concern local files only; a deployment could inject configuration not present here.

Before the fix, both clients used an existing client secret when the federation assertion was missing; the baseline probe confirms this. After the fix, both raise before contacting the identity provider. Creating an Entra federated credential establishes trust, but the workload must still obtain a current assertion and exchange it for an access token; see [Microsoft workload federation](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation) and [client-credentials assertion flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow).

Supply the approved refreshing assertion source, validate issuer/subject/audience and dedicated Dataverse application permissions, then write and read back an identified audit event. Demonstrate rotation after token expiry before removing active credentials.

### R10 — P1: Health state is set without authenticating to the provider (OPEN, source)

[Connection monitor](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/connection_manager.py:607) marks federated/managed identities healthy if a client ID exists, and secret-based connections healthy if a secret resolves. This is configuration presence, not authentication, source access, or database write permission.

Report configuration/readiness separately and require a bounded real probe before HEALTHY. Verify bad assertions, revoked permissions and unavailable endpoints cannot remain healthy.

### R11 — P1: S/4HANA runtime still uses a shared API key (OPEN, source)

[S/4HANA middleware](/Users/vikrambala/copilotstudio/mcp-apps/ask-s4hana/s4hana_mcp/server.py:95) compares API-key/bearer text to `settings.mcp_api_key`; it does not call the new JWT verifier. Its organizational-scope check reads a caller-supplied header. The existence of the shared identity file does not migrate the runtime to client-ID/secret-backed Entra access tokens or prove user authorization.

Migrate the actual ingress to the approved service/user token contract and enforce trusted organization/resource entitlements. Keep the current key until the replacement path is concretely verified, then remove it and prove old credentials fail.

### R12 — P1: Policy lookup broadens scope or uses a seeded policy (OPEN, source)

[Disclosure policy](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/successfactors_mcp/dataverse_audit.py:1216) ignores the supplied environment in live filtering and broadens a missing agent policy to any active domain policy. When unconfigured it uses an in-memory default policy. This is not verified per-agent/per-environment authorization.

Require exact approved scope and version; no active matching policy must deny the affected retrieval. Test policies for another agent/environment and an unavailable policy store.

### R13 — P2: Some live Graph reads do not match the requested contract (OPEN, source)

[Channel context](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:759) ignores requested team/channel in live mode and performs a broad message search. [Calendar parsing](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/m365_client.py:628) calls `.get` on `onlineMeeting` even when Graph returns null. The Graph client caches an acquired access token without expiry-based refresh.

Use actual channel IDs and scoped endpoints, handle null optional objects, implement bounded pagination/completeness signaling, and refresh expired tokens. Verify null calendar fields, more than one result page, selected-channel isolation and token expiry. Existing suite passes do not cover these cases.

### R14 — P2: Several advertised capabilities remain intentionally unavailable (OPEN, source)

Facilitator history retrieval, calendar workflow, pre-meeting briefing and Loop export return `SOURCE_UNAVAILABLE`. This is truthful behavior, but not implemented integration. S/4HANA budget consumption still passes `mapping_approved=False` in its calculation path. A valid connection will not enable those capabilities by itself.

Provide a precise enabled-tool inventory, implement and test each retained capability against its approved source, or remove the explicitly unwanted tools from code, manifests, connectors and the published agent together. The target removal list has not yet been supplied.

### R15 — P1 if used to authorize actions: Adaptive Card signing has a built-in secret (OPEN, source)

[Card signer](/Users/vikrambala/copilotstudio/mcp-apps/dynamic-adaptive-card-service/src/security/idempotency-signer.ts:15) falls back to a known string; its consumed tokens are held in a process-local set. Tickets are not bound to an authenticated tenant/user and approved submitted payload. Six current tests do not close this issue.

Require configured signing material and durable, user/payload-bound replay controls where cards authorize actions. Test restart, another replica, wrong user, changed submission and missing signing configuration.

### R16 — P1: Existing control closure evidence is unreliable (HEADLINE FIXED; matrix reconciliation OPEN)

The prior matrix claimed complete engineering verification. Twenty-four of its 32 distinct referenced test function names were not found in the source test definitions. Its MCP domains diverge from original tracker IDs (for example, original MCP-14 is egress control, while the implementation matrix labels it atomic leases). The former “live” script generated healthy/audit-success payloads without contacting providers.

Use `control-review-matrix.csv`, which preserves the original 58 requirements. Attach actual test IDs/results and deployment evidence to those IDs. Do not mark source/helper tests as live or independent security closure. The 58-control CSV was taken from the previously extracted original tracker; this review did not alter the Excel workbook.

### R17 — P1: Deployment and runtime hardening evidence is incomplete (OPEN)

Azure returned `AuthorizationFailed` for `Microsoft.App/containerApps/read` in the previously identified resource group. No current image digest, revision, managed identity or runtime environment could be verified. Facilitator's missing shared module is fixed locally; its Docker recipe and the Productivity/S4 recipes also need a current runtime-hardening review (several do not select a non-root user). No container build, release SBOM, vulnerability scan, gateway configuration review, or deployment occurred in this turn.

Obtain read access or an authenticated deployment evidence export; match source hashes to immutable images and verify per-service identity, configuration, ingress/egress, non-root execution, storage, diagnostics, and rollback. Old evidence is not current deployment proof.

## Credential and tool cleanup disposition

**Completed:** removed the implicit client-secret fallback from explicit federated logging; removed fabricated verification data; protected the local credential file from Git.

**Pending exact scope:** deletion/revocation of stored “other tokens” and removal of registered “other tools.” The inspected services still use different authentication mechanisms. Client secrets for provider access, API ingress keys, workload assertions, and approval/card signing keys have different purposes. Deleting them indiscriminately would disable working paths or weaken approval controls. No stored credential was deleted or revoked, and no published tool was removed.

Use `auth-configuration-summary.json` and `configuration-name-inventory.json` for names/presence only. Never attach raw `.env` files, assertions, secrets or unrestricted cloud exports as AATC evidence. The ignored local file remains on disk; ignoring it is not credential rotation or a history purge.

## Evidence needed to close AATC

1. Confirm the target agent/environment and exact retained tool list and credential names to remove.
2. Close R01–R08 and R10–R12/R15 on every active ingress/tool/worker path; prove negative tests block provider calls and permitted requests still succeed.
3. Supply a real federation assertion source and verify token exchange, expiry/rotation, authorized Dataverse create and readback with the same correlation/event ID. Record server-side row ID and timestamp, not a generated success receipt.
4. Execute the retained live capabilities as an authorized user; preserve redacted source references, completeness, authorization denials, and truthful unavailable/error results. Obtain Finance/data-owner reconciliation where relevant.
5. Prove approval confirmation and cross-replica retry/restart behavior against the actual transactional store.
6. Capture deployment source/digest mapping, identities, gateway controls, configuration, current dependency/security scans, monitoring and retention evidence.
7. Attach the exact evidence to all 58 original control IDs and obtain independent security/business owner sign-off. Keep controls open where evidence is absent.

This pack is evidence of the review and local fixes. It is not evidence that AATC is complete.
