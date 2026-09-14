"""Tests for Unified Operation Store Lifecycle (W03, R08, Acceptance T03)."""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone

from productivity_mcp.operation_store import (
    AccessDeniedError,
    ConcurrencyConflictError,
    DurableOperationStore,
    InvalidTokenError,
    OperationRecord,
    OperationState,
    SqliteOperationStore,
)


class TestOperationStoreLifecycle(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_ops.db")
        self.store = SqliteOperationStore(db_path=self.db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    async def test_prepare_and_token_hash_isolation(self):
        """Verify prepare hashes raw approval token with SHA-256 and never persists bearer raw token."""
        raw_token = "secret-bearer-token-12345"
        rec = self.store.prepare_operation(
            operation_type="send_email",
            tenant_id="tenant-alpha",
            user_object_id="usr-123",
            user_email="exec@velora.ae",
            proposed_payload={"to": "board@velora.ae", "subject": "Notice"},
            approval_token=raw_token,
            expiry_minutes=15,
        )
        self.assertTrue(rec.operation_id.startswith("OP-"))
        self.assertTrue(rec.approval_id)

        # Retrieve operation and verify token_hash
        fetched = self.store.get_operation_by_id(rec.operation_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.state, OperationState.PREPARED)
        # Raw token must NOT be stored in plaintext
        self.assertNotEqual(fetched.token_hash, raw_token)
        self.assertEqual(len(fetched.token_hash), 64)  # SHA-256 hex string

    async def test_tenant_isolation_denies_cross_tenant_access(self):
        """Verify Tenant A cannot access or mutate Tenant B operations."""
        rec = self.store.prepare_operation(
            operation_type="send_email",
            tenant_id="tenant-a",
            user_object_id="usr-a",
            user_email="alice@tenant-a.ae",
            proposed_payload={"subject": "Confidential A"},
            approval_token="tok-a",
            expiry_minutes=10,
        )

        # Tenant B attempt to confirm approval on Tenant A operation
        with self.assertRaises(AccessDeniedError):
            self.store.confirm_approval(
                approval_id=rec.approval_id,
                tenant_id="tenant-b",
                user_object_id="usr-b",
                approval_token="tok-a",
            )

        # Ensure state remains PREPARED
        fetched = self.store.get_operation_by_id(rec.operation_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.state, OperationState.PREPARED)

    async def test_full_approval_claim_and_completion_lifecycle(self):
        """Verify full two-step approval, worker claim, and completion."""
        raw_token = "valid-token-777"
        rec = self.store.prepare_operation(
            operation_type="create_calendar_event",
            tenant_id="velora-corp",
            user_object_id="usr-cal",
            user_email="cal@velora.ae",
            proposed_payload={"title": "Q3 Strategy"},
            approval_token=raw_token,
            expiry_minutes=30,
        )

        # 1. Confirm Approval
        approved_rec = self.store.confirm_approval(
            approval_id=rec.approval_id,
            tenant_id="velora-corp",
            user_object_id="usr-cal",
            approval_token=raw_token,
        )
        self.assertEqual(approved_rec.state, OperationState.APPROVED)

        # 2. Worker 1 claims execution
        claimed, claimed_rec, reason = self.store.claim_execution(
            approval_id=rec.approval_id,
            executor_id="worker-node-1",
            presented_user_oid="usr-cal",
            presented_tenant_id="velora-corp",
            expected_operation="create_calendar_event",
            lease_seconds=60,
        )
        self.assertTrue(claimed)
        self.assertEqual(claimed_rec.state, OperationState.EXECUTING)
        self.assertEqual(claimed_rec.claimed_by_owner, "worker-node-1")

        # 3. Worker 2 attempts concurrent claim - fails with conflict
        claimed2, rec2, reason2 = self.store.claim_execution(
            approval_id=rec.approval_id,
            executor_id="worker-node-2",
            presented_user_oid="usr-cal",
            presented_tenant_id="velora-corp",
            expected_operation="create_calendar_event",
            lease_seconds=60,
        )
        self.assertFalse(claimed2)
        self.assertIn(reason2, {"CONCURRENTLY_EXECUTING", "INVALID_STATE_EXECUTING"})

        # 4. Complete execution with result data
        completed_rec = self.store.record_success(
            approval_id=rec.approval_id,
            result_payload={"eventId": "EVT-M365-1001", "status": "CONFIRMED"},
        )
        self.assertEqual(completed_rec.state, OperationState.SUCCEEDED)
        self.assertEqual(completed_rec.result_payload["eventId"], "EVT-M365-1001")

    async def test_rejection_lifecycle(self):
        """Verify rejection moves state to REJECTED."""
        rec = self.store.prepare_operation(
            operation_type="send_email",
            tenant_id="velora-corp",
            user_object_id="usr-rej",
            user_email="rej@velora.ae",
            proposed_payload={},
            approval_token="tok-reject",
            expiry_minutes=15,
        )
        rejected_rec = self.store.reject_operation(
            approval_id=rec.approval_id,
            tenant_id="velora-corp",
            user_object_id="usr-rej",
            reason="Executive rejected proposed email content.",
        )
        self.assertEqual(rejected_rec.state, OperationState.REJECTED)
        self.assertIn("Executive rejected", rejected_rec.last_error)


if __name__ == "__main__":
    unittest.main()
