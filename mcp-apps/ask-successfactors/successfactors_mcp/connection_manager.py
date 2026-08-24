"""Velora Enterprise Connection Manager (Phase 0).

Provides centralized, administrator-managed enterprise connection ownership,
deterministic runtime resolution, secure secret-store integration, background
health monitoring, and user-safe failure handling across Development, UAT,
and Production environments.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("connection_manager")


class ConnectionType(str, enum.Enum):
    SAP_SF = "SAP_SF"
    SAP_S4HANA = "SAP_S4HANA"
    SAP_SAC = "SAP_SAC"
    DATAVERSE_SHARED = "DATAVERSE_SHARED"
    DATAVERSE_ADMIN = "DATAVERSE_ADMIN"
    GRAPH_SERVICE_MAILBOX = "GRAPH_SERVICE_MAILBOX"
    GRAPH_USER_DELEGATED = "GRAPH_USER_DELEGATED"


class ReadWriteClassification(str, enum.Enum):
    READ_ONLY = "READ_ONLY"
    ADMIN_WRITE = "ADMIN_WRITE"
    NOTIFICATION_WRITE = "NOTIFICATION_WRITE"
    USER_CONTEXT = "USER_CONTEXT"


class AuthType(str, enum.Enum):
    OAUTH2_CLIENT_CREDENTIALS = "OAuth2_ClientCredentials"
    BASIC_SERVICE_ACCOUNT = "Basic_ServiceAccount"
    MANAGED_IDENTITY = "ManagedIdentity"
    CERTIFICATE = "Certificate"
    DELEGATED_BEARER = "DelegatedBearer"


class ConnectionHealthStatus(str, enum.Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    EXPIRING_SOON = "EXPIRING_SOON"
    AUTH_FAILED = "AUTH_FAILED"
    PERMISSION_FAILED = "PERMISSION_FAILED"
    DISABLED = "DISABLED"
    CONFIG_INCOMPLETE = "CONFIG_INCOMPLETE"


@dataclass
class EnterpriseConnection:
    """Represents an administrator-managed enterprise connection record."""
    connection_id: str
    connection_name: str
    connection_type: ConnectionType
    environment: str  # "Development", "UAT", "Production"
    data_source_url: str
    connection_owner: str
    client_id: Optional[str] = None
    tenant_id: Optional[str] = None
    dataverse_connection_reference: Optional[str] = None
    secret_store_reference: str = ""  # Key Vault secret URI or environment variable key
    auth_type: AuthType = AuthType.OAUTH2_CLIENT_CREDENTIALS
    granted_scopes: List[str] = field(default_factory=list)
    read_write_classification: ReadWriteClassification = ReadWriteClassification.READ_ONLY
    agent_assignments: List[str] = field(default_factory=list)
    status: ConnectionHealthStatus = ConnectionHealthStatus.HEALTHY
    last_successful_validation: Optional[str] = None
    last_failure_message: Optional[str] = None
    last_failure_timestamp: Optional[str] = None
    token_expiry_timestamp: Optional[str] = None
    rotation_due_date: Optional[str] = None
    created_by: str = "system_admin@velora.ae"
    modified_by: str = "system_admin@velora.ae"
    enabled: bool = True
    health_check_interval_seconds: int = 300
    custom_properties: Dict[str, Any] = field(default_factory=dict)

    def is_active(self) -> bool:
        return self.enabled and self.status in (
            ConnectionHealthStatus.HEALTHY,
            ConnectionHealthStatus.EXPIRING_SOON,
            ConnectionHealthStatus.DEGRADED,
        )


class SecretStoreProvider:
    """Resolves secret references securely without storing plaintext credentials in Dataverse."""

    def __init__(self, keyvault_url: Optional[str] = None) -> None:
        self.keyvault_url = keyvault_url or os.getenv("AZURE_KEYVAULT_URL", "")
        self._secret_cache: Dict[str, tuple[str, float]] = {}
        self._cache_ttl_seconds = 300.0

    async def get_secret(self, secret_ref: str) -> str:
        """Resolve secret by reference name or URI."""
        if not secret_ref:
            return ""

        now = time.time()
        if secret_ref in self._secret_cache:
            val, expiry = self._secret_cache[secret_ref]
            if now < expiry:
                return val

        # 1. Check environment variable alias
        env_val = os.getenv(secret_ref)
        if env_val:
            self._secret_cache[secret_ref] = (env_val, now + self._cache_ttl_seconds)
            return env_val

        # 2. Check direct standard environment keys
        fallback_mappings = {
            "SF_PASSWORD_REF": "SF_PASSWORD",
            "SF_CLIENT_SECRET_REF": "SF_CLIENT_SECRET",
            "DATAVERSE_CLIENT_SECRET_REF": "DATAVERSE_CLIENT_SECRET",
            "GRAPH_CLIENT_SECRET_REF": "GRAPH_CLIENT_SECRET",
            "S4HANA_PASSWORD_REF": "S4HANA_PASSWORD",
            "SAC_PASSWORD_REF": "SAC_PASSWORD",
        }
        fallback_env = fallback_mappings.get(secret_ref)
        if fallback_env and os.getenv(fallback_env):
            resolved = os.getenv(fallback_env, "")
            self._secret_cache[secret_ref] = (resolved, now + self._cache_ttl_seconds)
            return resolved

        logger.warning(f"Secret reference '{secret_ref}' could not be resolved from secure store.")
        return ""

    def invalidate_cache(self, secret_ref: Optional[str] = None) -> None:
        if secret_ref:
            self._secret_cache.pop(secret_ref, None)
        else:
            self._secret_cache.clear()


class ConnectionManager:
    """Manages enterprise connection registry, deterministic resolution, and background health checks."""

    def __init__(
        self,
        secret_store: Optional[SecretStoreProvider] = None,
        default_environment: Optional[str] = None,
    ) -> None:
        self.secret_store = secret_store or SecretStoreProvider()
        self.default_environment = default_environment or os.getenv("DEPLOYMENT_ENVIRONMENT", "Development")
        self._connections: Dict[str, EnterpriseConnection] = {}
        self._logical_references: Dict[str, Dict[str, str]] = {}  # {ref_name: {environment: connection_id}}
        self._health_check_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._health_probes: Dict[ConnectionType, Callable[[EnterpriseConnection], Any]] = {}

        self._seed_default_connections()

    def _seed_default_connections(self) -> None:
        """Seed canonical enterprise connections with secure secret references."""
        # 1. SAP SuccessFactors Connection (Shared Read-Only)
        sf_conn = EnterpriseConnection(
            connection_id="CONN-SF-001",
            connection_name="Velora SuccessFactors Connection",
            connection_type=ConnectionType.SAP_SF,
            environment=self.default_environment,
            data_source_url=os.getenv("SF_API_URL", "https://api22preview.sapsf.com/odata/v2"),
            connection_owner="admin.hr@velora.ae",
            client_id=os.getenv("SF_USERNAME", "service-user"),
            tenant_id=os.getenv("SF_COMPANY_ID", "company"),
            dataverse_connection_reference="velora_cr_successfactors",
            secret_store_reference="SF_PASSWORD_REF",
            auth_type=AuthType.BASIC_SERVICE_ACCOUNT,
            granted_scopes=["EmpJob.Read", "User.Read", "PerPersonal.Read", "FODepartment.Read"],
            read_write_classification=ReadWriteClassification.READ_ONLY,
            agent_assignments=["velora-hcm-agent", "velora-executive-agent"],
            status=ConnectionHealthStatus.HEALTHY,
            enabled=True,
            health_check_interval_seconds=300,
        )
        self.register_connection(sf_conn, logical_reference="Velora SuccessFactors Connection")

        # 2. Dataverse Shared Connection (Audit & Policy Read)
        dv_shared = EnterpriseConnection(
            connection_id="CONN-DV-SHARED-001",
            connection_name="Velora Dataverse Shared Connection",
            connection_type=ConnectionType.DATAVERSE_SHARED,
            environment=self.default_environment,
            data_source_url=os.getenv("DATAVERSE_URL", "https://org123.crm4.dynamics.com"),
            connection_owner="admin.security@velora.ae",
            client_id=os.getenv("DATAVERSE_CLIENT_ID", "sp-velora-agent"),
            tenant_id=os.getenv("DATAVERSE_TENANT_ID", "velora-tenant-id"),
            dataverse_connection_reference="velora_cr_dataverse_shared",
            secret_store_reference="DATAVERSE_CLIENT_SECRET_REF",
            auth_type=AuthType.OAUTH2_CLIENT_CREDENTIALS,
            granted_scopes=["AuditLog.Create", "AuditLog.Read", "DisclosurePolicy.Read"],
            read_write_classification=ReadWriteClassification.READ_ONLY,
            agent_assignments=["velora-hcm-agent", "velora-executive-agent"],
            status=ConnectionHealthStatus.HEALTHY,
            enabled=True,
            health_check_interval_seconds=300,
        )
        self.register_connection(dv_shared, logical_reference="Velora Dataverse Connection")

        # 3. Dataverse Policy Admin Connection (Privileged)
        dv_admin = EnterpriseConnection(
            connection_id="CONN-DV-ADMIN-001",
            connection_name="Velora Dataverse Policy Admin Connection",
            connection_type=ConnectionType.DATAVERSE_ADMIN,
            environment=self.default_environment,
            data_source_url=os.getenv("DATAVERSE_URL", "https://org123.crm4.dynamics.com"),
            connection_owner="ciso.admin@velora.ae",
            client_id=os.getenv("DATAVERSE_ADMIN_CLIENT_ID", "sp-velora-policy-admin"),
            tenant_id=os.getenv("DATAVERSE_TENANT_ID", "velora-tenant-id"),
            dataverse_connection_reference="velora_cr_dataverse_admin",
            secret_store_reference="DATAVERSE_ADMIN_CLIENT_SECRET_REF",
            auth_type=AuthType.OAUTH2_CLIENT_CREDENTIALS,
            granted_scopes=["DisclosurePolicy.Admin", "DisclosurePolicy.Write"],
            read_write_classification=ReadWriteClassification.ADMIN_WRITE,
            agent_assignments=["velora-policy-admin"],
            status=ConnectionHealthStatus.HEALTHY,
            enabled=True,
            health_check_interval_seconds=600,
        )
        self.register_connection(dv_admin, logical_reference="Velora Dataverse Admin Connection")

        # 4. Graph Service Mailbox Connection (Dedicated Notifications)
        graph_conn = EnterpriseConnection(
            connection_id="CONN-GRAPH-MAIL-001",
            connection_name="Velora Graph Service Mailbox Connection",
            connection_type=ConnectionType.GRAPH_SERVICE_MAILBOX,
            environment=self.default_environment,
            data_source_url="https://graph.microsoft.com/v1.0",
            connection_owner="admin.it@velora.ae",
            client_id=os.getenv("GRAPH_CLIENT_ID", "sp-velora-graph"),
            tenant_id=os.getenv("GRAPH_TENANT_ID", "velora-tenant-id"),
            dataverse_connection_reference="velora_cr_graph_mailbox",
            secret_store_reference="GRAPH_CLIENT_SECRET_REF",
            auth_type=AuthType.OAUTH2_CLIENT_CREDENTIALS,
            granted_scopes=["Mail.Send.RestrictedToServiceMailbox"],
            read_write_classification=ReadWriteClassification.NOTIFICATION_WRITE,
            agent_assignments=["velora-executive-agent"],
            status=ConnectionHealthStatus.HEALTHY,
            enabled=True,
            health_check_interval_seconds=300,
            custom_properties={"service_mailbox": "svc_aiagent@velora.ae"},
        )
        self.register_connection(graph_conn, logical_reference="Velora Service Mailbox Connection")

    def register_connection(self, conn: EnterpriseConnection, logical_reference: Optional[str] = None) -> None:
        """Register or update a managed enterprise connection."""
        self._connections[conn.connection_id] = conn
        if logical_reference:
            if logical_reference not in self._logical_references:
                self._logical_references[logical_reference] = {}
            self._logical_references[logical_reference][conn.environment] = conn.connection_id

    def get_connection(self, connection_id: str) -> Optional[EnterpriseConnection]:
        return self._connections.get(connection_id)

    def list_connections(self, environment: Optional[str] = None) -> List[EnterpriseConnection]:
        conns = list(self._connections.values())
        if environment:
            conns = [c for c in conns if c.environment.lower() == environment.lower()]
        return conns

    def resolve_connection(
        self,
        reference_or_name: str,
        environment: Optional[str] = None,
        agent_id: Optional[str] = None,
        require_admin: bool = False,
    ) -> Optional[EnterpriseConnection]:
        """Deterministically resolve active enterprise connection by logical reference and environment."""
        env = environment or self.default_environment

        # 1. Direct lookup by ID
        if reference_or_name in self._connections:
            conn = self._connections[reference_or_name]
            if conn.environment.lower() == env.lower():
                return self._validate_and_return(conn, agent_id, require_admin)

        # 2. Lookup by logical reference map
        if reference_or_name in self._logical_references:
            env_map = self._logical_references[reference_or_name]
            target_id = env_map.get(env) or env_map.get(self.default_environment)
            if target_id and target_id in self._connections:
                return self._validate_and_return(self._connections[target_id], agent_id, require_admin)

        # 3. Lookup by Connection Name
        for conn in self._connections.values():
            if conn.connection_name.lower() == reference_or_name.lower() and conn.environment.lower() == env.lower():
                return self._validate_and_return(conn, agent_id, require_admin)

        logger.warning(f"Could not resolve connection reference '{reference_or_name}' for environment '{env}'")
        return None

    def _validate_and_return(
        self,
        conn: EnterpriseConnection,
        agent_id: Optional[str] = None,
        require_admin: bool = False,
    ) -> Optional[EnterpriseConnection]:
        # Privilege separation check
        if not require_admin and conn.read_write_classification == ReadWriteClassification.ADMIN_WRITE:
            logger.error(f"Attempted to use privileged admin connection '{conn.connection_id}' in normal user context.")
            return None

        # Agent assignment check
        if agent_id and conn.agent_assignments and agent_id not in conn.agent_assignments:
            logger.warning(f"Agent '{agent_id}' is not assigned to connection '{conn.connection_id}'.")
            return None

        return conn

    async def get_resolved_credentials(self, conn: EnterpriseConnection) -> Dict[str, Any]:
        """Retrieve connection secrets safely via SecretStoreProvider."""
        secret_val = await self.secret_store.get_secret(conn.secret_store_reference)
        return {
            "connection_id": conn.connection_id,
            "client_id": conn.client_id,
            "tenant_id": conn.tenant_id,
            "data_source_url": conn.data_source_url,
            "secret": secret_val,
            "auth_type": conn.auth_type,
            "scopes": conn.granted_scopes,
        }

    def set_connection_status(
        self,
        connection_id: str,
        status: ConnectionHealthStatus,
        error_message: Optional[str] = None,
    ) -> None:
        """Update connection status and failure audit trail."""
        conn = self._connections.get(connection_id)
        if not conn:
            return

        conn.status = status
        now_str = datetime.now(timezone.utc).isoformat()
        if status == ConnectionHealthStatus.HEALTHY:
            conn.last_successful_validation = now_str
            conn.last_failure_message = None
        else:
            conn.last_failure_timestamp = now_str
            conn.last_failure_message = error_message or f"Connection entered status {status.value}"

    def disable_connection(self, connection_id: str, admin_email: str) -> bool:
        """Instantly disable an enterprise connection (operational kill-switch)."""
        conn = self._connections.get(connection_id)
        if not conn:
            return False
        conn.enabled = False
        conn.status = ConnectionHealthStatus.DISABLED
        conn.modified_by = admin_email
        logger.info(f"Enterprise connection '{connection_id}' was disabled by '{admin_email}'.")
        return True

    def enable_connection(self, connection_id: str, admin_email: str) -> bool:
        """Re-enable a previously disabled enterprise connection."""
        conn = self._connections.get(connection_id)
        if not conn:
            return False
        conn.enabled = True
        conn.status = ConnectionHealthStatus.HEALTHY
        conn.modified_by = admin_email
        logger.info(f"Enterprise connection '{connection_id}' was enabled by '{admin_email}'.")
        return True

    def get_user_facing_failure_message(self, conn_type: ConnectionType) -> str:
        """Standardized user-facing error message without raw technical details (Phase 0.10)."""
        system_names = {
            ConnectionType.SAP_SF: "SuccessFactors",
            ConnectionType.SAP_S4HANA: "SAP S/4HANA",
            ConnectionType.SAP_SAC: "SAP Analytics Cloud",
            ConnectionType.DATAVERSE_SHARED: "Velora Data Services",
            ConnectionType.DATAVERSE_ADMIN: "Governance Services",
            ConnectionType.GRAPH_SERVICE_MAILBOX: "Notification Services",
        }
        name = system_names.get(conn_type, "The enterprise data service")
        return f"{name} is temporarily unavailable because the managed enterprise connection needs administrator attention."

    def register_health_probe(
        self,
        conn_type: ConnectionType,
        probe_fn: Callable[[EnterpriseConnection], Any],
    ) -> None:
        self._health_probes[conn_type] = probe_fn

    async def start_health_monitor(self) -> None:
        """Start the background connection health monitor."""
        if self._is_running:
            return
        self._is_running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("Connection Manager background health monitor started.")

    async def stop_health_monitor(self) -> None:
        self._is_running = False
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        logger.info("Connection Manager background health monitor stopped.")

    async def _health_check_loop(self) -> None:
        while self._is_running:
            try:
                for conn in list(self._connections.values()):
                    if not conn.enabled:
                        continue
                    probe = self._health_probes.get(conn.connection_type)
                    if probe:
                        try:
                            if asyncio.iscoroutinefunction(probe):
                                res = await probe(conn)
                            else:
                                res = probe(conn)
                            if res:
                                self.set_connection_status(conn.connection_id, ConnectionHealthStatus.HEALTHY)
                            else:
                                self.set_connection_status(conn.connection_id, ConnectionHealthStatus.DEGRADED, "Health probe returned non-truthy.")
                        except Exception as probe_err:
                            logger.warning(f"Health probe failed for connection {conn.connection_id}: {probe_err}")
                            self.set_connection_status(conn.connection_id, ConnectionHealthStatus.AUTH_FAILED, str(probe_err))
                    else:
                        # Default check: verify secret reference resolution
                        secret = await self.secret_store.get_secret(conn.secret_store_reference)
                        if secret:
                            self.set_connection_status(conn.connection_id, ConnectionHealthStatus.HEALTHY)
                        else:
                            self.set_connection_status(conn.connection_id, ConnectionHealthStatus.CONFIG_INCOMPLETE, "Missing secret resolution.")
            except Exception as e:
                logger.error(f"Error in connection health monitor loop: {e}", exc_info=True)

            await asyncio.sleep(60)


_GLOBAL_CONNECTION_MANAGER: Optional[ConnectionManager] = None


def get_connection_manager() -> ConnectionManager:
    """Retrieve global singleton ConnectionManager."""
    global _GLOBAL_CONNECTION_MANAGER
    if _GLOBAL_CONNECTION_MANAGER is None:
        _GLOBAL_CONNECTION_MANAGER = ConnectionManager()
    return _GLOBAL_CONNECTION_MANAGER


def set_connection_manager(mgr: ConnectionManager) -> None:
    global _GLOBAL_CONNECTION_MANAGER
    _GLOBAL_CONNECTION_MANAGER = mgr
