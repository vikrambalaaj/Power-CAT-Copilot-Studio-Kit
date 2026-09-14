# Velora Platform - Database & Schema Migrations and Rollback Guidance

This document describes the schema architecture, storage migrations, and rollback procedures introduced in the Velora Executive AI Platform Security and Reliability Remediation.

---

## 1. Storage & Schema Architecture Overview

The platform supports two transactional storage architectures:

1. **Enterprise Multi-Replica Production Architecture (PostgreSQL / Azure Database for PostgreSQL)**:
   - Configured via `DATABASE_URL` and `VELORA_ENV=production`.
   - Supports multi-replica container apps with row-level locking (`SELECT ... FOR UPDATE SKIP LOCKED`), ACID transaction isolation, and persistent leases.
   - Required for any environment with multiple container replicas or horizontally scaled background workers.

2. **Single-Host Development Architecture (SQLite WAL mode)**:
   - Configured via `${VELORA_STATE_DIR}/operations.db` and `${VELORA_OUTBOX_DIR}/outbox.db`.
   - **Caution**: SQLite WAL mode is strictly restricted to single-host local development. Multi-replica deployments over network filesystems (NFS/CIFS/Azure Files) will fail lock reconciliation and are explicitly blocked when `VELORA_ENV=production`.

3. **Dataverse Audit Entity (`cre2f_veloraagentauditlogs`)**:
   - Corporate compliance table in Microsoft Dataverse.
   - Enforces unique alternate key constraint `(cre2f_invocationid, cre2f_recordtype)`.

---

## 2. Table Definitions (DDL)

### 2.1 PostgreSQL Enterprise Schema (Production)

```sql
-- Operations and Approvals Table
CREATE TABLE IF NOT EXISTS operations (
    operation_id VARCHAR(128) PRIMARY KEY,
    approval_id VARCHAR(128) UNIQUE NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    user_object_id VARCHAR(128) NOT NULL,
    user_email VARCHAR(255) NOT NULL,
    operation_type VARCHAR(64) NOT NULL,
    payload_reference TEXT NOT NULL,
    payload_checksum VARCHAR(128) NOT NULL,
    expiry_timestamp DOUBLE PRECISION NOT NULL,
    policy_version VARCHAR(32) NOT NULL,
    confirmation_user_object_id VARCHAR(128),
    confirmation_timestamp DOUBLE PRECISION,
    execution_state VARCHAR(64) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    executor_instance_id VARCHAR(128),
    claim_timestamp DOUBLE PRECISION,
    provider_evidence TEXT,
    error_message TEXT,
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_operations_approval_id ON operations(approval_id);
CREATE INDEX IF NOT EXISTS idx_operations_tenant_user ON operations(tenant_id, user_object_id);
CREATE INDEX IF NOT EXISTS idx_operations_state ON operations(execution_state);
CREATE INDEX IF NOT EXISTS idx_operations_lease ON operations(execution_state, claim_timestamp);

-- Notification Deliveries Table
CREATE TABLE IF NOT EXISTS notification_deliveries (
    delivery_id VARCHAR(128) PRIMARY KEY,
    deduplication_key VARCHAR(255) UNIQUE NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    recommendation_id VARCHAR(128) NOT NULL,
    recipient VARCHAR(255) NOT NULL,
    channel VARCHAR(64) NOT NULL,
    state VARCHAR(64) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    lease_owner VARCHAR(128),
    lease_expiry DOUBLE PRECISION,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    provider_reference TEXT,
    last_error TEXT,
    provider_receipt TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_deliveries_claim 
ON notification_deliveries(state, lease_expiry);

-- Outbox Events Table
CREATE TABLE IF NOT EXISTS outbox_events (
    event_id VARCHAR(128) PRIMARY KEY,
    aggregate_id VARCHAR(128) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    state VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_outbox_pending ON outbox_events(state, created_at);
```

### 2.2 SQLite Development Schema (Local Single-Host Only)

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
```

---

## 3. Migration Procedure

### Pre-Deployment Verification:
1. **Production (PostgreSQL)**:
   - Ensure PostgreSQL 14+ instance is provisioned with SSL enforcement (`sslmode=require`).
   - Run the PostgreSQL DDL script via migration runner or DBA deployment pipeline.
   - Verify connection string `DATABASE_URL` is populated in Azure Key Vault and referenced in Container App secrets.
2. **Development (SQLite)**:
   - Verify local state directory is accessible with read/write permissions.
   - Confirm SQLite 3.35+ is available in the Python runtime.
   - Tables are auto-initialized on startup with WAL pragma.

---

## 4. Rollback Guidance

1. **PostgreSQL Schema Rollback**:
   - If a rollback is needed, the tables can be preserved as they are additive.
   - In the event of schema tear-down:
     ```sql
     DROP TABLE IF EXISTS outbox_events;
     DROP TABLE IF EXISTS notification_deliveries;
     DROP TABLE IF EXISTS operations;
     ```
2. **Container Image Rollback**:
   - Execute: `az containerapp update --name velora-mcp-<service> --image <previous_image_digest>`.
3. **Emergency Lease Cleardown**:
   - If worker nodes crash holding locks, unexpired leases can be reset to `OUTCOME_UNKNOWN` for reconciliation:
     ```sql
     UPDATE operations 
     SET execution_state = 'OUTCOME_UNKNOWN', updated_at = EXTRACT(EPOCH FROM NOW())
     WHERE execution_state = 'EXECUTING' AND claim_timestamp < (EXTRACT(EPOCH FROM NOW()) - 300);
     ```
