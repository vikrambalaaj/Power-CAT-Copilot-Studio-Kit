"""Unit and Acceptance Test Suite for Work Package W09 (Per-Recommendation Feedback).

Validates Acceptance Criteria T09:
1. Useful and Not-Useful Feedback Persistence.
2. Double-Click Idempotency (no duplicate entries, returns ALREADY_COMMITTED).
3. Impersonation Prevention (rejects conflicting body reviewer).
4. Strict Tenant Boundary Isolation (cross-tenant submission blocked).
5. Original Recommendation Immutability (metrics, claims, and status unmutated).
6. Separation of Lifecycle Actions (status remains ACTIVE, not mutated to dismissed).
7. Fail-Closed Persistence & Readback Verification.
8. Allowlist Validation & Comment Length Bounds (<= 1000 chars).
9. Rule-Level Aggregation Statistics (human review required, no automated tuning).
10. Parent Handoff Router Integration.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict

from productivity_mcp.business_repository import (
    RecommendationEntityRecord,
    RecommendationFeedbackRepository,
    SqliteBusinessRepository,
    get_business_repository_client,
    reset_business_repository_for_testing,
)
from productivity_mcp.feedback_service import (
    ALLOWED_FEEDBACK_TYPES,
    FeedbackAccessDeniedError,
    FeedbackNotFoundError,
    FeedbackPersistenceError,
    FeedbackValidationError,
    get_recommendation_feedback,
    get_rule_feedback_summary,
    list_feedback_for_recommendation,
    record_recommendation_feedback,
)
from productivity_mcp.models import HandoffRequest
from productivity_mcp.server import handle_parent_handoff
from shared_mcp.identity import VerifiedIdentity


class TestRecommendationFeedbackAcceptance(unittest.TestCase):
    def setUp(self):
        reset_business_repository_for_testing()
        self.test_dir = tempfile.mkdtemp(prefix="velora_test_feedback_")
        self.db_path = os.path.join(self.test_dir, "business_repo.db")
        os.environ["VELORA_BUSINESS_REPO_DB"] = self.db_path
        os.environ["ALLOW_OFFLINE_TEST_TOKENS"] = "1"
        self.repo = SqliteBusinessRepository(db_path=self.db_path)
        self.fb_repo = RecommendationFeedbackRepository(db_path=self.db_path)

        # Seed an active test recommendation
        self.test_rec = RecommendationEntityRecord(
            recommendation_id="REC-TEST-OVERDUE-001",
            tenant_id="velora-tenant",
            rec_id="REC-TEST-OVERDUE-001",
            rule_code="REC-AR-OVERDUE-90D",
            rule_version="1.0.0",
            kpi_code="AR_OVERDUE_90D",
            organization_scope="1000",
            category="WORKING_CAPITAL",
            observed_value=Decimal("4500000.00"),
            threshold=Decimal("3000000.00"),
            impact="Overdue receivables >90d exceed threshold by 1.5M USD",
            explanation="Customer payment delay in plant 1000",
            suggested_action="Initiate executive escalation and credit hold",
            confidence="HIGH",
            confidence_reason="100% verified OData snapshot from S4HANA",
            first_detected="2026-09-14T08:00:00Z",
            last_detected="2026-09-14T08:00:00Z",
            status="ACTIVE",
            duplicate_key="rec:velora-tenant:REC-AR-OVERDUE-90D:1000:ep1",
            snapshot_id="SNAP-AR-001",
            version=1,
        )
        self.repo.save_recommendation(self.test_rec)

    def tearDown(self):
        reset_business_repository_for_testing()
        os.environ.pop("VELORA_BUSINESS_REPO_DB", None)
        os.environ.pop("ALLOW_OFFLINE_TEST_TOKENS", None)
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_record_useful_feedback_persistence_and_readback(self):
        """Verify successful persistence and readback of useful recommendation feedback."""
        res = asyncio.run(
            record_recommendation_feedback(
                recommendation_id="REC-TEST-OVERDUE-001",
                is_useful=True,
                feedback_type="TIMELY_AND_ACCURATE",
                comment="Critical catch for plant 1000 cash collection.",
                idempotency_key="key-useful-001",
                user_email="cfo@velora.ae",
                user_object_id="user-cfo-123",
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
        self.assertEqual(res["status"], "PERSISTED")
        self.assertEqual(res["recommendationId"], "REC-TEST-OVERDUE-001")
        self.assertEqual(res["reviewer"], "cfo@velora.ae")
        self.assertTrue(res["isUseful"])
        self.assertEqual(res["feedbackType"], "TIMELY_AND_ACCURATE")
        self.assertFalse(res["isDuplicate"])

        # Readback directly from DB
        fb = self.repo.get_recommendation_feedback(res["feedbackId"], "velora-tenant")
        self.assertIsNotNone(fb)
        self.assertEqual(fb.reviewer, "cfo@velora.ae")
        self.assertTrue(fb.is_useful)
        self.assertEqual(fb.comment, "Critical catch for plant 1000 cash collection.")

    def test_02_record_not_useful_feedback_persistence(self):
        """Verify recording not-useful feedback with reason code."""
        res = asyncio.run(
            record_recommendation_feedback(
                recommendation_id="REC-TEST-OVERDUE-001",
                is_useful=False,
                feedback_type="FALSE_POSITIVE",
                comment="Customer wire already cleared in S4 cash desk.",
                idempotency_key="key-notuseful-001",
                user_email="treasurer@velora.ae",
                user_object_id="user-treasurer-456",
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
        self.assertEqual(res["status"], "PERSISTED")
        self.assertFalse(res["isUseful"])
        self.assertEqual(res["feedbackType"], "FALSE_POSITIVE")

        # Query helper
        fb_list = list_feedback_for_recommendation("REC-TEST-OVERDUE-001", "velora-tenant", db_path=self.db_path)
        self.assertEqual(len(fb_list), 1)
        self.assertFalse(fb_list[0]["isUseful"])
        self.assertEqual(fb_list[0]["feedbackType"], "FALSE_POSITIVE")

    def test_03_double_click_idempotency(self):
        """Verify double-click feedback submission returns ALREADY_COMMITTED with zero duplicate records."""
        # First call
        res1 = asyncio.run(
            record_recommendation_feedback(
                recommendation_id="REC-TEST-OVERDUE-001",
                is_useful=True,
                feedback_type="ACTIONABLE",
                comment="Escalating right away.",
                idempotency_key="double-click-token-999",
                user_email="vp.finance@velora.ae",
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
        self.assertEqual(res1["status"], "PERSISTED")
        self.assertFalse(res1["isDuplicate"])

        # Second call with exact same idempotency key
        res2 = asyncio.run(
            record_recommendation_feedback(
                recommendation_id="REC-TEST-OVERDUE-001",
                is_useful=True,
                feedback_type="ACTIONABLE",
                comment="Escalating right away.",
                idempotency_key="double-click-token-999",
                user_email="vp.finance@velora.ae",
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
        self.assertEqual(res2["status"], "ALREADY_COMMITTED")
        self.assertTrue(res2["isDuplicate"])
        self.assertEqual(res1["feedbackId"], res2["feedbackId"])

        # Ensure only 1 record exists in repository
        all_fb = list_feedback_for_recommendation("REC-TEST-OVERDUE-001", "velora-tenant", db_path=self.db_path)
        self.assertEqual(len(all_fb), 1)

    def test_04_impersonation_prevention(self):
        """Verify body-supplied reviewer override is strictly rejected when it conflicts with authenticated identity."""
        with self.assertRaises(FeedbackAccessDeniedError) as ctx:
            asyncio.run(
                record_recommendation_feedback(
                    recommendation_id="REC-TEST-OVERDUE-001",
                    is_useful=True,
                    feedback_type="TIMELY_AND_ACCURATE",
                    comment="Attempting impersonation",
                    user_email="legitimate.user@velora.ae",
                    body_reviewer="executive.cfo@velora.ae",  # Conflicting body reviewer
                    tenant_id="velora-tenant",
                    db_path=self.db_path,
                )
            )
        self.assertIn("Impersonation attempt detected", str(ctx.exception))

    def test_05_cross_tenant_isolation(self):
        """Verify feedback cannot be recorded for a recommendation owned by another tenant."""
        # Create recommendation for Tenant B
        rec_tenant_b = RecommendationEntityRecord(
            recommendation_id="REC-TENANT-B-001",
            tenant_id="tenant-beta",
            rec_id="REC-TENANT-B-001",
            rule_code="REC-AR-OVERDUE-90D",
            rule_version="1.0.0",
            kpi_code="AR_OVERDUE_90D",
            organization_scope="2000",
            category="WORKING_CAPITAL",
            observed_value=Decimal("1000000.00"),
            threshold=Decimal("500000.00"),
            impact="Beta overdue",
            explanation="Beta delay",
            suggested_action="Review",
            confidence="HIGH",
            confidence_reason="Verified",
            first_detected="2026-09-14T08:00:00Z",
            last_detected="2026-09-14T08:00:00Z",
            status="ACTIVE",
            duplicate_key="rec:tenant-beta:REC-AR-OVERDUE-90D:2000:ep1",
            snapshot_id="SNAP-B-001",
            version=1,
        )
        self.repo.save_recommendation(rec_tenant_b)

        # Tenant A caller tries to submit feedback for Tenant B recommendation
        with self.assertRaises(FeedbackAccessDeniedError) as ctx:
            asyncio.run(
                record_recommendation_feedback(
                    recommendation_id="REC-TENANT-B-001",
                    is_useful=True,
                    feedback_type="TIMELY_AND_ACCURATE",
                    user_email="caller@velora.ae",
                    tenant_id="velora-tenant",  # Different tenant
                    db_path=self.db_path,
                )
            )
        self.assertIn("Cross-tenant access violation", str(ctx.exception))

    def test_06_recommendation_immutability(self):
        """Verify recording feedback does NOT mutate the original recommendation, metrics, or claims."""
        initial_rec = self.repo.get_recommendation("REC-TEST-OVERDUE-001", "velora-tenant")
        initial_val = initial_rec.observed_value
        initial_threshold = initial_rec.threshold
        initial_status = initial_rec.status
        initial_confidence = initial_rec.confidence
        initial_impact = initial_rec.impact

        # Submit feedback
        asyncio.run(
            record_recommendation_feedback(
                recommendation_id="REC-TEST-OVERDUE-001",
                is_useful=False,
                feedback_type="IRRELEVANT",
                comment="Not within my scope of operations.",
                user_email="director@velora.ae",
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )

        # Re-fetch recommendation from DB
        after_rec = self.repo.get_recommendation("REC-TEST-OVERDUE-001", "velora-tenant")
        self.assertEqual(after_rec.observed_value, initial_val)
        self.assertEqual(after_rec.threshold, initial_threshold)
        self.assertEqual(after_rec.status, initial_status)
        self.assertEqual(after_rec.confidence, initial_confidence)
        self.assertEqual(after_rec.impact, initial_impact)
        self.assertEqual(after_rec.rule_code, "REC-AR-OVERDUE-90D")

    def test_07_separation_of_lifecycle_actions(self):
        """Verify feedback submission does not alter recommendation lifecycle state (status remains ACTIVE)."""
        self.assertEqual(self.test_rec.status, "ACTIVE")
        asyncio.run(
            record_recommendation_feedback(
                recommendation_id="REC-TEST-OVERDUE-001",
                is_useful=False,
                feedback_type="FALSE_POSITIVE",
                user_email="manager@velora.ae",
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
        rec = self.repo.get_recommendation("REC-TEST-OVERDUE-001", "velora-tenant")
        self.assertEqual(rec.status, "ACTIVE")  # Acknowledge / Dismiss are separate lifecycle actions

    def test_08_allowlist_and_comment_validation(self):
        """Verify feedback_type must be in allowlist and comments cannot exceed 1000 characters."""
        # Invalid feedback type
        with self.assertRaises(FeedbackValidationError) as ctx1:
            asyncio.run(
                record_recommendation_feedback(
                    recommendation_id="REC-TEST-OVERDUE-001",
                    is_useful=True,
                    feedback_type="INVALID_CUSTOM_TYPE",
                    user_email="user@velora.ae",
                    tenant_id="velora-tenant",
                    db_path=self.db_path,
                )
            )
        self.assertIn("Invalid feedback_type", str(ctx1.exception))

        # Comment exceeding 1000 characters
        long_comment = "A" * 1005
        with self.assertRaises(FeedbackValidationError) as ctx2:
            asyncio.run(
                record_recommendation_feedback(
                    recommendation_id="REC-TEST-OVERDUE-001",
                    is_useful=True,
                    feedback_type="TIMELY_AND_ACCURATE",
                    comment=long_comment,
                    user_email="user@velora.ae",
                    tenant_id="velora-tenant",
                    db_path=self.db_path,
                )
            )
        self.assertIn("exceeds maximum allowable length", str(ctx2.exception))

    def test_09_rule_level_aggregation_summary(self):
        """Verify rule-level aggregation statistics without automated retuning."""
        # Add 3 feedbacks for REC-TEST-OVERDUE-001 (rule REC-AR-OVERDUE-90D)
        asyncio.run(
            record_recommendation_feedback(
                recommendation_id="REC-TEST-OVERDUE-001",
                is_useful=True,
                feedback_type="TIMELY_AND_ACCURATE",
                user_email="u1@velora.ae",
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
        asyncio.run(
            record_recommendation_feedback(
                recommendation_id="REC-TEST-OVERDUE-001",
                is_useful=True,
                feedback_type="ACTIONABLE",
                user_email="u2@velora.ae",
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )
        asyncio.run(
            record_recommendation_feedback(
                recommendation_id="REC-TEST-OVERDUE-001",
                is_useful=False,
                feedback_type="INCORRECT_THRESHOLD",
                user_email="u3@velora.ae",
                tenant_id="velora-tenant",
                db_path=self.db_path,
            )
        )

        summary = get_rule_feedback_summary("REC-AR-OVERDUE-90D", "velora-tenant", db_path=self.db_path)
        self.assertEqual(summary["status"], "SUCCESS")
        self.assertEqual(summary["totalFeedback"], 3)
        self.assertEqual(summary["usefulCount"], 2)
        self.assertEqual(summary["notUsefulCount"], 1)
        self.assertEqual(summary["usefulRatio"], 0.6667)
        self.assertEqual(summary["feedbackTypeBreakdown"]["TIMELY_AND_ACCURATE"], 1)
        self.assertEqual(summary["feedbackTypeBreakdown"]["ACTIONABLE"], 1)
        self.assertEqual(summary["feedbackTypeBreakdown"]["INCORRECT_THRESHOLD"], 1)
        self.assertTrue(summary["requiresHumanReview"])
        self.assertFalse(summary["automatedRetuningApplied"])

    def test_10_server_handoff_integration(self):
        """Verify end-to-end handoff invocation for RECORD_RECOMMENDATION_FEEDBACK and GET_RULE_FEEDBACK_SUMMARY."""
        req_record = HandoffRequest(
            task="Submit feedback on AR overdue recommendation",
            operation="RECORD_RECOMMENDATION_FEEDBACK",
            rootCorrelationId="corr-handoff-fb-001",
            conversationId="conv-fb-001",
            turnId="turn-fb-001",
            userObjectId="user-executive-789",
            userEmail="executive@velora.ae",
            tenantId="velora-tenant",
            parameters={
                "recommendationId": "REC-TEST-OVERDUE-001",
                "isUseful": True,
                "feedbackType": "TIMELY_AND_ACCURATE",
                "comment": "Validated with Head of Finance.",
                "idempotencyKey": "handoff-key-789",
            },
        )
        resp_record = asyncio.run(handle_parent_handoff(req_record))
        self.assertEqual(resp_record.status, "PERSISTED")
        self.assertEqual(resp_record.correlationId, "corr-handoff-fb-001")
        self.assertIn("Feedback recorded and verified successfully", resp_record.resultSummary)

        # Query summary via handoff
        req_summary = HandoffRequest(
            task="Get rule feedback statistics",
            operation="GET_RULE_FEEDBACK_SUMMARY",
            rootCorrelationId="corr-handoff-fb-002",
            conversationId="conv-fb-001",
            turnId="turn-fb-002",
            userObjectId="user-executive-789",
            userEmail="executive@velora.ae",
            tenantId="velora-tenant",
            parameters={"ruleCode": "REC-AR-OVERDUE-90D"},
        )
        resp_summary = asyncio.run(handle_parent_handoff(req_summary))
        self.assertEqual(resp_summary.status, "SUCCESS")
        self.assertIn("Feedback summary for rule REC-AR-OVERDUE-90D", resp_summary.resultSummary)
        self.assertEqual(resp_summary.structuredResult["totalFeedback"], 1)


if __name__ == "__main__":
    unittest.main()
