"""Acceptance Test Suite for Briefing Variants and Governed Subscriptions (W07 / Acceptance T07).

Validates:
1. MORNING, PRE_MEETING, and END_OF_DAY briefing synthesis via BriefingService.
2. Canceled meeting exclusion invariant in pre-meeting dossier.
3. Truthful EOD attribution invariant: completed tasks come from Planner; sent emails are NEVER counted as completed tasks.
4. Deterministic snapshot SHA-256 content hashing and binding to preview/email payload.
5. Governed 2-step subscription lifecycle (PREPARE -> CONFIRM -> REVOKE).
6. Worker sweep idempotency: exactly one dispatch per scheduled occurrence, zero duplicate sends.
7. Zero dispatches for revoked or disabled subscriptions.
8. Server handoff route execution for all new operations.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

from productivity_mcp.briefing_service import BriefingService, compute_content_hash, get_briefing_service
from productivity_mcp.dataverse_audit import get_dataverse_client
from productivity_mcp.evidence_contracts import ConfidenceLabel, OperationStatus, SubscriptionKind
from productivity_mcp.m365_client import Microsoft365Client, seed_test_m365_data
from productivity_mcp.models import HandoffRequest
from productivity_mcp.operation_store import get_operation_store
from productivity_mcp.server import handle_handoff_request
from productivity_mcp.subscription_service import SubscriptionService, reset_subscription_service_for_testing
from productivity_mcp.worker import evaluate_and_dispatch_subscriptions, run_worker_pass


class TestBriefingVariantsAndSubscriptions(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        os.environ["MOCK_M365"] = "1"
        os.environ["VELORA_OUTBOX_DIR"] = os.path.join(self.tmp_dir, "outbox")
        os.environ["VELORA_SUBSCRIPTION_DB"] = os.path.join(self.tmp_dir, "subscriptions.db")
        os.environ["VELORA_OPERATION_STORE_DB"] = os.path.join(self.tmp_dir, "opstore.db")
        os.environ["GATEWAY_SHARED_SECRET"] = "velora_test_secret_32_bytes_long!!"
        os.environ["TOKEN_SIGNING_KEY"] = "test_signing_key_32_bytes_long_hmac!"

        seed_test_m365_data()
        get_dataverse_client().clear_all_for_testing()
        reset_subscription_service_for_testing()
        self.sub_svc = SubscriptionService(db_path=os.environ["VELORA_SUBSCRIPTION_DB"])
        self.client = Microsoft365Client(user_email="balaadm@velora.ae")
        self.ref_time = datetime(2026, 8, 26, 7, 0, 0, tzinfo=timezone.utc)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_morning_briefing_synthesis_and_content_hash(self):
        service = BriefingService()
        res = service.get_morning_briefing(self.client, user_email="balaadm@velora.ae", reference_time=self.ref_time)

        self.assertEqual(res["kind"], "MORNING")
        self.assertEqual(res["status"], OperationStatus.SUCCESS.value)
        self.assertGreaterEqual(len(res["meetings"]), 1)
        self.assertGreaterEqual(len(res["tasks"]), 1)
        self.assertTrue(len(res["contentHash"]) == 64)  # SHA-256 hex string
        self.assertIn("renderedHtml", res)
        self.assertIn("Snapshot SHA-256", res["renderedHtml"])

        # Validate deterministic hashing
        hash_repeat = compute_content_hash({
            "kind": "MORNING",
            "date": res["date"],
            "executive_name": res["executive_name"],
            "executive_email": res["executive_email"],
            "summary_text": res["summary_text"],
            "meetings_count": len(res["meetings"]),
            "tasks_count": len(res["tasks"]),
            "overdue_count": len(res["overdue_tasks"]),
            "attention_count": len(res["attention_items"]),
            "approvals_count": len(res["approvals"]),
            "meetings": res["meetings"],
            "tasks": res["tasks"],
            "overdue_tasks": res["overdue_tasks"],
            "attention_items": res["attention_items"],
            "approvals": res["approvals"],
            "warnings": res["warnings"],
        })
        self.assertEqual(res["contentHash"], hash_repeat)

    def test_pre_meeting_briefing_excludes_canceled_events(self):
        service = BriefingService()
        raw_events = self.client.list_calendar_events()

        # Find any canceled event if present or synthesize test check
        res = service.get_pre_meeting_briefing(
            client=self.client,
            user_email="balaadm@velora.ae",
            reference_time=self.ref_time,
        )

        self.assertEqual(res["kind"], "PRE_MEETING")
        if res.get("targetEvent"):
            # Must strictly not be canceled
            self.assertFalse(res["targetEvent"].get("isCancelled", False))
            self.assertIn("attendees", res)
            self.assertTrue(len(res["contentHash"]) == 64)

    def test_eod_digest_truthful_attribution(self):
        service = BriefingService()
        res = service.get_end_of_day_digest(
            client=self.client,
            user_email="balaadm@velora.ae",
            local_schedule="17:30",
            reference_time=self.ref_time,
        )

        self.assertEqual(res["kind"], "END_OF_DAY")
        self.assertEqual(res["status"], OperationStatus.SUCCESS.value)

        # Ground truth task completion check:
        # Every item in completed_tasks MUST be a Planner task, not an email
        for task in res["completed_tasks"]:
            self.assertIn("percentComplete", task)
            self.assertEqual(task["percentComplete"], 100)
            self.assertNotIn("receivedDateTime", task)  # NOT an email!

        # Content hash check
        self.assertTrue(len(res["contentHash"]) == 64)
        self.assertIn("Closed-Loop Digest", res["renderedHtml"])

    def test_subscription_two_step_lifecycle(self):
        # 1. PREPARE: creates DRAFT subscription (enabled=0)
        sub, token = self.sub_svc.prepare_subscription(
            tenant_id="velora-tenant",
            owner="user-vikram",
            mailbox="balaadm@velora.ae",
            sender="agent@velora.ae",
            recipients=["balaadm@velora.ae"],
            kind="MORNING",
            timezone_str="Asia/Dubai",
            local_schedule="07:00",
            user_object_id="user-vikram",
            user_email="balaadm@velora.ae",
        )

        self.assertFalse(sub.enabled)  # Strict default disabled!
        self.assertTrue(token.startswith("velora_appr."))

        # 2. Verify active list is empty before confirmation
        active_before = self.sub_svc.list_active_subscriptions(tenant_id="velora-tenant")
        self.assertEqual(len(active_before), 0)

        # 3. CONFIRM: activates subscription
        confirmed = self.sub_svc.confirm_subscription(
            confirmation_token=token,
            subscription_id=sub.subscriptionId,
            user_object_id="user-vikram",
            user_email="balaadm@velora.ae",
            tenant_id="velora-tenant",
        )
        self.assertTrue(confirmed.enabled)

        active_after = self.sub_svc.list_active_subscriptions(tenant_id="velora-tenant")
        self.assertEqual(len(active_after), 1)
        self.assertEqual(active_after[0].subscriptionId, sub.subscriptionId)

        # 4. REVOKE: disables subscription
        revoked = self.sub_svc.revoke_subscription(
            subscription_id=sub.subscriptionId,
            tenant_id="velora-tenant",
            revoked_by="user-vikram",
        )
        self.assertFalse(revoked.enabled)

        active_revoked = self.sub_svc.list_active_subscriptions(tenant_id="velora-tenant")
        self.assertEqual(len(active_revoked), 0)

    def test_worker_pass_idempotency_and_zero_duplicate_sends(self):
        # Set up an active confirmed subscription
        sub, token = self.sub_svc.prepare_subscription(
            tenant_id="velora-tenant",
            owner="user-vikram",
            mailbox="balaadm@velora.ae",
            sender="agent@velora.ae",
            recipients=["balaadm@velora.ae"],
            kind="MORNING",
            timezone_str="Asia/Dubai",
            local_schedule="07:00",
            user_object_id="user-vikram",
            user_email="balaadm@velora.ae",
        )
        self.sub_svc.confirm_subscription(
            confirmation_token=token,
            subscription_id=sub.subscriptionId,
            user_object_id="user-vikram",
            user_email="balaadm@velora.ae",
            tenant_id="velora-tenant",
        )

        # Execution time: 07:05 GST on 2026-09-14 (due window)
        # Note: 07:05 GST = 03:05 UTC
        run_clock = datetime(2026, 9, 14, 3, 5, 0, tzinfo=timezone.utc)

        # First worker sweep: should dispatch exactly 1 briefing
        dispatched_pass1 = evaluate_and_dispatch_subscriptions(
            client=self.client,
            tenant_id="velora-tenant",
            now=run_clock,
        )
        self.assertEqual(dispatched_pass1, 1)

        # Second worker sweep with SAME clock: run_key is already in history, must dispatch 0!
        dispatched_pass2 = evaluate_and_dispatch_subscriptions(
            client=self.client,
            tenant_id="velora-tenant",
            now=run_clock,
        )
        self.assertEqual(dispatched_pass2, 0)

        # Check run history
        history = self.sub_svc.get_run_history(sub.subscriptionId)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "SUCCESS")

    def test_revoked_subscription_yields_zero_worker_dispatches(self):
        sub, token = self.sub_svc.prepare_subscription(
            tenant_id="velora-tenant",
            owner="user-vikram",
            mailbox="balaadm@velora.ae",
            sender="agent@velora.ae",
            recipients=["balaadm@velora.ae"],
            kind="MORNING",
            timezone_str="Asia/Dubai",
            local_schedule="07:00",
            user_object_id="user-vikram",
            user_email="balaadm@velora.ae",
        )
        self.sub_svc.confirm_subscription(
            confirmation_token=token,
            subscription_id=sub.subscriptionId,
            user_object_id="user-vikram",
            user_email="balaadm@velora.ae",
            tenant_id="velora-tenant",
        )
        # Revoke immediately
        self.sub_svc.revoke_subscription(
            subscription_id=sub.subscriptionId,
            tenant_id="velora-tenant",
            revoked_by="user-vikram",
        )

        run_clock = datetime(2026, 9, 14, 3, 5, 0, tzinfo=timezone.utc)
        dispatched = evaluate_and_dispatch_subscriptions(
            client=self.client,
            tenant_id="velora-tenant",
            now=run_clock,
        )
        self.assertEqual(dispatched, 0)

    async def test_server_handoff_briefing_routes(self):
        # 1. GET_PRE_MEETING_BRIEF
        req_pre = HandoffRequest(
            task="PreMeetingBriefing",
            operation="GET_PRE_MEETING_BRIEF",
            conversationId="conv-pre-01",
            turnId="turn-1",
            rootCorrelationId="corr-test-pre-01",
            userObjectId="user-vikram",
            userEmail="balaadm@velora.ae",
            parameters={"eventId": "EVT-2026-0826-01", "leadTimeMinutes": 15},
        )
        resp_pre = await handle_handoff_request(req_pre)
        self.assertEqual(resp_pre.status, "SUCCESS")
        self.assertIn("Pre-Meeting Briefing", resp_pre.resultSummary)

        # 2. GET_END_OF_DAY_DIGEST
        req_eod = HandoffRequest(
            task="EndOfDayDigest",
            operation="GET_END_OF_DAY_DIGEST",
            conversationId="conv-eod-01",
            turnId="turn-1",
            rootCorrelationId="corr-test-eod-01",
            userObjectId="user-vikram",
            userEmail="balaadm@velora.ae",
            parameters={"localSchedule": "17:30"},
        )
        resp_eod = await handle_handoff_request(req_eod)
        self.assertEqual(resp_eod.status, "SUCCESS")
        self.assertIn("Executive End-of-Day Digest", resp_eod.resultSummary)

        # 3. PREPARE_AUTOMATION_SUBSCRIPTION
        req_sub_prep = HandoffRequest(
            task="PrepareSubscription",
            operation="PREPARE_AUTOMATION_SUBSCRIPTION",
            conversationId="conv-sub-01",
            turnId="turn-1",
            rootCorrelationId="corr-test-sub-01",
            userObjectId="user-vikram",
            userEmail="balaadm@velora.ae",
            parameters={
                "kind": "MORNING",
                "localSchedule": "07:00",
                "timezone": "Asia/Dubai",
            },
        )
        resp_sub_prep = await handle_handoff_request(req_sub_prep)
        self.assertEqual(resp_sub_prep.status, "PREVIEW_READY")
        self.assertTrue(resp_sub_prep.approvalRequired)
        self.assertIsNotNone(resp_sub_prep.confirmationToken)

        # 4. CONFIRM_AUTOMATION_SUBSCRIPTION
        sub_id = resp_sub_prep.previewDetails.get("subscriptionId")
        req_sub_conf = HandoffRequest(
            task="ConfirmSubscription",
            operation="CONFIRM_AUTOMATION_SUBSCRIPTION",
            conversationId="conv-sub-01",
            turnId="turn-2",
            rootCorrelationId="corr-test-sub-02",
            userObjectId="user-vikram",
            userEmail="balaadm@velora.ae",
            confirmationToken=resp_sub_prep.confirmationToken,
            parameters={
                "subscriptionId": sub_id,
                "confirmationToken": resp_sub_prep.confirmationToken,
            },
        )
        resp_sub_conf = await handle_handoff_request(req_sub_conf)
        self.assertEqual(resp_sub_conf.status, "SUCCESS")
        self.assertIn("successfully confirmed and ACTIVATED", resp_sub_conf.resultSummary)

        # 5. REVOKE_AUTOMATION_SUBSCRIPTION
        req_sub_rev = HandoffRequest(
            task="RevokeSubscription",
            operation="REVOKE_AUTOMATION_SUBSCRIPTION",
            conversationId="conv-sub-01",
            turnId="turn-3",
            rootCorrelationId="corr-test-sub-03",
            userObjectId="user-vikram",
            userEmail="balaadm@velora.ae",
            parameters={"subscriptionId": sub_id},
        )
        resp_sub_rev = await handle_handoff_request(req_sub_rev)
        self.assertEqual(resp_sub_rev.status, "SUCCESS")
        self.assertIn("has been REVOKED", resp_sub_rev.resultSummary)


if __name__ == "__main__":
    unittest.main()
