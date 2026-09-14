# Velora Platform - Exec AI Agent Security Control Traceability Matrix (WP11 / WP12)

Document Version: 2.1.0  
Baseline Review Date: 8 September 2026  
Status: NOT READY — 8 September independent source review found open engineering defects.  

---

## 1. Overview & Verification Summary

This matrix provides comprehensive engineering traceability for all **58 security controls** (28 AIDEV controls and 30 MCP controls) established in the 8 September 2026 Exec AI Agent Security Tracker.

### Remediation Status Summary
- **Local Application Source Remediations**: **PARTIAL; verification claims below are not closure evidence**.
  - See `docs/aatc-review-20260908/REVIEW.md` for fresh test results, reproduced defects, source hashes, and live verification limitations. Unit-test passes do not establish deployed operation or durable database logging.
  - The rows below retain earlier implementation claims for reconciliation. Some MCP control IDs/domains differ from the original security tracker; use the original requirements preserved in `docs/security-tracker-review-20260908/CONTROL_FIX_MATRIX.csv` and the new review matrix as the baseline.
- **External Platform Boundaries**: Explicitly documented as **OPEN / EXTERNAL DEPENDENCY** for live tenant owners (Cloudflare, Quilr, Microsoft Entra, SAP S/4HANA production admins).

---

## 2. AIDEV Security Controls Traceability (28 Controls)

| Control ID | Domain | Work Package | Implementation File(s) | Verification Test Suite / Test ID | Status | External / Platform Dependency |
|---|---|---|---|---|---|---|
| **AIDEV-01** | Architecture & Data-Flows | WP01 | `docs/deploy/ARCHITECTURE_AND_THREAT_MODEL.md` | Doc Review & Topology Audit | Implemented | Cloudflare / Quilr per-flow peering verification |
| **AIDEV-02** | Threat Modelling | WP01 | `docs/deploy/ARCHITECTURE_AND_THREAT_MODEL.md` | `test_identity_boundary.py`, `test_financial_error_propagation.py` | Implemented | Ongoing threat register updates |
| **AIDEV-03** | Environment Segregation | WP10 | `deploy/velora.env.template`, `shared_mcp/identity.py` | `test_identity_boundary.py::test_rejects_offline_tokens_in_prod` | Implemented | Azure Key Vault prod secret isolation |
| **AIDEV-04** | Secure SDLC | WP11 | `.github/workflows/`, `pyproject.toml` | CI pipeline regression suites (238 tests passing) | Implemented | GitHub repository branch protection rules |
| **AIDEV-05** | Identity & Service Principals | WP02, WP10 | `shared_mcp/identity.py`, `productivity_mcp/server.py` | `test_identity_boundary.py::test_handoff_rejects_missing_authorization` | Implemented | Microsoft Entra managed identity assignments |
| **AIDEV-06** | Tool Authorization Matrix | WP03 | `facilitator_mcp/tools.py`, `token_manager.py` | `test_facilitator_governance.py::test_non_admin_cannot_configure_policy` | Implemented | Copilot Studio action tool registration |
| **AIDEV-07** | User Context Preservation | WP02 | `productivity_mcp/server.py`, `shared_mcp/identity.py` | `test_identity_boundary.py::test_handoff_rejects_body_identity_conflict` | Implemented | Entra ID token claim emission (`oid`, `upn`) |
| **AIDEV-08** | Secrets Management | WP10 | `deploy/velora.env.template` | Secret audit, `test_identity_boundary.py` | Implemented | Azure Key Vault secret rotation policy |
| **AIDEV-09** | Network & Egress Routing | WP05 | `shared_mcp/network_security.py` | `test_network_and_killswitch.py::test_ssrf_blocks_cloud_metadata` | Implemented | Cloudflare / Quilr egress proxy routes |
| **AIDEV-10** | Encryption in Transit & Rest | WP05, WP08 | `docs/deploy/DATA_INVENTORY_AND_RETENTION.md`, `shared_mcp/network_security.py` | `test_network_and_killswitch.py::test_ssrf_rejects_plain_http` | Implemented | Azure Files / PostgreSQL volume encryption |
| **AIDEV-11** | Input Validation & Schemas | WP06 | `s4hana_mcp/contracts.py`, `tools_m365_writes.py` | `test_four_failed_cases.py`, `test_m365_writes.py` | Implemented | Copilot Studio JSON schema enforcement |
| **AIDEV-12** | Prompt Injection Defense | WP07 | `facilitator_mcp/tools.py` (`html.escape`) | `test_facilitator_governance.py::test_html_escaping_prevents_injection` | Implemented | Azure AI Foundry prompt guardrails |
| **AIDEV-13** | Tool Inventory & Allowlisting | WP03, WP11 | `productivity-plugin.json`, `s4hana-plugin.json` | Discovery endpoint schema audits | Implemented | Copilot Studio published tool manifest |
| **AIDEV-14** | Agency Containment | WP03, WP04 | `productivity_mcp/token_manager.py`, `operation_store.py` | `test_two_step_pattern.py`, `test_operation_state_machine.py` | Implemented | Executive Adaptive Card action review |
| **AIDEV-15** | Output Controls & Minimization | WP07 | `s4hana_mcp/server.py`, `report_calculations.py` | `test_financial_error_propagation.py` | Implemented | SOC DLP monitoring |
| **AIDEV-16** | Response Grounding & Factualness| WP07 | `s4hana_mcp/report_calculations.py` | `test_financial_error_propagation.py::test_financial_currency_mismatch` | Implemented | Live SAP S/4HANA OData reconciliation |
| **AIDEV-17** | Retrieval Security & Provenance | WP07, WP08 | `facilitator_mcp/tools.py`, `knowledge_graph.jsonl` | `test_app.py::test_ingest_chat_to_knowledge_graph` | Implemented | Dataverse Knowledge Base ACLs |
| **AIDEV-18** | Data Minimization | WP08 | `docs/deploy/DATA_INVENTORY_AND_RETENTION.md`, `contracts.py` | Synthetic payload inspection in unit tests | Implemented | Gateway attribute filtering |
| **AIDEV-19** | Data Isolation & Multi-Tenancy | WP02, WP08 | `successfactors_mcp/memory_service.py` | `test_dataverse_audit_and_memory.py::test_30_day_memory_partition_and_user_isolation` | Implemented | Microsoft Entra tenant separation |
| **AIDEV-20** | Logging & Audit Traceability | WP09 | `successfactors_mcp/background_logger.py` | `test_audit_durability.py::test_buffered_sink_never_produces_committed_spool_marker` | Implemented | Dataverse compliance table access |
| **AIDEV-21** | Security Monitoring & Alerts | WP09 | `successfactors_mcp/background_logger.py`, `logger.py` | `test_audit_durability.py` | Implemented | CyberNxt SOC SIEM ingestion pipeline |
| **AIDEV-22** | Emergency Kill Switch | WP12 | `shared_mcp/kill_switch.py` | `test_network_and_killswitch.py::test_kill_switch_global_and_tool` | Implemented | Azure App Configuration feature flags |
| **AIDEV-23** | Configuration Integrity | WP11 | `deploy/containerapp.bicep`, `manifest.yml` | Container deployment validation | Implemented | Azure GitOps deployment pipeline |
| **AIDEV-24** | Dependency & Supply Chain | WP11 | `uv.lock`, `pyproject.toml` | SBOM generation & lockfile verification | Implemented | GitHub Dependabot / Azure Container Registry scanning |
| **AIDEV-25** | Independent Security Testing | WP12 | Full 238-test regression suite | All local suites passing; vendor handoff package prepared | In Progress | Third-party penetration testing vendor onboarding |
| **AIDEV-26** | Secure Error Handling | WP06 | `s4hana_mcp/tools.py`, `server.py` | `test_financial_error_propagation.py::test_safe_error_masking` | Implemented | Gateway error transformation |
| **AIDEV-27** | Resilience & Rate Limiting | WP04, WP06 | `productivity_mcp/operation_store.py`, `cache.py` | `test_cache_and_concurrency.py`, `test_operation_state_machine.py` | Implemented | Azure API Management rate limit tiers |
| **AIDEV-28** | Privacy & Retention Lifecycle | WP08 | `docs/deploy/DATA_INVENTORY_AND_RETENTION.md`, `memory_service.py` | `test_dataverse_audit_and_memory.py::test_memory_30_day_rolling_cutoff` | Implemented | Dataverse automated bulk-delete jobs |

---

## 3. MeshX & SAP MCP Security Controls Traceability (30 Controls)

| Control ID | Domain | Work Package | Implementation File(s) | Verification Test Suite / Test ID | Status | External / Platform Dependency |
|---|---|---|---|---|---|---|
| **MCP-01** | MeshX/SAP Architecture | WP01 | `docs/deploy/ARCHITECTURE_AND_THREAT_MODEL.md` | Architecture review | Implemented | MeshX & SAP network routing approval |
| **MCP-02** | Attack Surface Minimization | WP03, WP11 | `s4hana_mcp/server.py`, `contracts.py` | Direct tool listing inspection | Implemented | SAP OData service catalog activation |
| **MCP-03** | Strong Authentication | WP02 | `shared_mcp/identity.py`, `s4hana_mcp/server.py` | `test_reviewer_findings.py::test_unauthenticated_request_rejected` | Implemented | Entra ID application registration |
| **MCP-04** | Strict Token Validation | WP02 | `shared_mcp/identity.py` | `test_identity_boundary.py::test_rejects_expired_token`, `test_rejects_wrong_issuer` | Implemented | Entra ID JWKS endpoint |
| **MCP-05** | Object & Tenant Authorization | WP02, WP03 | `s4hana_mcp/tools.py`, `successfactors_tools.py` | `test_policy_and_drilldown.py`, `test_leavers_attrition_trend.py` | Implemented | SAP ERP authorization profiles (PFCG) |
| **MCP-06** | Confused Deputy Prevention | WP02 | `shared_mcp/identity.py`, `server.py` | `test_identity_boundary.py::test_handoff_rejects_body_identity_conflict` | Implemented | Downstream OData user principal mapping |
| **MCP-07** | Read-Only Enforcement | WP03 | `s4hana_mcp/tools.py` | `test_reviewer_findings.py::test_s4_pnl_strictly_unsupported` | Implemented | SAP communication user read-only roles |
| **MCP-08** | Schema Validation & Limits | WP06 | `s4hana_mcp/contracts.py` | `test_app.py::test_schema_validation` | Implemented | FastMCP JSON-RPC schema compliance |
| **MCP-09** | Injection Resistance | WP07 | `facilitator_mcp/tools.py` | `test_facilitator_governance.py::test_html_escaping_prevents_injection` | Implemented | Upstream ERP metadata sanitization |
| **MCP-10** | Tool Definition Integrity | WP11 | `s4hana-plugin.json`, `manifest.yml` | Plugin manifest checksum validation | Implemented | Copilot Studio connector synchronization |
| **MCP-11** | Rug-Pull & Drift Prevention | WP11 | `contracts.py`, `tools.py` | Hash-checked tool signatures | Implemented | Deployment CI/CD drift detection |
| **MCP-12** | Egress & SSRF Protection | WP05 | `shared_mcp/network_security.py`, `client.py` | `test_network_and_killswitch.py::test_ssrf_blocks_private_rfc1918_unless_allowlisted` | Implemented | Azure VNet NSG outbound rules |
| **MCP-13** | Replay & Nonce Defense | WP02, WP04 | `shared_mcp/identity.py`, `operation_store.py` | `test_identity_boundary.py::test_gateway_assertion_replay_prevented` | Implemented | Multi-replica Redis/PostgreSQL nonce store |
| **MCP-14** | Atomic Leases & State Machine | WP04 | `productivity_mcp/operation_store.py` | `test_operation_state_machine.py::test_expired_lease_transitions_to_outcome_unknown` | Implemented | PostgreSQL 14+ row-level locking |
| **MCP-15** | Idempotency & Deduplication | WP04 | `recommendation_engine.py`, `operation_store.py` | `test_notification_claims.py::test_outbox_claim_deduplication` | Implemented | Unique constraint on `deduplication_key` |
| **MCP-16** | Failure Modes & Safe Errors | WP06 | `s4hana_mcp/tools.py` | `test_financial_error_propagation.py::test_internal_exception_stack_masked` | Implemented | API Gateway custom error responses |
| **MCP-17** | Data Minimization & Truncation | WP08 | `s4hana_mcp/report_calculations.py` | `test_app.py::test_drilldown_truncation` | Implemented | SAP OData `$select` filtering |
| **MCP-18** | Transport Encryption (TLS 1.3) | WP05 | `shared_mcp/network_security.py` | `test_network_and_killswitch.py::test_ssrf_rejects_plain_http` | Implemented | Azure Container App TLS certificate binding |
| **MCP-19** | Secrets in Vault | WP10 | `deploy/velora.env.template` | Secret audit, `settings.py` | Implemented | Azure Key Vault managed identity secret references |
| **MCP-20** | Environment Partitioning | WP10 | `shared_mcp/identity.py`, `velora.env.template` | `test_identity_boundary.py::test_rejects_offline_tokens_in_prod` | Implemented | Subnet & VNet routing isolation |
| **MCP-21** | Audit Durability & Spooling | WP09 | `successfactors_mcp/background_logger.py` | `test_audit_durability.py::test_uncommitted_events_recovered_on_restart` | Implemented | Microsoft Dataverse API availability |
| **MCP-22** | Structured Telemetry & Trace | WP09 | `successfactors_mcp/dataverse_audit.py` | `test_audit_durability.py::test_required_audit_fields_survive_round_trip` | Implemented | Azure Application Insights workspace |
| **MCP-23** | Multi-Tier Emergency Kill Switch | WP12 | `shared_mcp/kill_switch.py` | `test_network_and_killswitch.py::test_kill_switch_client_and_tenant` | Implemented | Azure App Configuration dynamic refresh |
| **MCP-24** | Rate Limiting & Concurrency | WP06 | `successfactors_mcp/cache.py` | `test_cache_and_concurrency.py` | Implemented | Azure Container Apps concurrency limits |
| **MCP-25** | Timeout & Circuit Breaker | WP06 | `s4hana_mcp/client.py`, `successfactors_client.py` | `test_app.py::test_client_timeout` | Implemented | Upstream SAP gateway latency SLO |
| **MCP-26** | Truthful Unconfigured Responses | WP07 | `facilitator_mcp/tools.py` | `test_app.py::test_query_user_history_from_dataverse` | Implemented | Live connector activation |
| **MCP-27** | Financial Mismatch Integrity | WP07 | `s4hana_mcp/report_calculations.py` | `test_financial_error_propagation.py::test_financial_missing_fields_contract_mismatch` | Implemented | SAP Finance G/L account reconciliation |
| **MCP-28** | Recipient Policy Enforcement | WP03 | `facilitator_mcp/tools.py` | `test_facilitator_governance.py::test_recipient_policy_blocks_unauthorized_domain` | Implemented | Exchange Online mail flow rules |
| **MCP-29** | Governed Write Confirmation | WP03 | `facilitator_mcp/tools.py`, `token_manager.py` | `test_facilitator_governance.py::test_email_send_requires_confirmation_token` | Implemented | Copilot Studio user confirmation dialogs |
| **MCP-30** | Independent MCP Retest Gate | WP12 | Full suite passing (238/238) | Vendor test pack ready | In Progress | External security assessment execution |
