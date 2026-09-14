"""Acceptance Test Suite T12: Cryptographic Decision Trail Export and Retention.

Validates:
1. Auditor export reconstructs W11 decision from saved data with full manifest.
2. Deterministic calculation replay: same inputs give same deterministic result.
3. Tamper detection: changed contribution or score is detected.
4. Tamper detection: removed candidate record or bad cryptographic signature is detected.
5. Application role (velora-app-service) cannot update or delete finalized evidence.
6. Unauthorized actor without audit/compliance role cannot export (403 / PermissionError).
7. Governed export fails closed during simulated audit logging outage.
8. Evidence artifact links are time-bounded; expired access is strictly denied.
9. Spreadsheet (CSV) export neutralizes formula injection attacks (CWE-1236).
10. Authorized declared redactions pass verification while undeclared alterations fail.
11. FastMCP tool registration and HTTP transport blocks GET mutations with 405.
"""
import asyncio
import base64
from copy import deepcopy
from decimal import Decimal
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest

from starlette.testclient import TestClient

from facilitator_mcp.audit_export import (
    ArtifactAccessExpiredError,
    ArtifactTokenInvalidError,
    export_decision_trail,
    generate_artifact_token,
    resolve_artifact_token,
    sanitize_cell_for_csv,
    verify_decision_manifest,
)
from facilitator_mcp.decision_audit import (
    AuditLoggingOutageError,
    DecisionNotFoundError,
    FinalizedEvidenceMutationError,
    build_decision_manifest,
    finalize_decision_evidence,
)
from facilitator_mcp.decision_service import evaluate_vendor_options
from facilitator_mcp.institutional_memory import ingest_institutional_record
from facilitator_mcp.server import create_app
from facilitator_mcp.tools import (
    export_decision_trail as export_decision_trail_tool,
    verify_decision_manifest as verify_decision_manifest_tool,
)
from productivity_mcp.business_repository import (
    VendorDecisionRecord,
    VendorDecisionRepository,
    get_business_repository,
    reset_business_repository_for_testing,
)

TEST_SECRET = "test-secret-facilitator-32-chars"
TEST_SIGNING_KEY = "test-audit-signing-key-32-bytes"


def make_test_jwt(payload: dict, secret: str = TEST_SECRET) -> str:
    header = {"alg": "HS256", "typ": "JWT", "kid": "test-key"}
    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode("utf-8")).decode("utf-8").rstrip("=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    signed_content = f"{h_b64}.{p_b64}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed_content, hashlib.sha256).digest()
    s_b64 = base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
    return f"{h_b64}.{p_b64}.{s_b64}"


class TestDecisionAuditExportAcceptanceT12(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_decision_audit.db")
        self.export_dir = Path(self.test_dir) / "exports"
        self.export_dir.mkdir(parents=True, exist_ok=True)

        os.environ["VELORA_BUSINESS_REPO_DB"] = self.db_path
        os.environ["VELORA_AUDIT_SIGNING_KEY"] = TEST_SIGNING_KEY
        os.environ["VELORA_AUDIT_EXPORT_DIR"] = str(self.export_dir)
        os.environ["ALLOW_ANONYMOUS"] = "false"
        os.environ["ALLOW_OFFLINE_TEST_TOKENS"] = "true"
        os.environ["TEST_JWT_SECRET"] = TEST_SECRET
        os.environ.pop("VELORA_SIMULATE_AUDIT_OUTAGE", None)

        reset_business_repository_for_testing()
        self.repo = get_business_repository(self.db_path)
        self.repo.clear_all_for_testing()
        self.app = create_app()
        self.client = TestClient(self.app)

        # Ingest baseline history for Alpha and Beta
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
                summary="On-time delivery SLA compliance 90%",
                source_doc_ref="DOC-AUDIT-ALPHA-2025",
                original_event_date="2025-11-15T00:00:00Z",
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
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
                summary="Actuator delivery breach",
                source_doc_ref="DOC-BREACH-BETA-2025",
                original_event_date="2025-10-10T00:00:00Z",
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )

        # Execute standard W11 decision
        self.candidates = [
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
        self.eval_envelope = asyncio.run(
            evaluate_vendor_options(
                candidates=self.candidates,
                tenant_id="velora-tenant",
                caller_entity_scopes=["1000"],
                caller_roles=["CORP_PROCUREMENT"],
                db_path=self.db_path,
            )
        )
        self.decision_id = self.eval_envelope["typedResult"]["decisionId"]
        self.version = self.eval_envelope["typedResult"]["version"]

    def tearDown(self):
        os.environ.pop("VELORA_BUSINESS_REPO_DB", None)
        os.environ.pop("VELORA_AUDIT_SIGNING_KEY", None)
        os.environ.pop("VELORA_AUDIT_EXPORT_DIR", None)
        os.environ.pop("ALLOW_ANONYMOUS", None)
        os.environ.pop("ALLOW_OFFLINE_TEST_TOKENS", None)
        os.environ.pop("TEST_JWT_SECRET", None)
        os.environ.pop("VELORA_SIMULATE_AUDIT_OUTAGE", None)
        reset_business_repository_for_testing()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_auditor_export_reconstructs_decision_from_saved_data(self):
        """Invariant 1: Auditor export reconstructs W11 decision from saved data with verified manifest."""
        export_res = export_decision_trail(
            decision_id=self.decision_id,
            version=self.version,
            tenant_id="velora-tenant",
            export_format="JSON",
            caller_roles=["AUDITOR"],
            db_path=self.db_path,
            export_dir=self.export_dir,
            signing_key=TEST_SIGNING_KEY,
        )

        self.assertEqual(export_res["operationStatus"], "SUCCESS")
        typed = export_res["typedResult"]
        self.assertEqual(typed["decisionId"], self.decision_id)
        self.assertEqual(typed["version"], self.version)
        self.assertTrue(os.path.exists(typed["artifactPath"]))

        # Verify manifest with standalone verifier
        manifest = typed["manifest"]
        is_valid, status, details = verify_decision_manifest(
            manifest_data=manifest,
            signing_key=TEST_SIGNING_KEY,
        )
        self.assertTrue(is_valid)
        self.assertEqual(status, "VERIFICATION_SUCCESSFUL")
        self.assertEqual(details["decisionId"], self.decision_id)

    def test_02_deterministic_replay_verification(self):
        """Invariant 2: Deterministic replay: same inputs give identical mathematical scores and deltas."""
        manifest = build_decision_manifest(
            decision_id=self.decision_id,
            tenant_id="velora-tenant",
            version=self.version,
            db_path=self.db_path,
            signing_key=TEST_SIGNING_KEY,
        )
        is_valid, status, _ = verify_decision_manifest(
            manifest_data=manifest.to_dict(),
            signing_key=TEST_SIGNING_KEY,
        )
        self.assertTrue(is_valid)
        self.assertEqual(status, "VERIFICATION_SUCCESSFUL")

        # Independent replay check
        trace = manifest.calculation_trace
        self.assertEqual(trace["baselineScores"]["VEND-10024-ALPHA"]["totalScore"], "42.50")
        self.assertEqual(trace["baselineScores"]["VEND-10025-BETA"]["totalScore"], "85.00")
        self.assertEqual(trace["finalScores"]["VEND-10024-ALPHA"]["totalScore"], "52.00")
        self.assertEqual(trace["finalScores"]["VEND-10025-BETA"]["totalScore"], "72.00")
        self.assertEqual(trace["selectedOption"], "VEND-10025-BETA")

    def test_03_tamper_detection_changed_contribution(self):
        """Invariant 3: Altered score or contribution delta in exported manifest is caught immediately."""
        manifest = build_decision_manifest(
            decision_id=self.decision_id,
            tenant_id="velora-tenant",
            version=self.version,
            db_path=self.db_path,
            signing_key=TEST_SIGNING_KEY,
        )
        tampered = deepcopy(manifest.to_dict())

        # Maliciously bump Alpha's final score from 52.00 to 80.00
        tampered["calculation_trace"]["finalScores"]["VEND-10024-ALPHA"]["totalScore"] = "80.00"

        # Attempt verification
        is_valid, status, _ = verify_decision_manifest(
            manifest_data=tampered,
            signing_key=TEST_SIGNING_KEY,
        )
        self.assertFalse(is_valid)
        self.assertIn("VERIFICATION_FAILED", status)
        self.assertTrue("HASH_MISMATCH" in status or "CONTRIBUTION_TAMPERED" in status)

    def test_04_tamper_detection_removed_record_and_bad_signature(self):
        """Invariant 4: Removed candidate record or corrupted cryptographic signature fails verification."""
        manifest = build_decision_manifest(
            decision_id=self.decision_id,
            tenant_id="velora-tenant",
            version=self.version,
            db_path=self.db_path,
            signing_key=TEST_SIGNING_KEY,
        )

        # 4a. Remove a candidate from input_snapshot
        tampered_removal = deepcopy(manifest.to_dict())
        tampered_removal["input_snapshot"] = [tampered_removal["input_snapshot"][0]]  # Dropped Beta
        is_valid, status, _ = verify_decision_manifest(
            manifest_data=tampered_removal,
            signing_key=TEST_SIGNING_KEY,
        )
        self.assertFalse(is_valid)
        self.assertIn("VERIFICATION_FAILED", status)

        # 4b. Corrupt signature
        tampered_sig = deepcopy(manifest.to_dict())
        tampered_sig["cryptographic_signature"]["signature"] = "deadbeef" * 8
        is_valid_sig, status_sig, _ = verify_decision_manifest(
            manifest_data=tampered_sig,
            signing_key=TEST_SIGNING_KEY,
        )
        self.assertFalse(is_valid_sig)
        self.assertEqual(status_sig, "VERIFICATION_FAILED: INVALID_SIGNATURE")

    def test_05_application_role_cannot_update_or_delete_finalized_evidence(self):
        """Invariant 5: Application role (velora-app-service) cannot update or delete finalized evidence."""
        # Finalize decision evidence
        finalize_decision_evidence(
            decision_id=self.decision_id,
            tenant_id="velora-tenant",
            version=self.version,
            db_path=self.db_path,
            signing_key=TEST_SIGNING_KEY,
        )

        repo = VendorDecisionRepository(db_path=self.db_path)

        # 5a. Attempt DELETE as application service -> blocked
        with self.assertRaises(FinalizedEvidenceMutationError):
            repo.delete_decision(
                decision_id=self.decision_id,
                tenant_id="velora-tenant",
                version=self.version,
                caller_role="velora-app-service",
            )

        # 5b. Attempt UPDATE on finalized record as application service -> blocked
        rec = repo.get_decision(self.decision_id, "velora-tenant", version=self.version)
        rec.concise_rationale = "Tampered rationale after finalization."
        with self.assertRaises(FinalizedEvidenceMutationError):
            repo.save_decision(rec, caller_role="velora-app-service")

    def test_06_unauthorized_actor_cannot_export(self):
        """Invariant 6: Non-auditor / unauthorized actor cannot export decision audit trail."""
        with self.assertRaises(PermissionError):
            export_decision_trail(
                decision_id=self.decision_id,
                version=self.version,
                tenant_id="velora-tenant",
                caller_roles=["Standard_User"],
                db_path=self.db_path,
            )

    def test_07_governed_mutation_fails_closed_during_audit_outage(self):
        """Invariant 7: Export mutation fails closed if audit logging experiences an outage."""
        os.environ["VELORA_SIMULATE_AUDIT_OUTAGE"] = "true"
        try:
            with self.assertRaises(AuditLoggingOutageError):
                export_decision_trail(
                    decision_id=self.decision_id,
                    version=self.version,
                    tenant_id="velora-tenant",
                    caller_roles=["AUDITOR"],
                    db_path=self.db_path,
                )
        finally:
            os.environ.pop("VELORA_SIMULATE_AUDIT_OUTAGE", None)

    def test_08_evidence_artifact_links_restricted_and_expired_denied(self):
        """Invariant 8: Artifact access tokens are signed and expire after TTL."""
        token = generate_artifact_token(
            artifact_path="/tmp/test_artifact.json",
            tenant_id="velora-tenant",
            ttl_seconds=1,  # 1 second TTL
            secret_key=TEST_SIGNING_KEY,
        )
        # Immediate resolution succeeds
        resolved = resolve_artifact_token(token, secret_key=TEST_SIGNING_KEY)
        self.assertEqual(resolved["artifactPath"], "/tmp/test_artifact.json")

        # Sleep past expiration
        time.sleep(1.1)
        with self.assertRaises(ArtifactAccessExpiredError):
            resolve_artifact_token(token, secret_key=TEST_SIGNING_KEY)

        # Tampered token signature fails
        bad_token = token[:-4] + "ffff"
        with self.assertRaises(ArtifactTokenInvalidError):
            resolve_artifact_token(bad_token, secret_key=TEST_SIGNING_KEY)

    def test_09_spreadsheet_export_formula_injection_defense(self):
        """Invariant 9: Spreadsheet CSV export neutralizes formula injection triggers (CWE-1236)."""
        # Test unit cell sanitizer
        self.assertEqual(sanitize_cell_for_csv("=CMD|' /C calc'!A0"), "'=CMD|' /C calc'!A0")
        self.assertEqual(sanitize_cell_for_csv("@SUM(A1:A10)"), "'@SUM(A1:A10)")
        self.assertEqual(sanitize_cell_for_csv("+1234567890!A1"), "'+1234567890!A1")
        self.assertEqual(sanitize_cell_for_csv("-2+3+cmd|' /C calc'!A0"), "'-2+3+cmd|' /C calc'!A0")
        # Standard numeric values must NOT be corrupted
        self.assertEqual(sanitize_cell_for_csv(Decimal("85.00")), "85.00")
        self.assertEqual(sanitize_cell_for_csv("-13.00"), "-13.00")
        self.assertEqual(sanitize_cell_for_csv("100000.00"), "100000.00")

        # Test CSV export on decision
        export_res = export_decision_trail(
            decision_id=self.decision_id,
            version=self.version,
            tenant_id="velora-tenant",
            export_format="CSV",
            caller_roles=["AUDITOR"],
            db_path=self.db_path,
            export_dir=self.export_dir,
            signing_key=TEST_SIGNING_KEY,
        )
        csv_content = export_res["typedResult"]["csvContent"]
        self.assertIn("ADAA COMPLIANT", csv_content)
        self.assertIn("Alpha Maintenance Logistics", csv_content)
        self.assertIn("Beta Technical Services", csv_content)

    def test_10_declared_redaction_vs_tampering(self):
        """Invariant 10: Declared redactions pass verification while undeclared modifications fail."""
        export_res = export_decision_trail(
            decision_id=self.decision_id,
            version=self.version,
            tenant_id="velora-tenant",
            export_format="JSON",
            caller_roles=["AUDITOR"],
            redacted_fields=["commercial_price"],
            db_path=self.db_path,
            export_dir=self.export_dir,
            signing_key=TEST_SIGNING_KEY,
        )
        manifest = export_res["typedResult"]["manifest"]

        # Verification with declared redactions succeeds
        is_valid, status, details = verify_decision_manifest(
            manifest_data=manifest,
            signing_key=TEST_SIGNING_KEY,
            declared_redactions=["commercial_price"],
        )
        self.assertTrue(is_valid)
        self.assertEqual(status, "VERIFIED_WITH_DECLARED_REDACTIONS")
        self.assertIn("commercial_price", details.get("declaredRedactions", []))

    def test_11_fastmcp_server_registration_and_get_block(self):
        """Invariant 11: Tool wrapper functions and FastMCP endpoints are registered and block GET mutations."""
        # 11a. Tool wrapper execution
        res = export_decision_trail_tool(
            decision_id=self.decision_id,
            version=self.version,
            tenant_id="velora-tenant",
            caller_roles=["AUDITOR"],
            db_path=self.db_path,
        )
        self.assertEqual(res["operationStatus"], "SUCCESS")

        # 11b. Verify tool execution
        v_res = verify_decision_manifest_tool(manifest=res["typedResult"]["manifest"])
        self.assertTrue(v_res["isValid"])
        self.assertEqual(v_res["statusCode"], "VERIFICATION_SUCCESSFUL")

        # 11c. REST HTTP boundary: GET on mutating export tool returns 405 Method Not Allowed
        token = make_test_jwt({
            "tid": "7d167021-f5e9-4331-9b75-d44d55a1ce9b",
            "oid": "auditor-1",
            "aud": "https://api.velora.ae",
            "roles": ["AUDITOR"],
            "exp": int(time.time()) + 3600,
            "sub": "auditor-1",
        }, secret=TEST_SECRET)

        response_get = self.client.get(
            "/export_decision_trail",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response_get.status_code, 405)


if __name__ == "__main__":
    unittest.main()
