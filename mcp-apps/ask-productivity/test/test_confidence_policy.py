"""Unit tests for Confidence Assessment Policy v1 (W01 Acceptance T01)."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import unittest

from productivity_mcp.confidence_policy import (
    evaluate_confidence,
    derive_composite_confidence,
)
from productivity_mcp.evidence_contracts import (
    ConfidenceAssessment,
    ConfidenceLabel,
    EvidenceSource,
)


class TestConfidencePolicy(unittest.TestCase):
    """Test suite verifying conservative evidence confidence policy v1."""

    def setUp(self):
        self.now = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)

    def test_no_sources_returns_unassessed(self):
        """Verify empty sources list returns UNASSESSED."""
        assessment = evaluate_confidence([], now=self.now)
        self.assertEqual(assessment.label, ConfidenceLabel.UNASSESSED)
        self.assertIn("NO_SOURCES_PROVIDED", assessment.limitingFactors)

    def test_authoritative_fresh_complete_source_returns_high(self):
        """Verify authoritative, fresh, and complete source returns HIGH."""
        fresh_ts = (self.now - timedelta(hours=2)).isoformat()
        src = EvidenceSource(
            sourceId="SRC-S4-01",
            system="S4HANA",
            businessTitle="Customer AR Ledger",
            retrievedAt=self.now.isoformat(),
            sourceUpdatedAt=fresh_ts,
        )
        assessment = evaluate_confidence([src], now=self.now, is_authoritative_single_source=True)
        self.assertEqual(assessment.label, ConfidenceLabel.HIGH)
        self.assertEqual(assessment.timeliness, "FRESH_WITHIN_SLA")
        self.assertEqual(len(assessment.limitingFactors), 0)

    def test_stale_source_exceeding_sla_forces_low(self):
        """Verify source updated beyond SLA (e.g. 36h old on 24h SLA) drops to LOW."""
        stale_ts = (self.now - timedelta(hours=36)).isoformat()
        src = EvidenceSource(
            sourceId="SRC-S4-OLD",
            system="S4HANA",
            businessTitle="Stale S/4HANA Ledger",
            retrievedAt=self.now.isoformat(),
            sourceUpdatedAt=stale_ts,
        )
        # Even with perfect completeness and authoritative system, staleness forces LOW
        assessment = evaluate_confidence(
            [src],
            now=self.now,
            source_sla_hours=24.0,
            is_materially_complete=True,
            is_authoritative_single_source=True,
        )
        self.assertEqual(assessment.label, ConfidenceLabel.LOW)
        self.assertEqual(assessment.timeliness, "STALE_EXCEEDS_SLA")
        self.assertTrue(any("EXCEED_SLA" in f for f in assessment.limitingFactors))

    def test_perfect_extraction_cannot_override_stale_source(self):
        """Acceptance T01 invariant: perfect extraction completeness cannot override a stale source."""
        stale_ts = (self.now - timedelta(hours=72)).isoformat()
        src = EvidenceSource(
            sourceId="SRC-01",
            system="S4HANA",
            businessTitle="AR 100% Extracted Rows",
            retrievedAt=self.now.isoformat(),
            sourceUpdatedAt=stale_ts,
            coverage="100% rows verified",
            limitations=[],
        )
        assessment = evaluate_confidence(
            [src],
            now=self.now,
            source_sla_hours=24.0,
            is_materially_complete=True,
        )
        self.assertEqual(assessment.label, ConfidenceLabel.LOW)

    def test_partial_extraction_or_conflict_drops_confidence_to_low(self):
        """Verify material incompleteness or unresolved conflict drops confidence to LOW."""
        fresh_ts = (self.now - timedelta(hours=1)).isoformat()
        src = EvidenceSource(
            sourceId="SRC-02",
            system="S4HANA",
            businessTitle="Partial Extraction",
            retrievedAt=self.now.isoformat(),
            sourceUpdatedAt=fresh_ts,
        )
        # Materially incomplete
        assessment_incomplete = evaluate_confidence(
            [src],
            now=self.now,
            is_materially_complete=False,
        )
        self.assertEqual(assessment_incomplete.label, ConfidenceLabel.LOW)
        self.assertIn("MATERIAL_EXTRACTION_GAPS", assessment_incomplete.limitingFactors)

        # Conflicting sources
        assessment_conflict = evaluate_confidence(
            [src],
            now=self.now,
            has_conflicts=True,
        )
        self.assertEqual(assessment_conflict.label, ConfidenceLabel.LOW)
        self.assertIn("UNRESOLVED_DATA_CONFLICT", assessment_conflict.limitingFactors)

    def test_non_comparable_definitions_forces_low(self):
        """Verify non-comparable definitions force LOW confidence."""
        src = EvidenceSource(
            sourceId="SRC-PEER-01",
            system="ExternalBenchmark",
            businessTitle="Peer DSO Benchmark",
            retrievedAt=self.now.isoformat(),
            sourceUpdatedAt=self.now.isoformat(),
        )
        assessment = evaluate_confidence([src], now=self.now, is_definition_compatible=False)
        self.assertEqual(assessment.label, ConfidenceLabel.LOW)
        self.assertIn("NON_COMPARABLE_DEFINITIONS", assessment.limitingFactors)

    def test_derived_recommendation_reflects_weakest_limiting_input(self):
        """Acceptance T01 invariant: derived composite confidence reflects weakest input."""
        high_assessment = ConfidenceAssessment(
            label=ConfidenceLabel.HIGH,
            sourceReliability="AUTHORITATIVE",
            corroboration="SATISFIED",
            timeliness="FRESH_WITHIN_SLA",
            completeness="COMPLETE",
            comparability="COMPATIBLE",
            reason="Authoritative verified ERP balance",
        )
        medium_assessment = ConfidenceAssessment(
            label=ConfidenceLabel.MEDIUM,
            sourceReliability="PRIMARY_M365",
            corroboration="SATISFIED",
            timeliness="FRESH_WITHIN_SLA",
            completeness="COMPLETE",
            comparability="COMPATIBLE",
            reason="Primary email communication",
        )
        low_assessment = ConfidenceAssessment(
            label=ConfidenceLabel.LOW,
            sourceReliability="UNVERIFIED",
            corroboration="NONE",
            timeliness="STALE_EXCEEDS_SLA",
            completeness="INCOMPLETE",
            comparability="UNKNOWN",
            reason="Stale third-party report",
            limitingFactors=["STALE_EXCEEDS_SLA"],
        )

        composite_high_med = derive_composite_confidence([high_assessment, medium_assessment])
        self.assertEqual(composite_high_med.label, ConfidenceLabel.MEDIUM)

        composite_with_low = derive_composite_confidence([high_assessment, medium_assessment, low_assessment])
        self.assertEqual(composite_with_low.label, ConfidenceLabel.LOW)
        self.assertIn("STALE_EXCEEDS_SLA", composite_with_low.limitingFactors)


if __name__ == "__main__":
    unittest.main()
