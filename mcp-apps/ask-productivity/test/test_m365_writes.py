"""Unit tests for Microsoft 365 Two-Step Transaction Write Tools (12 tools)."""
import asyncio
import unittest

from productivity_mcp.tools_m365_writes import (
    prepare_email,
    send_approved_email,
    prepare_email_reply,
    send_approved_email_reply,
    prepare_meeting_creation,
    create_approved_meeting,
    prepare_meeting_update,
    update_approved_meeting,
    prepare_meeting_cancellation,
    cancel_approved_meeting,
    prepare_teams_chat_message,
    send_approved_teams_chat_message,
    prepare_teams_channel_post,
    send_approved_teams_channel_post,
    prepare_planner_task,
    create_approved_planner_task,
    prepare_planner_task_update,
    update_approved_planner_task,
    prepare_planner_completion,
    complete_approved_planner_task,
)
from productivity_mcp.dataverse_audit import get_dataverse_client


class TestM365Writes(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        get_dataverse_client().clear_all_for_testing()

    # --- Email Write Tools ---
    async def test_email_two_step_lifecycle(self):
        # Stage A: Prepare
        prep = await prepare_email(
            to=["Ahmed Al Nuaimi", "fatima.mansoori@velora.ae"],
            subject="Q3 Executive Receivables Update",
            body="Review attached S/4HANA breakdown.",
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(prep["status"], "PREVIEW_READY")
        self.assertTrue(prep["approvalRequired"])
        self.assertTrue(prep["confirmationToken"].startswith("velora_appr."))
        self.assertIn("ahmed.nuaimi@velora.ae", prep["previewDetails"]["to"])

        # Stage B: Execute with valid token
        res = await send_approved_email(
            confirmationToken=prep["confirmationToken"],
            previewDetails=prep["previewDetails"],
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["externalObjectId"].startswith("MS-MSG-"))
        self.assertIn("outlook.office.com", res["evidenceLink"])

    async def test_email_reply_two_step_lifecycle(self):
        prep = await prepare_email_reply(
            threadId="TH-001",
            body="Thank you Ahmed, acknowledged.",
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(prep["status"], "PREVIEW_READY")
        self.assertTrue(prep["approvalRequired"])

        res = await send_approved_email_reply(
            confirmationToken=prep["confirmationToken"],
            previewDetails=prep["previewDetails"],
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(res["status"], "SUCCESS")

    # --- Calendar Write Tools ---
    async def test_meeting_creation_lifecycle(self):
        prep = await prepare_meeting_creation(
            subject="Board Financial Review",
            attendees=["Fatima Al Mansoori", "balaadm@velora.ae"],
            startTime="2026-08-28T09:00:00Z",
            endTime="2026-08-28T10:00:00Z",
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(prep["status"], "PREVIEW_READY")
        self.assertTrue(prep["approvalRequired"])

        res = await create_approved_meeting(
            confirmationToken=prep["confirmationToken"],
            previewDetails=prep["previewDetails"],
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["externalObjectId"].startswith("EVT-"))

    async def test_meeting_update_and_cancellation_lifecycle(self):
        # Update
        prep_upd = await prepare_meeting_update(
            eventId="EVT-2026-0826-01",
            updates={"subject": "Updated: Executive Operations Alignment"},
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(prep_upd["status"], "PREVIEW_READY")
        res_upd = await update_approved_meeting(
            confirmationToken=prep_upd["confirmationToken"],
            previewDetails=prep_upd["previewDetails"],
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(res_upd["status"], "SUCCESS")

        # Cancel
        prep_canc = await prepare_meeting_cancellation(
            eventId="EVT-2026-0826-01",
            reason="Rescheduled to Q4",
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(prep_canc["status"], "PREVIEW_READY")
        res_canc = await cancel_approved_meeting(
            confirmationToken=prep_canc["confirmationToken"],
            previewDetails=prep_canc["previewDetails"],
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(res_canc["status"], "SUCCESS")

    # --- Teams Write Tools ---
    async def test_teams_chat_and_channel_post_lifecycle(self):
        # Chat
        prep_chat = await prepare_teams_chat_message(
            chatId="CHAT-EXEC-DIRECT-01",
            messageContent="Let us review the SAC EBITDA numbers.",
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(prep_chat["status"], "PREVIEW_READY")
        res_chat = await send_approved_teams_chat_message(
            confirmationToken=prep_chat["confirmationToken"],
            previewDetails=prep_chat["previewDetails"],
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(res_chat["status"], "SUCCESS")

        # Channel
        prep_chan = await prepare_teams_channel_post(
            teamName="Executive Leadership Team",
            channelName="General",
            messageContent="Weekly executive operations summary posted.",
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(prep_chan["status"], "PREVIEW_READY")
        res_chan = await send_approved_teams_channel_post(
            confirmationToken=prep_chan["confirmationToken"],
            previewDetails=prep_chan["previewDetails"],
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(res_chan["status"], "SUCCESS")

    # --- Planner Write Tools ---
    async def test_planner_tasks_lifecycle(self):
        # Create
        prep_tsk = await prepare_planner_task(
            planName="Executive Strategic Initiatives",
            bucketName="Q3 Deliverables",
            title="Review SAP Analytics Cloud Margins",
            assignees=["Mariam Al Kaabi"],
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(prep_tsk["status"], "PREVIEW_READY")
        res_tsk = await create_approved_planner_task(
            confirmationToken=prep_tsk["confirmationToken"],
            previewDetails=prep_tsk["previewDetails"],
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(res_tsk["status"], "SUCCESS")
        task_id = res_tsk["externalObjectId"]

        # Update
        prep_upd = await prepare_planner_task_update(
            taskId=task_id,
            updates={"title": "Updated: Review SAP Analytics Cloud Operating Margins"},
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(prep_upd["status"], "PREVIEW_READY")
        res_upd = await update_approved_planner_task(
            confirmationToken=prep_upd["confirmationToken"],
            previewDetails=prep_upd["previewDetails"],
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(res_upd["status"], "SUCCESS")

        # Complete
        prep_cmp = await prepare_planner_completion(
            taskId=task_id,
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(prep_cmp["status"], "PREVIEW_READY")
        res_cmp = await complete_approved_planner_task(
            confirmationToken=prep_cmp["confirmationToken"],
            previewDetails=prep_cmp["previewDetails"],
            userEmail="balaadm@velora.ae",
        )
        self.assertEqual(res_cmp["status"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
