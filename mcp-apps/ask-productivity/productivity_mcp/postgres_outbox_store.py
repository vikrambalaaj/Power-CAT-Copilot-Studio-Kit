"""Shared PostgreSQL Outbox and Run State Store for Velora Executive Platform (W03).

Provides multi-replica ACID delivery claiming via PostgreSQL row locking,
durable outbox event persistence, persistent cooldowns, and breach episode tracking.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .recommendation_engine import (
    DeliveryStatus,
    NotificationDeliveryRecord,
    RecommendationRecord,
    RecommendationStatus,
    StaleWorkerError,
)

log = logging.getLogger("productivity_mcp.postgres_outbox_store")


class PostgresOutboxStore:
    """Multi-replica production transactional outbox backed by PostgreSQL."""

    def __init__(self, connection_url: Optional[str] = None):
        self.connection_url = connection_url or os.getenv("DATABASE_URL", "")
        if not self.connection_url:
            raise ValueError("DATABASE_URL must be configured for PostgresOutboxStore")
        self._init_db()

    def _get_connection(self):
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            conn = psycopg2.connect(self.connection_url, cursor_factory=RealDictCursor)
            conn.autocommit = False
            return conn
        except ImportError:
            raise RuntimeError(
                "psycopg2 is required for PostgresOutboxStore in production. "
                "Ensure psycopg2-binary is installed or configure connection pool."
            )

    def _init_db(self) -> None:
        try:
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS notification_deliveries (
                            delivery_id VARCHAR(64) PRIMARY KEY,
                            deduplication_key VARCHAR(128) UNIQUE NOT NULL,
                            tenant_id VARCHAR(128) NOT NULL,
                            recommendation_id VARCHAR(64) NOT NULL,
                            recipient VARCHAR(256) NOT NULL,
                            channel VARCHAR(32) NOT NULL,
                            state VARCHAR(32) NOT NULL,
                            version INTEGER NOT NULL DEFAULT 1,
                            lease_owner VARCHAR(128),
                            lease_expiry DOUBLE PRECISION,
                            attempt_count INTEGER NOT NULL DEFAULT 0,
                            max_attempts INTEGER NOT NULL DEFAULT 3,
                            provider_reference TEXT,
                            last_error TEXT,
                            provider_receipt JSONB,
                            created_at VARCHAR(64) NOT NULL,
                            updated_at VARCHAR(64) NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_deliveries_claim 
                        ON notification_deliveries(state, lease_expiry);

                        CREATE TABLE IF NOT EXISTS recommendations (
                            recommendation_id VARCHAR(64) PRIMARY KEY,
                            duplicate_key VARCHAR(128) UNIQUE NOT NULL,
                            payload JSONB NOT NULL,
                            created_at VARCHAR(64) NOT NULL
                        );

                        CREATE TABLE IF NOT EXISTS breach_episodes (
                            episode_key VARCHAR(256) PRIMARY KEY,
                            episode_value VARCHAR(64) NOT NULL,
                            updated_at VARCHAR(64) NOT NULL
                        );

                        CREATE TABLE IF NOT EXISTS cooldowns (
                            cooldown_key VARCHAR(256) PRIMARY KEY,
                            expires_at DOUBLE PRECISION NOT NULL,
                            updated_at VARCHAR(64) NOT NULL
                        );
                    """)
                conn.commit()
            finally:
                conn.close()
        except Exception as ex:
            log.warning(f"postgres_outbox_db_init_warning error={ex}")

    def _row_to_record(self, row: Dict[str, Any]) -> NotificationDeliveryRecord:
        receipt = row.get("provider_receipt")
        if isinstance(receipt, str):
            try:
                receipt = json.loads(receipt)
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
            attempt_count=int(row["attempt_count"]),
            max_attempts=int(row["max_attempts"]),
            last_error=row.get("last_error"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            provider_receipt=receipt,
            version=int(row["version"]),
            lease_owner=row.get("lease_owner"),
            lease_expiry=float(row["lease_expiry"]) if row.get("lease_expiry") is not None else None,
            provider_reference=row.get("provider_reference"),
        )

    def enqueue(self, item: NotificationDeliveryRecord) -> bool:
        """Atomically insert or ignore delivery record using deduplication key."""
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                receipt_json = json.dumps(item.provider_receipt) if item.provider_receipt else None
                cur.execute("""
                    INSERT INTO notification_deliveries (
                        delivery_id, deduplication_key, tenant_id, recommendation_id,
                        recipient, channel, state, version, attempt_count, max_attempts,
                        last_error, provider_reference, provider_receipt, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (deduplication_key) DO NOTHING;
                """, (
                    item.delivery_id, item.deduplication_key, item.tenant_id, item.recommendation_id,
                    item.recipient, item.channel, item.status.value, item.version,
                    item.attempt_count, item.max_attempts, item.last_error,
                    item.provider_reference, receipt_json, item.created_at, now_iso
                ))
                inserted = cur.rowcount > 0
            conn.commit()
            return inserted
        except Exception as ex:
            conn.rollback()
            log.error(f"postgres_enqueue_failed error={ex}")
            raise
        finally:
            conn.close()

    def claim_pending(
        self,
        worker_id: str,
        lease_duration_seconds: float = 30.0,
        limit: int = 10,
    ) -> List[NotificationDeliveryRecord]:
        """Atomically claim eligible pending/expired-claimed deliveries using SELECT ... FOR UPDATE SKIP LOCKED."""
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        expiry = now + lease_duration_seconds
        claimed: List[NotificationDeliveryRecord] = []

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # 1. Reconcile any expired SUBMITTING tasks -> move to RECONCILING to prevent duplicate sends
                cur.execute("""
                    UPDATE notification_deliveries
                    SET state = %s, last_error = %s, version = version + 1, updated_at = %s
                    WHERE state = %s AND lease_expiry < %s;
                """, (
                    DeliveryStatus.RECONCILING.value,
                    "Lease expired while in SUBMITTING status; moving to RECONCILING to prevent duplicate dispatch",
                    now_iso,
                    DeliveryStatus.SUBMITTING.value,
                    now,
                ))

                # 2. Select candidates using row-level locking
                cur.execute("""
                    SELECT delivery_id, version
                    FROM notification_deliveries
                    WHERE ((state = %s AND attempt_count < max_attempts)
                       OR (state = %s AND lease_expiry < %s AND attempt_count < max_attempts))
                    ORDER BY created_at ASC
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED;
                """, (DeliveryStatus.PENDING.value, DeliveryStatus.CLAIMED.value, now, limit))
                candidates = cur.fetchall()

                for row in candidates:
                    d_id = row["delivery_id"]
                    v = row["version"]
                    cur.execute("""
                        UPDATE notification_deliveries
                        SET state = %s, lease_owner = %s, lease_expiry = %s,
                            attempt_count = attempt_count + 1, version = version + 1,
                            updated_at = %s
                        WHERE delivery_id = %s AND version = %s;
                    """, (DeliveryStatus.CLAIMED.value, worker_id, expiry, now_iso, d_id, v))
                    if cur.rowcount > 0:
                        cur.execute("SELECT * FROM notification_deliveries WHERE delivery_id = %s;", (d_id,))
                        rec_row = cur.fetchone()
                        if rec_row:
                            claimed.append(self._row_to_record(rec_row))

            conn.commit()
            return claimed
        except Exception as ex:
            conn.rollback()
            log.error(f"postgres_claim_pending_failed error={ex}")
            raise
        finally:
            conn.close()

    def mark_submitting(
        self,
        item: NotificationDeliveryRecord,
        worker_id: str,
        lease_duration_seconds: float = 30.0,
    ) -> None:
        """Transition CLAIMED -> SUBMITTING under active lease."""
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        expiry = now + lease_duration_seconds

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE notification_deliveries
                    SET state = %s, lease_owner = %s, lease_expiry = %s,
                        version = version + 1, updated_at = %s
                    WHERE delivery_id = %s AND lease_owner = %s AND version = %s;
                """, (DeliveryStatus.SUBMITTING.value, worker_id, expiry, now_iso, item.delivery_id, worker_id, item.version))
                if cur.rowcount == 0:
                    raise StaleWorkerError(f"Worker {worker_id} lost lease on {item.delivery_id}")
            conn.commit()
            item.status = DeliveryStatus.SUBMITTING
            item.version += 1
            item.lease_expiry = expiry
            item.updated_at = now_iso
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def mark_submitted(
        self,
        item: NotificationDeliveryRecord,
        worker_id: str,
        provider_reference: Optional[str] = None,
        provider_receipt: Optional[Dict[str, Any]] = None,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE notification_deliveries
                    SET state = %s, provider_reference = %s, provider_receipt = %s,
                        version = version + 1, updated_at = %s
                    WHERE delivery_id = %s AND lease_owner = %s;
                """, (
                    DeliveryStatus.SUBMITTED.value, provider_reference,
                    json.dumps(provider_receipt) if provider_receipt else None,
                    now_iso, item.delivery_id, worker_id
                ))
            conn.commit()
            item.status = DeliveryStatus.SUBMITTED
            item.version += 1
            item.provider_reference = provider_reference
            item.provider_receipt = provider_receipt
            item.updated_at = now_iso
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def mark_delivered(
        self,
        item: NotificationDeliveryRecord,
        worker_id: str,
        provider_receipt: Optional[Dict[str, Any]] = None,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE notification_deliveries
                    SET state = %s, provider_receipt = %s, version = version + 1, updated_at = %s
                    WHERE delivery_id = %s AND lease_owner = %s;
                """, (
                    DeliveryStatus.DELIVERED.value,
                    json.dumps(provider_receipt) if provider_receipt else None,
                    now_iso, item.delivery_id, worker_id
                ))
            conn.commit()
            item.status = DeliveryStatus.DELIVERED
            item.version += 1
            item.provider_receipt = provider_receipt
            item.updated_at = now_iso
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def mark_failed(
        self,
        item: NotificationDeliveryRecord,
        worker_id: str,
        error_message: str,
        can_retry: bool = True,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        next_state = DeliveryStatus.PENDING.value if (can_retry and item.attempt_count < item.max_attempts) else DeliveryStatus.FAILED.value
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE notification_deliveries
                    SET state = %s, last_error = %s, version = version + 1, updated_at = %s
                    WHERE delivery_id = %s AND lease_owner = %s;
                """, (next_state, error_message, now_iso, item.delivery_id, worker_id))
            conn.commit()
            item.status = DeliveryStatus(next_state)
            item.last_error = error_message
            item.version += 1
            item.updated_at = now_iso
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def mark_reconciling(
        self,
        item: NotificationDeliveryRecord,
        worker_id: str,
        error_message: str,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE notification_deliveries
                    SET state = %s, last_error = %s, version = version + 1, updated_at = %s
                    WHERE delivery_id = %s AND lease_owner = %s;
                """, (DeliveryStatus.RECONCILING.value, error_message, now_iso, item.delivery_id, worker_id))
            conn.commit()
            item.status = DeliveryStatus.RECONCILING
            item.last_error = error_message
            item.version += 1
            item.updated_at = now_iso
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def save_recommendation(self, rec: RecommendationRecord) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "recommendation_id": rec.recommendation_id,
            "rule_code": rec.rule_code,
            "rule_version": rec.rule_version,
            "kpi_code": rec.kpi_code,
            "organization_scope": rec.organization_scope,
            "category": rec.category,
            "observed_value": str(rec.observed_value),
            "threshold": str(rec.threshold),
            "impact": rec.impact,
            "explanation": rec.explanation,
            "suggested_action": rec.suggested_action,
            "confidence": rec.confidence,
            "confidence_reason": rec.confidence_reason,
            "first_detected": rec.first_detected,
            "last_detected": rec.last_detected,
            "status": rec.status.value,
            "duplicate_key": rec.duplicate_key,
            "snapshot_id": rec.snapshot_id,
        }
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO recommendations (recommendation_id, duplicate_key, payload, created_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (duplicate_key) DO UPDATE
                    SET payload = EXCLUDED.payload;
                """, (rec.recommendation_id, rec.duplicate_key, json.dumps(payload), now_iso))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_recommendation(self, rec_id: str) -> Optional[RecommendationRecord]:
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM recommendations WHERE recommendation_id = %s;", (rec_id,))
                row = cur.fetchone()
                if not row:
                    return None
                data = row["payload"]
                if isinstance(data, str):
                    data = json.loads(data)
                return self._dict_to_recommendation(data)
        finally:
            conn.close()

    def get_recommendation_by_duplicate_key(self, dup_key: str) -> Optional[RecommendationRecord]:
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM recommendations WHERE duplicate_key = %s;", (dup_key,))
                row = cur.fetchone()
                if not row:
                    return None
                data = row["payload"]
                if isinstance(data, str):
                    data = json.loads(data)
                return self._dict_to_recommendation(data)
        finally:
            conn.close()

    def _dict_to_recommendation(self, data: Dict[str, Any]) -> RecommendationRecord:
        return RecommendationRecord(
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
            confidence=data["confidence"],
            confidence_reason=data["confidence_reason"],
            first_detected=data["first_detected"],
            last_detected=data["last_detected"],
            status=RecommendationStatus(data["status"]),
            duplicate_key=data["duplicate_key"],
            snapshot_id=data["snapshot_id"],
        )

    def set_breach_episode(self, episode_key: str, episode_value: str) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO breach_episodes (episode_key, episode_value, updated_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (episode_key) DO UPDATE
                    SET episode_value = EXCLUDED.episode_value, updated_at = EXCLUDED.updated_at;
                """, (episode_key, episode_value, now_iso))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_breach_episode(self, episode_key: str) -> Optional[str]:
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT episode_value FROM breach_episodes WHERE episode_key = %s;", (episode_key,))
                row = cur.fetchone()
                return row["episode_value"] if row else None
        finally:
            conn.close()

    def set_cooldown(self, cooldown_key: str, expires_at: float) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO cooldowns (cooldown_key, expires_at, updated_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (cooldown_key) DO UPDATE
                    SET expires_at = EXCLUDED.expires_at, updated_at = EXCLUDED.updated_at;
                """, (cooldown_key, expires_at, now_iso))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def is_cooldown_active(self, cooldown_key: str, now: Optional[float] = None) -> bool:
        check_time = now if now is not None else time.time()
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT expires_at FROM cooldowns WHERE cooldown_key = %s;", (cooldown_key,))
                row = cur.fetchone()
                if not row:
                    return False
                return float(row["expires_at"]) > check_time
        finally:
            conn.close()

    def get_cooldown(self, cooldown_key: str) -> Optional[float]:
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT expires_at FROM cooldowns WHERE cooldown_key = %s;", (cooldown_key,))
                row = cur.fetchone()
                return float(row["expires_at"]) if row else None
        finally:
            conn.close()

    def clear_cooldown(self, cooldown_key: str) -> None:
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM cooldowns WHERE cooldown_key = %s;", (cooldown_key,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def clear_all_for_testing(self) -> None:
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM notification_deliveries;")
                cur.execute("DELETE FROM recommendations;")
                cur.execute("DELETE FROM breach_episodes;")
                cur.execute("DELETE FROM cooldowns;")
            conn.commit()
        finally:
            conn.close()
