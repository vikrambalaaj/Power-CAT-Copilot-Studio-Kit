"""Comprehensive tests for Dataverse MCP Server & Tool Access Priority Matrix.

Validates:
1. Priority Matrix Evaluation Ordering (lower integer priority rank has strict precedence).
2. Specificity Tie-Breaking (exact user > role > wildcard; specific tool > wildcard).
3. Zero-Trust Fail-Closed Default (unmatched calls are DENIED).
4. Runtime Authorization Enforcement via `enforce_mcp_policy` raising AuthorizationError.
5. Permission Matrix Inspection via `get_effective_matrix` and the Handoff API (`GET_MCP_ACCESS_MATRIX`).
"""
import pytest
from shared_mcp.identity import VerifiedIdentity, AuthorizationError
from shared_mcp.policy_matrix import (
    McpPolicyRule,
    PolicyMatrixEngine,
    enforce_mcp_policy,
    get_policy_matrix_engine,
)


@pytest.fixture
def clean_engine():
    """Create a fresh PolicyMatrixEngine with default enterprise rules."""
    engine = PolicyMatrixEngine()
    return engine


def test_default_enterprise_matrix_admin_access(clean_engine):
    """Platform administrators with Velora_Admin role should have Priority 10 unrestricted access."""
    admin_ident = VerifiedIdentity(
        tenant_id="velora-tenant",
        object_id="admin-user-001",
        principal_type="user",
        client_application_id="portal",
        roles={"Velora_Admin"},
        display_email="admin@velora.ae",
    )

    decision = clean_engine.evaluate_access(
        user_email=admin_ident.display_email,
        user_oid=admin_ident.object_id,
        roles=admin_ident.roles,
        is_admin=admin_ident.is_admin,
        mcp_server="ask-productivity",
        tool_name="send_executive_email",
    )
    assert decision.allowed is True
    assert decision.matched_rule.priority == 10
    assert decision.matched_rule.role == "Velora_Admin"


def test_amurugan_exclusive_priority_1_all_data_access(clean_engine):
    """Bala Murugan (amurugan@velora.ae) must have Priority 1 exclusive full access across all servers and tools."""
    amurugan_ident = VerifiedIdentity(
        tenant_id="7d167021-f5e9-4331-9b75-d44d55a1ce9b",
        object_id="ec8aeb61-ad58-4250-bda8-14fec68e9b08",
        principal_type="user",
        client_application_id="copilot",
        roles=set(), # Even without explicit admin or executive roles
        display_email="amurugan@velora.ae",
    )

    # Test all MCP servers: productivity, successfactors, s4hana, facilitator, sac
    for server in ["ask-productivity", "ask-successfactors", "ask-s4hana", "ask-facilitator", "ask-sac"]:
        decision = clean_engine.evaluate_access(
            user_email=amurugan_ident.display_email,
            user_oid=amurugan_ident.object_id,
            roles=amurugan_ident.roles,
            is_admin=amurugan_ident.is_admin,
            mcp_server=server,
            tool_name="any_sensitive_tool",
        )
        assert decision.allowed is True
        assert decision.matched_rule.priority == 1
        assert "murugan" in decision.matched_rule.name.lower()
        assert decision.matched_rule.user_principal == "amurugan@velora.ae"


def test_priority_override_lower_number_wins(clean_engine):
    """Lower priority number (e.g. 5) strictly overrides higher priority number (e.g. 20)."""
    # Add high-priority DENY rule (Priority 5) for a specific executive
    clean_engine.add_rule(
        McpPolicyRule(
            policy_id="test-deny-001",
            name="Block Executive from S4 HANA Modifications",
            priority=5,
            user_principal="restricted_exec@velora.ae",
            role="*",
            mcp_server="ask-s4hana",
            tool_name="execute_payment",
            permission="DENY",
            description="Restricted executive cannot execute payments",
        )
    )

    exec_ident = VerifiedIdentity(
        tenant_id="velora-tenant",
        object_id="exec-user-002",
        principal_type="user",
        client_application_id="copilot",
        roles={"Executive"},
        display_email="restricted_exec@velora.ae",
    )

    decision = clean_engine.evaluate_access(
        user_email=exec_ident.display_email,
        user_oid=exec_ident.object_id,
        roles=exec_ident.roles,
        is_admin=exec_ident.is_admin,
        mcp_server="ask-s4hana",
        tool_name="execute_payment",
    )
    # Priority 5 DENY must beat Priority 20 ALLOW
    assert decision.allowed is False
    assert decision.matched_rule.priority == 5
    assert "test-deny-001" == decision.matched_rule.policy_id


def test_specificity_tie_breaker_on_equal_priority(clean_engine):
    """When two rules share identical priority rank, the more specific rule wins."""
    # Add two rules at Priority 50 on test-server: one generic role, one specific user
    clean_engine.add_rule(
        McpPolicyRule(
            policy_id="role-allow-50",
            name="Finance Role Allow",
            priority=50,
            role="Finance_Manager",
            mcp_server="test-server",
            tool_name="*",
            permission="ALLOW",
        )
    )
    clean_engine.add_rule(
        McpPolicyRule(
            policy_id="user-deny-50",
            name="Specific User Deny",
            priority=50,
            user_principal="bad_actor@velora.ae",
            role="*",
            mcp_server="test-server",
            tool_name="test_tool",
            permission="DENY",
        )
    )

    decision = clean_engine.evaluate_access(
        user_email="bad_actor@velora.ae",
        user_oid="bad-oid",
        roles={"Finance_Manager"},
        is_admin=False,
        mcp_server="test-server",
        tool_name="test_tool",
    )
    # Both priority 50, but specific user + specific tool (weight 80+20+10=110) beats role (weight 40+20=60)
    assert decision.allowed is False
    assert decision.matched_rule.policy_id == "user-deny-50"


def test_fail_closed_default_deny(clean_engine):
    """Unknown/unmatched tool on unprivileged user results in fail-closed DENY."""
    guest_ident = VerifiedIdentity(
        tenant_id="velora-tenant",
        object_id="guest-001",
        principal_type="user",
        client_application_id="copilot",
        roles={"ExternalGuest"},
        display_email="guest@external.com",
    )

    decision = clean_engine.evaluate_access(
        user_email=guest_ident.display_email,
        user_oid=guest_ident.object_id,
        roles=guest_ident.roles,
        is_admin=guest_ident.is_admin,
        mcp_server="ask-s4hana",
        tool_name="get_cost_center_actuals",
    )
    assert decision.allowed is False
    assert decision.matched_rule.priority == 9999 or decision.matched_rule.permission == "DENY"


def test_enforce_mcp_policy_raises_authorization_error():
    """enforce_mcp_policy should raise AuthorizationError(403) when priority matrix denies access."""
    guest_ident = VerifiedIdentity(
        tenant_id="velora-tenant",
        object_id="guest-001",
        principal_type="user",
        client_application_id="copilot",
        roles={"Guest"},
        display_email="guest@velora.ae",
    )

    with pytest.raises(AuthorizationError) as exc_info:
        enforce_mcp_policy(
            identity=guest_ident,
            mcp_server="ask-s4hana",
            tool_name="execute_payment",
        )
    assert exc_info.value.status_code == 403
    assert "Forbidden" in exc_info.value.message


def test_get_effective_matrix_inspection(clean_engine):
    """get_effective_matrix returns a complete, structured matrix of user permissions."""
    result = clean_engine.get_effective_matrix(
        user_email="hr_user@velora.ae",
        user_oid="hr-oid-01",
        roles={"HR_Specialist"},
        is_admin=False,
    )
    assert result["user_principal"] == "hr_user@velora.ae"
    assert "HR_Specialist" in result["roles"]
    assert result["total_tools_evaluated"] > 0
    assert result["allowed_count"] > 0
    assert result["denied_count"] > 0

    # HR_Specialist should be allowed on SuccessFactors
    sf_tools = [r for r in result["matrix"] if r["mcp_server"] == "ask-successfactors"]
    assert len(sf_tools) > 0
    assert any(r["permission"] == "ALLOW" for r in sf_tools)

    # HR_Specialist should be denied on S4HANA finance actuals
    s4_tools = [r for r in result["matrix"] if r["mcp_server"] == "ask-s4hana"]
    assert len(s4_tools) > 0
    assert all(r["permission"] == "DENY" for r in s4_tools)


@pytest.mark.asyncio
async def test_handoff_api_get_mcp_access_matrix():
    """Verify that Velora Productivity /handoff endpoint supports GET_MCP_ACCESS_MATRIX."""
    from productivity_mcp.server import handle_handoff_request, HandoffRequest

    req = HandoffRequest(
        task="Inspect user MCP permissions",
        operation="GET_MCP_ACCESS_MATRIX",
        rootCorrelationId="corr-test-01",
        conversationId="conv-test-01",
        turnId="turn-test-01",
        userObjectId="exec-123",
        userEmail="executive@velora.ae",
        tenantId="velora-tenant",
        parameters={"userPrincipal": "executive@velora.ae"},
    )
    resp = await handle_handoff_request(req)
    assert resp.status == "SUCCESS"
    assert "Evaluated Dataverse Priority Matrix" in resp.resultSummary
    assert resp.structuredResult is not None
    assert "matrix" in resp.structuredResult
    assert resp.structuredResult["allowed_count"] > 0
