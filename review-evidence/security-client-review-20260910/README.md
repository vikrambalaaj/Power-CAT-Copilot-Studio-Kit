# Fresh security and client identity review — 10 September 2026

Scope: current local working tree at HEAD f1f9a1bb51fcef4c538db4a8c705937ab5c702f3, including existing uncommitted changes. This is a targeted implementation review, not a live tenant or full platform assessment. No application changes or deployments were made. “Security” is interpreted as the custom connector Security configuration and its backend identity enforcement.

## Why the client ID and details are missing

All four local connector Swagger files (Productivity, Facilitator, S/4HANA and SAC) omit both `securityDefinitions` and `security`. The generator at `deploy/generate_connectors_swagger.py` also omits authentication and writes three of those files directly. Regeneration therefore cannot supply OAuth configuration. None of these files supplies connector OAuth client registration details.

Importing those artifacts alone cannot complete the connector Security configuration. Microsoft documents configuring OAuth and the Entra application information on the connector Security page after import: https://learn.microsoft.com/en-us/connectors/custom-connectors/azure-active-directory-authentication . A live connector could have separately configured settings; its current state was not inspected, so this is the confirmed local artifact gap and a likely explanation of the reported screen, not proof of live settings.

The solution builder (`deploy/build_velora_executive_platform_solution.py:13`) packages only solution.xml, customizations.xml, [Content_Types].xml and audit_cloud_flows.json. Inspection of its existing ZIP confirmed exactly those four entries. It does not package the standalone connector definitions or separate connector OAuth properties. Importing that package does not establish that these connector security settings were provisioned.

## Findings and closure requirements

| Priority | Verified gap | Evidence | Required closure |
|---|---|---|---|
| P1 | Connector authentication configuration is absent from all four local definitions and the three-connector generator. | `deploy/generate_connectors_swagger.py`; `mcp-apps/*/*connector-swagger.json` | Add supported OAuth definitions and environment-specific connector configuration. Verify the imported Security settings and authenticated connection in the target environment. Keep secrets out of Swagger and source. |
| P1 | Audience configuration names disagree. The template declares ENTRA_INBOUND_AUDIENCE; the shared verifier reads API_AUDIENCE or ENTRA_CLIENT_ID and otherwise falls back to a hardcoded audience. | `deploy/velora.env.template:13`; `mcp-apps/ask-productivity/shared_mcp/identity.py:36,229` | Use one required audience setting consistently; reject missing production configuration and test deployment-to-verifier wiring. |
| P1 | The deployment script reads tenant/audience variables but does not pass those names into its container environment arguments. | `mcp-apps/deploy-azure-containerapps.sh:33,34` and its `--env-vars` blocks | Explicitly provision tenant and API audience for every protected service; confirm deployed values without printing secrets. |
| P1 | Client application ID is optional and no allowed-client policy is enforced by the shared verifier. A token without appid/azp becomes an identity with an empty client ID. | `mcp-apps/ask-productivity/shared_mcp/identity.py:279`; `probe-results.json` | Require the appropriate verified client claim and enforce the approved caller policy. Test missing and unapproved callers with valid asymmetric test signatures and on actual routes. |
| P1 | Per-client kill-switch helper exists but has no production call sites in the four inspected service trees. | `shared_mcp/kill_switch.py:80` in Productivity, Facilitator, S/4HANA and SuccessFactors; source search found only definitions and test calls. | Invoke it before business execution using the verified client and tenant; prove a disabled client causes zero downstream calls. |
| P1 | Environment-controlled test verification remains in production identity code. TEST_JWT_SECRET permits HS256 and relaxed issuer handling. | `mcp-apps/ask-productivity/shared_mcp/identity.py:144,214` and the other shared copies | Remove environment-triggered test trust; inject test verifiers only in tests. This is a conditional deployment hazard, not evidence that production has this variable set. |
| P2 | Handoff requires a user principal but supplies no required_scope/required_role to the boundary helper. | `mcp-apps/ask-productivity/productivity_mcp/server.py:156` | Define operation permissions and verify their enforcement through dispatch and downstream calls. Identity validation alone does not close authorization requirements. |

## What is actually implemented

- VerifiedIdentity includes tenant, object ID, principal type, client application ID, scopes, roles and optional display identity. The client field exists; it is not mandatory.
- The verifier implements signature verification, JWKS support, expiry, tenant/audience checks and exact issuer checks outside its test-key mode. It exposes optional role/scope checks.
- Productivity `/handoff` now invokes identity verification, requires a user principal, and rejects conflicting body identity. The older review describing this route as unauthenticated is no longer current.
- A client ID used by the Dataverse audit authentication client is an outbound workload credential, not automatically the inbound connector caller ID. Do not copy an unrelated Graph/Dataverse application ID into connector security without confirming its registration and API permissions.

## Fresh validation

Executed `PYTHONPATH=mcp-apps/ask-productivity python3 -m unittest discover -s mcp-apps/ask-productivity/test -p test_identity_boundary.py`: **15 tests passed**. Includes real local HTTP route checks for missing credentials, forged principal headers and body identity conflict.

Two additional local synthetic-token probes called the existing verifier with an explicit test key and explicit expected tenant/audience. Both a missing client claim and an arbitrary client claim were accepted; results are saved in `probe-results.json`. These probes demonstrate claim-policy behavior, not production signature bypass or a live exploit. Existing tests passing does not cover the connector provisioning and client-policy gaps.

## Configuration evidence still needed

For each target connector record: environment and connector ID/name, approved Entra client registration, tenant, API resource/audience, delegated scopes, credential mechanism, registered connector redirect URI, consent status, connection reference and owner. Verify those values against the deployed connector and API, then run a successful authorized call plus wrong-client, wrong-audience and disabled-client negatives. Real client IDs were not invented and credentials were not copied into this review.
