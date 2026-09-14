-- ==============================================================================
-- Migration: 002_create_business_entities.sql
-- Description: Business entity tables corresponding to verified-local-schema.csv.
--              Includes tenant isolation, explicit object ownership, policy/version,
--              evidence reference tracking, and optimistic concurrency (version).
-- Safety: Fully additive and idempotent.
-- ==============================================================================

-- 1. Source Catalog (Data Sources & Connection Metadata)
CREATE TABLE IF NOT EXISTS source_catalog (
    source_catalog_id VARCHAR(200) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    owner VARCHAR(400) NOT NULL DEFAULT '',
    environment VARCHAR(200) NOT NULL DEFAULT 'Production',
    connection_alias VARCHAR(200) NOT NULL DEFAULT '',
    permitted_tools VARCHAR(2000) NOT NULL DEFAULT '',
    allowed_scope VARCHAR(1000) NOT NULL DEFAULT '',
    refresh_expectation VARCHAR(200) NOT NULL DEFAULT 'Daily',
    sensitivity VARCHAR(100) NOT NULL DEFAULT 'CONFIDENTIAL',
    effective_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    effective_to TIMESTAMPTZ,
    tenant_id VARCHAR(128) NOT NULL DEFAULT '',
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_source_catalog_tenant ON source_catalog (tenant_id);
CREATE INDEX IF NOT EXISTS idx_source_catalog_alias ON source_catalog (connection_alias);

-- 2. KPI Definitions (Business Definition, Scope, Sign Convention)
CREATE TABLE IF NOT EXISTS kpi_definition (
    kpi_definition_id VARCHAR(200) PRIMARY KEY,
    kpi_code VARCHAR(200) NOT NULL UNIQUE,
    name VARCHAR(400) NOT NULL,
    business_definition TEXT NOT NULL,
    source_catalog_id VARCHAR(200) REFERENCES source_catalog(source_catalog_id) ON DELETE SET NULL,
    calculation_code VARCHAR(200) NOT NULL DEFAULT '',
    unit VARCHAR(100) NOT NULL DEFAULT '',
    organization_scope VARCHAR(200) NOT NULL DEFAULT 'Enterprise',
    sign_convention VARCHAR(100) NOT NULL DEFAULT 'HIGHER_IS_BETTER',
    freshness_max_minutes INT NOT NULL DEFAULT 1440,
    tenant_id VARCHAR(128) NOT NULL DEFAULT '',
    owner VARCHAR(400) NOT NULL DEFAULT '',
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kpi_definition_code ON kpi_definition (kpi_code);
CREATE INDEX IF NOT EXISTS idx_kpi_definition_tenant ON kpi_definition (tenant_id);

-- 3. KPI Recommendation Rules (Thresholds, Cooldowns, Hysteresis Clear Thresholds)
CREATE TABLE IF NOT EXISTS kpi_recommendation_rule (
    kpi_recommendation_rule_id VARCHAR(200) PRIMARY KEY,
    rule_code VARCHAR(200) NOT NULL UNIQUE,
    version_tag VARCHAR(60) NOT NULL DEFAULT '1.0',
    name VARCHAR(400) NOT NULL,
    kpi VARCHAR(200) NOT NULL,
    organization_scope VARCHAR(200) NOT NULL DEFAULT 'Enterprise',
    category VARCHAR(100) NOT NULL,
    comparator VARCHAR(100) NOT NULL,
    threshold NUMERIC(18, 4) NOT NULL,
    upper_threshold NUMERIC(18, 4),
    clear_threshold NUMERIC(18, 4),
    unit VARCHAR(100) NOT NULL DEFAULT '',
    currency VARCHAR(20) NOT NULL DEFAULT 'AED',
    comparison_window VARCHAR(100) NOT NULL DEFAULT 'MTD',
    cooldown_minutes INT NOT NULL DEFAULT 1440,
    severity VARCHAR(100) NOT NULL DEFAULT 'MEDIUM',
    priority INT NOT NULL DEFAULT 1,
    recommendation_template TEXT NOT NULL,
    explanation_template TEXT NOT NULL,
    requires_complete BOOLEAN NOT NULL DEFAULT TRUE,
    owner VARCHAR(400) NOT NULL DEFAULT '',
    state VARCHAR(100) NOT NULL DEFAULT 'ACTIVE',
    effective_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    effective_to TIMESTAMPTZ,
    tenant_id VARCHAR(128) NOT NULL DEFAULT '',
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kpi_rule_code ON kpi_recommendation_rule (rule_code);
CREATE INDEX IF NOT EXISTS idx_kpi_rule_scope ON kpi_recommendation_rule (organization_scope, state);
CREATE INDEX IF NOT EXISTS idx_kpi_rule_tenant ON kpi_recommendation_rule (tenant_id);

-- 4. KPI Snapshots (Point-in-time Observed Metrics with Input Hash)
CREATE TABLE IF NOT EXISTS kpi_snapshot (
    kpi_snapshot_id VARCHAR(200) PRIMARY KEY,
    snapshot_id VARCHAR(200) NOT NULL,
    kpi_code VARCHAR(200) NOT NULL,
    organization_scope VARCHAR(200) NOT NULL,
    period VARCHAR(100) NOT NULL,
    metric_value NUMERIC(18, 4) NOT NULL,
    unit VARCHAR(100) NOT NULL,
    currency VARCHAR(20) NOT NULL DEFAULT 'AED',
    source_updated_time TIMESTAMPTZ NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completeness VARCHAR(100) NOT NULL DEFAULT 'COMPLETE',
    evidence_ref VARCHAR(1000) NOT NULL DEFAULT '',
    input_hash VARCHAR(256) NOT NULL DEFAULT '',
    tenant_id VARCHAR(128) NOT NULL DEFAULT '',
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kpi_snapshot_code_scope ON kpi_snapshot (kpi_code, organization_scope, period);
CREATE INDEX IF NOT EXISTS idx_kpi_snapshot_hash ON kpi_snapshot (input_hash);
CREATE INDEX IF NOT EXISTS idx_kpi_snapshot_tenant ON kpi_snapshot (tenant_id);

-- 5. Recommendation Feedback (Executive Feedback & Action Verification)
CREATE TABLE IF NOT EXISTS recommendation_feedback (
    recommendation_feedback_id VARCHAR(200) PRIMARY KEY,
    feedback_id VARCHAR(200) NOT NULL UNIQUE,
    recommendation_id VARCHAR(200) NOT NULL,
    reviewer VARCHAR(400) NOT NULL,
    is_useful BOOLEAN NOT NULL,
    feedback_type VARCHAR(100) NOT NULL DEFAULT 'EXECUTIVE_REVIEW',
    comment TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tenant_id VARCHAR(128) NOT NULL DEFAULT '',
    owner VARCHAR(400) NOT NULL DEFAULT '',
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feedback_rec_id ON recommendation_feedback (recommendation_id);
CREATE INDEX IF NOT EXISTS idx_feedback_reviewer ON recommendation_feedback (reviewer);
CREATE INDEX IF NOT EXISTS idx_feedback_tenant ON recommendation_feedback (tenant_id);

-- 6. Decision Evidence (Cryptographically Hashed Evidence Packages for AI Decisions)
CREATE TABLE IF NOT EXISTS decision_evidence (
    decision_evidence_id VARCHAR(200) PRIMARY KEY,
    claim_id VARCHAR(200) NOT NULL,
    decision_id VARCHAR(200) NOT NULL,
    source_lookup VARCHAR(200) NOT NULL,
    source_version VARCHAR(100) NOT NULL,
    input_snapshot TEXT NOT NULL,
    rationale TEXT NOT NULL,
    output_hash VARCHAR(256) NOT NULL,
    verified_identity VARCHAR(400) NOT NULL,
    limitations TEXT,
    manifest_ref VARCHAR(1000) NOT NULL DEFAULT '',
    tenant_id VARCHAR(128) NOT NULL DEFAULT '',
    owner VARCHAR(400) NOT NULL DEFAULT '',
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_decision_evidence_claim ON decision_evidence (claim_id);
CREATE INDEX IF NOT EXISTS idx_decision_evidence_decision ON decision_evidence (decision_id);
CREATE INDEX IF NOT EXISTS idx_decision_evidence_hash ON decision_evidence (output_hash);
CREATE INDEX IF NOT EXISTS idx_decision_evidence_tenant ON decision_evidence (tenant_id);

-- 7. Institutional Records (Executive Decisions, Meeting Actions, Strategy Artifacts)
CREATE TABLE IF NOT EXISTS institutional_record (
    institutional_record_id VARCHAR(200) PRIMARY KEY,
    record_title VARCHAR(400) NOT NULL,
    record_type VARCHAR(200) NOT NULL,
    source_agent VARCHAR(200) NOT NULL,
    executive_owner VARCHAR(400) NOT NULL,
    summary TEXT NOT NULL,
    key_decisions TEXT NOT NULL,
    action_items TEXT NOT NULL,
    retention_policy VARCHAR(400) NOT NULL DEFAULT '7_YEARS_STANDARD',
    loop_component_id VARCHAR(1000),
    notebook_location VARCHAR(2000),
    created_on TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tenant_id VARCHAR(128) NOT NULL DEFAULT '',
    owner VARCHAR(400) NOT NULL DEFAULT '',
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_institutional_record_owner ON institutional_record (executive_owner);
CREATE INDEX IF NOT EXISTS idx_institutional_record_type ON institutional_record (record_type);
CREATE INDEX IF NOT EXISTS idx_institutional_record_tenant ON institutional_record (tenant_id);

-- 8. Proposal Evaluation (Capital Allocations, Rubric Scoring, Financial Evaluation)
CREATE TABLE IF NOT EXISTS proposal_evaluation (
    proposal_evaluation_id VARCHAR(200) PRIMARY KEY,
    proposal_title VARCHAR(400) NOT NULL,
    proposal_id VARCHAR(200) NOT NULL UNIQUE,
    submitter VARCHAR(400) NOT NULL,
    requested_capital VARCHAR(200) NOT NULL,
    currency VARCHAR(20) NOT NULL DEFAULT 'AED',
    payback_period_months VARCHAR(100) NOT NULL,
    irr VARCHAR(100) NOT NULL,
    npv VARCHAR(200) NOT NULL,
    rubric_score VARCHAR(100) NOT NULL,
    evaluation_status VARCHAR(100) NOT NULL DEFAULT 'UNDER_REVIEW',
    evaluation_summary TEXT NOT NULL,
    evaluated_by VARCHAR(400) NOT NULL,
    evaluated_on TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tenant_id VARCHAR(128) NOT NULL DEFAULT '',
    owner VARCHAR(400) NOT NULL DEFAULT '',
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_proposal_evaluation_id ON proposal_evaluation (proposal_id);
CREATE INDEX IF NOT EXISTS idx_proposal_evaluation_status ON proposal_evaluation (evaluation_status);
CREATE INDEX IF NOT EXISTS idx_proposal_evaluation_tenant ON proposal_evaluation (tenant_id);

-- 9. Peer Benchmark (Cohort Analysis, Quartile Distributions, Variance Detection)
CREATE TABLE IF NOT EXISTS peer_benchmark (
    peer_benchmark_id VARCHAR(200) PRIMARY KEY,
    benchmark_name VARCHAR(400) NOT NULL,
    metric_code VARCHAR(200) NOT NULL,
    cohort_name VARCHAR(400) NOT NULL,
    internal_value VARCHAR(200) NOT NULL,
    peer_median VARCHAR(200) NOT NULL,
    peer_top_quartile VARCHAR(200) NOT NULL,
    peer_bottom_quartile VARCHAR(200) NOT NULL,
    unit VARCHAR(100) NOT NULL,
    variance_status VARCHAR(100) NOT NULL DEFAULT 'ON_PAR',
    data_source VARCHAR(400) NOT NULL,
    benchmark_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tenant_id VARCHAR(128) NOT NULL DEFAULT '',
    owner VARCHAR(400) NOT NULL DEFAULT '',
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_peer_benchmark_metric_cohort ON peer_benchmark (metric_code, cohort_name);
CREATE INDEX IF NOT EXISTS idx_peer_benchmark_tenant ON peer_benchmark (tenant_id);

-- Compatibility view mapping cre2f_recommendation to recommendations table
CREATE OR REPLACE VIEW cre2f_recommendation AS
SELECT
    rec_id AS cre2f_recommendationid,
    rec_id AS cre2f_recid,
    rule_code AS cre2f_rulecode,
    rule_version AS cre2f_ruleversion,
    kpi_code AS cre2f_kpicode,
    organization_scope AS cre2f_organizationscope,
    category AS cre2f_category,
    observed_value AS cre2f_observedvalue,
    threshold AS cre2f_threshold,
    impact AS cre2f_impact,
    explanation AS cre2f_explanation,
    suggested_action AS cre2f_suggestedaction,
    confidence AS cre2f_confidence,
    confidence_reason AS cre2f_confidencereason,
    first_detected AS cre2f_firstdetected,
    last_detected AS cre2f_lastdetected,
    status AS cre2f_status,
    duplicate_key AS cre2f_duplicatekey,
    snapshot_id AS cre2f_snapshotid
FROM recommendations;
