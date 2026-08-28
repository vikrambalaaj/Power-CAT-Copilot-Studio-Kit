"""Unit tests for Microsoft 365 & Work IQ Read Tools (16 tools)."""
import asyncio
import unittest

from productivity_mcp.tools_m365_reads import (
    search_mail,
    get_mail_thread,
    summarize_priority_mail,
    find_mail_follow_ups,
    list_calendar_events,
    get_meeting_details,
    check_availability,
    get_meeting_context,
    search_teams_messages,
    get_channel_context,
    get_chat_context,
    find_teams_follow_ups,
    list_my_planner_tasks,
    list_plan_tasks,
    get_planner_task,
    find_overdue_tasks,
)


class TestM365Reads(unittest.IsolatedAsyncioTestCase):
    # --- Mail Reads ---
    async def test_search_mail(self):
        res = await search_mail(query="headcount", userEmail="balaadm@velora.ae")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertGreaterEqual(res["resultCount"], 1)
        self.assertEqual(res["sourceSystem"], "Microsoft Outlook Mail")
        self.assertIn("correlationId", res)

    async def test_get_mail_thread(self):
        res = await get_mail_thread(threadId="TH-001", userEmail="balaadm@velora.ae")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(len(res["structuredResult"]), 1)

    async def test_summarize_priority_mail(self):
        res = await summarize_priority_mail(maximumResults=5, userEmail="balaadm@velora.ae")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertGreaterEqual(res["resultCount"], 1)

    async def test_find_mail_follow_ups(self):
        res = await find_mail_follow_ups(userEmail="balaadm@velora.ae")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertGreaterEqual(res["resultCount"], 1)

    # --- Calendar Reads ---
    async def test_list_calendar_events(self):
        res = await list_calendar_events(userEmail="balaadm@velora.ae")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertGreaterEqual(res["resultCount"], 2)

    async def test_get_meeting_details(self):
        res = await get_meeting_details(eventId="EVT-2026-0826-01", userEmail="balaadm@velora.ae")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["structuredResult"]["id"], "EVT-2026-0826-01")

    async def test_check_availability(self):
        # Time overlapping with EVT-2026-0826-01 (10:00 - 11:00 UTC)
        res = await check_availability(
            attendees=["balaadm@velora.ae", "ahmed.nuaimi@velora.ae"],
            startTime="2026-08-26T10:30:00Z",
            endTime="2026-08-26T11:30:00Z",
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(res["status"], "CONFLICT_DETECTED")
        self.assertGreaterEqual(len(res["warnings"]), 1)

    async def test_get_meeting_context(self):
        res = await get_meeting_context(subjectOrId="Executive Operations", userEmail="balaadm@velora.ae")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("headcount", res["structuredResult"]["bodyPreview"].lower())

    # --- Teams Reads ---
    async def test_search_teams_messages(self):
        res = await search_teams_messages(query="Emiratisation", userEmail="balaadm@velora.ae")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertGreaterEqual(res["resultCount"], 1)

    async def test_get_channel_context(self):
        res = await get_channel_context(teamName="Executive Leadership Team", channelName="General", userEmail="balaadm@velora.ae")
        self.assertEqual(res["status"], "SUCCESS")

    async def test_get_chat_context(self):
        res = await get_chat_context(chatId="CHAT-EXEC-DIRECT-01", userEmail="balaadm@velora.ae")
        self.assertEqual(res["status"], "SUCCESS")

    async def test_find_teams_follow_ups(self):
        res = await find_teams_follow_ups(userEmail="balaadm@velora.ae")
        self.assertEqual(res["status"], "SUCCESS")

    # --- Planner Reads ---
    async def test_list_my_planner_tasks(self):
        res = await list_my_planner_tasks(userEmail="balaadm@velora.ae")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertGreaterEqual(res["resultCount"], 1)

    async def test_list_plan_tasks(self):
        res = await list_plan_tasks(planName="Executive Strategic Initiatives", userEmail="balaadm@velora.ae")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertGreaterEqual(res["resultCount"], 2)

    async def test_get_planner_task(self):
        res = await get_planner_task(taskId="TSK-001", userEmail="balaadm@velora.ae")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["structuredResult"]["title"], "Finalize Workforce Allocation for Unassigned Headcount")

    async def test_find_overdue_tasks(self):
        res = await find_overdue_tasks(userEmail="balaadm@velora.ae")
        self.assertEqual(res["status"], "OVERDUE_ITEMS_FOUND")
        self.assertGreaterEqual(res["resultCount"], 1)


if __name__ == "__main__":
    unittest.main()
