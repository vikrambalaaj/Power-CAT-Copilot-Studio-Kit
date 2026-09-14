import os
import tempfile
from pathlib import Path
import asyncio
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

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
        self._temp_dir = tempfile.TemporaryDirectory()
        self._orig_spool = os.environ.get("DATAVERSE_AUDIT_SPOOL_PATH")
        os.environ["DATAVERSE_AUDIT_SPOOL_PATH"] = str(Path(self._temp_dir.name) / "sf_audit_spool.jsonl")
        self._orig_allow_buffered = os.environ.get("ALLOW_BUFFERED_AUDIT_WRITES")
        os.environ["ALLOW_BUFFERED_AUDIT_WRITES"] = "1"
        self.dv_client = DataverseClient()
        self.dv_client.clear_all_for_testing()
        self.bg_logger = BackgroundLogger(dataverse_client=self.dv_client)
        self.memory_service = MemoryService(
            dataverse_client=self.dv_client,
            background_logger=self.bg_logger,
        )

    async def asyncTearDown(self):
        await self.bg_logger.stop()
        if self._orig_spool is not None:
            os.environ["DATAVERSE_AUDIT_SPOOL_PATH"] = self._orig_spool
        else:
            os.environ.pop("DATAVERSE_AUDIT_SPOOL_PATH", None)
        if self._orig_allow_buffered is not None:
            os.environ["ALLOW_BUFFERED_AUDIT_WRITES"] = self._orig_allow_buffered
        else:
            os.environ.pop("ALLOW_BUFFERED_AUDIT_WRITES", None)
        self._temp_dir.cleanup()

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


    async def test_spool_replay_ignores_committed_records(self):
        """F09 verification: A pending record followed by its commit marker must NOT be requeued on restart."""
        import tempfile
        import json
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".jsonl") as tf:
            spool_file = tf.name
            # Turn 1: Enqueued then committed
            turn_1_pending = {
                "turn_id": "turn-committed-001",
                "record_type": RECORD_TYPE_USER_TURN,
                "time": 1000.0,
                "persisted": False,
                "payload": {
                    "cre2f_recordtype": "USER_TURN",
                    "cre2f_turnid": "turn-committed-001",
                    "cre2f_usermessage": "Should not be recovered",
                    "cre2f_useremail": "exec@velora.ae",
                },
            }
            turn_1_commit = {
                "turn_id": "turn-committed-001",
                "persisted": True,
                "time": 1001.0,
            }
            # Turn 2: Pending (uncommitted)
            turn_2_pending = {
                "turn_id": "turn-pending-002",
                "record_type": RECORD_TYPE_TOOL_EXECUTION,
                "time": 1002.0,
                "persisted": False,
                "payload": {
                    "cre2f_recordtype": "TOOL_EXECUTION",
                    "cre2f_turnid": "turn-pending-002",
                    "cre2f_toolname": "sf__get_headcount",
                    "cre2f_latencymilliseconds": 142,
                    "cre2f_useremail": "exec@velora.ae",
                },
            }
            tf.write(json.dumps(turn_1_pending) + "\n")
            tf.write(json.dumps(turn_1_commit) + "\n")
            tf.write(json.dumps(turn_2_pending) + "\n")
            tf.flush()

        logger = BackgroundLogger(dataverse_client=self.dv_client, spool_path=spool_file)
        stats = logger.get_stats()
        # Only turn-pending-002 should be enqueued!
        self.assertEqual(stats["total_enqueued"], 1)
        self.assertEqual(stats["queue_size"], 1)
        recovered_rec = logger._get_queue().get_nowait()
        self.assertEqual(recovered_rec.turn_id, "turn-pending-002")
        self.assertEqual(recovered_rec.tool_name, "sf__get_headcount")
        self.assertEqual(recovered_rec.latency_ms, 142)

    async def test_spool_reconstructs_full_record_fields(self):
        """F09 verification: Full 70+ field audit record is reconstructed without dropping fields."""
        import tempfile
        import json
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".jsonl") as tf:
            spool_file = tf.name
            original_rec = DataverseAuditRecord(
                record_type=RECORD_TYPE_TOOL_EXECUTION,
                user_object_id="entra-user-999",
                user_email="cfo@velora.ae",
                user_display_name="Chief Financial Officer",
                root_correlation_id="root-corr-xyz",
                conversation_id="conv-abc",
                session_id="sess-123",
                turn_id="turn-full-payload",
                parent_turn_id="pturn-0",
                tool_name="sf__execute_query",
                operation="sf__execute_query",
                transaction_type="QUERY",
                source_system="SuccessFactors",
                approval_status="APPROVED",
                approval_token_hash="hash-abc-def",
                latency_ms=280,
                result_count=42,
                error_category="",
                content_classification="HIGHLY_CONFIDENTIAL",
                request_filter_safe="CompanyCode eq '1000'",
                user_groups=["ExecutiveBoard", "FinanceAudit"],
                memory_eligible=True,
                memory_summary="CFO queried Q3 budget execution.",
                memory_topics=["Finance", "Budget"],
            )
            spool_entry = {
                "turn_id": original_rec.turn_id,
                "record_type": original_rec.record_type,
                "time": 2000.0,
                "persisted": False,
                "payload": original_rec.to_dataverse_payload(),
            }
            tf.write(json.dumps(spool_entry) + "\n")
            tf.flush()

        logger = BackgroundLogger(dataverse_client=self.dv_client, spool_path=spool_file)
        self.assertEqual(logger.get_stats()["total_enqueued"], 1)
        rec = logger._get_queue().get_nowait()
        self.assertEqual(rec.turn_id, "turn-full-payload")
        self.assertEqual(rec.user_email, "cfo@velora.ae")
        self.assertEqual(rec.user_display_name, "Chief Financial Officer")
        self.assertEqual(rec.root_correlation_id, "root-corr-xyz")
        self.assertEqual(rec.session_id, "sess-123")
        self.assertEqual(rec.transaction_type, "QUERY")
        self.assertEqual(rec.source_system, "SuccessFactors")
        self.assertEqual(rec.approval_status, "APPROVED")
        self.assertEqual(rec.approval_token_hash, "hash-abc-def")
        self.assertEqual(rec.latency_ms, 280)
        self.assertEqual(rec.result_count, 42)
        self.assertEqual(rec.content_classification, "HIGHLY_CONFIDENTIAL")
        self.assertEqual(rec.request_filter_safe, "CompanyCode eq '1000'")
        self.assertEqual(rec.user_groups, ["ExecutiveBoard", "FinanceAudit"])
        self.assertTrue(rec.memory_eligible)
        self.assertEqual(rec.memory_summary, "CFO queried Q3 budget execution.")
        self.assertEqual(rec.memory_topics, ["Finance", "Budget"])

    async def test_federated_dataverse_client_assertion_and_is_live(self):
        """Verify that DataverseClient in SuccessFactors uses client_id with federated token assertion (RFC 7523)."""
        captured_requests = []

        class MockResponse:
            def __init__(self, status_code=200, json_data=None):
                self.status_code = status_code
                self._json_data = json_data or {"access_token": "fed_access_token_sf_999", "expires_in": 3600}
                self.content = b'{"access_token": "fed_access_token_sf_999"}'

            def raise_for_status(self):
                pass

            def json(self):
                return self._json_data

        class MockAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def post(self, url, data=None, **kwargs):
                captured_requests.append({"url": url, "data": data})
                return MockResponse()

        with patch.dict(
            os.environ,
            {
                "AZURE_CLIENT_SECRET": "",
                "DATAVERSE_CLIENT_SECRET": "",
                "MOCK_DATAVERSE": "0",
            },
        ):
            client = DataverseClient(
                base_url="https://org4b098979.crm15.dynamics.com",
                tenant_id="9ce80a2a-2703-4502-b26e-d911a3f83418",
                client_id="c659609b-76db-49b1-8470-3205a6c35ecb",
                federated_token="sample-jwt-federated-assertion-sf",
                auth_type="FederatedCredential",
            )

            # Confirm is_live is True even without client_secret
            self.assertTrue(client.is_live)
            self.assertFalse(client.client_secret)

            with patch("httpx.AsyncClient", MockAsyncClient):
                token = await client._get_access_token()
                self.assertEqual(token, "fed_access_token_sf_999")

        self.assertEqual(len(captured_requests), 1)
        req = captured_requests[0]
        self.assertIn("9ce80a2a-2703-4502-b26e-d911a3f83418", req["url"])
        self.assertEqual(req["data"]["client_id"], "c659609b-76db-49b1-8470-3205a6c35ecb")
        self.assertEqual(req["data"]["client_assertion_type"], "urn:ietf:params:oauth:client-assertion-type:jwt-bearer")
        self.assertEqual(req["data"]["client_assertion"], "sample-jwt-federated-assertion-sf")
        self.assertEqual(req["data"]["grant_type"], "client_credentials")


if __name__ == "__main__":
    unittest.main()

