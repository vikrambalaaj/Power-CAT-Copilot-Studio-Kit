"""Unit tests for Centralized Dataverse Tool Authorization Architecture.

Tests:
1. Static default-deny registry enforcement
2. Direct user permission matching
3. Entra group permission matching
4. Expiration enforcement (valid_until)
5. Entity scoping enforcement
6. Fail-closed on Dataverse outage
7. Policy caching and cache invalidation
8. Audit trail emission
"""

import asyncio
from datetime import datetime, timedelta, timezone
import pytest

from shared_mcp.identity import VerifiedIdentity
from shared_mcp.tool_authorization import (
    AuthorizationDenied,
    DataversePolicyRepository,
    PolicyCache,
    ToolAuthorizer,
    ToolPermission,
    TOOL_ACTIONS,
)


class MockDataversePolicyRepository(DataversePolicyRepository):
    """In-memory mock of Dataverse Policy Repository for deterministic testing."""

    def __init__(self, policies=None, fail_on_query=False):
        super().__init__()
        self.policies = policies or []
        self.fail_on_query = fail_on_query
        self.list_calls = 0
        self.audit_log = []

    async def list_policies(self, tenant_id: str):
        self.list_calls += 1
        if self.fail_on_query:
            raise ConnectionError("Dataverse service temporarily unavailable")
        return [p for p in self.policies if p.tenant_id == tenant_id and p.enabled]

    async def log_audit(self, identity, tool_name, decision, reason, correlation_id=None):
        self.audit_log.append({
            "user_id": getattr(identity, "object_id", "anon"),
            "tool_name": tool_name,
            "decision": decision,
            "reason": reason,
            "correlation_id": correlation_id,
        })


@pytest.fixture
def test_identity():
    return VerifiedIdentity(
        tenant_id="7d167021-f5e9-4331-9b75-d44d55a1ce9b",
        object_id="user-executive-001",
        principal_type="user",
        client_application_id="velora-agent",
        roles={"Executive"},
        groups={"group-finance-execs", "group-hr-general"},
        display_email="executive@velora.ae",
    )


@pytest.mark.asyncio
async def test_static_registry_default_deny(test_identity):
    """A tool not in TOOL_ACTIONS must be denied even if present in Dataverse."""
    malicious_policy = ToolPermission(
        tool_name="unapproved_arbitrary_shell_tool",
        action="EXECUTE",
        tenant_id=test_identity.tenant_id,
        user_object_id=test_identity.object_id,
    )
    repo = MockDataversePolicyRepository(policies=[malicious_policy])
    authorizer = ToolAuthorizer(policy_repository=repo)

    with pytest.raises(AuthorizationDenied) as exc_info:
        await authorizer.authorize(test_identity, "unapproved_arbitrary_shell_tool")

    assert "not in approved static registry" in str(exc_info.value)
    assert len(repo.audit_log) == 1
    assert repo.audit_log[0]["decision"] == "DENY"


@pytest.mark.asyncio
async def test_user_permission_matching(test_identity):
    """Direct user object ID match authorizes the tool."""
    policy = ToolPermission(
        tool_name="search_mail",
        action="READ",
        tenant_id=test_identity.tenant_id,
        user_object_id=test_identity.object_id,
    )
    repo = MockDataversePolicyRepository(policies=[policy])
    authorizer = ToolAuthorizer(policy_repository=repo)

    result = await authorizer.authorize(test_identity, "search_mail")
    assert result is True
    assert len(repo.audit_log) == 1
    assert repo.audit_log[0]["decision"] == "ALLOW"


@pytest.mark.asyncio
async def test_group_permission_matching(test_identity):
    """Entra group ID match authorizes the tool."""
    policy = ToolPermission(
        tool_name="s4__get_receivables_aging",
        action="READ",
        tenant_id=test_identity.tenant_id,
        group_id="group-finance-execs",
        entity_scope="1000",
    )
    repo = MockDataversePolicyRepository(policies=[policy])
    authorizer = ToolAuthorizer(policy_repository=repo)

    result = await authorizer.authorize(test_identity, "s4__get_receivables_aging", entity_scope="1000")
    assert result is True
    assert repo.audit_log[-1]["decision"] == "ALLOW"


@pytest.mark.asyncio
async def test_entity_scope_mismatch_denied(test_identity):
    """Group matches, but requested entity scope does not match policy scope."""
    policy = ToolPermission(
        tool_name="s4__get_receivables_aging",
        action="READ",
        tenant_id=test_identity.tenant_id,
        group_id="group-finance-execs",
        entity_scope="1000",
    )
    repo = MockDataversePolicyRepository(policies=[policy])
    authorizer = ToolAuthorizer(policy_repository=repo)

    with pytest.raises(AuthorizationDenied):
        await authorizer.authorize(test_identity, "s4__get_receivables_aging", entity_scope="2000")

    assert repo.audit_log[-1]["decision"] == "DENY"


@pytest.mark.asyncio
async def test_expired_permission_denied(test_identity):
    """Policy past valid_until is ignored and denied."""
    past_time = datetime.now(timezone.utc) - timedelta(hours=1)
    policy = ToolPermission(
        tool_name="send_approved_email",
        action="WRITE",
        tenant_id=test_identity.tenant_id,
        user_object_id=test_identity.object_id,
        valid_until=past_time,
    )
    repo = MockDataversePolicyRepository(policies=[policy])
    authorizer = ToolAuthorizer(policy_repository=repo)

    with pytest.raises(AuthorizationDenied):
        await authorizer.authorize(test_identity, "send_approved_email")

    assert repo.audit_log[-1]["decision"] == "DENY"


@pytest.mark.asyncio
async def test_dataverse_outage_fails_closed(test_identity):
    """When Dataverse is unreachable, the authorizer must fail closed."""
    repo = MockDataversePolicyRepository(fail_on_query=True)
    authorizer = ToolAuthorizer(policy_repository=repo)

    with pytest.raises(AuthorizationDenied) as exc_info:
        await authorizer.authorize(test_identity, "search_mail")

    assert "Authorization service unavailable" in str(exc_info.value)


@pytest.mark.asyncio
async def test_policy_caching_and_invalidation(test_identity):
    """Policies are cached for TTL to prevent Dataverse bottlenecks."""
    policy = ToolPermission(
        tool_name="search_mail",
        action="READ",
        tenant_id=test_identity.tenant_id,
        user_object_id=test_identity.object_id,
    )
    repo = MockDataversePolicyRepository(policies=[policy])
    cache = PolicyCache(ttl_seconds=180)
    authorizer = ToolAuthorizer(policy_repository=repo, cache=cache)

    # First call loads from repository
    await authorizer.authorize(test_identity, "search_mail")
    assert repo.list_calls == 1

    # Second call uses cache
    await authorizer.authorize(test_identity, "search_mail")
    assert repo.list_calls == 1

    # Invalidate cache -> Third call re-fetches
    cache.invalidate(test_identity.tenant_id)
    await authorizer.authorize(test_identity, "search_mail")
    assert repo.list_calls == 2
