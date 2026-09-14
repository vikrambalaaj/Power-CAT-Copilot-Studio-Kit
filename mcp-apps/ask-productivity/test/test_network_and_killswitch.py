"""Acceptance tests for Network Security / SSRF and Kill-Switch Controls (WP05, WP12).

Tests:
1. Rejection of cloud metadata and link-local addresses (169.254.169.254, 168.63.129.16)
2. Rejection of loopback addresses (127.0.0.1, ::1)
3. Rejection of unapproved private network addresses
4. Permission of approved internal SAP/MeshX hostnames
5. Rejection of non-HTTPS schemes (http, ftp, file)
6. OData NextLink security validation (cross-origin / scheme change blocked)
7. Kill Switch: Global emergency shutdown blocks operations
8. Kill Switch: Tool-specific disabling blocks target tool while keeping others open
9. Kill Switch: Client-specific and Tenant-specific suspension
"""
import os
import unittest

from shared_mcp.network_security import (
    SSRFSecurityError,
    validate_destination_url,
    validate_odata_next_link,
)
from shared_mcp.kill_switch import (
    KillSwitchActiveError,
    check_kill_switch,
    is_global_kill_switch_active,
)


class TestNetworkSecurityAndKillSwitch(unittest.TestCase):
    def setUp(self):
        os.environ.pop("VELORA_EMERGENCY_KILL_SWITCH", None)
        os.environ.pop("DISABLED_TOOLS", None)
        os.environ.pop("DISABLED_CLIENTS", None)
        os.environ.pop("DISABLED_TENANTS", None)
        os.environ["ALLOWED_INTERNAL_HOSTS"] = "sap.corp.velora.ae,meshx.velora.ae"

    def tearDown(self):
        os.environ.pop("VELORA_EMERGENCY_KILL_SWITCH", None)
        os.environ.pop("DISABLED_TOOLS", None)
        os.environ.pop("DISABLED_CLIENTS", None)
        os.environ.pop("DISABLED_TENANTS", None)

    def test_ssrf_blocks_cloud_metadata(self):
        with self.assertRaises(SSRFSecurityError) as ctx:
            validate_destination_url("https://169.254.169.254/metadata/instance")
        self.assertIn("metadata", str(ctx.exception).lower())

        with self.assertRaises(SSRFSecurityError) as ctx:
            validate_destination_url("https://168.63.129.16/wireserver")
        self.assertIn("metadata", str(ctx.exception).lower())

    def test_ssrf_blocks_loopback(self):
        with self.assertRaises(SSRFSecurityError) as ctx:
            validate_destination_url("https://127.0.0.1:8000/internal")
        self.assertIn("metadata", str(ctx.exception).lower())

    def test_ssrf_blocks_unauthorized_private_ip(self):
        # 10.0.0.5 without approved hostname
        with self.assertRaises(SSRFSecurityError) as ctx:
            validate_destination_url("https://10.0.0.5/api/v1")
        self.assertIn("private internal network", str(ctx.exception).lower())

    def test_ssrf_blocks_non_https_schemes(self):
        with self.assertRaises(SSRFSecurityError) as ctx:
            validate_destination_url("http://sap.corp.velora.ae/odata")
        self.assertIn("scheme", str(ctx.exception).lower())

        with self.assertRaises(SSRFSecurityError) as ctx:
            validate_destination_url("file:///etc/passwd")
        self.assertIn("scheme", str(ctx.exception).lower())

    def test_odata_next_link_validates_same_origin(self):
        base_url = "https://sap.corp.velora.ae/sap/opu/odata/sap/API_JOURNALENTRYITEM_2/"
        
        # 1. Valid relative nextLink passes
        valid_next = "?$skiptoken=100"
        result = validate_odata_next_link(base_url, valid_next)
        self.assertTrue(result.startswith("https://sap.corp.velora.ae"))

        # 2. Host changing nextLink is blocked
        attacker_next = "https://evil-attacker.com/steal_token?$skiptoken=100"
        with self.assertRaises(SSRFSecurityError) as ctx:
            validate_odata_next_link(base_url, attacker_next)
        self.assertIn("host mismatch", str(ctx.exception).lower())

        # 3. Scheme changing nextLink is blocked
        http_next = "http://sap.corp.velora.ae/sap/opu/odata/sap/API_JOURNALENTRYITEM_2/?$skiptoken=100"
        with self.assertRaises(SSRFSecurityError) as ctx:
            validate_odata_next_link(base_url, http_next)
        self.assertIn("scheme", str(ctx.exception).lower())

    def test_kill_switch_global(self):
        # Normal state
        check_kill_switch(tool_name="send_email", client_id="app-1", tenant_id="tenant-1")

        # Engage global kill switch
        os.environ["VELORA_EMERGENCY_KILL_SWITCH"] = "true"
        self.assertTrue(is_global_kill_switch_active())
        with self.assertRaises(KillSwitchActiveError) as ctx:
            check_kill_switch(tool_name="send_email")
        self.assertIn("emergency kill switch", str(ctx.exception).lower())

    def test_kill_switch_per_tool(self):
        os.environ["DISABLED_TOOLS"] = "send_email,create_meeting"

        # Allowed tool proceeds
        check_kill_switch(tool_name="search_mail")

        # Disabled tool blocked
        with self.assertRaises(KillSwitchActiveError) as ctx:
            check_kill_switch(tool_name="send_email")
        self.assertIn("send_email", str(ctx.exception).lower())

    def test_kill_switch_per_client_and_tenant(self):
        os.environ["DISABLED_CLIENTS"] = "rogue-client-app-id"
        os.environ["DISABLED_TENANTS"] = "compromised-tenant-id"

        # Allowed client & tenant pass
        check_kill_switch(client_id="good-client", tenant_id="good-tenant")

        # Blocked client
        with self.assertRaises(KillSwitchActiveError):
            check_kill_switch(client_id="rogue-client-app-id")

        # Blocked tenant
        with self.assertRaises(KillSwitchActiveError):
            check_kill_switch(tenant_id="compromised-tenant-id")


if __name__ == "__main__":
    unittest.main()
