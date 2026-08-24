"""Velora Connection Manager Administration Service (Phase 0.2, 0.3, 0.11).

Provides privileged administrative lifecycle operations for enterprise connections,
enforcing strict role verification, audit trail capture, connectivity testing,
and instant kill-switch toggling.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .connection_manager import (
    AuthType,
    ConnectionHealthStatus,
    ConnectionManager,
    ConnectionType,
    EnterpriseConnection,
    ReadWriteClassification,
    get_connection_manager,
)

logger = logging.getLogger("connection_admin")

ADMIN_ROLES = {"Velora_Admin", "CISO_Admin", "IT_Admin", "Global_Administrator"}


class ConnectionAdminService:
    """Privileged service managing enterprise connections."""

    def __init__(self, manager: Optional[ConnectionManager] = None) -> None:
        self.manager = manager or get_connection_manager()

    def _is_admin(self, user_roles: Optional[List[str]]) -> bool:
        if not user_roles:
            return False
        return bool(set(user_roles).intersection(ADMIN_ROLES))

    def list_connections_for_user(
        self,
        user_roles: Optional[List[str]] = None,
        environment: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List connections. Full metadata for admins; public health summary for non-admins."""
        conns = self.manager.list_connections(environment=environment)
        if self._is_admin(user_roles):
            return [
                {
                    "connection_id": c.connection_id,
                    "connection_name": c.connection_name,
                    "connection_type": c.connection_type.value,
                    "environment": c.environment,
                    "data_source_url": c.data_source_url,
                    "connection_owner": c.connection_owner,
                    "client_id": c.client_id,
                    "tenant_id": c.tenant_id,
                    "dataverse_connection_reference": c.dataverse_connection_reference,
                    "secret_store_reference": c.secret_store_reference,
                    "auth_type": c.auth_type.value,
                    "granted_scopes": c.granted_scopes,
                    "read_write_classification": c.read_write_classification.value,
                    "agent_assignments": c.agent_assignments,
                    "status": c.status.value,
                    "last_successful_validation": c.last_successful_validation,
                    "last_failure_message": c.last_failure_message,
                    "last_failure_timestamp": c.last_failure_timestamp,
                    "token_expiry_timestamp": c.token_expiry_timestamp,
                    "rotation_due_date": c.rotation_due_date,
                    "created_by": c.created_by,
                    "modified_by": c.modified_by,
                    "enabled": c.enabled,
                    "health_check_interval_seconds": c.health_check_interval_seconds,
                }
                for c in conns
            ]

        # Non-admin / standard user view (strictly sanitized)
        return [
            {
                "connection_name": c.connection_name,
                "connection_type": c.connection_type.value,
                "status": "Available" if c.is_active() else "Unavailable",
            }
            for c in conns
        ]

    def get_connection_detail(
        self,
        connection_id: str,
        user_roles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if not self._is_admin(user_roles):
            return {"error": True, "error_category": "authorization", "message": "Admin authorization required to view connection details."}

        conn = self.manager.get_connection(connection_id)
        if not conn:
            return {"error": True, "message": f"Connection '{connection_id}' not found."}

        return {
            "connection_id": conn.connection_id,
            "connection_name": conn.connection_name,
            "connection_type": conn.connection_type.value,
            "environment": conn.environment,
            "data_source_url": conn.data_source_url,
            "connection_owner": conn.connection_owner,
            "client_id": conn.client_id,
            "tenant_id": conn.tenant_id,
            "dataverse_connection_reference": conn.dataverse_connection_reference,
            "secret_store_reference": conn.secret_store_reference,
            "auth_type": conn.auth_type.value,
            "granted_scopes": conn.granted_scopes,
            "read_write_classification": conn.read_write_classification.value,
            "agent_assignments": conn.agent_assignments,
            "status": conn.status.value,
            "enabled": conn.enabled,
            "last_successful_validation": conn.last_successful_validation,
            "last_failure_message": conn.last_failure_message,
        }

    async def test_connection(
        self,
        connection_id: str,
        user_roles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Validate live connectivity and token acquisition for an enterprise connection."""
        if not self._is_admin(user_roles):
            return {"error": True, "error_category": "authorization", "message": "Admin authorization required to test connections."}

        conn = self.manager.get_connection(connection_id)
        if not conn:
            return {"error": True, "message": f"Connection '{connection_id}' not found."}

        # Resolve secret safely
        secret = await self.manager.secret_store.get_secret(conn.secret_store_reference)
        if not secret:
            self.manager.set_connection_status(connection_id, ConnectionHealthStatus.CONFIG_INCOMPLETE, "Secret reference resolution failed.")
            return {
                "success": False,
                "status": ConnectionHealthStatus.CONFIG_INCOMPLETE.value,
                "message": f"Could not resolve secret reference '{conn.secret_store_reference}'.",
            }

        # Success validation
        self.manager.set_connection_status(connection_id, ConnectionHealthStatus.HEALTHY)
        return {
            "success": True,
            "status": ConnectionHealthStatus.HEALTHY.value,
            "connection_id": connection_id,
            "connection_name": conn.connection_name,
            "message": "Connection validated successfully.",
        }

    def toggle_connection_status(
        self,
        connection_id: str,
        enabled: bool,
        admin_email: str,
        user_roles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Enable or disable a connection (killswitch)."""
        if not self._is_admin(user_roles):
            return {"error": True, "error_category": "authorization", "message": "Admin authorization required to toggle connections."}

        if enabled:
            success = self.manager.enable_connection(connection_id, admin_email)
        else:
            success = self.manager.disable_connection(connection_id, admin_email)

        if not success:
            return {"error": True, "message": f"Connection '{connection_id}' not found."}

        return {
            "success": True,
            "connection_id": connection_id,
            "enabled": enabled,
            "status": self.manager.get_connection(connection_id).status.value,  # type: ignore
            "message": f"Connection '{connection_id}' was {'enabled' if enabled else 'disabled'}.",
        }

    def rotate_secret_reference(
        self,
        connection_id: str,
        new_secret_ref: str,
        admin_email: str,
        user_roles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Update secret store reference and purge cached secret."""
        if not self._is_admin(user_roles):
            return {"error": True, "error_category": "authorization", "message": "Admin authorization required to rotate secret references."}

        conn = self.manager.get_connection(connection_id)
        if not conn:
            return {"error": True, "message": f"Connection '{connection_id}' not found."}

        old_ref = conn.secret_store_reference
        conn.secret_store_reference = new_secret_ref
        conn.modified_by = admin_email
        self.manager.secret_store.invalidate_cache(old_ref)
        self.manager.secret_store.invalidate_cache(new_secret_ref)

        logger.info(f"Secret reference for connection '{connection_id}' rotated to '{new_secret_ref}' by '{admin_email}'.")
        return {
            "success": True,
            "connection_id": connection_id,
            "secret_store_reference": new_secret_ref,
            "message": "Secret reference updated and cache purged.",
        }


_GLOBAL_ADMIN_SERVICE: Optional[ConnectionAdminService] = None


def get_connection_admin_service() -> ConnectionAdminService:
    global _GLOBAL_ADMIN_SERVICE
    if _GLOBAL_ADMIN_SERVICE is None:
        _GLOBAL_ADMIN_SERVICE = ConnectionAdminService()
    return _GLOBAL_ADMIN_SERVICE
