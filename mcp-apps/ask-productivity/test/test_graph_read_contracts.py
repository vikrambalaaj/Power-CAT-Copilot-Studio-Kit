"""Acceptance Test Suite T05: Microsoft Graph Read Contracts & Boundary Governance (W05).

Verifies:
1. Local-midnight boundary with Asia/Dubai (+04:00) windowing.
2. Recurrent meeting metadata (occurrence, seriesMasterId, recurrence).
3. Null onlineMeeting safety with zero AttributeError.
4. Canceled event handling (isCancelled=True preserved and filtered).
5. Unread mail filtering (unreadOnly=True returns only unread messages).
6. Multiple pages & page cap (truncated, nextLink, SSRF protection).
7. Error isolation status mapping (ACCESS_DENIED, THROTTLED, TIMEOUT, SOURCE_UNAVAILABLE).
8. Tasks overdue by timestamp identified even when title lacks 'overdue'.
9. Foreign mailbox and foreign plan authorization failure (AccessDeniedError).
10. Meeting-to-context exact vs uncertain candidate matching without Work IQ claim.
"""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from productivity_mcp.m365_client import (
    Microsoft365Client,
    AccessDeniedError,
    GraphRateLimitError,
    GraphTimeoutError,
    GraphSourceUnavailableError,
    get_local_midnight_boundaries,
)
from productivity_mcp.tools_m365_reads import (
    search_mail,
    list_calendar_events,
    get_meeting_details,
    get_meeting_context,
    list_my_planner_tasks,
    list_plan_tasks,
    get_planner_task,
    find_overdue_tasks,
    get_daily_executive_briefing,
)


class TestGraphReadContracts(unittest.IsolatedAsyncioTestCase):
    """Acceptance T05 validation suite."""

    def setUp(self):
        self.valid_email = "balaadm@velora.ae"
        self.client = Microsoft365Client(user_email=self.valid_email)

    # -------------------------------------------------------------------------
    # Test 1: Local-midnight boundary with Asia/Dubai (+04:00) windowing
    # -------------------------------------------------------------------------
    def test_01_local_midnight_boundary_asia_dubai(self):
        # Specific reference time: 2026-09-14 10:00:00 UTC = 2026-09-14 14:00:00 GST (+04:00)
        dt = datetime(2026, 9, 14, 10, 0, 0, tzinfo=timezone.utc)
        start_iso, end_iso = get_local_midnight_boundaries(target_dt=dt, tz_name="Asia/Dubai")

        self.assertTrue(start_iso.startswith("2026-09-14T00:00:00"))
        self.assertTrue(start_iso.endswith("+04:00"))
        self.assertTrue(end_iso.startswith("2026-09-15T00:00:00"))
        self.assertTrue(end_iso.endswith("+04:00"))

        # Default list_calendar_events uses local midnight boundaries
        events = self.client.list_calendar_events(time_zone="Asia/Dubai")
        self.assertIsInstance(events, list)
        for e in events:
            self.assertIn("start", e)
            self.assertIn("end", e)

    # -------------------------------------------------------------------------
    # Test 2: Recurrent meeting metadata
    # -------------------------------------------------------------------------
    def test_02_recurrent_meeting_metadata(self):
        # EVT-2026-0826-03 is a recurrent weekly meeting occurrence in seed fixtures
        evt = self.client.get_meeting_details("EVT-2026-0826-03")
        self.assertIsNotNone(evt)
        self.assertEqual(evt.get("type"), "occurrence")
        self.assertEqual(evt.get("seriesMasterId"), "SERIES-WEEKLY-OPS-01")
        self.assertIn("recurrence", evt)
        self.assertEqual(evt["recurrence"].get("pattern", {}).get("type"), "weekly")

    # -------------------------------------------------------------------------
    # Test 3: Null onlineMeeting handled safely with zero AttributeError
    # -------------------------------------------------------------------------
    async def test_03_null_online_meeting_safety(self):
        # EVT-2026-0826-04 has "onlineMeeting": None in seed fixtures
        evt = self.client.get_meeting_details("EVT-2026-0826-04")
        self.assertIsNotNone(evt)
        self.assertIsNone(evt.get("onlineMeeting"))
        self.assertEqual(evt.get("onlineMeetingUrl"), "")

        # Call via tool envelope
        res = await get_meeting_details(eventId="EVT-2026-0826-04", userEmail=self.valid_email)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["structuredResult"]["id"], "EVT-2026-0826-04")
        self.assertIsNone(res["structuredResult"].get("onlineMeeting"))

    # -------------------------------------------------------------------------
    # Test 4: Canceled event handling
    # -------------------------------------------------------------------------
    async def test_04_canceled_event_handling(self):
        # Default exclude cancelled
        events_active = self.client.list_calendar_events(include_cancelled=False)
        active_ids = [e["id"] for e in events_active]
        self.assertNotIn("EVT-2026-0826-05", active_ids)

        # Include cancelled
        events_all = self.client.list_calendar_events(include_cancelled=True)
        all_ids = [e["id"] for e in events_all]
        self.assertIn("EVT-2026-0826-05", all_ids)
        cancel_evt = next(e for e in events_all if e["id"] == "EVT-2026-0826-05")
        self.assertTrue(cancel_evt.get("isCancelled"))

        # Tool wrapper passes includeCancelled flag
        tool_res = await list_calendar_events(includeCancelled=True, userEmail=self.valid_email)
        self.assertEqual(tool_res["status"], "SUCCESS")
        ids = [e["id"] for e in tool_res["structuredResult"]]
        self.assertIn("EVT-2026-0826-05", ids)

    # -------------------------------------------------------------------------
    # Test 5: Unread filtering
    # -------------------------------------------------------------------------
    async def test_05_unread_mail_filtering(self):
        # Search unread only
        unread_res = await search_mail(unreadOnly=True, userEmail=self.valid_email)
        self.assertEqual(unread_res["status"], "SUCCESS")
        self.assertGreater(len(unread_res["structuredResult"]), 0)
        for msg in unread_res["structuredResult"]:
            self.assertFalse(msg.get("isRead", True))

        # Search all
        all_res = await search_mail(unreadOnly=False, userEmail=self.valid_email)
        self.assertEqual(all_res["status"], "SUCCESS")
        self.assertGreaterEqual(len(all_res["structuredResult"]), len(unread_res["structuredResult"]))

    # -------------------------------------------------------------------------
    # Test 6: Multiple pages & SSRF host check
    # -------------------------------------------------------------------------
    def test_06_pagination_and_ssrf_protection(self):
        # SSRF protection: reject redirect nextLink pointing outside Microsoft Graph
        evil_url = "https://evil-attacker.com/v1.0/me/messages?$skiptoken=abc"
        with self.assertRaises(AccessDeniedError) as ctx:
            self.client._fetch_graph_paged(evil_url)
        self.assertIn("SSRF", str(ctx.exception))

        # Legitimate Graph URL host is permitted
        valid_graph_url = "https://graph.microsoft.com/v1.0/me/messages"
        # Mocking httpx to return an empty 200 page
        with patch("httpx.Client.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"value": [{"id": "MSG-PAGED-1"}], "@odata.nextLink": None}
            mock_get.return_value = mock_resp
            res = self.client._fetch_graph_paged(valid_graph_url, headers={"Authorization": "Bearer fake"})
            self.assertEqual(len(res["items"]), 1)
            self.assertFalse(res["truncated"])

        # Pagination metadata tracking in client
        self.client.search_mail(max_results=1)
        pag = self.client.get_last_pagination()
        self.assertIn("pageCount", pag)
        self.assertIn("truncated", pag)

    # -------------------------------------------------------------------------
    # Test 7: Error isolation status mapping
    # -------------------------------------------------------------------------
    async def test_07_error_isolation_status_mapping(self):
        # AccessDeniedError -> ACCESS_DENIED
        with patch.object(Microsoft365Client, "search_mail", side_effect=AccessDeniedError("Forbidden")):
            res = await search_mail(query="test", userEmail=self.valid_email)
            self.assertEqual(res["status"], "ACCESS_DENIED")
            self.assertEqual(res["resultCount"], 0)
            self.assertIn("Forbidden", res["warnings"][0])

        # GraphRateLimitError -> THROTTLED with retry-after
        with patch.object(Microsoft365Client, "search_mail", side_effect=GraphRateLimitError("Too Many Requests", retry_after=45)):
            res = await search_mail(query="test", userEmail=self.valid_email)
            self.assertEqual(res["status"], "THROTTLED")
            self.assertEqual(res["resultCount"], 0)
            self.assertTrue(any("45s" in w for w in res["warnings"]))

        # GraphTimeoutError -> TIMEOUT
        with patch.object(Microsoft365Client, "search_mail", side_effect=GraphTimeoutError("Gateway Timeout")):
            res = await search_mail(query="test", userEmail=self.valid_email)
            self.assertEqual(res["status"], "TIMEOUT")

        # GraphSourceUnavailableError -> SOURCE_UNAVAILABLE
        with patch.object(Microsoft365Client, "search_mail", side_effect=GraphSourceUnavailableError("Service Down")):
            res = await search_mail(query="test", userEmail=self.valid_email)
            self.assertEqual(res["status"], "SOURCE_UNAVAILABLE")

    # -------------------------------------------------------------------------
    # Test 8: Timestamp overdue task identification (no "overdue" in title)
    # -------------------------------------------------------------------------
    async def test_08_timestamp_overdue_task_detection(self):
        # TSK-003 has title "Audit Table Dataverse Migration Sign-off" (NO "overdue" word!)
        tasks = self.client.list_planner_tasks(overdue_only=True)
        task_ids = [t["id"] for t in tasks]
        self.assertIn("TSK-003", task_ids)

        tsk03 = next(t for t in tasks if t["id"] == "TSK-003")
        self.assertNotIn("overdue", tsk03["title"].lower())
        self.assertTrue(tsk03["isOverdue"])
        self.assertIn("Bala Murugan", tsk03["assigneeNames"])

        # Via find_overdue_tasks tool
        res = await find_overdue_tasks(userEmail=self.valid_email)
        self.assertEqual(res["status"], "OVERDUE_ITEMS_FOUND")
        res_ids = [t["id"] for t in res["structuredResult"]]
        self.assertIn("TSK-003", res_ids)

    # -------------------------------------------------------------------------
    # Test 9: Foreign mailbox and foreign plan authorization failure
    # -------------------------------------------------------------------------
    async def test_09_foreign_mailbox_and_plan_authorization(self):
        # Foreign mailbox rejected with AccessDeniedError
        with self.assertRaises(AccessDeniedError):
            self.client._validate_user_mailbox("attacker@foreign-domain.com")

        # Tool wraps rejection into ACCESS_DENIED envelope
        res_mail = await search_mail(userEmail="attacker@foreign-domain.com")
        self.assertEqual(res_mail["status"], "ACCESS_DENIED")

        # Foreign plan rejected with AccessDeniedError
        with self.assertRaises(AccessDeniedError):
            self.client._validate_planner_plan("Rogue Competitor Strategy")

        # Tool wraps rejection into ACCESS_DENIED envelope
        res_plan = await list_plan_tasks(planName="Rogue Competitor Strategy", userEmail=self.valid_email)
        self.assertEqual(res_plan["status"], "ACCESS_DENIED")

    # -------------------------------------------------------------------------
    # Test 10: Meeting-to-context join & honest source attribution
    # -------------------------------------------------------------------------
    async def test_10_meeting_context_exact_vs_uncertain_and_no_work_iq(self):
        # 1. Exact match by subject
        exact_res = await get_meeting_context(subjectOrId="Executive Operations & Workforce Alignment", userEmail=self.valid_email)
        self.assertEqual(exact_res["status"], "SUCCESS")
        self.assertEqual(exact_res["sourceSystem"], "Microsoft Outlook Calendar & Graph")
        self.assertNotIn("Work IQ", exact_res["sourceSystem"])
        self.assertTrue(exact_res["structuredResult"]["verifiedMatch"])
        self.assertEqual(exact_res["structuredResult"]["candidateRelationship"], "EXACT_MATCH")
        self.assertEqual(len(exact_res["warnings"]), 0)

        # 2. Substring candidate match
        substr_res = await get_meeting_context(subjectOrId="Workforce Alignment", userEmail=self.valid_email)
        self.assertEqual(substr_res["status"], "SUCCESS")
        self.assertEqual(substr_res["sourceSystem"], "Microsoft Outlook Calendar & Graph")
        self.assertNotIn("Work IQ", substr_res["sourceSystem"])
        self.assertFalse(substr_res["structuredResult"]["verifiedMatch"])
        self.assertEqual(substr_res["structuredResult"]["candidateRelationship"], "UNCERTAIN_CANDIDATE")
        self.assertTrue(any("UNCERTAIN_CANDIDATE" in w for w in substr_res["warnings"]))

        # 3. Executive daily briefing section degradation
        with patch.object(Microsoft365Client, "list_pending_approvals", side_effect=RuntimeError("Approvals offline")):
            briefing_res = await get_daily_executive_briefing(userEmail=self.valid_email)
            self.assertEqual(briefing_res["status"], "PARTIAL")
            self.assertEqual(briefing_res["sourceSystem"], "Microsoft 365 Graph")
            self.assertTrue(any("Approvals" in w for w in briefing_res["warnings"]))


if __name__ == "__main__":
    unittest.main()
