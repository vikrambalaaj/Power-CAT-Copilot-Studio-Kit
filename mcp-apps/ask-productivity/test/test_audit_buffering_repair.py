"""Tests for Audit Buffering Repair and Reconciliation Queue (W03, E11, Acceptance T03)."""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from productivity_mcp.audit_client import AuditReconciliationQueue, ProductivityAuditService
from productivity_mcp.dataverse_audit import (
    AuditCommitStatus,
    DataverseAuditRecord,
    DataverseClient,
    RECORD_TYPE_TOOL_EXECUTION_END,
    RECORD_TYPE_TRANSACTION_PREVIEW,
    RECORD_TYPE_TRANSACTION_RESULT,
    RECORD_TYPE_TRANSACTION_START,
)


class TestAuditBufferingRepair(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.rec_db_path = os.path.join(self.tmp_dir.name, "reconcile.db")
        
        # Unconfigured / offline client (is_live=False)
        self.offline_client = DataverseClient(
            base_url="",
            tenant_id="",
            client_id="",
            client_secret="",
        )
        self.offline_client.simulate_unconfigured = True
        self.offline_client.clear_all_for_testing()

    def tearDown(self):
        self.tmp_dir.cleanup()

    async def test_buffered_audit_does_not_populate_confirmed_commit_indexes(self):
        """Verify buffered audits do NOT enter _alternate_keys_index or _idempotency_index (E11)."""
        inv_id = "inv-buf-test-01"
        idemp_key = "idemp-buf-test-01"
        op = "SendApprovedEmail"

        rec = DataverseAuditRecord(
            record_type=RECORD_TYPE_TRANSACTION_START,
            invocation_id=inv_id,
            idempotency_key=idemp_key,
            operation=op,
            user_email="exec@velora.ae",
        )

        # Call create_audit_record on unconfigured client -> buffers
        res = await self.offline_client.create_audit_record(rec)
        self.assertEqual(res["commit_status"], AuditCommitStatus.BUFFERED)
        self.assertTrue(res["id"].startswith("BUF-"))

        # Confirmed-commit index MUST NOT contain this uncommitted invocation_id
        self.assertFalse(self.offline_client.check_alternate_key_exists(inv_id, RECORD_TYPE_TRANSACTION_START))

        # Confirmed-commit idempotency index MUST NOT contain this key
        self.assertFalse(self.offline_client.check_successful_idempotency_exists(idemp_key, op))

    async def test_buffered_audit_retry_still_denies_governed_writes(self):
        """Acceptance T03: buffered audit retry still denies governed writes."""
        rec_start = DataverseAuditRecord(
            record_type=RECORD_TYPE_TRANSACTION_START,
            invocation_id="inv-retry-01",
            idempotency_key="idemp-retry-01",
            operation="SendApprovedEmail",
            user_email="exec@velora.ae",
        )

        # First attempt when Dataverse is offline
        res1 = await self.offline_client.start_write_transaction_fail_closed(rec_start)
        self.assertFalse(res1["may_proceed"], "First write must fail closed when Dataverse is uncommitted")

        # Retry attempt with identical record
        res2 = await self.offline_client.start_write_transaction_fail_closed(rec_start)
        self.assertFalse(res2["may_proceed"], "Retry MUST STILL fail closed; cannot falsely claim ALREADY_COMMITTED")

    async def test_arbitrary_412_not_automatically_duplicate(self):
        """Verify arbitrary 412 (e.g. ETag mismatch) raises error rather than claiming ALREADY_COMMITTED."""
        live_client = DataverseClient(
            base_url="https://example.crm.dynamics.com",
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",
        )
        live_client.clear_all_for_testing()

        # Simulate arbitrary 412 (ETag mismatch, not duplicate key)
        mock_response = httpx.Response(
            status_code=412,
            request=httpx.Request("POST", "https://example.crm.dynamics.com"),
            text="The version of the existing record doesn't match the version provided.",
        )
        live_client._create_live_audit_row = AsyncMock(
            side_effect=httpx.HTTPStatusError("Precondition Failed", request=mock_response.request, response=mock_response)
        )

        rec = DataverseAuditRecord(
            record_type=RECORD_TYPE_TRANSACTION_START,
            invocation_id="inv-412-etag",
            idempotency_key="idemp-412",
            operation="CreateTask",
            user_email="exec@velora.ae",
        )

        # Must raise ConnectionError / fail closed, NOT return ALREADY_COMMITTED
        with self.assertRaises(ConnectionError):
            await live_client.create_audit_record(rec)

    async def test_durable_reconciliation_queue_lifecycle(self):
        """Verify failed or buffered audits are enqueued in durable SQLite queue and replayed."""
        queue = AuditReconciliationQueue(db_path=self.rec_db_path)
        self.assertEqual(queue.get_pending_count(), 0)

        rec = DataverseAuditRecord(
            record_type=RECORD_TYPE_TOOL_EXECUTION_END,
            invocation_id="inv-recon-01",
            operation="list_emails",
            user_email="exec@velora.ae",
            outcome="SUCCESS",
        )

        # Enqueue item
        q_id = queue.enqueue(rec, reason="Dataverse endpoint offline")
        self.assertTrue(q_id.startswith("REC-Q-"))
        self.assertEqual(queue.get_pending_count(), 1)

        # Reconcile using a client whose _create_live_audit_row succeeds
        live_client = DataverseClient(
            base_url="https://example.crm.dynamics.com",
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",
        )
        live_client._create_live_audit_row = AsyncMock(return_value="RECON-ROW-001")

        report = await queue.reconcile_pending(live_client, max_items=10)
        self.assertEqual(report["reconciled"], 1)
        self.assertEqual(report["failed"], 0)
        self.assertEqual(queue.get_pending_count(), 0)


if __name__ == "__main__":
    unittest.main()
