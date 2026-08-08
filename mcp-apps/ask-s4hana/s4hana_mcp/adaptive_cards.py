"""Copilot-safe Adaptive Card instances for S/4HANA finance results."""
from __future__ import annotations

from typing import Any


def _fact(title: str, value: Any) -> dict[str, str]:
    return {"title": title, "value": "—" if value in (None, "") else str(value)}


def _card(title: str, subtitle: str, facts: list[dict[str, str]], *, status: str, color: str, note: str) -> dict[str, Any]:
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "wrap": True},
            {"type": "TextBlock", "text": subtitle, "isSubtle": True, "wrap": True, "spacing": "Small"},
            {"type": "TextBlock", "text": status, "weight": "Bolder", "color": color, "wrap": True},
            {"type": "FactSet", "facts": facts, "separator": True},
            {"type": "TextBlock", "text": note, "size": "Small", "isSubtle": True, "wrap": True, "separator": True},
        ],
    }


def decorate(data: dict[str, Any]) -> dict[str, Any]:
    result = dict(data)
    if result.get("status") == "error":
        title = "S/4HANA finance data unavailable"
        subtitle = "The requested result could not be verified."
        card = _card(title, subtitle, [], status="Action required", color="Attention", note=str(result.get("message", "Check the configured finance service.")))
        result.update({"cardTitle": title, "cardSubtitle": subtitle, "adaptiveCard": card})
        return result

    kind = str(result.get("type", "FinanceResult"))
    titles = {
        "ReceivablesAging": "Receivables aging",
        "PayablesAging": "Payables aging",
        "ProfitAndLoss": "Profit and loss",
        "BudgetVariance": "Budget variance",
    }
    title = titles.get(kind, "S/4HANA finance result")
    source = result.get("source", {})
    query = result.get("query", {})
    quality = result.get("quality", {})
    filters = query.get("filters", {})
    subtitle = f"SAP S/4HANA · {source.get('object', 'approved finance service')}"
    facts = [
        _fact("Records", result.get("data", {}).get("total")),
        _fact("Company code", filters.get("CompanyCode")),
        _fact("Period / key date", query.get("period")),
        _fact("Currency", query.get("currency") or "As returned by SAP"),
    ]
    sampled = bool(quality.get("sampled"))
    status = "Sampled result" if sampled else "Complete returned result"
    note = "Copilot will label conclusions that rely on a partial record set." if sampled else "Figures remain subject to the configured ledger, hierarchy, and SAP authorization."
    card = _card(title, subtitle, facts, status=status, color="Warning" if sampled else "Good", note=note)
    result.update({"cardTitle": title, "cardSubtitle": subtitle, "adaptiveCard": card})
    return result
