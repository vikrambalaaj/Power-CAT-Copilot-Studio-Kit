"""Automation Subscription Service — Velora Executive Agent Platform.

Manages governed recurring automation subscriptions with 2-step approval (PREPARE -> CONFIRM),
revocation, idempotent run keys, and audit-preserving execution history.
Default state is disabled. Standing authorization is verified on every run.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .evidence_contracts import AutomationSubscription, SubscriptionKind, decimal_serializer
from .token_manager import get_token_manager, InvalidTokenError

log = logging.getLogger("productivity_mcp.subscription_service")


class SubscriptionService:
    """Thread-safe persistent store and lifecycle manager for AutomationSubscriptions."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.getenv("VELORA_SUBSCRIPTION_DB", "/tmp/velora_subscriptions.db")
        self._init_db()

    def _init_db(self) -> None:
        """Initialize subscriptions and run_history tables."""
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS automation_subscriptions (
                    subscription_id TEXT PRIMARY KEY,
                    version TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    mailbox TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    recipients_json TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    local_schedule TEXT,
                    meeting_filters_json TEXT,
                    lead_time_minutes INTEGER,
                    horizon_hours INTEGER,
                    channel TEXT,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    valid_until TEXT,
                    authorized_by TEXT,
                    authorized_at TEXT,
                    allowed_data_scope_json TEXT,
                    last_run_at TEXT,
                    next_run_at TEXT,
                    quiet_hours_policy TEXT,
                    missed_run_policy TEXT,
                    state TEXT NOT NULL DEFAULT 'DRAFT',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS subscription_run_history (
                    run_key TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    subscription_id TEXT NOT NULL,
                    subscription_version TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    scheduled_occurrence TEXT NOT NULL,
                    status TEXT NOT NULL,
                    executed_at TEXT NOT NULL,
                    details_json TEXT
                )
            """)
            conn.commit()

    def prepare_subscription(
        self,
        tenant_id: str,
        owner: str,
        mailbox: str,
        sender: str,
        recipients: List[str],
        kind: str,
        timezone_str: str = "Asia/Dubai",
        local_schedule: Optional[str] = None,
        meeting_filters: Optional[Dict[str, Any]] = None,
        lead_time_minutes: int = 15,
        horizon_hours: int = 24,
        channel: str = "EMAIL",
        valid_until: Optional[str] = None,
        allowed_data_scope: Optional[List[str]] = None,
        quiet_hours_policy: str = "SUPPRESS",
        missed_run_policy: str = "SKIP",
        user_object_id: str = "",
        user_email: str = "",
    ) -> Tuple[AutomationSubscription, str]:
        """Prepare an automation subscription in DRAFT state and generate a confirmation token.
        
        Default state is disabled. Requires explicit confirmation before activation.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        sub_id = f"SUB-{kind[:3]}-{hashlib.sha256(f'{tenant_id}:{owner}:{kind}:{now_iso}'.encode()).hexdigest()[:10]}"

        # Validate kind
        try:
            sub_kind = SubscriptionKind(kind.upper())
        except ValueError:
            raise ValueError(f"Invalid subscription kind: {kind}. Must be one of: MORNING, PRE_MEETING, EOD, ACTION_REMINDER")

        # Validate EOD schedule
        if sub_kind == SubscriptionKind.EOD and not local_schedule:
            raise ValueError("CONFIGURATION_REQUIRED: Missing explicit EOD local schedule time")

        subscription = AutomationSubscription(
            subscriptionId=sub_id,
            version="1.0.0",
            tenantId=tenant_id,
            owner=owner,
            mailbox=mailbox,
            sender=sender,
            recipients=recipients,
            kind=sub_kind,
            timezone=timezone_str,
            localSchedule=local_schedule,
            meetingFilters=meeting_filters or {},
            leadTimeMinutes=lead_time_minutes,
            horizonHours=horizon_hours,
            channel=channel,
            enabled=False,  # Strict default disabled!
            validUntil=valid_until,
            authorizedBy=user_object_id or owner,
            authorizedAt=now_iso,
            allowedDataScope=allowed_data_scope or [],
            quietHoursPolicy=quiet_hours_policy,
            missedRunPolicy=missed_run_policy,
        )

        # Persist as DRAFT
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO automation_subscriptions (
                    subscription_id, version, tenant_id, owner, mailbox, sender, recipients_json,
                    kind, timezone, local_schedule, meeting_filters_json, lead_time_minutes,
                    horizon_hours, channel, enabled, valid_until, authorized_by, authorized_at,
                    allowed_data_scope_json, state, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, 'DRAFT', ?, ?)
            """, (
                sub_id, "1.0.0", tenant_id, owner, mailbox, sender, json.dumps(recipients),
                sub_kind.value, timezone_str, local_schedule, json.dumps(meeting_filters or {}),
                lead_time_minutes, horizon_hours, channel, valid_until, user_object_id or owner,
                now_iso, json.dumps(allowed_data_scope or []), now_iso, now_iso,
            ))
            conn.commit()

        # Generate HMAC approval token
        token_mgr = get_token_manager()
        preview_details = {
            "subscriptionId": sub_id,
            "kind": sub_kind.value,
            "mailbox": mailbox,
            "recipients": recipients,
            "schedule": local_schedule,
            "timezone": timezone_str,
            "tenantId": tenant_id,
        }
        token, _ = token_mgr.create_approval_token(
            operation="PREPARE_AUTOMATION_SUBSCRIPTION",
            user_object_id=user_object_id or owner,
            user_email=user_email or mailbox,
            preview_data=preview_details,
            idempotency_key=f"idemp-{sub_id}",
            root_correlation_id=f"corr-{sub_id}",
            expiry_minutes=30,
        )

        return subscription, token

    def confirm_subscription(
        self,
        confirmation_token: str,
        subscription_id: str,
        user_object_id: str,
        user_email: str,
        tenant_id: str,
    ) -> AutomationSubscription:
        """Confirm and activate an approved subscription via cryptographic token."""
        token_mgr = get_token_manager()
        valid, reason, token_data = token_mgr.verify_approval_token(
            token=confirmation_token,
            expected_operation="PREPARE_AUTOMATION_SUBSCRIPTION",
            user_object_id=user_object_id,
            user_email=user_email,
            tenant_id=tenant_id,
            consume_nonce=True,
        )
        if not valid or not token_data:
            raise InvalidTokenError(f"Confirmation token is invalid: {reason}")

        now_iso = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM automation_subscriptions WHERE subscription_id = ? AND tenant_id = ?",
                (subscription_id, tenant_id),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Subscription '{subscription_id}' not found in tenant '{tenant_id}'")

            cursor.execute("""
                UPDATE automation_subscriptions
                SET enabled = 1, state = 'ENABLED', authorized_by = ?, authorized_at = ?, updated_at = ?
                WHERE subscription_id = ? AND tenant_id = ?
            """, (user_object_id, now_iso, now_iso, subscription_id, tenant_id))
            conn.commit()

        sub = self.get_subscription(subscription_id, tenant_id)
        if not sub:
            raise RuntimeError("Failed to load confirmed subscription")
        return sub

    def revoke_subscription(
        self,
        subscription_id: str,
        tenant_id: str,
        revoked_by: str,
    ) -> AutomationSubscription:
        """Revoke / disable an automation subscription. Preserves run history."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE automation_subscriptions
                SET enabled = 0, state = 'REVOKED', updated_at = ?
                WHERE subscription_id = ? AND tenant_id = ?
            """, (now_iso, subscription_id, tenant_id))
            conn.commit()

        sub = self.get_subscription(subscription_id, tenant_id)
        if not sub:
            raise ValueError(f"Subscription '{subscription_id}' not found")
        return sub

    def get_subscription(self, subscription_id: str, tenant_id: str) -> Optional[AutomationSubscription]:
        """Fetch subscription by ID and tenant."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM automation_subscriptions WHERE subscription_id = ? AND tenant_id = ?",
                (subscription_id, tenant_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_subscription(row)

    def list_active_subscriptions(self, tenant_id: Optional[str] = None) -> List[AutomationSubscription]:
        """List all currently enabled subscriptions."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if tenant_id:
                cursor.execute(
                    "SELECT * FROM automation_subscriptions WHERE enabled = 1 AND tenant_id = ?",
                    (tenant_id,),
                )
            else:
                cursor.execute("SELECT * FROM automation_subscriptions WHERE enabled = 1")
            rows = cursor.fetchall()
            return [self._row_to_subscription(r) for r in rows]

    def is_run_already_executed(self, run_key: str) -> bool:
        """Check if a specific run key has already been claimed or executed (idempotency barrier)."""
        now = datetime.now(timezone.utc)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, executed_at FROM subscription_run_history WHERE run_key = ?", (run_key,))
            row = cursor.fetchone()
            if not row:
                return False
            status, executed_at = row
            if status == "CLAIMED":
                # Check for crashed worker (stale claim > 10 minutes)
                try:
                    claimed_dt = datetime.fromisoformat(executed_at)
                    if (now - claimed_dt).total_seconds() > 600:
                        cursor.execute("UPDATE subscription_run_history SET status = 'EXPIRED_CLAIM' WHERE run_key = ?", (run_key,))
                        conn.commit()
                        return False
                except Exception:
                    pass
                return True
            return status in ("SUCCESS", "FAILED")

    def claim_subscription_run(
        self,
        run_key: str,
        tenant_id: str,
        subscription_id: str,
        subscription_version: str,
        execution_id: str,
        scheduled_occurrence: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Atomically claim a subscription run before dispatching to prevent duplicate execution across concurrent workers."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO subscription_run_history (
                        run_key, tenant_id, subscription_id, subscription_version,
                        execution_id, scheduled_occurrence, status, executed_at, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, 'CLAIMED', ?, ?)
                """, (
                    run_key, tenant_id, subscription_id, subscription_version,
                    execution_id, scheduled_occurrence, now_iso, json.dumps(details or {}, default=decimal_serializer),
                ))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                # Contest detected or already claimed/run
                return False

    def complete_subscription_run(
        self,
        run_key: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update a claimed subscription run to final status (SUCCESS, FAILED) with provider receipts."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE subscription_run_history
                SET status = ?, executed_at = ?, details_json = ?
                WHERE run_key = ?
            """, (
                status, now_iso, json.dumps(details or {}, default=decimal_serializer), run_key,
            ))
            if status == "SUCCESS":
                cursor.execute("""
                    UPDATE automation_subscriptions
                    SET last_run_at = ?
                    WHERE subscription_id = (SELECT subscription_id FROM subscription_run_history WHERE run_key = ?)
                """, (now_iso, run_key))
            conn.commit()

    def record_subscription_run(
        self,
        run_key: str,
        tenant_id: str,
        subscription_id: str,
        subscription_version: str,
        execution_id: str,
        scheduled_occurrence: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record executed subscription run in audit history."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO subscription_run_history (
                    run_key, tenant_id, subscription_id, subscription_version,
                    execution_id, scheduled_occurrence, status, executed_at, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_key, tenant_id, subscription_id, subscription_version,
                execution_id, scheduled_occurrence, status, now_iso, json.dumps(details or {}, default=decimal_serializer),
            ))
            # Also update last_run_at on subscription
            cursor.execute("""
                UPDATE automation_subscriptions
                SET last_run_at = ?
                WHERE subscription_id = ? AND tenant_id = ?
            """, (now_iso, subscription_id, tenant_id))
            conn.commit()

    def get_run_history(self, subscription_id: str) -> List[Dict[str, Any]]:
        """Retrieve run history for a subscription, even if later revoked."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM subscription_run_history WHERE subscription_id = ? ORDER BY executed_at DESC",
                (subscription_id,),
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def _row_to_subscription(self, row: Any) -> AutomationSubscription:
        return AutomationSubscription(
            subscriptionId=row["subscription_id"],
            version=row["version"],
            tenantId=row["tenant_id"],
            owner=row["owner"],
            mailbox=row["mailbox"],
            sender=row["sender"],
            recipients=json.loads(row["recipients_json"]),
            kind=SubscriptionKind(row["kind"]),
            timezone=row["timezone"],
            localSchedule=row["local_schedule"],
            meetingFilters=json.loads(row["meeting_filters_json"] or "{}"),
            leadTimeMinutes=row["lead_time_minutes"] or 15,
            horizonHours=row["horizon_hours"] or 24,
            channel=row["channel"] or "EMAIL",
            enabled=bool(row["enabled"]),
            validUntil=row["valid_until"],
            authorizedBy=row["authorized_by"],
            authorizedAt=row["authorized_at"],
            allowedDataScope=json.loads(row["allowed_data_scope_json"] or "[]"),
            lastRunAt=row["last_run_at"],
            nextRunAt=row["next_run_at"],
            quietHoursPolicy=row["quiet_hours_policy"] or "SUPPRESS",
            missedRunPolicy=row["missed_run_policy"] or "SKIP",
        )


_SUBSCRIPTION_SERVICE: Optional[SubscriptionService] = None

def get_subscription_service(db_path: Optional[str] = None) -> SubscriptionService:
    global _SUBSCRIPTION_SERVICE
    target_path = db_path or os.getenv("VELORA_SUBSCRIPTION_DB", "/tmp/velora_subscriptions.db")
    if _SUBSCRIPTION_SERVICE is None or _SUBSCRIPTION_SERVICE.db_path != target_path:
        _SUBSCRIPTION_SERVICE = SubscriptionService(db_path=target_path)
    return _SUBSCRIPTION_SERVICE

def reset_subscription_service_for_testing() -> None:
    global _SUBSCRIPTION_SERVICE
    _SUBSCRIPTION_SERVICE = None
