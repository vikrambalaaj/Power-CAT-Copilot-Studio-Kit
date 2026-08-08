"""FastMCP tool specifications for SAP SuccessFactors HCM following Velora Delegated Identity Architecture."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from mcp.types import CallToolResult, TextContent

from .successfactors_client import SuccessFactorsClient
from .adaptive_cards import decorate as decorate_with_card
from shared_mcp.logger import get_logger

log = get_logger("sf_hcm")
_client = SuccessFactorsClient()


def _json_response(data: Dict[str, Any]) -> Any:
    """Return both readable JSON text and MCP structured content."""
    data = decorate_with_card(data)
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, ensure_ascii=False, default=str))],
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
    company: Optional[str] = None,
    department: Optional[str] = None,
    business_unit: Optional[str] = None,
    as_of_date: Optional[str] = None,
) -> Any:
    """Return aggregate headcount and a sample-derived department breakdown."""
    res = await _client.list_emp_jobs(
        company=company,
        department=department,
        business_unit=business_unit,
        as_of_date=as_of_date,
        top=1000,
    )
    if not isinstance(res, dict) or res.get("error"):
        return _json_response(res if isinstance(res, dict) else {"error": True, "message": "Unexpected SuccessFactors response"})
    rows = res.get("results", [])
    departments: Dict[str, int] = {}
    for row in rows:
        name = row.get("department") or "Unassigned"
        departments[name] = departments.get(name, 0) + 1
    total = int(res.get("total", len(rows)))
    return _json_response({
        "type": "Headcount",
        "total_headcount": total,
        "sample_size": len(rows),
        "department_breakdown_sample": departments,
        "sampled": len(rows) < total,
        "filters": {
            "company": company,
            "department": department,
            "business_unit": business_unit,
            "as_of_date": as_of_date,
        },
        "source": "SAP SuccessFactors · EmpJob",
        "access_context": "configured_service_account",
        "cache": res.get("cache", {}),
    })


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
    """Retrieve a workforce summary and sample-based department breakdown from SuccessFactors."""
    res = await _client.list_users(status="active", top=100)
    if not isinstance(res, dict) or res.get("error"):
        return _json_response(res if isinstance(res, dict) else {"error": True, "message": "Unexpected SuccessFactors response"})
    users = res.get("results", [])
    total = int(res.get("total", len(users)))

    dept_counts = {}
    for u in users:
        dept = u.get("department") or "Unassigned"
        dept_counts[dept] = dept_counts.get(dept, 0) + 1

    chart_bars = []
    for dept, count in dept_counts.items():
        pct = round((count / len(users)) * 100, 1) if users else 0
        chart_bars.append({"dept": dept, "count": count, "pct": pct})
    chart_bars.sort(key=lambda item: item["count"], reverse=True)

    facts = [
        {"title": "Total Active Headcount:", "value": f"{total} Employees"},
        {"title": "Active Departments:", "value": str(len(dept_counts))},
        {"title": "Company Tenant:", "value": _client.settings.sf_company_id},
        {"title": "Largest Department in Sample:", "value": f"{chart_bars[0]['dept']} ({chart_bars[0]['count']})" if chart_bars else "No data"}
    ]

    audit_info = {
        "source": "SAP SuccessFactors · EmpJob",
        "access_context": "configured_service_account"
    }

    card = build_adaptive_card(
        title="Velora Executive Headcount & Analytics",
        subtitle=f"Permission-trimmed headcount breakdown for company {_client.settings.sf_company_id}",
        facts=facts,
        chart_bars=chart_bars,
        audit_info=audit_info
    )

    return _json_response({
        "type": "AnalyticsDashboard",
        "total_headcount": total,
        "sample_size": len(users),
        "department_counts_sample": dept_counts,
        "chart_bars": chart_bars,
        "adaptiveCard": card,
        "source": "SAP SuccessFactors · EmpJob",
        "access_context": "configured_service_account",
        "cache": res.get("cache", {}),
    })


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
    return _json_response(res)


# ──────── Specifications ────────────────────────────────────────────────────────

TOOL_SPECS = [
    {
        "name": "sf__get_headcount",
        "description": "Return aggregate headcount and a department breakdown from SAP SuccessFactors EmpJob.",
        "handler": sf__get_headcount,
    },
    {
        "name": "sf__get_analytics_dashboard",
        "description": "Retrieve a workforce summary and sample-based department breakdown from SAP SuccessFactors.",
        "handler": sf__get_analytics_dashboard,
    },
    {
        "name": "sf__get_emiratisation_kpi",
        "description": "Return an aggregate Emiratisation KPI using the tenant-specific filter configured by the administrator.",
        "handler": sf__get_emiratisation_kpi,
    },
    {
        "name": "sf__get_emp_jobs",
        "description": "Retrieve employee job history records allowed by the configured SuccessFactors account.",
        "handler": sf__get_emp_jobs,
    },
    {
        "name": "sf__get_emp_job_detail",
        "description": "Retrieve specific employee job history entry by user_id and seq_num.",
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
        "description": "Retrieve employee directory profiles from SAP SuccessFactors. Filter by name/email/ID (query), department, or status.",
        "handler": sf__get_users,
    },
    {
        "name": "sf__get_user_detail",
        "description": "Retrieve full profile details for a specific user ID in SuccessFactors.",
        "handler": sf__get_user_detail,
    },
    {
        "name": "sf__update_user",
        "description": "Update employee profile details (first_name, last_name, email, title, department, city) in SuccessFactors.",
        "handler": sf__update_user,
    },
    {
        "name": "sf__get_employment_info",
        "description": "Retrieve employment details (EmpEmployment) for an employee.",
        "handler": sf__get_employment_info,
    },
    {
        "name": "sf__get_personal_info",
        "description": "Retrieve personal details (PerPersonal) by personIdExternal.",
        "handler": sf__get_personal_info,
    },
    {
        "name": "sf__get_org_units",
        "description": "Retrieve organization foundation master data (FOCompany, FOBusinessUnit, FODepartment, FODivision).",
        "handler": sf__get_org_units,
    },
    {
        "name": "sf__execute_odata",
        "description": "Execute an arbitrary OData v2 query against any SAP SuccessFactors entity with optional $select, $filter, $top, and $expand.",
        "handler": sf__execute_odata,
    },
]

PROMPT_SPECS = []
