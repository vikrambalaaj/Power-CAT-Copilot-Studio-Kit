"""Centralized Dataverse Tool Authorization Architecture for Velora MCP Suite.

Zero-Trust Policy Enforcement Engine:
1. Validates identity claims strictly from verified Entra access tokens (oid, tid, groups, roles).
2. Evaluates requested tool against a static default-deny registry (TOOL_ACTIONS).
3. Queries Dataverse tool permissions (cre2f_veloratoolpermissions) with short caching (1-5 min TTL).
4. Fails closed (denies access) on policy absence or Dataverse outages.
5. Emits structured authorization audit records (cre2f_veloraauthorizationaudits).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("velora.tool_authorization")

# -----------------------------------------------------------------------------
# Static Default-Deny Registry (Codebase Ground Truth)
# If a tool is missing here, deny execution even if permitted in Dataverse.
# -----------------------------------------------------------------------------
TOOL_ACTIONS: Dict[str, str] = {
    # Productivity MCP Tools - Mail & Daily Briefings
    "search_mail": "READ",
    "prepare_email": "WRITE_PREVIEW",
    "send_approved_email": "WRITE",
    "get_mail_thread": "READ",
    "summarize_priority_mail": "READ",
    "find_mail_follow_ups": "READ",
    "prepare_email_reply": "WRITE_PREVIEW",
    "send_approved_email_reply": "WRITE",
    "plan_my_day": "READ",
    "quick_action_checklist": "READ",
    "get_pre_meeting_brief": "READ",
    "get_end_of_day_digest": "READ",
    "get_executive_briefing": "READ",
    "get_daily_executive_briefing": "READ",
    "prepare_daily_briefing_email": "WRITE_PREVIEW",
    "send_approved_daily_briefing_email": "WRITE",
    "send_daily_briefing_email": "WRITE",
    "prepare_end_of_day_wrapup_email": "WRITE_PREVIEW",
    "get_executive_attention": "READ",
    # Calendar Operations
    "list_calendar_events": "READ",
    "get_meeting_details": "READ",
    "check_availability": "READ",
    "get_meeting_context": "READ",
    "prepare_meeting": "WRITE_PREVIEW",
    "prepare_meeting_creation": "WRITE_PREVIEW",
    "create_approved_event": "WRITE",
    "create_approved_meeting": "WRITE",
    "prepare_meeting_update": "WRITE_PREVIEW",
    "update_approved_meeting": "WRITE",
    "prepare_meeting_cancellation": "WRITE_PREVIEW",
    "cancel_approved_meeting": "WRITE",
    # Meeting Action Items
    "get_meeting_action_tracker": "READ",
    "prepare_meeting_actions": "WRITE_PREVIEW",
    "create_approved_meeting_actions": "WRITE",
    # Teams Collaboration
    "search_teams_messages": "READ",
    "get_channel_context": "READ",
    "get_chat_context": "READ",
    "find_teams_follow_ups": "READ",
    "prepare_teams_chat_message": "WRITE_PREVIEW",
    "send_approved_teams_chat_message": "WRITE",
    "prepare_teams_channel_post": "WRITE_PREVIEW",
    "send_approved_teams_channel_post": "WRITE",
    # Planner Tasks
    "list_my_tasks": "READ",
    "list_my_planner_tasks": "READ",
    "list_plan_tasks": "READ",
    "get_planner_task": "READ",
    "find_overdue_tasks": "READ",
    "prepare_task": "WRITE_PREVIEW",
    "prepare_planner_task": "WRITE_PREVIEW",
    "create_approved_task": "WRITE",
    "create_approved_planner_task": "WRITE",
    "update_approved_task": "WRITE",
    "prepare_planner_task_update": "WRITE_PREVIEW",
    "update_approved_planner_task": "WRITE",
    "prepare_planner_task_assignment": "WRITE_PREVIEW",
    "assign_approved_planner_task": "WRITE",
    # Subscriptions & Recommendations
    "prepare_automation_subscription": "WRITE_PREVIEW",
    "confirm_automation_subscription": "WRITE",
    "revoke_automation_subscription": "WRITE",
    "evaluate_verified_kpi_snapshot": "READ",
    "list_recommendations": "READ",
    "record_recommendation_feedback": "WRITE",
    "get_rule_feedback_summary": "READ",
    # S/4HANA Finance MCP Tools
    "s4__get_receivables_aging": "READ",
    "s4__get_payables_aging": "READ",
    "s4__get_profit_loss": "READ",
    "s4__get_budget_consumption": "READ",
    "s4__transfer_budget": "WRITE",
    "s4__get_customer_balance": "READ",
    "s4__get_cost_center_expenses": "READ",
    "s4__get_profit_center_breakdown": "READ",
    # Facilitator MCP Tools
    "get_facilitator_guide": "READ",
    "draft_meeting_summary_email": "WRITE_PREVIEW",
    "export_decision_trail": "AUDIT",
    # SuccessFactors HR Workforce MCP Tools
    "sf__get_emiratisation_metrics": "READ",
    "sf__get_gender_diversity_metrics": "READ",
    "sf__get_age_demographics": "READ",
    "sf__get_headcount_by_department": "READ",
    "sf__get_workforce_summary": "READ",
    "sf__get_employee_info": "READ",
    # Governance & Matrix Inspection Tools
    "get_mcp_access_matrix": "READ",
}


@dataclass(frozen=True)
class ToolPermission:
    tool_name: str
    action: str
    tenant_id: str
    user_object_id: Optional[str] = None
    group_id: Optional[str] = None
    entity_scope: Optional[str] = None
    valid_until: Optional[datetime] = None
    enabled: bool = True


class AuthorizationDenied(Exception):
    """Raised when caller lacks active authorization policy for requested tool."""
    pass


class PolicyCache:
    """In-memory cache with configurable TTL (default 180s / 3 mins)."""

    def __init__(self, ttl_seconds: int = 180):
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, tuple[float, List[ToolPermission]]] = {}

    def get(self, tenant_id: str) -> Optional[List[ToolPermission]]:
        if tenant_id in self._cache:
            cached_time, policies = self._cache[tenant_id]
            if time.time() - cached_time < self.ttl_seconds:
                return policies
            del self._cache[tenant_id]
        return None

    def set(self, tenant_id: str, policies: List[ToolPermission]) -> None:
        self._cache[tenant_id] = (time.time(), policies)

    def invalidate(self, tenant_id: Optional[str] = None) -> None:
        if tenant_id:
            self._cache.pop(tenant_id, None)
        else:
            self._cache.clear()


class DataversePolicyRepository:
    """Repository connecting to Dataverse OData Web API for permissions & audit."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
        access_token: Optional[str] = None,
    ):
        self.base_url = (base_url or os.getenv("DATAVERSE_URL", "")).rstrip("/")
        self.client_id = client_id or os.getenv("DATAVERSE_CLIENT_ID") or os.getenv("AZURE_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("DATAVERSE_CLIENT_SECRET") or os.getenv("AZURE_CLIENT_SECRET")
        self.tenant_id = tenant_id or os.getenv("DATAVERSE_TENANT_ID") or os.getenv("AZURE_TENANT_ID")
        self._access_token = access_token
        self._token_expiry = 0.0

    def _get_bearer_token(self) -> Optional[str]:
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token
        if not (self.base_url and self.client_id and self.client_secret and self.tenant_id):
            return self._access_token

        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        params = urllib.parse.urlencode({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
            "scope": f"{self.base_url}/.default",
        }).encode()

        req = urllib.request.Request(token_url, data=params, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.load(resp)
                self._access_token = data.get("access_token")
                expires_in = int(data.get("expires_in", 3600))
                self._token_expiry = time.time() + expires_in - 60
                return self._access_token
        except Exception as err:
            logger.warning(f"Failed to acquire Dataverse token via client credentials: {err}")
            return self._access_token

    def to_permission(self, row: Dict[str, Any]) -> ToolPermission:
        valid_until = None
        if row.get("cre2f_validuntil"):
            try:
                valid_until = datetime.fromisoformat(row["cre2f_validuntil"].replace("Z", "+00:00"))
            except Exception:
                pass

        return ToolPermission(
            tool_name=str(row.get("cre2f_toolname", "")),
            action=str(row.get("cre2f_allowedaction", "READ")).upper(),
            tenant_id=str(row.get("cre2f_tenantid", "")),
            user_object_id=row.get("cre2f_entraobjectid"),
            group_id=row.get("cre2f_entragroupid"),
            entity_scope=row.get("cre2f_entityscope"),
            valid_until=valid_until,
            enabled=bool(row.get("cre2f_enabled", True)),
        )

    async def list_policies(self, tenant_id: str) -> List[ToolPermission]:
        token = self._get_bearer_token()
        if not (self.base_url and token):
            logger.debug("No Dataverse credentials configured; returning empty policy set.")
            return []

        filter_query = urllib.parse.quote(f"cre2f_tenantid eq '{tenant_id}' and cre2f_enabled eq true")
        url = f"{self.base_url}/api/data/v9.2/cre2f_veloratoolpermissions?$filter={filter_query}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        })

        loop = asyncio.get_running_loop()
        try:
            def _fetch():
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return json.load(resp)
            data = await loop.run_in_executor(None, _fetch)
            return [self.to_permission(r) for r in data.get("value", [])]
        except Exception as err:
            logger.error(f"Dataverse list_policies failed for tenant {tenant_id}: {err}")
            # Fail closed: re-raise error so ToolAuthorizer knows Dataverse is down
            raise

    async def log_audit(
        self,
        identity: Any,
        tool_name: str,
        decision: str,
        reason: str,
        correlation_id: Optional[str] = None,
    ) -> None:
        token = self._get_bearer_token()
        if not (self.base_url and token):
            return

        payload = {
            "cre2f_name": f"Audit-{tool_name}-{int(time.time())}",
            "cre2f_userobjectid": getattr(identity, "object_id", None) or getattr(identity, "oid", None) or "ANONYMOUS",
            "cre2f_toolname": tool_name,
            "cre2f_decision": decision,
            "cre2f_reason": reason[:250],
            "cre2f_correlationid": correlation_id or getattr(identity, "correlation_id", "N/A"),
            "cre2f_createdon": datetime.now(timezone.utc).isoformat(),
        }

        url = f"{self.base_url}/api/data/v9.2/cre2f_veloraauthorizationaudits"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )

        loop = asyncio.get_running_loop()
        try:
            def _post():
                with urllib.request.urlopen(req, timeout=5):
                    pass
            await loop.run_in_executor(None, _post)
        except Exception as err:
            logger.warning(f"Failed to record authorization audit to Dataverse: {err}")


class ToolAuthorizer:
    """Centralized zero-trust authorization service used by every MCP server."""

    def __init__(
        self,
        policy_repository: Optional[DataversePolicyRepository] = None,
        cache: Optional[PolicyCache] = None,
        static_registry: Optional[Dict[str, str]] = None,
    ):
        self.policy_repository = policy_repository or DataversePolicyRepository()
        self.cache = cache or PolicyCache(ttl_seconds=int(os.getenv("POLICY_CACHE_TTL_SECONDS", "180")))
        self.registry = static_registry or TOOL_ACTIONS

    async def _get_policies(self, tenant_id: str) -> List[ToolPermission]:
        cached = self.cache.get(tenant_id)
        if cached is not None:
            return cached

        try:
            policies = await self.policy_repository.list_policies(tenant_id)
            self.cache.set(tenant_id, policies)
            return policies
        except Exception as err:
            logger.error(f"Error loading policies from Dataverse: {err}. Failing closed.")
            raise AuthorizationDenied(f"Authorization service unavailable. Access denied for safety.")

    async def authorize(
        self,
        identity: Any,
        tool_name: str,
        action: Optional[str] = None,
        entity_scope: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> bool:
        # 1. Static default-deny check
        expected_action = self.registry.get(tool_name)
        if not expected_action:
            await self.policy_repository.log_audit(
                identity, tool_name, "DENY", "Tool missing from static registry", correlation_id
            )
            raise AuthorizationDenied(f"Tool '{tool_name}' is not in approved static registry.")

        if action and action.upper() != expected_action.upper():
            await self.policy_repository.log_audit(
                identity, tool_name, "DENY", f"Action mismatch (got {action}, expected {expected_action})", correlation_id
            )
            raise AuthorizationDenied(f"Action '{action}' is not permitted for tool '{tool_name}'.")

        action = expected_action

        # Extract verified claims
        tenant_id = getattr(identity, "tenant_id", None) or getattr(identity, "tid", None) or ""
        user_id = getattr(identity, "object_id", None) or getattr(identity, "oid", None) or ""
        user_groups: Set[str] = set(getattr(identity, "groups", []) or [])
        user_roles: Set[str] = set(getattr(identity, "roles", []) or [])

        # If admin or executive app role is present in verified token, allow with audit
        if "Velora_Admin" in user_roles or "Global_Admin" in user_roles:
            await self.policy_repository.log_audit(
                identity, tool_name, "ALLOW", "Administrative role grant", correlation_id
            )
            return True

        if not tenant_id:
            await self.policy_repository.log_audit(
                identity, tool_name, "DENY", "Missing tenant ID claim", correlation_id
            )
            raise AuthorizationDenied("Caller identity contains no valid tenant ID claim.")

        # 2. Query Dataverse policies with short caching
        policies = await self._get_policies(tenant_id)
        now = datetime.now(timezone.utc)

        for policy in policies:
            if not policy.enabled:
                continue
            if policy.tool_name != tool_name and policy.tool_name != "*":
                continue
            if policy.action != action and policy.action != "*":
                continue
            if policy.tenant_id != tenant_id and policy.tenant_id != "*":
                continue
            if policy.valid_until and policy.valid_until <= now:
                continue

            user_matches = (
                policy.user_object_id
                and (policy.user_object_id == user_id or policy.user_object_id == "*")
            )

            group_matches = (
                policy.group_id
                and (policy.group_id in user_groups or policy.group_id == "*")
            )

            scope_matches = (
                not policy.entity_scope
                or policy.entity_scope == "*"
                or policy.entity_scope == entity_scope
            )

            if (user_matches or group_matches) and scope_matches:
                await self.policy_repository.log_audit(
                    identity, tool_name, "ALLOW", "Matching Dataverse policy", correlation_id
                )
                return True

        # No matching policy found: Emit DENY audit and raise
        await self.policy_repository.log_audit(
            identity, tool_name, "DENY", "No matching active policy", correlation_id
        )
        raise AuthorizationDenied(f"You are not authorized to access this information.")


# Singleton instance for application runtime
_global_authorizer: Optional[ToolAuthorizer] = None


def get_tool_authorizer() -> ToolAuthorizer:
    global _global_authorizer
    if _global_authorizer is None:
        _global_authorizer = ToolAuthorizer()
    return _global_authorizer
