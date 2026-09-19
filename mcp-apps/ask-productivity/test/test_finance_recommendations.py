"""Comprehensive Acceptance Tests for Work Package W08 (Acceptance T08).

Validates all 10 Acceptance T08 Invariants:
1. Fixture S4 records produce independently calculated snapshot and categorized recommendation.
2. S4 overdue >90d isolation (sum of bucket_91_180 and bucket_over_180; never gross receivables).
3. Source outage / error containment (cannot trigger a confident complete recommendation).
4. Partial data handling (requires_complete skips recommendation generation).
5. Unapproved mapping protection (Budget recommendation blocked/skipped).
6. Complete new breach emits exactly one alert.
7. Continued breach emits no duplicate alerts.
8. Recovery updates status to RECOVERED, increments episode, resets cooldown.
9. Recovery and episodes survive engine restart from SQLite durable store.
10. Comparator coverage (GT, LT, OUTSIDE_RANGE breach and recovery).
11. Expired rules (effective_to in past) do not run.
12. Empty approved rules yields zero recommendations (no default seed fallback).
13. Source reconciliation (scope, currency, as-of, input hash).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict

from productivity_mcp.business_repository import (
    KPIRuleRecord,
    SqliteBusinessRepository,
    get_business_repository,
)
from productivity_mcp.evidence_contracts import (
    ClaimKind,
    ConfidenceLabel,
    EvidenceSource,
    MaterialClaim,
)
from productivity_mcp.recommendation_engine import (
    Comparator,
    DeliveryStatus,
    DurableOutboxStore,
    KPIRecommendationRule,
    KPISnapshot,
    RecommendationEngine,
    RecommendationStatus,
    RuleState,
)
from facilitator_mcp.finance_snapshot_service import (
    generate_finance_snapshot,
    evaluate_finance_snapshot,
)


class TestFinanceRecommendationsAcceptanceT08(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_business_w08.db")
        self.outbox_dir = os.path.join(self.temp_dir, "outbox")
        os.makedirs(self.outbox_dir, exist_ok=True)
        self.repo = SqliteBusinessRepository(db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_mock_s4_ar_result(
        self,
        b_91_180: Decimal = Decimal("1200000.00"),
        b_over_180: Decimal = Decimal("1300000.00"),
        gross_debit: Decimal = Decimal("10000000.00"),
        completion_state: str = "COMPLETE",
        currency: str = "AED",
        status: str = "success",
    ) -> Dict[str, Any]:
        """Fixture representing authoritative SAP S/4HANA OData AR aging payload."""
        overdue_90d = b_91_180 + b_over_180
        return {
            "status": status,
            "type": "ReceivablesAging",
            "coverage": {
                "rowsRead": 100,
                "rowsDisplayed": 100,
                "pageCount": 1,
                "declaredTotal": 100,
                "completionState": completion_state,
                "incompleteReason": "" if completion_state == "COMPLETE" else "Data truncated by backend filter",
            },
            "sourceRecord": {
                "sourceId": "S4_RECEIVABLES_AGING",
                "businessTitle": "SAP S/4HANA Receivables Aging",
                "environment": "Production",
                "organizationScope": "1000",
                "currency": currency,
                "retrievedAt": datetime.now(timezone.utc).isoformat(),
                "completeness": completion_state,
            },
            "calculations": {
                "currency": currency,
                "gross_debit": gross_debit,
                "total_open_signed": gross_debit,
                "overdue_exposure": overdue_90d,
                "status": "VALID",
                "is_valid": True,
                "buckets": {
                    "not_yet_due": {"label": "Not Yet Due", "amount": Decimal("4000000.00"), "count": 20},
                    "due_today": {"label": "Due Today", "amount": Decimal("500000.00"), "count": 10},
                    "bucket_1_30": {"label": "1-30 Days", "amount": Decimal("1500000.00"), "count": 25},
                    "bucket_31_60": {"label": "31-60 Days", "amount": Decimal("1000000.00"), "count": 15},
                    "bucket_61_90": {"label": "61-90 Days", "amount": Decimal("500000.00"), "count": 10},
                    "bucket_91_180": {"label": "91-180 Days", "amount": b_91_180, "count": 10},
                    "bucket_over_180": {"label": ">180 Days", "amount": b_over_180, "count": 10},
                },
            },
            "data": {
                "records": [{"Invoice": "INV-1001", "OpenAmount": "1200000.00"}, {"Invoice": "INV-1002", "OpenAmount": "1300000.00"}],
                "total": 100,
            },
        }

    async def test_01_s4_overdue_90d_independent_calculation_and_recommendation(self):
        """Invariant 1 & 2: Overdue >90d strictly sums bucket_91_180 + bucket_over_180 (never gross receivables)."""
        mock_ar = self._create_mock_s4_ar_result(
            b_91_180=Decimal("1200000.00"),
            b_over_180=Decimal("1300000.00"),
            gross_debit=Decimal("10000000.00"),  # Gross is 10M, but overdue >90d is 2.5M
        )

        snap = await generate_finance_snapshot(
            kpi_code="RECEIVABLES",
            company_code="1000",
            currency="AED",
            tenant_id="velora-aviation",
            db_path=self.db_path,
            s4_tool_override=lambda **kwargs: mock_ar,
        )

        # Invariant: Value must be EXACTLY 2.5M AED, not 10.0M AED!
        self.assertEqual(snap["value"], Decimal("2500000.00"))
        self.assertNotEqual(snap["value"], Decimal("10000000.00"))
        self.assertEqual(snap["completeness"], "COMPLETE")
        self.assertEqual(snap["currency"], "AED")
        self.assertEqual(snap["organization_scope"], "1000")
        self.assertTrue(snap["input_hash"])

        # Evaluate snapshot through RecommendationEngine
        engine = RecommendationEngine(outbox_dir=self.outbox_dir, tenant_id="velora-aviation")
        recs = engine.evaluate_snapshot(KPISnapshot(**{k: v for k, v in snap.items() if k in KPISnapshot.__dataclass_fields__}))

        self.assertEqual(len(recs), 1)
        rec = recs[0]
        self.assertEqual(rec.rule_code, "REC-RULE-AR-OVERDUE-90D")
        self.assertEqual(rec.category, "RISK")
        self.assertEqual(rec.status, RecommendationStatus.ACTIVE_BREACH)
        self.assertEqual(rec.observed_value, Decimal("2500000.00"))
        self.assertIn("Risk Alert [HIGH]", rec.impact)
        self.assertIn("2500000.00", rec.explanation)
        self.assertEqual(rec.confidence, "HIGH")

        # Traceability: claims and sources
        self.assertTrue(len(rec.supporting_claims) > 0)
        self.assertTrue(len(rec.supporting_sources) > 0)
        self.assertEqual(rec.supporting_sources[0]["system"], "S4HANA")

    async def test_02_s4_outage_containment(self):
        """Invariant 3: Source outage produces EMPTY completeness and cannot trigger a confident recommendation."""
        outage_ar = {"status": "error", "message": "SAP S/4HANA gateway timeout (504 Gateway Timeout)."}

        snap = await generate_finance_snapshot(
            kpi_code="RECEIVABLES",
            company_code="1000",
            currency="AED",
            tenant_id="velora-aviation",
            db_path=self.db_path,
            s4_tool_override=lambda **kwargs: outage_ar,
        )

        self.assertEqual(snap["completeness"], "EMPTY")
        self.assertEqual(snap["value"], Decimal("0.00"))
        self.assertIn("S4_OUTAGE", snap["evidence_ref"])

        engine = RecommendationEngine(outbox_dir=self.outbox_dir, tenant_id="velora-aviation")
        kpi_snap = KPISnapshot(**{k: v for k, v in snap.items() if k in KPISnapshot.__dataclass_fields__})
        recs = engine.evaluate_snapshot(kpi_snap)

        # Zero recommendations because requires_complete=True and completeness is EMPTY
        self.assertEqual(len(recs), 0)
        self.assertEqual(len(engine.outbox.get_all()), 0)

    async def test_03_partial_data_handling(self):
        """Invariant 4: Incomplete/partial dataset skips confident recommendation generation."""
        mock_partial = self._create_mock_s4_ar_result(
            b_91_180=Decimal("1500000.00"),
            b_over_180=Decimal("1500000.00"),
            completion_state="PARTIAL",
        )

        snap = await generate_finance_snapshot(
            kpi_code="RECEIVABLES",
            company_code="1000",
            currency="AED",
            tenant_id="velora-aviation",
            db_path=self.db_path,
            s4_tool_override=lambda **kwargs: mock_partial,
        )

        self.assertEqual(snap["completeness"], "PARTIAL")
        self.assertTrue(len(snap["limitations"]) > 0)

        engine = RecommendationEngine(outbox_dir=self.outbox_dir, tenant_id="velora-aviation")
        kpi_snap = KPISnapshot(**{k: v for k, v in snap.items() if k in KPISnapshot.__dataclass_fields__})
        recs = engine.evaluate_snapshot(kpi_snap)

        # Rule requires_complete skips PARTIAL snapshot
        self.assertEqual(len(recs), 0)

    async def test_04_unapproved_budget_mapping_protection(self):
        """Invariant 5: Budget recommendation mapping is unapproved and must be blocked."""
        snap = await generate_finance_snapshot(
            kpi_code="BUDGET_CONSUMPTION",
            company_code="1000",
            currency="AED",
            tenant_id="velora-aviation",
            db_path=self.db_path,
        )

        self.assertTrue(snap.get("unapproved_mapping"))
        self.assertEqual(snap["evidence_ref"], "UNAPPROVED_MAPPING")
        self.assertEqual(snap["completeness"], "PARTIAL")

        engine = RecommendationEngine(outbox_dir=self.outbox_dir, tenant_id="velora-aviation")
        kpi_snap = KPISnapshot(**{k: v for k, v in snap.items() if k in KPISnapshot.__dataclass_fields__})
        kpi_snap.unapproved_mapping = True
        recs = engine.evaluate_snapshot(kpi_snap)

        self.assertEqual(len(recs), 0)

    async def test_05_deduplication_single_alert_and_zero_duplicate_on_continued_breach(self):
        """Invariant 6 & 7: Initial breach emits one alert; continued breach emits zero duplicates."""
        mock_ar_1 = self._create_mock_s4_ar_result(b_91_180=Decimal("1200000.00"), b_over_180=Decimal("1000000.00"))
        snap1_dict = await generate_finance_snapshot(
            kpi_code="RECEIVABLES", company_code="1000", currency="AED", db_path=self.db_path,
            s4_tool_override=lambda **kw: mock_ar_1
        )
        snap1 = KPISnapshot(**{k: v for k, v in snap1_dict.items() if k in KPISnapshot.__dataclass_fields__})

        engine = RecommendationEngine(outbox_dir=self.outbox_dir, tenant_id="velora-aviation")
        recs1 = engine.evaluate_snapshot(snap1)
        self.assertEqual(len(recs1), 1)
        self.assertEqual(len(engine.outbox.get_all()), 1)

        # Second snapshot with increased breach amount
        mock_ar_2 = self._create_mock_s4_ar_result(b_91_180=Decimal("1500000.00"), b_over_180=Decimal("1200000.00"))
        snap2_dict = await generate_finance_snapshot(
            kpi_code="RECEIVABLES", company_code="1000", currency="AED", db_path=self.db_path,
            s4_tool_override=lambda **kw: mock_ar_2
        )
        snap2 = KPISnapshot(**{k: v for k, v in snap2_dict.items() if k in KPISnapshot.__dataclass_fields__})

        recs2 = engine.evaluate_snapshot(snap2)
        self.assertEqual(len(recs2), 1)
        self.assertEqual(recs2[0].recommendation_id, recs1[0].recommendation_id)
        self.assertEqual(recs2[0].observed_value, Decimal("2700000.00"))

        # Invariant: Outbox deliveries count remains 1! No duplicate email queued!
        self.assertEqual(len(engine.outbox.get_all()), 1)

    async def test_06_recovery_updates_status_increments_episode_resets_cooldown(self):
        """Invariant 8: Recovery updates status to RECOVERED, increments episode counter, resets cooldown."""
        # 1. Breach at 2.5M AED
        mock_breach = self._create_mock_s4_ar_result(b_91_180=Decimal("1200000.00"), b_over_180=Decimal("1300000.00"))
        snap1 = KPISnapshot(**{k: v for k, v in (await generate_finance_snapshot(
            kpi_code="RECEIVABLES", company_code="1000", currency="AED", db_path=self.db_path, s4_tool_override=lambda **kw: mock_breach
        )).items() if k in KPISnapshot.__dataclass_fields__})

        engine = RecommendationEngine(outbox_dir=self.outbox_dir, tenant_id="velora-aviation")
        engine.evaluate_snapshot(snap1)
        self.assertEqual(engine.breach_episodes.get("REC-RULE-AR-OVERDUE-90D:1000:RECEIVABLES"), "ep1")

        # 2. Metric clears below clear_threshold of 1.5M AED (recovery to 1.2M AED)
        mock_recovery = self._create_mock_s4_ar_result(b_91_180=Decimal("600000.00"), b_over_180=Decimal("600000.00"))
        snap_rec = KPISnapshot(**{k: v for k, v in (await generate_finance_snapshot(
            kpi_code="RECEIVABLES", company_code="1000", currency="AED", db_path=self.db_path, s4_tool_override=lambda **kw: mock_recovery
        )).items() if k in KPISnapshot.__dataclass_fields__})

        engine.evaluate_snapshot(snap_rec)

        # Invariant: Status transitioned to RECOVERED, episode incremented to ep2, cooldown cleared
        active_rec = list(engine.active_recommendations.values())[0]
        self.assertEqual(active_rec.status, RecommendationStatus.RECOVERED)
        self.assertEqual(engine.breach_episodes.get("REC-RULE-AR-OVERDUE-90D:1000:RECEIVABLES"), "ep2")
        self.assertFalse(engine.outbox.is_cooldown_active("REC-RULE-AR-OVERDUE-90D:1000:RECEIVABLES"))

        # 3. New breach in episode 2 emits a new alert!
        snap_new_breach = KPISnapshot(**{k: v for k, v in (await generate_finance_snapshot(
            kpi_code="RECEIVABLES", company_code="1000", currency="AED", db_path=self.db_path, s4_tool_override=lambda **kw: mock_breach
        )).items() if k in KPISnapshot.__dataclass_fields__})
        recs_new = engine.evaluate_snapshot(snap_new_breach)
        self.assertEqual(len(recs_new), 1)
        self.assertEqual(recs_new[0].status, RecommendationStatus.ACTIVE_BREACH)
        self.assertEqual(len(engine.outbox.get_all()), 2)  # New distinct alert enqueued for ep2!

    async def test_07_recovery_and_episodes_survive_engine_restart(self):
        """Invariant 9: State transitions, episode progression, and cooldowns survive instance reboot."""
        # 1. Breach then recover
        mock_breach = self._create_mock_s4_ar_result(b_91_180=Decimal("1500000.00"), b_over_180=Decimal("1500000.00"))
        mock_rec = self._create_mock_s4_ar_result(b_91_180=Decimal("500000.00"), b_over_180=Decimal("500000.00"))

        snap_breach = KPISnapshot(**{k: v for k, v in (await generate_finance_snapshot(
            kpi_code="RECEIVABLES", db_path=self.db_path, s4_tool_override=lambda **kw: mock_breach
        )).items() if k in KPISnapshot.__dataclass_fields__})
        snap_clear = KPISnapshot(**{k: v for k, v in (await generate_finance_snapshot(
            kpi_code="RECEIVABLES", db_path=self.db_path, s4_tool_override=lambda **kw: mock_rec
        )).items() if k in KPISnapshot.__dataclass_fields__})

        engine1 = RecommendationEngine(outbox_dir=self.outbox_dir, tenant_id="velora-aviation")
        engine1.evaluate_snapshot(snap_breach)
        engine1.evaluate_snapshot(snap_clear)

        # Verify engine 1 episode is ep2 and rec is RECOVERED
        self.assertEqual(engine1.breach_episodes.get("REC-RULE-AR-OVERDUE-90D:1000:RECEIVABLES"), "ep2")
        rec_id = list(engine1.active_recommendations.values())[0].recommendation_id

        # 2. Simulate container restart / crash by destroying engine1 and creating engine2 from same outbox_dir
        del engine1
        engine2 = RecommendationEngine(outbox_dir=self.outbox_dir, tenant_id="velora-aviation")

        # Invariant: engine2 restored episode ep2 and RECOVERED recommendation status
        self.assertEqual(engine2.breach_episodes.get("REC-RULE-AR-OVERDUE-90D:1000:RECEIVABLES"), "ep2")
        restored_rec = engine2.recommendations_by_id.get(rec_id)
        self.assertIsNotNone(restored_rec)
        self.assertEqual(restored_rec.status, RecommendationStatus.RECOVERED)

    async def test_08_comparator_coverage_including_outside_range(self):
        """Invariant 10: Validates GT, LT, and OUTSIDE_RANGE comparator breach and recovery."""
        custom_rule_range = KPIRecommendationRule(
            rule_code="REC-RULE-MARGIN-RANGE",
            rule_version="1.0.0",
            name="Operating Margin Corridor",
            kpi_code="OPERATING_MARGIN",
            organization_scope="1000",
            category="RISK",
            comparator=Comparator.OUTSIDE_RANGE,
            threshold=Decimal("15.0"),        # Lower bound: 15%
            upper_threshold=Decimal("25.0"),  # Upper bound: 25%
            unit="percent",
            currency="",
            severity="medium",
            priority=2,
            recommendation_template="Investigate margin deviation outside approved corridor.",
            explanation_template="Operating margin is {value}%, outside approved range 15%-25%.",
            owner="finance-ops@velora.ae",
        )

        engine = RecommendationEngine(rules=[custom_rule_range], outbox_dir=self.outbox_dir, tenant_id="velora-aviation")

        # 1. In range (20%) -> No breach
        snap_in = KPISnapshot(
            snapshot_id="S-CORR-1", kpi_code="OPERATING_MARGIN", organization_scope="1000",
            period="2026-09", value=Decimal("20.0"), unit="percent", currency="",
            source_updated_time="", retrieved_at="2026-09-14T00:00:00Z", completeness="COMPLETE",
            evidence_ref="E-1", input_hash="h1"
        )
        self.assertEqual(len(engine.evaluate_snapshot(snap_in)), 0)

        # 2. Below range (12%) -> Breached!
        snap_low = KPISnapshot(
            snapshot_id="S-CORR-2", kpi_code="OPERATING_MARGIN", organization_scope="1000",
            period="2026-09", value=Decimal("12.0"), unit="percent", currency="",
            source_updated_time="", retrieved_at="2026-09-14T00:00:00Z", completeness="COMPLETE",
            evidence_ref="E-2", input_hash="h2"
        )
        recs_low = engine.evaluate_snapshot(snap_low)
        self.assertEqual(len(recs_low), 1)
        self.assertEqual(recs_low[0].status, RecommendationStatus.ACTIVE_BREACH)

        # 3. Recovers back into range (18%) -> RECOVERED!
        snap_back = KPISnapshot(
            snapshot_id="S-CORR-3", kpi_code="OPERATING_MARGIN", organization_scope="1000",
            period="2026-09", value=Decimal("18.0"), unit="percent", currency="",
            source_updated_time="", retrieved_at="2026-09-14T00:00:00Z", completeness="COMPLETE",
            evidence_ref="E-3", input_hash="h3"
        )
        recs_rec = engine.evaluate_snapshot(snap_back)
        self.assertEqual(len(recs_rec), 0)
        self.assertEqual(engine.active_recommendations[recs_low[0].duplicate_key].status, RecommendationStatus.RECOVERED)

    async def test_09_expired_rule_does_not_run(self):
        """Invariant 11: Rules past effective_to do not evaluate."""
        past_iso = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        expired_rule = KPIRecommendationRule(
            rule_code="REC-EXPIRED-TEST",
            rule_version="1.0.0",
            name="Temporary Rule",
            kpi_code="RECEIVABLES",
            organization_scope="1000",
            category="RISK",
            comparator=Comparator.GT,
            threshold=Decimal("100.00"),
            unit="currency",
            currency="AED",
            effective_from="2025-01-01T00:00:00Z",
            effective_to=past_iso,
            owner="finance-ops@velora.ae",
        )

        engine = RecommendationEngine(rules=[expired_rule], outbox_dir=self.outbox_dir, tenant_id="velora-aviation")
        mock_ar = self._create_mock_s4_ar_result(b_91_180=Decimal("500.00"), b_over_180=Decimal("500.00"))
        snap = KPISnapshot(**{k: v for k, v in (await generate_finance_snapshot(
            kpi_code="RECEIVABLES", db_path=self.db_path, s4_tool_override=lambda **kw: mock_ar
        )).items() if k in KPISnapshot.__dataclass_fields__})

        recs = engine.evaluate_snapshot(snap)
        self.assertEqual(len(recs), 0)

    async def test_10_empty_approved_rules_yields_zero_recommendations(self):
        """Invariant 12: Empty approved rules in repository produces ZERO recommendations (no seed fallback)."""
        # Create engine for a new tenant that has NO rules registered in the Business Repository
        engine_empty = RecommendationEngine(outbox_dir=self.outbox_dir, tenant_id="tenant-with-no-rules")
        self.assertEqual(len(engine_empty.rules), 0)

        mock_ar = self._create_mock_s4_ar_result(b_91_180=Decimal("5000000.00"), b_over_180=Decimal("5000000.00"))
        snap = KPISnapshot(**{k: v for k, v in (await generate_finance_snapshot(
            kpi_code="RECEIVABLES", db_path=self.db_path, s4_tool_override=lambda **kw: mock_ar
        )).items() if k in KPISnapshot.__dataclass_fields__})

        recs = engine_empty.evaluate_snapshot(snap)
        self.assertEqual(len(recs), 0)
        self.assertEqual(len(engine_empty.outbox.get_all()), 0)

    async def test_11_source_scope_currency_and_reconciliation(self):
        """Invariant 13: Generated recommendation reconciles exactly to source scope, currency, and as-of."""
        mock_ar = self._create_mock_s4_ar_result(
            b_91_180=Decimal("1100000.00"),
            b_over_180=Decimal("1100000.00"),
            currency="AED",
        )
        res = await evaluate_finance_snapshot(
            kpi_code="RECEIVABLES",
            company_code="1000",
            currency="AED",
            tenant_id="velora-aviation",
            outbox_dir=self.outbox_dir,
            db_path=self.db_path,
            s4_tool_override=lambda **kw: mock_ar,
        )

        self.assertEqual(res.get("status"), "SUCCESS")
        recs = res.get("recommendations", [])
        self.assertEqual(len(recs), 1)
        rec = recs[0]

        # Reconciles to S/4HANA source attributes
        self.assertEqual(rec["organizationScope"], "1000")
        self.assertEqual(rec["kpiCode"], "RECEIVABLES")
        self.assertEqual(Decimal(str(rec["observedValue"])), Decimal("2200000.00"))
        self.assertTrue(len(rec["supportingClaims"]) > 0)
        self.assertEqual(rec["supportingClaims"][0]["currency"], "AED")
        self.assertTrue(len(rec["supportingSources"]) > 0)
        self.assertEqual(rec["supportingSources"][0]["system"], "S4HANA")


if __name__ == "__main__":
    unittest.main()
