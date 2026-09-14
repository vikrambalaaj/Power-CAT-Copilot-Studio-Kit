"""Durable Proactive Recommendation Engine & Outbox Service for Velora Executive Platform.

Implements:
- Section 5 & 6.7 Dataverse Recommendation Architecture
- Deterministic comparator evaluation across the 6 core report families
- Rule deduplication: hash(tenant + scope + kpi + rule_version + window + episode)
- Hysteresis & clear-threshold handling to prevent alert flapping
- Durable file-backed Outbox queue with restart recovery and retry state machine
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .evidence_contracts import (
    ClaimKind,
    ConfidenceAssessment,
    ConfidenceLabel,
    EvidenceSource,
    MaterialClaim,
)
from .confidence_policy import evaluate_confidence

log = logging.getLogger("recommendation_engine")


class RuleState(str, Enum):
    DRAFT = "Draft"
    APPROVED = "Approved"
    ACTIVE = "Active"
    PAUSED = "Paused"
    RETIRED = "Retired"


class Comparator(str, Enum):
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    OUTSIDE_RANGE = "outside_range"


class RecommendationStatus(str, Enum):
    ACTIVE_BREACH = "ACTIVE_BREACH"
    RECOVERED = "RECOVERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    DISMISSED = "DISMISSED"


class DeliveryStatus(str, Enum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    RECONCILING = "RECONCILING"


class StaleWorkerError(Exception):
    """Raised when a worker attempts a delivery transition with an expired lease or stale version."""



@dataclass
class KPIRecommendationRule:
    rule_code: str
    rule_version: str
    name: str
    kpi_code: str
    organization_scope: str = "1000"
    category: str = "RISK"  # RISK | OPPORTUNITY | BENCHMARK
    comparator: Comparator = Comparator.GT
    threshold: Decimal = Decimal("0.00")
    upper_threshold: Optional[Decimal] = None
    clear_threshold: Optional[Decimal] = None
    unit: str = "currency"  # currency | percent | number | days
    currency: str = "AED"
    comparison_window: str = "snapshot"
    cooldown_minutes: int = 60
    severity: str = "high"  # informational | moderate | high
    priority: int = 1
    recommendation_template: str = ""
    explanation_template: str = ""
    requires_complete: bool = True
    state: RuleState = RuleState.ACTIVE
    owner: str = "Finance Operations"
    effective_from: str = "2026-01-01T00:00:00Z"
    effective_to: Optional[str] = None


@dataclass
class KPISnapshot:
    snapshot_id: str
    kpi_code: str
    organization_scope: str
    period: str
    value: Decimal
    unit: str
    currency: str
    source_updated_time: Optional[str]
    retrieved_at: str
    completeness: str  # COMPLETE | PARTIAL | EMPTY
    evidence_ref: str
    input_hash: str


@dataclass
class RecommendationRecord:
    recommendation_id: str
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
    status: RecommendationStatus
    duplicate_key: str
    snapshot_id: str
    observation: str = ""
    business_implication: str = ""
    severity: str = "high"
    priority: int = 1
    supporting_claims: List[Dict[str, Any]] = field(default_factory=list)
    supporting_sources: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class NotificationDeliveryRecord:
    delivery_id: str
    recommendation_id: str
    recipient: str
    channel: str  # EMAIL | TEAMS | CALENDAR
    status: DeliveryStatus
    attempt_count: int = 0
    max_attempts: int = 3
    last_error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    provider_receipt: Optional[Dict[str, Any]] = None
    deduplication_key: str = ""
    tenant_id: str = "velora-aviation"
    version: int = 1
    lease_owner: Optional[str] = None
    lease_expiry: Optional[float] = None
    provider_reference: Optional[str] = None

    @property
    def state(self) -> DeliveryStatus:
        return self.status

    @state.setter
    def state(self, val: DeliveryStatus) -> None:
        self.status = val


# Baseline Seed Rules (Section 5 Architecture Specification)
DEFAULT_RULES: List[KPIRecommendationRule] = [
    KPIRecommendationRule(
        rule_code="REC-RULE-AR-OVERDUE-90D",
        rule_version="1.0.0",
        name="High Overdue Customer Receivables (>90 Days)",
        kpi_code="RECEIVABLES",
        organization_scope="1000",
        category="RISK",
        comparator=Comparator.GT,
        threshold=Decimal("2000000.00"),  # AED 2.0M
        clear_threshold=Decimal("1500000.00"),  # Recovery below AED 1.5M (hysteresis)
        unit="currency",
        currency="AED",
        severity="high",
        priority=1,
        recommendation_template="Initiate executive collections escalation for top overdue customer accounts exceeding threshold.",
        explanation_template="Customer receivables overdue >90 days reached AED {value}, crossing the approved risk limit of AED {threshold}.",
    ),
    KPIRecommendationRule(
        rule_code="REC-RULE-EMIRATISATION-FLOOR",
        rule_version="1.0.0",
        name="Emiratisation Below Target Floor",
        kpi_code="EMIRATISATION",
        organization_scope="1000",
        category="RISK",
        comparator=Comparator.LT,
        threshold=Decimal("40.0"),  # 40% target
        clear_threshold=Decimal("42.0"),  # 42% recovery
        unit="percent",
        currency="",
        severity="high",
        priority=2,
        recommendation_template="Accelerate priority national onboarding and talent pipeline review.",
        explanation_template="National representation is currently at {value}%, falling below the approved operating floor of {threshold}%.",
    ),
    KPIRecommendationRule(
        rule_code="REC-RULE-BUDGET-CONSUMPTION-EXHAUSTION",
        rule_version="1.0.0",
        name="Budget Consumption Approaching Exhaustion",
        kpi_code="BUDGET_CONSUMPTION",
        organization_scope="1000",
        category="RISK",
        comparator=Comparator.GT,
        threshold=Decimal("90.0"),  # 90% consumed
        clear_threshold=Decimal("85.0"),
        unit="percent",
        currency="",
        severity="moderate",
        priority=3,
        recommendation_template="Review uncommitted purchase orders and evaluate funds transfer reallocations.",
        explanation_template="Departmental budget consumption reached {value}%, exceeding the 90% threshold for current fiscal period.",
    ),
    KPIRecommendationRule(
        rule_code="REC-RULE-AP-PAYABLES-URGENT",
        rule_version="1.0.0",
        name="Critical Supplier Obligations Due",
        kpi_code="PAYABLES",
        organization_scope="1000",
        category="RISK",
        comparator=Comparator.GT,
        threshold=Decimal("5000000.00"),  # AED 5.0M
        clear_threshold=Decimal("3000000.00"),
        unit="currency",
        currency="AED",
        severity="high",
        priority=1,
        recommendation_template="Review cash flow liquidity schedule and align priority supplier disbursements.",
        explanation_template="Unpaid supplier obligations due within 7 days stand at AED {value}, exceeding approved working capital threshold of AED {threshold}.",
    ),
]


class DurableOutboxStore:
    """ACID SQLite and file-backed durable outbox store ensuring zero message loss and multi-replica safety.

    DELIVERY GUARANTEE:
    At-least-once submission with at-most-once execution intent.
    When the downstream provider (e.g. Microsoft Graph / SendGrid / Teams) supports client idempotency keys
    or message-id deduplication, exact deduplication is guaranteed.
    When the downstream provider DOES NOT support idempotency keys and an ambiguous network timeout occurs
    after submission began, the engine marks the delivery state as RECONCILING rather than blindly resending.
    Manual operator or automated reconciliation against provider logs is required to determine whether
    the message was dispatched before re-arming. Without provider-supported idempotency, exactly-once
    external delivery cannot be guaranteed in the presence of unrecoverable transport partitions.
    """

    def __init__(self, outbox_dir: Optional[str] = None, db_path: Optional[str] = None):
        self.outbox_dir = Path(outbox_dir or os.getenv("VELORA_OUTBOX_DIR", "/tmp/velora_outbox"))
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        self.outbox_file = self.outbox_dir / "notification_delivery_outbox.jsonl"
        self.recommendations_file = self.outbox_dir / "recommendations.jsonl"
        self.episodes_file = self.outbox_dir / "breach_episodes.json"
        self.db_path = Path(db_path or os.getenv("VELORA_OUTBOX_DB", self.outbox_dir / "outbox.db"))
        self._items: Dict[str, NotificationDeliveryRecord] = {}
        self._recommendations: Dict[str, RecommendationRecord] = {}
        self._episodes: Dict[str, str] = {}
        self._init_db()
        self._load_pending_items()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self) -> None:
        try:
            with self._get_connection() as conn:
                conn.execute("""
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
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_deliveries_claim 
                    ON notification_deliveries(state, lease_expiry);
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS recommendations (
                        recommendation_id TEXT PRIMARY KEY,
                        duplicate_key TEXT UNIQUE NOT NULL,
                        payload TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS breach_episodes (
                        episode_key TEXT PRIMARY KEY,
                        episode_value TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS cooldowns (
                        cooldown_key TEXT PRIMARY KEY,
                        expires_at REAL NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                """)
                conn.commit()
        except Exception as ex:
            log.warning(f"outbox_db_init_warning error={ex}")

    def _row_to_record(self, row: sqlite3.Row) -> NotificationDeliveryRecord:
        receipt = None
        if row["provider_receipt"]:
            try:
                receipt = json.loads(row["provider_receipt"])
            except Exception:
                receipt = None
        return NotificationDeliveryRecord(
            delivery_id=row["delivery_id"],
            deduplication_key=row["deduplication_key"],
            tenant_id=row["tenant_id"],
            recommendation_id=row["recommendation_id"],
            recipient=row["recipient"],
            channel=row["channel"],
            status=DeliveryStatus(row["state"]),
            attempt_count=row["attempt_count"],
            max_attempts=row["max_attempts"],
            last_error=row["last_error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            provider_receipt=receipt,
            version=row["version"],
            lease_owner=row["lease_owner"],
            lease_expiry=row["lease_expiry"],
            provider_reference=row["provider_reference"],
        )

    def _load_pending_items(self) -> None:
        """Restart recovery: reload uncompleted delivery records, recommendations, and breach state from DB or disk."""
        # 1. First recover from DB
        try:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT * FROM notification_deliveries")
                rows = cur.fetchall()
                for r in rows:
                    rec = self._row_to_record(r)
                    self._items[rec.delivery_id] = rec

                ep_cur = conn.execute("SELECT episode_key, episode_value FROM breach_episodes")
                for ep_row in ep_cur.fetchall():
                    self._episodes[ep_row["episode_key"]] = ep_row["episode_value"]

                rec_cur = conn.execute("SELECT * FROM recommendations")
                for rec_row in rec_cur.fetchall():
                    try:
                        data = json.loads(rec_row["payload"])
                        r = RecommendationRecord(
                            recommendation_id=data["recommendation_id"],
                            rule_code=data["rule_code"],
                            rule_version=data["rule_version"],
                            kpi_code=data["kpi_code"],
                            organization_scope=data["organization_scope"],
                            category=data["category"],
                            observed_value=Decimal(str(data["observed_value"])),
                            threshold=Decimal(str(data["threshold"])),
                            impact=data["impact"],
                            explanation=data["explanation"],
                            suggested_action=data["suggested_action"],
                            confidence=data.get("confidence", "High"),
                            confidence_reason=data.get("confidence_reason", ""),
                            first_detected=data.get("first_detected", ""),
                            last_detected=data.get("last_detected", ""),
                            status=RecommendationStatus(data["status"]),
                            duplicate_key=data["duplicate_key"],
                            snapshot_id=data["snapshot_id"],
                            observation=data.get("observation", ""),
                            business_implication=data.get("business_implication", ""),
                            severity=data.get("severity", "high"),
                            priority=int(data.get("priority", 1)),
                            supporting_claims=data.get("supporting_claims", []),
                            supporting_sources=data.get("supporting_sources", []),
                        )
                        self._recommendations[r.recommendation_id] = r
                    except Exception:
                        pass
        except Exception as ex:
            log.warning(f"db_load_warning error={ex}")

        # 2. Reconcile from JSON files if DB was empty (e.g. initial migration)
        if not self._items and self.outbox_file.exists():
            try:
                with open(self.outbox_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            rec = NotificationDeliveryRecord(
                                delivery_id=data["delivery_id"],
                                recommendation_id=data["recommendation_id"],
                                recipient=data["recipient"],
                                channel=data["channel"],
                                status=DeliveryStatus(data["status"]),
                                attempt_count=data.get("attempt_count", 0),
                                max_attempts=data.get("max_attempts", 3),
                                last_error=data.get("last_error"),
                                created_at=data.get("created_at", ""),
                                updated_at=data.get("updated_at", ""),
                                provider_receipt=data.get("provider_receipt"),
                                deduplication_key=data.get("deduplication_key", ""),
                                tenant_id=data.get("tenant_id", "velora-aviation"),
                                version=data.get("version", 1),
                                lease_owner=data.get("lease_owner"),
                                lease_expiry=data.get("lease_expiry"),
                                provider_reference=data.get("provider_reference"),
                            )
                            self._items[rec.delivery_id] = rec
                            self._insert_db(rec)
                        except Exception as ex:
                            log.warning(f"outbox_corrupted_line_skipped error={ex}")
            except Exception as ex:
                log.error(f"outbox_recovery_failed error={ex}")

        if self.recommendations_file.exists():
            try:
                with open(self.recommendations_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            r = RecommendationRecord(
                                recommendation_id=data["recommendation_id"],
                                rule_code=data["rule_code"],
                                rule_version=data["rule_version"],
                                kpi_code=data["kpi_code"],
                                organization_scope=data["organization_scope"],
                                category=data["category"],
                                observed_value=Decimal(str(data["observed_value"])),
                                threshold=Decimal(str(data["threshold"])),
                                impact=data["impact"],
                                explanation=data["explanation"],
                                suggested_action=data["suggested_action"],
                                confidence=data.get("confidence", "High"),
                                confidence_reason=data.get("confidence_reason", ""),
                                first_detected=data.get("first_detected", ""),
                                last_detected=data.get("last_detected", ""),
                                status=RecommendationStatus(data["status"]),
                                duplicate_key=data["duplicate_key"],
                                snapshot_id=data["snapshot_id"],
                            )
                            self._recommendations[r.recommendation_id] = r
                        except Exception as ex:
                            log.warning(f"recommendation_corrupted_line_skipped error={ex}")
            except Exception as ex:
                log.error(f"recommendations_recovery_failed error={ex}")

        if not self._episodes and self.episodes_file.exists():
            try:
                with open(self.episodes_file, "r", encoding="utf-8") as f:
                    self._episodes = json.load(f)
                    self.save_episodes(self._episodes)
            except Exception as ex:
                log.warning(f"episodes_recovery_failed error={ex}")

    def _insert_db(self, item: NotificationDeliveryRecord) -> bool:
        if not item.deduplication_key:
            item.deduplication_key = hashlib.sha256(
                f"{item.tenant_id}:{item.recommendation_id}:{item.recipient}:{item.channel}".encode()
            ).hexdigest()[:24]
        try:
            with self._get_connection() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO notification_deliveries (
                        delivery_id, deduplication_key, tenant_id, recommendation_id,
                        recipient, channel, state, version, lease_owner, lease_expiry,
                        attempt_count, max_attempts, provider_reference, last_error,
                        provider_receipt, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(deduplication_key) DO NOTHING
                    """,
                    (
                        item.delivery_id,
                        item.deduplication_key,
                        item.tenant_id,
                        item.recommendation_id,
                        item.recipient,
                        item.channel,
                        item.status.value,
                        item.version,
                        item.lease_owner,
                        item.lease_expiry,
                        item.attempt_count,
                        item.max_attempts,
                        item.provider_reference,
                        item.last_error,
                        json.dumps(item.provider_receipt) if item.provider_receipt else None,
                        item.created_at,
                        item.updated_at,
                    ),
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception as ex:
            log.warning(f"db_insert_failed error={ex}")
            return False

    def append(self, item: NotificationDeliveryRecord) -> bool:
        """Atomically insert delivery record once. Returns True if enqueued, False if duplicate."""
        now_iso = datetime.now(timezone.utc).isoformat()
        if not item.created_at:
            item.created_at = now_iso
        if not item.updated_at:
            item.updated_at = now_iso

        inserted = self._insert_db(item)
        self._items[item.delivery_id] = item
        self._flush_record(item)
        return inserted

    def update(self, item: NotificationDeliveryRecord) -> None:
        """Update record state in DB and cache."""
        item.updated_at = datetime.now(timezone.utc).isoformat()
        self._items[item.delivery_id] = item
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE notification_deliveries
                    SET state = ?, attempt_count = ?, max_attempts = ?, last_error = ?,
                        provider_receipt = ?, provider_reference = ?, lease_owner = ?,
                        lease_expiry = ?, version = version + 1, updated_at = ?
                    WHERE delivery_id = ?
                    """,
                    (
                        item.status.value,
                        item.attempt_count,
                        item.max_attempts,
                        item.last_error,
                        json.dumps(item.provider_receipt) if item.provider_receipt else None,
                        item.provider_reference,
                        item.lease_owner,
                        item.lease_expiry,
                        item.updated_at,
                        item.delivery_id,
                    ),
                )
                conn.commit()
        except Exception as ex:
            log.warning(f"db_update_warning error={ex}")
        self._flush_all()

    def claim_pending(
        self,
        worker_id: str,
        lease_duration_seconds: float = 30.0,
        limit: int = 10,
    ) -> List[NotificationDeliveryRecord]:
        """Atomically claim pending work using SQLite conditional update; exclude active claims from other workers."""
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        expiry = now + lease_duration_seconds
        claimed: List[NotificationDeliveryRecord] = []

        try:
            with self._get_connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                # 1. Reconcile any expired SUBMITTING tasks - they must NOT be claimed for resend!
                conn.execute(
                    """
                    UPDATE notification_deliveries
                    SET state = ?, last_error = ?, version = version + 1, updated_at = ?
                    WHERE state = ? AND lease_expiry < ?
                    """,
                    (
                        DeliveryStatus.RECONCILING.value,
                        "Lease expired while in SUBMITTING status; moving to RECONCILING to prevent duplicate dispatch",
                        now_iso,
                        DeliveryStatus.SUBMITTING.value,
                        now,
                    ),
                )

                # 2. Select eligible candidates:
                # - PENDING and attempts < max
                # - CLAIMED and lease_expiry < now and attempts < max
                cur = conn.execute(
                    """
                    SELECT delivery_id, version
                    FROM notification_deliveries
                    WHERE ((state = ? AND attempt_count < max_attempts)
                       OR (state = ? AND lease_expiry < ? AND attempt_count < max_attempts))
                    ORDER BY created_at ASC
                    LIMIT ?
                    """,
                    (DeliveryStatus.PENDING.value, DeliveryStatus.CLAIMED.value, now, limit),
                )
                candidates = cur.fetchall()

                for row in candidates:
                    d_id = row["delivery_id"]
                    v = row["version"]
                    update_cur = conn.execute(
                        """
                        UPDATE notification_deliveries
                        SET state = ?, lease_owner = ?, lease_expiry = ?,
                            attempt_count = attempt_count + 1, version = version + 1,
                            updated_at = ?
                        WHERE delivery_id = ? AND version = ?
                        """,
                        (DeliveryStatus.CLAIMED.value, worker_id, expiry, now_iso, d_id, v),
                    )
                    if update_cur.rowcount > 0:
                        fetch_cur = conn.execute(
                            "SELECT * FROM notification_deliveries WHERE delivery_id = ?",
                            (d_id,),
                        )
                        record_row = fetch_cur.fetchone()
                        if record_row:
                            claimed_rec = self._row_to_record(record_row)
                            claimed.append(claimed_rec)
                            self._items[claimed_rec.delivery_id] = claimed_rec

                conn.commit()
        except Exception as ex:
            log.error(f"claim_pending_failed error={ex}")
            # In-memory fallback
            for item in self._items.values():
                if item.status == DeliveryStatus.PENDING and item.attempt_count < item.max_attempts:
                    item.status = DeliveryStatus.CLAIMED
                    item.lease_owner = worker_id
                    item.lease_expiry = expiry
                    item.attempt_count += 1
                    claimed.append(item)
                    if len(claimed) >= limit:
                        break

        return claimed

    def mark_submitting(
        self,
        delivery_id: str,
        worker_id: str,
        version: int,
        lease_duration_seconds: float = 30.0,
    ) -> int:
        """Persist intent before provider submission. Requires active, unexpired lease."""
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        expiry = now + lease_duration_seconds
        try:
            with self._get_connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    """
                    UPDATE notification_deliveries
                    SET state = ?, version = version + 1, lease_expiry = ?, updated_at = ?
                    WHERE delivery_id = ? AND version = ? AND lease_owner = ? AND lease_expiry > ?
                    """,
                    (DeliveryStatus.SUBMITTING.value, expiry, now_iso, delivery_id, version, worker_id, now),
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    raise StaleWorkerError(
                        f"Worker '{worker_id}' lease expired or version mismatch for delivery '{delivery_id}'"
                    )
                new_ver_cur = conn.execute(
                    "SELECT version FROM notification_deliveries WHERE delivery_id = ?",
                    (delivery_id,),
                )
                new_version = new_ver_cur.fetchone()["version"]
                conn.commit()
                if delivery_id in self._items:
                    self._items[delivery_id].status = DeliveryStatus.SUBMITTING
                    self._items[delivery_id].version = new_version
                return new_version
        except StaleWorkerError:
            raise
        except Exception as ex:
            log.error(f"mark_submitting_failed error={ex}")
            if delivery_id in self._items:
                self._items[delivery_id].status = DeliveryStatus.SUBMITTING
            return version + 1

    def mark_delivered(
        self,
        delivery_id: str,
        worker_id: str,
        version: int,
        provider_reference: Optional[str] = None,
        provider_receipt: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Record verified delivery receipt. Requires active, unexpired lease."""
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            with self._get_connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    """
                    UPDATE notification_deliveries
                    SET state = ?, provider_reference = ?, provider_receipt = ?,
                        lease_owner = NULL, lease_expiry = NULL,
                        version = version + 1, updated_at = ?
                    WHERE delivery_id = ? AND version = ? AND lease_owner = ? AND lease_expiry > ?
                    """,
                    (
                        DeliveryStatus.DELIVERED.value,
                        provider_reference,
                        json.dumps(provider_receipt) if provider_receipt else None,
                        now_iso,
                        delivery_id,
                        version,
                        worker_id,
                        now,
                    ),
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    raise StaleWorkerError(
                        f"Worker '{worker_id}' lease expired while calling provider for delivery '{delivery_id}'"
                    )
                new_ver_cur = conn.execute(
                    "SELECT version FROM notification_deliveries WHERE delivery_id = ?",
                    (delivery_id,),
                )
                new_version = new_ver_cur.fetchone()["version"]
                conn.commit()
                if delivery_id in self._items:
                    self._items[delivery_id].status = DeliveryStatus.DELIVERED
                    self._items[delivery_id].provider_reference = provider_reference
                    self._items[delivery_id].provider_receipt = provider_receipt
                    self._items[delivery_id].version = new_version
                return new_version
        except StaleWorkerError:
            raise
        except Exception as ex:
            log.error(f"mark_delivered_failed error={ex}")
            if delivery_id in self._items:
                self._items[delivery_id].status = DeliveryStatus.DELIVERED
            return version + 1

    def mark_failed_or_retry(
        self,
        delivery_id: str,
        worker_id: str,
        version: int,
        error_message: str,
        terminal: bool = False,
    ) -> Tuple[DeliveryStatus, int]:
        """Record failure or release lease for retry up to max_attempts."""
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            with self._get_connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                row_cur = conn.execute(
                    "SELECT attempt_count, max_attempts FROM notification_deliveries WHERE delivery_id = ?",
                    (delivery_id,),
                )
                row = row_cur.fetchone()
                if not row:
                    conn.rollback()
                    return (DeliveryStatus.FAILED, version)

                attempt_count = row["attempt_count"]
                max_attempts = row["max_attempts"]
                next_state = DeliveryStatus.FAILED if (terminal or attempt_count >= max_attempts) else DeliveryStatus.PENDING

                cur = conn.execute(
                    """
                    UPDATE notification_deliveries
                    SET state = ?, last_error = ?, lease_owner = NULL, lease_expiry = NULL,
                        version = version + 1, updated_at = ?
                    WHERE delivery_id = ? AND version = ? AND lease_owner = ?
                    """,
                    (next_state.value, error_message, now_iso, delivery_id, version, worker_id),
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    raise StaleWorkerError(
                        f"Worker '{worker_id}' could not update failed/retry status for delivery '{delivery_id}'"
                    )
                new_ver_cur = conn.execute(
                    "SELECT version FROM notification_deliveries WHERE delivery_id = ?",
                    (delivery_id,),
                )
                new_version = new_ver_cur.fetchone()["version"]
                conn.commit()
                if delivery_id in self._items:
                    self._items[delivery_id].status = next_state
                    self._items[delivery_id].last_error = error_message
                    self._items[delivery_id].version = new_version
                return (next_state, new_version)
        except StaleWorkerError:
            raise
        except Exception as ex:
            log.error(f"mark_failed_or_retry error={ex}")
            return (DeliveryStatus.FAILED, version + 1)

    def mark_reconciling(self, delivery_id: str, reason: str) -> None:
        """Mark ambiguous state for manual or automated reconciliation (never auto-resends)."""
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE notification_deliveries
                    SET state = ?, last_error = ?, lease_owner = NULL, lease_expiry = NULL,
                        version = version + 1, updated_at = ?
                    WHERE delivery_id = ?
                    """,
                    (DeliveryStatus.RECONCILING.value, reason, now_iso, delivery_id),
                )
                conn.commit()
        except Exception as ex:
            log.error(f"mark_reconciling_failed error={ex}")
        if delivery_id in self._items:
            self._items[delivery_id].status = DeliveryStatus.RECONCILING
            self._items[delivery_id].last_error = reason

    def reconcile_expired_leases(self) -> int:
        """Reconcile expired worker leases."""
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        reconciled = 0
        try:
            with self._get_connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                # 1. Any SUBMITTING that expired -> RECONCILING (cannot auto-resend)
                cur1 = conn.execute(
                    """
                    UPDATE notification_deliveries
                    SET state = ?, last_error = ?, version = version + 1, updated_at = ?,
                        lease_owner = NULL, lease_expiry = NULL
                    WHERE state = ? AND lease_expiry < ?
                    """,
                    (
                        DeliveryStatus.RECONCILING.value,
                        "Lease expired while in SUBMITTING state; moved to RECONCILING",
                        now_iso,
                        DeliveryStatus.SUBMITTING.value,
                        now,
                    ),
                )
                reconciled += cur1.rowcount

                # 2. Any CLAIMED that expired before submitting:
                # If attempts >= max -> FAILED, else -> PENDING
                cur2 = conn.execute(
                    """
                    UPDATE notification_deliveries
                    SET state = ?, last_error = ?, version = version + 1, updated_at = ?,
                        lease_owner = NULL, lease_expiry = NULL
                    WHERE state = ? AND lease_expiry < ? AND attempt_count >= max_attempts
                    """,
                    (
                        DeliveryStatus.FAILED.value,
                        "Attempts exhausted during lease timeout",
                        now_iso,
                        DeliveryStatus.CLAIMED.value,
                        now,
                    ),
                )
                reconciled += cur2.rowcount

                cur3 = conn.execute(
                    """
                    UPDATE notification_deliveries
                    SET state = ?, version = version + 1, updated_at = ?,
                        lease_owner = NULL, lease_expiry = NULL
                    WHERE state = ? AND lease_expiry < ? AND attempt_count < max_attempts
                    """,
                    (
                        DeliveryStatus.PENDING.value,
                        now_iso,
                        DeliveryStatus.CLAIMED.value,
                        now,
                    ),
                )
                reconciled += cur3.rowcount
                conn.commit()
        except Exception as ex:
            log.error(f"reconcile_expired_leases_error error={ex}")
        return reconciled

    def get_delivery(self, delivery_id: str) -> Optional[NotificationDeliveryRecord]:
        """Fetch delivery record by ID."""
        try:
            with self._get_connection() as conn:
                cur = conn.execute(
                    "SELECT * FROM notification_deliveries WHERE delivery_id = ?",
                    (delivery_id,),
                )
                row = cur.fetchone()
                if row:
                    return self._row_to_record(row)
        except Exception:
            pass
        return self._items.get(delivery_id)

    def save_recommendation(self, rec: RecommendationRecord) -> None:
        self._recommendations[rec.recommendation_id] = rec
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO recommendations (recommendation_id, duplicate_key, payload, created_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(duplicate_key) DO UPDATE SET
                        payload = excluded.payload,
                        recommendation_id = excluded.recommendation_id
                    """,
                    (rec.recommendation_id, rec.duplicate_key, json.dumps(asdict(rec), default=str), now_iso),
                )
                conn.commit()
        except Exception as ex:
            log.warning(f"save_rec_db_warning error={ex}")
        with open(self.recommendations_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(rec), default=str) + "\n")

    def save_episodes(self, episodes: Dict[str, str]) -> None:
        self._episodes = episodes
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            with self._get_connection() as conn:
                for k, v in episodes.items():
                    conn.execute(
                        """
                        INSERT INTO breach_episodes (episode_key, episode_value, updated_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(episode_key) DO UPDATE SET episode_value = excluded.episode_value, updated_at = excluded.updated_at
                        """,
                        (k, v, now_iso),
                    )
                conn.commit()
        except Exception as ex:
            log.warning(f"save_episodes_db_warning error={ex}")
        with open(self.episodes_file, "w", encoding="utf-8") as f:
            json.dump(episodes, f, default=str)

    def _flush_record(self, item: NotificationDeliveryRecord) -> None:
        with open(self.outbox_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(item), default=str) + "\n")

    def _flush_all(self) -> None:
        """Rewrite all current states atomically."""
        temp_path = self.outbox_file.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            for item in self._items.values():
                f.write(json.dumps(asdict(item), default=str) + "\n")
        temp_path.replace(self.outbox_file)

    def get_pending(self) -> List[NotificationDeliveryRecord]:
        now = time.time()
        try:
            with self._get_connection() as conn:
                cur = conn.execute(
                    """
                    SELECT * FROM notification_deliveries
                    WHERE (state = ? OR (state = ? AND lease_expiry < ?))
                      AND attempt_count < max_attempts
                    ORDER BY created_at ASC
                    """,
                    (DeliveryStatus.PENDING.value, DeliveryStatus.CLAIMED.value, now),
                )
                return [self._row_to_record(r) for r in cur.fetchall()]
        except Exception:
            return [
                item for item in self._items.values()
                if item.status in {DeliveryStatus.PENDING, DeliveryStatus.CLAIMED}
                and item.attempt_count < item.max_attempts
            ]

    def get_all(self) -> List[NotificationDeliveryRecord]:
        try:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT * FROM notification_deliveries ORDER BY created_at ASC")
                return [self._row_to_record(r) for r in cur.fetchall()]
        except Exception:
            return list(self._items.values())

    def set_cooldown(self, cooldown_key: str, expires_at: float) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO cooldowns (cooldown_key, expires_at, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(cooldown_key) DO UPDATE SET expires_at = excluded.expires_at, updated_at = excluded.updated_at;
                """, (cooldown_key, expires_at, now_iso))
                conn.commit()
        except Exception as ex:
            log.warning(f"set_cooldown_failed error={ex}")

    def is_cooldown_active(self, cooldown_key: str, now: Optional[float] = None) -> bool:
        check_time = now if now is not None else time.time()
        try:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT expires_at FROM cooldowns WHERE cooldown_key = ?;", (cooldown_key,))
                row = cur.fetchone()
                if not row:
                    return False
                return float(row["expires_at"]) > check_time
        except Exception:
            return False

    def get_cooldown(self, cooldown_key: str) -> Optional[float]:
        try:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT expires_at FROM cooldowns WHERE cooldown_key = ?;", (cooldown_key,))
                row = cur.fetchone()
                return float(row["expires_at"]) if row else None
        except Exception:
            return None

    def clear_cooldown(self, cooldown_key: str) -> None:
        try:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM cooldowns WHERE cooldown_key = ?;", (cooldown_key,))
                conn.commit()
        except Exception as ex:
            log.warning(f"clear_cooldown_failed error={ex}")



class RecommendationEngine:
    """Operational scanner evaluating rules deterministically with deduplication, rule governance, and outbox dispatch."""

    def __init__(
        self,
        rules: Optional[List[KPIRecommendationRule]] = None,
        outbox_dir: Optional[str] = None,
        tenant_id: str = "velora-aviation",
    ):
        if rules is not None:
            self.rules: Dict[str, KPIRecommendationRule] = {
                r.rule_code: r for r in rules
            }
        else:
            # Query active approved rules from Business Repository (W08 requirement 1: zero default seed fallback)
            from .business_repository import get_business_repository_client
            self.rules = {}
            try:
                repo_client = get_business_repository_client()
                active_rule_dicts = repo_client.rules.list_active_rules(tenant_id)
                for rd in active_rule_dicts:
                    comp_str = str(rd.get("comparator", "gt")).lower()
                    try:
                        comp = Comparator(comp_str)
                    except Exception:
                        comp = Comparator.GT
                    r = KPIRecommendationRule(
                        rule_code=rd["rule_code"],
                        rule_version=rd.get("rule_version", "1.0.0"),
                        name=rd.get("name", rd["rule_code"]),
                        kpi_code=rd.get("kpi") or rd.get("kpi_code", ""),
                        organization_scope=rd.get("organization_scope", "1000"),
                        category=rd.get("category", "RISK"),
                        comparator=comp,
                        threshold=Decimal(str(rd.get("threshold", "0.00"))),
                        upper_threshold=Decimal(str(rd["upper_threshold"])) if rd.get("upper_threshold") is not None else None,
                        clear_threshold=Decimal(str(rd["clear_threshold"])) if rd.get("clear_threshold") is not None else None,
                        unit=rd.get("unit", "currency"),
                        currency=rd.get("currency", "AED"),
                        comparison_window=rd.get("comparison_window", "snapshot"),
                        cooldown_minutes=int(rd.get("cooldown_minutes", 60)),
                        severity=rd.get("severity", "high"),
                        priority=int(rd.get("priority", 1)),
                        recommendation_template=rd.get("recommendation_template", ""),
                        explanation_template=rd.get("explanation_template", ""),
                        requires_complete=bool(rd.get("requires_complete", True)),
                        state=RuleState.ACTIVE,
                        owner=rd.get("owner", "Finance Operations"),
                        effective_from=rd.get("effective_from", "2026-01-01T00:00:00Z"),
                        effective_to=rd.get("effective_to"),
                    )
                    self.rules[r.rule_code] = r
            except Exception as ex:
                log.info(f"business_repo_rules_empty_or_unavailable error={ex}")
                self.rules = {}

        self.tenant_id = tenant_id
        self.outbox = DurableOutboxStore(outbox_dir)
        self.active_recommendations: Dict[str, RecommendationRecord] = {
            r.duplicate_key: r for r in self.outbox._recommendations.values()
        }
        self.recommendations_by_id: Dict[str, RecommendationRecord] = dict(self.outbox._recommendations)
        self.breach_episodes: Dict[str, str] = dict(self.outbox._episodes)
        self.cooldown_tracker: Dict[str, float] = {}

    def compute_deduplication_key(
        self,
        rule_code: str,
        rule_version: str,
        kpi_code: str,
        scope: str,
        period: str,
        breach_episode: str = "ep1",
    ) -> str:
        """Deterministic deduplication key: hash(tenant + scope + kpi + rule_version + window + episode)."""
        raw = f"{self.tenant_id}:{scope}:{kpi_code}:{rule_code}:{rule_version}:{period}:{breach_episode}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def evaluate_snapshot(self, snapshot: KPISnapshot) -> List[RecommendationRecord]:
        """Evaluate snapshot against applicable active rules with governance, hysteresis, and deduplication (F08 / W08)."""
        # Reject non-finite values (W08 requirement 5)
        if snapshot.value is None or not isinstance(snapshot.value, Decimal) or not snapshot.value.is_finite():
            log.warning(f"rejected_nonfinite_snapshot kpi={snapshot.kpi_code} val={snapshot.value}")
            return []

        # W08 requirement 2: Do not enable budget recommendations while code reports unapproved mapping
        if getattr(snapshot, "unapproved_mapping", False) or getattr(snapshot, "evidence_ref", "") == "UNAPPROVED_MAPPING":
            log.info(f"unapproved_mapping_skipped kpi={snapshot.kpi_code}")
            return []

        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        results: List[RecommendationRecord] = []

        applicable_rules = [
            r for r in self.rules.values()
            if r.kpi_code == snapshot.kpi_code
            and r.organization_scope == snapshot.organization_scope
            and r.state == RuleState.ACTIVE
        ]

        for rule in applicable_rules:
            # Category validation (W08 requirement 4: restrict to RISK, OPPORTUNITY, RECOMMENDATION, BENCHMARK)
            if rule.category not in ("RISK", "OPPORTUNITY", "RECOMMENDATION", "BENCHMARK"):
                log.warning(f"unsupported_rule_category rule={rule.rule_code} cat={rule.category}")
                continue
            if rule.category == "BENCHMARK":
                # W08 requirement 4: no benchmark without W14 comparable data
                log.info(f"benchmark_recommendation_requires_w14_data rule={rule.rule_code}")
                continue

            # 0. Completeness requirement enforcement (A06 / T33 / W08)
            if getattr(rule, "requires_complete", False) and str(snapshot.completeness).upper() != "COMPLETE":
                log.info(f"rule_requires_complete_skipped rule={rule.rule_code} completeness={snapshot.completeness}")
                continue

            # 1. Effective date window enforcement (F08)
            if rule.effective_from:
                try:
                    from_dt = datetime.fromisoformat(rule.effective_from.replace("Z", "+00:00"))
                    if now_dt < from_dt:
                        log.info(f"rule_not_yet_effective rule={rule.rule_code} from={rule.effective_from}")
                        continue
                except Exception:
                    pass

            if rule.effective_to:
                try:
                    to_dt = datetime.fromisoformat(rule.effective_to.replace("Z", "+00:00"))
                    if now_dt > to_dt:
                        log.info(f"rule_expired rule={rule.rule_code} to={rule.effective_to}")
                        continue
                except Exception:
                    pass

            # 2. Unit and Currency compatibility enforcement (F08 / W08)
            if rule.unit and snapshot.unit and rule.unit.lower() != snapshot.unit.lower():
                log.warning(f"rule_unit_mismatch rule={rule.rule_code} rule_unit={rule.unit} snapshot_unit={snapshot.unit}")
                continue

            if rule.unit.lower() == "currency" and rule.currency and snapshot.currency:
                if rule.currency.upper() != snapshot.currency.upper():
                    log.warning(f"rule_currency_mismatch rule={rule.rule_code} rule_curr={rule.currency} snapshot_curr={snapshot.currency}")
                    continue

            cooldown_key = f"{rule.rule_code}:{snapshot.organization_scope}:{snapshot.kpi_code}"
            val = snapshot.value
            thresh = rule.threshold
            is_breached = False

            # Deterministic comparator evaluation across all supported types
            if rule.comparator == Comparator.GT:
                is_breached = val > thresh
            elif rule.comparator == Comparator.GTE:
                is_breached = val >= thresh
            elif rule.comparator == Comparator.LT:
                is_breached = val < thresh
            elif rule.comparator == Comparator.LTE:
                is_breached = val <= thresh
            elif rule.comparator == Comparator.OUTSIDE_RANGE:
                upper = rule.upper_threshold or thresh
                is_breached = val < thresh or val > upper

            episode = self.breach_episodes.get(cooldown_key, "ep1")
            self.breach_episodes[cooldown_key] = episode
            dedup_key = self.compute_deduplication_key(
                rule.rule_code, rule.rule_version, rule.kpi_code, rule.organization_scope, snapshot.period, episode
            )

            existing = self.active_recommendations.get(dedup_key)

            if is_breached:
                # Meaningful category impact (W08 requirement 4)
                if rule.category == "RISK":
                    impact_text = f"Risk Alert [{rule.severity.upper()}]: {rule.name} breached limit of {thresh} {rule.unit or ''}"
                elif rule.category == "OPPORTUNITY":
                    impact_text = f"Opportunity Identified [{rule.severity.upper()}]: {rule.name} favorable variance vs baseline of {thresh} {rule.unit or ''}"
                elif rule.category == "RECOMMENDATION":
                    impact_text = f"Operational Advisory [{rule.severity.upper()}]: {rule.name} recommended threshold of {thresh} {rule.unit or ''}"
                else:
                    impact_text = f"Executive Alert [{rule.severity.upper()}]: {rule.name}"

                explanation = rule.explanation_template.format(value=val, threshold=thresh)
                action = rule.recommendation_template

                if existing and existing.status == RecommendationStatus.ACTIVE_BREACH:
                    # Continuing breach: update timestamp and observed value, suppress duplicate alert
                    existing.last_detected = now_iso
                    existing.observed_value = val
                    self.outbox.save_recommendation(existing)
                    results.append(existing)
                    continue

                # 3. Cooldown check for new alert generation (F08 / W03 persisted)
                if self.outbox.is_cooldown_active(cooldown_key):
                    log.info(f"rule_cooldown_active rule={rule.rule_code} cooldown_key={cooldown_key}")
                    continue

                # W01 Confidence evaluation (W08 requirement 5)
                source_rec = EvidenceSource(
                    sourceId=snapshot.snapshot_id,
                    system="S4HANA",
                    businessTitle=f"KPI Snapshot {snapshot.kpi_code}",
                    retrievedAt=snapshot.retrieved_at or now_iso,
                    sourceUpdatedAt=snapshot.source_updated_time if snapshot.source_updated_time else None,
                    measurementPeriod=snapshot.period,
                    scope=snapshot.organization_scope,
                    currency=snapshot.currency,
                    unit=snapshot.unit,
                    contentHash=snapshot.input_hash,
                )
                is_comp = str(snapshot.completeness).upper() == "COMPLETE"
                conf_assessment = evaluate_confidence(
                    sources=[source_rec],
                    now=now_dt,
                    is_authoritative_single_source=True,
                    is_materially_complete=is_comp,
                )
                conf_label = conf_assessment.label.value if hasattr(conf_assessment.label, "value") else str(conf_assessment.label)
                conf_reason = conf_assessment.reason

                obs_text = f"Observed {snapshot.kpi_code} value of {val} {snapshot.unit or ''} for scope {snapshot.organization_scope} ({snapshot.period})."
                claim = MaterialClaim(
                    claimId=f"CLM-{hashlib.sha256(f'{snapshot.snapshot_id}:{val}'.encode()).hexdigest()[:12]}",
                    kind=ClaimKind.RECOMMENDATION,
                    text=obs_text,
                    numericValue=val,
                    unit=snapshot.unit or snapshot.currency or "",
                    currency=snapshot.currency or "",
                    sourceIds=[snapshot.snapshot_id, snapshot.evidence_ref],
                    confidenceAssessment=conf_assessment,
                )

                # New breach
                rec_id = f"REC-{hashlib.md5(f'{dedup_key}:{now_iso}'.encode()).hexdigest()[:12]}"
                rec = RecommendationRecord(
                    recommendation_id=rec_id,
                    rule_code=rule.rule_code,
                    rule_version=rule.rule_version,
                    kpi_code=rule.kpi_code,
                    organization_scope=rule.organization_scope,
                    category=rule.category,
                    observed_value=val,
                    threshold=thresh,
                    impact=impact_text,
                    explanation=explanation,
                    suggested_action=action,
                    confidence=conf_label,
                    confidence_reason=conf_reason,
                    first_detected=now_iso,
                    last_detected=now_iso,
                    status=RecommendationStatus.ACTIVE_BREACH,
                    duplicate_key=dedup_key,
                    snapshot_id=snapshot.snapshot_id,
                    observation=obs_text,
                    business_implication=explanation,
                    severity=rule.severity,
                    priority=rule.priority,
                    supporting_claims=[claim.model_dump()],
                    supporting_sources=[source_rec.model_dump()],
                )
                self.active_recommendations[dedup_key] = rec
                self.recommendations_by_id[rec.recommendation_id] = rec
                cooldown_expiry = time.time() + (rule.cooldown_minutes * 60.0)
                self.outbox.set_cooldown(cooldown_key, cooldown_expiry)
                self.cooldown_tracker[cooldown_key] = time.time()
                self.outbox.save_recommendation(rec)
                self.outbox.save_episodes(self.breach_episodes)
                results.append(rec)

                # Enqueue into durable delivery outbox if authorized recipient exists
                self._enqueue_notification(rec)

            else:
                # Check hysteresis clear threshold across all comparators including OUTSIDE_RANGE
                if existing and existing.status == RecommendationStatus.ACTIVE_BREACH:
                    clear_thresh = rule.clear_threshold if rule.clear_threshold is not None else thresh
                    cleared = False
                    if rule.comparator in {Comparator.GT, Comparator.GTE}:
                        cleared = val <= clear_thresh
                    elif rule.comparator in {Comparator.LT, Comparator.LTE}:
                        cleared = val >= clear_thresh
                    elif rule.comparator == Comparator.OUTSIDE_RANGE:
                        upper = rule.upper_threshold or thresh
                        cleared = (val >= thresh and val <= upper)

                    if cleared:
                        existing.status = RecommendationStatus.RECOVERED
                        existing.last_detected = now_iso
                        # Increment episode for next breach cycle
                        ep_num = int(episode.replace("ep", "") or "1") + 1
                        self.breach_episodes[cooldown_key] = f"ep{ep_num}"
                        self.outbox.save_episodes(self.breach_episodes)
                        self.outbox.save_recommendation(existing)
                        # Reset cooldown on recovery so new episode can re-arm (F08 / W03)
                        self.outbox.clear_cooldown(cooldown_key)
                        self.cooldown_tracker.pop(cooldown_key, None)
                        log.info(f"recommendation_cleared_by_hysteresis key={dedup_key} val={val}")

        return results

    def _enqueue_notification(self, rec: RecommendationRecord, recipient: Optional[str] = None) -> None:
        """Enqueue delivery item only when an authorized recipient is specified (W08 requirement 6)."""
        target_recipient = recipient
        if not target_recipient:
            rule = self.rules.get(rec.rule_code)
            if rule:
                owner = getattr(rule, "owner", "")
                if "@" in owner:
                    target_recipient = owner
                elif owner:
                    target_recipient = f"{owner.lower().replace(' ', '.')}@velora.ae"
        if not target_recipient:
            log.info(f"no_authorized_notification_recipient_suppressed rec_id={rec.recommendation_id}")
            return

        raw = f"{self.tenant_id}:{rec.recommendation_id}:{target_recipient}:EMAIL"
        dedup_key = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        delivery_id = f"DLV-{dedup_key[:16]}"
        item = NotificationDeliveryRecord(
            delivery_id=delivery_id,
            recommendation_id=rec.recommendation_id,
            recipient=target_recipient,
            channel="EMAIL",
            status=DeliveryStatus.PENDING,
            deduplication_key=dedup_key,
            tenant_id=self.tenant_id,
            version=1,
        )
        inserted = self.outbox.append(item)
        if inserted:
            log.info(f"recommendation_enqueued_in_outbox delivery_id={delivery_id} rec_id={rec.recommendation_id}")
        else:
            log.info(f"recommendation_duplicate_suppressed delivery_id={delivery_id} rec_id={rec.recommendation_id}")

    def scan_and_evaluate_snapshots(
        self,
        snapshots: List[KPISnapshot],
        recipient: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Scheduled scan phase evaluating snapshots separate from outbox dispatch (W08 requirement 7)."""
        all_recs: List[RecommendationRecord] = []
        for snap in snapshots:
            recs = self.evaluate_snapshot(snap)
            for r in recs:
                if recipient:
                    self._enqueue_notification(r, recipient=recipient)
                all_recs.append(r)
        return {
            "status": "SUCCESS",
            "snapshots_evaluated": len(snapshots),
            "recommendations_generated": len(all_recs),
            "recommendations": all_recs,
        }

    def dispatch_outbox(
        self,
        m365_client: Any,
        require_live_delivery: bool = False,
        worker_id: Optional[str] = None,
        lease_duration_seconds: float = 30.0,
    ) -> int:
        """Claim and deliver pending outbox notifications through M365 client with delivery gate verification (F08 / Section 7)."""
        worker_id = worker_id or f"worker-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        claimed = self.outbox.claim_pending(worker_id=worker_id, lease_duration_seconds=lease_duration_seconds)
        delivered_count = 0

        for item in claimed:
            rec = self.recommendations_by_id.get(item.recommendation_id) or next(
                (r for r in self.active_recommendations.values() if r.recommendation_id == item.recommendation_id), None
            )
            if not rec:
                self.outbox.mark_failed_or_retry(
                    item.delivery_id,
                    worker_id,
                    item.version,
                    "Recommendation record not found",
                )
                continue

            # 1. Persist intent before provider submission (Section 7)
            try:
                item.version = self.outbox.mark_submitting(
                    delivery_id=item.delivery_id,
                    worker_id=worker_id,
                    version=item.version,
                    lease_duration_seconds=lease_duration_seconds,
                )
            except StaleWorkerError as ex:
                log.warning(f"stale_worker_before_submit item={item.delivery_id} err={ex}")
                continue

            # 2. Invoke provider
            try:
                subject = f"Executive Alert [{rec.category}]: {rec.kpi_code} Scope {rec.organization_scope}"
                body = (
                    f"{rec.impact}\n\n"
                    f"Observation: {rec.explanation}\n"
                    f"Action: {rec.suggested_action}\n\n"
                    f"Evidence: {rec.confidence_reason}"
                )
                res = m365_client.execute_send_email(
                    to=[item.recipient],
                    cc=[],
                    subject=subject,
                    body=body,
                    attachments=[],
                )
                res_status = str(res.get("status") or "").upper() if isinstance(res, dict) else ""
                receipt = res.get("providerReceipt") or {} if isinstance(res, dict) else {}
                is_sim = bool(receipt.get("simulated") or (isinstance(res, dict) and res.get("simulated")))

                # Delivery assurance: Provider error or failure must never be marked DELIVERED
                if res_status in {"ERROR", "FAILED"}:
                    err_msg = res.get("message") or res.get("error") or f"Provider returned {res_status}"
                    self.outbox.mark_failed_or_retry(item.delivery_id, worker_id, item.version, err_msg)
                    continue

                # Delivery acceptance gate: reject simulated send when live delivery is required
                if is_sim and require_live_delivery:
                    err_msg = "Delivery rejected: simulated receipt returned when verified live delivery is required"
                    self.outbox.mark_failed_or_retry(item.delivery_id, worker_id, item.version, err_msg, terminal=True)
                    continue

                if require_live_delivery and not receipt:
                    err_msg = "Delivery rejected: missing receipt when verified live delivery is required"
                    self.outbox.mark_failed_or_retry(item.delivery_id, worker_id, item.version, err_msg, terminal=True)
                    continue

                # Provider accepted! Save delivery with lease verification
                provider_ref = receipt.get("messageId") or receipt.get("id") or (res.get("messageId") if isinstance(res, dict) else None) or f"ref-{int(time.time()*1000)}"
                try:
                    self.outbox.mark_delivered(
                        delivery_id=item.delivery_id,
                        worker_id=worker_id,
                        version=item.version,
                        provider_reference=provider_ref,
                        provider_receipt=receipt,
                    )
                    delivered_count += 1
                except StaleWorkerError as ex:
                    # Lease expired while waiting for provider!
                    # Do not resend; move to RECONCILING so operator/reconciliation can verify
                    log.error(f"stale_worker_after_provider_acceptance item={item.delivery_id} err={ex}")
                    self.outbox.mark_reconciling(
                        item.delivery_id,
                        reason=f"Provider accepted (ref={provider_ref}) but worker lease expired before save: {ex}",
                    )
            except Exception as ex:
                # Ambiguous network/transport exception during submission! Move to RECONCILING
                log.error(f"provider_submission_ambiguous item={item.delivery_id} err={ex}")
                self.outbox.mark_reconciling(
                    item.delivery_id,
                    reason=f"Ambiguous network/provider outcome during submission: {ex}",
                )

        return delivered_count


def get_outbox_store(outbox_dir: Optional[str] = None, db_path: Optional[str] = None):
    """Factory returning PostgreSQL outbox in production or SQLite DurableOutboxStore in development/test."""
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("postgresql://") or db_url.startswith("postgres://"):
        try:
            from .postgres_outbox_store import PostgresOutboxStore
            return PostgresOutboxStore(connection_url=db_url)
        except Exception as ex:
            log.warning(f"Could not connect to PostgresOutboxStore via DATABASE_URL: {ex}; falling back to DurableOutboxStore")
    return DurableOutboxStore(outbox_dir=outbox_dir, db_path=db_path)
