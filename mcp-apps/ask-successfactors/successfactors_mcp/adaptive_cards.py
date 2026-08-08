"""Copilot-safe Adaptive Card instances for SuccessFactors tool results."""
from __future__ import annotations

from typing import Any


def _fact(title: str, value: Any) -> dict[str, str]:
    return {"title": title, "value": "—" if value in (None, "") else str(value)}


def _card(
    title: str,
    subtitle: str,
    facts: list[dict[str, str]],
    *,
    status: str = "",
    status_color: str = "Accent",
    note: str = "",
) -> dict[str, Any]:
    body: list[dict[str, Any]] = [
        {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "wrap": True},
        {"type": "TextBlock", "text": subtitle, "isSubtle": True, "wrap": True, "spacing": "Small"},
    ]
    if status:
        body.append({"type": "TextBlock", "text": status, "weight": "Bolder", "color": status_color, "wrap": True})
    if facts:
        body.append({"type": "FactSet", "facts": facts, "separator": True})
    if note:
        body.append({"type": "TextBlock", "text": note, "size": "Small", "isSubtle": True, "wrap": True, "separator": True})
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": body,
    }


def decorate(data: dict[str, Any]) -> dict[str, Any]:
    result = dict(data)
    if result.get("error"):
        title = "SuccessFactors data unavailable"
        subtitle = "The requested workforce result could not be verified."
        result.update({
            "cardTitle": title,
            "cardSubtitle": subtitle,
            "adaptiveCard": _card(title, subtitle, [], status="Action required", status_color="Attention", note=str(result.get("message", "Check the configured data source."))),
        })
        return result

    kind = str(result.get("type", "SuccessFactorsResult"))
    if kind == "Headcount":
        title = "Workforce headcount"
        subtitle = "SAP SuccessFactors · EmpJob"
        facts = [
            _fact("Headcount", result.get("total_headcount")),
            _fact("Rows evaluated", result.get("sample_size")),
            _fact("As of", result.get("filters", {}).get("as_of_date") or "Current effective view"),
        ]
        note = "Department breakdown is sample-based." if result.get("sampled") else "Department breakdown covers the returned population."
        card = _card(title, subtitle, facts, status="Sampled" if result.get("sampled") else "Complete", status_color="Warning" if result.get("sampled") else "Good", note=note)
    elif kind == "EmiratisationKPI":
        title = "Emiratisation KPI"
        subtitle = "Aggregate workforce measure · PDPL controls applied"
        status = str(result.get("target_compliance", "Status unavailable"))
        facts = [
            _fact("Current ratio", f"{result.get('emiratisation_ratio_percent', 0)}%"),
            _fact("Target", f"{result.get('target_percent', 0)}%"),
            _fact("Eligible headcount", result.get("total_headcount")),
            _fact("As of", result.get("as_of_date") or "Current effective view"),
        ]
        card = _card(title, subtitle, facts, status=status.replace("_", " ").title(), status_color="Good" if status == "ON_TRACK" else "Warning", note="Individual nationality data is not displayed.")
    elif kind == "AnalyticsDashboard":
        title = "Workforce overview"
        subtitle = "SAP SuccessFactors executive summary"
        facts = [
            _fact("Active headcount", result.get("total_headcount")),
            _fact("Rows evaluated", result.get("sample_size")),
            _fact("Departments in sample", len(result.get("department_counts_sample", {}))),
        ]
        card = _card(title, subtitle, facts, status="Sample-based breakdown" if result.get("sample_size") != result.get("total_headcount") else "Current view", status_color="Warning" if result.get("sample_size") != result.get("total_headcount") else "Good")
    else:
        title = {
            "EmpJob": "Employee job records",
            "User": "Employee directory",
            "FOCompany": "Companies",
            "FOBusinessUnit": "Business units",
            "FODepartment": "Departments",
            "FODivision": "Divisions",
        }.get(kind, "SuccessFactors result")
        subtitle = str(result.get("source", "SAP SuccessFactors"))
        facts = [
            _fact("Records", result.get("total", len(result.get("results", [])))),
            _fact("Access", result.get("access_context", "Configured SAP authorization")),
        ]
        card = _card(title, subtitle, facts, note="Copilot shows only the fields needed for the answer.")

    result.update({"cardTitle": title, "cardSubtitle": subtitle, "adaptiveCard": card})
    return result
