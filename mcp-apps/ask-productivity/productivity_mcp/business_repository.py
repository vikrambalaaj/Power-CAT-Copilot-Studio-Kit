"""Durable Business Repository for Velora Executive Platform (W03).

Provides tenant-scoped, concurrency-protected, and bounded persistence for:
- Source Catalogues (`cre2f_sourcecatalog`)
- KPI Definitions (`cre2f_kpidefinition`)
- KPI Recommendation Rules (`cre2f_kpirecommendationrule`)
- KPI Snapshots (`cre2f_kpisnapshot`)
- Recommendations (`cre2f_recommendation`)
- Recommendation Feedback (`cre2f_recommendationfeedback`)
- Institutional Records (`cre2f_institutionalrecord`)
- Decision Evidence (`cre2f_decisionevidence`)
- Peer Benchmarks (`cre2f_peerbenchmark`)
- Proposal Evaluations (`cre2f_proposalevaluation`)
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("productivity_mcp.business_repository")


class ConcurrencyConflictError(Exception):
    """Raised when an update fails due to version/optimistic concurrency conflict."""


class AccessDeniedError(Exception):
    """Raised when cross-tenant access or unauthorized modification is detected."""


class FinalizedEvidenceMutationError(PermissionError):
    """Raised when an application role or unauthorized caller attempts to update or delete finalized decision evidence."""


@dataclass
class SourceCatalogRecord:
    source_catalog_id: str
    tenant_id: str
    name: str
    description: str
    owner: str
    environment: str
    connection_alias: str
    permitted_tools: str
    allowed_scope: str
    refresh_expectation: str
    sensitivity: str
    effective_from: str
    effective_to: Optional[str] = None
    version: int = 1


@dataclass
class KPIDefinitionRecord:
    kpi_definition_id: str
    tenant_id: str
    kpi_code: str
    name: str
    business_definition: str
    source_catalog_id: str
    calculation_code: str
    unit: str
    organization_scope: str
    sign_convention: str
    freshness_max_minutes: int
    version: int = 1


@dataclass
class KPIRuleRecord:
    kpi_recommendation_rule_id: str
    tenant_id: str
    rule_code: str
    rule_version: str
    name: str
    kpi: str
    organization_scope: str
    category: str
    comparator: str
    threshold: Decimal
    upper_threshold: Optional[Decimal] = None
    clear_threshold: Optional[Decimal] = None
    unit: str = "currency"
    currency: str = "AED"
    comparison_window: str = "snapshot"
    cooldown_minutes: int = 60
    severity: str = "high"
    priority: int = 1
    recommendation_template: str = ""
    explanation_template: str = ""
    requires_complete: bool = True
    owner: str = "Finance Operations"
    state: str = "Active"
    effective_from: str = "2026-01-01T00:00:00Z"
    effective_to: Optional[str] = None
    version: int = 1


@dataclass
class KPISnapshotRecord:
    kpi_snapshot_id: str
    tenant_id: str
    snapshot_id: str
    kpi_code: str
    organization_scope: str
    period: str
    metric_value: Decimal
    unit: str
    currency: str
    source_updated_time: Optional[str]
    retrieved_at: str
    completeness: str
    evidence_ref: str
    input_hash: str
    version: int = 1


@dataclass
class RecommendationEntityRecord:
    recommendation_id: str
    tenant_id: str
    rec_id: str
    rule_code: str
    rule_version: str
    kpi_code: str
    organization_scope: str
    category: str
    observed_value: Decimal
    threshold: Decimal
    impact: str
    explanation: str
    suggested_action: str
    confidence: str
    confidence_reason: str
    first_detected: str
    last_detected: str
    status: str
    duplicate_key: str
    snapshot_id: str
    version: int = 1


@dataclass
class RecommendationFeedbackRecord:
    recommendation_feedback_id: str
    tenant_id: str
    feedback_id: str
    recommendation_id: str
    reviewer: str
    is_useful: bool
    feedback_type: str
    comment: str
    recorded_at: str
    version: int = 1


@dataclass
class InstitutionalRecordEntity:
    institutional_record_id: str
    tenant_id: str
    record_title: str
    record_type: str
    source_agent: str
    executive_owner: str
    summary: str
    key_decisions: str
    action_items: str
    retention_policy: str
    loop_component_id: str = ""
    notebook_location: str = ""
    created_on: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: int = 1


@dataclass
class VendorPerformanceHistoryRecord:
    record_id: str
    tenant_id: str
    vendor_id: str
    vendor_name: str
    entity_scope: str
    contract_ref: str
    period_start: str
    period_end: str
    event_type: str
    severity: str
    numeric_value: Optional[Decimal]
    unit: str
    currency: str
    summary: str
    details: str
    source_doc_ref: str
    source_hash: str
    source_system: str
    recorded_by: str
    verification_status: str
    access_scope: str
    retention_policy: str
    legal_hold: bool
    original_event_date: str
    ingested_at: str
    version: int = 1


@dataclass
class DecisionEvidenceRecord:
    decision_evidence_id: str
    tenant_id: str
    claim_id: str
    decision_id: str
    source_lookup: str
    source_version: str
    input_snapshot: str
    rationale: str
    output_hash: str
    verified_identity: str
    limitations: str
    manifest_ref: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: int = 1


@dataclass
class PeerBenchmarkRecord:
    peer_benchmark_id: str
    tenant_id: str
    benchmark_name: str
    metric_code: str
    cohort_name: str
    internal_value: str
    peer_median: str
    peer_top_quartile: str
    peer_bottom_quartile: str
    unit: str
    variance_status: str
    data_source: str
    benchmark_date: str
    version: int = 1


@dataclass
class ProposalEvaluationRecord:
    proposal_evaluation_id: str
    tenant_id: str
    proposal_title: str
    proposal_id: str
    submitter: str
    requested_capital: str
    currency: str
    payback_period_months: str
    irr: str
    npv: str
    rubric_score: str
    evaluation_status: str
    evaluationsummary: str
    evaluated_by: str
    evaluated_on: str
    version: int = 1


@dataclass
class VendorDecisionRecord:
    decision_id: str
    version: str
    tenant_id: str
    use_case: str
    evaluated_options_json: str
    criteria_weights_json: str
    input_snapshot_ids_json: str
    baseline_score_json: str
    memory_contributions_json: str
    final_score_json: str
    final_rank_json: str
    tie_policy: str
    missing_data_policy: str
    selected_option: Optional[str]
    claims_json: str
    concise_rationale: str
    policy_id: str
    policy_version: str
    code_version: str
    authenticated_actor_json: str
    audit_manifest_ref: Optional[str]
    created_at: str
    updated_at: str


@dataclass
class MeetingActionMappingRecord:
    mapping_id: str
    tenant_id: str
    meeting_id: str
    source_version: str
    extracted_action_id: str
    planner_task_id: str
    plan_id: str
    bucket_id: Optional[str]
    title: str
    owner_user_id: Optional[str]
    owner_email: Optional[str]
    due_date: Optional[str]
    status: str  # "NOT_STARTED", "IN_PROGRESS", "COMPLETED", "CANCELED"
    percent_complete: int  # 0 to 100
    originating_decision: Optional[str]
    source_citation: Optional[str]
    evidence_id: Optional[str]
    audit_id: Optional[str]
    created_at: str
    updated_at: str
    version: int = 1


class SqliteBusinessRepository:
    """ACID SQLite implementation of Business Repository for local/test execution."""

    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            base_dir = os.getenv("VELORA_STORAGE_DIR") or os.getenv("VELORA_OUTBOX_DIR") or str(Path.home() / ".velora")
            p = Path(base_dir)
            p.mkdir(parents=True, exist_ok=True)
            db_path = str(p / "velora_business.db")
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS source_catalog (
                    source_catalog_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    connection_alias TEXT NOT NULL,
                    permitted_tools TEXT NOT NULL,
                    allowed_scope TEXT NOT NULL,
                    refresh_expectation TEXT NOT NULL,
                    sensitivity TEXT NOT NULL,
                    effective_from TEXT NOT NULL,
                    effective_to TEXT,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_sc_tenant ON source_catalog(tenant_id);

                CREATE TABLE IF NOT EXISTS kpi_definition (
                    kpi_definition_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    kpi_code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    business_definition TEXT NOT NULL,
                    source_catalog_id TEXT NOT NULL,
                    calculation_code TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    organization_scope TEXT NOT NULL,
                    sign_convention TEXT NOT NULL,
                    freshness_max_minutes INTEGER NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_kpi_def_tenant ON kpi_definition(tenant_id, kpi_code);

                CREATE TABLE IF NOT EXISTS kpi_recommendation_rule (
                    kpi_recommendation_rule_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    rule_code TEXT NOT NULL,
                    rule_version TEXT NOT NULL,
                    name TEXT NOT NULL,
                    kpi TEXT NOT NULL,
                    organization_scope TEXT NOT NULL,
                    category TEXT NOT NULL,
                    comparator TEXT NOT NULL,
                    threshold TEXT NOT NULL,
                    upper_threshold TEXT,
                    clear_threshold TEXT,
                    unit TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    comparison_window TEXT NOT NULL,
                    cooldown_minutes INTEGER NOT NULL,
                    severity TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    recommendation_template TEXT NOT NULL,
                    explanation_template TEXT NOT NULL,
                    requires_complete INTEGER NOT NULL,
                    owner TEXT NOT NULL,
                    state TEXT NOT NULL,
                    effective_from TEXT NOT NULL,
                    effective_to TEXT,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_kpi_rule_tenant ON kpi_recommendation_rule(tenant_id, rule_code);

                CREATE TABLE IF NOT EXISTS kpi_snapshot (
                    kpi_snapshot_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    kpi_code TEXT NOT NULL,
                    organization_scope TEXT NOT NULL,
                    period TEXT NOT NULL,
                    metric_value TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    source_updated_time TEXT,
                    retrieved_at TEXT NOT NULL,
                    completeness TEXT NOT NULL,
                    evidence_ref TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_kpi_snap_tenant ON kpi_snapshot(tenant_id, kpi_code);

                CREATE TABLE IF NOT EXISTS recommendations (
                    recommendation_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    rec_id TEXT NOT NULL,
                    rule_code TEXT NOT NULL,
                    rule_version TEXT NOT NULL,
                    kpi_code TEXT NOT NULL,
                    organization_scope TEXT NOT NULL,
                    category TEXT NOT NULL,
                    observed_value TEXT NOT NULL,
                    threshold TEXT NOT NULL,
                    impact TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    suggested_action TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    confidence_reason TEXT NOT NULL,
                    first_detected TEXT NOT NULL,
                    last_detected TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duplicate_key TEXT UNIQUE NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_rec_tenant ON recommendations(tenant_id, status);

                CREATE TABLE IF NOT EXISTS recommendation_feedback (
                    recommendation_feedback_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    feedback_id TEXT NOT NULL,
                    recommendation_id TEXT NOT NULL,
                    reviewer TEXT NOT NULL,
                    is_useful INTEGER NOT NULL,
                    feedback_type TEXT NOT NULL,
                    comment TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_fb_tenant ON recommendation_feedback(tenant_id, recommendation_id);

                CREATE TABLE IF NOT EXISTS institutional_record (
                    institutional_record_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    record_title TEXT NOT NULL,
                    record_type TEXT NOT NULL,
                    source_agent TEXT NOT NULL,
                    executive_owner TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    key_decisions TEXT NOT NULL,
                    action_items TEXT NOT NULL,
                    retention_policy TEXT NOT NULL,
                    loop_component_id TEXT,
                    notebook_location TEXT,
                    created_on TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_inst_tenant ON institutional_record(tenant_id, record_type);

                CREATE TABLE IF NOT EXISTS decision_evidence (
                    decision_evidence_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    claim_id TEXT NOT NULL,
                    decision_id TEXT NOT NULL,
                    source_lookup TEXT NOT NULL,
                    source_version TEXT NOT NULL,
                    input_snapshot TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    output_hash TEXT NOT NULL,
                    verified_identity TEXT NOT NULL,
                    limitations TEXT NOT NULL,
                    manifest_ref TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_de_tenant ON decision_evidence(tenant_id, decision_id);

                CREATE TABLE IF NOT EXISTS peer_benchmark (
                    peer_benchmark_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    benchmark_name TEXT NOT NULL,
                    metric_code TEXT NOT NULL,
                    cohort_name TEXT NOT NULL,
                    internal_value TEXT NOT NULL,
                    peer_median TEXT NOT NULL,
                    peer_top_quartile TEXT NOT NULL,
                    peer_bottom_quartile TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    variance_status TEXT NOT NULL,
                    data_source TEXT NOT NULL,
                    benchmark_date TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_pb_tenant ON peer_benchmark(tenant_id, metric_code);

                CREATE TABLE IF NOT EXISTS proposal_evaluation (
                    proposal_evaluation_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    proposal_title TEXT NOT NULL,
                    proposal_id TEXT NOT NULL,
                    submitter TEXT NOT NULL,
                    requested_capital TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    payback_period_months TEXT NOT NULL,
                    irr TEXT NOT NULL,
                    npv TEXT NOT NULL,
                    rubric_score TEXT NOT NULL,
                    evaluation_status TEXT NOT NULL,
                    evaluationsummary TEXT NOT NULL,
                    evaluated_by TEXT NOT NULL,
                    evaluated_on TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_pe_tenant ON proposal_evaluation(tenant_id);

                CREATE TABLE IF NOT EXISTS vendor_performance_history (
                    record_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    vendor_id TEXT NOT NULL,
                    vendor_name TEXT NOT NULL,
                    entity_scope TEXT NOT NULL,
                    contract_ref TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    numeric_value TEXT,
                    unit TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    details TEXT,
                    source_doc_ref TEXT NOT NULL,
                    source_hash TEXT NOT NULL,
                    source_system TEXT NOT NULL,
                    recorded_by TEXT NOT NULL,
                    verification_status TEXT NOT NULL,
                    access_scope TEXT NOT NULL,
                    retention_policy TEXT NOT NULL,
                    legal_hold INTEGER NOT NULL DEFAULT 0,
                    original_event_date TEXT NOT NULL,
                    ingested_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_vph_tenant_vendor ON vendor_performance_history(tenant_id, vendor_id);
                CREATE INDEX IF NOT EXISTS idx_vph_tenant_scope ON vendor_performance_history(tenant_id, entity_scope);
                CREATE INDEX IF NOT EXISTS idx_vph_source_hash ON vendor_performance_history(tenant_id, source_hash);

                CREATE TABLE IF NOT EXISTS vendor_decision_record (
                    decision_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    use_case TEXT NOT NULL,
                    evaluated_options_json TEXT NOT NULL,
                    criteria_weights_json TEXT NOT NULL,
                    input_snapshot_ids_json TEXT NOT NULL,
                    baseline_score_json TEXT NOT NULL,
                    memory_contributions_json TEXT NOT NULL,
                    final_score_json TEXT NOT NULL,
                    final_rank_json TEXT NOT NULL,
                    tie_policy TEXT NOT NULL,
                    missing_data_policy TEXT NOT NULL,
                    selected_option TEXT,
                    claims_json TEXT NOT NULL,
                    concise_rationale TEXT NOT NULL,
                    policy_id TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    code_version TEXT NOT NULL,
                    authenticated_actor_json TEXT NOT NULL,
                    audit_manifest_ref TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, decision_id, version)
                );
                CREATE INDEX IF NOT EXISTS idx_vdr_tenant_use_case ON vendor_decision_record(tenant_id, use_case);
                CREATE INDEX IF NOT EXISTS idx_vdr_tenant_decision ON vendor_decision_record(tenant_id, decision_id);

                CREATE TABLE IF NOT EXISTS meeting_action_mapping (
                    mapping_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    meeting_id TEXT NOT NULL,
                    source_version TEXT NOT NULL,
                    extracted_action_id TEXT NOT NULL,
                    planner_task_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    bucket_id TEXT,
                    title TEXT NOT NULL,
                    owner_user_id TEXT,
                    owner_email TEXT,
                    due_date TEXT,
                    status TEXT NOT NULL,
                    percent_complete INTEGER NOT NULL DEFAULT 0,
                    originating_decision TEXT,
                    source_citation TEXT,
                    evidence_id TEXT,
                    audit_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_mam_lookup ON meeting_action_mapping(tenant_id, meeting_id, source_version);
                CREATE INDEX IF NOT EXISTS idx_mam_task ON meeting_action_mapping(tenant_id, planner_task_id);
            """)
            self._seed_baseline_rules(conn)
        finally:
            conn.close()

    @property
    def rules(self) -> KpiRecommendationRuleRepository:
        return KpiRecommendationRuleRepository(db_path=self.db_path)

    @property
    def meeting_actions(self) -> MeetingActionRepository:
        return MeetingActionRepository(db_path=self.db_path)


    def _seed_baseline_rules(self, conn: sqlite3.Connection) -> None:
        """Seed initial approved rules for velora-aviation tenant to ensure baseline operational continuity."""
        cur = conn.execute("SELECT COUNT(*) as cnt FROM kpi_recommendation_rule WHERE tenant_id = 'velora-aviation'")
        row = cur.fetchone()
        if row and row["cnt"] > 0:
            return

        baseline_rules = [
            (
                "RULE-AR-001", "velora-aviation", "REC-RULE-AR-OVERDUE-90D", "1.0.0",
                "High Overdue Customer Receivables (>90 Days)", "RECEIVABLES", "1000",
                "RISK", "GT", "2000000.00", None, "1500000.00", "currency", "AED",
                "snapshot", 60, "high", 1,
                "Initiate executive collections escalation for top overdue customer accounts exceeding threshold.",
                "Customer receivables overdue >90 days reached AED {value}, crossing the approved risk limit of AED {threshold}.",
                1, "finance-ops@velora.ae", "ACTIVE", "2026-01-01T00:00:00Z", None, 1
            ),
            (
                "RULE-HR-001", "velora-aviation", "REC-RULE-EMIRATISATION-FLOOR", "1.0.0",
                "Emiratisation Below Target Floor", "EMIRATISATION", "1000",
                "RISK", "LT", "40.0", None, "42.0", "percent", "",
                "snapshot", 60, "high", 2,
                "Accelerate priority national onboarding and talent pipeline review.",
                "National representation is currently at {value}%, falling below the approved operating floor of {threshold}%.",
                1, "hr-ops@velora.ae", "ACTIVE", "2026-01-01T00:00:00Z", None, 1
            ),
            (
                "RULE-BUDGET-001", "velora-aviation", "REC-RULE-BUDGET-CONSUMPTION-EXHAUSTION", "1.0.0",
                "Budget Consumption Approaching Exhaustion", "BUDGET_CONSUMPTION", "1000",
                "RISK", "GT", "90.0", None, "85.0", "percent", "",
                "snapshot", 60, "moderate", 3,
                "Review uncommitted purchase orders and evaluate funds transfer reallocations.",
                "Departmental budget consumption reached {value}%, exceeding the 90% threshold for current fiscal period.",
                1, "finance-ops@velora.ae", "ACTIVE", "2026-01-01T00:00:00Z", None, 1
            ),
            (
                "RULE-AP-001", "velora-aviation", "REC-RULE-AP-PAYABLES-URGENT", "1.0.0",
                "Critical Supplier Obligations Due", "PAYABLES", "1000",
                "RISK", "GT", "5000000.00", None, "3000000.00", "currency", "AED",
                "snapshot", 60, "high", 1,
                "Prioritize working capital release and schedule critical supplier payments.",
                "Supplier payables due/overdue reached AED {value}, crossing the operational threshold of AED {threshold}.",
                1, "finance-ops@velora.ae", "ACTIVE", "2026-01-01T00:00:00Z", None, 1
            ),
        ]

        conn.executemany("""
            INSERT OR IGNORE INTO kpi_recommendation_rule (
                kpi_recommendation_rule_id, tenant_id, rule_code, rule_version,
                name, kpi, organization_scope, category, comparator,
                threshold, upper_threshold, clear_threshold, unit, currency,
                comparison_window, cooldown_minutes, severity, priority,
                recommendation_template, explanation_template, requires_complete,
                owner, state, effective_from, effective_to, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, baseline_rules)
        conn.commit()

    # --- Source Catalog ---
    def save_source_catalog(self, record: SourceCatalogRecord) -> SourceCatalogRecord:
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT version, tenant_id FROM source_catalog WHERE source_catalog_id = ?", (record.source_catalog_id,))
            row = cursor.fetchone()
            if row:
                if row["tenant_id"] != record.tenant_id:
                    raise AccessDeniedError("Cannot modify source catalog belonging to another tenant")
                if row["version"] != record.version:
                    raise ConcurrencyConflictError(f"SourceCatalog {record.source_catalog_id} was modified concurrently")
                conn.execute("""
                    UPDATE source_catalog
                    SET name=?, description=?, owner=?, environment=?, connection_alias=?,
                        permitted_tools=?, allowed_scope=?, refresh_expectation=?, sensitivity=?,
                        effective_from=?, effective_to=?, version=version+1
                    WHERE source_catalog_id=? AND version=?;
                """, (
                    record.name, record.description, record.owner, record.environment,
                    record.connection_alias, record.permitted_tools, record.allowed_scope,
                    record.refresh_expectation, record.sensitivity, record.effective_from,
                    record.effective_to, record.source_catalog_id, record.version
                ))
                record.version += 1
            else:
                conn.execute("""
                    INSERT INTO source_catalog (
                        source_catalog_id, tenant_id, name, description, owner, environment,
                        connection_alias, permitted_tools, allowed_scope, refresh_expectation,
                        sensitivity, effective_from, effective_to, version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
                """, (
                    record.source_catalog_id, record.tenant_id, record.name, record.description,
                    record.owner, record.environment, record.connection_alias, record.permitted_tools,
                    record.allowed_scope, record.refresh_expectation, record.sensitivity,
                    record.effective_from, record.effective_to
                ))
                record.version = 1
            return record
        finally:
            conn.close()

    def get_source_catalog(self, source_catalog_id: str, tenant_id: str) -> Optional[SourceCatalogRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM source_catalog WHERE source_catalog_id = ? AND tenant_id = ?", (source_catalog_id, tenant_id))
            row = cursor.fetchone()
            if not row:
                return None
            return SourceCatalogRecord(
                source_catalog_id=row["source_catalog_id"],
                tenant_id=row["tenant_id"],
                name=row["name"],
                description=row["description"],
                owner=row["owner"],
                environment=row["environment"],
                connection_alias=row["connection_alias"],
                permitted_tools=row["permitted_tools"],
                allowed_scope=row["allowed_scope"],
                refresh_expectation=row["refresh_expectation"],
                sensitivity=row["sensitivity"],
                effective_from=row["effective_from"],
                effective_to=row["effective_to"],
                version=row["version"],
            )
        finally:
            conn.close()

    def list_source_catalogs(self, tenant_id: str, limit: int = 50, offset: int = 0) -> List[SourceCatalogRecord]:
        limit = min(max(1, limit), 200)
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM source_catalog WHERE tenant_id = ? ORDER BY name ASC LIMIT ? OFFSET ?",
                (tenant_id, limit, offset)
            )
            return [
                SourceCatalogRecord(
                    source_catalog_id=row["source_catalog_id"],
                    tenant_id=row["tenant_id"],
                    name=row["name"],
                    description=row["description"],
                    owner=row["owner"],
                    environment=row["environment"],
                    connection_alias=row["connection_alias"],
                    permitted_tools=row["permitted_tools"],
                    allowed_scope=row["allowed_scope"],
                    refresh_expectation=row["refresh_expectation"],
                    sensitivity=row["sensitivity"],
                    effective_from=row["effective_from"],
                    effective_to=row["effective_to"],
                    version=row["version"],
                ) for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    # --- KPI Definitions ---
    def save_kpi_definition(self, record: KPIDefinitionRecord) -> KPIDefinitionRecord:
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT version, tenant_id FROM kpi_definition WHERE kpi_definition_id = ?", (record.kpi_definition_id,))
            row = cursor.fetchone()
            if row:
                if row["tenant_id"] != record.tenant_id:
                    raise AccessDeniedError("Cannot modify KPI definition belonging to another tenant")
                if row["version"] != record.version:
                    raise ConcurrencyConflictError("KPIDefinition was modified concurrently")
                conn.execute("""
                    UPDATE kpi_definition
                    SET kpi_code=?, name=?, business_definition=?, source_catalog_id=?,
                        calculation_code=?, unit=?, organization_scope=?, sign_convention=?,
                        freshness_max_minutes=?, version=version+1
                    WHERE kpi_definition_id=? AND version=?;
                """, (
                    record.kpi_code, record.name, record.business_definition, record.source_catalog_id,
                    record.calculation_code, record.unit, record.organization_scope, record.sign_convention,
                    record.freshness_max_minutes, record.kpi_definition_id, record.version
                ))
                record.version += 1
            else:
                conn.execute("""
                    INSERT INTO kpi_definition (
                        kpi_definition_id, tenant_id, kpi_code, name, business_definition,
                        source_catalog_id, calculation_code, unit, organization_scope,
                        sign_convention, freshness_max_minutes, version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
                """, (
                    record.kpi_definition_id, record.tenant_id, record.kpi_code, record.name,
                    record.business_definition, record.source_catalog_id, record.calculation_code,
                    record.unit, record.organization_scope, record.sign_convention,
                    record.freshness_max_minutes
                ))
                record.version = 1
            return record
        finally:
            conn.close()

    def get_kpi_definition(self, kpi_definition_id: str, tenant_id: str) -> Optional[KPIDefinitionRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM kpi_definition WHERE kpi_definition_id = ? AND tenant_id = ?", (kpi_definition_id, tenant_id))
            row = cursor.fetchone()
            if not row:
                return None
            return KPIDefinitionRecord(
                kpi_definition_id=row["kpi_definition_id"],
                tenant_id=row["tenant_id"],
                kpi_code=row["kpi_code"],
                name=row["name"],
                business_definition=row["business_definition"],
                source_catalog_id=row["source_catalog_id"],
                calculation_code=row["calculation_code"],
                unit=row["unit"],
                organization_scope=row["organization_scope"],
                sign_convention=row["sign_convention"],
                freshness_max_minutes=row["freshness_max_minutes"],
                version=row["version"],
            )
        finally:
            conn.close()

    def list_kpi_definitions(self, tenant_id: str, limit: int = 50, offset: int = 0) -> List[KPIDefinitionRecord]:
        limit = min(max(1, limit), 200)
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM kpi_definition WHERE tenant_id = ? ORDER BY kpi_code ASC LIMIT ? OFFSET ?",
                (tenant_id, limit, offset)
            )
            return [
                KPIDefinitionRecord(
                    kpi_definition_id=row["kpi_definition_id"],
                    tenant_id=row["tenant_id"],
                    kpi_code=row["kpi_code"],
                    name=row["name"],
                    business_definition=row["business_definition"],
                    source_catalog_id=row["source_catalog_id"],
                    calculation_code=row["calculation_code"],
                    unit=row["unit"],
                    organization_scope=row["organization_scope"],
                    sign_convention=row["sign_convention"],
                    freshness_max_minutes=row["freshness_max_minutes"],
                    version=row["version"],
                ) for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    # --- Institutional Records ---
    def save_institutional_record(self, record: InstitutionalRecordEntity) -> InstitutionalRecordEntity:
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT version, tenant_id FROM institutional_record WHERE institutional_record_id = ?", (record.institutional_record_id,))
            row = cursor.fetchone()
            if row:
                if row["tenant_id"] != record.tenant_id:
                    raise AccessDeniedError("Cannot modify institutional record belonging to another tenant")
                if row["version"] != record.version:
                    raise ConcurrencyConflictError("InstitutionalRecord was modified concurrently")
                conn.execute("""
                    UPDATE institutional_record
                    SET record_title=?, record_type=?, source_agent=?, executive_owner=?,
                        summary=?, key_decisions=?, action_items=?, retention_policy=?,
                        loop_component_id=?, notebook_location=?, version=version+1
                    WHERE institutional_record_id=? AND version=?;
                """, (
                    record.record_title, record.record_type, record.source_agent, record.executive_owner,
                    record.summary, record.key_decisions, record.action_items, record.retention_policy,
                    record.loop_component_id, record.notebook_location, record.institutional_record_id, record.version
                ))
                record.version += 1
            else:
                conn.execute("""
                    INSERT INTO institutional_record (
                        institutional_record_id, tenant_id, record_title, record_type, source_agent,
                        executive_owner, summary, key_decisions, action_items, retention_policy,
                        loop_component_id, notebook_location, created_on, version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
                """, (
                    record.institutional_record_id, record.tenant_id, record.record_title, record.record_type,
                    record.source_agent, record.executive_owner, record.summary, record.key_decisions,
                    record.action_items, record.retention_policy, record.loop_component_id,
                    record.notebook_location, record.created_on
                ))
                record.version = 1
            return record
        finally:
            conn.close()

    def get_institutional_record(self, record_id: str, tenant_id: str) -> Optional[InstitutionalRecordEntity]:
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM institutional_record WHERE institutional_record_id = ? AND tenant_id = ?", (record_id, tenant_id))
            row = cursor.fetchone()
            if not row:
                return None
            return InstitutionalRecordEntity(
                institutional_record_id=row["institutional_record_id"],
                tenant_id=row["tenant_id"],
                record_title=row["record_title"],
                record_type=row["record_type"],
                source_agent=row["source_agent"],
                executive_owner=row["executive_owner"],
                summary=row["summary"],
                key_decisions=row["key_decisions"],
                action_items=row["action_items"],
                retention_policy=row["retention_policy"],
                loop_component_id=row["loop_component_id"] or "",
                notebook_location=row["notebook_location"] or "",
                created_on=row["created_on"],
                version=row["version"],
            )
        finally:
            conn.close()

    def list_institutional_records(self, tenant_id: str, record_type: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[InstitutionalRecordEntity]:
        limit = min(max(1, limit), 200)
        conn = self._get_connection()
        try:
            if record_type:
                cursor = conn.execute(
                    "SELECT * FROM institutional_record WHERE tenant_id = ? AND record_type = ? ORDER BY created_on DESC LIMIT ? OFFSET ?",
                    (tenant_id, record_type, limit, offset)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM institutional_record WHERE tenant_id = ? ORDER BY created_on DESC LIMIT ? OFFSET ?",
                    (tenant_id, limit, offset)
                )
            return [
                InstitutionalRecordEntity(
                    institutional_record_id=row["institutional_record_id"],
                    tenant_id=row["tenant_id"],
                    record_title=row["record_title"],
                    record_type=row["record_type"],
                    source_agent=row["source_agent"],
                    executive_owner=row["executive_owner"],
                    summary=row["summary"],
                    key_decisions=row["key_decisions"],
                    action_items=row["action_items"],
                    retention_policy=row["retention_policy"],
                    loop_component_id=row["loop_component_id"] or "",
                    notebook_location=row["notebook_location"] or "",
                    created_on=row["created_on"],
                    version=row["version"],
                ) for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    # --- Decision Evidence ---
    def save_decision_evidence(self, record: DecisionEvidenceRecord) -> DecisionEvidenceRecord:
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT version, tenant_id FROM decision_evidence WHERE decision_evidence_id = ?", (record.decision_evidence_id,))
            row = cursor.fetchone()
            if row:
                if row["tenant_id"] != record.tenant_id:
                    raise AccessDeniedError("Cannot modify decision evidence belonging to another tenant")
                if row["version"] != record.version:
                    raise ConcurrencyConflictError("DecisionEvidence was modified concurrently")
                conn.execute("""
                    UPDATE decision_evidence
                    SET claim_id=?, decision_id=?, source_lookup=?, source_version=?,
                        input_snapshot=?, rationale=?, output_hash=?, verified_identity=?,
                        limitations=?, manifest_ref=?, version=version+1
                    WHERE decision_evidence_id=? AND version=?;
                """, (
                    record.claim_id, record.decision_id, record.source_lookup, record.source_version,
                    record.input_snapshot, record.rationale, record.output_hash, record.verified_identity,
                    record.limitations, record.manifest_ref, record.decision_evidence_id, record.version
                ))
                record.version += 1
            else:
                conn.execute("""
                    INSERT INTO decision_evidence (
                        decision_evidence_id, tenant_id, claim_id, decision_id, source_lookup,
                        source_version, input_snapshot, rationale, output_hash, verified_identity,
                        limitations, manifest_ref, created_at, version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
                """, (
                    record.decision_evidence_id, record.tenant_id, record.claim_id, record.decision_id,
                    record.source_lookup, record.source_version, record.input_snapshot, record.rationale,
                    record.output_hash, record.verified_identity, record.limitations, record.manifest_ref,
                    record.created_at
                ))
                record.version = 1
            return record
        finally:
            conn.close()

    def get_decision_evidence(self, decision_evidence_id: str, tenant_id: str) -> Optional[DecisionEvidenceRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM decision_evidence WHERE decision_evidence_id = ? AND tenant_id = ?", (decision_evidence_id, tenant_id))
            row = cursor.fetchone()
            if not row:
                return None
            return DecisionEvidenceRecord(
                decision_evidence_id=row["decision_evidence_id"],
                tenant_id=row["tenant_id"],
                claim_id=row["claim_id"],
                decision_id=row["decision_id"],
                source_lookup=row["source_lookup"],
                source_version=row["source_version"],
                input_snapshot=row["input_snapshot"],
                rationale=row["rationale"],
                output_hash=row["output_hash"],
                verified_identity=row["verified_identity"],
                limitations=row["limitations"],
                manifest_ref=row["manifest_ref"],
                created_at=row["created_at"],
                version=row["version"],
            )
        finally:
            conn.close()

    def list_decision_evidence(self, tenant_id: str, decision_id: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[DecisionEvidenceRecord]:
        limit = min(max(1, limit), 200)
        conn = self._get_connection()
        try:
            if decision_id:
                cursor = conn.execute(
                    "SELECT * FROM decision_evidence WHERE tenant_id = ? AND decision_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (tenant_id, decision_id, limit, offset)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM decision_evidence WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (tenant_id, limit, offset)
                )
            return [
                DecisionEvidenceRecord(
                    decision_evidence_id=row["decision_evidence_id"],
                    tenant_id=row["tenant_id"],
                    claim_id=row["claim_id"],
                    decision_id=row["decision_id"],
                    source_lookup=row["source_lookup"],
                    source_version=row["source_version"],
                    input_snapshot=row["input_snapshot"],
                    rationale=row["rationale"],
                    output_hash=row["output_hash"],
                    verified_identity=row["verified_identity"],
                    limitations=row["limitations"],
                    manifest_ref=row["manifest_ref"],
                    created_at=row["created_at"],
                    version=row["version"],
                ) for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    # --- Proposal Evaluations (Vendor Scorecards) ---
    def save_proposal_evaluation(self, record: ProposalEvaluationRecord) -> ProposalEvaluationRecord:
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT version, tenant_id FROM proposal_evaluation WHERE proposal_evaluation_id = ?", (record.proposal_evaluation_id,))
            row = cursor.fetchone()
            if row:
                if row["tenant_id"] != record.tenant_id:
                    raise AccessDeniedError("Cannot modify proposal evaluation belonging to another tenant")
                if row["version"] != record.version:
                    raise ConcurrencyConflictError("ProposalEvaluation was modified concurrently")
                conn.execute("""
                    UPDATE proposal_evaluation
                    SET proposal_title=?, proposal_id=?, submitter=?, requested_capital=?, currency=?,
                        payback_period_months=?, irr=?, npv=?, rubric_score=?, evaluation_status=?,
                        evaluationsummary=?, evaluated_by=?, evaluated_on=?, version=version+1
                    WHERE proposal_evaluation_id=? AND version=?;
                """, (
                    record.proposal_title, record.proposal_id, record.submitter, record.requested_capital,
                    record.currency, record.payback_period_months, record.irr, record.npv,
                    record.rubric_score, record.evaluation_status, record.evaluationsummary,
                    record.evaluated_by, record.evaluated_on, record.proposal_evaluation_id, record.version
                ))
                record.version += 1
            else:
                conn.execute("""
                    INSERT INTO proposal_evaluation (
                        proposal_evaluation_id, tenant_id, proposal_title, proposal_id, submitter,
                        requested_capital, currency, payback_period_months, irr, npv,
                        rubric_score, evaluation_status, evaluationsummary, evaluated_by,
                        evaluated_on, version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
                """, (
                    record.proposal_evaluation_id, record.tenant_id, record.proposal_title, record.proposal_id,
                    record.submitter, record.requested_capital, record.currency, record.payback_period_months,
                    record.irr, record.npv, record.rubric_score, record.evaluation_status,
                    record.evaluationsummary, record.evaluated_by, record.evaluated_on
                ))
                record.version = 1
            return record
        finally:
            conn.close()

    def get_proposal_evaluation(self, evaluation_id: str, tenant_id: str) -> Optional[ProposalEvaluationRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM proposal_evaluation WHERE proposal_evaluation_id = ? AND tenant_id = ?", (evaluation_id, tenant_id))
            row = cursor.fetchone()
            if not row:
                return None
            return ProposalEvaluationRecord(
                proposal_evaluation_id=row["proposal_evaluation_id"],
                tenant_id=row["tenant_id"],
                proposal_title=row["proposal_title"],
                proposal_id=row["proposal_id"],
                submitter=row["submitter"],
                requested_capital=row["requested_capital"],
                currency=row["currency"],
                payback_period_months=row["payback_period_months"],
                irr=row["irr"],
                npv=row["npv"],
                rubric_score=row["rubric_score"],
                evaluation_status=row["evaluation_status"],
                evaluationsummary=row["evaluationsummary"],
                evaluated_by=row["evaluated_by"],
                evaluated_on=row["evaluated_on"],
                version=row["version"],
            )
        finally:
            conn.close()

    def list_proposal_evaluations(self, tenant_id: str, limit: int = 50, offset: int = 0) -> List[ProposalEvaluationRecord]:
        limit = min(max(1, limit), 200)
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM proposal_evaluation WHERE tenant_id = ? ORDER BY evaluated_on DESC LIMIT ? OFFSET ?",
                (tenant_id, limit, offset)
            )
            return [
                ProposalEvaluationRecord(
                    proposal_evaluation_id=row["proposal_evaluation_id"],
                    tenant_id=row["tenant_id"],
                    proposal_title=row["proposal_title"],
                    proposal_id=row["proposal_id"],
                    submitter=row["submitter"],
                    requested_capital=row["requested_capital"],
                    currency=row["currency"],
                    payback_period_months=row["payback_period_months"],
                    irr=row["irr"],
                    npv=row["npv"],
                    rubric_score=row["rubric_score"],
                    evaluation_status=row["evaluation_status"],
                    evaluationsummary=row["evaluationsummary"],
                    evaluated_by=row["evaluated_by"],
                    evaluated_on=row["evaluated_on"],
                    version=row["version"],
                ) for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    def save_kpi_rule(self, record: KPIRuleRecord) -> KPIRuleRecord:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT version, tenant_id FROM kpi_recommendation_rule WHERE kpi_recommendation_rule_id = ?",
                (record.kpi_recommendation_rule_id,)
            )
            existing = cursor.fetchone()
            if existing:
                if existing["tenant_id"] != record.tenant_id:
                    raise AccessDeniedError(f"Cross-tenant mutation denied for rule {record.kpi_recommendation_rule_id}")
                if existing["version"] != record.version:
                    raise ConcurrencyConflictError(
                        f"Rule {record.kpi_recommendation_rule_id} version mismatch: expected {existing['version']}, got {record.version}"
                    )
                new_version = record.version + 1
                conn.execute("""
                    UPDATE kpi_recommendation_rule
                    SET name = ?, kpi = ?, organization_scope = ?, category = ?, comparator = ?,
                        threshold = ?, upper_threshold = ?, clear_threshold = ?, unit = ?, currency = ?,
                        comparison_window = ?, cooldown_minutes = ?, severity = ?, priority = ?,
                        recommendation_template = ?, explanation_template = ?, requires_complete = ?,
                        owner = ?, state = ?, effective_from = ?, effective_to = ?, version = ?
                    WHERE kpi_recommendation_rule_id = ? AND tenant_id = ?;
                """, (
                    record.name, record.kpi, record.organization_scope, record.category, record.comparator,
                    str(record.threshold), str(record.upper_threshold) if record.upper_threshold is not None else None,
                    str(record.clear_threshold) if record.clear_threshold is not None else None, record.unit, record.currency,
                    record.comparison_window, record.cooldown_minutes, record.severity, record.priority,
                    record.recommendation_template, record.explanation_template, 1 if record.requires_complete else 0,
                    record.owner, record.state, record.effective_from, record.effective_to, new_version,
                    record.kpi_recommendation_rule_id, record.tenant_id
                ))
                record.version = new_version
            else:
                conn.execute("""
                    INSERT INTO kpi_recommendation_rule (
                        kpi_recommendation_rule_id, tenant_id, rule_code, rule_version, name, kpi,
                        organization_scope, category, comparator, threshold, upper_threshold, clear_threshold,
                        unit, currency, comparison_window, cooldown_minutes, severity, priority,
                        recommendation_template, explanation_template, requires_complete, owner, state,
                        effective_from, effective_to, version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    record.kpi_recommendation_rule_id, record.tenant_id, record.rule_code, record.rule_version,
                    record.name, record.kpi, record.organization_scope, record.category, record.comparator,
                    str(record.threshold), str(record.upper_threshold) if record.upper_threshold is not None else None,
                    str(record.clear_threshold) if record.clear_threshold is not None else None, record.unit, record.currency,
                    record.comparison_window, record.cooldown_minutes, record.severity, record.priority,
                    record.recommendation_template, record.explanation_template, 1 if record.requires_complete else 0,
                    record.owner, record.state, record.effective_from, record.effective_to, record.version
                ))
            return record
        finally:
            conn.close()

    def get_kpi_rule(self, rule_id: str, tenant_id: str) -> Optional[KPIRuleRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM kpi_recommendation_rule WHERE kpi_recommendation_rule_id = ? AND tenant_id = ?",
                (rule_id, tenant_id)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return KPIRuleRecord(
                kpi_recommendation_rule_id=row["kpi_recommendation_rule_id"],
                tenant_id=row["tenant_id"],
                rule_code=row["rule_code"],
                rule_version=row["rule_version"],
                name=row["name"],
                kpi=row["kpi"],
                organization_scope=row["organization_scope"],
                category=row["category"],
                comparator=row["comparator"],
                threshold=Decimal(str(row["threshold"])),
                upper_threshold=Decimal(str(row["upper_threshold"])) if row["upper_threshold"] else None,
                clear_threshold=Decimal(str(row["clear_threshold"])) if row["clear_threshold"] else None,
                unit=row["unit"],
                currency=row["currency"],
                comparison_window=row["comparison_window"],
                cooldown_minutes=row["cooldown_minutes"],
                severity=row["severity"],
                priority=row["priority"],
                recommendation_template=row["recommendation_template"],
                explanation_template=row["explanation_template"],
                requires_complete=bool(row["requires_complete"]),
                owner=row["owner"],
                state=row["state"],
                effective_from=row["effective_from"],
                effective_to=row["effective_to"],
                version=row["version"],
            )
        finally:
            conn.close()

    def get_kpi_rule_by_code(self, rule_code: str, tenant_id: str) -> Optional[KPIRuleRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM kpi_recommendation_rule WHERE rule_code = ? AND tenant_id = ?",
                (rule_code, tenant_id)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self.get_kpi_rule(row["kpi_recommendation_rule_id"], tenant_id)
        finally:
            conn.close()

    def list_active_rules(self, tenant_id: str) -> List[KPIRuleRecord]:
        """List active/approved recommendation rules for tenant (W08 requirement 1)."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM kpi_recommendation_rule WHERE tenant_id = ? AND UPPER(state) IN ('ACTIVE', 'APPROVED')",
                (tenant_id,)
            )
            rows = cursor.fetchall()
            results = []
            for row in rows:
                rec = KPIRuleRecord(
                    kpi_recommendation_rule_id=row["kpi_recommendation_rule_id"],
                    tenant_id=row["tenant_id"],
                    rule_code=row["rule_code"],
                    rule_version=row["rule_version"],
                    name=row["name"],
                    kpi=row["kpi"],
                    organization_scope=row["organization_scope"],
                    category=row["category"],
                    comparator=row["comparator"],
                    threshold=Decimal(row["threshold"]),
                    upper_threshold=Decimal(row["upper_threshold"]) if row["upper_threshold"] else None,
                    clear_threshold=Decimal(row["clear_threshold"]) if row["clear_threshold"] else None,
                    unit=row["unit"],
                    currency=row["currency"],
                    comparison_window=row["comparison_window"],
                    cooldown_minutes=int(row["cooldown_minutes"]),
                    severity=row["severity"],
                    priority=int(row["priority"]),
                    recommendation_template=row["recommendation_template"] or "",
                    explanation_template=row["explanation_template"] or "",
                    requires_complete=bool(row["requires_complete"]),
                    owner=row["owner"] or "Finance Operations",
                    state=row["state"],
                    effective_from=row["effective_from"],
                    effective_to=row["effective_to"],
                    version=int(row["version"]),
                )
                results.append(rec)
            return results
        finally:
            conn.close()

    def save_kpi_snapshot(self, record: KPISnapshotRecord) -> KPISnapshotRecord:
        conn = self._get_connection()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO kpi_snapshot (
                    kpi_snapshot_id, tenant_id, snapshot_id, kpi_code, organization_scope,
                    period, metric_value, unit, currency, source_updated_time, retrieved_at,
                    completeness, evidence_ref, input_hash, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                record.kpi_snapshot_id, record.tenant_id, record.snapshot_id, record.kpi_code,
                record.organization_scope, record.period, str(record.metric_value), record.unit,
                record.currency, record.source_updated_time, record.retrieved_at, record.completeness,
                record.evidence_ref, record.input_hash, record.version
            ))
            return record
        finally:
            conn.close()

    def get_kpi_snapshot(self, snapshot_id: str, tenant_id: str) -> Optional[KPISnapshotRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM kpi_snapshot WHERE (kpi_snapshot_id = ? OR snapshot_id = ?) AND tenant_id = ?",
                (snapshot_id, snapshot_id, tenant_id)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return KPISnapshotRecord(
                kpi_snapshot_id=row["kpi_snapshot_id"],
                tenant_id=row["tenant_id"],
                snapshot_id=row["snapshot_id"],
                kpi_code=row["kpi_code"],
                organization_scope=row["organization_scope"],
                period=row["period"],
                metric_value=Decimal(str(row["metric_value"])),
                unit=row["unit"],
                currency=row["currency"],
                source_updated_time=row["source_updated_time"],
                retrieved_at=row["retrieved_at"],
                completeness=row["completeness"],
                evidence_ref=row["evidence_ref"],
                input_hash=row["input_hash"],
                version=row["version"],
            )
        finally:
            conn.close()

    def save_recommendation(self, record: RecommendationEntityRecord) -> RecommendationEntityRecord:
        conn = self._get_connection()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO recommendations (
                    recommendation_id, tenant_id, rec_id, duplicate_key, rule_code, rule_version, kpi_code,
                    organization_scope, category, observed_value, threshold,
                    impact, explanation, suggested_action, confidence,
                    confidence_reason, first_detected, last_detected,
                    status, snapshot_id, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                record.recommendation_id, record.tenant_id, record.rec_id, record.duplicate_key, record.rule_code, record.rule_version,
                record.kpi_code, record.organization_scope, record.category, str(record.observed_value),
                str(record.threshold), record.impact, record.explanation, record.suggested_action,
                record.confidence, record.confidence_reason, record.first_detected, record.last_detected,
                record.status, record.snapshot_id, record.version
            ))
            conn.commit()
            return record
        finally:
            conn.close()


    def get_recommendation(self, rec_id: str, tenant_id: str) -> Optional[RecommendationEntityRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM recommendations WHERE (rec_id = ? OR recommendation_id = ?) AND tenant_id = ?",
                (rec_id, rec_id, tenant_id)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return RecommendationEntityRecord(
                recommendation_id=row["rec_id"],
                tenant_id=row["tenant_id"],
                rec_id=row["rec_id"],
                rule_code=row["rule_code"],
                rule_version=row["rule_version"],
                kpi_code=row["kpi_code"],
                organization_scope=row["organization_scope"],
                category=row["category"],
                observed_value=Decimal(str(row["observed_value"])),
                threshold=Decimal(str(row["threshold"])),
                impact=row["impact"],
                explanation=row["explanation"],
                suggested_action=row["suggested_action"],
                confidence=row["confidence"],
                confidence_reason=row["confidence_reason"],
                first_detected=row["first_detected"],
                last_detected=row["last_detected"],
                status=row["status"],
                duplicate_key=row["duplicate_key"],
                snapshot_id=row["snapshot_id"],
                version=row["version"],
            )
        finally:
            conn.close()

    def get_recommendation_any_tenant(self, rec_id: str) -> Optional[RecommendationEntityRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM recommendations WHERE (rec_id = ? OR recommendation_id = ?)",
                (rec_id, rec_id)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return RecommendationEntityRecord(
                recommendation_id=row["rec_id"],
                tenant_id=row["tenant_id"],
                rec_id=row["rec_id"],
                rule_code=row["rule_code"],
                rule_version=row["rule_version"],
                kpi_code=row["kpi_code"],
                organization_scope=row["organization_scope"],
                category=row["category"],
                observed_value=Decimal(str(row["observed_value"])),
                threshold=Decimal(str(row["threshold"])),
                impact=row["impact"],
                explanation=row["explanation"],
                suggested_action=row["suggested_action"],
                confidence=row["confidence"],
                confidence_reason=row["confidence_reason"],
                first_detected=row["first_detected"],
                last_detected=row["last_detected"],
                status=row["status"],
                duplicate_key=row["duplicate_key"],
                snapshot_id=row["snapshot_id"],
                version=row["version"],
            )
        finally:
            conn.close()

    def save_recommendation_feedback(self, record: RecommendationFeedbackRecord) -> RecommendationFeedbackRecord:
        conn = self._get_connection()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO recommendation_feedback (
                    recommendation_feedback_id, tenant_id, feedback_id, recommendation_id,
                    reviewer, is_useful, feedback_type, comment, recorded_at, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                record.recommendation_feedback_id, record.tenant_id, record.feedback_id,
                record.recommendation_id, record.reviewer, 1 if record.is_useful else 0,
                record.feedback_type, record.comment, record.recorded_at, record.version
            ))
            conn.commit()
            return record
        finally:
            conn.close()

    def get_recommendation_feedback(self, feedback_id: str, tenant_id: str) -> Optional[RecommendationFeedbackRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM recommendation_feedback WHERE (feedback_id = ? OR recommendation_feedback_id = ?) AND tenant_id = ?",
                (feedback_id, feedback_id, tenant_id)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return RecommendationFeedbackRecord(
                recommendation_feedback_id=row["recommendation_feedback_id"],
                tenant_id=row["tenant_id"],
                feedback_id=row["feedback_id"],
                recommendation_id=row["recommendation_id"],
                reviewer=row["reviewer"],
                is_useful=bool(row["is_useful"]),
                feedback_type=row["feedback_type"],
                comment=row["comment"],
                recorded_at=row["recorded_at"],
                version=row["version"],
            )
        finally:
            conn.close()

    def list_feedback_for_recommendation(self, recommendation_id: str, tenant_id: str) -> List[RecommendationFeedbackRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM recommendation_feedback WHERE recommendation_id = ? AND tenant_id = ? ORDER BY recorded_at DESC",
                (recommendation_id, tenant_id)
            )
            return [
                RecommendationFeedbackRecord(
                    recommendation_feedback_id=row["recommendation_feedback_id"],
                    tenant_id=row["tenant_id"],
                    feedback_id=row["feedback_id"],
                    recommendation_id=row["recommendation_id"],
                    reviewer=row["reviewer"],
                    is_useful=bool(row["is_useful"]),
                    feedback_type=row["feedback_type"],
                    comment=row["comment"],
                    recorded_at=row["recorded_at"],
                    version=row["version"],
                ) for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    def get_feedback_summary_by_rule(self, rule_code: str, tenant_id: str) -> Dict[str, Any]:
        conn = self._get_connection()
        try:
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total_feedback,
                    SUM(CASE WHEN rf.is_useful = 1 THEN 1 ELSE 0 END) as useful_count,
                    SUM(CASE WHEN rf.is_useful = 0 THEN 1 ELSE 0 END) as not_useful_count
                FROM recommendation_feedback rf
                JOIN recommendations r ON rf.recommendation_id = r.recommendation_id AND rf.tenant_id = r.tenant_id
                WHERE r.rule_code = ? AND rf.tenant_id = ?
            """, (rule_code, tenant_id))
            row = cursor.fetchone()
            total = row["total_feedback"] if row and row["total_feedback"] else 0
            useful = row["useful_count"] if row and row["useful_count"] else 0
            not_useful = row["not_useful_count"] if row and row["not_useful_count"] else 0

            cur_types = conn.execute("""
                SELECT rf.feedback_type, COUNT(*) as cnt
                FROM recommendation_feedback rf
                JOIN recommendations r ON rf.recommendation_id = r.recommendation_id AND rf.tenant_id = r.tenant_id
                WHERE r.rule_code = ? AND rf.tenant_id = ?
                GROUP BY rf.feedback_type
            """, (rule_code, tenant_id))
            type_breakdown = {t_row["feedback_type"]: t_row["cnt"] for t_row in cur_types.fetchall()}

            return {
                "rule_code": rule_code,
                "tenant_id": tenant_id,
                "total_feedback": total,
                "useful_count": useful,
                "not_useful_count": not_useful,
                "useful_ratio": round(useful / total, 4) if total > 0 else 0.0,
                "feedback_type_breakdown": type_breakdown,
            }
        finally:
            conn.close()


    def save_peer_benchmark(self, record: PeerBenchmarkRecord) -> PeerBenchmarkRecord:
        conn = self._get_connection()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO peer_benchmark (
                    peer_benchmark_id, tenant_id, benchmark_name, metric_code, cohort_name,
                    internal_value, peer_median, peer_top_quartile, peer_bottom_quartile,
                    unit, variance_status, datasource, benchmark_date, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                record.peer_benchmark_id, record.tenant_id, record.benchmark_name, record.metric_code,
                record.cohort_name, record.internal_value, record.peer_median, record.peer_top_quartile,
                record.peer_bottom_quartile, record.unit, record.variance_status, record.datasource,
                record.benchmark_date, record.version
            ))
            return record
        finally:
            conn.close()

    def get_peer_benchmark(self, benchmark_id: str, tenant_id: str) -> Optional[PeerBenchmarkRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM peer_benchmark WHERE peer_benchmark_id = ? AND tenant_id = ?",
                (benchmark_id, tenant_id)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return PeerBenchmarkRecord(
                peer_benchmark_id=row["peer_benchmark_id"],
                tenant_id=row["tenant_id"],
                benchmark_name=row["benchmark_name"],
                metric_code=row["metric_code"],
                cohort_name=row["cohort_name"],
                internal_value=row["internal_value"],
                peer_median=row["peer_median"],
                peer_top_quartile=row["peer_top_quartile"],
                peer_bottom_quartile=row["peer_bottom_quartile"],
                unit=row["unit"],
                variance_status=row["variance_status"],
                datasource=row["datasource"],
                benchmark_date=row["benchmark_date"],
                version=row["version"],
            )
        finally:
            conn.close()

    def save_vendor_performance_history(self, record: VendorPerformanceHistoryRecord) -> VendorPerformanceHistoryRecord:
        conn = self._get_connection()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO vendor_performance_history (
                    record_id, tenant_id, vendor_id, vendor_name, entity_scope, contract_ref,
                    period_start, period_end, event_type, severity, numeric_value, unit, currency,
                    summary, details, source_doc_ref, source_hash, source_system, recorded_by,
                    verification_status, access_scope, retention_policy, legal_hold,
                    original_event_date, ingested_at, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                record.record_id, record.tenant_id, record.vendor_id, record.vendor_name, record.entity_scope,
                record.contract_ref, record.period_start, record.period_end, record.event_type, record.severity,
                str(record.numeric_value) if record.numeric_value is not None else None,
                record.unit, record.currency, record.summary, record.details, record.source_doc_ref,
                record.source_hash, record.source_system, record.recorded_by, record.verification_status,
                record.access_scope, record.retention_policy, 1 if record.legal_hold else 0,
                record.original_event_date, record.ingested_at, record.version
            ))
            conn.commit()
            return record
        finally:
            conn.close()

    def get_vendor_performance_history(self, record_id: str, tenant_id: str) -> Optional[VendorPerformanceHistoryRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM vendor_performance_history WHERE record_id = ? AND tenant_id = ?",
                (record_id, tenant_id)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_vendor_history(row)
        finally:
            conn.close()

    def find_vendor_history_by_source_hash(self, source_hash: str, tenant_id: str) -> Optional[VendorPerformanceHistoryRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM vendor_performance_history WHERE source_hash = ? AND tenant_id = ?",
                (source_hash, tenant_id)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_vendor_history(row)
        finally:
            conn.close()

    def list_vendor_history(self, vendor_id: str, tenant_id: str, entity_scope: Optional[str] = None) -> List[VendorPerformanceHistoryRecord]:
        conn = self._get_connection()
        try:
            if entity_scope:
                cursor = conn.execute(
                    "SELECT * FROM vendor_performance_history WHERE vendor_id = ? AND tenant_id = ? AND entity_scope = ? ORDER BY original_event_date DESC",
                    (vendor_id, tenant_id, entity_scope)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM vendor_performance_history WHERE vendor_id = ? AND tenant_id = ? ORDER BY original_event_date DESC",
                    (vendor_id, tenant_id)
                )
            return [self._row_to_vendor_history(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def _row_to_vendor_history(self, row: sqlite3.Row) -> VendorPerformanceHistoryRecord:
        num_val = Decimal(str(row["numeric_value"])) if row["numeric_value"] is not None else None
        return VendorPerformanceHistoryRecord(
            record_id=row["record_id"],
            tenant_id=row["tenant_id"],
            vendor_id=row["vendor_id"],
            vendor_name=row["vendor_name"],
            entity_scope=row["entity_scope"],
            contract_ref=row["contract_ref"],
            period_start=row["period_start"],
            period_end=row["period_end"],
            event_type=row["event_type"],
            severity=row["severity"],
            numeric_value=num_val,
            unit=row["unit"],
            currency=row["currency"],
            summary=row["summary"],
            details=row["details"] or "",
            source_doc_ref=row["source_doc_ref"],
            source_hash=row["source_hash"],
            source_system=row["source_system"],
            recorded_by=row["recorded_by"],
            verification_status=row["verification_status"],
            access_scope=row["access_scope"],
            retention_policy=row["retention_policy"],
            legal_hold=bool(row["legal_hold"]),
            original_event_date=row["original_event_date"],
            ingested_at=row["ingested_at"],
            version=row["version"],
        )

    # --- Vendor Decision Records (W11 & W12) ---
    def save_vendor_decision(self, record: VendorDecisionRecord, caller_role: str = "velora-app-service") -> VendorDecisionRecord:
        conn = self._get_connection()
        try:
            cur = conn.execute(
                "SELECT audit_manifest_ref FROM vendor_decision_record WHERE tenant_id = ? AND decision_id = ? AND version = ?",
                (record.tenant_id, record.decision_id, record.version)
            )
            existing = cur.fetchone()
            if existing:
                # If finalized, reject update by application roles
                if existing["audit_manifest_ref"] and "FINALIZED" in existing["audit_manifest_ref"] and caller_role != "RECORDS_ADMIN_OVERRIDE":
                    raise FinalizedEvidenceMutationError(
                        f"Application role '{caller_role}' is denied UPDATE privilege on finalized decision evidence "
                        f"'{record.decision_id}' v{record.version}. Finalized records are append-only under ADAA immutability policy."
                    )
                conn.execute("""
                    UPDATE vendor_decision_record
                    SET use_case = ?, evaluated_options_json = ?, criteria_weights_json = ?,
                        input_snapshot_ids_json = ?, baseline_score_json = ?, memory_contributions_json = ?,
                        final_score_json = ?, final_rank_json = ?, tie_policy = ?, missing_data_policy = ?,
                        selected_option = ?, claims_json = ?, concise_rationale = ?, policy_id = ?,
                        policy_version = ?, code_version = ?, authenticated_actor_json = ?,
                        audit_manifest_ref = ?, updated_at = ?
                    WHERE tenant_id = ? AND decision_id = ? AND version = ?
                """, (
                    record.use_case, record.evaluated_options_json, record.criteria_weights_json,
                    record.input_snapshot_ids_json, record.baseline_score_json, record.memory_contributions_json,
                    record.final_score_json, record.final_rank_json, record.tie_policy, record.missing_data_policy,
                    record.selected_option, record.claims_json, record.concise_rationale, record.policy_id,
                    record.policy_version, record.code_version, record.authenticated_actor_json,
                    record.audit_manifest_ref, record.updated_at,
                    record.tenant_id, record.decision_id, record.version
                ))
            else:
                conn.execute("""
                    INSERT INTO vendor_decision_record (
                        decision_id, version, tenant_id, use_case, evaluated_options_json,
                        criteria_weights_json, input_snapshot_ids_json, baseline_score_json,
                        memory_contributions_json, final_score_json, final_rank_json, tie_policy,
                        missing_data_policy, selected_option, claims_json, concise_rationale,
                        policy_id, policy_version, code_version, authenticated_actor_json,
                        audit_manifest_ref, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record.decision_id, record.version, record.tenant_id, record.use_case,
                    record.evaluated_options_json, record.criteria_weights_json, record.input_snapshot_ids_json,
                    record.baseline_score_json, record.memory_contributions_json, record.final_score_json,
                    record.final_rank_json, record.tie_policy, record.missing_data_policy,
                    record.selected_option, record.claims_json, record.concise_rationale,
                    record.policy_id, record.policy_version, record.code_version,
                    record.authenticated_actor_json, record.audit_manifest_ref,
                    record.created_at, record.updated_at
                ))
            return record
        finally:
            conn.close()

    def update_vendor_decision_audit_manifest(self, decision_id: str, tenant_id: str, version: str, audit_manifest_ref: str) -> None:
        conn = self._get_connection()
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE vendor_decision_record SET audit_manifest_ref = ?, updated_at = ? WHERE tenant_id = ? AND decision_id = ? AND version = ?",
                (audit_manifest_ref, now_iso, tenant_id, decision_id, version)
            )
        finally:
            conn.close()

    def delete_vendor_decision(self, decision_id: str, tenant_id: str, version: Optional[str] = None, caller_role: str = "velora-app-service") -> bool:
        conn = self._get_connection()
        try:
            sql = "SELECT version, audit_manifest_ref FROM vendor_decision_record WHERE tenant_id = ? AND decision_id = ?"
            params = [tenant_id, decision_id]
            if version:
                sql += " AND version = ?"
                params.append(version)
            cur = conn.execute(sql, tuple(params))
            row = cur.fetchone()
            if not row:
                return False

            # Strict ADAA retention enforcement:
            # Finalized records and requests from application service roles are strictly blocked from DELETE.
            is_finalized = bool(row["audit_manifest_ref"] and "FINALIZED" in row["audit_manifest_ref"])
            is_app_role = caller_role in ("velora-app-service", "Standard_User", "ApplicationService", "WorkerService")
            if is_finalized or is_app_role:
                raise FinalizedEvidenceMutationError(
                    f"Application role '{caller_role}' is denied DELETE privilege on finalized decision evidence "
                    f"'{decision_id}' v{row['version']}. Finalized records are append-only under ADAA immutability policy."
                )

            del_sql = "DELETE FROM vendor_decision_record WHERE tenant_id = ? AND decision_id = ?"
            del_params = [tenant_id, decision_id]
            if version:
                del_sql += " AND version = ?"
                del_params.append(version)
            conn.execute(del_sql, tuple(del_params))
            return True
        finally:
            conn.close()

    def get_vendor_decision(self, decision_id: str, tenant_id: str, version: Optional[str] = None) -> Optional[VendorDecisionRecord]:
        conn = self._get_connection()
        try:
            if version:
                cursor = conn.execute(
                    "SELECT * FROM vendor_decision_record WHERE tenant_id = ? AND decision_id = ? AND version = ?",
                    (tenant_id, decision_id, version)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM vendor_decision_record WHERE tenant_id = ? AND decision_id = ? ORDER BY created_at DESC LIMIT 1",
                    (tenant_id, decision_id)
                )
            row = cursor.fetchone()
            return self._row_to_vendor_decision(row) if row else None
        finally:
            conn.close()

    def list_vendor_decisions(self, tenant_id: str, use_case: Optional[str] = None, limit: int = 50) -> List[VendorDecisionRecord]:
        conn = self._get_connection()
        try:
            if use_case:
                cursor = conn.execute(
                    "SELECT * FROM vendor_decision_record WHERE tenant_id = ? AND use_case = ? ORDER BY created_at DESC LIMIT ?",
                    (tenant_id, use_case, limit)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM vendor_decision_record WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?",
                    (tenant_id, limit)
                )
            return [self._row_to_vendor_decision(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def _row_to_vendor_decision(self, row: sqlite3.Row) -> VendorDecisionRecord:
        return VendorDecisionRecord(
            decision_id=row["decision_id"],
            version=row["version"],
            tenant_id=row["tenant_id"],
            use_case=row["use_case"],
            evaluated_options_json=row["evaluated_options_json"],
            criteria_weights_json=row["criteria_weights_json"],
            input_snapshot_ids_json=row["input_snapshot_ids_json"],
            baseline_score_json=row["baseline_score_json"],
            memory_contributions_json=row["memory_contributions_json"],
            final_score_json=row["final_score_json"],
            final_rank_json=row["final_rank_json"],
            tie_policy=row["tie_policy"],
            missing_data_policy=row["missing_data_policy"],
            selected_option=row["selected_option"],
            claims_json=row["claims_json"],
            concise_rationale=row["concise_rationale"],
            policy_id=row["policy_id"],
            policy_version=row["policy_version"],
            code_version=row["code_version"],
            authenticated_actor_json=row["authenticated_actor_json"],
            audit_manifest_ref=row["audit_manifest_ref"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def save_meeting_action_mapping(self, record: MeetingActionMappingRecord) -> MeetingActionMappingRecord:
        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT INTO meeting_action_mapping (
                    mapping_id, tenant_id, meeting_id, source_version, extracted_action_id,
                    planner_task_id, plan_id, bucket_id, title, owner_user_id, owner_email,
                    due_date, status, percent_complete, originating_decision, source_citation,
                    evidence_id, audit_id, created_at, updated_at, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mapping_id) DO UPDATE SET
                    planner_task_id=excluded.planner_task_id,
                    plan_id=excluded.plan_id,
                    bucket_id=excluded.bucket_id,
                    title=excluded.title,
                    owner_user_id=excluded.owner_user_id,
                    owner_email=excluded.owner_email,
                    due_date=excluded.due_date,
                    status=excluded.status,
                    percent_complete=excluded.percent_complete,
                    originating_decision=excluded.originating_decision,
                    source_citation=excluded.source_citation,
                    evidence_id=excluded.evidence_id,
                    audit_id=excluded.audit_id,
                    updated_at=excluded.updated_at,
                    version=meeting_action_mapping.version + 1
                """,
                (
                    record.mapping_id, record.tenant_id, record.meeting_id, record.source_version,
                    record.extracted_action_id, record.planner_task_id, record.plan_id, record.bucket_id,
                    record.title, record.owner_user_id, record.owner_email, record.due_date,
                    record.status, record.percent_complete, record.originating_decision,
                    record.source_citation, record.evidence_id, record.audit_id,
                    record.created_at, record.updated_at, record.version,
                )
            )
            return record
        finally:
            conn.close()

    def get_meeting_action_mapping(self, tenant_id: str, mapping_id: str) -> Optional[MeetingActionMappingRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM meeting_action_mapping WHERE tenant_id = ? AND mapping_id = ?",
                (tenant_id, mapping_id)
            )
            row = cursor.fetchone()
            return self._row_to_meeting_action_mapping(row) if row else None
        finally:
            conn.close()

    def find_meeting_action_by_task(self, tenant_id: str, planner_task_id: str) -> Optional[MeetingActionMappingRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM meeting_action_mapping WHERE tenant_id = ? AND planner_task_id = ?",
                (tenant_id, planner_task_id)
            )
            row = cursor.fetchone()
            return self._row_to_meeting_action_mapping(row) if row else None
        finally:
            conn.close()

    def find_meeting_action_by_extracted(self, tenant_id: str, meeting_id: str, source_version: str, extracted_action_id: str) -> Optional[MeetingActionMappingRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM meeting_action_mapping WHERE tenant_id = ? AND meeting_id = ? AND source_version = ? AND extracted_action_id = ?",
                (tenant_id, meeting_id, source_version, extracted_action_id)
            )
            row = cursor.fetchone()
            return self._row_to_meeting_action_mapping(row) if row else None
        finally:
            conn.close()

    def list_meeting_action_mappings(self, tenant_id: str = "velora-aviation", meeting_id: Optional[str] = None, source_version: Optional[str] = None) -> List[MeetingActionMappingRecord]:
        conn = self._get_connection()
        try:
            if meeting_id and source_version:
                cursor = conn.execute(
                    "SELECT * FROM meeting_action_mapping WHERE tenant_id = ? AND meeting_id = ? AND source_version = ? ORDER BY created_at ASC",
                    (tenant_id, meeting_id, source_version)
                )
            elif meeting_id:
                cursor = conn.execute(
                    "SELECT * FROM meeting_action_mapping WHERE tenant_id = ? AND meeting_id = ? ORDER BY created_at ASC",
                    (tenant_id, meeting_id)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM meeting_action_mapping WHERE tenant_id = ? ORDER BY created_at ASC",
                    (tenant_id,)
                )
            return [self._row_to_meeting_action_mapping(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def update_meeting_action_status(
        self,
        tenant_id: str,
        planner_task_id: str,
        status: str,
        percent_complete: int,
        due_date: Optional[str] = None,
        owner_email: Optional[str] = None,
    ) -> bool:
        conn = self._get_connection()
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            if due_date is not None and owner_email is not None:
                cur = conn.execute(
                    """
                    UPDATE meeting_action_mapping
                    SET status = ?, percent_complete = ?, due_date = ?, owner_email = ?, updated_at = ?, version = version + 1
                    WHERE tenant_id = ? AND planner_task_id = ?
                    """,
                    (status, percent_complete, due_date, owner_email, now_iso, tenant_id, planner_task_id)
                )
            elif due_date is not None:
                cur = conn.execute(
                    """
                    UPDATE meeting_action_mapping
                    SET status = ?, percent_complete = ?, due_date = ?, updated_at = ?, version = version + 1
                    WHERE tenant_id = ? AND planner_task_id = ?
                    """,
                    (status, percent_complete, due_date, now_iso, tenant_id, planner_task_id)
                )
            elif owner_email is not None:
                cur = conn.execute(
                    """
                    UPDATE meeting_action_mapping
                    SET status = ?, percent_complete = ?, owner_email = ?, updated_at = ?, version = version + 1
                    WHERE tenant_id = ? AND planner_task_id = ?
                    """,
                    (status, percent_complete, owner_email, now_iso, tenant_id, planner_task_id)
                )
            else:
                cur = conn.execute(
                    """
                    UPDATE meeting_action_mapping
                    SET status = ?, percent_complete = ?, updated_at = ?, version = version + 1
                    WHERE tenant_id = ? AND planner_task_id = ?
                    """,
                    (status, percent_complete, now_iso, tenant_id, planner_task_id)
                )
            return cur.rowcount > 0
        finally:
            conn.close()

    def _row_to_meeting_action_mapping(self, row: sqlite3.Row) -> MeetingActionMappingRecord:
        return MeetingActionMappingRecord(
            mapping_id=row["mapping_id"],
            tenant_id=row["tenant_id"],
            meeting_id=row["meeting_id"],
            source_version=row["source_version"],
            extracted_action_id=row["extracted_action_id"],
            planner_task_id=row["planner_task_id"],
            plan_id=row["plan_id"],
            bucket_id=row["bucket_id"],
            title=row["title"],
            owner_user_id=row["owner_user_id"],
            owner_email=row["owner_email"],
            due_date=row["due_date"],
            status=row["status"],
            percent_complete=row["percent_complete"],
            originating_decision=row["originating_decision"],
            source_citation=row["source_citation"],
            evidence_id=row["evidence_id"],
            audit_id=row["audit_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            version=row["version"],
        )

    def clear_all_for_testing(self) -> None:
        conn = self._get_connection()
        try:
            conn.execute("DELETE FROM source_catalog;")
            conn.execute("DELETE FROM kpi_definition;")
            conn.execute("DELETE FROM kpi_recommendation_rule;")
            conn.execute("DELETE FROM kpi_snapshot;")
            conn.execute("DELETE FROM recommendations;")
            conn.execute("DELETE FROM recommendation_feedback;")
            conn.execute("DELETE FROM institutional_record;")
            conn.execute("DELETE FROM decision_evidence;")
            conn.execute("DELETE FROM peer_benchmark;")
            conn.execute("DELETE FROM proposal_evaluation;")
            conn.execute("DELETE FROM vendor_performance_history;")
            conn.execute("DELETE FROM vendor_decision_record;")
            conn.execute("DELETE FROM meeting_action_mapping;")
        finally:
            conn.close()


# --- Typed Repository Facades ---

class SourceCatalogRepository:
    def __init__(self, db_path: Optional[str] = None):
        self._repo = SqliteBusinessRepository(db_path=db_path)

    def create_catalog_entry(self, name: str, description: str, owner: str, tenant_id: str = "", **kwargs) -> str:
        cat_id = kwargs.get("source_catalog_id") or f"CAT-{int(time.time() * 1000)}"
        rec = SourceCatalogRecord(
            source_catalog_id=cat_id,
            tenant_id=tenant_id,
            name=name,
            description=description,
            owner=owner,
            environment=kwargs.get("environment", "Production"),
            connection_alias=kwargs.get("connection_alias", ""),
            permitted_tools=kwargs.get("permitted_tools", ""),
            allowed_scope=kwargs.get("allowed_scope", ""),
            refresh_expectation=kwargs.get("refresh_expectation", "Daily"),
            sensitivity=kwargs.get("sensitivity", "CONFIDENTIAL"),
            effective_from=datetime.now(timezone.utc).isoformat(),
        )
        self._repo.save_source_catalog(rec)
        return cat_id

    def get_catalog_entry(self, source_catalog_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        rec = self._repo.get_source_catalog(source_catalog_id, tenant_id)
        return rec.__dict__ if rec else None

    def list_catalog(self, tenant_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        return [r.__dict__ for r in self._repo.list_source_catalogs(tenant_id, limit, offset)]

    def update_catalog_entry(self, entry_id: str, tenant_id: str, expected_version: int, **updates) -> bool:
        rec = self._repo.get_source_catalog(entry_id, tenant_id)
        if not rec or rec.version != expected_version:
            return False
        for k, v in updates.items():
            if hasattr(rec, k):
                setattr(rec, k, v)
        rec.version = expected_version
        try:
            self._repo.save_source_catalog(rec)
            return True
        except (ConcurrencyConflictError, AccessDeniedError):
            return False


class KpiDefinitionRepository:
    def __init__(self, db_path: Optional[str] = None):
        self._repo = SqliteBusinessRepository(db_path=db_path)

    def create_kpi_definition(self, kpi_code: str, name: str, business_definition: str, tenant_id: str = "", **kwargs) -> str:
        kpi_id = kwargs.get("kpi_definition_id") or f"KPI-{int(time.time() * 1000)}"
        rec = KPIDefinitionRecord(
            kpi_definition_id=kpi_id,
            tenant_id=tenant_id,
            kpi_code=kpi_code,
            name=name,
            business_definition=business_definition,
            source_catalog_id=kwargs.get("source_catalog_id", ""),
            calculation_code=kwargs.get("calculation_code", ""),
            unit=kwargs.get("unit", ""),
            organization_scope=kwargs.get("organization_scope", "Enterprise"),
            sign_convention=kwargs.get("sign_convention", "HIGHER_IS_BETTER"),
            freshness_max_minutes=kwargs.get("freshness_max_minutes", 1440),
        )
        self._repo.save_kpi_definition(rec)
        return kpi_id

    def get_kpi_definition(self, kpi_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        rec = self._repo.get_kpi_definition(kpi_id, tenant_id)
        return rec.__dict__ if rec else None


class KpiRecommendationRuleRepository:
    def __init__(self, db_path: Optional[str] = None):
        self._repo = SqliteBusinessRepository(db_path=db_path)

    def create_rule(self, rule_code: str, name: str, kpi: str, threshold: Decimal, tenant_id: str = "", **kwargs) -> str:
        rule_id = kwargs.get("kpi_recommendation_rule_id") or f"RULE-{int(time.time() * 1000)}"
        rec = KPIRuleRecord(
            kpi_recommendation_rule_id=rule_id,
            tenant_id=tenant_id,
            rule_code=rule_code,
            rule_version=kwargs.get("rule_version", "1.0"),
            name=name,
            kpi=kpi,
            organization_scope=kwargs.get("organization_scope", "Enterprise"),
            category=kwargs.get("category", "OPERATIONAL"),
            comparator=kwargs.get("comparator", "LT"),
            threshold=threshold,
            upper_threshold=kwargs.get("upper_threshold"),
            clear_threshold=kwargs.get("clear_threshold"),
            unit=kwargs.get("unit", ""),
            currency=kwargs.get("currency", "AED"),
            comparison_window=kwargs.get("comparison_window", "MTD"),
            cooldown_minutes=kwargs.get("cooldown_minutes", 1440),
            severity=kwargs.get("severity", "MEDIUM"),
            priority=kwargs.get("priority", 1),
            recommendation_template=kwargs.get("recommendation_template", ""),
            explanation_template=kwargs.get("explanation_template", ""),
            requires_complete=kwargs.get("requires_complete", True),
            owner=kwargs.get("owner", ""),
            state=kwargs.get("state", "ACTIVE"),
            effective_from=datetime.now(timezone.utc).isoformat(),
        )
        self._repo.save_kpi_rule(rec)
        return rule_id

    def get_rule_by_code(self, rule_code: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        rec = self._repo.get_kpi_rule_by_code(rule_code, tenant_id)
        return rec.__dict__ if rec else None

    def list_active_rules(self, tenant_id: str) -> List[Dict[str, Any]]:
        rules = self._repo.list_active_rules(tenant_id)
        return [r.__dict__ for r in rules]


KpiRuleRepository = KpiRecommendationRuleRepository


class KpiSnapshotRepository:
    def __init__(self, db_path: Optional[str] = None):
        self._repo = SqliteBusinessRepository(db_path=db_path)


class RecommendationRepository:
    def __init__(self, db_path: Optional[str] = None):
        self._repo = SqliteBusinessRepository(db_path=db_path)


class RecommendationFeedbackRepository:
    def __init__(self, db_path: Optional[str] = None):
        self._repo = SqliteBusinessRepository(db_path=db_path)

    def save_feedback(self, record: RecommendationFeedbackRecord) -> RecommendationFeedbackRecord:
        return self._repo.save_recommendation_feedback(record)

    def get_feedback(self, feedback_id: str, tenant_id: str) -> Optional[RecommendationFeedbackRecord]:
        return self._repo.get_recommendation_feedback(feedback_id, tenant_id)

    def list_feedback(self, recommendation_id: str, tenant_id: str) -> List[RecommendationFeedbackRecord]:
        return self._repo.list_feedback_for_recommendation(recommendation_id, tenant_id)

    def get_summary_by_rule(self, rule_code: str, tenant_id: str) -> Dict[str, Any]:
        return self._repo.get_feedback_summary_by_rule(rule_code, tenant_id)


class DecisionEvidenceRepository:
    def __init__(self, db_path: Optional[str] = None):
        self._repo = SqliteBusinessRepository(db_path=db_path)

    def record_decision_evidence(self, claim_id: str, decision_id: str, source_lookup: str, output_hash: str, tenant_id: str = "", **kwargs) -> str:
        ev_id = kwargs.get("decision_evidence_id") or f"EV-{int(time.time() * 1000)}"
        rec = DecisionEvidenceRecord(
            decision_evidence_id=ev_id,
            tenant_id=tenant_id,
            claim_id=claim_id,
            decision_id=decision_id,
            source_lookup=source_lookup,
            source_version=kwargs.get("source_version", "1.0"),
            input_snapshot=kwargs.get("input_snapshot", "{}"),
            rationale=kwargs.get("rationale", ""),
            output_hash=output_hash,
            verified_identity=kwargs.get("verified_identity", ""),
            limitations=kwargs.get("limitations", ""),
            manifest_ref=kwargs.get("manifest_ref", ""),
        )
        self._repo.save_decision_evidence(rec)
        return ev_id

    def get_decision_evidence(self, ev_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        rec = self._repo.get_decision_evidence(ev_id, tenant_id)
        return rec.__dict__ if rec else None


class InstitutionalRecordRepository:
    def __init__(self, db_path: Optional[str] = None):
        self._repo = SqliteBusinessRepository(db_path=db_path)

    def create_record(self, record_title: str, record_type: str, source_agent: str, executive_owner: str, summary: str, tenant_id: str = "", **kwargs) -> str:
        rec_id = kwargs.get("institutional_record_id") or f"INST-{int(time.time() * 1000)}"
        rec = InstitutionalRecordEntity(
            institutional_record_id=rec_id,
            tenant_id=tenant_id,
            record_title=record_title,
            record_type=record_type,
            source_agent=source_agent,
            executive_owner=executive_owner,
            summary=summary,
            key_decisions=kwargs.get("key_decisions", ""),
            action_items=kwargs.get("action_items", ""),
            retention_policy=kwargs.get("retention_policy", "7_YEARS_STANDARD"),
            loop_component_id=kwargs.get("loop_component_id"),
            notebook_location=kwargs.get("notebook_location"),
            created_on=datetime.now(timezone.utc).isoformat(),
        )
        self._repo.save_institutional_record(rec)
        return rec_id

    def get_record(self, rec_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        rec = self._repo.get_institutional_record(rec_id, tenant_id)
        return rec.__dict__ if rec else None


class ProposalEvaluationRepository:
    def __init__(self, db_path: Optional[str] = None):
        self._repo = SqliteBusinessRepository(db_path=db_path)


class PeerBenchmarkRepository:
    def __init__(self, db_path: Optional[str] = None):
        self._repo = SqliteBusinessRepository(db_path=db_path)


class VendorHistoryRepository:
    def __init__(self, db_path: Optional[str] = None):
        self._repo = SqliteBusinessRepository(db_path=db_path)

    def save_record(self, record: VendorPerformanceHistoryRecord) -> VendorPerformanceHistoryRecord:
        return self._repo.save_vendor_performance_history(record)

    def get_record(self, record_id: str, tenant_id: str) -> Optional[VendorPerformanceHistoryRecord]:
        return self._repo.get_vendor_performance_history(record_id, tenant_id)

    def find_by_hash(self, source_hash: str, tenant_id: str) -> Optional[VendorPerformanceHistoryRecord]:
        return self._repo.find_vendor_history_by_source_hash(source_hash, tenant_id)

    def list_records(self, vendor_id: str, tenant_id: str, entity_scope: Optional[str] = None) -> List[VendorPerformanceHistoryRecord]:
        return self._repo.list_vendor_history(vendor_id, tenant_id, entity_scope=entity_scope)


class VendorDecisionRepository:
    def __init__(self, db_path: Optional[str] = None):
        self._repo = SqliteBusinessRepository(db_path=db_path)

    def save_decision(self, record: VendorDecisionRecord, caller_role: str = "velora-app-service") -> VendorDecisionRecord:
        return self._repo.save_vendor_decision(record, caller_role=caller_role)

    def get_decision(self, decision_id: str, tenant_id: str, version: Optional[str] = None) -> Optional[VendorDecisionRecord]:
        return self._repo.get_vendor_decision(decision_id, tenant_id, version=version)

    def list_decisions(self, tenant_id: str, use_case: Optional[str] = None, limit: int = 50) -> List[VendorDecisionRecord]:
        return self._repo.list_vendor_decisions(tenant_id, use_case=use_case, limit=limit)

    def update_audit_manifest(self, decision_id: str, tenant_id: str, version: str, audit_manifest_ref: str) -> None:
        self._repo.update_vendor_decision_audit_manifest(decision_id, tenant_id, version, audit_manifest_ref)

    def delete_decision(self, decision_id: str, tenant_id: str, version: Optional[str] = None, caller_role: str = "velora-app-service") -> bool:
        return self._repo.delete_vendor_decision(decision_id, tenant_id, version=version, caller_role=caller_role)


class MeetingActionRepository:
    def __init__(self, db_path: Optional[str] = None):
        self._repo = SqliteBusinessRepository(db_path=db_path)

    def save_mapping(self, record: MeetingActionMappingRecord) -> MeetingActionMappingRecord:
        return self._repo.save_meeting_action_mapping(record)

    def get_mapping(self, tenant_id: str, mapping_id: str) -> Optional[MeetingActionMappingRecord]:
        return self._repo.get_meeting_action_mapping(tenant_id, mapping_id)

    def find_by_task(self, tenant_id: str, planner_task_id: str) -> Optional[MeetingActionMappingRecord]:
        return self._repo.find_meeting_action_by_task(tenant_id, planner_task_id)

    def find_by_extracted(self, tenant_id: str, meeting_id: str, source_version: str, extracted_action_id: str) -> Optional[MeetingActionMappingRecord]:
        return self._repo.find_meeting_action_by_extracted(tenant_id, meeting_id, source_version, extracted_action_id)

    def list_mappings(self, tenant_id: str = "velora-aviation", meeting_id: Optional[str] = None, source_version: Optional[str] = None) -> List[MeetingActionMappingRecord]:
        return self._repo.list_meeting_action_mappings(tenant_id, meeting_id=meeting_id, source_version=source_version)

    def update_status(self, tenant_id: str, planner_task_id: str, status: str, percent_complete: int, due_date: Optional[str] = None, owner_email: Optional[str] = None) -> bool:
        return self._repo.update_meeting_action_status(tenant_id, planner_task_id, status, percent_complete, due_date=due_date, owner_email=owner_email)



_BUSINESS_REPO = None


def get_business_repository(db_path: Optional[str] = None):
    """Factory returning SqliteBusinessRepository or PostgresBusinessRepository."""
    global _BUSINESS_REPO
    if db_path:
        return SqliteBusinessRepository(db_path=db_path)
    env_db = os.getenv("VELORA_BUSINESS_REPO_DB")
    if env_db:
        if _BUSINESS_REPO is None or _BUSINESS_REPO.db_path != env_db:
            _BUSINESS_REPO = SqliteBusinessRepository(db_path=env_db)
        return _BUSINESS_REPO
    if _BUSINESS_REPO is None or not os.path.exists(_BUSINESS_REPO.db_path):
        _BUSINESS_REPO = SqliteBusinessRepository()
    return _BUSINESS_REPO


def reset_business_repository_for_testing():
    """Reset global business repo cache for testing isolation."""
    global _BUSINESS_REPO
    _BUSINESS_REPO = None


get_business_repository_client = get_business_repository

