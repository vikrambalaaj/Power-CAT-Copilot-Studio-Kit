import unittest
from unittest.mock import MagicMock, patch
from facilitator_mcp.tools import (
    get_facilitator_guide,
    get_calendar_meetings,
    process_calendar_meeting_workflow,
    query_user_history_from_dataverse,
    sync_dataverse_logs_to_memory,
    draft_meeting_summary_email,
    configure_auto_send_policy,
    ingest_chat_to_knowledge_graph,
    generate_pre_meeting_briefing,
    export_meeting_to_loop_notebook,
    send_executive_email_via_graph,
)


class TestFacilitatorServer(unittest.TestCase):
    def test_get_facilitator_guide(self):
        res = get_facilitator_guide()
        self.assertIn("content", res)
        self.assertIn("steps", res)
        self.assertEqual(len(res["steps"]), 3)
        self.assertIn("Office 365 Outlook", res["content"])

    def test_query_user_history_from_dataverse(self):
        # Query for balaadm@velora.ae
        res = query_user_history_from_dataverse(user_email="balaadm@velora.ae", limit=5)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["user_email"], "balaadm@velora.ae")
        self.assertTrue(res["user_isolation_enforced"])
        self.assertGreaterEqual(res["returned_records_count"], 2)
        
        # Verify all returned records belong strictly to balaadm@velora.ae
        for entry in res["history_timeline"]:
            self.assertIn(entry["system"], ["SuccessFactors", "S4HANA"])
            self.assertNotIn("otheruser@velora.ae", entry["summary"])

    def test_query_user_history_isolation(self):
        # Query for otheruser@velora.ae
        res = query_user_history_from_dataverse(user_email="otheruser@velora.ae", limit=5)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["returned_records_count"], 1)
        self.assertEqual(res["history_timeline"][0]["operation"], "READ_CARGO_OPERATIONS")

    def test_sync_dataverse_logs_to_memory(self):
        res = sync_dataverse_logs_to_memory(user_email="balaadm@velora.ae", limit=2)
        self.assertEqual(res["status"], "DATAVERSE_MEMORY_SYNCED")
        self.assertEqual(res["user_email"], "balaadm@velora.ae")
        self.assertGreaterEqual(res["active_knowledge_graph_size"], 2)

    def test_get_calendar_meetings(self):
        res = get_calendar_meetings(timeframe="today")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertGreaterEqual(res["total_meetings"], 1)
        self.assertEqual(res["meetings"][0]["meeting_id"], "MTG-2026-0818-01")
        self.assertIn("balaadm@velora.ae", res["meetings"][0]["attendees"])

    @patch("facilitator_mcp.tools.send_executive_email_via_graph")
    def test_process_calendar_meeting_workflow_post_meeting(self, mock_send):
        mock_send.return_value = {
            "status": "EMAIL_SENT",
            "sender": "svc_aiagent@velora.ae",
            "graph_http_status": 202
        }

        res = process_calendar_meeting_workflow(
            meeting_subject="Executive Strategy & Operational Alignment",
            phase="POST_MEETING",
            key_decisions=["Approved automated calendar wrapup"],
            action_items=[{"task": "Deploy to BTP", "owner": "Bala", "due": "2026-08-18"}]
        )

        self.assertEqual(res["workflow"], "POST_MEETING_AUTO_WRAPUP")
        self.assertEqual(res["status"], "COMPLETED_AND_AUTO_DISPATCHED")
        self.assertIn("balaadm@velora.ae", res["meeting_context"]["attendees"])
        self.assertIn("LOOP-", res["loop_storage"]["loop_component_id"])
        mock_send.assert_called_once()

    def test_process_calendar_meeting_workflow_pre_meeting(self):
        res = process_calendar_meeting_workflow(
            meeting_subject="Weekly Ground Operations & Workforce Planning",
            phase="PRE_MEETING"
        )
        self.assertEqual(res["workflow"], "PRE_MEETING_BRIEFING")
        self.assertEqual(res["status"], "BRIEFING_DELIVERED_TO_INBOX")
        self.assertIn("connector_synthesis", res["briefing_packet"])

    def test_draft_meeting_summary_email(self):
        res = draft_meeting_summary_email(
            topic="Executive Review 2026",
            attendees=["balaadm@velora.ae"],
            key_decisions=["Decided to automate audit logging across all MCP servers."],
            action_items=[{"task": "Verify Dataverse tables", "owner": "Bala", "due": "2026-08-16"}],
            notes="Comprehensive cross-system verification."
        )
        self.assertEqual(res["status"], "ready_for_auto_send")
        self.assertTrue(res["auto_send_eligible"])
        self.assertIn("balaadm@velora.ae", res["to"])
        self.assertIn("Executive Review 2026", res["subject"])
        self.assertIn("Decided to automate audit logging", res["body_html"])

    def test_configure_auto_send_policy(self):
        res = configure_auto_send_policy(agent_name="Velora Facilitator", require_confirmation=False)
        self.assertTrue(res["policy"]["auto_send_enabled"])
        self.assertTrue(res["policy"]["bypass_user_review"])
        self.assertEqual(res["policy"]["trigger_event"], "End_of_Meeting")

    def test_ingest_chat_to_knowledge_graph(self):
        res = ingest_chat_to_knowledge_graph(
            chat_id="CHAT-101",
            user_query="What are the latest AR aging figures and Emirati headcount?",
            agent_response="AR aging overdue is AED 2.4M and Emiratisation is at 42.5%.",
            topics=["Finance", "Workforce"],
            entities=[{"type": "Metric", "name": "AR Aging"}, {"type": "Metric", "name": "Emiratisation"}],
            decisions_captured=["Target Q3 review for overdue accounts"],
            source_systems=["SuccessFactors", "S4HANA"]
        )
        self.assertEqual(res["status"], "INGESTED_TO_KNOWLEDGE_GRAPH")
        self.assertIn("KG-NODE-", res["node_id"])
        self.assertGreaterEqual(res["total_indexed_nodes"], 1)

    def test_generate_pre_meeting_briefing(self):
        res = generate_pre_meeting_briefing(
            meeting_title="Q3 Strategy & Governance Alignment",
            attendees=["leadership@velora.ae", "balaadm@velora.ae"],
            meeting_date="2026-08-16",
            focus_areas=["Workforce", "Finance", "SAC BI"]
        )
        self.assertEqual(res["status"], "BRIEFING_GENERATED")
        self.assertIn("connector_synthesis", res["briefing_packet"])
        self.assertIn("successfactors_hcm", res["briefing_packet"]["connector_synthesis"])
        self.assertIn("s4hana_finance", res["briefing_packet"]["connector_synthesis"])
        self.assertIn("sac_analytics", res["briefing_packet"]["connector_synthesis"])

    def test_export_meeting_to_loop_notebook(self):
        res = export_meeting_to_loop_notebook(
            meeting_title="Q3 Executive Board Review",
            attendees=["leadership@velora.ae"],
            summary="Review of cross-system SAP metrics and automated Facilitator dispatch.",
            key_decisions=["Approved automated briefing synthesis and Loop storage."],
            action_items=[{"task": "Deploy updated Facilitator to BTP", "owner": "Bala", "due": "2026-08-16"}]
        )
        self.assertEqual(res["status"], "SAVED_TO_LOOP_NOTEBOOK")
        self.assertIn("LOOP-", res["loop_component_id"])
        self.assertTrue(res["searchable_from_go_live"])
        self.assertIn("OneNote://", res["notebook_location"])

    def test_send_executive_email_via_graph_simulation(self):
        with patch("urllib.request.urlopen") as mock_urlopen:
            token_mock = MagicMock()
            token_mock.read.return_value = b'{"access_token": "mock-token-xyz"}'
            
            send_mock = MagicMock()
            send_mock.status = 202

            mock_urlopen.side_effect = [
                MagicMock(__enter__=MagicMock(return_value=token_mock)),
                MagicMock(__enter__=MagicMock(return_value=send_mock))
            ]

            res = send_executive_email_via_graph(
                to_recipients=["leadership@velora.ae"],
                subject="Test Executive Brief",
                body_html="<p>Summary of decisions</p>"
            )

            self.assertEqual(res["status"], "EMAIL_SENT")
            self.assertEqual(res["sender"], "svc_aiagent@velora.ae")
            self.assertEqual(res["graph_http_status"], 202)


if __name__ == "__main__":
    unittest.main()
