"""Dataverse Audit Client Integration for Productivity Agent."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import json
import sqlite3
import time

from .dataverse_audit import (
    AuditCommitStatus,
    DataverseAuditRecord,
    DataverseClient,
    get_dataverse_client,
    RECORD_TYPE_AGENT_DELEGATION_START,
    RECORD_TYPE_AGENT_DELEGATION_END,
    RECORD_TYPE_TOOL_EXECUTION_START,
    RECORD_TYPE_TOOL_EXECUTION_END,
    RECORD_TYPE_TRANSACTION_PREVIEW,
    RECORD_TYPE_USER_APPROVAL,
    RECORD_TYPE_TRANSACTION_START,
    RECORD_TYPE_TRANSACTION_RESULT,
    RECORD_TYPE_TRANSACTION_ERROR,
    compute_approval_token_hash,
)
from shared_mcp.logger import get_logger

log = get_logger("productivity_audit")


class AuditReconciliationQueue:
    """Durable reconciliation queue for audit records that could not be committed immediately."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.getenv("VELORA_AUDIT_RECONCILIATION_DB", "audit_reconciliation.db")
        self._init_db()

    def _init_db(self) -> None:
        parent_dir = os.path.dirname(self.db_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_reconciliation_queue (
                    id TEXT PRIMARY KEY,
                    record_type TEXT NOT NULL,
                    invocation_id TEXT,
                    idempotency_key TEXT,
                    payload TEXT NOT NULL,
                    reason TEXT,
                    retry_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    status TEXT DEFAULT 'PENDING'
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_rec_status ON audit_reconciliation_queue(status)")

    def enqueue(self, record: DataverseAuditRecord, reason: str = "") -> str:
        rec_id = f"REC-Q-{int(time.time() * 1000)}-{os.urandom(3).hex()}"
        payload_json = json.dumps(record.to_dataverse_payload())
        now_iso = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO audit_reconciliation_queue (id, record_type, invocation_id, idempotency_key, payload, reason, retry_count, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?, 'PENDING')
                """,
                (rec_id, record.record_type, record.invocation_id, record.idempotency_key, payload_json, reason, now_iso),
            )
        return rec_id

    def get_pending_count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT COUNT(*) FROM audit_reconciliation_queue WHERE status = 'PENDING'")
            return cur.fetchone()[0]

    async def reconcile_pending(self, dv_client: DataverseClient, max_items: int = 50) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM audit_reconciliation_queue WHERE status = 'PENDING' ORDER BY created_at ASC LIMIT ?",
                (max_items,),
            ).fetchall()

        reconciled = 0
        failed = 0
        for row in rows:
            try:
                payload = json.loads(row["payload"])
                await dv_client._create_live_audit_row(payload)
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("UPDATE audit_reconciliation_queue SET status = 'RECONCILED' WHERE id = ?", (row["id"],))
                reconciled += 1
            except Exception as ex:
                failed += 1
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "UPDATE audit_reconciliation_queue SET retry_count = retry_count + 1, reason = ? WHERE id = ?",
                        (str(ex), row["id"]),
                    )
        return {"reconciled": reconciled, "failed": failed, "remaining": self.get_pending_count()}


class ProductivityAuditService:
    """Provides high-level audit governance methods for Microsoft 365 reads and writes."""

    def __init__(self, dv_client: Optional[DataverseClient] = None, reconciliation_db_path: Optional[str] = None):
        self.dv_client = dv_client or get_dataverse_client()
        self.agent_name = "Velora Productivity Agent"
        self.agent_version = os.getenv("VeloraAgentVersion", "1.0.0")
        self.environment = os.getenv("VeloraEnvironmentName", "Velora-AgenticAD-Dev")
        self.audit_enabled = os.getenv("VeloraAuditEnabled", "true").lower() in ("true", "1", "yes")
        self.reconciliation_queue = AuditReconciliationQueue(db_path=reconciliation_db_path)

    def get_reconciliation_pending_count(self) -> int:
        return self.reconciliation_queue.get_pending_count()

    async def reconcile_pending_audits(self, max_items: int = 50) -> Dict[str, Any]:
        return await self.reconciliation_queue.reconcile_pending(self.dv_client, max_items=max_items)

    async def audit_read_tool_execution(
        self,
        tool_name: str,
        root_correlation_id: str,
        user_object_id: str,
        user_email: str,
        result_count: int,
        summary: str,
        safe_filters: str = "",
        latency_ms: int = 0,
        outcome: str = "SUCCESS",
        error_msg: str = "",
        conversation_id: str = "",
        turn_id: str = "",
    ) -> str:
        """Audit M365 Read operations (asynchronous/best-effort)."""
        if not self.audit_enabled:
            return "AUDIT_DISABLED"

        rec = DataverseAuditRecord(
            record_type=RECORD_TYPE_TOOL_EXECUTION_END if outcome == "SUCCESS" else RECORD_TYPE_TRANSACTION_ERROR,
            root_correlation_id=root_correlation_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            user_object_id=user_object_id,
            user_email=user_email,
            calling_agent="Velora Copilot Studio Parent",
            executing_agent=self.agent_name,
            agent_name=self.agent_name,
            agent_version=self.agent_version,
            environment=self.environment,
            capability=tool_name,
            operation=tool_name,
            transaction_type="READ",
            source_system="Microsoft365",
            outcome=outcome,
            latency_ms=latency_ms,
            result_count=result_count,
            message_summary=summary,
            request_filter_safe=safe_filters,
            error_message_safe=error_msg,
            error_category="" if outcome == "SUCCESS" else "READ_ERROR",
        )
        try:
            res = await self.dv_client.create_audit_record(rec)
            commit_status = res.get("commit_status") or res.get("status")
            if commit_status in (AuditCommitStatus.COMMITTED, "COMMITTED"):
                return res.get("audit_record_id") or res.get("id") or "PERSISTED"
            # If merely buffered because Dataverse is offline/unconfigured, enqueue to durable reconciliation
            self.reconciliation_queue.enqueue(rec, reason=f"dataverse_status_{commit_status}")
            return "QUEUED_FOR_RECONCILIATION"
        except Exception as ex:
            log.warning("async_read_audit_failed_reconcile_later", error=str(ex), tool=tool_name)
            try:
                self.reconciliation_queue.enqueue(rec, reason=str(ex))
                return "QUEUED_FOR_RECONCILIATION"
            except Exception as q_err:
                log.error("reconciliation_queue_enqueue_failed", error=str(q_err))
                return "FAILED_UNQUEUED"

    async def audit_stage_a_preview(
        self,
        operation: str,
        root_correlation_id: str,
        user_object_id: str,
        user_email: str,
        preview_summary: str,
        preview_details: Dict[str, Any],
        idempotency_key: str,
        approval_token: str,
        expires_on: str,
        conversation_id: str = "",
        turn_id: str = "",
    ) -> Dict[str, Any]:
        """Record Stage A TRANSACTION_PREVIEW in Dataverse."""
        token_hash = compute_approval_token_hash(approval_token)
        rec = DataverseAuditRecord(
            record_type=RECORD_TYPE_TRANSACTION_PREVIEW,
            root_correlation_id=root_correlation_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            invocation_id=f"prev-{idempotency_key}",
            idempotency_key=idempotency_key,
            user_object_id=user_object_id,
            user_email=user_email,
            calling_agent="Velora Copilot Studio Parent",
            executing_agent=self.agent_name,
            agent_name=self.agent_name,
            agent_version=self.agent_version,
            environment=self.environment,
            capability=operation,
            operation=operation,
            transaction_type="WRITE_PREVIEW",
            source_system="Microsoft365",
            approval_status="PENDING",
            approval_expires_on=expires_on,
            approval_token_hash=token_hash,
            message_summary=preview_summary,
            audit_detail=f"Prepared {operation} preview for executive approval.",
            target_summary_safe=str(preview_details.get("to") or preview_details.get("channelName") or preview_details.get("planName") or ""),
        )
        try:
            res = await self.dv_client.create_audit_record(rec)
            commit_status = res.get("commit_status", AuditCommitStatus.COMMITTED if self.dv_client.is_live else AuditCommitStatus.BUFFERED)
            rec_id = res.get("audit_record_id") or res.get("id", "")
            return {"status": "SUCCESS", "commit_status": commit_status, "id": rec_id, "audit_record_id": rec_id}
        except Exception as ex:
            log.warning("stage_a_preview_audit_warn", error=str(ex))
            q_id = self.reconciliation_queue.enqueue(rec, reason=str(ex))
            return {"status": "BUFFERED", "commit_status": AuditCommitStatus.BUFFERED, "id": q_id, "audit_record_id": q_id}

    async def start_stage_b_write_fail_closed(
        self,
        operation: str,
        root_correlation_id: str,
        user_object_id: str,
        user_email: str,
        idempotency_key: str,
        approval_token: str,
        summary: str,
        conversation_id: str = "",
        turn_id: str = "",
    ) -> Dict[str, Any]:
        """Record Stage B TRANSACTION_START with strict fail-closed enforcement (Section 3.5 & 6.1)."""
        token_hash = compute_approval_token_hash(approval_token)
        inv_id = f"exec-{idempotency_key}"

        rec = DataverseAuditRecord(
            record_type=RECORD_TYPE_TRANSACTION_START,
            root_correlation_id=root_correlation_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            invocation_id=inv_id,
            idempotency_key=idempotency_key,
            user_object_id=user_object_id,
            user_email=user_email,
            calling_agent="Velora Copilot Studio Parent",
            executing_agent=self.agent_name,
            agent_name=self.agent_name,
            agent_version=self.agent_version,
            environment=self.environment,
            capability=operation,
            operation=operation,
            transaction_type="WRITE_EXECUTE",
            source_system="Microsoft365",
            approval_status="APPROVED",
            approval_token_hash=token_hash,
            message_summary=summary,
            audit_detail=f"Executing approved {operation}",
        )
        return await self.dv_client.start_write_transaction_fail_closed(rec)

    async def complete_stage_b_write(
        self,
        audit_record_id: str,
        invocation_id: str,
        outcome: str,
        external_object_id: str = "",
        evidence_link: str = "",
        summary: str = "",
        error_msg: str = "",
        start_time: str = "",
        root_correlation_id: str = "",
        user_email: str = "",
        operation: str = "",
        idempotency_key: str = "",
    ) -> Dict[str, Any]:
        """Record Stage B TRANSACTION_RESULT or TRANSACTION_ERROR (Section 6.2)."""
        return await self.dv_client.complete_write_transaction(
            audit_record_id=audit_record_id,
            invocation_id=invocation_id,
            outcome=outcome,
            external_object_id=external_object_id,
            evidence_link=evidence_link,
            safe_summary=summary,
            safe_error=error_msg,
            start_time=start_time,
            record_type=RECORD_TYPE_TRANSACTION_RESULT if outcome == "SUCCESS" else RECORD_TYPE_TRANSACTION_ERROR,
            calling_agent=self.agent_name,
            executing_agent=self.agent_name,
            root_correlation_id=root_correlation_id,
            user_email=user_email,
            operation=operation,
            idempotency_key=idempotency_key,
        )


# Global singleton
_audit_service = ProductivityAuditService()


def get_productivity_audit_service() -> ProductivityAuditService:
    return _audit_service
