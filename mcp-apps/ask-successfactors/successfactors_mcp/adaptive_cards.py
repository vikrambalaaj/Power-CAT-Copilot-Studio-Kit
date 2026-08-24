"""Copilot-safe Adaptive Card instances for SuccessFactors tool results."""
from __future__ import annotations

import json
from typing import Any

from .chart_images import store_headcount_chart, store_joiners_chart
from .successfactors_settings import get_settings


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


def _headcount_card(result: dict[str, Any]) -> dict[str, Any]:
    breakdown = result.get("department_breakdown", [])
    bars = result.get("chart_bars", breakdown[:10])
    maximum = max((int(item.get("headcount", 0)) for item in bars), default=1)
    chart_data = [
        {
            "legend": str(item.get("department", "Unassigned")),
            "value": int(item.get("headcount", 0)),
            "color": ["categoricalPurple", "categoricalBlue", "categoricalTeal", "categoricalMarigold"][index % 4],
        }
        for index, item in enumerate(bars)
    ]
    chart_id = store_headcount_chart(bars, int(result.get("total_headcount", 0)))
    base_url = get_settings().public_base_url.rstrip("/")
    chart_url = f"{base_url}/charts/{chart_id}.png" if base_url else ""
    text_fallback = {
        "type": "TextBlock",
        "text": "\n".join(f"{item.get('department', 'Unassigned')}: {int(item.get('headcount', 0)):,} ({item.get('percentage', 0)}%)" for item in bars),
        "wrap": True,
    }
    image_fallback: dict[str, Any] = text_fallback
    if chart_url:
        image_fallback = {
            "type": "Image",
            "url": chart_url,
            "altText": "Horizontal bar chart of workforce headcount by department",
            "size": "Stretch",
            "fallback": text_fallback,
        }
    # Teams and Copilot Studio do not consistently render the preview Chart.*
    # elements. Send the generated image as the primary, standards-based card
    # element and retain text as its fallback.
    chart_element = image_fallback
    body: list[dict[str, Any]] = [
        {"type": "TextBlock", "text": "Workforce headcount by department", "weight": "Bolder", "size": "Medium", "wrap": True},
        {"type": "TextBlock", "text": "Complete role-visible aggregation from SAP SuccessFactors", "isSubtle": True, "wrap": True, "spacing": "Small"},
        {
            "type": "FactSet",
            "separator": True,
            "facts": [
                _fact("Total headcount", f"{int(result.get('total_headcount', 0)):,}"),
                _fact("Active headcount", f"{int(result.get('active_headcount') or 0):,}" if result.get("active_headcount") is not None else "Unavailable"),
                _fact("Departments", result.get("department_count", len(breakdown))),
                _fact("Rows evaluated", f"{int(result.get('rows_evaluated', 0)):,}"),
                _fact("Coverage", "Complete" if result.get("aggregation_complete") else "Partial"),
            ],
        },
        chart_element,
    ]
    for item in bars:
        count = int(item.get("headcount", 0))
        width = max(1, round((count / maximum) * 16))
        body.append({
            "type": "TextBlock",
            "text": f"**{item.get('department', 'Unassigned')}**  {'█' * width}  {count:,} ({item.get('percentage', 0)}%)",
            "wrap": True,
            "spacing": "Small",
        })
    if len(breakdown) > len(bars):
        body.append({"type": "TextBlock", "text": f"Plus {len(breakdown) - len(bars)} additional departments in the detailed result.", "isSubtle": True, "size": "Small", "wrap": True})
    return {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.5", "body": body}


def _joiners_card(result: dict[str, Any]) -> dict[str, Any]:
    breakdown = result.get("breakdown", [])
    label_key = "department" if result.get("group_by") == "department" else "period"
    maximum = max((int(item.get("joiners", 0)) for item in breakdown), default=1)
    bars = breakdown[:12]
    title = "Joiners by department" if label_key == "department" else "Joiners over time"
    chart_id = store_joiners_chart(bars, int(result.get("total_joiners", 0)), label_key, title)
    base_url = get_settings().public_base_url.rstrip("/")
    chart_url = f"{base_url}/charts/{chart_id}.png" if base_url else ""
    text_fallback = {
        "type": "TextBlock",
        "text": "\n".join(f"{item.get(label_key, 'Unknown')}: {int(item.get('joiners', 0)):,}" for item in bars) or "No joiners found for this period.",
        "wrap": True,
    }
    image_fallback: dict[str, Any] = text_fallback
    if chart_url:
        image_fallback = {
            "type": "Image", "url": chart_url, "altText": title,
            "size": "Stretch", "fallback": text_fallback,
        }
    chart_data = [
        {"legend": str(item.get(label_key, "Unknown")), "value": int(item.get("joiners", 0)),
         "color": ["categoricalBlue", "categoricalTeal", "categoricalPurple", "categoricalRed"][index % 4]}
        for index, item in enumerate(bars)
    ]
    body: list[dict[str, Any]] = [
        {"type": "TextBlock", "text": "New-hire analytics", "weight": "Bolder", "size": "Medium", "wrap": True},
        {"type": "TextBlock", "text": f"{result.get('start_date')} to {result.get('end_date')}", "isSubtle": True, "wrap": True},
        {"type": "FactSet", "separator": True, "facts": [_fact("Total joiners", f"{int(result.get('total_joiners', 0)):,}"), _fact("Coverage", "Complete" if result.get("aggregation_complete") else "Partial")]},
        image_fallback,
    ]
    for item in bars:
        count = int(item.get("joiners", 0))
        width = max(1, round((count / maximum) * 16))
        body.append({"type": "TextBlock", "text": f"**{item.get(label_key, 'Unknown')}**  {'█' * width}  {count:,}", "wrap": True, "spacing": "Small"})
    return {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.5", "body": body}


def _delivery_fields(card: dict[str, Any]) -> dict[str, Any]:
    """Expose fallbacks explicitly so Copilot topics can bind them without parsing the card."""
    for element in card.get("body", []):
        if element.get("type") == "Image":
            return {
                "chartImageUrl": element.get("url", ""),
                "chartTextFallback": element.get("fallback", {}).get("text", ""),
            }
        if str(element.get("type", "")).startswith("Chart."):
            fallback = element.get("fallback", {})
            if fallback.get("type") == "Image":
                return {
                    "chartImageUrl": fallback.get("url", ""),
                    "chartTextFallback": fallback.get("fallback", {}).get("text", ""),
                }
            return {"chartImageUrl": "", "chartTextFallback": fallback.get("text", "")}
    return {}


def _visualization_spec(result: dict[str, Any]) -> dict[str, Any]:
    """Return a compact, model-friendly presentation contract.

    The model may select and describe the presentation, while the Copilot topic
    renders the validated Adaptive Card JSON returned alongside this contract.
    """
    if result.get("type") in {"Headcount", "AnalyticsDashboard"}:
        rows = result.get("chart_bars", result.get("department_breakdown", [])[:10])
        return {
            "template": "ranked_horizontal_bar",
            "title": "Workforce headcount by department",
            "total": int(result.get("total_headcount", 0)),
            "categoryLabel": "Department",
            "valueLabel": "Headcount",
            "categories": [str(row.get("department", "Unassigned")) for row in rows],
            "values": [int(row.get("headcount", 0)) for row in rows],
            "source": "SAP SuccessFactors",
        }
    if result.get("type") == "JoinerAnalytics":
        label_key = "department" if result.get("group_by") == "department" else "period"
        rows = result.get("breakdown", [])[:12]
        return {
            "template": "ranked_horizontal_bar" if label_key == "department" else "period_comparison",
            "title": "Joiners by department" if label_key == "department" else "Joiners over time",
            "total": int(result.get("total_joiners", 0)),
            "categoryLabel": "Department" if label_key == "department" else "Period",
            "valueLabel": "Joiners",
            "categories": [str(row.get(label_key, "Unknown")) for row in rows],
            "values": [int(row.get("joiners", 0)) for row in rows],
            "source": "SAP SuccessFactors",
        }
    return {"template": "facts", "source": "SAP SuccessFactors"}


def _drilldown_card(result: dict[str, Any]) -> dict[str, Any]:
    dept = result.get("department", "All")
    total = result.get("total_matched", 0)
    page = result.get("page", 1)
    total_pages = result.get("total_pages", 1)
    employees = result.get("employees", [])
    has_next = result.get("has_next_page", False)
    next_page = result.get("next_page")
    policy_ver = result.get("policy_version", "1.0.0")

    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": f"👥 Workforce Drill-Down: {dept}",
            "weight": "Bolder",
            "size": "Medium",
            "color": "Accent",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": f"Dataverse Policy v{policy_ver} · {total} employees matched (Page {page} of {total_pages})",
            "isSubtle": True,
            "size": "Small",
            "wrap": True,
            "spacing": "None",
        },
    ]

    for emp in employees:
        name = emp.get("name", "Unknown")
        emp_id = emp.get("userId", "—")
        job = emp.get("jobTitle", "—")
        country = emp.get("country", "—")
        age_group = emp.get("age_group", "—")
        joined = emp.get("joined_date", "—")
        service = emp.get("length_of_service", "—")
        recruiter = emp.get("recruited_by", "—")

        body.append({
            "type": "TextBlock",
            "text": f"**{name}** (ID: `{emp_id}`) · {job}",
            "wrap": True,
            "spacing": "Medium",
            "separator": True,
        })
        body.append({
            "type": "TextBlock",
            "text": f"📍 **Country:** {country} | 🎂 **Age Group:** {age_group} | 📅 **Joined:** {joined} ({service}) | 🤝 **Recruiter:** {recruiter}",
            "size": "Small",
            "isSubtle": True,
            "wrap": True,
            "spacing": "None",
        })

    body.append({
        "type": "TextBlock",
        "text": "🔒 *Source: SAP SuccessFactors · Field-level privacy filters enforced by Microsoft Dataverse*",
        "size": "Small",
        "isSubtle": True,
        "wrap": True,
        "spacing": "Medium",
        "separator": True,
    })

    card: dict[str, Any] = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": body,
    }

    if has_next and next_page:
        card["actions"] = [
            {
                "type": "Action.Submit",
                "title": f"Next Page ({next_page}/{total_pages}) →",
                "data": {
                    "action": "drilldown_page",
                    "department": dept,
                    "page": next_page,
                },
            }
        ]

    return card


def _memory_recall_card(result: dict[str, Any]) -> dict[str, Any]:
    topic = result.get("query_topic", "Recent History")
    items = result.get("recalled_items", [])
    user_email = result.get("user_email", "")

    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": f"🧠 30-Day Memory Recall: {topic}",
            "weight": "Bolder",
            "size": "Medium",
            "color": "Accent",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": f"Dataverse Memory Partition for {user_email} · Last 30 Days",
            "isSubtle": True,
            "size": "Small",
            "wrap": True,
            "spacing": "None",
        },
    ]

    for item in items:
        date_str = item.get("date", "")
        summary = item.get("summary", "")
        body.append({
            "type": "TextBlock",
            "text": f"• **[{date_str}]**: {summary}",
            "wrap": True,
            "spacing": "Small",
        })

    body.append({
        "type": "TextBlock",
        "text": str(result.get("historical_notice", "⚠️ Historical context shown.")),
        "size": "Small",
        "color": "Warning",
        "wrap": True,
        "spacing": "Medium",
        "separator": True,
    })

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": body,
        "actions": [
            {
                "type": "Action.Submit",
                "title": "🔄 Refresh Latest Live SAP Data",
                "data": {"query": f"Refresh live SAP workforce numbers for {topic}"},
            }
        ],
    }


def decorate(data: dict[str, Any]) -> dict[str, Any]:
    result = dict(data)
    if result.get("error"):
        title = "SuccessFactors data unavailable"
        subtitle = "The requested workforce result could not be verified."
        card = _card(title, subtitle, [], status="Action required", status_color="Attention", note=str(result.get("message", "Check the configured data source.")))
    elif result.get("adaptiveCard"):
        # Pre-built card (e.g. SessionGreeting or ConsentGate)
        card = result.get("adaptiveCard")
        title = result.get("cardTitle") or "Velora Assistant"
        subtitle = result.get("cardSubtitle") or "Interactive Notification"
    else:
        kind = str(result.get("type", "SuccessFactorsResult"))
        if kind == "WorkforceDrilldown":
            title = f"Workforce drill-down ({result.get('department', 'All')})"
            subtitle = f"Dataverse Policy v{result.get('policy_version', '1.0.0')} · {result.get('total_matched', 0)} employees"
            card = _drilldown_card(result)
        elif kind == "Headcount":
            title = "Workforce headcount"
            subtitle = "SAP SuccessFactors · complete department aggregation"
            card = _headcount_card(result)
        elif kind == "JoinerAnalytics":
            title = "New-hire analytics"
            subtitle = "SAP SuccessFactors · verified aggregate joiners"
            card = _joiners_card(result)
        elif kind == "LeaverAnalytics":
            title = "Employee leavers & separations"
            subtitle = "SAP SuccessFactors · separation intelligence"
            facts = [
                _fact("Total leavers", result.get("total_leavers", 0)),
                _fact("Voluntary departures", result.get("voluntary_leavers")),
                _fact("Involuntary separations", result.get("involuntary_leavers")),
                _fact("Unclassified departures", result.get("unclassified_leavers", 0)),
                _fact("Top driver", result.get("top_separation_reason")),
            ]
            card = _card(title, subtitle, facts, status="Verified aggregate", status_color="Accent", note="Unavailable separation classifications remain unclassified and are not estimated.")
        elif kind == "AttritionAnalytics":
            title = "Workforce attrition rate"
            subtitle = "SAP SuccessFactors · organizational mobility KPI"
            rate = result.get("overall_attrition_rate_pct", 0)
            facts = [
                _fact("Overall attrition rate", f"{rate}%"),
                _fact("UAE National attrition", f"{result.get('uae_national_attrition_rate_pct')}%" if result.get("uae_national_attrition_rate_pct") is not None else "Unavailable"),
                _fact("Total departures", result.get("total_leavers", 0)),
                _fact("Active headcount evaluated", f"{result.get('total_headcount_evaluated', 0):,}"),
                _fact("Denominator method", result.get("denominator_method")),
            ]
            card = _card(title, subtitle, facts, status=f"{rate}% for period", status_color="Good" if rate < 10 else "Warning", note="Not annualized. Unavailable drivers are not estimated.")
        elif kind == "JoinerLeaverTrend":
            title = "Net workforce growth trend"
            subtitle = "SAP SuccessFactors · talent momentum & velocity"
            net_growth = result.get("net_talent_growth", 0)
            facts = [
                _fact("Total joiners", result.get("total_joiners", 0)),
                _fact("Total leavers", result.get("total_leavers", 0)),
                _fact("Net talent growth", f"+{net_growth}" if net_growth > 0 else str(net_growth)),
                _fact("Talent velocity ratio", f"{result.get('talent_replacement_ratio')}x" if result.get("talent_replacement_ratio") is not None else "Undefined (zero leavers)"),
                _fact("UAE National net growth", result.get("uae_national_net_growth")),
            ]
            card = _card(title, subtitle, facts, status=result.get("hiring_velocity_status", "EXPANDING"), status_color="Good" if net_growth > 0 else "Warning", note="Multi-period pipeline tracking net headcount expansion.")
        elif kind == "EmiratisationKPI":
            title = "Emiratisation KPI"
            subtitle = "Aggregate workforce measure · PDPL controls applied"
            status = str(result.get("target_compliance", "Status unavailable"))
            facts = [
                _fact("Current ratio", f"{result.get('emiratisation_ratio_percent', 0)}%"),
                _fact("UAE Nationals", result.get("uae_national_count")),
                _fact("Known non-UAE Nationals", result.get("non_uae_national_count")),
                _fact("Missing/unclassified", result.get("missing_unclassified_nationality_count")),
                _fact("Target", f"{result.get('target_percent', 0)}%"),
                _fact("Active eligible headcount", result.get("active_headcount")),
                _fact("As of", result.get("as_of_date") or "Current effective view"),
            ]
            card = _card(title, subtitle, facts, status=status.replace("_", " ").title(), status_color="Good" if status == "ON_TRACK" else "Warning", note="Individual nationality data is not displayed.")
        elif kind == "AnalyticsDashboard":
            title = "Workforce overview"
            subtitle = "SAP SuccessFactors executive summary"
            card = _headcount_card(result)
        elif kind == "MemoryRecall":
            title = "30-Day conversation memory"
            subtitle = f"Dataverse user partition ({result.get('user_email', '')})"
            card = _memory_recall_card(result)
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

    result.update({
        "cardTitle": title,
        "cardSubtitle": subtitle,
        "visualizationSpec": _visualization_spec(result),
        "adaptiveCard": card,
        "adaptiveCardJson": json.dumps(card, separators=(",", ":"), ensure_ascii=False),
        "cardDeliveryMode": "copilot_response_semantics",
        "cardRenderingInstruction": "Prefer the adaptiveCard response semantic. If it cannot render, show fallbackText from the MCP text content.",
        **_delivery_fields(card),
    })
    return result
