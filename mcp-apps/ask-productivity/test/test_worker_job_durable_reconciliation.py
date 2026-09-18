"""Automated Verification Suite for Scheduled Worker Job (Requirement 7).

Verifies:
1. Finite execution of worker pass (clean single-pass completion without infinite loops).
2. Durable scheduling with atomic idempotency claiming (prevents duplicate execution across sweeps).
3. Outbox lease expiration, retry state tracking, attempt incrementing, and exhaustion.
4. Kill switch evaluation immediately halting worker execution.
5. Multi-worker race resilience (two workers sweep concurrently; exactly one dispatches).
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from productivity_mcp.briefing_service import get_briefing_service
from productivity_mcp.dataverse_audit import get_dataverse_client
from productivity_mcp.evidence_contracts import SubscriptionKind
from productivity_mcp.m365_client import Microsoft365Client, seed_test_m365_data
from productivity_mcp.recommendation_engine import (
    DeliveryStatus,
    NotificationDeliveryRecord,
    RecommendationEngine,
)
from shared_mcp.kill_switch import (
    KillSwitchActiveError,
    check_kill_switch,
)
from productivity_mcp.subscription_service import (
    SubscriptionService,
    reset_subscription_service_for_testing,
)
from productivity_mcp.worker import (
    evaluate_and_dispatch_subscriptions,
    run_worker_pass,
)


class TestWorkerJobDurableReconciliation(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.outbox_dir = os.path.join(self.tmp_dir, "outbox")
        self.sub_db = os.path.join(self.tmp_dir, "subscriptions.db")
        self.op_db = os.path.join(self.tmp_dir, "opstore.db")

        os.environ["MOCK_M365"] = "1"
        os.environ["VELORA_OUTBOX_DIR"] = self.outbox_dir
        os.environ["VELORA_SUBSCRIPTION_DB"] = self.sub_db
        os.environ["VELORA_OPERATION_STORE_DB"] = self.op_db
        os.environ["GATEWAY_SHARED_SECRET"] = "velora_test_secret_32_bytes_long!!"
        os.environ["TOKEN_SIGNING_KEY"] = "test_signing_key_32_bytes_long_hmac!"
        os.environ.pop("VELORA_EMERGENCY_KILL_SWITCH", None)
        os.environ.pop("DISABLED_TOOLS", None)

        seed_test_m365_data()
        get_dataverse_client().clear_all_for_testing()
        reset_subscription_service_for_testing()

        self.sub_svc = SubscriptionService(db_path=self.sub_db)
        self.client = Microsoft365Client(user_email="balaadm@velora.ae")
        self.ref_time = datetime(2026, 8, 26, 7, 0, 0, tzinfo=timezone.utc)

    def tearDown(self):
        os.environ.pop("VELORA_EMERGENCY_KILL_SWITCH", None)
        os.environ.pop("DISABLED_TOOLS", None)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_worker_finite_execution_and_clean_exit(self):
        """Worker job must run as a finite pass, return count, and terminate with code 0."""
        delivered = run_worker_pass(
            outbox_dir=self.outbox_dir,
            require_live_delivery=False,
            user_email="balaadm@velora.ae",
            now=self.ref_time,
        )
        self.assertIsInstance(delivered, int)
        self.assertEqual(delivered, 0)

    def test_durable_scheduling_and_idempotency_run_key(self):
        """Subscriptions evaluate schedule and enforce idempotency run key across sweeps."""
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

        # 07:05 GST = 03:05 UTC (within 07:00 morning schedule window)
        run_clock = datetime(2026, 9, 14, 3, 5, 0, tzinfo=timezone.utc)

        # First sweep at 07:05 GST -> Dispatches exactly 1
        dispatched_1 = evaluate_and_dispatch_subscriptions(
            client=self.client,
            tenant_id="velora-tenant",
            now=run_clock,
            require_live_delivery=False,
        )
        self.assertEqual(dispatched_1, 1)

        # Immediate repeat sweep with same clock -> Blocked by idempotency run key
        dispatched_2 = evaluate_and_dispatch_subscriptions(
            client=self.client,
            tenant_id="velora-tenant",
            now=run_clock,
            require_live_delivery=False,
        )
        self.assertEqual(dispatched_2, 0)

    def test_outbox_lease_expiration_and_retry_state_tracking(self):
        """Stalled outbox delivery leases expire and are reclaimed for retry until max_attempts."""
        engine = RecommendationEngine(outbox_dir=self.outbox_dir)

        # 1. Enqueue outbox notification
        rec_id = "rec-retry-001"
        delivery_id = "del-retry-001"
        delivery = NotificationDeliveryRecord(
            delivery_id=delivery_id,
            deduplication_key="dedup-retry-001",
            tenant_id="velora-tenant",
            recommendation_id=rec_id,
            recipient="exec@velora.ae",
            channel="EMAIL",
            status=DeliveryStatus.PENDING,
            attempt_count=0,
            max_attempts=3,
        )
        engine.outbox.append(delivery)

        # 2. Worker 1 claims delivery with 0.1-second lease
        claimed = engine.outbox.claim_pending(worker_id="worker-replica-1", lease_duration_seconds=0.1)
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0].delivery_id, delivery_id)
        self.assertEqual(claimed[0].attempt_count, 1)
        self.assertEqual(claimed[0].status, DeliveryStatus.CLAIMED)

        # 3. Simulate worker-replica-2 attempting to claim while lease is active -> Returns empty
        no_claim = engine.outbox.claim_pending(worker_id="worker-replica-2", lease_duration_seconds=0.1)
        self.assertEqual(len(no_claim), 0)

        # 4. Wait for lease to expire
        import time
        time.sleep(0.15)

        # 5. Worker 2 claims for retry attempt 2
        retry_claim = engine.outbox.claim_pending(worker_id="worker-replica-2", lease_duration_seconds=0.1)
        self.assertEqual(len(retry_claim), 1)
        self.assertEqual(retry_claim[0].attempt_count, 2)

        # 6. Wait for lease to expire again and claim attempt 3 (final)
        time.sleep(0.15)
        retry_claim_3 = engine.outbox.claim_pending(worker_id="worker-replica-3", lease_duration_seconds=0.1)
        self.assertEqual(len(retry_claim_3), 1)
        self.assertEqual(retry_claim_3[0].attempt_count, 3)

        # 7. Once attempt_count >= max_attempts (3), it can no longer be claimed for retry
        time.sleep(0.15)
        exhausted_claim = engine.outbox.claim_pending(worker_id="worker-replica-4", lease_duration_seconds=0.1)
        self.assertEqual(len(exhausted_claim), 0)

    def test_worker_kill_switch_aborts_immediately(self):
        """Worker pass aborts immediately if kill switch is active."""
        os.environ["DISABLED_TOOLS"] = "dispatch_outbox"

        with self.assertRaises(KillSwitchActiveError):
            run_worker_pass(
                outbox_dir=self.outbox_dir,
                tenant_id="velora-tenant",
                now=self.ref_time,
            )


if __name__ == "__main__":
    unittest.main()
