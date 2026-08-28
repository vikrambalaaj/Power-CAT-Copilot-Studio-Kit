"""Dataverse Audit Client Integration for Productivity Agent."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .dataverse_audit import (
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


class ProductivityAuditService:
    """Provides high-level audit governance methods for Microsoft 365 reads and writes."""

    def __init__(self, dv_client: Optional[DataverseClient] = None):
        self.dv_client = dv_client or get_dataverse_client()
        self.agent_name = "Velora Productivity Agent"
        self.agent_version = os.getenv("VeloraAgentVersion", "1.0.0")
        self.environment = os.getenv("VeloraEnvironmentName", "Velora-AgenticAD-Dev")
        self.audit_enabled = os.getenv("VeloraAuditEnabled", "true").lower() in ("true", "1", "yes")

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
            return res.get("id", "PERSISTED")
        except Exception as ex:
            log.warning("async_read_audit_failed_reconcile_later", error=str(ex), tool=tool_name)
            return "QUEUED_FOR_RECONCILIATION"

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
            invocation_id=f"prev-{idempotency_key[:12]}",
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
            return {"status": "SUCCESS", "id": res.get("id", "")}
        except Exception as ex:
            log.warning("stage_a_preview_audit_warn", error=str(ex))
            return {"status": "BUFFERED", "id": "LOCAL-PREVIEW-AUD"}

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
        inv_id = f"exec-{idempotency_key[:12]}"

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
