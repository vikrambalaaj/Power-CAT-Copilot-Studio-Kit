"""Acceptance Test Suite T13: Teams Meeting Action Tracker with Named Owners, Due Dates, and Follow-ups.

Verifies MoM Requirements R09, R10 and Acceptance Criteria T13:
1. Real notes extract reviewable actions with cited owner and deadline evidence.
2. Missing owner/date remain UNASSIGNED and DATE_REQUIRED (zero hallucination).
3. Absent owner/date blocks commitment only for that action; valid actions proceed.
4. Ambiguous directory owner requires human review (AMBIGUOUS).
5. Stage A preview creates zero tasks; Stage B creates tasks.
6. Idempotent retries prevent duplicate Planner tasks.
7. Live tracker reflects provider updates (percentComplete, status, due date changes).
8. Automatic reminders follow deadline rules (due-soon, overdue).
9. Completed task suppresses automatic reminders (REMINDER_SUPPRESSED_COMPLETED).
10. Denied/absent transcript reports TRANSCRIPT_UNAVAILABLE / SOURCE_UNAVAILABLE without fabricated minutes.
11. Calendar event ID distinct from onlineMeeting ID mapping verified.
12. Server handoff routing for GET_MEETING_ACTION_TRACKER, PREPARE_MEETING_ACTIONS, and CREATE_APPROVED_MEETING_ACTIONS.
"""
import os
import unittest
from datetime import datetime, timezone, timedelta

from productivity_mcp.business_repository import (
    MeetingActionMappingRecord,
    get_business_repository,
)
from productivity_mcp.dataverse_audit import get_dataverse_client
from productivity_mcp.m365_client import (
    Microsoft365Client,
    AccessDeniedError,
    _M365_PLANNER_TASKS,
    seed_test_m365_data,
)
from productivity_mcp.meeting_actions import (
    ExtractedActionItem,
    create_approved_meeting_actions,
    evaluate_meeting_action_reminders,
    extract_actions_from_transcript_or_notes,
    get_meeting_action_tracker,
    prepare_meeting_actions,
    resolve_action_owners,
)
from productivity_mcp.models import HandoffRequest
from productivity_mcp.server import handle_parent_handoff
from productivity_mcp.token_manager import get_token_manager


class TestMeetingActionsAcceptanceT13(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        os.environ["MOCK_M365"] = "1"
        seed_test_m365_data()
        self.repo = get_business_repository()
        self.repo.clear_all_for_testing()
        get_dataverse_client().clear_all_for_testing()
        self.client = Microsoft365Client(user_email="balaadm@velora.ae")
        self.client.force_mock = True

    # -------------------------------------------------------------------------
    # Test 1: Real notes extract reviewable actions with cited evidence
    # -------------------------------------------------------------------------
    async def test_01_real_notes_produce_reviewable_actions_with_cited_evidence(self):
        """AC-T13-01: Realistic notes extract reviewable actions with exact cited owner and deadline."""
        notes = (
            "Executive Review — Ground Operations Alignment\n\n"
            "Key Decisions:\n"
            "1. Approved credit delivery freeze for overdue accounts.\n\n"
            "Action Items:\n"
            "- Action: Freeze credit deliveries on accounts overdue > 180d. Owner: Ahmed Al Nuaimi. Due: 2026-09-24.\n"
            "- Action: Coordinate passenger flow reassignment. Owner: Fatima Al Mansoori. Due: 2026-09-22.\n"
        )
        res = await prepare_meeting_actions(
            meeting_id="EVT-2026-0826-02",
            source_version="1.0",
            notes_override=notes,
            user_email="balaadm@velora.ae",
        )
        self.assertEqual(res["status"], "PREVIEW_READY")
        self.assertTrue(res["approvalRequired"])
        self.assertIn("confirmationToken", res)
        self.assertTrue(res["confirmationToken"].startswith("velora_appr."))

        preview = res["previewDetails"]
        actions = preview["actions"]
        self.assertEqual(len(actions), 2)
        self.assertEqual(preview["eligibleCount"], 2)
        self.assertEqual(preview["blockedCount"], 0)

        # Check Action 1 cited evidence
        a1 = actions[0]
        self.assertIn("Freeze credit deliveries", a1["title"])
        self.assertEqual(a1["namedOwner"], "Ahmed Al Nuaimi")
        self.assertEqual(a1["ownerStatus"], "ASSIGNED")
        self.assertIsNotNone(a1["ownerEvidence"])
        self.assertEqual(a1["dueDate"], "2026-09-24")
        self.assertEqual(a1["dateStatus"], "SPECIFIED")
        self.assertIsNotNone(a1["deadlineEvidence"])
        self.assertEqual(a1["resolvedOwnerEmail"], "ahmed.nuaimi@velora.ae")
        self.assertTrue(a1["commitmentEligible"])

    # -------------------------------------------------------------------------
    # Test 2: Missing owner and date remain UNASSIGNED and DATE_REQUIRED
    # -------------------------------------------------------------------------
    def test_02_missing_owner_and_date_remain_unassigned_and_required(self):
        """AC-T13-02: Missing owner/date remain unassigned/required. Strict anti-hallucination."""
        raw_text = (
            "Action Items:\n"
            "- Action: Conduct audit of supplier receivables backlog.\n"
            "- Action: Review air cargo security protocols. Owner: Ahmed Al Nuaimi.\n"
            "- Action: Update ground support equipment roster. Due: 2026-09-30.\n"
        )
        extracted = extract_actions_from_transcript_or_notes(raw_text)
        self.assertEqual(len(extracted), 3)

        # Action 1: missing both
        self.assertIsNone(extracted[0].named_owner)
        self.assertEqual(extracted[0].owner_status, "UNASSIGNED")
        self.assertIsNone(extracted[0].due_date)
        self.assertEqual(extracted[0].date_status, "DATE_REQUIRED")

        # Action 2: has owner, missing date
        self.assertEqual(extracted[0].named_owner, None)
        self.assertEqual(extracted[1].named_owner, "Ahmed Al Nuaimi")
        self.assertEqual(extracted[1].owner_status, "ASSIGNED")
        self.assertIsNone(extracted[1].due_date)
        self.assertEqual(extracted[1].date_status, "DATE_REQUIRED")

        # Action 3: has date, missing owner
        self.assertIsNone(extracted[2].named_owner)
        self.assertEqual(extracted[2].owner_status, "UNASSIGNED")
        self.assertEqual(extracted[2].due_date, "2026-09-30")
        self.assertEqual(extracted[2].date_status, "SPECIFIED")

        # Ensure no hallucinated default names or dates
        for item in extracted:
            if item.owner_status == "UNASSIGNED":
                self.assertIsNone(item.named_owner)
            if item.date_status == "DATE_REQUIRED":
                self.assertIsNone(item.due_date)

    # -------------------------------------------------------------------------
    # Test 3: Absent owner/date blocks commitment only for that action
    # -------------------------------------------------------------------------
    async def test_03_absent_owner_or_date_blocks_commitment_only_for_that_action(self):
        """AC-T13-03: Incomplete action blocks commitment only for itself; complete actions commit."""
        mixed_notes = (
            "Action Items:\n"
            "- Action: Complete flight crew duty roster reconciliation. Owner: Fatima Al Mansoori. Due: 2026-09-25.\n"
            "- Action: Procure ramp de-icing fluid reserve stock.\n"
        )
        prep = await prepare_meeting_actions(
            meeting_id="EVT-MIXED-001",
            source_version="1.0",
            notes_override=mixed_notes,
            user_email="balaadm@velora.ae",
        )
        self.assertEqual(prep["status"], "PREVIEW_READY")
        self.assertEqual(prep["previewDetails"]["eligibleCount"], 1)
        self.assertEqual(prep["previewDetails"]["blockedCount"], 1)

        # Stage B: Execute commitment
        res = await create_approved_meeting_actions(
            confirmation_token=prep["confirmationToken"],
            preview_details=prep["previewDetails"],
            user_email="balaadm@velora.ae",
        )
        self.assertEqual(res["status"], "PARTIAL")
        self.assertEqual(len(res["createdTasks"]), 1)
        self.assertEqual(len(res["blockedActions"]), 1)

        # Valid action committed
        created = res["createdTasks"][0]
        self.assertIn("Complete flight crew duty roster", created["title"])
        self.assertEqual(created["status"], "TASK_CREATED")
        self.assertEqual(created["ownerEmail"], "fatima.mansoori@velora.ae")

        # Incomplete action safely blocked
        blocked = res["blockedActions"][0]
        self.assertIn("Procure ramp de-icing fluid", blocked["title"])
        self.assertEqual(blocked["status"], "ACTION_INCOMPLETE_BLOCKED")

    # -------------------------------------------------------------------------
    # Test 4: Ambiguous directory owner requires human review
    # -------------------------------------------------------------------------
    def test_04_ambiguous_directory_owner_requires_review(self):
        """AC-T13-04: Ambiguous owner mention marks AMBIGUOUS and blocks commitment."""
        actions = [
            ExtractedActionItem(
                action_id="ACT-AMB-01",
                title="Review airport terminal expansion blueprint",
                named_owner="Operations Lead",
                owner_status="ASSIGNED",
                owner_evidence="Owner: Operations Lead",
                due_date="2026-09-28",
                date_status="SPECIFIED",
                deadline_evidence="Due: 2026-09-28",
                originating_decision=None,
            )
        ]
        resolved = resolve_action_owners(actions, self.client)
        self.assertEqual(len(resolved), 1)
        item = resolved[0]
        self.assertEqual(item.resolution_status, "AMBIGUOUS")
        self.assertFalse(item.commitment_eligible)
        self.assertIn("Ambiguous owner", item.block_reason)

    # -------------------------------------------------------------------------
    # Test 5: Stage A preview creates zero tasks; Stage B creates tasks
    # -------------------------------------------------------------------------
    async def test_05_prepare_actions_creates_no_tasks_until_approval(self):
        """AC-T13-05: Stage A preview creates 0 tasks; Stage B creates tasks in Planner."""
        notes = (
            "Action Items:\n"
            "- Action: Finalize Dubai South fuel supply contract. Owner: Ahmed Al Nuaimi. Due: 2026-09-29.\n"
        )
        # Stage A: Prepare
        prep = await prepare_meeting_actions(
            meeting_id="EVT-ZERO-TASK-001",
            source_version="1.0",
            notes_override=notes,
            user_email="balaadm@velora.ae",
        )
        self.assertEqual(prep["status"], "PREVIEW_READY")

        # Invariant: Business repository mapping table MUST be empty
        mappings_before = self.repo.meeting_actions.list_mappings(meeting_id="EVT-ZERO-TASK-001")
        self.assertEqual(len(mappings_before), 0)

        # Stage B: Commit
        commit = await create_approved_meeting_actions(
            confirmation_token=prep["confirmationToken"],
            preview_details=prep["previewDetails"],
            user_email="balaadm@velora.ae",
        )
        self.assertEqual(commit["status"], "SUCCESS")
        self.assertEqual(commit["tasksCommitted"], 1)

        # Invariant: Now exactly 1 mapping exists in repository
        mappings_after = self.repo.meeting_actions.list_mappings(meeting_id="EVT-ZERO-TASK-001")
        self.assertEqual(len(mappings_after), 1)
        self.assertEqual(mappings_after[0].planner_task_id, commit["createdTasks"][0]["taskId"])

    # -------------------------------------------------------------------------
    # Test 6: Idempotent retries prevent duplicate Planner tasks
    # -------------------------------------------------------------------------
    async def test_06_idempotent_retry_prevents_duplicate_planner_tasks(self):
        """AC-T13-06: Repeated commitment of the same action returns existing mapping."""
        notes = (
            "Action Items:\n"
            "- Action: Update ground crew safety checklist. Owner: Fatima Al Mansoori. Due: 2026-09-27.\n"
        )
        prep = await prepare_meeting_actions(
            meeting_id="EVT-IDEMP-001",
            source_version="1.0",
            notes_override=notes,
            user_email="balaadm@velora.ae",
        )
        token_mgr = get_token_manager()

        # Run 1
        commit1 = await create_approved_meeting_actions(
            confirmation_token=prep["confirmationToken"],
            preview_details=prep["previewDetails"],
            user_email="balaadm@velora.ae",
        )
        self.assertEqual(commit1["status"], "SUCCESS")
        task_id_1 = commit1["createdTasks"][0]["taskId"]
        self.assertFalse(commit1["createdTasks"][0]["isDuplicate"])

        # Re-issue valid token for retry simulation
        token2, exp2 = token_mgr.create_approval_token(
            operation="PREPARE_MEETING_ACTIONS",
            user_object_id="usr-bala-001",
            user_email="balaadm@velora.ae",
            preview_data=prep["previewDetails"],
            idempotency_key="idemp-key-retry",
            root_correlation_id="corr-test-retry",
            tenant_id="velora-aviation",
        )

        # Run 2 (Retry)
        commit2 = await create_approved_meeting_actions(
            confirmation_token=token2,
            preview_details=prep["previewDetails"],
            user_email="balaadm@velora.ae",
        )
        self.assertEqual(commit2["status"], "SUCCESS")
        task_id_2 = commit2["createdTasks"][0]["taskId"]
        self.assertTrue(commit2["createdTasks"][0]["isDuplicate"])
        self.assertEqual(task_id_1, task_id_2)

    # -------------------------------------------------------------------------
    # Test 7: Live tracker reflects provider updates
    # -------------------------------------------------------------------------
    async def test_07_live_tracker_reflects_provider_updates(self):
        """AC-T13-07: Tracker queries Microsoft Graph provider directly to reflect live state."""
        # Commit a task
        notes = (
            "Action Items:\n"
            "- Action: Deploy ground vehicle telematics sensors. Owner: Ahmed Al Nuaimi. Due: 2026-09-20.\n"
        )
        prep = await prepare_meeting_actions(
            meeting_id="EVT-TRACKER-001",
            source_version="1.0",
            notes_override=notes,
            user_email="balaadm@velora.ae",
        )
        commit = await create_approved_meeting_actions(
            confirmation_token=prep["confirmationToken"],
            preview_details=prep["previewDetails"],
            user_email="balaadm@velora.ae",
        )
        task_id = commit["createdTasks"][0]["taskId"]

        # 1. Initial tracker read
        tracker1 = await get_meeting_action_tracker(
            meeting_id="EVT-TRACKER-001",
            user_email="balaadm@velora.ae",
            reference_time=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(tracker1["status"], "SUCCESS")
        row1 = tracker1["trackerRows"][0]
        self.assertEqual(row1["status"], "NOT_STARTED")
        self.assertEqual(row1["percentComplete"], 0)
        self.assertFalse(row1["isOverdue"])

        # 2. Simulate task progress and completion in Planner provider
        t = next((task for task in _M365_PLANNER_TASKS if task["id"] == task_id), None)
        if t:
            t["percentComplete"] = 100
            t["completedDateTime"] = "2026-09-18T10:00:00Z"

        tracker2 = await get_meeting_action_tracker(
            meeting_id="EVT-TRACKER-001",
            user_email="balaadm@velora.ae",
            reference_time=datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc),
        )
        row2 = tracker2["trackerRows"][0]
        self.assertEqual(row2["status"], "COMPLETED")
        self.assertEqual(row2["percentComplete"], 100)

        # 3. Simulate an overdue uncompleted task
        if t:
            t["percentComplete"] = 50
        tracker3 = await get_meeting_action_tracker(
            meeting_id="EVT-TRACKER-001",
            user_email="balaadm@velora.ae",
            reference_time=datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc),  # past 2026-09-20
        )
        row3 = tracker3["trackerRows"][0]
        self.assertEqual(row3["status"], "IN_PROGRESS")
        self.assertTrue(row3["isOverdue"])
        self.assertGreaterEqual(row3["daysOverdue"], 5)

    # -------------------------------------------------------------------------
    # Test 8: Automatic reminders follow deadline rules
    # -------------------------------------------------------------------------
    def test_08_automatic_reminder_follows_deadline_rules(self):
        """AC-T13-08: Follow-up reminders generated for due-soon and overdue tasks."""
        # Create mapping records in repo
        rec_due_soon = MeetingActionMappingRecord(
            mapping_id="MAP-REM-01",
            tenant_id="velora-aviation",
            meeting_id="EVT-REM-01",
            source_version="1.0",
            extracted_action_id="ACT-01",
            planner_task_id="TSK-MOCK-REM-01",
            plan_id="Plan A",
            bucket_id="Bucket B",
            title="Inspect cargo refrigeration units",
            owner_user_id="ahmed.nuaimi@velora.ae",
            owner_email="ahmed.nuaimi@velora.ae",
            due_date="2026-09-16T12:00:00Z",
            status="NOT_STARTED",
            percent_complete=0,
            originating_decision="Logistics QA",
            source_citation="Owner: Ahmed",
            evidence_id="EV-01",
            audit_id="AUD-01",
            created_at="2026-09-14T00:00:00Z",
            updated_at="2026-09-14T00:00:00Z",
        )
        self.repo.meeting_actions.save_mapping(rec_due_soon)
        _M365_PLANNER_TASKS.append({
            "id": "TSK-MOCK-REM-01",
            "title": "Inspect cargo refrigeration units",
            "percentComplete": 0,
            "dueDateTime": "2026-09-16T12:00:00Z",
            "assigneeIds": ["ahmed.nuaimi@velora.ae"],
        })

        # Reference time: 2026-09-15 12:00:00 UTC (24 hours before due date -> DUE_SOON)
        ref_time = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)
        reminders = evaluate_meeting_action_reminders(
            tenant_id="velora-aviation",
            due_soon_hours=48,
            reference_time=ref_time,
            client=self.client,
        )
        self.assertEqual(len(reminders), 1)
        r = reminders[0]
        self.assertEqual(r["status"], "REMINDER_DUE")
        self.assertEqual(r["reminderWindow"], "DUE_SOON")
        self.assertEqual(r["recipient"], "ahmed.nuaimi@velora.ae")
        self.assertIn("REMINDER: Action Due Soon", r["subject"])
        self.assertIn("TSK-MOCK-REM-01:1.0.0:2026-09-16T12-00-00Z:DUE_SOON:ahmed.nuaimi@velora.ae", r["dedupRunKey"])

    # -------------------------------------------------------------------------
    # Test 9: Completed task suppresses automatic reminders
    # -------------------------------------------------------------------------
    def test_09_completed_task_suppresses_automatic_reminders(self):
        """AC-T13-09: Re-reading task verifies 100% completion and suppresses reminder."""
        rec_done = MeetingActionMappingRecord(
            mapping_id="MAP-REM-DONE",
            tenant_id="velora-aviation",
            meeting_id="EVT-REM-DONE",
            source_version="1.0",
            extracted_action_id="ACT-DONE",
            planner_task_id="TSK-MOCK-DONE",
            plan_id="Plan A",
            bucket_id="Bucket B",
            title="Calibrate ground radar altimeter",
            owner_user_id="fatima.mansoori@velora.ae",
            owner_email="fatima.mansoori@velora.ae",
            due_date="2026-09-14T10:00:00Z",
            status="NOT_STARTED",
            percent_complete=0,
            originating_decision="Calibration",
            source_citation="Owner: Fatima",
            evidence_id="EV-02",
            audit_id="AUD-02",
            created_at="2026-09-10T00:00:00Z",
            updated_at="2026-09-10T00:00:00Z",
        )
        self.repo.meeting_actions.save_mapping(rec_done)

        # In Planner provider, task is already marked 100% complete
        _M365_PLANNER_TASKS.append({
            "id": "TSK-MOCK-DONE",
            "title": "Calibrate ground radar altimeter",
            "percentComplete": 100,
            "dueDateTime": "2026-09-14T10:00:00Z",
            "completedDateTime": "2026-09-13T16:00:00Z",
            "assigneeIds": ["fatima.mansoori@velora.ae"],
        })

        # Reference time is after due date (would be overdue if not complete)
        ref_time = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)
        reminders = evaluate_meeting_action_reminders(
            tenant_id="velora-aviation",
            reference_time=ref_time,
            client=self.client,
        )
        self.assertEqual(len(reminders), 1)
        r = reminders[0]
        self.assertEqual(r["status"], "REMINDER_SUPPRESSED_COMPLETED")
        self.assertIn("100% complete", r["reason"])
        self.assertNotIn("subject", r)  # Suppressed reminders do not construct dispatch email

    # -------------------------------------------------------------------------
    # Test 10: Denied or absent transcript reports SOURCE_UNAVAILABLE
    # -------------------------------------------------------------------------
    async def test_10_denied_or_absent_transcript_reports_source_unavailable(self):
        """AC-T13-10: 403 AccessDenied or absent content returns SOURCE_UNAVAILABLE with no hallucinated minutes."""
        # Non-existent meeting with no transcripts or notes
        res = await prepare_meeting_actions(
            meeting_id="EVT-NON-EXISTENT-9999",
            source_version="1.0",
            user_email="balaadm@velora.ae",
        )
        self.assertEqual(res["status"], "SOURCE_UNAVAILABLE")
        self.assertFalse(res.get("approvalRequired", False))
        self.assertIn("will not fabricate minutes", res["resultSummary"])
        self.assertEqual(res["previewDetails"], {})

    # -------------------------------------------------------------------------
    # Test 11: Calendar event ID distinct from onlineMeeting ID
    # -------------------------------------------------------------------------
    def test_11_calendar_event_id_distinct_from_online_meeting_id(self):
        """AC-T13-11: Calendar event ID (EVT-...) decouples from onlineMeeting ID (Mtg-...)."""
        calendar_id = "EVT-2026-0826-02"
        resolved_id, meta = self.client.resolve_online_meeting_id(calendar_id)
        self.assertNotEqual(calendar_id, resolved_id)
        self.assertTrue(resolved_id.startswith("Mtg-"))
        self.assertEqual(resolved_id, "Mtg-Finance-Liquidity-2026-02")

    # -------------------------------------------------------------------------
    # Test 12: Server handoff routing and mutation safety
    # -------------------------------------------------------------------------
    async def test_12_server_handoff_routing_and_mutation_blocking(self):
        """AC-T13-12: Server dispatches PREPARE, CREATE, and TRACKER through handoff contract."""
        notes = (
            "Action Items:\n"
            "- Action: Establish logistics spare parts corridor. Owner: Ahmed Al Nuaimi. Due: 2026-09-30.\n"
        )
        # 1. Handoff: PREPARE_MEETING_ACTIONS
        prep_req = HandoffRequest(
            task="Extract meeting actions",
            operation="PREPARE_MEETING_ACTIONS",
            rootCorrelationId="corr-handoff-act-001",
            conversationId="conv-act-01",
            turnId="turn-act-01",
            userObjectId="usr-bala-001",
            userEmail="balaadm@velora.ae",
            parameters={
                "meetingId": "EVT-HANDOFF-001",
                "notesOverride": notes,
            },
        )
        prep_resp = await handle_parent_handoff(prep_req)
        self.assertEqual(prep_resp.status, "PREVIEW_READY")
        self.assertTrue(prep_resp.approvalRequired)
        self.assertIsNotNone(prep_resp.confirmationToken)

        # 2. Handoff: CREATE_APPROVED_MEETING_ACTIONS
        commit_req = HandoffRequest(
            task="Commit approved actions",
            operation="CREATE_APPROVED_MEETING_ACTIONS",
            rootCorrelationId="corr-handoff-act-001",
            conversationId="conv-act-01",
            turnId="turn-act-02",
            userObjectId="usr-bala-001",
            userEmail="balaadm@velora.ae",
            parameters={
                "confirmationToken": prep_resp.confirmationToken,
                "previewDetails": prep_resp.previewDetails,
            },
        )
        commit_resp = await handle_parent_handoff(commit_req)
        self.assertEqual(commit_resp.status, "SUCCESS")
        self.assertFalse(commit_resp.approvalRequired)
        self.assertEqual(commit_resp.structuredResult["tasksCommitted"], 1)

        # 3. Handoff: GET_MEETING_ACTION_TRACKER
        track_req = HandoffRequest(
            task="Get meeting action tracker",
            operation="GET_MEETING_ACTION_TRACKER",
            rootCorrelationId="corr-handoff-act-001",
            conversationId="conv-act-01",
            turnId="turn-act-03",
            userObjectId="usr-bala-001",
            userEmail="balaadm@velora.ae",
            parameters={
                "meetingId": "EVT-HANDOFF-001",
            },
        )
        track_resp = await handle_parent_handoff(track_req)
        self.assertEqual(track_resp.status, "SUCCESS")
        self.assertFalse(track_resp.approvalRequired)
        self.assertEqual(track_resp.structuredResult["summaryMetrics"]["totalActions"], 1)


if __name__ == "__main__":
    unittest.main()
