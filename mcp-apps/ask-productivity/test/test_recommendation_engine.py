"""Unit tests for RecommendationEngine, Evaluator, Deduplication, Hysteresis, and DurableOutboxStore.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock
from decimal import Decimal
from datetime import datetime, timezone
from productivity_mcp.recommendation_engine import (
    Comparator,
    DeliveryStatus,
    DurableOutboxStore,
    KPIRecommendationRule,
    KPISnapshot,
    NotificationDeliveryRecord,
    RecommendationEngine,
    RecommendationStatus,
    RuleState,
)


class TestRecommendationEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.outbox = DurableOutboxStore(outbox_dir=self.temp_dir)
        self.engine = RecommendationEngine(outbox_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_default_rules_registered(self):
        rules = list(self.engine.rules.values())
        self.assertGreaterEqual(len(rules), 4)
        rule_codes = {r.rule_code for r in rules}
        self.assertIn("REC-RULE-AR-OVERDUE-90D", rule_codes)
        self.assertIn("REC-RULE-EMIRATISATION-FLOOR", rule_codes)
        self.assertIn("REC-RULE-BUDGET-CONSUMPTION-EXHAUSTION", rule_codes)
        self.assertIn("REC-RULE-AP-PAYABLES-URGENT", rule_codes)

    def test_evaluate_rule_breach_and_recommendation_generation(self):
        # REC-RULE-AR-OVERDUE-90D triggers when AR overdue > 90d exceeds 2,000,000 AED
        snapshot = KPISnapshot(
            snapshot_id="SNAP-AR-001",
            kpi_code="RECEIVABLES",
            organization_scope="1000",
            period="2026-09",
            value=Decimal("2500000.00"),
            unit="currency",
            currency="AED",
            source_updated_time=datetime.now(timezone.utc).isoformat(),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            completeness="COMPLETE",
            evidence_ref="S4HANA-REPORT-REC-2026-09",
            input_hash="hash123456",
        )

        recs = self.engine.evaluate_snapshot(snapshot)
        self.assertEqual(len(recs), 1)
        rec = recs[0]
        self.assertEqual(rec.rule_code, "REC-RULE-AR-OVERDUE-90D")
        self.assertEqual(rec.status, RecommendationStatus.ACTIVE_BREACH)
        self.assertIn("2000000.00", rec.explanation)
        self.assertIn("2500000.00", rec.explanation)

        # Check outbox queued delivery record
        pending = self.engine.outbox.get_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].recommendation_id, rec.recommendation_id)
        self.assertEqual(pending[0].channel, "EMAIL")

    def test_deduplication_on_continuous_breach(self):
        # 1st breach generates recommendation
        snap1 = KPISnapshot(
            snapshot_id="SNAP-BUDGET-001",
            kpi_code="BUDGET_CONSUMPTION",
            organization_scope="1000",
            period="2026-09",
            value=Decimal("92.0"),
            unit="percent",
            currency="",
            source_updated_time=datetime.now(timezone.utc).isoformat(),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            completeness="COMPLETE",
            evidence_ref="S4HANA-BUDGET-2026-09",
            input_hash="hash-budget-1",
        )
        recs1 = self.engine.evaluate_snapshot(snap1)
        self.assertEqual(len(recs1), 1)
        first_rec_id = recs1[0].recommendation_id

        # 2nd breach with continuing breach state updates timestamp/value but does not enqueue a second delivery
        snap2 = KPISnapshot(
            snapshot_id="SNAP-BUDGET-002",
            kpi_code="BUDGET_CONSUMPTION",
            organization_scope="1000",
            period="2026-09",
            value=Decimal("94.5"),
            unit="percent",
            currency="",
            source_updated_time=datetime.now(timezone.utc).isoformat(),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            completeness="COMPLETE",
            evidence_ref="S4HANA-BUDGET-2026-09",
            input_hash="hash-budget-2",
        )
        recs2 = self.engine.evaluate_snapshot(snap2)
        self.assertEqual(len(recs2), 1)
        self.assertEqual(recs2[0].recommendation_id, first_rec_id)
        self.assertEqual(recs2[0].observed_value, Decimal("94.5"))

        # Only one outbox delivery was enqueued for the episode
        pending = self.engine.outbox.get_pending()
        self.assertEqual(len(pending), 1)

    def test_hysteresis_clear_and_rearm(self):
        # Rule: REC-RULE-EMIRATISATION-FLOOR triggers when metric < 40.0, clear threshold is 42.0
        # 1. Breach below 40.0
        snap_breach = KPISnapshot(
            snapshot_id="SNAP-HR-001",
            kpi_code="EMIRATISATION",
            organization_scope="1000",
            period="2026-09",
            value=Decimal("38.0"),
            unit="percent",
            currency="",
            source_updated_time=datetime.now(timezone.utc).isoformat(),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            completeness="COMPLETE",
            evidence_ref="SF-EMIRATISATION-2026-09",
            input_hash="hash-hr-1",
        )
        recs_breach = self.engine.evaluate_snapshot(snap_breach)
        self.assertEqual(len(recs_breach), 1)
        self.assertEqual(recs_breach[0].status, RecommendationStatus.ACTIVE_BREACH)

        # 2. Metric rises to 41.0 (above 40.0 threshold, but NOT above 42.0 clear threshold)
        # Hysteresis keeps status in ACTIVE_BREACH, no recovery
        snap_in_hysteresis = KPISnapshot(
            snapshot_id="SNAP-HR-002",
            kpi_code="EMIRATISATION",
            organization_scope="1000",
            period="2026-09",
            value=Decimal("41.0"),
            unit="percent",
            currency="",
            source_updated_time=datetime.now(timezone.utc).isoformat(),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            completeness="COMPLETE",
            evidence_ref="SF-EMIRATISATION-2026-09",
            input_hash="hash-hr-2",
        )
        recs_hysteresis = self.engine.evaluate_snapshot(snap_in_hysteresis)
        self.assertEqual(len(recs_hysteresis), 0)
        dedup_key = self.engine.compute_deduplication_key(
            "REC-RULE-EMIRATISATION-FLOOR", "1.0.0", "EMIRATISATION", "1000", "2026-09"
        )
        self.assertEqual(self.engine.active_recommendations[dedup_key].status, RecommendationStatus.ACTIVE_BREACH)

        # 3. Metric rises to 43.0 (above clear threshold 42.0) -> recovers recommendation
        snap_cleared = KPISnapshot(
            snapshot_id="SNAP-HR-003",
            kpi_code="EMIRATISATION",
            organization_scope="1000",
            period="2026-09",
            value=Decimal("43.0"),
            unit="percent",
            currency="",
            source_updated_time=datetime.now(timezone.utc).isoformat(),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            completeness="COMPLETE",
            evidence_ref="SF-EMIRATISATION-2026-09",
            input_hash="hash-hr-3",
        )
        recs_cleared = self.engine.evaluate_snapshot(snap_cleared)
        self.assertEqual(len(recs_cleared), 0)
        self.assertEqual(self.engine.active_recommendations[dedup_key].status, RecommendationStatus.RECOVERED)

        # 4. New breach drops back to 37.0 -> re-fires new active breach
        snap_rearm = KPISnapshot(
            snapshot_id="SNAP-HR-004",
            kpi_code="EMIRATISATION",
            organization_scope="1000",
            period="2026-09",
            value=Decimal("37.0"),
            unit="percent",
            currency="",
            source_updated_time=datetime.now(timezone.utc).isoformat(),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            completeness="COMPLETE",
            evidence_ref="SF-EMIRATISATION-2026-09",
            input_hash="hash-hr-4",
        )
        recs_rearm = self.engine.evaluate_snapshot(snap_rearm)
        self.assertEqual(len(recs_rearm), 1, "Should re-fire after status recovered")
        self.assertEqual(recs_rearm[0].status, RecommendationStatus.ACTIVE_BREACH)

    def test_durable_outbox_restart_recovery(self):
        # Enqueue item
        rec = NotificationDeliveryRecord(
            delivery_id="DELIV-TEST-001",
            recommendation_id="REC-TEST-001",
            recipient="cfo@velora.ae",
            channel="EMAIL",
            status=DeliveryStatus.PENDING,
        )
        self.outbox.append(rec)

        # Verify initial pending
        pending_initial = self.outbox.get_pending()
        self.assertEqual(len(pending_initial), 1)

        # Restart simulation: instantiate new store pointing to same directory
        restarted_outbox = DurableOutboxStore(outbox_dir=self.temp_dir)
        recovered_pending = restarted_outbox.get_pending()
        self.assertEqual(len(recovered_pending), 1)
        self.assertEqual(recovered_pending[0].delivery_id, "DELIV-TEST-001")
        self.assertEqual(recovered_pending[0].recipient, "cfo@velora.ae")

        # Mark sent / delivered
        recovered_pending[0].status = DeliveryStatus.DELIVERED
        recovered_pending[0].provider_receipt = {"mock": True}
        restarted_outbox.update(recovered_pending[0])
        self.assertEqual(len(restarted_outbox.get_pending()), 0)

        # Re-load third time to ensure delivered state was persisted to file
        third_outbox = DurableOutboxStore(outbox_dir=self.temp_dir)
        self.assertEqual(len(third_outbox.get_pending()), 0)
    def test_f08_full_engine_restart_recovery_and_dispatch(self):
        """F08: Engine restart recovers both deliveries AND recommendations; dispatch succeeds without 'not found' failure."""
        snap = KPISnapshot(
            snapshot_id="SNAP-AR-001",
            kpi_code="RECEIVABLES",
            organization_scope="1000",
            period="2026-09",
            value=Decimal("15000000.00"),
            unit="currency",
            currency="AED",
            source_updated_time=datetime.now(timezone.utc).isoformat(),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            completeness="COMPLETE",
            evidence_ref="S4HANA-AR-2026-09",
            input_hash="hash-ar-1",
        )
        recs = self.engine.evaluate_snapshot(snap)
        self.assertEqual(len(recs), 1)
        rec_id = recs[0].recommendation_id

        # Pending outbox item created
        self.assertEqual(len(self.engine.outbox.get_pending()), 1)

        # RESTART SIMULATION: Create new RecommendationEngine with same directory
        restarted_engine = RecommendationEngine(outbox_dir=self.temp_dir)
        self.assertEqual(len(restarted_engine.outbox.get_pending()), 1)
        # Recommendation record must be recovered from disk!
        self.assertIn(rec_id, restarted_engine.recommendations_by_id)

        # Dispatch should find the recommendation and succeed (NOT fail with 'Recommendation record not found')
        mock_m365 = MagicMock()
        mock_m365.execute_send_email.return_value = {
            "status": "SENT",
            "message_id": "MSG-LIVE-123",
            "providerReceipt": {"simulated": False, "live_id": "MSG-LIVE-123"},
        }
        delivered = restarted_engine.dispatch_outbox(mock_m365, require_live_delivery=True)
        self.assertEqual(delivered, 1)
        item = restarted_engine.outbox.get_all()[0]
        self.assertEqual(item.status, DeliveryStatus.DELIVERED)

    def test_f08_rule_governance_effective_dates_and_unit_currency(self):
        """F08: Evaluator enforces effective_from/effective_to, unit, and currency compatibility."""
        # 1. Expired rule
        expired_rule = KPIRecommendationRule(
            rule_code="REC-EXPIRED",
            rule_version="1.0.0",
            name="Expired Rule",
            kpi_code="OVERDUE_AR",
            organization_scope="1000",
            threshold=Decimal("1000000.00"),
            effective_from="2020-01-01T00:00:00Z",
            effective_to="2025-01-01T00:00:00Z",
        )
        engine = RecommendationEngine(rules=[expired_rule], outbox_dir=self.temp_dir)
        snap = KPISnapshot(
            snapshot_id="S1",
            kpi_code="OVERDUE_AR",
            organization_scope="1000",
            period="2026-09",
            value=Decimal("5000000.00"),
            unit="currency",
            currency="AED",
            source_updated_time="",
            retrieved_at="",
            completeness="COMPLETE",
            evidence_ref="E1",
            input_hash="H1",
        )
        recs = engine.evaluate_snapshot(snap)
        self.assertEqual(len(recs), 0, "Expired rule must not fire")

        # 2. Currency mismatch: AED rule on USD snapshot
        aed_rule = KPIRecommendationRule(
            rule_code="REC-AED",
            rule_version="1.0.0",
            name="AED Rule",
            kpi_code="OVERDUE_AR",
            organization_scope="1000",
            threshold=Decimal("1000000.00"),
            unit="currency",
            currency="AED",
        )
        engine_curr = RecommendationEngine(rules=[aed_rule], outbox_dir=self.temp_dir)
        snap_usd = KPISnapshot(
            snapshot_id="S2",
            kpi_code="OVERDUE_AR",
            organization_scope="1000",
            period="2026-09",
            value=Decimal("5000000.00"),
            unit="currency",
            currency="USD",
            source_updated_time="",
            retrieved_at="",
            completeness="COMPLETE",
            evidence_ref="E2",
            input_hash="H2",
        )
        recs_usd = engine_curr.evaluate_snapshot(snap_usd)
        self.assertEqual(len(recs_usd), 0, "AED rule must not fire for USD snapshot")

    def test_f08_delivery_acceptance_gate_rejects_simulated(self):
        """F08: Delivery gate rejects marking simulated sends as DELIVERED when live delivery is required."""
        snap = KPISnapshot(
            snapshot_id="S3",
            kpi_code="RECEIVABLES",
            organization_scope="1000",
            period="2026-09",
            value=Decimal("15000000.00"),
            unit="currency",
            currency="AED",
            source_updated_time="",
            retrieved_at="",
            completeness="COMPLETE",
            evidence_ref="E3",
            input_hash="H3",
        )
        self.engine.evaluate_snapshot(snap)

        mock_sim_m365 = MagicMock()
        mock_sim_m365.execute_send_email.return_value = {
            "status": "SENT",
            "message_id": "SIM-001",
            "providerReceipt": {"simulated": True, "live_id": "SIM-001"},
            "simulated": True,
        }
        delivered = self.engine.dispatch_outbox(mock_sim_m365, require_live_delivery=True)
        self.assertEqual(delivered, 0)
        item = self.engine.outbox.get_all()[0]
        self.assertEqual(item.status, DeliveryStatus.FAILED)
        self.assertIn("simulated receipt", item.last_error)


if __name__ == "__main__":
    unittest.main()
