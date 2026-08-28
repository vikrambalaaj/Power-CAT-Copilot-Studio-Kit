"""Unit and integration tests for Dataverse Audit Foundation with Fail-Closed semantics."""
import asyncio
import unittest
from datetime import datetime, timezone

from productivity_mcp.dataverse_audit import (
    DataverseAuditRecord,
    DataverseClient,
    RECORD_TYPE_AGENT_DELEGATION_START,
    RECORD_TYPE_AGENT_DELEGATION_END,
    RECORD_TYPE_TOOL_EXECUTION_START,
    RECORD_TYPE_TOOL_EXECUTION_END,
    RECORD_TYPE_TRANSACTION_PREVIEW,
    RECORD_TYPE_USER_APPROVAL,
    RECORD_TYPE_TRANSACTION_START,
    RECORD_TYPE_TRANSACTION_RESULT,
    RECORD_TYPE_TRANSACTION_ERROR,
    RECORD_TYPE_POLICY_DECISION,
    RECORD_TYPE_RECONCILIATION,
    RECORD_TYPE_LOGGING_ERROR,
    compute_approval_token_hash,
)


class TestDataverseAuditFoundation(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dv_client = DataverseClient()
        self.dv_client.clear_all_for_testing()

    async def test_all_12_record_types_valid(self):
        """Verify that all 12 required record types are supported and persisted."""
        record_types = [
            RECORD_TYPE_AGENT_DELEGATION_START,
            RECORD_TYPE_AGENT_DELEGATION_END,
            RECORD_TYPE_TOOL_EXECUTION_START,
            RECORD_TYPE_TOOL_EXECUTION_END,
            RECORD_TYPE_TRANSACTION_PREVIEW,
            RECORD_TYPE_USER_APPROVAL,
            RECORD_TYPE_TRANSACTION_START,
            RECORD_TYPE_TRANSACTION_RESULT,
            RECORD_TYPE_TRANSACTION_ERROR,
            RECORD_TYPE_POLICY_DECISION,
            RECORD_TYPE_RECONCILIATION,
            RECORD_TYPE_LOGGING_ERROR,
        ]

        for r_type in record_types:
            rec = DataverseAuditRecord(
                record_type=r_type,
                user_object_id="user-001",
                user_email="balaadm@velora.ae",
                root_correlation_id="corr-test-101",
                operation=f"op_{r_type}",
                invocation_id=f"inv-{r_type}",
            )
            res = await self.dv_client.create_audit_record(rec)
            self.assertEqual(res["status"], "SUCCESS")
            self.assertTrue(res["id"].startswith("AUD-"))

    async def test_alternate_key_idempotency(self):
        """Verify Section 3.4 alternate key idempotency: cre2f_invocationid + cre2f_recordtype."""
        rec1 = DataverseAuditRecord(
            record_type=RECORD_TYPE_TRANSACTION_PREVIEW,
            user_email="balaadm@velora.ae",
            invocation_id="inv-unique-999",
            operation="PrepareEmail",
        )
        res1 = await self.dv_client.create_audit_record(rec1)
        self.assertEqual(res1["status"], "SUCCESS")

        # Attempt duplicate with same invocation_id and record_type
        rec2 = DataverseAuditRecord(
            record_type=RECORD_TYPE_TRANSACTION_PREVIEW,
            user_email="balaadm@velora.ae",
            invocation_id="inv-unique-999",
            operation="PrepareEmail",
        )
        res2 = await self.dv_client.create_audit_record(rec2)
        self.assertEqual(res2["status"], "DUPLICATE_KEY")
        self.assertIn("already exists", res2["message"])

    async def test_duplicate_successful_write_prevention(self):
        """Verify Section 3.4: idempotencykey + operation prevents duplicate write execution."""
        rec_start = DataverseAuditRecord(
            record_type=RECORD_TYPE_TRANSACTION_START,
            user_email="balaadm@velora.ae",
            idempotency_key="idemp-send-888",
            operation="SendApprovedEmail",
            invocation_id="inv-send-01",
        )
        start_res = await self.dv_client.start_write_transaction_fail_closed(rec_start)
        self.assertTrue(start_res["may_proceed"])

        # Complete operation successfully
        await self.dv_client.complete_write_transaction(
            audit_record_id=start_res["audit_record_id"],
            invocation_id="inv-send-01",
            outcome="SUCCESS",
            external_object_id="MSG-OUTLOOK-001",
            operation="SendApprovedEmail",
            idempotency_key="idemp-send-888",
        )

        # Attempt to start the same transaction again with same idempotency key
        rec_retry = DataverseAuditRecord(
            record_type=RECORD_TYPE_TRANSACTION_START,
            user_email="balaadm@velora.ae",
            idempotency_key="idemp-send-888",
            operation="SendApprovedEmail",
            invocation_id="inv-send-02",
        )
        retry_res = await self.dv_client.start_write_transaction_fail_closed(rec_retry)
        self.assertFalse(retry_res["may_proceed"])
        self.assertEqual(retry_res["status"], "DUPLICATE_BLOCKED")

    async def test_fail_closed_write_auditing_when_dataverse_offline(self):
        """Verify Section 3.5: If Dataverse is unavailable, write actions fail closed."""
        self.dv_client.simulate_down = True

        rec_write = DataverseAuditRecord(
            record_type=RECORD_TYPE_TRANSACTION_START,
            user_email="balaadm@velora.ae",
            idempotency_key="idemp-offline-01",
            operation="SendApprovedEmail",
        )
        res = await self.dv_client.start_write_transaction_fail_closed(rec_write)
        self.assertFalse(res["may_proceed"])
        self.assertEqual(res["status"], "FAIL_CLOSED_BLOCKED")
        self.assertIn("Write action blocked", res["error"])

    def test_token_hashing_never_stores_raw_token(self):
        """Verify Section 6.3: Raw approval tokens are hashed with HMAC-SHA256."""
        raw_token = "velora_appr.eyJvcCI6ICJQUkVQQVJFX0VNQUlMIn0.sig123"
        hashed = compute_approval_token_hash(raw_token)
        self.assertNotEqual(raw_token, hashed)
        self.assertEqual(len(hashed), 64)  # 256-bit hex
        # Deterministic
        self.assertEqual(hashed, compute_approval_token_hash(raw_token))


if __name__ == "__main__":
    unittest.main()
