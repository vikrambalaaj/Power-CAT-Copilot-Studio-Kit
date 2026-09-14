"""Tests for Business Repository Layer (W03, R04, R07, Acceptance T03)."""
from __future__ import annotations

import os
import tempfile
import unittest
from decimal import Decimal
from datetime import datetime, timezone

from productivity_mcp.business_repository import (
    DecisionEvidenceRepository,
    InstitutionalRecordRepository,
    KpiDefinitionRepository,
    KpiRecommendationRuleRepository,
    KpiSnapshotRepository,
    PeerBenchmarkRepository,
    ProposalEvaluationRepository,
    RecommendationFeedbackRepository,
    RecommendationRepository,
    SourceCatalogRepository,
)


class TestBusinessRepositories(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_business.db")

        # Instantiate all repositories
        self.cat_repo = SourceCatalogRepository(db_path=self.db_path)
        self.kpi_repo = KpiDefinitionRepository(db_path=self.db_path)
        self.rule_repo = KpiRecommendationRuleRepository(db_path=self.db_path)
        self.snap_repo = KpiSnapshotRepository(db_path=self.db_path)
        self.rec_repo = RecommendationRepository(db_path=self.db_path)
        self.fb_repo = RecommendationFeedbackRepository(db_path=self.db_path)
        self.ev_repo = DecisionEvidenceRepository(db_path=self.db_path)
        self.inst_repo = InstitutionalRecordRepository(db_path=self.db_path)
        self.prop_repo = ProposalEvaluationRepository(db_path=self.db_path)
        self.bench_repo = PeerBenchmarkRepository(db_path=self.db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    async def test_source_catalog_and_tenant_isolation(self):
        """Verify SourceCatalog creation, ownership, and strict tenant isolation."""
        cat_id = self.cat_repo.create_catalog_entry(
            name="SAP S/4HANA Finance",
            description="Core general ledger and cost center accounting",
            owner="finance-lead@velora.ae",
            tenant_id="tenant-alpha",
            connection_alias="sap_prod",
            permitted_tools="sap_get_gl_balance,sap_get_cost_centers",
        )
        self.assertTrue(cat_id)

        # Tenant Alpha can access
        entry = self.cat_repo.get_catalog_entry(cat_id, tenant_id="tenant-alpha")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["name"], "SAP S/4HANA Finance")
        self.assertEqual(entry["owner"], "finance-lead@velora.ae")

        # Tenant Beta cannot access
        entry_beta = self.cat_repo.get_catalog_entry(cat_id, tenant_id="tenant-beta")
        self.assertIsNone(entry_beta)

        # Listing by tenant only returns own entries
        list_alpha = self.cat_repo.list_catalog(tenant_id="tenant-alpha")
        self.assertEqual(len(list_alpha), 1)
        list_beta = self.cat_repo.list_catalog(tenant_id="tenant-beta")
        self.assertEqual(len(list_beta), 0)

    async def test_kpi_definition_and_rules_decimal_preservation(self):
        """Verify KPI definitions and recommendation rules with decimal precision."""
        kpi_id = self.kpi_repo.create_kpi_definition(
            kpi_code="KPI-FIN-001",
            name="Operating Margin",
            business_definition="Operating income divided by net revenue",
            unit="PERCENT",
            organization_scope="Enterprise",
            sign_convention="HIGHER_IS_BETTER",
            tenant_id="tenant-alpha",
            owner="cfo@velora.ae",
        )
        self.assertTrue(kpi_id)

        rule_id = self.rule_repo.create_rule(
            rule_code="RULE-OP-MARGIN-LOW",
            name="Low Operating Margin Alert",
            kpi="KPI-FIN-001",
            organization_scope="Enterprise",
            category="FINANCIAL",
            comparator="LT",
            threshold=Decimal("15.5000"),
            clear_threshold=Decimal("17.0000"),
            unit="PERCENT",
            recommendation_template="Review OPEX drivers for margin recovery",
            explanation_template="Margin fell below target threshold",
            tenant_id="tenant-alpha",
            owner="cfo@velora.ae",
        )
        self.assertTrue(rule_id)

        # Retrieve and verify threshold decimal precision
        rule = self.rule_repo.get_rule_by_code("RULE-OP-MARGIN-LOW", tenant_id="tenant-alpha")
        self.assertIsNotNone(rule)
        self.assertEqual(rule["threshold"], Decimal("15.5000"))
        self.assertEqual(rule["clear_threshold"], Decimal("17.0000"))

    async def test_optimistic_concurrency_version(self):
        """Verify optimistic concurrency checking on mutable entities."""
        entry_id = self.cat_repo.create_catalog_entry(
            name="Original Name",
            description="Desc",
            owner="owner@velora.ae",
            tenant_id="tenant-alpha",
        )

        entry = self.cat_repo.get_catalog_entry(entry_id, tenant_id="tenant-alpha")
        initial_version = entry["version"]

        # First update with expected version succeeds
        success = self.cat_repo.update_catalog_entry(
            entry_id=entry_id,
            tenant_id="tenant-alpha",
            expected_version=initial_version,
            name="Updated Name",
        )
        self.assertTrue(success)

        # Stale update with old version fails
        stale_update = self.cat_repo.update_catalog_entry(
            entry_id=entry_id,
            tenant_id="tenant-alpha",
            expected_version=initial_version,
            name="Stale Name",
        )
        self.assertFalse(stale_update)

        # Updated entry version is incremented
        updated_entry = self.cat_repo.get_catalog_entry(entry_id, tenant_id="tenant-alpha")
        self.assertEqual(updated_entry["version"], initial_version + 1)
        self.assertEqual(updated_entry["name"], "Updated Name")

    async def test_decision_evidence_and_institutional_records(self):
        """Verify DecisionEvidence recording with output hash and InstitutionalRecord logging."""
        ev_id = self.ev_repo.record_decision_evidence(
            claim_id="CLM-CAPEX-99",
            decision_id="DEC-CAPEX-99",
            source_lookup="cre2f_proposalevaluation",
            source_version="1.0",
            input_snapshot='{"proposal_id": "PROP-01", "npv": 1250000}',
            rationale="Approved based on positive IRR and payback period under 24 months.",
            output_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            verified_identity="director@velora.ae",
            tenant_id="tenant-alpha",
            owner="director@velora.ae",
        )
        self.assertTrue(ev_id)

        evidence = self.ev_repo.get_decision_evidence(ev_id, tenant_id="tenant-alpha")
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence["claim_id"], "CLM-CAPEX-99")
        self.assertEqual(evidence["output_hash"], "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")

        rec_id = self.inst_repo.create_record(
            record_title="Executive Committee Q3 Decisions",
            record_type="EXECUTIVE_MINUTES",
            source_agent="Velora Executive Agent",
            executive_owner="ceo@velora.ae",
            summary="Approved Q3 growth initiatives.",
            key_decisions="1. Capital allocation approved. 2. Hiring approved.",
            action_items="Finance to disburse funds by Oct 1.",
            tenant_id="tenant-alpha",
        )
        self.assertTrue(rec_id)

        record = self.inst_repo.get_record(rec_id, tenant_id="tenant-alpha")
        self.assertIsNotNone(record)
        self.assertEqual(record["record_title"], "Executive Committee Q3 Decisions")


if __name__ == "__main__":
    unittest.main()
