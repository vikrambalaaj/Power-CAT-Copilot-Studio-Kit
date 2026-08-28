"""Unit tests for Executive Daily Briefing tools and email dispatch."""
import asyncio
import unittest

from productivity_mcp.dataverse_audit import get_dataverse_client
from productivity_mcp.m365_client import Microsoft365Client
from productivity_mcp.tools_m365_reads import get_daily_executive_briefing
from productivity_mcp.tools_m365_writes import (
    prepare_daily_briefing_email,
    send_approved_daily_briefing_email,
    send_daily_briefing_email,
)


class TestDailyBriefing(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        get_dataverse_client().clear_all_for_testing()

    def test_m365_client_get_daily_briefing(self):
        client = Microsoft365Client(user_email="balaadm@velora.ae")
        briefing = client.get_daily_briefing()

        self.assertIn("date", briefing)
        self.assertEqual(briefing["executive_email"], "balaadm@velora.ae")
        self.assertGreaterEqual(len(briefing["meetings_today"]), 2)
        self.assertGreaterEqual(len(briefing["tasks_to_do"]), 3)
        self.assertGreaterEqual(len(briefing["upcoming_approvals"]), 3)
        self.assertGreaterEqual(len(briefing["teams_activity"]), 3)
        self.assertIn("Meetings Today", briefing["summary_text"])

    def test_m365_client_generate_html_email(self):
        client = Microsoft365Client(user_email="balaadm@velora.ae")
        briefing = client.get_daily_briefing()
        html = client.generate_daily_briefing_html(briefing)

        self.assertIn("Executive Daily Briefing", html)
        self.assertIn("Executive Operations & Workforce Alignment", html)
        self.assertIn("Upcoming Approvals Requiring Sign-Off", html)
        self.assertIn("cre2f_veloraagentauditlog", html)

    async def test_get_daily_executive_briefing_tool(self):
        res = await get_daily_executive_briefing(userEmail="balaadm@velora.ae")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("Executive Daily Briefing", res["resultSummary"])
        self.assertIn("meetings_today", res["structuredResult"])
        self.assertIn("tasks_to_do", res["structuredResult"])
        self.assertIn("upcoming_approvals", res["structuredResult"])
        self.assertGreaterEqual(res["resultCount"], 2)

    async def test_daily_briefing_two_step_email_lifecycle(self):
        # Stage A: Prepare
        prep = await prepare_daily_briefing_email(userEmail="balaadm@velora.ae")
        self.assertEqual(prep["status"], "PREVIEW_READY")
        self.assertTrue(prep["approvalRequired"])
        self.assertTrue(prep["confirmationToken"].startswith("velora_appr."))
        self.assertIn("Daily Briefing email preview compiled", prep["resultSummary"])

        # Stage B: Execute
        token = prep["confirmationToken"]
        send_res = await send_approved_daily_briefing_email(
            confirmationToken=token,
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(send_res["status"], "SUCCESS")
        self.assertIn("Daily Briefing email successfully delivered", send_res["resultSummary"])
        self.assertTrue(send_res["externalObjectId"].startswith("MS-MSG-"))

    async def test_send_daily_briefing_email_direct(self):
        send_res = await send_daily_briefing_email(userEmail="balaadm@velora.ae")
        self.assertEqual(send_res["status"], "SUCCESS")
        self.assertIn("Daily Briefing email successfully delivered", send_res["resultSummary"])


if __name__ == "__main__":
    unittest.main()
