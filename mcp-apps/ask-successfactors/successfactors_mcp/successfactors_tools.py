"""FastMCP tool specifications for SAP SuccessFactors HCM following Velora Delegated Identity Architecture."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult, TextContent

from .successfactors_client import SuccessFactorsClient
from .adaptive_cards import decorate as decorate_with_card
from shared_mcp.logger import get_logger

log = get_logger("sf_hcm")
_client = SuccessFactorsClient()


def _safe_result(data: Dict[str, Any]) -> Dict[str, Any]:
    """Keep validation guidance, but never expose backend or Python errors to users."""
    result = dict(data)
    if not result.get("error"):
        return result
    category = str(result.get("error_category") or "service")
    if category == "validation":
        message = str(result.get("message") or "The request parameters are invalid.")
    elif category in {"authorization", "permission"} or result.get("status") in {401, 403}:
        message = "I couldn't retrieve that information with the current access."
    else:
        message = "I couldn't retrieve that information right now. Please try again shortly."
    return {"error": True, "error_category": category, "message": message}


def _card_fallback_text(card: Dict[str, Any]) -> str:
    """Build concise readable fallback text without serializing card JSON."""
    lines: list[str] = []
    fact_seen = False
    for element in card.get("body", []):
        if not isinstance(element, dict):
            continue
        if element.get("type") == "FactSet":
            fact_seen = True
            for fact in element.get("facts", [])[:8]:
                if isinstance(fact, dict) and fact.get("title"):
                    lines.append(f"{fact.get('title')}: {fact.get('value', '—')}")
            continue
        if element.get("type") != "TextBlock":
            continue
        text = str(element.get("text") or "").strip()
        if not text:
            continue
        if text.lower().startswith("source:"):
            continue
        if not fact_seen or (element.get("isSubtle") and element.get("separator")):
            lines.append(text)
    return "\n".join(lines)[:3000]


def _json_response(data: Dict[str, Any]) -> Any:
    """Prefer an Adaptive Card while retaining the original result as fallback."""
    data = decorate_with_card(_safe_result(data))
    fallback_text = _card_fallback_text(data.get("adaptiveCard", {}))
    data.update({
        "presentationPreference": "adaptive_card",
        "fallbackPresentation": "text",
        "fallbackText": fallback_text,
    })
    return CallToolResult(
        # Non-card clients receive business-readable text, never card JSON.
        content=[TextContent(type="text", text=fallback_text)],
        structuredContent=data,
        isError=bool(data.get("error")),
    )


def build_adaptive_card(title: str, subtitle: str, facts: list, chart_bars: list = None, audit_info: dict = None) -> Dict[str, Any]:
    """Helper to build an Adaptive Card v1.5 JSON payload with Velora Reasoning, Sources & Audit metadata."""
    body = [
        {
            "type": "TextBlock",
            "text": f"📊 {title}",
            "weight": "Bolder",
            "size": "Medium",
            "color": "Accent"
        },
        {
            "type": "TextBlock",
            "text": subtitle,
            "isSubtle": True,
            "wrap": True
        },
        {
            "type": "FactSet",
            "facts": [{"title": f["title"], "value": str(f["value"])} for f in facts]
        }
    ]

    if chart_bars:
        body.append({
            "type": "TextBlock",
            "text": "📈 Department Headcount Distribution",
            "weight": "Bolder",
            "size": "Small",
            "spacing": "Medium"
        })
        for bar in chart_bars:
            fill_str = "█" * min(15, max(1, int(bar["count"] / 3)))
            body.append({
                "type": "TextBlock",
                "text": f"**{bar['dept']}**: {fill_str} {bar['count']} ({bar['pct']}%)",
                "wrap": True,
                "spacing": "None"
            })

    if audit_info:
        body.append({
            "type": "TextBlock",
            "text": f"🔒 *Source: {audit_info.get('source', 'SAP SuccessFactors')} | Access: configured SuccessFactors service account*",
            "size": "Small",
            "isSubtle": True,
            "spacing": "Medium"
        })

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": body
    }


# ──────── Handlers ─────────────────────────────────────────────────────────────

async def sf__get_emp_jobs(
    user_id: Optional[str] = None,
    company: Optional[str] = None,
    department: Optional[str] = None,
    business_unit: Optional[str] = None,
    job_title: Optional[str] = None,
    as_of_date: Optional[str] = None,
    top: int = 20,
) -> Any:
    """Retrieve headcount and job records allowed by the configured SuccessFactors account."""
    res = await _client.list_emp_jobs(
        user_id=user_id,
        company=company,
        department=department,
        business_unit=business_unit,
        job_title=job_title,
        as_of_date=as_of_date,
        top=top,
    )
    return _json_response(res)


async def sf__get_emiratisation_kpi(
    company: Optional[str] = None,
    as_of_date: Optional[str] = None,
) -> Any:
    """Return an aggregate Emiratisation KPI using the configured tenant-specific filter."""
    res = await _client.get_emiratisation_kpi(company=company, as_of_date=as_of_date)
    return _json_response(res)


async def sf__get_headcount(
    ctx: Context,
    company: Optional[str] = None,
    department: Optional[str] = None,
    business_unit: Optional[str] = None,
    as_of_date: Optional[str] = None,
) -> Any:
    """Return complete aggregate headcount by department description with an executive visualization and sources."""
    await ctx.report_progress(0.03, 1.0, "Connecting to SAP SuccessFactors test environment")

    async def report(progress: float, message: str) -> None:
        await ctx.report_progress(progress, 1.0, message)

    res = await _client.aggregate_headcount_by_department(
        company=company,
        department=department,
        business_unit=business_unit,
        as_of_date=as_of_date,
        progress_callback=report,
    )
    await ctx.report_progress(1.0, 1.0, "SuccessFactors analysis complete")
    return _json_response(res if isinstance(res, dict) else {"error": True, "message": "Unexpected SuccessFactors response"})


async def sf__get_joiners(
    ctx: Context,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    group_by: str = "month",
    company: Optional[str] = None,
) -> Any:
    """Return real, aggregate new-hire counts and trends for an inclusive date range. If dates are omitted, defaults to the current reporting period."""
    await ctx.report_progress(0.03, 1.0, "Connecting to SAP SuccessFactors test environment")

    async def report(progress: float, message: str) -> None:
        await ctx.report_progress(progress, 1.0, message)

    res = await _client.aggregate_joiners(
        start_date=start_date,
        end_date=end_date,
        group_by=group_by,
        company=company,
        progress_callback=report,
    )
    await ctx.report_progress(1.0, 1.0, "SuccessFactors joiner analysis complete")
    return _json_response(res if isinstance(res, dict) else {"error": True, "message": "Unexpected SuccessFactors response"})


async def sf__get_leavers(
    ctx: Context,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    group_by: str = "department",
    company: Optional[str] = None,
    reason_type: Optional[str] = "all",
) -> Any:
    """Return verified aggregate leaver/separation counts and reason breakdown from SAP SuccessFactors."""
    await ctx.report_progress(0.03, 1.0, "Connecting to SAP SuccessFactors test environment")

    async def report(progress: float, message: str) -> None:
        await ctx.report_progress(progress, 1.0, message)

    res = await _client.aggregate_leavers(
        start_date=start_date,
        end_date=end_date,
        group_by=group_by,
        company=company,
        reason_type=reason_type,
        progress_callback=report,
    )
    await ctx.report_progress(1.0, 1.0, "SuccessFactors leaver analysis complete")
    return _json_response(res if isinstance(res, dict) else {"error": True, "message": "Unexpected SuccessFactors response"})


async def sf__get_attrition(
    ctx: Context,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    company: Optional[str] = None,
    business_unit: Optional[str] = None,
) -> Any:
    """Calculate verified organization-wide and UAE National attrition rates with voluntary/involuntary drivers."""
    await ctx.report_progress(0.03, 1.0, "Connecting to SAP SuccessFactors test environment")

    async def report(progress: float, message: str) -> None:
        await ctx.report_progress(progress, 1.0, message)

    res = await _client.aggregate_attrition(
        start_date=start_date,
        end_date=end_date,
        company=company,
        business_unit=business_unit,
        progress_callback=report,
    )
    await ctx.report_progress(1.0, 1.0, "SuccessFactors attrition rate analysis complete")
    return _json_response(res if isinstance(res, dict) else {"error": True, "message": "Unexpected SuccessFactors response"})


async def sf__get_joiners_leavers_trend(
    ctx: Context,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    granularity: str = "month",
    company: Optional[str] = None,
) -> Any:
    """Return net workforce growth; omitted dates use the current year-to-date reporting period."""
    await ctx.report_progress(0.03, 1.0, "Connecting to SAP SuccessFactors test environment")

    async def report(progress: float, message: str) -> None:
        await ctx.report_progress(progress, 1.0, message)

    res = await _client.aggregate_joiners_leavers_trend(
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
        company=company,
        progress_callback=report,
    )
    await ctx.report_progress(1.0, 1.0, "SuccessFactors talent trend analysis complete")
    return _json_response(res if isinstance(res, dict) else {"error": True, "message": "Unexpected SuccessFactors response"})


async def sf__get_emp_job_detail(user_id: str, seq_num: int = 1) -> Any:
    """Retrieve a specific employee's job history record."""
    res = await _client.get_emp_job(user_id=user_id, seq_num=seq_num)
    return _json_response(res)


async def sf__create_emp_job(
    user_id: str,
    start_date: str,
    company: str,
    job_title: str,
    department: Optional[str] = None,
    business_unit: Optional[str] = None,
    employee_class: Optional[str] = None,
    employment_type: Optional[str] = None,
    event_reason: Optional[str] = None,
) -> Any:
    """Create a new job history entry (EmpJob) for an employee in SuccessFactors."""
    data = {
        "userId": user_id,
        "startDate": f"/Date({start_date})/" if not start_date.startswith("/") else start_date,
        "company": company,
        "jobTitle": job_title,
    }
    if department:
        data["department"] = department
    if business_unit:
        data["businessUnit"] = business_unit
    if employee_class:
        data["employeeClass"] = employee_class
    if employment_type:
        data["employmentType"] = employment_type
    if event_reason:
        data["eventReason"] = event_reason

    res = await _client.create_emp_job(data)
    return _json_response(res)


async def sf__update_emp_job(
    user_id: str,
    start_date: str,
    seq_num: int,
    job_title: Optional[str] = None,
    department: Optional[str] = None,
    business_unit: Optional[str] = None,
    employee_class: Optional[str] = None,
    employment_type: Optional[str] = None,
) -> Any:
    """Update an existing employee job history record in SuccessFactors."""
    update_fields = {}
    if job_title:
        update_fields["jobTitle"] = job_title
    if department:
        update_fields["department"] = department
    if business_unit:
        update_fields["businessUnit"] = business_unit
    if employee_class:
        update_fields["employeeClass"] = employee_class
    if employment_type:
        update_fields["employmentType"] = employment_type

    res = await _client.update_emp_job(user_id, start_date, seq_num, update_fields)
    return _json_response(res)


async def sf__get_users(
    query: Optional[str] = None,
    department: Optional[str] = None,
    status: Optional[str] = "active",
    top: int = 20,
) -> Any:
    """Retrieve employee directory profiles allowed by the configured SuccessFactors account."""
    res = await _client.list_users(query=query, department=department, status=status, top=top)
    return _json_response(res)


async def sf__get_user_detail(user_id: str) -> Any:
    """Retrieve details for a specific employee user ID."""
    res = await _client.get_user(user_id=user_id)
    return _json_response(res)


async def sf__update_user(
    user_id: str,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    email: Optional[str] = None,
    title: Optional[str] = None,
    department: Optional[str] = None,
    city: Optional[str] = None,
) -> Any:
    """Update employee profile details in SuccessFactors."""
    data = {}
    if first_name:
        data["firstName"] = first_name
    if last_name:
        data["lastName"] = last_name
    if email:
        data["email"] = email
    if title:
        data["title"] = title
    if department:
        data["department"] = department
    if city:
        data["city"] = city

    res = await _client.update_user(user_id, data)
    return _json_response(res)


async def sf__get_employment_info(user_id: str) -> Any:
    """Retrieve employment history and details (EmpEmployment)."""
    res = await _client.get_employment_info(user_id=user_id)
    return _json_response(res)


async def sf__get_personal_info(person_id_external: str) -> Any:
    """Retrieve personal information (PerPersonal) by external person ID."""
    res = await _client.get_personal_info(person_id_external=person_id_external)
    return _json_response(res)


async def sf__get_org_units(entity_type: str = "FOCompany", top: int = 20) -> Any:
    """Retrieve master org foundation objects (FOCompany, FOBusinessUnit, FODepartment, FODivision)."""
    res = await _client.list_org_units(entity_type=entity_type, top=top)
    return _json_response(res)


async def sf__get_analytics_dashboard() -> Any:
    """Retrieve a combined workforce overview from independently verified aggregate queries."""
    headcount = await _client.aggregate_headcount_by_department()
    if not isinstance(headcount, dict) or headcount.get("error"):
        return _json_response(headcount if isinstance(headcount, dict) else {"error": True, "message": "Headcount query failed."})
    emiratisation = await _client.get_emiratisation_kpi()
    omitted = []
    result = {**headcount, "type": "AnalyticsDashboard", "included_kpis": ["headcount"]}
    if isinstance(emiratisation, dict) and not emiratisation.get("error"):
        result["emiratisation"] = {
            key: emiratisation.get(key)
            for key in (
                "active_headcount", "uae_national_count", "non_uae_national_count",
                "missing_unclassified_nationality_count", "emiratisation_ratio_percent",
                "target_percent", "target_gap_percentage_points", "reconciliation",
                "population_definition", "rule_version", "warnings", "source",
            )
        }
        result["included_kpis"].append("emiratisation")
    else:
        omitted.append({
            "kpi": "emiratisation",
            "reason": emiratisation.get("message", "Emiratisation query failed.") if isinstance(emiratisation, dict) else "Emiratisation query failed.",
        })
    result["omitted_kpis"] = omitted
    return _json_response(result)


async def sf__execute_odata(
    entity: str,
    select: Optional[str] = None,
    filter_str: Optional[str] = None,
    top: int = 20,
    expand: Optional[str] = None,
) -> Any:
    """Execute an arbitrary OData v2 query against any SAP SuccessFactors entity."""
    res = await _client.execute_odata(
        entity=entity,
        select=select,
        filter_str=filter_str,
        top=top,
        expand=expand,
    )
async def sf__get_workforce_drilldown(
    department: Optional[str] = "Unassigned",
    company: Optional[str] = None,
    business_unit: Optional[str] = None,
    as_of_date: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    field_profile: str = "workforce_drilldown",
    user_object_id: Optional[str] = None,
    user_email: Optional[str] = None,
) -> Any:
    """Drill down into employee-level records for a specific group/department governed by Dataverse disclosure policy."""
    res = await _client.drilldown_employees(
        department=department,
        company=company,
        business_unit=business_unit,
        as_of_date=as_of_date,
        page=page,
        page_size=page_size,
        field_profile=field_profile,
        user_object_id=user_object_id,
        user_email=user_email,
    )
    return _json_response(res)


async def sf__check_and_record_consent(
    user_object_id: str = "",
    user_email: str = "",
    action: str = "check",
    accepted: bool = False,
    notice_version: str = "2026.1",
) -> Any:
    """Check user confidentiality consent or record consent acceptance in Microsoft Dataverse."""
    from .consent_service import get_consent_service
    svc = get_consent_service()
    if action == "record":
        res = await svc.record_user_consent(
            user_object_id=user_object_id,
            user_email=user_email,
            accepted=accepted,
            notice_version=notice_version,
        )
        return _json_response({
            "type": "ConsentRecorded",
            "status": "SUCCESS",
            "message": "Consent successfully recorded.",
            **res,
        })
    else:
        is_consented, card = await svc.verify_user_consent(
            user_object_id=user_object_id,
            user_email=user_email,
            notice_version=notice_version,
        )
        return _json_response({
            "type": "ConsentCheck",
            "is_consented": is_consented,
            "adaptiveCard": card if not is_consented else None,
            "message": "User consent verified." if is_consented else "Consent agreement required before proceeding.",
        })


async def sf__get_session_greeting(
    user_object_id: str = "",
    user_email: str = "",
    user_display_name: str = "",
    user_timezone: str = "Asia/Dubai",
) -> Any:
    """Generate session start greeting and capability starters while triggering background 30-day memory pre-load."""
    from .greeting_service import get_greeting_service
    svc = get_greeting_service()
    res = await svc.get_session_greeting(
        user_object_id=user_object_id,
        user_email=user_email,
        user_display_name=user_display_name,
        user_timezone=user_timezone,
    )
    return _json_response(res)


async def sf__recall_user_memory(
    user_object_id: str = "",
    user_email: str = "",
    topic_query: Optional[str] = None,
) -> Any:
    """Recall 30-day user conversation topics, decisions, and context from Dataverse."""
    from .memory_service import get_memory_service
    svc = get_memory_service()
    res = await svc.recall_user_context(
        user_object_id=user_object_id,
        user_email=user_email,
        topic_query=topic_query,
    )
    res["type"] = "MemoryRecall"
    return _json_response(res)


async def sf__manage_disclosure_policy(
    action: str = "list",
    policy_id: Optional[str] = None,
    policy_name: Optional[str] = None,
    policy_code: Optional[str] = None,
    version: Optional[str] = None,
    allowed_fields: Optional[List[str]] = None,
    is_active: bool = False,
    change_reason: str = "Policy update",
) -> Any:
    """Manage Dataverse employee disclosure policies (list, activate, create/update)."""
    from .policy_admin import get_policy_admin
    admin = get_policy_admin()
    if action == "activate" and policy_id:
        res = await admin.activate_policy(policy_id)
    elif action in {"create", "update"} and policy_name and policy_code and version:
        res = await admin.create_or_update_policy(
            policy_name=policy_name,
            policy_code=policy_code,
            version=version,
            allowed_fields=allowed_fields or [],
            is_active=is_active,
            change_reason=change_reason,
        )
    else:
        policies = await admin.list_policies()
        res = {"type": "PolicyList", "policies": policies, "total": len(policies)}
    return _json_response(res)


async def sf__preview_disclosure_policy(
    sample_query: str = "Who are the 15 employees in the Unassigned department?",
    profile: str = "workforce_drilldown",
) -> Any:
    """Preview permitted vs prohibited employee fields under active Dataverse policy."""
    from .policy_admin import get_policy_admin
    admin = get_policy_admin()
    res = admin.preview_policy_output(sample_query=sample_query, profile=profile)
    res["type"] = "PolicyPreview"
    return _json_response(res)


# ──────── Specifications ────────────────────────────────────────────────────────

TOOL_SPECS = [
    {
        "name": "sf__get_workforce_drilldown",
        "description": "Drill down from aggregate groups (such as 'Who are the 15 employees in Unassigned?') into individual employee records governed by active Dataverse disclosure policy. Enforces field allowlists, server-side age ranges, original hire dates, and role verification.",
        "handler": sf__get_workforce_drilldown,
    },
    {
        "name": "sf__check_and_record_consent",
        "description": "Check whether the authenticated user has agreed to the Velora confidentiality notice or record user acceptance in Dataverse.",
        "handler": sf__check_and_record_consent,
    },
    {
        "name": "sf__get_session_greeting",
        "description": "Present the initial session greeting and capability starters while asynchronously loading 30-day user memory in the background.",
        "handler": sf__get_session_greeting,
    },
    {
        "name": "sf__recall_user_memory",
        "description": "Recall past conversation topics, decisions, and follow-up items from the user's 30-day Dataverse memory partition.",
        "handler": sf__recall_user_memory,
    },
    {
        "name": "sf__manage_disclosure_policy",
        "description": "Administrative tool to view, draft, or activate Dataverse employee disclosure policies and trigger cache invalidation.",
        "handler": sf__manage_disclosure_policy,
    },
    {
        "name": "sf__preview_disclosure_policy",
        "description": "Generate a preview comparing released vs permanently prohibited fields for a given employee query under active policy.",
        "handler": sf__preview_disclosure_policy,
    },
    {
        "name": "sf__get_joiners",
        "description": "Fallback only for explicitly dated or filtered analysis. For normal Copilot aggregate responses, use the enabled native Adaptive Card workforce connector instead. Returns distinct joiners over an inclusive YYYY-MM-DD range with reconciled breakdowns and nationality aggregates when available; never use employee-directory records to calculate hiring analytics.",
        "handler": sf__get_joiners,
    },
    {
        "name": "sf__get_leavers",
        "description": "Fallback only for explicitly dated or filtered analysis. For normal Copilot aggregate responses, use the enabled native Adaptive Card workforce connector instead. Returns verified distinct leavers over an inclusive YYYY-MM-DD range; unavailable reason or organization classifications are explicitly unclassified and never estimated.",
        "handler": sf__get_leavers,
    },
    {
        "name": "sf__get_attrition",
        "description": "Fallback only for explicitly dated or filtered analysis. For normal Copilot aggregate responses, use the enabled native Adaptive Card workforce connector instead. Calculates period leavers divided by current active headcount, is not annualized, and never substitutes historical values.",
        "handler": sf__get_attrition,
    },
    {
        "name": "sf__get_joiners_leavers_trend",
        "description": "Fallback for explicitly dated or filtered joiner-versus-leaver analysis. For normal aggregate Copilot responses, prefer the enabled native Adaptive Card workforce connector. If dates are omitted, use the current year-to-date period without asking a follow-up question. Every period is calculated from live joiner and leaver results; period totals must match headline totals and zero denominators are not converted to fallback values.",
        "handler": sf__get_joiners_leavers_trend,
    },
    {
        "name": "sf__get_headcount",
        "description": "Fallback only for explicitly dated or filtered analysis. For normal Copilot aggregate responses, use the enabled native Adaptive Card workforce connector instead. Returns distinct current-effective employees, active headcount, complete pagination, and reconciled department breakdowns.",
        "handler": sf__get_headcount,
    },
    {
        "name": "sf__get_analytics_dashboard",
        "description": "Fallback only when the native Adaptive Card workforce connector is unavailable. Builds a combined overview from independently verified KPIs, preserves each population and period, and omits any KPI whose query failed.",
        "handler": sf__get_analytics_dashboard,
    },
    {
        "name": "sf__get_emiratisation_kpi",
        "description": "Fallback only for explicitly dated or filtered analysis. For normal Copilot aggregate responses, use the enabled native Adaptive Card workforce connector instead. Uses the configured nationality mapping and the same active population for numerator and denominator; missing nationality stays separate and individual nationality is never exposed.",
        "handler": sf__get_emiratisation_kpi,
    },
    {
        "name": "sf__get_emp_jobs",
        "description": "Use only for an authorized, narrowly filtered employee or organization job-history lookup. Never use for aggregate headcount. Returns a minimized field allowlist plus total, rows returned, and partial-result status.",
        "handler": sf__get_emp_jobs,
    },
    {
        "name": "sf__get_emp_job_detail",
        "description": "Use only for an authorized lookup of one identified employee and job-history sequence. Returns only approved job fields and effective dates.",
        "handler": sf__get_emp_job_detail,
    },
    {
        "name": "sf__create_emp_job",
        "description": "Create a new employee job history record in EmpJob.",
        "handler": sf__create_emp_job,
    },
    {
        "name": "sf__update_emp_job",
        "description": "Update an existing employee job history record in EmpJob.",
        "handler": sf__update_emp_job,
    },
    {
        "name": "sf__get_users",
        "description": "Use for a narrow employee-directory lookup by name, email, ID, or department. Requires a lookup filter, returns directory-safe fields only, and must not be used to enumerate the workforce or calculate analytics.",
        "handler": sf__get_users,
    },
    {
        "name": "sf__get_user_detail",
        "description": "Use only for an authorized lookup of one resolved employee ID. Returns an approved directory-safe field allowlist rather than the full User entity.",
        "handler": sf__get_user_detail,
    },
    {
        "name": "sf__update_user",
        "description": "Update employee profile details (first_name, last_name, email, title, department, city) in SuccessFactors.",
        "handler": sf__update_user,
    },
    {
        "name": "sf__get_employment_info",
        "description": "Use only for an authorized employment-date or employment-relationship question about one identified employee. Returns a minimized effective-date field allowlist.",
        "handler": sf__get_employment_info,
    },
    {
        "name": "sf__get_personal_info",
        "description": "Restricted personal-information lookup. Disabled by default for the executive agent and never used for aggregate analytics or Emiratisation.",
        "handler": sf__get_personal_info,
    },
    {
        "name": "sf__get_org_units",
        "description": "Use to resolve exact SuccessFactors company, business-unit, division, or department codes before applying organization filters. Returns total, rows returned, and completeness status.",
        "handler": sf__get_org_units,
    },
    {
        "name": "sf__execute_odata",
        "description": "Execute an arbitrary OData v2 query against any SAP SuccessFactors entity with optional $select, $filter, $top, and $expand.",
        "handler": sf__execute_odata,
    },
]

PROMPT_SPECS = []

