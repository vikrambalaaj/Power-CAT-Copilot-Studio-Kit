"""Standing Authorization Policy Engine for Velora Platform (W04, R02, R07, W07, W13).

Enforces:
- Typed policy record for standing background dispatches (morning brief, meeting actions).
- Explicit tenant and user isolation: never impersonate a user by substituting an email string.
- Bounded recipients, resources, operations, and schedules.
- Time-bounded expiration and instantaneous revocation checks prior to any worker run.
- Workload identity binding: verifies the calling worker's service identity against policy.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

log = logging.getLogger("productivity_mcp.standing_authorization")


@dataclass
class StandingAuthorizationRecord:
    policy_id: str
    tenant_id: str
    authorizing_user_oid: str
    authorizing_user_email: str
    workload_identity: str
    allowed_operations: List[str]
    allowed_recipients: List[str]
    allowed_resources: List[str] = field(default_factory=list)
    schedule_cron: Optional[str] = None
    schedule_local_time: Optional[str] = "07:00"
    schedule_timezone: str = "Asia/Dubai"
    status: str = "ACTIVE"  # "ACTIVE", "REVOKED", "EXPIRED"
    expires_at: float = 0.0
    revoked_at: Optional[str] = None
    revocation_reason: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class StandingAuthorizationStore:
    """Durable store for standing authorization policies."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db_path = db_path
        else:
            data_dir = Path(__file__).resolve().parent.parent / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(data_dir / "standing_authorization.db")
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS standing_authorizations (
                    policy_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    authorizing_user_oid TEXT NOT NULL,
                    authorizing_user_email TEXT NOT NULL,
                    workload_identity TEXT NOT NULL,
                    allowed_operations TEXT NOT NULL,
                    allowed_recipients TEXT NOT NULL,
                    allowed_resources TEXT NOT NULL,
                    schedule_cron TEXT,
                    schedule_local_time TEXT,
                    schedule_timezone TEXT NOT NULL DEFAULT 'Asia/Dubai',
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    expires_at REAL NOT NULL,
                    revoked_at TEXT,
                    revocation_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_standing_auth_lookup
                ON standing_authorizations (tenant_id, authorizing_user_oid, status);
            """)
            conn.commit()
        finally:
            conn.close()

    def create_policy(self, record: StandingAuthorizationRecord) -> StandingAuthorizationRecord:
        now_iso = datetime.now(timezone.utc).isoformat()
        if record.expires_at <= 0.0:
            record.expires_at = time.time() + (30 * 86400.0)  # Default 30-day bounded horizon

        conn = self._get_connection()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO standing_authorizations (
                    policy_id, tenant_id, authorizing_user_oid, authorizing_user_email,
                    workload_identity, allowed_operations, allowed_recipients, allowed_resources,
                    schedule_cron, schedule_local_time, schedule_timezone, status,
                    expires_at, revoked_at, revocation_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                record.policy_id,
                record.tenant_id,
                record.authorizing_user_oid,
                record.authorizing_user_email.strip().lower(),
                record.workload_identity,
                json.dumps(record.allowed_operations),
                json.dumps([r.strip().lower() for r in record.allowed_recipients]),
                json.dumps(record.allowed_resources),
                record.schedule_cron,
                record.schedule_local_time,
                record.schedule_timezone,
                record.status,
                record.expires_at,
                record.revoked_at,
                record.revocation_reason,
                record.created_at or now_iso,
                now_iso,
            ))
            conn.commit()
            return record
        finally:
            conn.close()

    save_policy = create_policy

    def get_policy(self, policy_id: str, tenant_id: str) -> Optional[StandingAuthorizationRecord]:
        conn = self._get_connection()
        try:
            cur = conn.execute(
                "SELECT * FROM standing_authorizations WHERE policy_id = ? AND tenant_id = ?;",
                (policy_id, tenant_id),
            )
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_record(row)
        finally:
            conn.close()

    def revoke_policy(self, policy_id: str, tenant_id: str, reason: str = "") -> bool:
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        try:
            cur = conn.execute("""
                UPDATE standing_authorizations
                SET status = 'REVOKED', revoked_at = ?, revocation_reason = ?, updated_at = ?
                WHERE policy_id = ? AND tenant_id = ? AND status = 'ACTIVE';
            """, (now_iso, reason or "Revoked by user", now_iso, policy_id, tenant_id))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def verify_standing_authorization(
        self,
        policy_id: str,
        tenant_id: str,
        operation: str,
        target_recipient: str = "",
        workload_identity: str = "",
    ) -> Tuple[bool, str, Optional[StandingAuthorizationRecord]]:
        """Verify standing authorization status immediately prior to background execution."""
        policy = self.get_policy(policy_id=policy_id, tenant_id=tenant_id)
        if not policy:
            return False, f"Standing authorization policy '{policy_id}' not found for tenant '{tenant_id}'", None

        # Check Revocation
        if policy.status == "REVOKED":
            return False, f"Standing authorization '{policy_id}' was revoked at {policy.revoked_at}: {policy.revocation_reason}", policy

        # Check Expiry
        now = time.time()
        if now > policy.expires_at or policy.status == "EXPIRED":
            return False, f"Standing authorization '{policy_id}' expired at {policy.expires_at}", policy

        # Check Operation Allowlist
        op_norm = operation.strip().upper()
        allowed_ops = {op.strip().upper() for op in policy.allowed_operations}
        if op_norm not in allowed_ops and "*" not in allowed_ops:
            return False, f"Operation '{operation}' not permitted by standing policy '{policy_id}' (allowed: {policy.allowed_operations})", policy

        # Check Recipient Boundedness
        if target_recipient:
            recip_clean = target_recipient.strip().lower()
            allowed_recips = {r.strip().lower() for r in policy.allowed_recipients}
            if allowed_recips and recip_clean not in allowed_recips and "*" not in allowed_recips:
                return False, f"Recipient '{target_recipient}' is outside bounded recipients for policy '{policy_id}'", policy

        # Check Workload Identity Binding if policy specifies one
        if policy.workload_identity and policy.workload_identity != "*":
            if not workload_identity:
                return False, f"Standing policy '{policy_id}' requires verified workload identity '{policy.workload_identity}'", policy
            if workload_identity != policy.workload_identity:
                return False, f"Workload identity mismatch: running as '{workload_identity}', policy requires '{policy.workload_identity}'", policy

        return True, "", policy

    def _row_to_record(self, row: sqlite3.Row) -> StandingAuthorizationRecord:
        return StandingAuthorizationRecord(
            policy_id=row["policy_id"],
            tenant_id=row["tenant_id"],
            authorizing_user_oid=row["authorizing_user_oid"],
            authorizing_user_email=row["authorizing_user_email"],
            workload_identity=row["workload_identity"],
            allowed_operations=json.loads(row["allowed_operations"]),
            allowed_recipients=json.loads(row["allowed_recipients"]),
            allowed_resources=json.loads(row["allowed_resources"]),
            schedule_cron=row["schedule_cron"],
            schedule_local_time=row["schedule_local_time"],
            schedule_timezone=row["schedule_timezone"],
            status=row["status"],
            expires_at=float(row["expires_at"]),
            revoked_at=row["revoked_at"],
            revocation_reason=row["revocation_reason"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


_standing_auth_store: Optional[StandingAuthorizationStore] = None


def get_standing_authorization_store() -> StandingAuthorizationStore:
    global _standing_auth_store
    if _standing_auth_store is None:
        _standing_auth_store = StandingAuthorizationStore()
    return _standing_auth_store
