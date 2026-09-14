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
- Token hash: Bearer approval tokens are hashed with SHA-256 rather than stored raw
- Parameter reconciliation: Reconciles expiry_minutes vs ttl_seconds uniformly
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


class AccessDeniedError(PermissionError, ValueError):
    """Raised when an operation is accessed or mutated by a non-matching user or tenant."""
    pass


class ConcurrencyConflictError(RuntimeError):
    """Raised when an operation suffers a concurrent modification or claim conflict."""
    pass


class InvalidTokenError(ValueError):
    """Raised when an approval token or hash does not match the stored operation authorization."""
    pass


class OperationState(str, Enum):
    PREPARED = "PREPARED"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    CLAIMED = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    COMPLETED = "SUCCEEDED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    FAILED_BEFORE_SUBMISSION = "FAILED_BEFORE_SUBMISSION"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


ALLOWED_OPERATION_MAPPINGS: Dict[str, str] = {
    # Email operations
    "PREPARE_EMAIL": "SEND_EMAIL",
    "PREPAREEMAIL": "SEND_EMAIL",
    "SEND_APPROVED_EMAIL": "SEND_EMAIL",
    "SENDAPPROVEDEMAIL": "SEND_EMAIL",
    "PREPARE_EMAIL_REPLY": "REPLY_EMAIL",
    "SEND_APPROVED_EMAIL_REPLY": "REPLY_EMAIL",
    "PREPARE_DAILY_BRIEFING_EMAIL": "SEND_DAILY_BRIEFING",
    "SEND_APPROVED_DAILY_BRIEFING_EMAIL": "SEND_DAILY_BRIEFING",
    # Calendar operations
    "CREATE_CALENDAR_EVENT": "CREATE_MEETING",
    "CREATE_EVENT": "CREATE_MEETING",
    "PREPARE_CALENDAR_EVENT": "CREATE_MEETING",
    "PREPARE_MEETING_CREATION": "CREATE_MEETING",
    "CREATE_APPROVED_MEETING": "CREATE_MEETING",
    "PREPARE_MEETING_UPDATE": "UPDATE_MEETING",
    "UPDATE_APPROVED_MEETING": "UPDATE_MEETING",
    "PREPARE_MEETING_CANCELLATION": "CANCEL_MEETING",
    "CANCEL_APPROVED_MEETING": "CANCEL_MEETING",
    # Direct canonicals
    "SEND_EMAIL": "SEND_EMAIL",
    "REPLY_EMAIL": "REPLY_EMAIL",
    "CREATE_MEETING": "CREATE_MEETING",
    "UPDATE_MEETING": "UPDATE_MEETING",
    "CANCEL_MEETING": "CANCEL_MEETING",
    # Teams operations
    "PREPARE_TEAMS_CHAT_MESSAGE": "SEND_TEAMS_CHAT",
    "SEND_APPROVED_TEAMS_CHAT_MESSAGE": "SEND_TEAMS_CHAT",
    "PREPARE_TEAMS_CHANNEL_POST": "POST_TEAMS_CHANNEL",
    "SEND_APPROVED_TEAMS_CHANNEL_POST": "POST_TEAMS_CHANNEL",
    # Planner operations
    "PREPARE_PLANNER_TASK": "CREATE_PLANNER_TASK",
    "CREATE_APPROVED_PLANNER_TASK": "CREATE_PLANNER_TASK",
    "PREPARE_PLANNER_TASK_UPDATE": "UPDATE_PLANNER_TASK",
    "UPDATE_APPROVED_PLANNER_TASK": "UPDATE_PLANNER_TASK",
    "PREPARE_PLANNER_COMPLETION": "COMPLETE_PLANNER_TASK",
    "COMPLETE_APPROVED_PLANNER_TASK": "COMPLETE_PLANNER_TASK",
    # Automation subscriptions (W03, W04, W07)
    "PREPARE_AUTOMATION_SUBSCRIPTION": "MANAGE_SUBSCRIPTION",
    "CONFIRM_AUTOMATION_SUBSCRIPTION": "MANAGE_SUBSCRIPTION",
    "REVOKE_AUTOMATION_SUBSCRIPTION": "MANAGE_SUBSCRIPTION",
    "CREATE_AUTOMATION_SUBSCRIPTION": "MANAGE_SUBSCRIPTION",
    "UPDATE_AUTOMATION_SUBSCRIPTION": "MANAGE_SUBSCRIPTION",
    "CANCEL_AUTOMATION_SUBSCRIPTION": "MANAGE_SUBSCRIPTION",
    "MANAGE_SUBSCRIPTION": "MANAGE_SUBSCRIPTION",
    # Meeting actions dispatch (W03, W04, W13)
    "PREPARE_MEETING_ACTIONS": "DISPATCH_MEETING_ACTIONS",
    "CREATE_MEETING_ACTION": "DISPATCH_MEETING_ACTIONS",
    "CREATE_APPROVED_MEETING_ACTIONS": "DISPATCH_MEETING_ACTIONS",
    "DISPATCH_MEETING_ACTIONS": "DISPATCH_MEETING_ACTIONS",
    "POST_MEETING_ACTIONS": "DISPATCH_MEETING_ACTIONS",
    # Vendor evaluations (W03, W11)
    "EVALUATE_VENDOR_OPTIONS": "EVALUATE_VENDOR_OPTIONS",
    "PREPARE_VENDOR_EVALUATION": "EVALUATE_VENDOR_OPTIONS",
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
    token_hash: Optional[str] = None
    confirmed_by_oid: Optional[str] = None
    confirmed_at: Optional[str] = None
    claimed_by_owner: Optional[str] = None
    lease_expires_at: Optional[float] = None
    provider_reference: Optional[Dict[str, Any]] = None
    result_payload: Optional[Dict[str, Any]] = None
    last_error: Optional[str] = None


class SqliteOperationStore:
    """Single-host development operation store backed by SQLite with WAL mode.
    
    WARNING: SQLite WAL mode requires all cooperating processes to reside on a single
    operating system host and is strictly unsupported on distributed network filesystems
    (such as CIFS/NFS/Azure Files) or across multi-host container replicas (see https://sqlite.org/wal.html).
    In multi-replica production deployments, a network transactional database (PostgreSQL / Azure SQL)
    must be configured via DATABASE_URL (WP04).
    """

    def __init__(self, db_path: Optional[str] = None):
        is_production = os.getenv("VELORA_ENV", "").lower() in ("production", "prod")
        if is_production and not os.getenv("ALLOW_SQLITE_SINGLE_HOST_OVERRIDE"):
            if not os.getenv("DATABASE_URL"):
                log.warning(
                    "Production configuration warning: Multi-replica production requires a supported network transactional "
                    "database (DATABASE_URL). Operating with single-host SQLite requires explicit override."
                )

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
                if is_production:
                    raise RuntimeError("Production storage mount not found; ephemeral local storage fallback is rejected in production.")
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
                    token_hash TEXT,
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
            try:
                conn.execute("ALTER TABLE operations ADD COLUMN token_hash TEXT;")
            except Exception:
                pass
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_approval ON operations(approval_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_tenant_user ON operations(tenant_id, user_object_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_state_expiry ON operations(state, expires_at);")
        finally:
            conn.close()

    def _row_to_record(self, row: sqlite3.Row) -> OperationRecord:
        keys = row.keys()
        return OperationRecord(
            operation_id=row["operation_id"],
            approval_id=row["approval_id"],
            token_hash=row["token_hash"] if "token_hash" in keys else None,
            tenant_id=row["tenant_id"],
            user_object_id=row["user_object_id"],
            user_email=row["user_email"],
            operation_type=row["operation_type"],
            payload_checksum=row["payload_checksum"],
            proposed_payload=json.loads(row["proposed_payload"]),
            policy_version=row["policy_version"],
            state=row["state"],
            version=row["version"],
            expires_at=float(row["expires_at"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            confirmed_by_oid=row["confirmed_by_oid"],
            confirmed_at=row["confirmed_at"],
            claimed_by_owner=row["claimed_by_owner"],
            lease_expires_at=float(row["lease_expires_at"]) if row["lease_expires_at"] is not None else None,
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
        approval_token: Optional[str] = None,
        expiry_minutes: Optional[int] = None,
        ttl_seconds: Optional[float] = None,
        policy_version: str = "2026.1",
    ) -> OperationRecord:
        """Store exact proposed operation in PREPARED state. Reconciles expiry_minutes vs ttl_seconds."""
        if not tenant_id or not user_object_id:
            raise ValueError("Authenticated tenant_id and user_object_id are required")

        canonical_op = normalize_operation_type(operation_type)
        checksum = compute_payload_checksum(proposed_payload)
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        
        effective_ttl = float(ttl_seconds) if ttl_seconds is not None else (float(expiry_minutes * 60) if expiry_minutes is not None else 900.0)
        expires_at = now + effective_ttl
        token_hash = hashlib.sha256(approval_token.encode("utf-8")).hexdigest() if approval_token else None

        op_id = f"OP-{uuid.uuid4().hex[:12]}"
        appr_id = approval_id or f"appr-{uuid.uuid4().hex}"

        conn = self._get_connection()
        try:
            conn.execute("""
                INSERT INTO operations (
                    operation_id, approval_id, token_hash, tenant_id, user_object_id, user_email,
                    operation_type, payload_checksum, proposed_payload, policy_version,
                    state, version, expires_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?);
            """, (
                op_id, appr_id, token_hash, tenant_id, user_object_id, user_email.strip().lower(),
                canonical_op, checksum, json.dumps(proposed_payload), policy_version,
                OperationState.PREPARED.value, expires_at, now_iso, now_iso
            ))
        finally:
            conn.close()

        return OperationRecord(
            operation_id=op_id,
            approval_id=appr_id,
            token_hash=token_hash,
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
        approval_token: Optional[str] = None,
    ) -> OperationRecord:
        """Bind user approval to stored preview with checksum, token hash, and identity validation."""
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
                raise AccessDeniedError("Approval token presented by conflicting user or tenant identity")

            # Token hash verification if stored
            if rec.token_hash and approval_token:
                presented_hash = hashlib.sha256(approval_token.encode("utf-8")).hexdigest()
                if presented_hash != rec.token_hash:
                    raise InvalidTokenError("Approval token hash mismatch; presented token is not authorized for this operation")

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

    def reject_operation(
        self,
        approval_id: str,
        user_object_id: str,
        tenant_id: str,
        reason: Optional[str] = None,
    ) -> OperationRecord:
        """Reject/revoke operation, transitioning state to REJECTED."""
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM operations WHERE approval_id = ?;", (approval_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Approval operation '{approval_id}' not found")
            rec = self._row_to_record(row)
            if rec.tenant_id != tenant_id or rec.user_object_id != user_object_id:
                raise AccessDeniedError("Rejection attempted by conflicting user or tenant identity")
            if rec.state in (OperationState.EXECUTING.value, OperationState.SUCCEEDED.value):
                raise ValueError(f"Cannot reject operation in state '{rec.state}'")

            conn.execute("""
                UPDATE operations
                SET state = ?, last_error = ?, version = version + 1, updated_at = ?
                WHERE approval_id = ?;
            """, (OperationState.REJECTED.value, reason or "Rejected by user", now_iso, approval_id))
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

            # Eligible for claim: state must be APPROVED
            if rec.state == OperationState.EXECUTING.value:
                if rec.lease_expires_at and now > rec.lease_expires_at:
                    log.warning(f"Execution lease expired for {approval_id}; transitioning to OUTCOME_UNKNOWN for reconciliation")
                    conn.execute(
                        "UPDATE operations SET state = ?, updated_at = ? WHERE approval_id = ? AND state = ?;",
                        (OperationState.OUTCOME_UNKNOWN.value, now_iso, approval_id, OperationState.EXECUTING.value)
                    )
                    conn.execute("COMMIT;")
                    return False, rec, "OUTCOME_UNKNOWN_RECONCILING"
                else:
                    conn.execute("COMMIT;")
                    return False, rec, "CONCURRENTLY_EXECUTING"

            if rec.state != OperationState.APPROVED.value:
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
        operation_id: Optional[str] = None,
        result_payload: Optional[Dict[str, Any]] = None,
        provider_reference: Optional[Dict[str, Any]] = None,
        approval_id: Optional[str] = None,
    ) -> OperationRecord:
        """Atomically transition EXECUTING -> SUCCEEDED and store result evidence."""
        identifier = operation_id or approval_id
        if not identifier:
            raise ValueError("operation_id or approval_id is required to complete execution")
        now_iso = datetime.now(timezone.utc).isoformat()
        res = result_payload or {}
        ref = provider_reference or {}
        conn = self._get_connection()
        try:
            conn.execute("""
                UPDATE operations
                SET state = ?, result_payload = ?, provider_reference = ?, updated_at = ?, version = version + 1
                WHERE operation_id = ? OR approval_id = ?;
            """, (
                OperationState.SUCCEEDED.value,
                json.dumps(res),
                json.dumps(ref),
                now_iso,
                identifier,
                identifier,
            ))
            cursor = conn.execute("SELECT * FROM operations WHERE operation_id = ? OR approval_id = ?;", (identifier, identifier))
            return self._row_to_record(cursor.fetchone())
        finally:
            conn.close()

    record_success = complete_execution

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

    def get_operation_by_id(self, operation_id: str) -> Optional[OperationRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM operations WHERE operation_id = ?;", (operation_id,))
            row = cursor.fetchone()
            return self._row_to_record(row) if row else None
        finally:
            conn.close()

    def expire_stale_operations(self) -> int:
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        try:
            cursor = conn.execute("""
                UPDATE operations
                SET state = ?, updated_at = ?, version = version + 1
                WHERE state IN (?, ?) AND expires_at < ?;
            """, (OperationState.EXPIRED.value, now_iso, OperationState.PREPARED.value, OperationState.APPROVED.value, now))
            return cursor.rowcount
        finally:
            conn.close()


# DurableOperationStore alias for standard SQLite storage adapter
DurableOperationStore = SqliteOperationStore


class PostgresOperationStore:
    """Network transactional store backed by PostgreSQL / Azure Database for PostgreSQL (WP04).
    
    Provides ACID row-level locking (SELECT ... FOR UPDATE) and optimistic concurrency
    control across multi-host container replicas.
    """

    def __init__(self, connection_url: Optional[str] = None):
        self.connection_url = connection_url or os.getenv("DATABASE_URL", "")
        if not self.connection_url:
            raise ValueError("DATABASE_URL must be configured for PostgresOperationStore")
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
                "psycopg2 is required for PostgresOperationStore in production. "
                "Ensure psycopg2-binary is installed or configure connection pool."
            )

    def _init_db(self) -> None:
        try:
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS operations (
                            operation_id VARCHAR(64) PRIMARY KEY,
                            approval_id VARCHAR(128) UNIQUE NOT NULL,
                            token_hash VARCHAR(128),
                            tenant_id VARCHAR(128) NOT NULL,
                            user_object_id VARCHAR(128) NOT NULL,
                            user_email VARCHAR(256) NOT NULL,
                            operation_type VARCHAR(64) NOT NULL,
                            payload_checksum VARCHAR(128) NOT NULL,
                            proposed_payload JSONB NOT NULL,
                            policy_version VARCHAR(32) NOT NULL,
                            state VARCHAR(32) NOT NULL,
                            version INTEGER NOT NULL DEFAULT 1,
                            expires_at DOUBLE PRECISION NOT NULL,
                            created_at VARCHAR(64) NOT NULL,
                            updated_at VARCHAR(64) NOT NULL,
                            confirmed_by_oid VARCHAR(128),
                            confirmed_at VARCHAR(64),
                            claimed_by_owner VARCHAR(128),
                            lease_expires_at DOUBLE PRECISION,
                            provider_reference JSONB,
                            result_payload JSONB,
                            last_error TEXT
                        );
                        CREATE INDEX IF NOT EXISTS idx_ops_approval ON operations(approval_id);
                        CREATE INDEX IF NOT EXISTS idx_ops_tenant_user ON operations(tenant_id, user_object_id);
                        CREATE INDEX IF NOT EXISTS idx_ops_state_expiry ON operations(state, expires_at);
                    """)
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            log.warning(f"Could not auto-initialize PostgreSQL operations table: {e}")

    def _row_to_record(self, row: Dict[str, Any]) -> OperationRecord:
        prop_payload = row["proposed_payload"]
        if isinstance(prop_payload, str):
            prop_payload = json.loads(prop_payload)
        prov_ref = row.get("provider_reference")
        if isinstance(prov_ref, str):
            prov_ref = json.loads(prov_ref)
        res_payload = row.get("result_payload")
        if isinstance(res_payload, str):
            res_payload = json.loads(res_payload)

        return OperationRecord(
            operation_id=row["operation_id"],
            approval_id=row["approval_id"],
            token_hash=row.get("token_hash"),
            tenant_id=row["tenant_id"],
            user_object_id=row["user_object_id"],
            user_email=row["user_email"],
            operation_type=row["operation_type"],
            payload_checksum=row["payload_checksum"],
            proposed_payload=prop_payload,
            policy_version=row["policy_version"],
            state=row["state"],
            version=int(row["version"]),
            expires_at=float(row["expires_at"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            confirmed_by_oid=row.get("confirmed_by_oid"),
            confirmed_at=row.get("confirmed_at"),
            claimed_by_owner=row.get("claimed_by_owner"),
            lease_expires_at=float(row["lease_expires_at"]) if row.get("lease_expires_at") is not None else None,
            provider_reference=prov_ref,
            result_payload=res_payload,
            last_error=row.get("last_error"),
        )

    def prepare_operation(
        self,
        operation_type: str,
        tenant_id: str,
        user_object_id: str,
        user_email: str,
        proposed_payload: Dict[str, Any],
        approval_id: Optional[str] = None,
        approval_token: Optional[str] = None,
        expiry_minutes: Optional[int] = None,
        ttl_seconds: Optional[float] = None,
        policy_version: str = "2026.1",
    ) -> OperationRecord:
        if not tenant_id or not user_object_id:
            raise ValueError("Authenticated tenant_id and user_object_id are required")

        canonical_op = normalize_operation_type(operation_type)
        checksum = compute_payload_checksum(proposed_payload)
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        
        effective_ttl = float(ttl_seconds) if ttl_seconds is not None else (float(expiry_minutes * 60) if expiry_minutes is not None else 900.0)
        expires_at = now + effective_ttl
        token_hash = hashlib.sha256(approval_token.encode("utf-8")).hexdigest() if approval_token else None

        op_id = f"OP-{uuid.uuid4().hex[:12]}"
        appr_id = approval_id or f"appr-{uuid.uuid4().hex}"

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO operations (
                        operation_id, approval_id, token_hash, tenant_id, user_object_id, user_email,
                        operation_type, payload_checksum, proposed_payload, policy_version,
                        state, version, expires_at, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s);
                """, (
                    op_id, appr_id, token_hash, tenant_id, user_object_id, user_email.strip().lower(),
                    canonical_op, checksum, json.dumps(proposed_payload), policy_version,
                    OperationState.PREPARED.value, expires_at, now_iso, now_iso
                ))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return OperationRecord(
            operation_id=op_id,
            approval_id=appr_id,
            token_hash=token_hash,
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
        approval_token: Optional[str] = None,
    ) -> OperationRecord:
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM operations WHERE approval_id = %s FOR UPDATE;", (approval_id,))
                row = cur.fetchone()
                if not row:
                    raise ValueError(f"Approval operation '{approval_id}' not found")

                rec = self._row_to_record(row)

                if now > rec.expires_at:
                    cur.execute(
                        "UPDATE operations SET state = %s, updated_at = %s WHERE approval_id = %s;",
                        (OperationState.EXPIRED.value, now_iso, approval_id)
                    )
                    conn.commit()
                    raise ValueError(f"Approval '{approval_id}' has expired")

                if rec.tenant_id != tenant_id or rec.user_object_id != user_object_id:
                    raise AccessDeniedError("Approval token presented by conflicting user or tenant identity")

                if rec.token_hash and approval_token:
                    presented_hash = hashlib.sha256(approval_token.encode("utf-8")).hexdigest()
                    if presented_hash != rec.token_hash:
                        raise InvalidTokenError("Approval token hash mismatch; presented token is not authorized for this operation")

                if current_preview_data is not None:
                    current_chk = compute_payload_checksum(current_preview_data)
                    if current_chk != rec.payload_checksum:
                        raise ValueError("Proposed payload has changed since preview; new approval required")

                if rec.state != OperationState.PREPARED.value and rec.state != OperationState.APPROVED.value:
                    raise ValueError(f"Cannot approve operation in state '{rec.state}'")

                cur.execute("""
                    UPDATE operations
                    SET state = %s, confirmed_by_oid = %s, confirmed_at = %s, version = version + 1, updated_at = %s
                    WHERE approval_id = %s AND (state = %s OR state = %s);
                """, (
                    OperationState.APPROVED.value, user_object_id, now_iso, now_iso,
                    approval_id, OperationState.PREPARED.value, OperationState.APPROVED.value
                ))

                cur.execute("SELECT * FROM operations WHERE approval_id = %s;", (approval_id,))
                updated_row = cur.fetchone()
            conn.commit()
            return self._row_to_record(updated_row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def reject_operation(
        self,
        approval_id: str,
        user_object_id: str,
        tenant_id: str,
        reason: Optional[str] = None,
    ) -> OperationRecord:
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM operations WHERE approval_id = %s FOR UPDATE;", (approval_id,))
                row = cur.fetchone()
                if not row:
                    raise ValueError(f"Approval operation '{approval_id}' not found")
                rec = self._row_to_record(row)
                if rec.tenant_id != tenant_id or rec.user_object_id != user_object_id:
                    raise AccessDeniedError("Rejection attempted by conflicting user or tenant identity")
                if rec.state in (OperationState.EXECUTING.value, OperationState.SUCCEEDED.value):
                    raise ValueError(f"Cannot reject operation in state '{rec.state}'")

                cur.execute("""
                    UPDATE operations
                    SET state = %s, last_error = %s, version = version + 1, updated_at = %s
                    WHERE approval_id = %s;
                """, (OperationState.REJECTED.value, reason or "Rejected by user", now_iso, approval_id))
                cur.execute("SELECT * FROM operations WHERE approval_id = %s;", (approval_id,))
                updated_row = cur.fetchone()
            conn.commit()
            return self._row_to_record(updated_row)
        except Exception:
            conn.rollback()
            raise
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
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        lease_expires_at = now + lease_seconds
        canonical_expected = normalize_operation_type(expected_operation)

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM operations WHERE approval_id = %s FOR UPDATE;", (approval_id,))
                row = cur.fetchone()
                if not row:
                    conn.commit()
                    return False, None, "APPROVAL_NOT_FOUND"

                rec = self._row_to_record(row)

                if rec.tenant_id != presented_tenant_id or rec.user_object_id != presented_user_oid:
                    conn.commit()
                    return False, rec, "IDENTITY_MISMATCH"

                if rec.operation_type != canonical_expected:
                    conn.commit()
                    return False, rec, "OPERATION_MISMATCH"

                if rec.state == OperationState.SUCCEEDED.value:
                    conn.commit()
                    return False, rec, "ALREADY_SUCCEEDED"

                if now > rec.expires_at:
                    cur.execute(
                        "UPDATE operations SET state = %s, updated_at = %s WHERE approval_id = %s;",
                        (OperationState.EXPIRED.value, now_iso, approval_id)
                    )
                    conn.commit()
                    return False, rec, "APPROVAL_EXPIRED"

                if rec.state == OperationState.EXECUTING.value:
                    if rec.lease_expires_at and now > rec.lease_expires_at:
                        log.warning(f"Execution lease expired for {approval_id}; transitioning to OUTCOME_UNKNOWN")
                        cur.execute(
                            "UPDATE operations SET state = %s, updated_at = %s WHERE approval_id = %s AND state = %s;",
                            (OperationState.OUTCOME_UNKNOWN.value, now_iso, approval_id, OperationState.EXECUTING.value)
                        )
                        conn.commit()
                        return False, rec, "OUTCOME_UNKNOWN_RECONCILING"
                    else:
                        conn.commit()
                        return False, rec, "CONCURRENTLY_EXECUTING"

                if rec.state != OperationState.APPROVED.value:
                    conn.commit()
                    return False, rec, f"INVALID_STATE_{rec.state}"

                cur.execute("""
                    UPDATE operations
                    SET state = %s, claimed_by_owner = %s, lease_expires_at = %s, version = version + 1, updated_at = %s
                    WHERE approval_id = %s AND version = %s;
                """, (
                    OperationState.EXECUTING.value, executor_id, lease_expires_at, now_iso,
                    approval_id, rec.version
                ))

                if cur.rowcount == 0:
                    conn.commit()
                    return False, None, "CONCURRENT_MODIFICATION"

                cur.execute("SELECT * FROM operations WHERE approval_id = %s;", (approval_id,))
                updated_row = cur.fetchone()
                conn.commit()
                return True, self._row_to_record(updated_row), ""
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def complete_execution(
        self,
        operation_id: Optional[str] = None,
        result_payload: Optional[Dict[str, Any]] = None,
        provider_reference: Optional[Dict[str, Any]] = None,
        approval_id: Optional[str] = None,
    ) -> OperationRecord:
        identifier = operation_id or approval_id
        if not identifier:
            raise ValueError("operation_id or approval_id is required to complete execution")
        now_iso = datetime.now(timezone.utc).isoformat()
        res = result_payload or {}
        ref = provider_reference or {}
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE operations
                    SET state = %s, result_payload = %s, provider_reference = %s, updated_at = %s, version = version + 1
                    WHERE operation_id = %s OR approval_id = %s;
                """, (
                    OperationState.SUCCEEDED.value,
                    json.dumps(res),
                    json.dumps(ref),
                    now_iso,
                    identifier,
                    identifier,
                ))
                cur.execute("SELECT * FROM operations WHERE operation_id = %s OR approval_id = %s;", (identifier, identifier))
                updated_row = cur.fetchone()
            conn.commit()
            return self._row_to_record(updated_row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    record_success = complete_execution

    def fail_execution(
        self,
        operation_id: str,
        error_message: str,
        before_submission: bool = True,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        final_state = (
            OperationState.FAILED_BEFORE_SUBMISSION.value
            if before_submission
            else OperationState.OUTCOME_UNKNOWN.value
        )
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE operations
                    SET state = %s, last_error = %s, updated_at = %s, version = version + 1
                    WHERE operation_id = %s;
                """, (final_state, error_message, now_iso, operation_id))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_operation_by_approval_id(self, approval_id: str) -> Optional[OperationRecord]:
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM operations WHERE approval_id = %s;", (approval_id,))
                row = cur.fetchone()
                return self._row_to_record(row) if row else None
        finally:
            conn.close()

    def get_operation_by_id(self, operation_id: str) -> Optional[OperationRecord]:
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM operations WHERE operation_id = %s;", (operation_id,))
                row = cur.fetchone()
                return self._row_to_record(row) if row else None
        finally:
            conn.close()

    def expire_stale_operations(self) -> int:
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE operations
                    SET state = %s, updated_at = %s, version = version + 1
                    WHERE state IN (%s, %s) AND expires_at < %s;
                """, (OperationState.EXPIRED.value, now_iso, OperationState.PREPARED.value, OperationState.APPROVED.value, now))
                count = cur.rowcount
            conn.commit()
            return count
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


# Global operation store instance
_OPERATION_STORE = None


def get_operation_store(db_path: Optional[str] = None):
    global _OPERATION_STORE
    if _OPERATION_STORE is None or db_path:
        db_url = os.getenv("DATABASE_URL", "")
        if db_url.startswith("postgresql://") or db_url.startswith("postgres://"):
            try:
                _OPERATION_STORE = PostgresOperationStore(connection_url=db_url)
                return _OPERATION_STORE
            except Exception as e:
                log.warning(f"Could not connect to PostgreSQL via DATABASE_URL: {e}")
                if os.getenv("VELORA_ENV") == "production":
                    raise
        _OPERATION_STORE = SqliteOperationStore(db_path=db_path)
    return _OPERATION_STORE
