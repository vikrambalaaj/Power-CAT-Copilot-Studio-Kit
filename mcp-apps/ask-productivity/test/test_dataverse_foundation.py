"""Unit and integration tests for Dataverse Audit Foundation with Fail-Closed semantics."""
import asyncio
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from productivity_mcp.dataverse_audit import (
    DataverseAuditRecord,
    DataverseClient,
    RECORD_TYPE_AGENT_DELEGATION_START,
    RECORD_TYPE_AGENT_DELEGATION_END,
    RECORD_TYPE_TOOL_EXECUTION_START,
    RECORD_TYPE_TOOL_EXECUTION_END,
    RECORD_TYPE_TRANSACTION_PREVIEW,
    RECORD_TYPE_USER_APPROVAL,
    RECORD_TYPE_TRANSACTION_START,
    RECORD_TYPE_TRANSACTION_RESULT,
    RECORD_TYPE_TRANSACTION_ERROR,
    RECORD_TYPE_POLICY_DECISION,
    RECORD_TYPE_RECONCILIATION,
    RECORD_TYPE_LOGGING_ERROR,
    compute_approval_token_hash,
)


class TestDataverseAuditFoundation(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._orig_mock_m365 = os.environ.pop("MOCK_M365", None)
        self._orig_mock_dv = os.environ.pop("MOCK_DATAVERSE", None)
        self.dv_client = DataverseClient(
            base_url="https://example.crm.dynamics.com",
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",
        )
        self.dv_client._create_live_audit_row = AsyncMock(
            side_effect=lambda payload: f"00000000-0000-0000-0000-{len(self.dv_client._audit_store) + 1:012d}"
        )
        self.dv_client.clear_all_for_testing()

    def tearDown(self):
        if self._orig_mock_m365 is not None:
            os.environ["MOCK_M365"] = self._orig_mock_m365
        else:
            os.environ.pop("MOCK_M365", None)
        if self._orig_mock_dv is not None:
            os.environ["MOCK_DATAVERSE"] = self._orig_mock_dv
        else:
            os.environ.pop("MOCK_DATAVERSE", None)

    async def test_all_12_record_types_valid(self):
        """Verify that all 12 required record types are supported and persisted."""
        record_types = [
            RECORD_TYPE_AGENT_DELEGATION_START,
            RECORD_TYPE_AGENT_DELEGATION_END,
            RECORD_TYPE_TOOL_EXECUTION_START,
            RECORD_TYPE_TOOL_EXECUTION_END,
            RECORD_TYPE_TRANSACTION_PREVIEW,
            RECORD_TYPE_USER_APPROVAL,
            RECORD_TYPE_TRANSACTION_START,
            RECORD_TYPE_TRANSACTION_RESULT,
            RECORD_TYPE_TRANSACTION_ERROR,
            RECORD_TYPE_POLICY_DECISION,
            RECORD_TYPE_RECONCILIATION,
            RECORD_TYPE_LOGGING_ERROR,
        ]

        for r_type in record_types:
            rec = DataverseAuditRecord(
                record_type=r_type,
                user_object_id="user-001",
                user_email="balaadm@velora.ae",
                root_correlation_id="corr-test-101",
                operation=f"op_{r_type}",
                invocation_id=f"inv-{r_type}",
            )
            res = await self.dv_client.create_audit_record(rec)
            self.assertEqual(res["status"], "SUCCESS")
            self.assertTrue(res["id"])

    async def test_alternate_key_idempotency(self):
        """Verify Section 3.4 alternate key idempotency: cre2f_invocationid + cre2f_recordtype."""
        rec1 = DataverseAuditRecord(
            record_type=RECORD_TYPE_TRANSACTION_PREVIEW,
            user_email="balaadm@velora.ae",
            invocation_id="inv-unique-999",
            operation="PrepareEmail",
        )
        res1 = await self.dv_client.create_audit_record(rec1)
        self.assertEqual(res1["status"], "SUCCESS")

        # Attempt duplicate with same invocation_id and record_type
        rec2 = DataverseAuditRecord(
            record_type=RECORD_TYPE_TRANSACTION_PREVIEW,
            user_email="balaadm@velora.ae",
            invocation_id="inv-unique-999",
            operation="PrepareEmail",
        )
        res2 = await self.dv_client.create_audit_record(rec2)
        self.assertEqual(res2["status"], "DUPLICATE_KEY")
        self.assertIn("already exists", res2["message"])

    async def test_duplicate_successful_write_prevention(self):
        """Verify Section 3.4: idempotencykey + operation prevents duplicate write execution."""
        rec_start = DataverseAuditRecord(
            record_type=RECORD_TYPE_TRANSACTION_START,
            user_email="balaadm@velora.ae",
            idempotency_key="idemp-send-888",
            operation="SendApprovedEmail",
            invocation_id="inv-send-01",
        )
        start_res = await self.dv_client.start_write_transaction_fail_closed(rec_start)
        self.assertTrue(start_res["may_proceed"])

        # Complete operation successfully
        await self.dv_client.complete_write_transaction(
            audit_record_id=start_res["audit_record_id"],
            invocation_id="inv-send-01",
            outcome="SUCCESS",
            external_object_id="MSG-OUTLOOK-001",
            operation="SendApprovedEmail",
            idempotency_key="idemp-send-888",
        )

        # Attempt to start the same transaction again with same idempotency key
        rec_retry = DataverseAuditRecord(
            record_type=RECORD_TYPE_TRANSACTION_START,
            user_email="balaadm@velora.ae",
            idempotency_key="idemp-send-888",
            operation="SendApprovedEmail",
            invocation_id="inv-send-02",
        )
        retry_res = await self.dv_client.start_write_transaction_fail_closed(rec_retry)
        self.assertFalse(retry_res["may_proceed"])
        self.assertEqual(retry_res["status"], "DUPLICATE_BLOCKED")

    async def test_fail_closed_write_auditing_when_dataverse_offline(self):
        """Verify Section 3.5: If Dataverse is unavailable, write actions fail closed."""
        self.dv_client.simulate_down = True

        rec_write = DataverseAuditRecord(
            record_type=RECORD_TYPE_TRANSACTION_START,
            user_email="balaadm@velora.ae",
            idempotency_key="idemp-offline-01",
            operation="SendApprovedEmail",
        )
        res = await self.dv_client.start_write_transaction_fail_closed(rec_write)
        self.assertFalse(res["may_proceed"])
        self.assertEqual(res["status"], "FAIL_CLOSED_BLOCKED")
        self.assertIn("Write action blocked", res["error"])

    def test_token_hashing_never_stores_raw_token(self):
        """Verify Section 6.3: Raw approval tokens are hashed with HMAC-SHA256."""
        raw_token = "velora_appr.eyJvcCI6ICJQUkVQQVJFX0VNQUlMIn0.sig123"
        hashed = compute_approval_token_hash(raw_token)
        self.assertNotEqual(raw_token, hashed)
        self.assertEqual(len(hashed), 64)  # 256-bit hex
        # Deterministic
        self.assertEqual(hashed, compute_approval_token_hash(raw_token))

    async def test_federated_client_assertion_token_acquisition(self):
        """Verify that DataverseClient uses client_id with federated token assertion (RFC 7523) without client_secret."""
        captured_requests = []

        class MockResponse:
            def __init__(self, status_code=200, json_data=None):
                self.status_code = status_code
                self._json_data = json_data or {"access_token": "fed_access_token_123", "expires_in": 3600}
                self.content = b'{"access_token": "fed_access_token_123"}'

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
                "MOCK_M365": "0",
                "MOCK_DATAVERSE": "0",
                "AZURE_CLIENT_SECRET": "",
                "DATAVERSE_CLIENT_SECRET": "",
                "M365_CLIENT_SECRET": "",
                "ENTRA_CLIENT_SECRET": "",
            },
        ):
            client = DataverseClient(
                base_url="https://org4b098979.crm15.dynamics.com",
                tenant_id="9ce80a2a-2703-4502-b26e-d911a3f83418",
                client_id="c659609b-76db-49b1-8470-3205a6c35ecb",
                federated_token="sample-jwt-federated-assertion",
                auth_type="FederatedCredential",
            )

            # Confirm is_live is True even without client_secret
            self.assertTrue(client.is_live)
            self.assertFalse(client.client_secret)

            with patch("httpx.AsyncClient", MockAsyncClient):
                token = await client._get_access_token()
                self.assertEqual(token, "fed_access_token_123")

        self.assertEqual(len(captured_requests), 1)
        req = captured_requests[0]
        self.assertIn("9ce80a2a-2703-4502-b26e-d911a3f83418", req["url"])
        self.assertEqual(req["data"]["client_id"], "c659609b-76db-49b1-8470-3205a6c35ecb")
        self.assertEqual(req["data"]["client_assertion_type"], "urn:ietf:params:oauth:client-assertion-type:jwt-bearer")
        self.assertEqual(req["data"]["client_assertion"], "sample-jwt-federated-assertion")
        self.assertEqual(req["data"]["grant_type"], "client_credentials")


if __name__ == "__main__":
    unittest.main()

