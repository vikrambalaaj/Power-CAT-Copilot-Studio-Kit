"""Durable Transactional Operation & Approval Store for Velora Executive Platform.

Provides ACID conditional state transitions across multiple container replicas:
States:
  PREPARED -> APPROVED -> EXECUTING -> SUCCEEDED
  (plus EXPIRED, REJECTED, FAILED_BEFORE_SUBMISSION, OUTCOME_UNKNOWN)

Guarantees:
- Preparation stores the exact proposed operation server-side
- Verified confirmation binds user approval to the stored preview
- Execution loads approved payload from server-side record
- Atomic claim execution prevents duplicate execution across instances
- Safe replay: Retrying a SUCCEEDED operation returns previous result without re-executing
- Ambiguous timeouts after possible provider submission move to OUTCOME_UNKNOWN
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger("productivity_mcp.operation_store")


class OperationState(str, Enum):
    PREPARED = "PREPARED"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    FAILED_BEFORE_SUBMISSION = "FAILED_BEFORE_SUBMISSION"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


ALLOWED_OPERATION_MAPPINGS: Dict[str, str] = {
    "PREPARE_EMAIL": "SEND_EMAIL",
    "PREPAREEMAIL": "SEND_EMAIL",
    "SEND_APPROVED_EMAIL": "SEND_EMAIL",
    "SENDAPPROVEDEMAIL": "SEND_EMAIL",
    "PREPARE_EMAIL_REPLY": "REPLY_EMAIL",
    "SEND_APPROVED_EMAIL_REPLY": "REPLY_EMAIL",
    "PREPARE_MEETING_CREATION": "CREATE_MEETING",
    "CREATE_APPROVED_MEETING": "CREATE_MEETING",
    "PREPARE_MEETING_UPDATE": "UPDATE_MEETING",
    "UPDATE_APPROVED_MEETING": "UPDATE_MEETING",
    "PREPARE_MEETING_CANCELLATION": "CANCEL_MEETING",
    "CANCEL_APPROVED_MEETING": "CANCEL_MEETING",
    "PREPARE_TEAMS_CHAT_MESSAGE": "SEND_TEAMS_CHAT",
    "SEND_APPROVED_TEAMS_CHAT_MESSAGE": "SEND_TEAMS_CHAT",
    "PREPARE_TEAMS_CHANNEL_POST": "POST_TEAMS_CHANNEL",
    "SEND_APPROVED_TEAMS_CHANNEL_POST": "POST_TEAMS_CHANNEL",
    "PREPARE_PLANNER_TASK": "CREATE_PLANNER_TASK",
    "CREATE_APPROVED_PLANNER_TASK": "CREATE_PLANNER_TASK",
    "PREPARE_PLANNER_TASK_UPDATE": "UPDATE_PLANNER_TASK",
    "UPDATE_APPROVED_PLANNER_TASK": "UPDATE_PLANNER_TASK",
    "PREPARE_PLANNER_COMPLETION": "COMPLETE_PLANNER_TASK",
    "COMPLETE_APPROVED_PLANNER_TASK": "COMPLETE_PLANNER_TASK",
    "PREPARE_DAILY_BRIEFING_EMAIL": "SEND_DAILY_BRIEFING",
    "SEND_APPROVED_DAILY_BRIEFING_EMAIL": "SEND_DAILY_BRIEFING",
}


def normalize_operation_type(op: str) -> str:
    """Explicit allowed mapping for operations. Rejects unknown operations."""
    cleaned = op.strip().upper()
    if cleaned in ALLOWED_OPERATION_MAPPINGS:
        return ALLOWED_OPERATION_MAPPINGS[cleaned]
    # Direct canonical values
    canonical_values = set(ALLOWED_OPERATION_MAPPINGS.values())
    if cleaned in canonical_values:
        return cleaned
    raise ValueError(f"Unknown or unauthorized operation type: '{op}'")


def compute_payload_checksum(payload: Dict[str, Any]) -> str:
    """Deterministic SHA-256 checksum of preview payload, excluding volatile timestamp/tracking fields."""
    volatile = {"approvalExpiresOn", "expiresOn", "correlationId", "turnId", "confirmationToken"}
    filtered = {k: v for k, v in payload.items() if k not in volatile}
    canonical = json.dumps(filtered, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class OperationRecord:
    operation_id: str
    approval_id: str
    tenant_id: str
    user_object_id: str
    user_email: str
    operation_type: str
    payload_checksum: str
    proposed_payload: Dict[str, Any]
    policy_version: str
    state: str
    version: int
    expires_at: float
    created_at: str
    updated_at: str
    confirmed_by_oid: Optional[str] = None
    confirmed_at: Optional[str] = None
    claimed_by_owner: Optional[str] = None
    lease_expires_at: Optional[float] = None
    provider_reference: Optional[Dict[str, Any]] = None
    result_payload: Optional[Dict[str, Any]] = None
    last_error: Optional[str] = None


class SqliteOperationStore:
    """ACID Transactional store backed by SQLite with WAL mode for cross-replica / cross-process safety."""

    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            storage_base = (
                os.getenv("AZURE_STORAGE_MOUNT_PATH")
                or os.getenv("VELORA_OUTBOX_DIR")
                or os.getenv("FACILITATOR_STORAGE_DIR")
                or "/mnt/velora"
            )
            p = Path(storage_base)
            if not p.exists() and not storage_base.startswith("/mnt"):
                p.mkdir(parents=True, exist_ok=True)
            if p.exists():
                db_path = str(p / "velora_operations.db")
            else:
                local_dir = Path.home() / ".velora"
                local_dir.mkdir(parents=True, exist_ok=True)
                db_path = str(local_dir / "velora_operations.db")

        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=10000;")
        return conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS operations (
                    operation_id TEXT PRIMARY KEY,
                    approval_id TEXT UNIQUE NOT NULL,
                    tenant_id TEXT NOT NULL,
                    user_object_id TEXT NOT NULL,
                    user_email TEXT NOT NULL,
                    operation_type TEXT NOT NULL,
                    payload_checksum TEXT NOT NULL,
                    proposed_payload TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    state TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    expires_at REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    confirmed_by_oid TEXT,
                    confirmed_at TEXT,
                    claimed_by_owner TEXT,
                    lease_expires_at REAL,
                    provider_reference TEXT,
                    result_payload TEXT,
                    last_error TEXT
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_approval ON operations(approval_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_tenant_user ON operations(tenant_id, user_object_id);")
        finally:
            conn.close()

    def _row_to_record(self, row: sqlite3.Row) -> OperationRecord:
        return OperationRecord(
            operation_id=row["operation_id"],
            approval_id=row["approval_id"],
            tenant_id=row["tenant_id"],
            user_object_id=row["user_object_id"],
            user_email=row["user_email"],
            operation_type=row["operation_type"],
            payload_checksum=row["payload_checksum"],
            proposed_payload=json.loads(row["proposed_payload"]),
            policy_version=row["policy_version"],
            state=row["state"],
            version=row["version"],
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            confirmed_by_oid=row["confirmed_by_oid"],
            confirmed_at=row["confirmed_at"],
            claimed_by_owner=row["claimed_by_owner"],
            lease_expires_at=row["lease_expires_at"],
            provider_reference=json.loads(row["provider_reference"]) if row["provider_reference"] else None,
            result_payload=json.loads(row["result_payload"]) if row["result_payload"] else None,
            last_error=row["last_error"],
        )

    def prepare_operation(
        self,
        operation_type: str,
        tenant_id: str,
        user_object_id: str,
        user_email: str,
        proposed_payload: Dict[str, Any],
        approval_id: Optional[str] = None,
        expiry_minutes: int = 15,
        policy_version: str = "2026.1",
    ) -> OperationRecord:
        """Store exact proposed operation in PREPARED state."""
        if not tenant_id or not user_object_id:
            raise ValueError("Authenticated tenant_id and user_object_id are required")

        canonical_op = normalize_operation_type(operation_type)
        checksum = compute_payload_checksum(proposed_payload)
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        expires_at = now + (expiry_minutes * 60)

        op_id = str(uuid.uuid4())
        appr_id = approval_id or f"appr-{uuid.uuid4().hex}"

        conn = self._get_connection()
        try:
            conn.execute("""
                INSERT INTO operations (
                    operation_id, approval_id, tenant_id, user_object_id, user_email,
                    operation_type, payload_checksum, proposed_payload, policy_version,
                    state, version, expires_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?);
            """, (
                op_id, appr_id, tenant_id, user_object_id, user_email.strip().lower(),
                canonical_op, checksum, json.dumps(proposed_payload), policy_version,
                OperationState.PREPARED.value, expires_at, now_iso, now_iso
            ))
        finally:
            conn.close()

        return OperationRecord(
            operation_id=op_id,
            approval_id=appr_id,
            tenant_id=tenant_id,
            user_object_id=user_object_id,
            user_email=user_email.strip().lower(),
            operation_type=canonical_op,
            payload_checksum=checksum,
            proposed_payload=proposed_payload,
            policy_version=policy_version,
            state=OperationState.PREPARED.value,
            version=1,
            expires_at=expires_at,
            created_at=now_iso,
            updated_at=now_iso,
        )

    def confirm_approval(
        self,
        approval_id: str,
        user_object_id: str,
        tenant_id: str,
        current_preview_data: Optional[Dict[str, Any]] = None,
    ) -> OperationRecord:
        """Bind user approval to stored preview with checksum and identity validation."""
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()

        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM operations WHERE approval_id = ?;", (approval_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Approval operation '{approval_id}' not found")

            rec = self._row_to_record(row)

            # Expiry check
            if now > rec.expires_at:
                conn.execute(
                    "UPDATE operations SET state = ?, updated_at = ? WHERE approval_id = ?;",
                    (OperationState.EXPIRED.value, now_iso, approval_id)
                )
                raise ValueError(f"Approval '{approval_id}' has expired")

            # Identity binding
            if rec.tenant_id != tenant_id or rec.user_object_id != user_object_id:
                raise ValueError("Approval token presented by conflicting user or tenant identity")

            # Payload integrity
            if current_preview_data is not None:
                current_chk = compute_payload_checksum(current_preview_data)
                if current_chk != rec.payload_checksum:
                    raise ValueError("Proposed payload has changed since preview; new approval required")

            if rec.state != OperationState.PREPARED.value and rec.state != OperationState.APPROVED.value:
                raise ValueError(f"Cannot approve operation in state '{rec.state}'")

            # Transition PREPARED -> APPROVED
            conn.execute("""
                UPDATE operations
                SET state = ?, confirmed_by_oid = ?, confirmed_at = ?, version = version + 1, updated_at = ?
                WHERE approval_id = ? AND (state = ? OR state = ?);
            """, (
                OperationState.APPROVED.value, user_object_id, now_iso, now_iso,
                approval_id, OperationState.PREPARED.value, OperationState.APPROVED.value
            ))

            cursor = conn.execute("SELECT * FROM operations WHERE approval_id = ?;", (approval_id,))
            return self._row_to_record(cursor.fetchone())
        finally:
            conn.close()

    def claim_execution(
        self,
        approval_id: str,
        executor_id: str,
        presented_user_oid: str,
        presented_tenant_id: str,
        expected_operation: str,
        lease_seconds: float = 60.0,
    ) -> Tuple[bool, Optional[OperationRecord], str]:
        """Atomically claim operation for execution.
        
        Returns:
            (claimed, record, reason)
        """
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        lease_expires_at = now + lease_seconds

        canonical_expected = normalize_operation_type(expected_operation)

        conn = self._get_connection()
        try:
            # Transaction block
            conn.execute("BEGIN IMMEDIATE;")
            cursor = conn.execute("SELECT * FROM operations WHERE approval_id = ?;", (approval_id,))
            row = cursor.fetchone()
            if not row:
                conn.execute("COMMIT;")
                return False, None, "APPROVAL_NOT_FOUND"

            rec = self._row_to_record(row)

            # Check tenant and identity
            if rec.tenant_id != presented_tenant_id or rec.user_object_id != presented_user_oid:
                conn.execute("COMMIT;")
                return False, rec, "IDENTITY_MISMATCH"

            # Check operation match
            if rec.operation_type != canonical_expected:
                conn.execute("COMMIT;")
                return False, rec, "OPERATION_MISMATCH"

            # If already succeeded: return existing result for idempotent replay
            if rec.state == OperationState.SUCCEEDED.value:
                conn.execute("COMMIT;")
                return False, rec, "ALREADY_SUCCEEDED"

            # Expiry check
            if now > rec.expires_at:
                conn.execute(
                    "UPDATE operations SET state = ?, updated_at = ? WHERE approval_id = ?;",
                    (OperationState.EXPIRED.value, now_iso, approval_id)
                )
                conn.execute("COMMIT;")
                return False, rec, "APPROVAL_EXPIRED"

            # Eligible for claim: state must be APPROVED, OR (EXECUTING with expired lease)
            is_claimable = False
            if rec.state == OperationState.APPROVED.value:
                is_claimable = True
            elif rec.state == OperationState.EXECUTING.value:
                if rec.lease_expires_at and now > rec.lease_expires_at:
                    log.warning(f"Stealing expired execution lease for {approval_id} from {rec.claimed_by_owner}")
                    is_claimable = True
                else:
                    conn.execute("COMMIT;")
                    return False, rec, "CONCURRENTLY_EXECUTING"

            if not is_claimable:
                conn.execute("COMMIT;")
                return False, rec, f"INVALID_STATE_{rec.state}"

            cursor = conn.execute("""
                UPDATE operations
                SET state = ?, claimed_by_owner = ?, lease_expires_at = ?, version = version + 1, updated_at = ?
                WHERE approval_id = ? AND version = ?;
            """, (
                OperationState.EXECUTING.value, executor_id, lease_expires_at, now_iso,
                approval_id, rec.version
            ))

            if cursor.rowcount == 0:
                conn.execute("COMMIT;")
                return False, None, "CONCURRENT_MODIFICATION"

            conn.execute("COMMIT;")
            cursor = conn.execute("SELECT * FROM operations WHERE approval_id = ?;", (approval_id,))
            updated_rec = self._row_to_record(cursor.fetchone())
            return True, updated_rec, ""
        except Exception as exc:
            try:
                conn.execute("ROLLBACK;")
            except Exception:
                pass
            raise exc
        finally:
            conn.close()

    def complete_execution(
        self,
        operation_id: str,
        result_payload: Dict[str, Any],
        provider_reference: Dict[str, Any],
    ) -> None:
        """Atomically transition EXECUTING -> SUCCEEDED and store result evidence."""
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        try:
            conn.execute("""
                UPDATE operations
                SET state = ?, result_payload = ?, provider_reference = ?, updated_at = ?, version = version + 1
                WHERE operation_id = ?;
            """, (
                OperationState.SUCCEEDED.value,
                json.dumps(result_payload),
                json.dumps(provider_reference),
                now_iso,
                operation_id,
            ))
        finally:
            conn.close()

    def fail_execution(
        self,
        operation_id: str,
        error_message: str,
        before_submission: bool = True,
    ) -> None:
        """Transition to FAILED_BEFORE_SUBMISSION or OUTCOME_UNKNOWN (if provider submission timed out)."""
        now_iso = datetime.now(timezone.utc).isoformat()
        final_state = (
            OperationState.FAILED_BEFORE_SUBMISSION.value
            if before_submission
            else OperationState.OUTCOME_UNKNOWN.value
        )
        conn = self._get_connection()
        try:
            conn.execute("""
                UPDATE operations
                SET state = ?, last_error = ?, updated_at = ?, version = version + 1
                WHERE operation_id = ?;
            """, (final_state, error_message, now_iso, operation_id))
        finally:
            conn.close()

    def get_operation_by_approval_id(self, approval_id: str) -> Optional[OperationRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM operations WHERE approval_id = ?;", (approval_id,))
            row = cursor.fetchone()
            return self._row_to_record(row) if row else None
        finally:
            conn.close()


# Global operation store instance
_OPERATION_STORE: Optional[SqliteOperationStore] = None


def get_operation_store(db_path: Optional[str] = None) -> SqliteOperationStore:
    global _OPERATION_STORE
    if _OPERATION_STORE is None or db_path:
        _OPERATION_STORE = SqliteOperationStore(db_path=db_path)
    return _OPERATION_STORE
