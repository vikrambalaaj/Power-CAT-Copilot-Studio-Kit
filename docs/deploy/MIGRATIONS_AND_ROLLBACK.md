# Velora Platform - Database & Schema Migrations and Rollback Guidance

This document describes the schema architecture, storage migrations, and rollback procedures introduced in the Velora Executive AI Platform Security and Reliability Remediation.

---

## 1. Storage & Schema Architecture Overview

The platform uses two durable SQLite WAL-mode stores backed by Azure Files persistent mounts, plus Microsoft Dataverse for corporate compliance auditing:

1. **Operation & Approval Store (`operations.db`)**:
   - Location: `${VELORA_STATE_DIR}/operations.db` (default mount `/mnt/velora/state/operations.db`)
   - Manages ACID two-step approvals, preventing approval token replay and multi-instance concurrency race conditions.

2. **Outbox & Notification Claims Store (`outbox.db`)**:
   - Location: `${VELORA_OUTBOX_DIR}/outbox.db` (default mount `/mnt/velora/outbox/outbox.db`)
   - Manages distributed lease claiming, intent persistence, deduplication keys, and reconciliation.

3. **Dataverse Audit Entity (`cre2f_veloraagentauditlogs`)**:
   - Corporate compliance table in Microsoft Dataverse.
   - Enforces unique alternate key constraint `(cre2f_invocationid, cre2f_recordtype)`.

---

## 2. Table Definitions (DDL)

### 2.1 Operations Table (`operations.db`)

```sql
CREATE TABLE IF NOT EXISTS operations (
    operation_id TEXT PRIMARY KEY,
    approval_id TEXT UNIQUE NOT NULL,
    tenant_id TEXT NOT NULL,
    user_object_id TEXT NOT NULL,
    user_email TEXT NOT NULL,
    operation_type TEXT NOT NULL,
    payload_reference TEXT NOT NULL,
    payload_checksum TEXT NOT NULL,
    expiry_timestamp REAL NOT NULL,
    policy_version TEXT NOT NULL,
    confirmation_user_object_id TEXT,
    confirmation_timestamp REAL,
    execution_state TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    executor_instance_id TEXT,
    claim_timestamp REAL,
    provider_evidence TEXT,
    error_message TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_operations_approval_id ON operations(approval_id);
CREATE INDEX IF NOT EXISTS idx_operations_tenant_user ON operations(tenant_id, user_object_id);
CREATE INDEX IF NOT EXISTS idx_operations_state ON operations(execution_state);
```

### 2.2 Notification Deliveries Table (`outbox.db`)

```sql
CREATE TABLE IF NOT EXISTS notification_deliveries (
    delivery_id TEXT PRIMARY KEY,
    deduplication_key TEXT UNIQUE NOT NULL,
    tenant_id TEXT NOT NULL,
    recommendation_id TEXT NOT NULL,
    recipient TEXT NOT NULL,
    channel TEXT NOT NULL,
    state TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    lease_owner TEXT,
    lease_expiry REAL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    provider_reference TEXT,
    last_error TEXT,
    provider_receipt TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_deliveries_claim 
ON notification_deliveries(state, lease_expiry);

CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id TEXT PRIMARY KEY,
    duplicate_key TEXT UNIQUE NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS breach_episodes (
    episode_key TEXT PRIMARY KEY,
    episode_value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

---

## 3. Migration Procedure

### Pre-Deployment Verification:
1. Verify Azure Files share mount `velorastate` is accessible with read/write permissions at `/mnt/velora`.
2. Confirm SQLite 3.35+ is available in the container image (included in base Python 3.11 image).
3. The application tables are automatically initialized upon startup using `CREATE TABLE IF NOT EXISTS` with `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000`.

### Data Ingestion from Legacy Spool Files:
- If legacy `.jsonl` files exist in `/mnt/velora/outbox/notification_delivery_outbox.jsonl`, `DurableOutboxStore` automatically reads existing pending records and inserts them into SQLite (`ON CONFLICT(deduplication_key) DO NOTHING`), ensuring zero loss of in-flight notifications.
- SuccessFactors audit spool (`sf_audit_spool.jsonl`) retains existing spool entries and drains only committed rows with stable event IDs.

---

## 4. Rollback Guidance

If a rollback of the application container image is required:

1. **Storage Compatibility**:
   - The SQLite database files are backward-compatible and do not delete legacy JSONL logs.
   - Legacy versions reading `.jsonl` will continue to read the synchronized JSONL records.
2. **Reverting Container Images**:
   - Execute `az containerapp update --name velora-mcp-<service> --image <previous_image_digest>`.
3. **Database Reset (Emergency Only)**:
   - If database corruption is suspected, rename the active database files:
     ```bash
     mv /mnt/velora/state/operations.db /mnt/velora/state/operations.db.bak.$(date +%s)
     mv /mnt/velora/outbox/outbox.db /mnt/velora/outbox/outbox.db.bak.$(date +%s)
     ```
   - On container restart, new empty databases will be created and state re-ingested from the persistent JSONL files.
