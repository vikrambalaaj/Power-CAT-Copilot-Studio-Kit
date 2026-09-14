"""Unit tests for Common Contracts v1 and Evidence Envelope (W01 Acceptance T01)."""
from datetime import datetime, timezone
from decimal import Decimal
import json
import unittest

from productivity_mcp.evidence_contracts import (
    ActorType,
    AttentionItem,
    AutomationSubscription,
    ClaimKind,
    ConfidenceAssessment,
    ConfidenceLabel,
    DecisionRecord,
    DeliveryReceipt,
    EvidenceEnvelope,
    EvidenceSource,
    ExecutionContext,
    MaterialClaim,
    OperationStatus,
    SubscriptionKind,
    decimal_serializer,
)
from productivity_mcp.models import HandoffRequest, HandoffResponse, ReadToolEnvelope


class TestEvidenceContracts(unittest.TestCase):
    """Test suite verifying Common Contracts v1 specifications."""

    def test_decimal_preservation_in_json_serialization(self):
        """Verify finance Decimals preserve exact precision without floating point corruption."""
        val = Decimal("2400000.00")
        claim = MaterialClaim(
            claimId="CLM-001",
            kind=ClaimKind.FACT,
            text="Customer receivables overdue > 180 days reached AED 2,400,000.00",
            numericValue=val,
            currency="AED",
            sourceIds=["SRC-S4-AR"],
        )
        self.assertEqual(claim.numericValue, Decimal("2400000.00"))
        
        # Test serialization
        dumped = claim.model_dump()
        self.assertEqual(dumped["numericValue"], "2400000.00")
        
        # Test JSON round trip
        json_str = json.dumps(dumped)
        reloaded = json.loads(json_str)
        self.assertEqual(reloaded["numericValue"], "2400000.00")
        self.assertEqual(Decimal(reloaded["numericValue"]), val)

    def test_unknown_timestamp_stays_null(self):
        """Verify missing source update time remains null and is not fabricated."""
        src = EvidenceSource(
            sourceId="SRC-01",
            system="S4HANA",
            businessTitle="AR Overdue Ledger",
            retrievedAt="2026-09-14T10:00:00Z",
            sourceUpdatedAt=None,
        )
        self.assertIsNone(src.sourceUpdatedAt)
        dumped = src.model_dump()
        self.assertIsNone(dumped["sourceUpdatedAt"])

    def test_factual_claim_requires_source_ids(self):
        """Verify factual claims fail validation if no source references are attached."""
        with self.assertRaises(ValueError):
            MaterialClaim(
                claimId="CLM-FACT-INVALID",
                kind=ClaimKind.FACT,
                text="Active headcount is 3,704",
                sourceIds=[],  # Empty sources forbidden for factual assertions
            )

    def test_two_source_response_maps_each_claim_to_source(self):
        """Verify multi-source envelope correctly attributes each claim to its originating source."""
        src_sf = EvidenceSource(
            sourceId="SRC-SF-HEADCOUNT",
            system="SuccessFactors",
            businessTitle="Active Workforce Roster",
            retrievedAt="2026-09-14T10:00:00Z",
        )
        src_s4 = EvidenceSource(
            sourceId="SRC-S4-AR",
            system="S4HANA",
            businessTitle="Accounts Receivable Aging",
            retrievedAt="2026-09-14T10:00:00Z",
        )

        claim_sf = MaterialClaim(
            claimId="CLM-01",
            kind=ClaimKind.FACT,
            text="Active eligible headcount is 3,704",
            numericValue=Decimal("3704"),
            unit="Headcount",
            sourceIds=["SRC-SF-HEADCOUNT"],
        )
        claim_s4 = MaterialClaim(
            claimId="CLM-02",
            kind=ClaimKind.FACT,
            text="Overdue receivables balance is AED 2,400,000.00",
            numericValue=Decimal("2400000.00"),
            currency="AED",
            sourceIds=["SRC-S4-AR"],
        )

        envelope = EvidenceEnvelope(
            operation="GET_EXECUTIVE_SUMMARY",
            status=OperationStatus.SUCCESS,
            resultSummary="Executive workforce and financial overview.",
            claims=[claim_sf, claim_s4],
            sources=[src_sf, src_s4],
            correlationId="corr-test-123",
            generatedAt="2026-09-14T10:05:00Z",
        )

        self.assertEqual(len(envelope.sources), 2)
        self.assertEqual(len(envelope.claims), 2)
        self.assertIn("SRC-SF-HEADCOUNT", envelope.claims[0].sourceIds)
        self.assertIn("SRC-S4-AR", envelope.claims[1].sourceIds)

        # Canonical JSON check
        canonical = envelope.to_canonical_json()
        self.assertIn("SRC-SF-HEADCOUNT", canonical)
        self.assertIn("2400000.00", canonical)

    def test_metadata_survives_handoff_response(self):
        """Verify claims, sources, and confidence metadata survive the full HandoffResponse route."""
        src = EvidenceSource(
            sourceId="SRC-OUTLOOK-01",
            system="Outlook",
            businessTitle="Executive Inbox Priority",
            retrievedAt="2026-09-14T10:00:00Z",
        )
        claim = MaterialClaim(
            claimId="CLM-MAIL-01",
            kind=ClaimKind.FACT,
            text="2 VIP urgent emails require executive attention",
            numericValue=Decimal("2"),
            unit="Items",
            sourceIds=["SRC-OUTLOOK-01"],
        )
        confidence = ConfidenceAssessment(
            label=ConfidenceLabel.HIGH,
            sourceReliability="AUTHORITATIVE",
            corroboration="SATISFIED",
            timeliness="FRESH_WITHIN_SLA",
            completeness="COMPLETE",
            comparability="COMPATIBLE",
            reason="Direct verified Graph mailbox query.",
        )

        resp = HandoffResponse(
            status="SUCCESS",
            resultSummary="Triage complete.",
            correlationId="corr-handoff-999",
            claims=[claim],
            sources=[src],
            confidence=confidence,
        )

        self.assertEqual(len(resp.claims), 1)
        self.assertEqual(resp.claims[0].claimId, "CLM-MAIL-01")
        self.assertEqual(len(resp.sources), 1)
        self.assertEqual(resp.sources[0].sourceId, "SRC-OUTLOOK-01")
        self.assertIsNotNone(resp.confidence)
        self.assertEqual(resp.confidence.label, ConfidenceLabel.HIGH)


if __name__ == "__main__":
    unittest.main()
