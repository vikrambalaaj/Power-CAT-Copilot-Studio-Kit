"""Dataverse MCP Server & Tool Access Priority Matrix Engine.

Enforces zero-trust access control based on a configurable Priority Matrix
stored in Microsoft Dataverse entity `cre2f_veloramcppolicy`.

Key features:
1. Priority Matrix Evaluation:
   - Lower numeric `cre2f_priority` has higher precedence (Priority 10 overrides Priority 100).
   - Specificity tie-breaker when priority numbers match (Exact User > Role > Wildcard; Specific Tool > Wildcard Tool).
   - Fail-closed default: if no rule matches, access is strictly DENIED (HTTP 403).
2. Dual Mode Operation:
   - Queries Dataverse OData Web API (`/api/data/v9.2/cre2f_veloramcppolicies`) when configured.
   - Resilient in-memory/cached store with baseline enterprise matrix for local/test execution.
3. Permission Matrix Visibility:
   - `get_effective_matrix()` enables users, administrators, and autonomous agents to inspect
     which users can access which MCP servers and tools.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

log = logging.getLogger("shared_mcp.policy_matrix")

DATAVERSE_POLICY_ENTITY_SET = os.getenv("DATAVERSE_POLICY_ENTITY_SET", "cre2f_veloramcppolicies")
DATAVERSE_API_VERSION = os.getenv("DATAVERSE_API_VERSION", "v9.2")
POLICY_CACHE_TTL_SECONDS = float(os.getenv("MCP_POLICY_CACHE_TTL", "60.0"))

KNOWN_MCP_SERVERS = [
    "ask-productivity",
    "ask-facilitator",
    "ask-s4hana",
    "ask-successfactors",
    "ask-sac",
    "ask-salesforce",
    "ask-servicenow",
]

COMMON_TOOL_CATALOG: Dict[str, List[str]] = {
    "ask-productivity": [
        "get_productivity_pulse",
        "search_executive_communications",
        "draft_executive_briefing",
        "send_executive_email",
        "schedule_calendar_meeting",
        "list_active_subscriptions",
        "evaluate_kpi_recommendation",
        "get_mcp_access_matrix",
    ],
    "ask-facilitator": [
        "get_facilitator_guide",
        "list_available_tools",
        "record_decision_checkpoint",
        "get_decision_trail",
        "export_decision_trail",
        "get_mcp_access_matrix",
    ],
    "ask-s4hana": [
        "get_cost_center_actuals",
        "get_gl_account_balance",
        "get_financial_kpis",
        "get_company_code_details",
        "verify_financial_health",
    ],
    "ask-successfactors": [
        "get_headcount_summary",
        "get_workforce_demographics",
        "get_employee_profile",
        "get_org_chart_level",
        "list_disclosure_policies",
    ],
    "ask-sac": [
        "get_sac_kpis",
        "get_sac_story_analytics",
        "get_sac_model_data",
    ],
}


@dataclass(frozen=True)
class McpPolicyRule:
    """Immutable representation of a Dataverse Priority Matrix rule."""
    policy_id: str
    name: str
    priority: int  # Lower number = higher evaluation precedence (e.g. 10 > 100)
    user_principal: str = "*"  # Email, UPN, Object ID, or "*"
    role: str = "*"  # e.g. "Velora_Admin", "Executive", "HR_Specialist", or "*"
    mcp_server: str = "*"  # Server name or "*"
    tool_name: str = "*"  # Specific tool name or "*"
    permission: str = "ALLOW"  # "ALLOW" or "DENY"
    is_active: bool = True
    conditions: Dict[str, Any] = field(default_factory=dict)
    description: str = ""

    @property
    def specificity_weight(self) -> int:
        """Calculate rule specificity for tie-breaking equal priorities."""
        weight = 0
        if self.user_principal and self.user_principal != "*":
            weight += 80
        if self.role and self.role != "*":
            weight += 40
        if self.mcp_server and self.mcp_server != "*":
            weight += 20
        if self.tool_name and self.tool_name != "*":
            weight += 10
        return weight


@dataclass(frozen=True)
class PolicyDecision:
    """Result of evaluating a request against the Dataverse Priority Matrix."""
    allowed: bool
    reason: str
    matched_rule: Optional[McpPolicyRule] = None
    status_code: int = 200
    evaluation_trace: List[str] = field(default_factory=list)


class PolicyMatrixEngine:
    """Enterprise Policy Matrix Engine backed by Microsoft Dataverse."""

    def __init__(self, dataverse_url: Optional[str] = None):
        self.dataverse_url = (dataverse_url or os.getenv("DATAVERSE_URL", "")).rstrip("/")
        self._rules: List[McpPolicyRule] = []
        self._last_loaded_at: float = 0.0
        self._seed_default_matrix()

    def _seed_default_matrix(self) -> None:
        """Seed baseline enterprise priority matrix rules."""
        self._rules = [
            # Priority 5: Strict Security Guardrail - Auditor Export
            McpPolicyRule(
                policy_id="rule-sec-001",
                name="Auditor Only - Decision Trail Export",
                priority=5,
                role="Auditor",
                mcp_server="ask-facilitator",
                tool_name="export_decision_trail",
                permission="ALLOW",
                description="Auditors may export verified decision trails",
            ),
            # Priority 10: Velora Platform Administrators have unrestricted access
            McpPolicyRule(
                policy_id="rule-admin-001",
                name="Velora Admin Full Access",
                priority=10,
                role="Velora_Admin",
                mcp_server="*",
                tool_name="*",
                permission="ALLOW",
                description="Platform administrators have full access to all MCP servers and tools",
            ),
            McpPolicyRule(
                policy_id="rule-admin-002",
                name="Azure Global Admin Full Access",
                priority=10,
                role="GlobalAdmin",
                mcp_server="*",
                tool_name="*",
                permission="ALLOW",
                description="Global administrators have full access to all MCP servers and tools",
            ),
            # Priority 20: Executive Leadership role access
            McpPolicyRule(
                policy_id="rule-exec-001",
                name="Executive Leadership Productivity Access",
                priority=20,
                role="Executive",
                mcp_server="ask-productivity",
                tool_name="*",
                permission="ALLOW",
                description="Executives have full access to productivity and briefing tools",
            ),
            McpPolicyRule(
                policy_id="rule-exec-002",
                name="Executive Leadership SuccessFactors Analytics",
                priority=20,
                role="Executive",
                mcp_server="ask-successfactors",
                tool_name="*",
                permission="ALLOW",
                description="Executives can access aggregate headcount and workforce analytics",
            ),
            McpPolicyRule(
                policy_id="rule-exec-003",
                name="Executive Leadership S4HANA Finance Analytics",
                priority=20,
                role="Executive",
                mcp_server="ask-s4hana",
                tool_name="*",
                permission="ALLOW",
                description="Executives can query company financial health and cost center KPIs",
            ),
            McpPolicyRule(
                policy_id="rule-exec-004",
                name="Executive Leadership SAC Analytics Access",
                priority=20,
                role="Executive",
                mcp_server="ask-sac",
                tool_name="*",
                permission="ALLOW",
                description="Executives can query SAC stories, models, and strategic KPIs",
            ),
            McpPolicyRule(
                policy_id="rule-exec-005",
                name="Executive Leadership Facilitator Access",
                priority=20,
                role="Executive",
                mcp_server="ask-facilitator",
                tool_name="*",
                permission="ALLOW",
                description="Executives can record and inspect decision governance trails",
            ),
            # Priority 30: Departmental Scoped Access
            McpPolicyRule(
                policy_id="rule-hr-001",
                name="HR Specialist SuccessFactors Access",
                priority=30,
                role="HR_Specialist",
                mcp_server="ask-successfactors",
                tool_name="*",
                permission="ALLOW",
                description="HR specialists have operational access to HR demographic tools",
            ),
            McpPolicyRule(
                policy_id="rule-fin-001",
                name="Finance Manager S4HANA Access",
                priority=30,
                role="Finance_Manager",
                mcp_server="ask-s4hana",
                tool_name="*",
                permission="ALLOW",
                description="Finance managers have operational access to SAP financial actuals",
            ),
            # Priority 50: Explicit Deny Guardrail - Financial Transfers & Payments
            McpPolicyRule(
                policy_id="rule-deny-001",
                name="Block Direct Payment Execution for Non-Treasury",
                priority=50,
                role="*",
                mcp_server="ask-s4hana",
                tool_name="execute_payment",
                permission="DENY",
                description="Direct automated payments are disabled via MCP matrix; requires Treasury portal",
            ),
            McpPolicyRule(
                policy_id="rule-guard-001",
                name="Block Non-Admin Auto Send Policy",
                priority=15,
                role="*",
                mcp_server="ask-facilitator",
                tool_name="configure_auto_send_policy",
                permission="DENY",
                description="Tool requires administrator privileges (Velora_Admin role)",
            ),
            # Priority 100: Baseline Authenticated User Safe Tools
            McpPolicyRule(
                policy_id="rule-base-001",
                name="All Authenticated Users - Pulse & Guide",
                priority=100,
                user_principal="*",
                role="*",
                mcp_server="ask-productivity",
                tool_name="get_productivity_pulse",
                permission="ALLOW",
                description="All authenticated users can retrieve their productivity pulse",
            ),
            McpPolicyRule(
                policy_id="rule-base-002",
                name="All Authenticated Users - Facilitator Guide",
                priority=100,
                user_principal="*",
                role="*",
                mcp_server="ask-facilitator",
                tool_name="get_facilitator_guide",
                permission="ALLOW",
                description="All authenticated users can retrieve facilitator guidance",
            ),
            McpPolicyRule(
                policy_id="rule-base-003",
                name="All Authenticated Users - Permission Matrix Inspection",
                priority=100,
                user_principal="*",
                role="*",
                mcp_server="*",
                tool_name="get_mcp_access_matrix",
                permission="ALLOW",
                description="All users can inspect their effective MCP server and tool permissions",
            ),
            McpPolicyRule(
                policy_id="rule-base-004",
                name="All Authenticated Users - Facilitator General Access",
                priority=100,
                user_principal="*",
                role="*",
                mcp_server="ask-facilitator",
                tool_name="*",
                permission="ALLOW",
                description="Authenticated users have general access to facilitator tools",
            ),
            # Priority 9999: Zero-Trust Baseline Fail-Closed Fallback
            McpPolicyRule(
                policy_id="rule-default-deny",
                name="Default Deny Fallback",
                priority=9999,
                user_principal="*",
                role="*",
                mcp_server="*",
                tool_name="*",
                permission="DENY",
                description="Fail-closed default deny rule when no higher-priority allow rule matches",
            ),
        ]
        self._last_loaded_at = time.time()

    def add_rule(self, rule: McpPolicyRule) -> None:
        """Register or override a rule in the in-memory store."""
        # Replace if ID exists, otherwise append
        self._rules = [r for r in self._rules if r.policy_id != rule.policy_id]
        self._rules.append(rule)
        log.info(f"Registered MCP policy matrix rule: {rule.name} (Priority {rule.priority}, {rule.permission})")

    def clear_rules(self) -> None:
        """Reset rule matrix for testing."""
        self._rules.clear()

    async def refresh_from_dataverse(self, force: bool = False) -> None:
        """Query Dataverse OData entity set if configured and TTL expired."""
        now = time.time()
        if not force and (now - self._last_loaded_at) < POLICY_CACHE_TTL_SECONDS:
            return

        if not self.dataverse_url:
            self._last_loaded_at = now
            return

        token = os.getenv("DATAVERSE_ACCESS_TOKEN") or os.getenv("AZURE_ACCESS_TOKEN")
        if not token:
            self._last_loaded_at = now
            return

        try:
            import httpx
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "OData-MaxVersion": "4.0",
                "OData-Version": "4.0",
            }
            url = f"{self.dataverse_url}/api/data/{DATAVERSE_API_VERSION}/{DATAVERSE_POLICY_ENTITY_SET}"
            params = {
                "$filter": "cre2f_isactive eq true",
                "$orderby": "cre2f_priority asc",
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=headers, params=params)
                if res.status_code == 200:
                    records = res.json().get("value", [])
                    new_rules = []
                    for r in records:
                        conditions = {}
                        raw_cond = r.get("cre2f_conditions")
                        if raw_cond and isinstance(raw_cond, str):
                            try:
                                conditions = json.loads(raw_cond)
                            except Exception:
                                pass
                        new_rules.append(
                            McpPolicyRule(
                                policy_id=r.get("cre2f_veloramcppolicyid", f"dv-{len(new_rules)}"),
                                name=r.get("cre2f_policyname", "Unnamed Rule"),
                                priority=int(r.get("cre2f_priority", 500)),
                                user_principal=r.get("cre2f_user_principal") or "*",
                                role=r.get("cre2f_role") or "*",
                                mcp_server=r.get("cre2f_mcpserver") or "*",
                                tool_name=r.get("cre2f_toolname") or "*",
                                permission=(r.get("cre2f_permission") or "ALLOW").upper(),
                                is_active=bool(r.get("cre2f_isactive", True)),
                                conditions=conditions,
                                description=r.get("cre2f_description") or "",
                            )
                        )
                    if new_rules:
                        # Append default fallback if not present
                        if not any(r.policy_id == "rule-default-deny" for r in new_rules):
                            new_rules.append(
                                McpPolicyRule(
                                    policy_id="rule-default-deny",
                                    name="Default Deny Fallback",
                                    priority=9999,
                                    user_principal="*",
                                    role="*",
                                    mcp_server="*",
                                    tool_name="*",
                                    permission="DENY",
                                )
                            )
                        self._rules = new_rules
                        log.info(f"Successfully loaded {len(new_rules)} rules from Dataverse OData")
        except Exception as exc:
            log.warning(f"Could not refresh policies from Dataverse: {exc}. Using cached/fallback matrix.")
        finally:
            self._last_loaded_at = now

    def _matches_rule(
        self,
        rule: McpPolicyRule,
        user_email: str,
        user_oid: str,
        roles: Set[str],
        is_admin: bool,
        target_server: str,
        target_tool: Optional[str],
    ) -> bool:
        """Check if an MCP request matches the rule criteria."""
        if not rule.is_active:
            return False

        # Server matching
        rule_server = rule.mcp_server.strip().lower()
        if rule_server != "*" and rule_server != target_server.strip().lower():
            return False

        # Tool matching
        if target_tool:
            rule_tool = rule.tool_name.strip().lower()
            if rule_tool != "*" and rule_tool != target_tool.strip().lower():
                return False

        # Subject matching
        user_matched = False
        rule_user = rule.user_principal.strip().lower()
        if rule_user == "*":
            user_matched = True
        elif user_email and rule_user == user_email.strip().lower():
            user_matched = True
        elif user_oid and rule_user == user_oid.strip().lower():
            user_matched = True

        role_matched = False
        rule_role = rule.role.strip()
        if rule_role == "*":
            role_matched = True
        elif rule_role in roles:
            role_matched = True
        elif is_admin and rule_role in ("Velora_Admin", "Admin", "GlobalAdmin"):
            role_matched = True

        # Rule matches if:
        # 1. Both user and role are wildcards
        # 2. Or explicit user matches
        # 3. Or explicit role matches
        if rule.user_principal != "*" and rule.role != "*":
            return user_matched and role_matched
        elif rule.user_principal != "*":
            return user_matched
        elif rule.role != "*":
            return role_matched
        else:
            return True

    def evaluate_access(
        self,
        user_email: Optional[str],
        user_oid: Optional[str],
        roles: Set[str],
        is_admin: bool,
        mcp_server: str,
        tool_name: Optional[str] = None,
    ) -> PolicyDecision:
        """Evaluate access against the priority matrix.
        
        Sorting logic:
        1. Priority rank ASC (lower number = higher precedence: e.g. Priority 10 > Priority 100)
        2. Specificity weight DESC (tie-breaker for identical priority numbers)
        """
        email_clean = (user_email or "").strip().lower()
        oid_clean = (user_oid or "").strip()
        server_clean = mcp_server.strip().lower()
        tool_clean = tool_name.strip().lower() if tool_name else None

        candidate_rules: List[McpPolicyRule] = []
        trace: List[str] = []

        for rule in self._rules:
            if self._matches_rule(
                rule=rule,
                user_email=email_clean,
                user_oid=oid_clean,
                roles=roles,
                is_admin=is_admin,
                target_server=server_clean,
                target_tool=tool_clean,
            ):
                candidate_rules.append(rule)
                trace.append(f"Matched rule '{rule.name}' [Priority {rule.priority}, {rule.permission}, Weight {rule.specificity_weight}]")

        if not candidate_rules:
            return PolicyDecision(
                allowed=False,
                reason=f"No matching policy rule in Dataverse Priority Matrix for server '{mcp_server}' tool '{tool_name}'. Fail-closed default DENY.",
                status_code=403,
                matched_rule=None,
                evaluation_trace=trace,
            )

        # Sort candidate rules by priority ASC, then specificity weight DESC
        candidate_rules.sort(key=lambda r: (r.priority, -r.specificity_weight))

        winning_rule = candidate_rules[0]
        is_allowed = winning_rule.permission.upper() == "ALLOW"

        if is_allowed:
            reason = f"Access granted by policy rule '{winning_rule.name}' (Priority {winning_rule.priority})"
            status = 200
        else:
            reason = f"Access denied by policy rule '{winning_rule.name}' (Priority {winning_rule.priority}): {winning_rule.description or 'Denied by priority matrix'}"
            status = 403

        return PolicyDecision(
            allowed=is_allowed,
            reason=reason,
            matched_rule=winning_rule,
            status_code=status,
            evaluation_trace=trace,
        )

    def get_effective_matrix(
        self,
        user_email: Optional[str],
        user_oid: Optional[str],
        roles: Set[str],
        is_admin: bool,
        server_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute the full effective permissions matrix for a user.
        
        Returns a structured view showing each server and tool with its
        Allow/Deny status, winning rule name, and priority ranking.
        """
        servers_to_evaluate = (
            [server_filter.strip().lower()]
            if server_filter and server_filter.strip().lower() in COMMON_TOOL_CATALOG
            else KNOWN_MCP_SERVERS
        )

        matrix_rows: List[Dict[str, Any]] = []

        for server in servers_to_evaluate:
            tools = COMMON_TOOL_CATALOG.get(server, ["*"])
            for tool in tools:
                decision = self.evaluate_access(
                    user_email=user_email,
                    user_oid=user_oid,
                    roles=roles,
                    is_admin=is_admin,
                    mcp_server=server,
                    tool_name=tool,
                )
                matrix_rows.append({
                    "mcp_server": server,
                    "tool_name": tool,
                    "permission": "ALLOW" if decision.allowed else "DENY",
                    "winning_rule": decision.matched_rule.name if decision.matched_rule else "None",
                    "priority": decision.matched_rule.priority if decision.matched_rule else 9999,
                    "reason": decision.reason,
                })

        return {
            "user_principal": user_email or user_oid or "anonymous",
            "roles": sorted(list(roles)),
            "is_admin": is_admin,
            "total_tools_evaluated": len(matrix_rows),
            "allowed_count": sum(1 for r in matrix_rows if r["permission"] == "ALLOW"),
            "denied_count": sum(1 for r in matrix_rows if r["permission"] == "DENY"),
            "matrix": matrix_rows,
        }


# Global singleton instance
_global_policy_matrix_engine = PolicyMatrixEngine()


def get_policy_matrix_engine() -> PolicyMatrixEngine:
    return _global_policy_matrix_engine


def enforce_mcp_policy(
    identity: Any,
    mcp_server: str,
    tool_name: Optional[str] = None,
) -> PolicyDecision:
    """Enforce Dataverse Priority Matrix policy on an incoming request.
    
    Raises:
        AuthorizationError (403): If the priority matrix denies access.
    """
    from shared_mcp.identity import AuthorizationError

    engine = get_policy_matrix_engine()

    email = getattr(identity, "display_email", None) if identity else None
    oid = getattr(identity, "object_id", None) if identity else None
    roles = set(getattr(identity, "roles", set())) if identity else set()
    is_admin = bool(getattr(identity, "is_admin", False)) if identity else False

    decision = engine.evaluate_access(
        user_email=email,
        user_oid=oid,
        roles=roles,
        is_admin=is_admin,
        mcp_server=mcp_server,
        tool_name=tool_name,
    )

    if not decision.allowed:
        log.warning(
            f"MCP Policy Denied: user={email or oid} server={mcp_server} tool={tool_name} "
            f"reason={decision.reason}"
        )
        raise AuthorizationError(
            message=f"Forbidden: {decision.reason}",
            status_code=403,
        )

    return decision
