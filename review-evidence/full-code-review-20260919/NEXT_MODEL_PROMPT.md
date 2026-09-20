# Implementation request for the next model

Review baseline: `635947d0b63dcf9f3e4a26c190e39614760adf6b` in the copilotstudio repository.

Implement the repairs described in `review-evidence/full-code-review-20260919/REVIEW_AND_FIX_PLAN.md` and `findings.json`. Read those files and the cited current source before editing. If HEAD differs from the baseline, revalidate each finding against the current code and identify already-fixed items rather than applying stale changes.

The review produced 22 repair tasks (16 P1, 6 P2) despite all 414 existing tests passing. Your goal is to correct the demonstrated behavior and meet each task’s acceptance tests, not merely preserve the old passing count. Use the saved synthetic probes as reproductions; convert them into proper regression tests that expect the secure/correct behavior.

## Required approach

1. Inspect applicable repository instructions and working-tree changes. Preserve unrelated user work. Establish a clean, reproducible service-specific dependency baseline; resolve F16’s lockfiles before assuming a combined test environment proves deployment packaging.
2. Create a finding-by-finding checklist. Implement small coherent changes in the order in the report, keeping security context, token format and storage contracts consistent across services.
3. Prioritize F01–F07 and F17/F21/F22. In particular, do not make native Facilitator tools callable by fixing their schema while leaving authentication absent. Derive tenant, actor, roles, mailbox and scopes from verified identity. Remove public filesystem/signing-key control and permissive audit/workload defaults.
4. Complete F08’s shared-state design before closing replay/scheduling findings. The source already supports PostgreSQL for some stores, but subscriptions/business records/card tickets are separate stores. Migrate each required store explicitly; preserve data and prove cross-process behavior. Do not solve multi-replica persistence by pointing SQLite WAL at a network share.
5. Fix F09/F10 with per-owner clients and a durable send/reconciliation state machine. A provider timeout or expired claim is not proof that no message was sent. Use lease ownership checks; do not implement blind retries after uncertain submission.
6. Fix F11/F18/F19 without inventing source documents, confidence, recipients, dates or business values. Keep raw user input distinct from verified provider evidence and preserve numeric zero.
7. Finish the SAC transport, plugin authentication, CI failure behavior and scheduling capability contracts. Disable unsupported automation at creation time until implemented.
8. Keep current working protections: explicit mandatory-stage failure, cryptographic JWT validation, production test-key prohibition, exact token structure, closed storage failures, governed two-step writes and metadata authentication. Do not bypass controls to make tests or integrations pass.

## Tests and verification

- Run the existing suites and add the per-finding acceptance tests from findings.json.
- Use synthetic isolated test data. Block real business/provider writes during local tests, remove provider credentials from test subprocesses and disable dotenv reads.
- Test REST and native MCP over their transport boundary, not just direct function calls. Include initialize/list/call, valid credentials, missing credentials, wrong user/tenant/role/scope and session ownership.
- Use two independent processes for replay/claim tests and a real disposable PostgreSQL instance for store contracts. Exercise crashes before submission, after provider acceptance and before local completion; inject storage failures.
- Clean-install each service from its own declared dependencies and test the actual container build context. Regenerate locks and generated agent/connector artifacts consistently.
- Rerun dependency audits. npm audit was unavailable during the review; do not mark it clean from the old error JSON. Record production and test-only findings separately.
- Distinguish local tests from staging acceptance. Do not claim deployed parity, live provider success or retained-audit-storage guarantees without evidence from those environments.

## Scope and deliverables

Perform code fixes, migrations, configuration changes and local/disposable test work. Produce a deployment/rotation plan for external environment changes, including invalidation of any historically used default keys; do not silently deploy, send business messages or rewrite historical audit records as part of this code repair request.

Deliver:

1. The implementation and necessary regression tests.
2. Updated service/package/plugin configuration and reproducible dependency locks.
3. Any required data migration, rollback/cutover instructions and operator steps for keys/environment provisioning.
4. A closure table for **every F01–F22**: status, files changed, tests/evidence, and any remaining environment-dependent check.
5. A concise summary of residual risks and exactly what was not verified.

If a finding no longer applies, document the current source/test evidence. Do not silently drop it. If a fix depends on a business policy decision (for example permitted data scopes or retention), implement the configurable enforcement contract and clearly identify the policy values that the owner must supply.
