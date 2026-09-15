"""Unit and concurrency tests for Section 7: Notification claims and reconciliation.

Tests:
1. Two workers compete for one delivery (atomic claiming, exactly one winner).
2. Worker crashes before submission (lease expiration, recovered by next worker).
3. Provider accepts, then worker crashes before saving response (state was SUBMITTING, moved to RECONCILING, never automatically re-sent).
4. Lease expires during slow provider call (stale worker's state update raises StaleWorkerError).
5. Provider returns an error (bounded retries up to max_attempts, then FAILED).
6. Restart preserves cooldown and episode state.
7. Delivery guarantee honestly documented.
"""
import os
import shutil
import tempfile
import time
import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from productivity_mcp.recommendation_engine import (
    DeliveryStatus,
    DurableOutboxStore,
    KPISnapshot,
    NotificationDeliveryRecord,
    RecommendationEngine,
    RecommendationRecord,
    RecommendationStatus,
    StaleWorkerError,
)


class TestNotificationClaimsAndReconciliation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.outbox = DurableOutboxStore(outbox_dir=self.temp_dir)
        self.engine = RecommendationEngine(outbox_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_two_workers_compete_for_one_delivery(self):
        """Two workers compete for one delivery: exactly one claims it, the other gets 0."""
        item = NotificationDeliveryRecord(
            delivery_id="DLV-COMPETE-001",
            recommendation_id="REC-001",
            recipient="exec@velora.ae",
            channel="EMAIL",
            status=DeliveryStatus.PENDING,
            deduplication_key="dedup-compete-1",
        )
        self.outbox.append(item)

        # Worker A claims
        claimed_a = self.outbox.claim_pending(worker_id="worker-A", lease_duration_seconds=30.0)
        self.assertEqual(len(claimed_a), 1)
        self.assertEqual(claimed_a[0].delivery_id, "DLV-COMPETE-001")
        self.assertEqual(claimed_a[0].lease_owner, "worker-A")

        # Worker B simultaneously tries to claim
        claimed_b = self.outbox.claim_pending(worker_id="worker-B", lease_duration_seconds=30.0)
        self.assertEqual(len(claimed_b), 0)

    def test_worker_crashes_before_submission(self):
        """Worker crashes before submission: lease expires and second worker claims and executes."""
        item = NotificationDeliveryRecord(
            delivery_id="DLV-CRASH-001",
            recommendation_id="REC-002",
            recipient="exec@velora.ae",
            channel="EMAIL",
            status=DeliveryStatus.PENDING,
            deduplication_key="dedup-crash-1",
        )
        self.outbox.append(item)

        # Worker A claims with very short lease (0.1s) and crashes (no submission)
        claimed_a = self.outbox.claim_pending(worker_id="worker-A", lease_duration_seconds=0.1)
        self.assertEqual(len(claimed_a), 1)

        time.sleep(0.2)  # Lease expires

        # Worker B arrives, reclaims expired lease
        claimed_b = self.outbox.claim_pending(worker_id="worker-B", lease_duration_seconds=30.0)
        self.assertEqual(len(claimed_b), 1)
        self.assertEqual(claimed_b[0].delivery_id, "DLV-CRASH-001")
        self.assertEqual(claimed_b[0].lease_owner, "worker-B")
        self.assertEqual(claimed_b[0].attempt_count, 2)

    def test_provider_accepts_then_worker_crashes_moved_to_reconciling(self):
        """Provider accepts, but worker crashes before saving response: state is SUBMITTING, moved to RECONCILING, never auto-resends."""
        item = NotificationDeliveryRecord(
            delivery_id="DLV-AMBIGUOUS-001",
            recommendation_id="REC-003",
            recipient="exec@velora.ae",
            channel="EMAIL",
            status=DeliveryStatus.PENDING,
            deduplication_key="dedup-ambig-1",
        )
        self.outbox.append(item)

        # Worker A claims and marks SUBMITTING with short lease
        claimed = self.outbox.claim_pending(worker_id="worker-A", lease_duration_seconds=2.0)
        rec = claimed[0]
        v2 = self.outbox.mark_submitting(
            delivery_id=rec.delivery_id,
            worker_id="worker-A",
            version=rec.version,
            lease_duration_seconds=0.1,
        )

        # Worker A crashes here! Provider received the email, but Worker A died.
        time.sleep(0.2)  # Lease expires

        # Reconciler sweeps or Worker B attempts to claim:
        claimed_b = self.outbox.claim_pending(worker_id="worker-B", lease_duration_seconds=30.0)
        # Worker B MUST NOT re-claim it!
        self.assertEqual(len(claimed_b), 0)

        # Record in store is now RECONCILING
        updated = self.outbox.get_delivery(rec.delivery_id)
        self.assertEqual(updated.status, DeliveryStatus.RECONCILING)
        self.assertIn("SUBMITTING", updated.last_error)

    def test_lease_expires_during_slow_provider_call_raises_stale_worker_error(self):
        """Lease expires during a slow provider call: stale worker's attempt to update raises StaleWorkerError."""
        item = NotificationDeliveryRecord(
            delivery_id="DLV-SLOW-001",
            recommendation_id="REC-004",
            recipient="exec@velora.ae",
            channel="EMAIL",
            status=DeliveryStatus.PENDING,
            deduplication_key="dedup-slow-1",
        )
        self.outbox.append(item)

        claimed = self.outbox.claim_pending(worker_id="worker-Slow", lease_duration_seconds=0.1)
        rec = claimed[0]
        v2 = self.outbox.mark_submitting(
            delivery_id=rec.delivery_id,
            worker_id="worker-Slow",
            version=rec.version,
            lease_duration_seconds=0.1,
        )

        # Slow provider call takes 0.25s while lease expired at 0.1s
        time.sleep(0.25)

        with self.assertRaises(StaleWorkerError):
            self.outbox.mark_delivered(
                delivery_id=rec.delivery_id,
                worker_id="worker-Slow",
                version=v2,
                provider_reference="MSG-LATE",
            )

    def test_bounded_retries_on_pre_submission_failure(self):
        """Bounded retries for verified failures: retried until max_attempts, then marked FAILED."""
        item = NotificationDeliveryRecord(
            delivery_id="DLV-FAIL-001",
            recommendation_id="REC-005",
            recipient="exec@velora.ae",
            channel="EMAIL",
            status=DeliveryStatus.PENDING,
            deduplication_key="dedup-fail-1",
            max_attempts=2,
        )
        self.outbox.append(item)

        # Attempt 1: fails
        claimed = self.outbox.claim_pending(worker_id="worker-1", lease_duration_seconds=30.0)[0]
        st1, v1 = self.outbox.mark_failed_or_retry(
            claimed.delivery_id, "worker-1", claimed.version, "Transient network drop"
        )
        self.assertEqual(st1, DeliveryStatus.PENDING)

        # Attempt 2: fails again (reaches max_attempts=2)
        claimed2 = self.outbox.claim_pending(worker_id="worker-2", lease_duration_seconds=30.0)[0]
        self.assertEqual(claimed2.attempt_count, 2)
        st2, v2 = self.outbox.mark_failed_or_retry(
            claimed2.delivery_id, "worker-2", claimed2.version, "Persistent network failure"
        )
        self.assertEqual(st2, DeliveryStatus.FAILED)

        # No further claims available
        self.assertEqual(len(self.outbox.claim_pending(worker_id="worker-3")), 0)

    def test_restart_preserves_cooldown_and_episode_state(self):
        """Restart preserves cooldown episodes and recommendation deduplication across instance reboot."""
        snap = KPISnapshot(
            snapshot_id="SNAP-EP-001",
            kpi_code="BUDGET_CONSUMPTION",
            organization_scope="1000",
            period="2026-09",
            value=Decimal("95.0"),
            unit="percent",
            currency="",
            source_updated_time="",
            retrieved_at="",
            completeness="COMPLETE",
            evidence_ref="EVID-1",
            input_hash="hash-1",
        )
        self.engine.evaluate_snapshot(snap)
        episodes_orig = dict(self.engine.breach_episodes)
        self.assertTrue(len(episodes_orig) > 0)

        # Simulate container restart with fresh Engine pointing to same directory
        rebooted_engine = RecommendationEngine(outbox_dir=self.temp_dir)
        self.assertEqual(rebooted_engine.breach_episodes, episodes_orig)
        self.assertEqual(len(rebooted_engine.outbox.get_all()), 1)

    def test_delivery_guarantee_honesty_documented(self):
        """Verify delivery guarantee contract is explicitly documented on DurableOutboxStore."""
        doc = DurableOutboxStore.__doc__ or ""
        self.assertIn("At-least-once submission", doc)
        self.assertIn("RECONCILING", doc)
        self.assertIn("exactly-once", doc)


if __name__ == "__main__":
    unittest.main()
