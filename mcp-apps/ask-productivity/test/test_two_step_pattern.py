"""Security, Integrity, and Resilience tests for Two-Step Transaction Pattern."""
import asyncio
import time
import unittest

from productivity_mcp.token_manager import TokenManager
from productivity_mcp.tools_m365_writes import prepare_email, send_approved_email
from productivity_mcp.dataverse_audit import get_dataverse_client


class TestTwoStepSecurityAndIntegrity(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        get_dataverse_client().clear_all_for_testing()

    async def test_modified_preview_checksum_rejection(self):
        """Verify that modifying the preview between Stage A and Stage B is rejected."""
        prep = await prepare_email(
            to=["Ahmed Al Nuaimi"],
            subject="Original Subject",
            body="Original Body",
            userEmail="balaadm@velora.ae",
        )
        token = prep["confirmationToken"]
        preview = dict(prep["previewDetails"])

        # Adversarial tampering: altering body or recipient after preview
        preview["body"] = "TAMPERED BODY: Please wire AED 5,000,000 immediately."

        res = await send_approved_email(
            confirmationToken=token,
            previewDetails=preview,
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(res["status"], "TOKEN_INVALID")
        self.assertIn("Preview data has changed", res["resultSummary"])

    async def test_expired_token_rejection(self):
        """Verify that expired approval tokens cannot execute transactions."""
        token_mgr = TokenManager()
        # Create token that expired 1 minute ago
        token, _ = token_mgr.create_approval_token(
            operation="PREPARE_EMAIL",
            user_object_id="usr-1",
            user_email="balaadm@velora.ae",
            preview_data={"subject": "Test"},
            idempotency_key="idemp-exp-01",
            root_correlation_id="corr-exp-01",
            expiry_minutes=-1,
        )

        res = await send_approved_email(
            confirmationToken=token,
            previewDetails={"subject": "Test"},
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(res["status"], "TOKEN_INVALID")
        self.assertIn("expired", res["resultSummary"].lower())

    async def test_user_identity_binding(self):
        """Verify that User B cannot approve a token issued to User A."""
        prep = await prepare_email(
            to=["Ahmed Al Nuaimi"],
            subject="Executive Confidential",
            body="Confidential notes.",
            userEmail="user_a@velora.ae",
        )
        token = prep["confirmationToken"]
        preview = prep["previewDetails"]

        # Attempt to execute as user_b
        res = await send_approved_email(
            confirmationToken=token,
            previewDetails=preview,
            userEmail="user_b@velora.ae",
        )
        self.assertEqual(res["status"], "TOKEN_INVALID")
        self.assertIn("User identity mismatch", res["resultSummary"])

    async def test_forged_token_signature_rejection(self):
        """Verify that forged tokens are rejected."""
        fake_token = "velora_appr.eyJvcCI6ICJQUkVQQVJFX0VNQUlMIiwgInVlbSI6ICJiYWxhYWRtQHZlbG9yYS5hZSJ9.fakeSig12345"
        res = await send_approved_email(
            confirmationToken=fake_token,
            previewDetails={"to": ["ahmed.nuaimi@velora.ae"]},
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(res["status"], "TOKEN_INVALID")

    async def test_fail_closed_blocking_during_execution(self):
        """Verify that if Dataverse goes offline between Stage A and Stage B, write is aborted."""
        prep = await prepare_email(
            to=["Ahmed Al Nuaimi"],
            subject="Test Subject",
            body="Test Body",
            userEmail="balaadm@velora.ae",
        )
        token = prep["confirmationToken"]
        preview = prep["previewDetails"]

        # Simulate Dataverse outage
        dv_client = get_dataverse_client()
        dv_client.simulate_down = True

        res = await send_approved_email(
            confirmationToken=token,
            previewDetails=preview,
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(res["status"], "FAIL_CLOSED_BLOCKED")
        self.assertIn("Fail-closed write policy", res["warnings"][0])


if __name__ == "__main__":
    unittest.main()
