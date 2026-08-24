"""Unit and integration tests for Extended Dataverse Audit Table & 30-Day Memory Service."""
import asyncio
import unittest
from datetime import datetime, timezone, timedelta

from successfactors_mcp.dataverse_audit import (
    DataverseAuditRecord,
    DataverseClient,
    RECORD_TYPE_USER_TURN,
    RECORD_TYPE_ASSISTANT_TURN,
    RECORD_TYPE_TOOL_EXECUTION,
    RECORD_TYPE_POLICY_DECISION,
    RECORD_TYPE_CONSENT,
    RECORD_TYPE_MEMORY_SUMMARY,
)
from successfactors_mcp.background_logger import BackgroundLogger
from successfactors_mcp.memory_service import MemoryService


class DataverseAuditAndMemoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dv_client = DataverseClient()
        self.dv_client.clear_all_for_testing()
        self.bg_logger = BackgroundLogger(dataverse_client=self.dv_client)
        self.memory_service = MemoryService(
            dataverse_client=self.dv_client,
            background_logger=self.bg_logger,
        )

    async def asyncTearDown(self):
        await self.bg_logger.stop()

    async def test_audit_record_discriminator_and_contract_fields(self):
        record = DataverseAuditRecord(
            record_type=RECORD_TYPE_USER_TURN,
            user_object_id="entra-user-001",
            user_email="exec1@velora.ae",
            conversation_id="conv-101",
            user_message="What is the headcount in Dubai?",
            assistant_message="The headcount is 1,250.",
            message_summary="User asked for Dubai headcount",
            content_classification="CONFIDENTIAL",
            tool_name="sf__get_headcount",
            latency_ms=350,
            cache_hit=True,
        )

        payload = record.to_dataverse_payload()
        
        # Verify discriminator
        self.assertEqual(payload["cre2f_recordtype"], "USER_TURN")
        
        # Verify backward compatibility fields
        self.assertEqual(payload["cre2f_newcolumn"], "exec1@velora.ae")
        self.assertEqual(payload["cre2f_toolname"], "sf__get_headcount")
        
        # Verify extended fields
        self.assertEqual(payload["cre2f_userobjectid"], "entra-user-001")
        self.assertEqual(payload["cre2f_useremail"], "exec1@velora.ae")
        self.assertEqual(payload["cre2f_conversationid"], "conv-101")
        self.assertEqual(payload["cre2f_latencymilliseconds"], 350)
        self.assertTrue(payload["cre2f_cachehit"])

        res = await self.dv_client.create_audit_record(record)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["id"].startswith("AUD-"))

    async def test_background_logger_async_queue_non_blocking(self):
        self.bg_logger.start()
        
        for i in range(5):
            rec = DataverseAuditRecord(
                record_type=RECORD_TYPE_TOOL_EXECUTION,
                user_object_id="entra-002",
                user_email="analyst@velora.ae",
                tool_name="sf__get_joiners",
                message_summary=f"Joiners query {i}",
            )
            success = self.bg_logger.enqueue(rec)
            self.assertTrue(success)

        # Allow worker to process queue
        await asyncio.sleep(0.1)
        stats = self.bg_logger.get_stats()
        self.assertEqual(stats["total_enqueued"], 5)
        self.assertEqual(stats["total_persisted"], 5)
        self.assertEqual(stats["total_failed"], 0)

    async def test_30_day_memory_partition_and_user_isolation(self):
        now = datetime.now(timezone.utc)
        
        # User 1: Recent turn (5 days ago)
        rec_u1_recent = DataverseAuditRecord(
            record_type=RECORD_TYPE_USER_TURN,
            user_object_id="entra-u1",
            user_email="user1@velora.ae",
            conversation_id="conv-u1-1",
            user_message="Who are the unassigned employees?",
            assistant_message="We reviewed the 15 unassigned employees.",
            event_time=(now - timedelta(days=5)).isoformat(),
        )
        # User 1: Old turn (35 days ago - beyond window)
        rec_u1_old = DataverseAuditRecord(
            record_type=RECORD_TYPE_USER_TURN,
            user_object_id="entra-u1",
            user_email="user1@velora.ae",
            conversation_id="conv-u1-2",
            user_message="Old query from last month",
            assistant_message="Old answer",
            event_time=(now - timedelta(days=35)).isoformat(),
        )
        # User 2: Recent turn (2 days ago)
        rec_u2 = DataverseAuditRecord(
            record_type=RECORD_TYPE_USER_TURN,
            user_object_id="entra-u2",
            user_email="user2@velora.ae",
            conversation_id="conv-u2-1",
            user_message="User 2 confidential financial query",
            assistant_message="Private financial response",
            event_time=(now - timedelta(days=2)).isoformat(),
        )

        await self.dv_client.create_audit_record(rec_u1_recent)
        await self.dv_client.create_audit_record(rec_u1_old)
        await self.dv_client.create_audit_record(rec_u2)

        # Query memory for User 1
        u1_memory = await self.dv_client.query_user_30_day_memory(
            user_object_id="entra-u1",
            user_email="user1@velora.ae",
            days=30,
        )

        self.assertEqual(len(u1_memory), 1)
        self.assertEqual(u1_memory[0]["cre2f_conversationid"], "conv-u1-1")
        # Ensure User 2 data is completely excluded
        for m in u1_memory:
            self.assertNotEqual(m["cre2f_useremail"], "user2@velora.ae")
            self.assertNotIn("User 2 confidential", m["cre2f_usermessage"])

    async def test_memory_service_layered_recall_and_disclaimer(self):
        now = datetime.now(timezone.utc)
        
        # Seed memory summary and user turn
        summary_rec = DataverseAuditRecord(
            record_type=RECORD_TYPE_MEMORY_SUMMARY,
            user_object_id="entra-u1",
            user_email="user1@velora.ae",
            conversation_id="conv-u1-sum",
            memory_summary="Executive reviewed Q1 hiring target and agreed to expand Engineering headcount by 25 positions.",
            memory_topics=["Headcount", "Engineering", "Hiring Targets"],
            event_time=(now - timedelta(days=3)).isoformat(),
        )
        await self.dv_client.create_audit_record(summary_rec)

        recall_res = await self.memory_service.recall_user_context(
            user_object_id="entra-u1",
            user_email="user1@velora.ae",
            topic_query="Engineering",
        )

        self.assertEqual(recall_res["status"], "SUCCESS")
        self.assertEqual(recall_res["recalled_count"], 1)
        self.assertIn("Historical figures reflect the state at the time", recall_res["historical_notice"])
        self.assertIn("Engineering headcount", recall_res["recalled_items"][0]["summary"])

    async def test_transcript_reconciliation(self):
        # Create transcript turns missing from Dataverse
        transcripts = [
            {
                "conversation_id": "conv-recon-1",
                "user_object_id": "entra-recon",
                "user_email": "recon@velora.ae",
                "user_message": "Transcribed question",
                "assistant_message": "Transcribed answer",
                "content_hash": "hash-abc-123",
            }
        ]

        res = await self.bg_logger.reconcile_transcripts(transcripts)
        self.assertEqual(res["status"], "RECONCILIATION_COMPLETE")
        self.assertEqual(res["backfilled_turns"], 1)

        # Re-running with same hash should backfill 0 turns
        res2 = await self.bg_logger.reconcile_transcripts(transcripts)
        self.assertEqual(res2["backfilled_turns"], 0)


if __name__ == "__main__":
    unittest.main()
