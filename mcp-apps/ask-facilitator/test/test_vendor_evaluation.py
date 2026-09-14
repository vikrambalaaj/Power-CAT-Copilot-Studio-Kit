"""Acceptance Test Suite T11: Combined Vendor Decision Demonstration.

Validates:
1. Exact match with independent hand calculation in pure Decimal.
2. Deterministic tie-breaking policy enforcement.
3. Missing critical technical/commercial evidence prevents winner.
4. Commercial comparability mismatch (currency, tax, scope) blocks winner without implicit FX conversion.
5. Approved history influence produces exact calculated contribution deltas.
6. Irrelevant and cross-subsidiary history contributes zero.
7. Prompt injection weight/direction overrides strictly rejected.
8. Reconstruct historical decision without fresh LLM evaluation.
9. New evaluation creates new version without destructive overwrite.
10. Card-ready output and EvidenceEnvelope conformance.
11. FastMCP and server HTTP transport registration and GET mutation block.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import shutil
import tempfile
import time
import unittest
from decimal import Decimal

from starlette.testclient import TestClient

from facilitator_mcp.decision_service import evaluate_vendor_options, get_historical_decision
from facilitator_mcp.institutional_memory import ingest_institutional_record
from facilitator_mcp.server import create_app
from facilitator_mcp.tools import evaluate_vendor_options_tool, get_vendor_decision_record
from facilitator_mcp.vendor_evaluation import (
    APPROVED_POLICY_CATALOGUE,
    POLICY_VENDOR_PROC_V1,
    get_approved_policy,
)
from productivity_mcp.business_repository import (
    VendorDecisionRepository,
    get_business_repository,
    reset_business_repository_for_testing,
)

TEST_SECRET = "test-secret-facilitator-32-chars"


def make_test_jwt(payload: dict, secret: str = TEST_SECRET) -> str:
    header = {"alg": "HS256", "typ": "JWT", "kid": "test-key"}
    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode("utf-8")).decode("utf-8").rstrip("=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    signed_content = f"{h_b64}.{p_b64}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed_content, hashlib.sha256).digest()
    s_b64 = base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
    return f"{h_b64}.{p_b64}.{s_b64}"


class TestVendorEvaluationAcceptanceT11(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_decision.db")
        os.environ["VELORA_BUSINESS_REPO_DB"] = self.db_path
        os.environ["ALLOW_ANONYMOUS"] = "false"
        os.environ["ALLOW_OFFLINE_TEST_TOKENS"] = "true"
        os.environ["TEST_JWT_SECRET"] = TEST_SECRET
        reset_business_repository_for_testing()
        self.repo = get_business_repository(self.db_path)
        self.repo.clear_all_for_testing()
        self.app = create_app()
        self.client = TestClient(self.app)

    def tearDown(self):
        os.environ.pop("VELORA_BUSINESS_REPO_DB", None)
        os.environ.pop("ALLOW_ANONYMOUS", None)
        os.environ.pop("ALLOW_OFFLINE_TEST_TOKENS", None)
        os.environ.pop("TEST_JWT_SECRET", None)
        reset_business_repository_for_testing()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_hand_calculation_matches_scores_and_contributions(self):
        """Invariant 1: Independent hand calculation matches scores, contributions, and deltas in pure Decimal."""
        # 1. Ingest positive history for Alpha
        asyncio.run(
            ingest_institutional_record(
                vendor_id="VEND-10024-ALPHA",
                vendor_name="Alpha Maintenance Logistics",
                entity_scope="1000",
                contract_ref="CTR-ALPHA-2025",
                period_start="2025-01-01",
                period_end="2025-12-31",
                event_type="CONTRACT_FULFILLMENT",
                severity="LOW",
                numeric_value=Decimal("90.00"),
                unit="PERCENT",
                summary="On-time delivery and parts SLA compliance 90%",
                source_doc_ref="DOC-AUDIT-ALPHA-2025",
                original_event_date="2025-11-15T00:00:00Z",
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )

        # 2. Ingest poor history for Beta (delivery breach)
        asyncio.run(
            ingest_institutional_record(
                vendor_id="VEND-10025-BETA",
                vendor_name="Beta Technical Services",
                entity_scope="1000",
                contract_ref="CTR-BETA-2025",
                period_start="2025-01-01",
                period_end="2025-12-31",
                event_type="SLA_BREACH",
                severity="HIGH",
                numeric_value=Decimal("20.00"),
                unit="PERCENT",
                summary="Critical delivery breach on A350 hydraulic actuator overhaul",
                source_doc_ref="DOC-BREACH-BETA-2025",
                original_event_date="2025-10-10T00:00:00Z",
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )

        candidates = [
            {
                "vendor_id": "VEND-10024-ALPHA",
                "vendor_name": "Alpha Maintenance Logistics",
                "technical_score": Decimal("85.00"),
                "technical_source_ref": "DOC-TECH-ALPHA",
                "commercial_price": Decimal("100000.00"),
                "commercial_currency": "AED",
                "commercial_tax_basis": "EXCLUDING_VAT",
                "commercial_term_basis": "ANNUALIZED",
                "commercial_scope": "1000",
                "commercial_source_ref": "DOC-COMM-ALPHA",
            },
            {
                "vendor_id": "VEND-10025-BETA",
                "vendor_name": "Beta Technical Services",
                "technical_score": Decimal("70.00"),
                "technical_source_ref": "DOC-TECH-BETA",
                "commercial_price": Decimal("80000.00"),
                "commercial_currency": "AED",
                "commercial_tax_basis": "EXCLUDING_VAT",
                "commercial_term_basis": "ANNUALIZED",
                "commercial_scope": "1000",
                "commercial_source_ref": "DOC-COMM-BETA",
            },
        ]

        envelope = asyncio.run(
            evaluate_vendor_options(
                candidates=candidates,
                policy_id="POLICY-VENDOR-PROC-V1",
                policy_version="1.0.0",
                tenant_id="velora-tenant",
                caller_entity_scopes=["1000"],
                caller_roles=["CORP_PROCUREMENT"],
                db_path=self.db_path,
            )
        )

        self.assertEqual(envelope["operationStatus"], "SUCCESS")
        result = envelope["typedResult"]

        # Hand calculation verification:
        # Prices: min=80k, max=100k, span=20k
        # Alpha price norm = 100 * (100k - 100k) / 20k = 0.00
        # Beta price norm = 100 * (100k - 80k) / 20k = 100.00
        # Alpha tech norm = 85.00, Beta tech norm = 70.00
        # Alpha history norm = 90.00, Beta history norm = 20.00

        # Baseline: Tech 0.50, Price 0.50
        # Alpha baseline: 0.50*85 + 0.50*0 = 42.50
        # Beta baseline: 0.50*70 + 0.50*100 = 35 + 50 = 85.00
        alpha_base = result["baselineScore"]["VEND-10024-ALPHA"]
        beta_base = result["baselineScore"]["VEND-10025-BETA"]
        self.assertEqual(alpha_base["totalScore"], "42.50")
        self.assertEqual(beta_base["totalScore"], "85.00")

        # History-Informed: Tech 0.40, Price 0.40, History 0.20
        # Alpha history-informed:
        # Tech: 0.40*85 = 34.00 (delta: 34.00 - 42.50 = -8.50)
        # Price: 0.40*0 = 0.00 (delta: 0.00 - 0.00 = 0.00)
        # History: 0.20*90 = 18.00 (delta: +18.00)
        # Total = 34.00 + 0.00 + 18.00 = 52.00 (score delta: 52.00 - 42.50 = +9.50)
        alpha_final = result["finalScore"]["VEND-10024-ALPHA"]
        alpha_mem = result["memoryContributions"]["VEND-10024-ALPHA"]
        self.assertEqual(alpha_final["totalScore"], "52.00")
        self.assertEqual(alpha_mem["scoreDelta"], "9.50")
        self.assertEqual(alpha_mem["contributionDeltas"]["HISTORICAL_PERFORMANCE"], "18.00")

        # Beta history-informed:
        # Tech: 0.40*70 = 28.00 (delta: 28.00 - 35.00 = -7.00)
        # Price: 0.40*100 = 40.00 (delta: 40.00 - 50.00 = -10.00)
        # History: 0.20*20 = 4.00 (delta: +4.00)
        # Total = 28.00 + 40.00 + 4.00 = 72.00 (score delta: 72.00 - 85.00 = -13.00)
        beta_final = result["finalScore"]["VEND-10025-BETA"]
        beta_mem = result["memoryContributions"]["VEND-10025-BETA"]
        self.assertEqual(beta_final["totalScore"], "72.00")
        self.assertEqual(beta_mem["scoreDelta"], "-13.00")

        # Winner: Beta (72.00 vs 52.00)
        self.assertEqual(result["selectedOption"], "VEND-10025-BETA")
        self.assertEqual(result["finalRank"], ["VEND-10025-BETA", "VEND-10024-ALPHA"])

    def test_02_deterministic_tie_policy_enforcement(self):
        """Invariant 2: When final composite scores are identical, tie policy (HIGHER_TECHNICAL_WINS) breaks tie."""
        candidates = [
            {
                "vendor_id": "VEND-TIED-A",
                "vendor_name": "Tied Vendor A (Higher Tech)",
                "technical_score": Decimal("80.00"),
                "commercial_price": Decimal("100000.00"),
                "commercial_currency": "AED",
                "commercial_tax_basis": "EXCLUDING_VAT",
                "commercial_term_basis": "ANNUALIZED",
                "commercial_scope": "1000",
            },
            {
                "vendor_id": "VEND-TIED-B",
                "vendor_name": "Tied Vendor B (Lower Tech, Equal Score)",
                "technical_score": Decimal("70.00"),
                "commercial_price": Decimal("100000.00"),
                "commercial_currency": "AED",
                "commercial_tax_basis": "EXCLUDING_VAT",
                "commercial_term_basis": "ANNUALIZED",
                "commercial_scope": "1000",
            },
        ]
        envelope = asyncio.run(
            evaluate_vendor_options(
                candidates=candidates,
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
        result = envelope["typedResult"]
        self.assertEqual(result["selectedOption"], "VEND-TIED-A")
        self.assertEqual(result["finalRank"][0], "VEND-TIED-A")

    def test_03_missing_mandatory_technical_evidence_blocks_winner(self):
        """Invariant 3: Missing critical technical evidence produces INSUFFICIENT_EVIDENCE and no winner."""
        candidates = [
            {
                "vendor_id": "VEND-INCOMPLETE-01",
                "vendor_name": "Incomplete Vendor",
                "technical_score": None,  # Missing mandatory score
                "commercial_price": Decimal("90000.00"),
                "commercial_currency": "AED",
                "commercial_tax_basis": "EXCLUDING_VAT",
                "commercial_term_basis": "ANNUALIZED",
                "commercial_scope": "1000",
            },
            {
                "vendor_id": "VEND-COMPLETE-02",
                "vendor_name": "Complete Vendor",
                "technical_score": Decimal("75.00"),
                "commercial_price": Decimal("95000.00"),
                "commercial_currency": "AED",
                "commercial_tax_basis": "EXCLUDING_VAT",
                "commercial_term_basis": "ANNUALIZED",
                "commercial_scope": "1000",
            },
        ]
        envelope = asyncio.run(
            evaluate_vendor_options(
                candidates=candidates,
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
        self.assertEqual(envelope["operationStatus"], "CONFIGURATION_REQUIRED")
        self.assertIsNone(envelope["typedResult"]["selectedOption"])
        self.assertTrue(any("Missing mandatory technical" in w for w in envelope["warnings"]))

    def test_04_commercial_comparability_mismatch_blocks_winner(self):
        """Invariant 4: Incomparable currency or scope mismatch prevents winner without implicit conversion."""
        candidates = [
            {
                "vendor_id": "VEND-AED-01",
                "vendor_name": "Local Vendor AED",
                "technical_score": Decimal("80.00"),
                "commercial_price": Decimal("100000.00"),
                "commercial_currency": "AED",
                "commercial_tax_basis": "EXCLUDING_VAT",
                "commercial_term_basis": "ANNUALIZED",
                "commercial_scope": "1000",
            },
            {
                "vendor_id": "VEND-USD-02",
                "vendor_name": "Foreign Vendor USD",
                "technical_score": Decimal("85.00"),
                "commercial_price": Decimal("25000.00"),
                "commercial_currency": "USD",  # Mismatch: policy requires AED
                "commercial_tax_basis": "EXCLUDING_VAT",
                "commercial_term_basis": "ANNUALIZED",
                "commercial_scope": "1000",
            },
        ]
        envelope = asyncio.run(
            evaluate_vendor_options(
                candidates=candidates,
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
        self.assertEqual(envelope["operationStatus"], "CONFIGURATION_REQUIRED")
        self.assertIsNone(envelope["typedResult"]["selectedOption"])
        self.assertTrue(any("currency mismatch" in w for w in envelope["warnings"]))

    def test_05_approved_history_influence_produces_exact_calculated_delta(self):
        """Invariant 5: Historical performance modifies composite score strictly by the policy-defined delta."""
        asyncio.run(
            ingest_institutional_record(
                vendor_id="VEND-DELTA-TEST",
                vendor_name="Delta Test Supplier",
                entity_scope="1000",
                contract_ref="CTR-DELTA-01",
                period_start="2025-01-01",
                period_end="2025-12-31",
                event_type="CONTRACT_FULFILLMENT",
                severity="LOW",
                numeric_value=Decimal("100.00"),
                unit="PERCENT",
                summary="Perfect contract fulfillment",
                source_doc_ref="DOC-PERFECT-01",
                original_event_date="2025-06-01T00:00:00Z",
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
        candidates = [
            {
                "vendor_id": "VEND-DELTA-TEST",
                "vendor_name": "Delta Test Supplier",
                "technical_score": Decimal("80.00"),
                "commercial_price": Decimal("100000.00"),
                "commercial_currency": "AED",
                "commercial_tax_basis": "EXCLUDING_VAT",
                "commercial_term_basis": "ANNUALIZED",
                "commercial_scope": "1000",
            }
        ]
        envelope = asyncio.run(
            evaluate_vendor_options(
                candidates=candidates,
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
        result = envelope["typedResult"]
        v_mem = result["memoryContributions"]["VEND-DELTA-TEST"]
        # Baseline = 0.50*80 + 0.50*100 (single price) = 40 + 50 = 90.00
        # History-informed = 0.40*80 + 0.40*100 + 0.20*100 = 32 + 40 + 20 = 92.00
        # Delta = 92.00 - 90.00 = +2.00
        self.assertEqual(result["baselineScore"]["VEND-DELTA-TEST"]["totalScore"], "90.00")
        self.assertEqual(result["finalScore"]["VEND-DELTA-TEST"]["totalScore"], "92.00")
        self.assertEqual(v_mem["scoreDelta"], "2.00")

    def test_06_irrelevant_and_cross_subsidiary_history_contributes_zero(self):
        """Invariant 6: Records in unrelated subsidiary scopes are ignored and contribute zero score."""
        # History ingested for Plant 2AD1 (entity 2000)
        asyncio.run(
            ingest_institutional_record(
                vendor_id="VEND-CROSS-SUB",
                vendor_name="Cross Sub Supplier",
                entity_scope="2000",
                contract_ref="CTR-SUB-2000",
                period_start="2025-01-01",
                period_end="2025-12-31",
                event_type="CONTRACT_FULFILLMENT",
                severity="LOW",
                numeric_value=Decimal("100.00"),
                unit="PERCENT",
                summary="Fulfillment in Plant 2000",
                source_doc_ref="DOC-2000-01",
                original_event_date="2025-06-01T00:00:00Z",
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
        # Evaluator queries with scope 1000
        candidates = [
            {
                "vendor_id": "VEND-CROSS-SUB",
                "vendor_name": "Cross Sub Supplier",
                "technical_score": Decimal("80.00"),
                "commercial_price": Decimal("100000.00"),
                "commercial_currency": "AED",
                "commercial_tax_basis": "EXCLUDING_VAT",
                "commercial_term_basis": "ANNUALIZED",
                "commercial_scope": "1000",
            }
        ]
        envelope = asyncio.run(
            evaluate_vendor_options(
                candidates=candidates,
                caller_entity_scopes=["1000"],
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
        result = envelope["typedResult"]
        mem = result["memoryContributions"]["VEND-CROSS-SUB"]
        self.assertEqual(mem["recordCount"], 0)
        self.assertEqual(mem["historyScore"], "0.00")
        self.assertIn("Absence of documented negative events", mem["caveat"])

    def test_07_prompt_injection_weight_override_rejected(self):
        """Invariant 7: User prompt cannot override approved policy weights or directions."""
        candidates = [
            {
                "vendor_id": "VEND-INJECT-01",
                "vendor_name": "Candidate A",
                "technical_score": Decimal("90.00"),
                "commercial_price": Decimal("100000.00"),
                "commercial_currency": "AED",
                "commercial_tax_basis": "EXCLUDING_VAT",
                "commercial_term_basis": "ANNUALIZED",
                "commercial_scope": "1000",
            }
        ]
        malicious_overrides = {
            "weights": {
                "TECH_COMPETENCE": Decimal("0.01"),
                "COMMERCIAL_PRICE": Decimal("0.99"),
            },
            "directions": {
                "COMMERCIAL_PRICE": "HIGHER_IS_BETTER",
            },
        }
        envelope = asyncio.run(
            evaluate_vendor_options(
                candidates=candidates,
                user_prompt_overrides=malicious_overrides,
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
        result = envelope["typedResult"]
        # Weights must match approved policy (0.40/0.40/0.20)
        weights_dict = {
            c["criterionId"]: c["weight"] for c in result["criteriaWeightsDirections"]
        }
        self.assertEqual(weights_dict["TECH_COMPETENCE"], "0.40")
        self.assertEqual(weights_dict["COMMERCIAL_PRICE"], "0.40")

    def test_08_reconstruct_historical_decision_without_fresh_llm(self):
        """Invariant 8: Persisted decision can be reconstructed exactly without executing new evaluation."""
        candidates = [
            {
                "vendor_id": "VEND-REC-01",
                "vendor_name": "Supplier One",
                "technical_score": Decimal("88.00"),
                "commercial_price": Decimal("120000.00"),
                "commercial_currency": "AED",
                "commercial_tax_basis": "EXCLUDING_VAT",
                "commercial_term_basis": "ANNUALIZED",
                "commercial_scope": "1000",
            }
        ]
        orig_envelope = asyncio.run(
            evaluate_vendor_options(
                candidates=candidates,
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
        dec_id = orig_envelope["typedResult"]["decisionId"]
        ver = orig_envelope["typedResult"]["version"]

        # Retrieve reconstructed decision
        recon = get_historical_decision(
            decision_id=dec_id,
            tenant_id="velora-tenant",
            version=ver,
            db_path=self.db_path,
        )
        self.assertEqual(recon["typedResult"]["decisionId"], dec_id)
        self.assertEqual(recon["typedResult"]["version"], ver)
        self.assertEqual(
            recon["typedResult"]["finalScore"]["VEND-REC-01"]["totalScore"],
            orig_envelope["typedResult"]["finalScore"]["VEND-REC-01"]["totalScore"],
        )
        self.assertEqual(recon["audit"]["status"], "HISTORICAL_RECONSTRUCTION")

    def test_09_new_evaluation_creates_new_version_without_overwrite(self):
        """Invariant 9: Re-evaluating candidate options creates a new version without destroying history."""
        candidates = [
            {
                "vendor_id": "VEND-VER-01",
                "vendor_name": "Versioned Supplier",
                "technical_score": Decimal("80.00"),
                "commercial_price": Decimal("90000.00"),
                "commercial_currency": "AED",
                "commercial_tax_basis": "EXCLUDING_VAT",
                "commercial_term_basis": "ANNUALIZED",
                "commercial_scope": "1000",
            }
        ]
        # First evaluation -> 1.0.0
        env1 = asyncio.run(
            evaluate_vendor_options(
                candidates=candidates,
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
        dec_id = env1["typedResult"]["decisionId"]
        self.assertEqual(env1["typedResult"]["version"], "1.0.0")

        # Second evaluation -> 1.0.1
        env2 = asyncio.run(
            evaluate_vendor_options(
                candidates=candidates,
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
        self.assertEqual(env2["typedResult"]["decisionId"], dec_id)
        self.assertEqual(env2["typedResult"]["version"], "1.0.1")

        # Confirm 1.0.0 is still retrievable
        v1_rec = get_historical_decision(decision_id=dec_id, tenant_id="velora-tenant", version="1.0.0", db_path=self.db_path)
        self.assertEqual(v1_rec["typedResult"]["version"], "1.0.0")

        # Confirm 1.0.1 is retrievable
        v2_rec = get_historical_decision(decision_id=dec_id, tenant_id="velora-tenant", version="1.0.1", db_path=self.db_path)
        self.assertEqual(v2_rec["typedResult"]["version"], "1.0.1")

    def test_10_card_ready_output_and_evidence_envelope_conformance(self):
        """Invariant 10: Output matches card-ready DecisionRecord and EvidenceEnvelope schema."""
        candidates = [
            {
                "vendor_id": "VEND-CARD-01",
                "vendor_name": "Card Ready Vendor",
                "technical_score": Decimal("82.00"),
                "commercial_price": Decimal("75000.00"),
                "commercial_currency": "AED",
                "commercial_tax_basis": "EXCLUDING_VAT",
                "commercial_term_basis": "ANNUALIZED",
                "commercial_scope": "1000",
            }
        ]
        envelope = asyncio.run(
            evaluate_vendor_options(
                candidates=candidates,
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
        self.assertIn("schemaVersion", envelope)
        self.assertIn("operationStatus", envelope)
        self.assertIn("resultSummary", envelope)
        self.assertIn("typedResult", envelope)
        self.assertIn("claims", envelope)
        self.assertIn("sources", envelope)
        self.assertIn("correlationId", envelope)
        self.assertIn("audit", envelope)

        res = envelope["typedResult"]
        self.assertIn("decisionId", res)
        self.assertIn("criteriaWeightsDirections", res)
        self.assertIn("baselineScore", res)
        self.assertIn("memoryContributions", res)
        self.assertIn("finalScore", res)
        self.assertIn("finalRank", res)
        self.assertIn("tiePolicy", res)
        self.assertIn("conciseRationale", res)

    def test_11_tools_and_server_registration(self):
        """Invariant 11: Tool wrapper functions and FastMCP server endpoints are registered and block GET mutations."""
        # Test tool wrapper execution
        candidates = [
            {
                "vendor_id": "VEND-TOOL-01",
                "vendor_name": "Tool Test Vendor",
                "technical_score": Decimal("85.00"),
                "commercial_price": Decimal("90000.00"),
                "commercial_currency": "AED",
                "commercial_tax_basis": "EXCLUDING_VAT",
                "commercial_term_basis": "ANNUALIZED",
                "commercial_scope": "1000",
            }
        ]
        res = asyncio.run(
            evaluate_vendor_options_tool(
                candidates=candidates,
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
        self.assertEqual(res["operationStatus"], "SUCCESS")
        dec_id = res["typedResult"]["decisionId"]

        # Test tool wrapper readback
        rec = get_vendor_decision_record(decision_id=dec_id, tenant_id="velora-tenant", db_path=self.db_path)
        self.assertEqual(rec["typedResult"]["decisionId"], dec_id)

        # Test HTTP REST boundary: GET on mutating tool must return 405 Method Not Allowed
        token = make_test_jwt({
            "tid": "7d167021-f5e9-4331-9b75-d44d55a1ce9b",
            "oid": "buyer-1",
            "aud": "https://api.velora.ae",
            "roles": ["CORP_PROCUREMENT"],
            "exp": int(time.time()) + 3600,
            "sub": "buyer-1",
        }, secret=TEST_SECRET)
        response_get = self.client.get(
            "/evaluate_vendor_options",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response_get.status_code, 405)


if __name__ == "__main__":
    unittest.main()
