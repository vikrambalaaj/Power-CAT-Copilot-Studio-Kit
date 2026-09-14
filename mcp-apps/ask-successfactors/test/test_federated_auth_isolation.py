"""Federated audit authentication must never reuse legacy client secrets."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
import httpx
from successfactors_mcp.dataverse_audit import DataverseClient

class TestFederatedAuthIsolation(unittest.IsolatedAsyncioTestCase):
    async def test_missing_assertion_does_not_use_existing_secret(self):
        with patch.dict(os.environ, {}, clear=True):
            client = DataverseClient(base_url="https://review.example.invalid", tenant_id="test-tenant", client_id="test-client", client_secret="obsolete-test-secret", auth_type="FederatedCredential", federated_token_file="/missing/review/assertion")
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as post:
                with self.assertRaisesRegex(ValueError, "client-secret fallback is disabled"):
                    await client._get_access_token()
                post.assert_not_awaited()

    async def test_assertion_rotation_uses_current_file_without_secret(self):
        with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "assertion"
            path.write_text("first-synthetic-assertion")
            client = DataverseClient(base_url="https://review.example.invalid", tenant_id="test-tenant", client_id="test-client", client_secret="obsolete-test-secret", auth_type="FederatedCredential", federated_token_file=str(path))
            response = httpx.Response(200, json={"access_token":"synthetic-access-token","expires_in":3600}, request=httpx.Request("POST","https://example.invalid"))
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=response) as post:
                await client._get_access_token()
                self.assertEqual(post.call_args.kwargs["data"]["client_assertion"], "first-synthetic-assertion")
                self.assertNotIn("client_secret", post.call_args.kwargs["data"])
                path.write_text("rotated-synthetic-assertion")
                client._token_expires_at = 0
                await client._get_access_token()
                self.assertEqual(post.call_args.kwargs["data"]["client_assertion"], "rotated-synthetic-assertion")
                self.assertNotIn("client_secret", post.call_args.kwargs["data"])
