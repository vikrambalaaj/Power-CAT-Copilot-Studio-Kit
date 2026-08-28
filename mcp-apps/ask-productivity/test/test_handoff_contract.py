"""Integration tests for Parent Velora Agent to Connected Productivity Agent Handoff Contract."""
import asyncio
import unittest

from productivity_mcp.models import HandoffRequest
from productivity_mcp.server import handle_parent_handoff
from productivity_mcp.dataverse_audit import get_dataverse_client


class TestHandoffContract(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        get_dataverse_client().clear_all_for_testing()

    async def test_parent_email_prepare_and_execution_handoff(self):
        """Test full handoff sequence for Section 13 contract example."""
        # 1. Parent initiates PREPARE_EMAIL
        parent_req = HandoffRequest(
            task="Prepare an email to the Finance leadership team",
            operation="PREPARE_EMAIL",
            rootCorrelationId="corr-parent-root-12345",
            conversationId="parent-conv-999",
            turnId="parent-turn-1",
            userObjectId="entra-user-001",
            userEmail="balaadm@velora.ae",
            userTimezone="Asia/Dubai",
            channel="Microsoft365Copilot",
            dataClassification="CONFIDENTIAL",
            parameters={
                "recipientNames": ["Finance leadership team"],
                "subject": "Receivables follow-up",
                "bodySource": "Approved S/4HANA summary"
            }
        )

        resp1 = await handle_parent_handoff(parent_req)
        self.assertEqual(resp1.status, "PREVIEW_READY")
        self.assertTrue(resp1.approvalRequired)
        self.assertEqual(resp1.correlationId, "corr-parent-root-12345")
        self.assertIsNotNone(resp1.confirmationToken)
        self.assertIn("financeleadership@velora.ae", resp1.previewDetails["to"])

        # 2. Executive approves in Parent UX -> Parent calls child with confirmationToken
        exec_req = HandoffRequest(
            task="Execute confirmed email dispatch",
            operation="SEND_APPROVED_EMAIL",
            rootCorrelationId="corr-parent-root-12345",
            conversationId="parent-conv-999",
            turnId="parent-turn-2",
            userObjectId="entra-user-001",
            userEmail="balaadm@velora.ae",
            parameters={
                "confirmationToken": resp1.confirmationToken,
                "previewDetails": resp1.previewDetails,
            }
        )

        resp2 = await handle_parent_handoff(exec_req)
        self.assertEqual(resp2.status, "SUCCESS")
        self.assertFalse(resp2.approvalRequired)
        self.assertEqual(resp2.correlationId, "corr-parent-root-12345")
        self.assertTrue(resp2.structuredResult["externalObjectId"].startswith("MS-MSG-"))

    async def test_parent_search_mail_read_handoff(self):
        """Test read delegation handoff contract."""
        read_req = HandoffRequest(
            task="Find priority emails for executive",
            operation="SEARCH_MAIL",
            rootCorrelationId="corr-parent-read-001",
            conversationId="parent-conv-888",
            turnId="parent-turn-1",
            userObjectId="entra-user-001",
            userEmail="balaadm@velora.ae",
            parameters={"query": "headcount", "maximumResults": 5}
        )

        resp = await handle_parent_handoff(read_req)
        self.assertEqual(resp.status, "SUCCESS")
        self.assertFalse(resp.approvalRequired)
        self.assertEqual(resp.correlationId, "corr-parent-read-001")
        self.assertGreaterEqual(len(resp.structuredResult), 1)


if __name__ == "__main__":
    unittest.main()
