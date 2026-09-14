# Velora Platform - Data Inventory, Classification, and Retention Runbook (WP08)

Document Version: 2.1.0  
Baseline Security Review: 8 September 2026  
Status: Reviewable Engineering Artifact  

---

## 1. Executive Summary & Policy Scope

This document defines the enterprise data lifecycle, classification boundaries, cryptographic partitioning, and retention runbooks for all data processed and persisted by the Velora Executive AI Platform. In accordance with enterprise governance policies and regional regulatory requirements (e.g., UAE Federal Decree-Law No. 45/2021 on Personal Data Protection), all data is subject to strict isolation, least-privilege access, and automated lifecycle purges.

---

## 2. Comprehensive Data Inventory Matrix

| Data Asset | Classification | Storage Location | Partition / Tenant Isolation Key | Encryption (At Rest / Transit) | Retention Period | Purge Trigger / Mechanism | Purpose & Regulatory Basis |
|---|---|---|---|---|---|---|---|
| **Executive Prompts & User Queries** | Confidential / Restricted | In-Memory ephemeral; Dataverse Audit spooled | `cre2f_userobjectid` + `tenant_id` | TLS 1.3 / AES-256 (Dataverse) | 30 Days (Interactive Memory) | Automatic cron-based 30-day purge in `MemoryService` | Conversational continuity; executive context |
| **Assistant Responses & Summaries** | Confidential | In-Memory ephemeral; Dataverse Audit spooled | `cre2f_userobjectid` + `cre2f_conversationid` | TLS 1.3 / AES-256 (Dataverse) | 30 Days (Interactive Memory) | Automatic cron-based 30-day purge in `MemoryService` | Contextual recall; audit trail |
| **Source Data Extracts (HCM / S/4HANA)** | Highly Confidential / PII | In-Memory ephemeral cache (`AsyncTTLCache`) | Hash of OData query parameters | TLS 1.3 / In-Memory only | 5 Minutes (TTL) | Automatic in-memory cache eviction on TTL expiry | Performance optimization; backend load reduction |
| **Two-Step Approval Previews** | Restricted / Governed | PostgreSQL (`operations`) / SQLite (`operations.db`) | `tenant_id` + `user_object_id` + `approval_id` | TLS 1.3 / AES-256 Volume encryption | 15 Minutes (Active); 90 Days (Archived Record) | Status transitions to `EXPIRED` after 15m; DB partition rotation | Write prevention; human-in-the-loop governance |
| **Notification Outbox Events & Leases** | Internal / Governed | PostgreSQL (`notification_deliveries`) / `outbox.db` | `tenant_id` + `deduplication_key` | TLS 1.3 / AES-256 Volume encryption | 7 Days (Delivered); 30 Days (Failed/Reconciled) | Batch purge job removing `state = 'DELIVERED'` > 7 days | Idempotent executive delivery; replay defense |
| **Audit Spool Records** | Compliance Audit | Local NVMe / Azure Files (`sf_audit_spool.jsonl`) | File append keyed by `event_id` / `turn_id` | Volume encryption at rest | Ephemeral until committed to Dataverse | Drained immediately upon `COMMITTED` status | Fail-closed durability during Dataverse outages |
| **Dataverse Compliance Audit Logs** | Compliance Audit | Microsoft Dataverse (`cre2f_veloraagentauditlogs`) | Alternate Key: `(cre2f_invocationid, cre2f_recordtype)` | TLS 1.3 / Microsoft Managed Keys (Customer Managed optional) | 7 Years (Statutory Requirement) | Annual compliance purge via Dataverse bulk-deletion job | Regulatory compliance, SOC forensics, non-repudiation |
| **Institutional Memory Knowledge Graph** | Confidential | Azure Files (`knowledge_graph.jsonl`) | Node ID (`KG-NODE-*`) + Topic Partition | Volume encryption at rest | 1 Year (Rolling) | Quarterly administrative review and purge | Organizational decision logging; meeting recall |

---

## 3. Data Isolation & Tenant Partitioning Architecture

1. **Multi-Tenant Logical Isolation**:
   - Every database record and audit entry strictly embeds `tenant_id` (Microsoft Entra Directory ID).
   - SQL queries must include `WHERE tenant_id = :tenant_id` to prevent cross-tenant data leakage.
2. **User Context Isolation**:
   - Interactive memory queries in `MemoryService` partition history strictly by `user_object_id`.
   - A query for `exec1@velora.ae` cannot retrieve or infer interaction history belonging to `exec2@velora.ae`.
3. **Cache Key Salting**:
   - In-memory cache keys for financial metrics and employee counts incorporate the caller's tenant identifier to prevent multi-tenant cache collision.

---

## 4. Retention & Deletion Runbooks

### 4.1 Automated 30-Day Memory Purge Runbook
The 30-day interactive memory purge is enforced programmatically by `MemoryService` and can be manually executed via admin CLI:
```bash
# Verify pending records older than 30 days
python -m successfactors_mcp.memory_service --action inspect-expired --cutoff-days 30

# Execute soft purge (mark records as ARCHIVED)
python -m successfactors_mcp.memory_service --action purge-expired --cutoff-days 30
```

### 4.2 Outbox & Delivery State Table Pruning
In PostgreSQL, run the following scheduled maintenance query (configured in Azure Database for PostgreSQL maintenance tasks or pg_cron):
```sql
-- Prune delivered notifications older than 7 days
DELETE FROM notification_deliveries
WHERE state IN ('DELIVERED', 'SUCCEEDED')
  AND updated_at < NOW() - INTERVAL '7 days';

-- Reconcile stalled leases
UPDATE operations
SET execution_state = 'OUTCOME_UNKNOWN', updated_at = EXTRACT(EPOCH FROM NOW())
WHERE execution_state = 'EXECUTING'
  AND claim_timestamp < EXTRACT(EPOCH FROM NOW()) - 900;
```

### 4.3 Data Subject Rights (GDPR / UAE PDPL) - Right to Erasure
To purge all personal records and interaction history for an offboarded executive:
1. Locate the user's Microsoft Entra Object ID (`user_object_id`).
2. Execute the user erasure script:
   ```bash
   python scripts/purge_user_data.py --tenant-id "7d167021-f5e9-4331-9b75-d44d55a1ce9b" --user-oid "<TARGET_USER_OID>"
   ```
3. The script executes the following atomic operations:
   - Deletes all records matching `cre2f_userobjectid` in `cre2f_veloraagentauditlogs` where retention policy permits.
   - Clears pending operations from `operations` where `user_object_id = :user_oid`.
   - Evicts cached entries associated with the user session.
   - Emits a cryptographic tombstone audit record verifying the completion of the erasure request.
