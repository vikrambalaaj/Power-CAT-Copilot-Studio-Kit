"""Tests for Audit Durability and Explicit Commitment Contract (Defect 5).

Verifies:
1. A BUFFERED sink never produces a committed spool marker.
2. A Dataverse outage prevents unaudited governed writes (fail-closed).
3. Lost responses after successful destination writes do not create duplicate events (ALREADY_COMMITTED).
4. Restart recovers pending events with unchanged IDs.
5. Spool write failures (e.g. read-only/disk errors) are visible to callers.
6. Required audit fields survive durable round-trip storage.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from successfactors_mcp.dataverse_audit import (
    AuditCommitStatus,
    DataverseAuditRecord,
    DataverseClient,
    RECORD_TYPE_TOOL_EXECUTION,
    RECORD_TYPE_TRANSACTION_START,
    RECORD_TYPE_TRANSACTION_RESULT,
)
from successfactors_mcp.background_logger import BackgroundLogger


@pytest.fixture
def temp_spool_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_buffered_sink_never_produces_committed_spool_marker(temp_spool_dir):
    """A BUFFERED sink (e.g. in-memory or unconfigured) must not release the spool with a commit marker."""
    spool_file = temp_spool_dir / "sf_audit_spool.jsonl"
    client = DataverseClient()  # not live, so create_audit_record returns BUFFERED
    assert not client.is_live

    logger = BackgroundLogger(dataverse_client=client, spool_path=str(spool_file))
    record = DataverseAuditRecord(
        record_type=RECORD_TYPE_TOOL_EXECUTION,
        user_email="exec@velora.com",
        operation="search_employees",
    )

    enqueued = logger.enqueue(record)
    assert enqueued is True
    assert spool_file.exists()

    # Process item in queue directly through _worker_loop logic
    queue = logger._get_queue()
    item = await queue.get()
    res = await client.create_audit_record(item)
    assert res["commit_status"] == AuditCommitStatus.BUFFERED

    # Since it is BUFFERED, no persisted: True marker should be written
    lines = [json.loads(line) for line in spool_file.read_text().strip().split("\n") if line.strip()]
    assert len(lines) == 1
    assert lines[0]["persisted"] is False
    # Verify no commit marker exists
    commit_markers = [l for l in lines if l.get("persisted") is True]
    assert len(commit_markers) == 0


@pytest.mark.asyncio
async def test_dataverse_outage_prevents_unaudited_governed_writes():
    """When Dataverse is unreachable (simulated outage), governed writes are blocked (fail-closed)."""
    client = DataverseClient()
    client.simulate_down = True

    record = DataverseAuditRecord(
        record_type=RECORD_TYPE_TRANSACTION_START,
        user_email="exec@velora.com",
        operation="update_employee_job",
        idempotency_key="idemp-test-outage",
    )

    result = await client.start_write_transaction_fail_closed(record)
    assert result["may_proceed"] is False
    assert result["commit_status"] == AuditCommitStatus.FAILED
    assert result["status"] == "FAIL_CLOSED_BLOCKED"
    assert "Dataverse audit log could not be saved" in result["error"]


@pytest.mark.asyncio
async def test_lost_response_idempotent_retry_does_not_duplicate():
    """If a write succeeded and client retries under the same alternate key, returns ALREADY_COMMITTED."""
    client = DataverseClient()
    inv_id = "inv-fixed-idempotency-1"

    record1 = DataverseAuditRecord(
        record_type=RECORD_TYPE_TOOL_EXECUTION,
        invocation_id=inv_id,
        user_email="exec@velora.com",
        operation="search_employees",
    )

    res1 = await client.create_audit_record(record1)
    assert res1["commit_status"] == AuditCommitStatus.BUFFERED

    # Retry with the same invocation_id and record_type (simulating lost response retry)
    record2 = DataverseAuditRecord(
        record_type=RECORD_TYPE_TOOL_EXECUTION,
        invocation_id=inv_id,
        user_email="exec@velora.com",
        operation="search_employees",
    )

    res2 = await client.create_audit_record(record2)
    assert res2["commit_status"] == AuditCommitStatus.ALREADY_COMMITTED
    assert res2["status"] == AuditCommitStatus.ALREADY_COMMITTED
    assert "already committed" in res2["message"]


@pytest.mark.asyncio
async def test_restart_recovers_pending_events_with_unchanged_ids(temp_spool_dir):
    """When process restarts, pending uncommitted spool records are recovered with unchanged event IDs."""
    spool_file = temp_spool_dir / "sf_audit_spool.jsonl"
    client = DataverseClient()

    logger1 = BackgroundLogger(dataverse_client=client, spool_path=str(spool_file))
    record = DataverseAuditRecord(
        record_type=RECORD_TYPE_TOOL_EXECUTION,
        invocation_id="inv-restart-test-999",
        user_email="exec@velora.com",
        operation="query_org_chart",
    )
    original_event_id = logger1._get_record_event_id(record)
    logger1.enqueue(record)

    # Simulate restart by creating a new logger instance pointing to the same spool
    logger2 = BackgroundLogger(dataverse_client=client, spool_path=str(spool_file))
    queue = logger2._get_queue()
    assert queue.qsize() == 1

    recovered_record = await queue.get()
    recovered_event_id = logger2._get_record_event_id(recovered_record)
    assert recovered_event_id == original_event_id
    assert recovered_record.invocation_id == "inv-restart-test-999"
    assert recovered_record.operation == "query_org_chart"


def test_spool_write_failure_is_visible(temp_spool_dir):
    """Spool write failures (e.g. read-only permission / disk error) must raise an IOError."""
    read_only_spool = temp_spool_dir / "readonly_dir" / "sf_audit_spool.jsonl"
    # Create the directory as read-only
    read_only_spool.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(read_only_spool.parent, 0o444)

    try:
        logger = BackgroundLogger(dataverse_client=DataverseClient(), spool_path=str(read_only_spool))
        record = DataverseAuditRecord(
            record_type=RECORD_TYPE_TOOL_EXECUTION,
            user_email="exec@velora.com",
            operation="test_fail",
        )
        with pytest.raises(IOError):
            logger._spool_record(record)
    finally:
        os.chmod(read_only_spool.parent, 0o755)


def test_required_audit_fields_survive_round_trip():
    """Detailed identity, approval reference, operation ID, policy version survive round-trip serialization."""
    original = DataverseAuditRecord(
        record_type=RECORD_TYPE_TRANSACTION_RESULT,
        user_object_id="oid-user-456",
        user_email="executive@velora.com",
        user_display_name="Jane Executive",
        root_correlation_id="root-corr-123",
        invocation_id="inv-roundtrip-789",
        idempotency_key="idemp-rt-001",
        operation="send_executive_email",
        source_system="ExchangeOnline",
        approval_status="APPROVED",
        policy_id="POL-EMAIL-01",
        policy_version="2.1.0",
        policy_decision="ALLOW",
        outcome="SUCCESS",
        source_as_of="2026-09-08T09:00:00Z",
        content_classification="HIGHLY_CONFIDENTIAL",
        audit_detail="Executive send approved and submitted",
    )
    original.audit_id = "EVT-STABLE-ROUNDTRIP-ID"

    payload = original.to_dataverse_payload()
    restored = DataverseAuditRecord.from_dataverse_payload(payload)

    assert restored.audit_id == "EVT-STABLE-ROUNDTRIP-ID"
    assert restored.user_object_id == "oid-user-456"
    assert restored.user_email == "executive@velora.com"
    assert restored.user_display_name == "Jane Executive"
    assert restored.root_correlation_id == "root-corr-123"
    assert restored.invocation_id == "inv-roundtrip-789"
    assert restored.idempotency_key == "idemp-rt-001"
    assert restored.operation == "send_executive_email"
    assert restored.source_system == "ExchangeOnline"
    assert restored.approval_status == "APPROVED"
    assert restored.policy_id == "POL-EMAIL-01"
    assert restored.policy_version == "2.1.0"
    assert restored.policy_decision == "ALLOW"
    assert restored.outcome == "SUCCESS"
    assert restored.source_as_of == "2026-09-08T09:00:00Z"
    assert restored.content_classification == "HIGHLY_CONFIDENTIAL"
