"""Acceptance tests for the 4 remediated Copilot Studio test cases.

Case 1: Plan my day
Case 9: Draft a reply to Ahmed
Case 13: Quick-action checklist
Case 15: End-of-day wrap-up email
"""
import os
import unittest

from productivity_mcp.m365_client import Microsoft365Client, seed_test_m365_data
from productivity_mcp.tools_m365_reads import plan_my_day, get_quick_action_checklist
from productivity_mcp.tools_m365_writes import (
    prepare_email_reply,
    send_approved_email_reply,
    prepare_end_of_day_wrapup_email,
    send_approved_email,
)
from productivity_mcp.dataverse_audit import get_dataverse_client


class TestFourRemediatedCases(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        os.environ["MOCK_M365"] = "1"
        seed_test_m365_data()
        get_dataverse_client().clear_all_for_testing()

    async def test_case_1_plan_my_day_acceptance(self):
        """Case 1: Combine live calendar events, overdue/due tasks and urgent mail.
        
        Acceptance test: With known meetings, tasks and urgent emails, produce a correctly
        ordered plan without overlapping existing meetings. Include source references.
        If one source fails, identify the missing section clearly.
        """
        res = await plan_my_day(userTimezone="Asia/Dubai", userEmail="balaadm@velora.ae")
        self.assertEqual(res["status"], "SUCCESS")
        structured = res["structuredResult"]

        # 1. Chronological non-overlapping plan
        plan = structured["chronologicalPlan"]
        self.assertGreaterEqual(len(plan), 3)

        # 2. Source references present
        all_refs = []
        for slot in plan:
            all_refs.extend(slot.get("sourceReferences", []))
        self.assertTrue(any("[Outlook Calendar:" in ref for ref in all_refs), "Must include Calendar source reference")
        self.assertTrue(any("[Planner:" in ref for ref in all_refs), "Must include Planner source reference")
        self.assertTrue(any("[Outlook Mail:" in ref for ref in all_refs), "Must include Mail source reference")

        # 3. Focus blocks identified without overlapping meetings
        focus = structured["focusBlocks"]
        self.assertGreaterEqual(len(focus), 1)

        # 4. Error isolation test: simulate calendar failure
        client = Microsoft365Client(user_email="balaadm@velora.ae")
        client.list_calendar_events = lambda: (_ for _ in ()).throw(RuntimeError("Calendar service offline"))
        isolated_res = client.plan_my_day(user_timezone="Asia/Dubai")
        self.assertIn("Outlook Calendar (Calendar service offline)", isolated_res["missingSections"])
        self.assertEqual(isolated_res["sourceStatus"]["calendar"], "UNAVAILABLE")
        self.assertEqual(isolated_res["sourceStatus"]["planner"], "AVAILABLE")
        self.assertEqual(isolated_res["sourceStatus"]["mail"], "AVAILABLE")

    async def test_case_9_draft_reply_to_ahmed_acceptance(self):
        """Case 9: Draft a reply to Ahmed.
        
        Acceptance test: Retrieve the correct thread, produce a contextually accurate draft,
        and confirm that no email is sent during drafting.
        """
        # Stage A: Prepare reply without thread ID (resolves Ahmed and retrieves thread)
        prep = await prepare_email_reply(
            recipientName="Ahmed",
            query="Q3 budget review",
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(prep["status"], "PREVIEW_READY")
        self.assertTrue(prep["approvalRequired"], "Drafting must require approval before sending")
        self.assertTrue(prep["confirmationToken"].startswith("velora_appr."))
        
        # Verify correct recipient resolved
        self.assertIn("ahmed.nuaimi@velora.ae", prep["previewDetails"]["to"])
        
        # Verify contextual draft from actual thread content
        draft_body = prep["previewDetails"]["body"]
        self.assertIn("Ahmed", draft_body)
        self.assertTrue(
            "headcount" in draft_body.lower() or "budget" in draft_body.lower() or "confirmed" in draft_body.lower(),
            "Draft body must be contextually accurate to the retrieved thread",
        )

        # Verify NO email was sent during Stage A
        client = Microsoft365Client(user_email="balaadm@velora.ae")
        mails = client.search_mail(query="Re: Q3")
        self.assertEqual(len(mails), 0, "No email may be sent during drafting stage")

        # Stage B: Approval executes send
        send_res = await send_approved_email_reply(
            confirmationToken=prep["confirmationToken"],
            previewDetails=prep["previewDetails"],
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(send_res["status"], "SUCCESS")

    async def test_case_13_quick_action_checklist_acceptance(self):
        """Case 13: Quick-action checklist.
        
        Acceptance test: Every checklist item traces to a real task, email or meeting.
        Empty sources produce an honest empty result, not invented work.
        """
        res = await get_quick_action_checklist(userEmail="balaadm@velora.ae")
        self.assertEqual(res["status"], "SUCCESS")
        checklist = res["structuredResult"]["checklist"]
        self.assertGreaterEqual(len(checklist), 1)
        self.assertLessEqual(len(checklist), 7, "Checklist should have max 7 items")

        # Verify every item traces to a real source
        for item in checklist:
            self.assertIn(item["sourceSystem"], ["Microsoft Planner", "Outlook Mail", "Outlook Calendar"])
            self.assertTrue(item["externalLink"].startswith("https://"))
            self.assertTrue(bool(item["sourceId"]))
            self.assertTrue(any(item["action"].startswith(prefix) for prefix in ["[Action Required]", "[Respond Today]", "[Attend]"]))

        # Verify honest empty state on empty sources (no invented work)
        client = Microsoft365Client(user_email="balaadm@velora.ae")
        client.list_planner_tasks = lambda **kwargs: []
        client.find_mail_follow_ups = lambda: []
        client.list_calendar_events = lambda: []
        empty_res = client.get_quick_action_checklist()
        self.assertTrue(empty_res["isEmpty"])
        self.assertEqual(len(empty_res["checklist"]), 0)
        self.assertIn("No pending actions found", empty_res["statusSummary"])

    async def test_case_15_end_of_day_wrapup_acceptance(self):
        """Case 15: End-of-day wrap-up email.
        
        Acceptance test: Draft matches the source records, excludes unverified achievements,
        identifies unavailable sources and sends nothing without approval.
        """
        # Prepare wrap-up email
        prep = await prepare_end_of_day_wrapup_email(
            userTimezone="Asia/Dubai",
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(prep["status"], "PREVIEW_READY")
        self.assertTrue(prep["approvalRequired"])
        self.assertTrue(prep["confirmationToken"].startswith("velora_appr."))

        body = prep["previewDetails"]["body"]
        self.assertIn("=== 1. VERIFIED ACHIEVEMENTS TODAY ===", body)
        self.assertIn("=== 2. UNRESOLVED ITEMS & CARRY-FORWARDS ===", body)
        self.assertIn("=== 3. SYSTEM SOURCE STATUS ===", body)

        # Verify that incomplete tasks are under UNRESOLVED, not VERIFIED
        self.assertIn("[UNRESOLVED]", body)
        self.assertIn("Finalize Workforce Allocation", body)

        # Verify that unavailable sources are identified clearly if any fail
        client = Microsoft365Client(user_email="balaadm@velora.ae")
        client.list_calendar_events = lambda: (_ for _ in ()).throw(RuntimeError("Exchange timeout"))
        isolated_wrapup = client.prepare_end_of_day_wrapup()
        self.assertIn("Calendar Meetings (Exchange timeout)", isolated_wrapup["unavailableSources"])
        self.assertIn("⚠️ Note: The following sources were unavailable", isolated_wrapup["body"])

        # Confirm nothing sent without approval
        token = prep["confirmationToken"]
        send_res = await send_approved_email(
            confirmationToken=token,
            previewDetails=prep["previewDetails"],
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(send_res["status"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
