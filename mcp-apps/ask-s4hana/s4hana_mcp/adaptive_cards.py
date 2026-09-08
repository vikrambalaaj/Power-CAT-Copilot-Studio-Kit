"""Copilot-safe Adaptive Card instances for S/4HANA finance results."""
from __future__ import annotations

from typing import Any

from .contracts import format_decimal
from .report_calculations import _get_record_currency


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
    status_str = str(result.get("status", "")).upper()
    if status_str in {"ERROR", "CONTRACT_MISMATCH"}:
        title = "S/4HANA financial contract mismatch" if status_str == "CONTRACT_MISMATCH" else "S/4HANA finance data unavailable"
        subtitle = "Source record validation failed." if status_str == "CONTRACT_MISMATCH" else "The requested result could not be verified."
        msg = str(result.get("message", "Check the configured finance service."))
        code = str(result.get("code", status_str))
        card = _card(
            title,
            subtitle,
            [_fact("Error Code", code), _fact("Status", status_str)],
            status="Validation Error" if status_str == "CONTRACT_MISMATCH" else "Action required",
            color="Attention",
            note=msg,
        )
        result.update({"cardTitle": title, "cardSubtitle": subtitle, "adaptiveCard": card})
        return result

    kind = str(result.get("type", "FinanceResult"))
    titles = {
        "ReceivablesAging": "Receivables aging",
        "PayablesAging": "Payables aging",
        "BudgetTransfer": "Budget movements",
        "BudgetConsumption": "Budget consumption",
        "CustomerMaster": "Customer Master Data",
        "CostCenterMaster": "Cost Center Master Data",
        "ProfitCenterMaster": "Profit Center Master Data",
    }
    title = titles.get(kind, "S/4HANA finance result")
    source = result.get("sources", [{}])[0] if result.get("sources") else result.get("source", {})
    query = result.get("query", {})
    quality = result.get("quality", {})
    coverage = result.get("coverage", {})
    filters = query.get("filters", {})
    subtitle = f"SAP S/4HANA · {source.get('businessTitle', source.get('object', 'Finance Service'))}"

    calcs = result.get("calculations", {})
    is_multi = bool(calcs.get("is_multi_currency"))
    curr_list = ", ".join(calcs.get("currencies_present", []))

    currency = calcs.get("currency")
    if not currency or currency == "MULTI":
        for r in result.get("data", {}).get("records", []):
            c = _get_record_currency(r, entity_type=kind)
            if c:
                currency = c
                break
    currency = currency or query.get("currency") or "AED"

    if kind == "ReceivablesAging":
        if is_multi:
            facts = [
                _fact("Company code", filters.get("CompanyCode", "1000")),
                _fact("Currencies", curr_list),
                _fact("Balances", f"Partitioned across {len(calcs.get('currencies_present', []))} currencies"),
                _fact("Records retrieved", f"{coverage.get('rowsRead', 0)} of {coverage.get('declaredTotal', 0)}"),
            ]
            note = calcs.get("warning", "Partitioned by currency; unified aggregation disallowed without approved exchange rates.")
        else:
            facts = [
                _fact("Company code", filters.get("CompanyCode", "1000")),
                _fact("Net open balance", f"{currency} {format_decimal(calcs.get('total_open_signed'))}"),
                _fact("Overdue exposure", f"{currency} {format_decimal(calcs.get('overdue_exposure'))}"),
                _fact("Records retrieved", f"{coverage.get('rowsRead', 0)} of {coverage.get('declaredTotal', 0)}"),
            ]
            note = "Source: Finance's customer open-invoice report in SAP. Credits treated according to Finance policy."

    elif kind == "PayablesAging":
        if is_multi:
            facts = [
                _fact("Company code", filters.get("CompanyCode", "1000")),
                _fact("Currencies", curr_list),
                _fact("Balances", f"Partitioned across {len(calcs.get('currencies_present', []))} currencies"),
                _fact("Records retrieved", f"{coverage.get('rowsRead', 0)} of {coverage.get('declaredTotal', 0)}"),
            ]
            note = calcs.get("warning", "Partitioned by currency; unified aggregation disallowed without approved exchange rates.")
        else:
            facts = [
                _fact("Company code", filters.get("CompanyCode", "1000")),
                _fact("Total open balance", f"{currency} {format_decimal(calcs.get('total_open_signed'))}"),
                _fact("Overdue obligations", f"{currency} {format_decimal(calcs.get('overdue_exposure'))}"),
                _fact("Records retrieved", f"{coverage.get('rowsRead', 0)} of {coverage.get('declaredTotal', 0)}"),
            ]
            note = "Source: Finance's unpaid-supplier report in SAP. Informational report, not payment approval."

    elif kind == "BudgetTransfer":
        if is_multi:
            facts = [
                _fact("Funds management area", filters.get("FinancialManagementArea", "1000")),
                _fact("Currencies", curr_list),
                _fact("Movements", f"Partitioned across {len(calcs.get('currencies_present', []))} currencies"),
                _fact("Records retrieved", f"{coverage.get('rowsRead', 0)}"),
                _fact("Period / Year", query.get("period") or "Current"),
            ]
            note = "Partitioned by currency; unified aggregation disallowed without approved exchange rates."
        else:
            facts = [
                _fact("Funds management area", filters.get("FinancialManagementArea", "1000")),
                _fact("Total movement amount", f"{currency} {format_decimal(calcs.get('total_movement_amount'))}"),
                _fact("Records retrieved", f"{coverage.get('rowsRead', 0)}"),
                _fact("Period / Year", query.get("period") or "Current"),
            ]
            note = "Source: Finance's budget-entry and movement register. Original budget entries remain distinct from transfers."

    elif kind == "BudgetConsumption":
        if is_multi:
            facts = [
                _fact("Funds management area", filters.get("FinancialManagementArea", "1000")),
                _fact("Currencies", curr_list),
                _fact("Budget Breakdown", f"Partitioned across {len(calcs.get('currencies_present', []))} currencies"),
                _fact("Records retrieved", f"{coverage.get('rowsRead', 0)}"),
            ]
            note = "Partitioned by currency; unified aggregation disallowed without approved exchange rates."
        else:
            facts = [
                _fact("Funds management area", filters.get("FinancialManagementArea", "1000")),
                _fact("Budget amount", f"{currency} {format_decimal(calcs.get('raw_budget'))}"),
                _fact("Actual expenditure", f"{currency} {format_decimal(calcs.get('raw_actuals'))}"),
                _fact("Open commitments", f"{currency} {format_decimal(calcs.get('raw_commitments'))}"),
            ]
            note = "Source: Finance's budget and expenditure report. Derived utilization metrics require confirmed business mapping."

    elif kind == "CustomerMaster":
        records = result.get("data", {}).get("records", [])
        sample_cust = records[0] if records else {}
        facts = [
            _fact("Total Matches", result.get("data", {}).get("total", len(records))),
            _fact("Customer Code", sample_cust.get("Customer") or filters.get("Customer")),
            _fact("Customer Name", sample_cust.get("CustomerName") or filters.get("CustomerName")),
            _fact("City / Country", f"{sample_cust.get('City', '')}, {sample_cust.get('Country', '')}".strip(", ")),
        ]
        note = "Source: SAP S/4HANA Customer Master"
    else:
        facts = [
            _fact("Records", result.get("data", {}).get("total")),
            _fact("Scope", filters.get("CompanyCode") or filters.get("FinancialManagementArea")),
            _fact("Period", query.get("period")),
            _fact("Currency", currency),
        ]
        note = "Source: SAP S/4HANA Finance"

    is_complete = bool(quality.get("complete", True))
    sampled = bool(quality.get("sampled", False))
    status_text = "Complete returned result" if is_complete else "Sampled or bounded result"
    color = "Good" if is_complete else "Warning"
    
    card = _card(title, subtitle, facts, status=status_text, color=color, note=note)
    result.update({"cardTitle": title, "cardSubtitle": subtitle, "adaptiveCard": card})
    return result
