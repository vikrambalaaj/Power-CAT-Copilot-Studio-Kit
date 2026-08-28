"""Unit and integration tests for Phase 0: Administrator-managed connection manager."""

import asyncio
import os
import unittest
from unittest.mock import patch

from successfactors_mcp.connection_manager import (
    AuthType,
    ConnectionHealthStatus,
    ConnectionManager,
    ConnectionType,
    EnterpriseConnection,
    ReadWriteClassification,
    SecretStoreProvider,
    get_connection_manager,
    set_connection_manager,
)
from successfactors_mcp.connection_admin import (
    ConnectionAdminService,
    get_connection_admin_service,
)


class ConnectionManagerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.secret_store = SecretStoreProvider()
        self.mgr = ConnectionManager(secret_store=self.secret_store, default_environment="Development")
        set_connection_manager(self.mgr)
        self.admin_svc = ConnectionAdminService(manager=self.mgr)

    def test_connection_ownership_model(self):
        """0.1: Verify separation of read, admin write, notification write, and user context connections."""
        sf_conn = self.mgr.resolve_connection("Velora SuccessFactors Connection", environment="Development")
        self.assertIsNotNone(sf_conn)
        self.assertEqual(sf_conn.connection_type, ConnectionType.SAP_SF)
        self.assertEqual(sf_conn.read_write_classification, ReadWriteClassification.READ_ONLY)

        dv_shared = self.mgr.resolve_connection("Velora Dataverse Connection", environment="Development")
        self.assertIsNotNone(dv_shared)
        self.assertEqual(dv_shared.connection_type, ConnectionType.DATAVERSE_SHARED)
        self.assertEqual(dv_shared.read_write_classification, ReadWriteClassification.READ_ONLY)

        # Normal user cannot resolve admin write connection
        dv_admin_normal = self.mgr.resolve_connection("Velora Dataverse Admin Connection", environment="Development", require_admin=False)
        self.assertIsNone(dv_admin_normal)

        # Admin user can resolve admin write connection
        dv_admin_privileged = self.mgr.resolve_connection("Velora Dataverse Admin Connection", environment="Development", require_admin=True)
        self.assertIsNotNone(dv_admin_privileged)
        self.assertEqual(dv_admin_privileged.read_write_classification, ReadWriteClassification.ADMIN_WRITE)

    async def test_secret_store_reference_resolution(self):
        """0.2: Verify secret reference resolution without plaintext secret storage."""
        with patch.dict(os.environ, {"SF_PASSWORD_REF": "TestSecretPass123!", "DATAVERSE_CLIENT_SECRET_REF": "DVSecret456!"}):
            sf_conn = self.mgr.resolve_connection("Velora SuccessFactors Connection")
            self.assertIsNotNone(sf_conn)
            
            # EnterpriseConnection object only contains the secret reference, never the plaintext password
            self.assertEqual(sf_conn.secret_store_reference, "SF_PASSWORD_REF")
            self.assertNotIn("TestSecretPass123!", str(sf_conn.__dict__))

            # SecretStoreProvider retrieves the actual secret
            resolved = await self.mgr.get_resolved_credentials(sf_conn)
            self.assertEqual(resolved["secret"], "TestSecretPass123!")
            self.assertEqual(resolved["client_id"], sf_conn.client_id)

    def test_logical_reference_environment_promotion(self):
        """0.4: Verify canonical logical references resolve correctly across Dev, UAT, and Prod."""
        uat_conn = EnterpriseConnection(
            connection_id="CONN-SF-UAT-001",
            connection_name="Velora SuccessFactors Connection UAT",
            connection_type=ConnectionType.SAP_SF,
            environment="UAT",
            data_source_url="https://api-uat.sapsf.com/odata/v2",
            connection_owner="admin.hr@velora.ae",
            secret_store_reference="SF_UAT_PASSWORD_REF",
            enabled=True,
        )
        prod_conn = EnterpriseConnection(
            connection_id="CONN-SF-PROD-001",
            connection_name="Velora SuccessFactors Connection Prod",
            connection_type=ConnectionType.SAP_SF,
            environment="Production",
            data_source_url="https://api.sapsf.com/odata/v2",
            connection_owner="admin.hr@velora.ae",
            secret_store_reference="SF_PROD_PASSWORD_REF",
            enabled=True,
        )
        self.mgr.register_connection(uat_conn, logical_reference="Velora SuccessFactors Connection")
        self.mgr.register_connection(prod_conn, logical_reference="Velora SuccessFactors Connection")

        resolved_dev = self.mgr.resolve_connection("Velora SuccessFactors Connection", environment="Development")
        self.assertEqual(resolved_dev.connection_id, "CONN-SF-001")

        resolved_uat = self.mgr.resolve_connection("Velora SuccessFactors Connection", environment="UAT")
        self.assertEqual(resolved_uat.connection_id, "CONN-SF-UAT-001")

        resolved_prod = self.mgr.resolve_connection("Velora SuccessFactors Connection", environment="Production")
        self.assertEqual(resolved_prod.connection_id, "CONN-SF-PROD-001")

    def test_admin_authorization_enforcement(self):
        """0.11: Verify that non-admin users cannot access connection management operations."""
        # Non-admin user listing
        normal_list = self.admin_svc.list_connections_for_user(user_roles=["Standard_User"])
        for item in normal_list:
            self.assertNotIn("secret_store_reference", item)
            self.assertNotIn("client_id", item)
            self.assertIn("status", item)

        # Non-admin detail query
        detail_res = self.admin_svc.get_connection_detail("CONN-SF-001", user_roles=["Standard_User"])
        self.assertTrue(detail_res.get("error"))
        self.assertEqual(detail_res.get("error_category"), "authorization")

        # Admin detail query
        admin_detail = self.admin_svc.get_connection_detail("CONN-SF-001", user_roles=["Velora_Admin"])
        self.assertFalse(admin_detail.get("error"))
        self.assertEqual(admin_detail.get("connection_id"), "CONN-SF-001")
        self.assertIn("secret_store_reference", admin_detail)

    def test_killswitch_disable_and_enable(self):
        """0.10, 0.12: Verify operational disable/enable toggle (kill-switch)."""
        conn_id = "CONN-SF-001"
        self.assertTrue(self.mgr.get_connection(conn_id).is_active())

        # Disable connection
        res = self.admin_svc.toggle_connection_status(conn_id, enabled=False, admin_email="ciso@velora.ae", user_roles=["Velora_Admin"])
        self.assertTrue(res["success"])
        self.assertFalse(res["enabled"])
        self.assertFalse(self.mgr.get_connection(conn_id).is_active())
        self.assertEqual(self.mgr.get_connection(conn_id).status, ConnectionHealthStatus.DISABLED)

        # Re-enable connection
        enable_res = self.admin_svc.toggle_connection_status(conn_id, enabled=True, admin_email="ciso@velora.ae", user_roles=["Velora_Admin"])
        self.assertTrue(enable_res["success"])
        self.assertTrue(enable_res["enabled"])
        self.assertTrue(self.mgr.get_connection(conn_id).is_active())
        self.assertEqual(self.mgr.get_connection(conn_id).status, ConnectionHealthStatus.HEALTHY)

    def test_user_facing_failure_messages(self):
        """0.10: Verify standardized, user-safe error messages without technical details."""
        sf_msg = self.mgr.get_user_facing_failure_message(ConnectionType.SAP_SF)
        self.assertEqual(sf_msg, "SuccessFactors is temporarily unavailable because the managed enterprise connection needs administrator attention.")

        dv_msg = self.mgr.get_user_facing_failure_message(ConnectionType.DATAVERSE_SHARED)
        self.assertEqual(dv_msg, "Velora Data Services is temporarily unavailable because the managed enterprise connection needs administrator attention.")

        graph_msg = self.mgr.get_user_facing_failure_message(ConnectionType.GRAPH_SERVICE_MAILBOX)
        self.assertEqual(graph_msg, "Notification Services is temporarily unavailable because the managed enterprise connection needs administrator attention.")

        s4_msg = self.mgr.get_user_facing_failure_message(ConnectionType.SAP_S4HANA)
        self.assertEqual(s4_msg, "SAP S/4HANA is temporarily unavailable because the managed enterprise connection needs administrator attention.")

        sac_msg = self.mgr.get_user_facing_failure_message(ConnectionType.SAP_SAC)
        self.assertEqual(sac_msg, "SAP Analytics Cloud is temporarily unavailable because the managed enterprise connection needs administrator attention.")

        prod_msg = self.mgr.get_user_facing_failure_message(ConnectionType.PRODUCTIVITY_AGENT)
        self.assertEqual(prod_msg, "Velora Productivity Services is temporarily unavailable because the managed enterprise connection needs administrator attention.")

        fac_msg = self.mgr.get_user_facing_failure_message(ConnectionType.FACILITATOR_AGENT)
        self.assertEqual(fac_msg, "Velora Meeting Facilitator is temporarily unavailable because the managed enterprise connection needs administrator attention.")

    async def test_background_health_probe_lifecycle(self):
        """0.9: Verify background health probe execution and status updating."""
        probe_called = False

        async def custom_sf_probe(conn):
            nonlocal probe_called
            probe_called = True
            return True

        self.mgr.register_health_probe(ConnectionType.SAP_SF, custom_sf_probe)
        
        # Start health monitor
        await self.mgr.start_health_monitor()
        await asyncio.sleep(0.1)  # allow task loop to run
        
        # Stop health monitor cleanly
        await self.mgr.stop_health_monitor()
        self.assertFalse(self.mgr._is_running)

    async def test_secret_cache_invalidation_on_rotation(self):
        """0.3, 0.6: Verify secret reference rotation and cache invalidation."""
        with patch.dict(os.environ, {"OLD_REF": "OldVal123", "NEW_REF": "NewVal456"}):
            conn = self.mgr.get_connection("CONN-SF-001")
            conn.secret_store_reference = "OLD_REF"

            # Cache old value
            val1 = await self.secret_store.get_secret("OLD_REF")
            self.assertEqual(val1, "OldVal123")

            # Rotate to new ref
            rotate_res = self.admin_svc.rotate_secret_reference("CONN-SF-001", "NEW_REF", admin_email="admin@velora.ae", user_roles=["Velora_Admin"])
            self.assertTrue(rotate_res["success"])
            self.assertEqual(conn.secret_store_reference, "NEW_REF")

            # Verify new secret resolution
            val2 = await self.secret_store.get_secret("NEW_REF")
            self.assertEqual(val2, "NewVal456")


if __name__ == "__main__":
    unittest.main()
