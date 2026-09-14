"""Dedicated Graph credentials must not mix with other application credentials."""
import os
import unittest
from unittest.mock import patch
from productivity_mcp.m365_client import Microsoft365Client

class GraphConfigurationTests(unittest.TestCase):
    def test_graph_credentials_override_legacy_group(self):
        with patch.dict(os.environ, {"GRAPH_CLIENT_ID": "graph-app", "GRAPH_TENANT_ID": "graph-tenant", "GRAPH_CLIENT_SECRET": "test-secret", "AZURE_CLIENT_ID": "other-app", "AZURE_CLIENT_SECRET": "other-secret"}, clear=True):
            client = Microsoft365Client()
            self.assertEqual((client.client_id, client.tenant_id, client.client_secret), ("graph-app", "graph-tenant", "test-secret"))

    def test_pending_secret_does_not_reuse_legacy_secret(self):
        with patch.dict(os.environ, {"GRAPH_CLIENT_ID": "graph-app", "GRAPH_TENANT_ID": "graph-tenant", "AZURE_CLIENT_SECRET": "other-secret"}, clear=True):
            client = Microsoft365Client()
            self.assertFalse(client.is_live)
            self.assertEqual(client.client_secret, "")

    def test_legacy_configuration_still_supported(self):
        with patch.dict(os.environ, {"M365_CLIENT_ID": "legacy-app", "M365_TENANT_ID": "legacy-tenant", "M365_CLIENT_SECRET": "test-secret"}, clear=True):
            client = Microsoft365Client()
            self.assertTrue(client.is_live)
            self.assertEqual(client.client_id, "legacy-app")
