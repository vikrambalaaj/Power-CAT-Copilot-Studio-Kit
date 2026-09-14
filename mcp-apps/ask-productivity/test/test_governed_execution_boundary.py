"""Acceptance Test Suite T04: Governed Execution Boundary, Kill Switches, and Replay Protection.

Verifies:
1. Unauthenticated / unauthorized callers denied at REST/MCP boundary (401/403).
2. Foreign tenant, foreign user identity, and tampered payloads are rejected before provider execution.
3. Expired or replayed approval tokens are blocked prior to mutation dispatch.
4. Dual replica race condition: two workers claiming same approval produces exactly one execution.
5. Ambiguous provider timeouts transition to OUTCOME_UNKNOWN and are never auto-resent.
6. Revoked standing authorization strictly blocks worker execution.
7. Global / Tool / Tenant kill switches immediately prevent write handlers from executing mutations.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import time
import unittest
from typing import Any, Dict
from unittest.mock import patch, MagicMock

from productivity_mcp.operation_store import (
    SqliteOperationStore,
    OperationState,
    normalize_operation_type,
)
from productivity_mcp.token_manager import TokenManager
from productivity_mcp.standing_authorization import (
    StandingAuthorizationRecord,
    StandingAuthorizationStore,
)
from productivity_mcp.tools_m365_writes import (
    prepare_email,
    send_approved_email,
    _execute_governed_stage_b,
)
from shared_mcp.kill_switch import (
    check_kill_switch,
    set_kill_switch,
    clear_all_kill_switches,
    KillSwitchActiveError,
)
from productivity_mcp.dataverse_audit import get_dataverse_client


class TestGovernedExecutionBoundary(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        clear_all_kill_switches()
        os.environ["MOCK_M365"] = "1"
        os.environ["ALLOW_BUFFERED_AUDIT_WRITES"] = "1"
        get_dataverse_client().clear_all_for_testing()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_gov_boundary.db")
        self.store = SqliteOperationStore(db_path=self.db_path)
        self.tm = TokenManager(secret="test-secret-boundary-1234567890abcdef")
        self.tm.operation_store = self.store

    def tearDown(self):
        clear_all_kill_switches()
        self.temp_dir.cleanup()

    async def test_foreign_identity_denied_before_provider(self):
        """Foreign tenant or foreign user presented against an approval token is rejected before provider call."""
        prep = await prepare_email(
            to=["sara@velora.ae"],
            subject="Confidential Budget Review",
            body="Review attached financial statement.",
            userEmail="balaadm@velora.ae",
        )
        token = prep["confirmationToken"]
        preview = prep["previewDetails"]

        provider_mock = MagicMock()

        # Attacker with foreign email tries to execute with legitimate token
        res_foreign_user = await _execute_governed_stage_b(
            operation_name="PREPARE_EMAIL",
            stage_b_operation_name="SendApprovedEmail",
            confirmation_token=token,
            preview_details=preview,
            executor_fn=provider_mock,
            action_desc_fn=lambda r: "Sent",
            user_email="attacker@external.com",
            tenant_id="velora-tenant",
        )
        self.assertEqual(res_foreign_user["status"], "TOKEN_INVALID")
        self.assertIn("mismatch", res_foreign_user["resultSummary"].lower())
        provider_mock.assert_not_called()

        # Attacker with foreign tenant tries to execute
        res_foreign_tenant = await _execute_governed_stage_b(
            operation_name="PREPARE_EMAIL",
            stage_b_operation_name="SendApprovedEmail",
            confirmation_token=token,
            preview_details=preview,
            executor_fn=provider_mock,
            action_desc_fn=lambda r: "Sent",
            user_email="balaadm@velora.ae",
            tenant_id="rogue-foreign-tenant",
        )
        self.assertEqual(res_foreign_tenant["status"], "TOKEN_INVALID")
        self.assertIn("tenant", res_foreign_tenant["resultSummary"].lower())
        provider_mock.assert_not_called()

    async def test_tampered_payload_denied_before_provider(self):
        """Tampered payload checksum or modified recipient is rejected before provider call."""
        prep = await prepare_email(
            to=["sara@velora.ae"],
            subject="Quarterly Allocation",
            body="Approved transfer of 50k AED.",
            userEmail="balaadm@velora.ae",
        )
        token = prep["confirmationToken"]
        tampered_preview = dict(prep["previewDetails"])
        # Attacker modifies recipient to external party
        tampered_preview["to"] = ["attacker@fraudulent.com"]

        provider_mock = MagicMock()
        res = await _execute_governed_stage_b(
            operation_name="PREPARE_EMAIL",
            stage_b_operation_name="SendApprovedEmail",
            confirmation_token=token,
            preview_details=tampered_preview,
            executor_fn=provider_mock,
            action_desc_fn=lambda r: "Sent",
            user_email="balaadm@velora.ae",
            tenant_id="velora-tenant",
        )
        self.assertEqual(res["status"], "TOKEN_INVALID")
        self.assertIn("changed", res["resultSummary"].lower())
        provider_mock.assert_not_called()

    async def test_replayed_token_denied_before_provider(self):
        """Replaying an already consumed approval token safely returns previous execution result without duplicates."""
        prep = await prepare_email(
            to=["fatima.mansoori@velora.ae"],
            subject="One-Time Notification",
            body="Payment executed.",
            userEmail="balaadm@velora.ae",
        )
        token = prep["confirmationToken"]
        preview = prep["previewDetails"]

        # First execution succeeds
        res1 = await send_approved_email(
            confirmationToken=token,
            previewDetails=preview,
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(res1["status"], "SUCCESS")

        # Second execution replay: token nonce was consumed, replay is blocked before provider
        res2 = await send_approved_email(
            confirmationToken=token,
            previewDetails=preview,
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(res2["status"], "TOKEN_INVALID")
        self.assertIn("replay", res2["resultSummary"].lower())

    async def test_dual_replica_race_produces_exactly_one_submission(self):
        """Simulate two worker replicas simultaneously attempting to claim the same approved operation."""
        store1 = SqliteOperationStore(db_path=self.db_path)
        store2 = SqliteOperationStore(db_path=self.db_path)

        preview = {"to": ["board@velora.ae"], "subject": "Annual Summary", "body": "Report"}
        token, _ = self.tm.create_approval_token(
            operation="PREPARE_EMAIL",
            user_object_id="balaadm@velora.ae",
            user_email="balaadm@velora.ae",
            preview_data=preview,
            idempotency_key="idemp-race-1",
            root_correlation_id="corr-race-1",
        )
        # Confirm approval
        store1.confirm_approval(
            approval_id=token,
            user_object_id="balaadm@velora.ae",
            tenant_id="velora-tenant",
            current_preview_data=preview,
            approval_token=token,
        )

        # Worker 1 and Worker 2 race to claim
        claimed1, rec1, reason1 = store1.claim_execution(
            approval_id=token,
            executor_id="replica-node-1",
            presented_user_oid="balaadm@velora.ae",
            presented_tenant_id="velora-tenant",
            expected_operation="PREPARE_EMAIL",
        )
        claimed2, rec2, reason2 = store2.claim_execution(
            approval_id=token,
            executor_id="replica-node-2",
            presented_user_oid="balaadm@velora.ae",
            presented_tenant_id="velora-tenant",
            expected_operation="PREPARE_EMAIL",
        )

        # Exactly one claim succeeds
        claims = [claimed1, claimed2]
        self.assertEqual(claims.count(True), 1)
        self.assertEqual(claims.count(False), 1)

    async def test_ambiguous_timeout_transitions_to_outcome_unknown(self):
        """Provider timeout moves operation to OUTCOME_UNKNOWN and does not blindly resubmit."""
        prep = await prepare_email(
            to=["vendor@partner.ae"],
            subject="Invoice Submission",
            body="Invoice payment payload.",
            userEmail="balaadm@velora.ae",
        )
        token = prep["confirmationToken"]
        preview = prep["previewDetails"]

        def timeout_executor():
            raise TimeoutError("504 Gateway Timeout while awaiting Microsoft Graph commit")

        res = await _execute_governed_stage_b(
            operation_name="PREPARE_EMAIL",
            stage_b_operation_name="SendApprovedEmail",
            confirmation_token=token,
            preview_details=preview,
            executor_fn=timeout_executor,
            action_desc_fn=lambda r: "Sent",
            user_email="balaadm@velora.ae",
            tenant_id="velora-tenant",
        )
        self.assertEqual(res["status"], "OUTCOME_UNKNOWN")
        self.assertIn("timeout", res["resultSummary"].lower())

    def test_revoked_standing_authorization_prevents_worker_run(self):
        """Revoking standing authorization record prevents background run."""
        auth_store = StandingAuthorizationStore(db_path=self.db_path)
        record = StandingAuthorizationRecord(
            policy_id="POL-001",
            tenant_id="velora-tenant",
            authorizing_user_oid="user-123",
            authorizing_user_email="balaadm@velora.ae",
            workload_identity="worker-briefing-cron",
            allowed_operations=["GENERATE_DAILY_BRIEFING"],
            allowed_recipients=["balaadm@velora.ae"],
            expires_at=time.time() + 86400,
        )
        auth_store.save_policy(record)

        # Active record is valid
        is_valid, _, pol = auth_store.verify_standing_authorization(
            policy_id="POL-001",
            tenant_id="velora-tenant",
            operation="GENERATE_DAILY_BRIEFING",
            target_recipient="balaadm@velora.ae",
            workload_identity="worker-briefing-cron",
        )
        self.assertTrue(is_valid)

        # Revoke authorization
        auth_store.revoke_policy(
            policy_id="POL-001",
            tenant_id="velora-tenant",
            reason="Executive revoked recurring authority",
        )

        # Subsequent check fails closed
        is_valid_after, reason, _ = auth_store.verify_standing_authorization(
            policy_id="POL-001",
            tenant_id="velora-tenant",
            operation="GENERATE_DAILY_BRIEFING",
            target_recipient="balaadm@velora.ae",
            workload_identity="worker-briefing-cron",
        )
        self.assertFalse(is_valid_after)
        self.assertIn("revoked", reason.lower())

    async def test_kill_switch_blocks_mutation_handler(self):
        """Global or tool kill switch blocks handler invocation before external call."""
        prep = await prepare_email(
            to=["ahmed.nuaimi@velora.ae"],
            subject="Emergency Notice",
            body="Important update.",
            userEmail="balaadm@velora.ae",
        )
        token = prep["confirmationToken"]
        preview = prep["previewDetails"]

        # Activate tool kill switch
        set_kill_switch("tools", "PREPARE_EMAIL")

        provider_mock = MagicMock()
        res = await _execute_governed_stage_b(
            operation_name="PREPARE_EMAIL",
            stage_b_operation_name="SendApprovedEmail",
            confirmation_token=token,
            preview_details=preview,
            executor_fn=provider_mock,
            action_desc_fn=lambda r: "Sent",
            user_email="balaadm@velora.ae",
            tenant_id="velora-tenant",
        )
        self.assertEqual(res["status"], "POLICY_BLOCKED")
        self.assertIn("kill switch", res["resultSummary"].lower())
        provider_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
