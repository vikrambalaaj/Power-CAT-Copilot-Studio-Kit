-- ==============================================================================
-- Migration: 001_create_operations_and_outbox.sql
-- Description: Core operational store, two-step execution operations,
--              outbox notification delivery state, durable recommendations,
--              breach episodes, and persistent cooldowns.
-- Safety: Fully additive and idempotent.
-- ==============================================================================

-- 1. Operations Lifecycle Store
CREATE TABLE IF NOT EXISTS operations (
    operation_id VARCHAR(128) PRIMARY KEY,
    capability VARCHAR(100) NOT NULL,
    operation VARCHAR(100) NOT NULL,
    state VARCHAR(50) NOT NULL DEFAULT 'PREPARED',
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    token_hash VARCHAR(128) NOT NULL,
    user_id VARCHAR(128) NOT NULL,
    user_email VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(128) NOT NULL DEFAULT '',
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    preview_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    external_object_id VARCHAR(255),
    retry_count INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 3,
    claimed_by VARCHAR(128),
    claim_expires_at TIMESTAMPTZ,
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_operations_state_expires ON operations (state, expires_at);
CREATE INDEX IF NOT EXISTS idx_operations_user_email ON operations (user_email);
CREATE INDEX IF NOT EXISTS idx_operations_tenant ON operations (tenant_id);
CREATE INDEX IF NOT EXISTS idx_operations_token_hash ON operations (token_hash);
CREATE INDEX IF NOT EXISTS idx_operations_claimed ON operations (claimed_by, claim_expires_at);

-- 2. Recommendations Store (Engine & Durable Mirror)
CREATE TABLE IF NOT EXISTS recommendations (
    rec_id VARCHAR(128) PRIMARY KEY,
    duplicate_key VARCHAR(128) NOT NULL UNIQUE,
    rule_code VARCHAR(100) NOT NULL,
    rule_version VARCHAR(50) NOT NULL,
    kpi_code VARCHAR(100) NOT NULL,
    organization_scope VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    observed_value NUMERIC(18, 4) NOT NULL,
    threshold NUMERIC(18, 4) NOT NULL,
    impact TEXT,
    explanation TEXT,
    suggested_action TEXT,
    confidence VARCHAR(50) NOT NULL,
    confidence_reason TEXT,
    first_detected TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_detected TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',
    snapshot_id VARCHAR(128),
    tenant_id VARCHAR(128) NOT NULL DEFAULT '',
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recommendations_scope_kpi ON recommendations (organization_scope, kpi_code);
CREATE INDEX IF NOT EXISTS idx_recommendations_status ON recommendations (status);
CREATE INDEX IF NOT EXISTS idx_recommendations_tenant ON recommendations (tenant_id);

-- 3. Outbox Notification Deliveries
CREATE TABLE IF NOT EXISTS notification_deliveries (
    delivery_id VARCHAR(128) PRIMARY KEY,
    recommendation_id VARCHAR(128) NOT NULL REFERENCES recommendations (rec_id) ON DELETE RESTRICT,
    recipient VARCHAR(255) NOT NULL,
    channel VARCHAR(50) NOT NULL DEFAULT 'EMAIL',
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    attempt_count INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 3,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_error TEXT,
    locked_by VARCHAR(128),
    locked_until TIMESTAMPTZ,
    tenant_id VARCHAR(128) NOT NULL DEFAULT '',
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_outbox_pending ON notification_deliveries (status, locked_until) WHERE status IN ('PENDING', 'FAILED_RETRYABLE');
CREATE INDEX IF NOT EXISTS idx_outbox_rec_id ON notification_deliveries (recommendation_id);
CREATE INDEX IF NOT EXISTS idx_outbox_recipient ON notification_deliveries (recipient);

-- 4. Persistent Breach Episodes (Prevents Alert Storms Across Container Restarts)
CREATE TABLE IF NOT EXISTS breach_episodes (
    episode_id VARCHAR(128) PRIMARY KEY,
    dedup_key VARCHAR(128) NOT NULL UNIQUE,
    rule_code VARCHAR(100) NOT NULL,
    kpi_code VARCHAR(100) NOT NULL,
    organization_scope VARCHAR(100) NOT NULL,
    first_breached_at TIMESTAMPTZ NOT NULL,
    last_breached_at TIMESTAMPTZ NOT NULL,
    peak_value NUMERIC(18, 4) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'OPEN',
    resolved_at TIMESTAMPTZ,
    tenant_id VARCHAR(128) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_breach_episodes_rule_scope ON breach_episodes (rule_code, organization_scope, status);

-- 5. Persistent Cooldowns Store (Prevents Duplicate Alerts on Restarts)
CREATE TABLE IF NOT EXISTS cooldowns (
    cooldown_key VARCHAR(128) PRIMARY KEY,
    rule_code VARCHAR(100) NOT NULL,
    organization_scope VARCHAR(100) NOT NULL,
    cooldown_until TIMESTAMPTZ NOT NULL,
    last_value NUMERIC(18, 4) NOT NULL,
    tenant_id VARCHAR(128) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cooldowns_expiry ON cooldowns (cooldown_until);

-- 6. Durable Audit Reconciliation Queue (Stores Failed or Buffered Audit Records for Background Mirroring)
CREATE TABLE IF NOT EXISTS audit_reconciliation_queue (
    id VARCHAR(128) PRIMARY KEY,
    record_type VARCHAR(100) NOT NULL,
    invocation_id VARCHAR(128),
    idempotency_key VARCHAR(128),
    payload JSONB NOT NULL,
    reason TEXT,
    retry_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING'
);

CREATE INDEX IF NOT EXISTS idx_audit_reconciliation_queue_status ON audit_reconciliation_queue (status, retry_count);
