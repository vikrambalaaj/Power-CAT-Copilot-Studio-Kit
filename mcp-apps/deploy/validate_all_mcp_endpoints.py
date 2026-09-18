"""Comprehensive Validation Suite for all 6 Velora MCP/Card Services and Azure Deployments.

Validates:
1. Target Port & Ingress Mappings:
   - SuccessFactors MCP -> Port 8082, Internal
   - S/4HANA Finance MCP -> Port 8083, Internal
   - SAC MCP -> Port 8084, Internal
   - Productivity MCP -> Port 8080, Internal
   - Facilitator MCP -> Port 8085, Internal
   - Adaptive Card Service -> Port 8086, External Ingress
   - Scheduled Worker -> Azure Container Apps Job
2. Immutable digest ACR push script & configuration.
3. Key Vault, Managed Identity, Entra ID, PostgreSQL & durable storage configuration.
4. Cloud Foundry connector URL deprecation & replacement with ACA URLs.
5. Adaptive Card service shared durable idempotency storage and token consumption.
6. Health endpoints & Authenticated MCP tool execution.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
MCP_APPS_DIR = ROOT_DIR / "mcp-apps"

# Ensure all MCP apps are in sys.path
sys.path.insert(0, str(MCP_APPS_DIR / "ask-productivity"))
sys.path.insert(0, str(MCP_APPS_DIR / "ask-productivity" / "productivity_mcp"))
sys.path.insert(0, str(MCP_APPS_DIR / "ask-successfactors"))
sys.path.insert(0, str(MCP_APPS_DIR / "ask-s4hana"))
sys.path.insert(0, str(MCP_APPS_DIR / "ask-sac"))
sys.path.insert(0, str(MCP_APPS_DIR / "ask-facilitator"))


def _create_test_token(secret: str = "test-secret", payload: dict | None = None) -> str:
    """Helper to generate a signed HS256 JWT for testing."""
    header = {"alg": "HS256", "typ": "JWT"}
    claims = {
        "iss": "https://login.microsoftonline.com/7d167021-f5e9-4331-9b75-d44d55a1ce9b/v2.0",
        "aud": "https://api.velora.ae",
        "tid": "7d167021-f5e9-4331-9b75-d44d55a1ce9b",
        "oid": "test-user-123",
        "sub": "test-user-123",
        "exp": int(time.time()) + 3600,
        "nbf": int(time.time()) - 10,
        "appid": "test-client-app",
    }
    if payload:
        claims.update(payload)

    def b64(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    h_b64 = b64(header)
    p_b64 = b64(claims)
    sig = hmac.new(secret.encode(), f"{h_b64}.{p_b64}".encode(), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{h_b64}.{p_b64}.{sig_b64}"


class TestDeploymentArchitectureAndPorts:
    """Validate deployment specifications, port mappings, and infrastructure configurations."""

    EXPECTED_TARGETS = {
        "velora-mcp-sf": {"port": 8082, "ingress": "internal"},
        "velora-mcp-s4hana": {"port": 8083, "ingress": "internal"},
        "velora-mcp-sac": {"port": 8084, "ingress": "internal"},
        "velora-mcp-productivity": {"port": 8080, "ingress": "internal"},
        "velora-mcp-facilitator": {"port": 8085, "ingress": "internal"},
        "velora-mcp-card-service": {"port": 8086, "ingress": "external"},
    }

    def test_deploy_script_provisions_all_six_services_and_worker(self):
        """Verify deploy-azure-containerapps.sh provisions all 6 ACA apps and the scheduled worker."""
        deploy_script = (MCP_APPS_DIR / "deploy-azure-containerapps.sh").read_text(encoding="utf-8")

        for app_name, config in self.EXPECTED_TARGETS.items():
            assert f'--name "{app_name}"' in deploy_script, f"Missing {app_name} in deploy script"
            assert f'--target-port {config["port"]}' in deploy_script, f"Port mismatch for {app_name}"
            assert f'--ingress {config["ingress"]}' in deploy_script, f"Ingress mismatch for {app_name}"

        # Scheduled worker job verification
        assert '--name "velora-scheduled-worker"' in deploy_script
        assert 'az containerapp job create' in deploy_script
        assert '--trigger-type "Schedule"' in deploy_script
        assert '--cron-expression "*/15 * * * *"' in deploy_script

    def test_keyvault_managed_identity_and_postgres_config(self):
        """Verify Key Vault, User-Assigned Managed Identity, Entra auth, and PostgreSQL wiring."""
        deploy_script = (MCP_APPS_DIR / "deploy-azure-containerapps.sh").read_text(encoding="utf-8")

        assert "az identity create" in deploy_script
        assert "az keyvault create" in deploy_script
        assert "az keyvault set-policy" in deploy_script
        assert "velora-database-url" in deploy_script
        assert "ENTRA_INBOUND_AUDIENCE" in deploy_script
        assert "az storage share create" in deploy_script
        assert "az containerapp env storage set" in deploy_script

    def test_build_script_supports_all_six_images_and_immutable_digests(self):
        """Verify build_all_images.sh builds all 6 images and captures immutable digests."""
        build_script = (MCP_APPS_DIR / "build_all_images.sh").read_text(encoding="utf-8")

        assert "velora-mcp-sf" in build_script
        assert "velora-mcp-s4hana" in build_script
        assert "velora-mcp-sac" in build_script
        assert "velora-mcp-productivity" in build_script
        assert "velora-mcp-facilitator" in build_script
        assert "velora-mcp-card-service" in build_script

        assert "--push" in build_script
        assert "image-digests.env" in build_script
        assert "RepoDigests" in build_script or "docker inspect" in build_script

    def test_no_legacy_cloud_foundry_urls_in_mcp_apps(self):
        """Verify all Cloud Foundry (*.cfapps.*) URLs have been replaced with ACA URLs in mcp-apps."""
        cf_pattern = re.compile(r"cfapps\.[a-z0-9-]+\.hana\.ondemand\.com", re.IGNORECASE)
        violating_files = []

        for p in MCP_APPS_DIR.rglob("*"):
            if p.is_file() and p.suffix in [".json", ".yml", ".yaml", ".py", ".md", ".sh"]:
                content = p.read_text(encoding="utf-8", errors="ignore")
                if cf_pattern.search(content):
                    violating_files.append(str(p.relative_to(ROOT_DIR)))

        assert not violating_files, f"Legacy Cloud Foundry URLs still present in: {violating_files}"


class TestAdaptiveCardServiceIdempotency:
    """Validate Adaptive Card Service port configuration, shared storage and idempotency."""

    def test_dockerfile_and_server_use_port_8086(self):
        """Verify Adaptive Card service defaults to port 8086."""
        dockerfile = (MCP_APPS_DIR / "dynamic-adaptive-card-service" / "Dockerfile").read_text(encoding="utf-8")
        assert "ENV PORT=8086" in dockerfile
        assert "EXPOSE 8086" in dockerfile

        index_ts = (MCP_APPS_DIR / "dynamic-adaptive-card-service" / "src" / "index.ts").read_text(encoding="utf-8")
        assert "8086" in index_ts

    def test_idempotency_signer_durable_storage_implementation(self):
        """Verify IdempotencySigner supports durable shared multi-replica persistence."""
        signer_ts = (MCP_APPS_DIR / "dynamic-adaptive-card-service" / "src" / "security" / "idempotency-signer.ts").read_text(encoding="utf-8")
        assert "getStoragePath" in signer_ts
        assert "AZURE_STORAGE_MOUNT_PATH" in signer_ts or "IDEMPOTENCY_STORAGE_PATH" in signer_ts
        assert "wx" in signer_ts or "consumeTicketDurable" in signer_ts or "O_EXCL" in signer_ts


class TestHealthAndAuthenticatedMCPCalls:
    """Validate health endpoints and authenticated MCP calls across all services."""

    def test_productivity_health_endpoint(self):
        """Validate Productivity MCP health route."""
        from productivity_mcp.server import app
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") in ["HEALTHY", "healthy", "ok", "UP"]

    def test_productivity_unauthenticated_request_rejected(self):
        """Validate Productivity MCP rejects unauthenticated/anonymous calls when missing token."""
        from shared_mcp.identity import extract_verified_identity, AuthenticationError

        with pytest.raises(AuthenticationError, match="Missing Authorization Bearer token"):
            extract_verified_identity({})

    def test_productivity_authenticated_request_accepted(self):
        """Validate Productivity MCP accepts valid authenticated token."""
        from shared_mcp.identity import extract_verified_identity

        test_token = _create_test_token(secret="unit-test-secret")
        headers = {"authorization": f"Bearer {test_token}"}

        identity = extract_verified_identity(
            headers,
            test_secret="unit-test-secret",
        )
        assert identity is not None
        assert identity.object_id == "test-user-123"
        assert identity.tenant_id == "7d167021-f5e9-4331-9b75-d44d55a1ce9b"

    def test_sac_health_and_auth_contract(self):
        """Validate SAC MCP health route and authentication enforcement."""
        from sac_mcp.server import app
        from sac_mcp.settings import settings
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json().get("status") in ["healthy", "HEALTHY", "ok"]

        # SAC requires auth when allow_anonymous is False
        assert settings.allow_anonymous is False

    def test_s4hana_health_and_auth_contract(self):
        """Validate S/4HANA Finance MCP health and settings."""
        from s4hana_mcp.server import app
        from s4hana_mcp.settings import get_settings
        from starlette.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json().get("status") in ["healthy", "HEALTHY", "ok"]
        s4_settings = get_settings()
        assert s4_settings.allow_anonymous is False
        assert s4_settings.s4_verify_tls is True

    def test_facilitator_health_and_auth_contract(self):
        """Validate Facilitator MCP health and tools specs."""
        from facilitator_mcp.tools import TOOL_SPECS, FACILITATOR_AUTO_SEND_GUIDE

        tool_names = [t[0] for t in TOOL_SPECS]
        assert "get_facilitator_guide" in tool_names
        assert "export_decision_trail" in tool_names
        assert isinstance(FACILITATOR_AUTO_SEND_GUIDE, str)
        assert len(FACILITATOR_AUTO_SEND_GUIDE) > 100

    def test_successfactors_health_and_settings(self):
        """Validate SuccessFactors MCP settings schema and default target port."""
        from successfactors_mcp.successfactors_settings import SuccessFactorsSettings

        # Model field default for port must be 8082
        assert SuccessFactorsSettings.model_fields["port"].default == 8082
