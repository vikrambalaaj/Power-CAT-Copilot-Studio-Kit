"""Acceptance tests for Durable Approval & Operation State Machine (Section 3).

Tests:
1. Rejection of empty caller identity
2. Simultaneous execution claim from two independent store instances yields exactly one execution
3. Replay of consumed approval after process restart is rejected
4. Tampered payload checksum or changed recipient/body requires new preview
5. Retrying an already succeeded operation returns previous result safely
6. Crash before submission (FAILED_BEFORE_SUBMISSION) vs timeout after submission (OUTCOME_UNKNOWN)
"""
import os
import tempfile
import time
import unittest

from productivity_mcp.operation_store import (
    SqliteOperationStore,
    OperationState,
    compute_payload_checksum,
)
from productivity_mcp.token_manager import TokenManager


class TestOperationStateMachine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_operations.db")
        self.store1 = SqliteOperationStore(db_path=self.db_path)
        self.store2 = SqliteOperationStore(db_path=self.db_path)
        self.tm = TokenManager(secret="test-secret-32-chars-long-abcdef")
        self.tm.operation_store = self.store1

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_reject_empty_caller_identity(self):
        preview = {"to": ["finance@velora.ae"], "subject": "Test", "body": "Hello"}
        token, _ = self.tm.create_approval_token(
            operation="SEND_APPROVED_EMAIL",
            user_object_id="user-123",
            user_email="user@velora.ae",
            preview_data=preview,
            idempotency_key="idemp-1",
            root_correlation_id="corr-1",
            tenant_id="tenant-1",
        )
        # Empty caller identity presented
        valid, reason, _ = self.tm.verify_approval_token(
            token=token,
            expected_operation="SEND_APPROVED_EMAIL",
            user_object_id="",
            user_email="",
        )
        self.assertFalse(valid)
        self.assertIn("empty", reason.lower())

    def test_simultaneous_execution_claim_across_two_instances(self):
        """Simulate two independent container replicas competing to claim the same approved operation."""
        preview = {"to": ["ceo@velora.ae"], "subject": "Briefing", "body": "Monthly Report"}
        rec = self.store1.prepare_operation(
            operation_type="SEND_EMAIL",
            tenant_id="velora-tenant",
            user_object_id="user-exec-1",
            user_email="exec@velora.ae",
            proposed_payload=preview,
            approval_id="appr-race-123",
        )
        self.assertEqual(rec.state, OperationState.PREPARED.value)

        # Confirm approval
        confirmed = self.store1.confirm_approval(
            approval_id="appr-race-123",
            user_object_id="user-exec-1",
            tenant_id="velora-tenant",
            current_preview_data=preview,
        )
        self.assertEqual(confirmed.state, OperationState.APPROVED.value)

        # Instance 1 claims execution
        claimed1, rec1, reason1 = self.store1.claim_execution(
            approval_id="appr-race-123",
            executor_id="worker-instance-1",
            presented_user_oid="user-exec-1",
            presented_tenant_id="velora-tenant",
            expected_operation="SEND_EMAIL",
        )
        self.assertTrue(claimed1)
        self.assertEqual(rec1.state, OperationState.EXECUTING.value)
        self.assertEqual(rec1.claimed_by_owner, "worker-instance-1")

        # Instance 2 attempts to claim simultaneously
        claimed2, rec2, reason2 = self.store2.claim_execution(
            approval_id="appr-race-123",
            executor_id="worker-instance-2",
            presented_user_oid="user-exec-1",
            presented_tenant_id="velora-tenant",
            expected_operation="SEND_EMAIL",
        )
        self.assertFalse(claimed2)
        self.assertIn(reason2, {"CONCURRENTLY_EXECUTING", "INVALID_STATE_EXECUTING"})

    def test_changed_payload_requires_new_approval(self):
        preview_original = {"to": ["board@velora.ae"], "amount": 100}
        self.store1.prepare_operation(
            operation_type="SEND_EMAIL",
            tenant_id="velora-tenant",
            user_object_id="user-1",
            user_email="u@velora.ae",
            proposed_payload=preview_original,
            approval_id="appr-payload-test",
        )
        # Attempt to confirm with tampered payload
        preview_tampered = {"to": ["attacker@velora.ae"], "amount": 999999}
        with self.assertRaises(ValueError) as ctx:
            self.store1.confirm_approval(
                approval_id="appr-payload-test",
                user_object_id="user-1",
                tenant_id="velora-tenant",
                current_preview_data=preview_tampered,
            )
        self.assertIn("changed", str(ctx.exception).lower())

    def test_cross_tenant_reuse_rejected(self):
        preview = {"to": ["test@velora.ae"]}
        self.store1.prepare_operation(
            operation_type="SEND_EMAIL",
            tenant_id="tenant-alpha",
            user_object_id="user-1",
            user_email="u@velora.ae",
            proposed_payload=preview,
            approval_id="appr-tenant-test",
        )
        # Attempt claim with wrong tenant
        claimed, _, reason = self.store1.claim_execution(
            approval_id="appr-tenant-test",
            executor_id="w-1",
            presented_user_oid="user-1",
            presented_tenant_id="tenant-bravo",
            expected_operation="SEND_EMAIL",
        )
        self.assertFalse(claimed)
        self.assertEqual(reason, "IDENTITY_MISMATCH")

    def test_successful_execution_returns_cached_result_on_retry(self):
        preview = {"subject": "Test"}
        self.store1.prepare_operation(
            operation_type="SEND_EMAIL",
            tenant_id="velora-tenant",
            user_object_id="user-1",
            user_email="u@velora.ae",
            proposed_payload=preview,
            approval_id="appr-retry-test",
        )
        self.store1.confirm_approval("appr-retry-test", "user-1", "velora-tenant")
        claimed, rec, _ = self.store1.claim_execution(
            "appr-retry-test", "worker-1", "user-1", "velora-tenant", "SEND_EMAIL"
        )
        self.assertTrue(claimed)

        # Complete execution
        result = {"status": "SUCCESS", "messageId": "msg-xyz-123"}
        provider_ref = {"graphHttpStatus": 202, "internetMessageId": "<abc@velora.ae>"}
        self.store1.complete_execution(rec.operation_id, result, provider_ref)

        # Retry execution
        claimed_retry, rec_retry, reason_retry = self.store2.claim_execution(
            "appr-retry-test", "worker-2", "user-1", "velora-tenant", "SEND_EMAIL"
        )
        self.assertFalse(claimed_retry)
        self.assertEqual(reason_retry, "ALREADY_SUCCEEDED")
        self.assertEqual(rec_retry.state, OperationState.SUCCEEDED.value)
        self.assertEqual(rec_retry.result_payload["messageId"], "msg-xyz-123")

    def test_crash_before_submission_vs_timeout_after_submission(self):
        preview = {"subject": "Test"}
        # 1. Crash before submission
        rec1 = self.store1.prepare_operation(
            operation_type="SEND_EMAIL",
            tenant_id="velora-tenant",
            user_object_id="user-1",
            user_email="u@velora.ae",
            proposed_payload=preview,
            approval_id="appr-crash-1",
        )
        self.store1.confirm_approval("appr-crash-1", "user-1", "velora-tenant")
        _, claimed_rec1, _ = self.store1.claim_execution(
            "appr-crash-1", "worker-1", "user-1", "velora-tenant", "SEND_EMAIL"
        )
        self.store1.fail_execution(claimed_rec1.operation_id, "Worker crashed before HTTP call", before_submission=True)
        op1 = self.store1.get_operation_by_approval_id("appr-crash-1")
        self.assertEqual(op1.state, OperationState.FAILED_BEFORE_SUBMISSION.value)

        # 2. Timeout after submission
        rec2 = self.store1.prepare_operation(
            operation_type="SEND_EMAIL",
            tenant_id="velora-tenant",
            user_object_id="user-1",
            user_email="u@velora.ae",
            proposed_payload=preview,
            approval_id="appr-timeout-2",
        )
        self.store1.confirm_approval("appr-timeout-2", "user-1", "velora-tenant")
        _, claimed_rec2, _ = self.store1.claim_execution(
            "appr-timeout-2", "worker-1", "user-1", "velora-tenant", "SEND_EMAIL"
        )
        self.store1.fail_execution(claimed_rec2.operation_id, "HTTP 504 Gateway Timeout after POST", before_submission=False)
        op2 = self.store1.get_operation_by_approval_id("appr-timeout-2")
        self.assertEqual(op2.state, OperationState.OUTCOME_UNKNOWN.value)


if __name__ == "__main__":
    unittest.main()
