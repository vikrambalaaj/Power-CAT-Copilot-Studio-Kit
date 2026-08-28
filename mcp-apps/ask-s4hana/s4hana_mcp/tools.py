"""Stable finance tool contracts for the Velora Executive Agent."""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from mcp.types import CallToolResult, TextContent

from .client import S4Client
from .adaptive_cards import decorate as decorate_with_card

client = S4Client()


def build_text_summary(data: dict[str, Any]) -> str:
    if data.get("status") == "error":
        return f"SAP S/4HANA Error: {data.get('message', 'Unable to retrieve records.')}"
    
    result_type = data.get("type", "")
    records = data.get("data", {}).get("records", [])
    total_count = data.get("data", {}).get("total", len(records))
    filters = data.get("query", {}).get("filters", {})
    comp_code = filters.get("CompanyCode", "1000")
    
    if result_type == "PayablesAging":
        total_open = 0.0
        b0_30 = 0.0
        b31_90 = 0.0
        b91_180 = 0.0
        b180_plus = 0.0
        supplier_totals: dict[str, float] = {}
        
        for r in records:
            amt = abs(float(r.get("OpenAmount") or 0.0))
            total_open += amt
            days = int(r.get("DaysOverdue") or 0)
            if days <= 30:
                b0_30 += amt
            elif days <= 90:
                b31_90 += amt
            elif days <= 180:
                b91_180 += amt
            else:
                b180_plus += amt
            
            sup_name = r.get("SupplierName") or r.get("Supplier") or "Unknown Supplier"
            supplier_totals[sup_name] = supplier_totals.get(sup_name, 0.0) + amt
            
        top_suppliers = sorted(supplier_totals.items(), key=lambda x: x[1], reverse=True)[:5]
        top_sup_str = "\n".join([f"  • {name}: AED {amt:,.2f}" for name, amt in top_suppliers]) or "  • None reported"
        
        return (
            f"### SAP S/4HANA Accounts Payable Aging Summary\n"
            f"• **Company Code**: {comp_code}\n"
            f"• **Total Open Records**: {total_count:,}\n"
            f"• **Sampled Open Balance**: AED {total_open:,.2f}\n\n"
            f"**Aging Buckets**:\n"
            f"  • Current (0–30 days): AED {b0_30:,.2f}\n"
            f"  • 31–90 days: AED {b31_90:,.2f}\n"
            f"  • 91–180 days: AED {b91_180:,.2f}\n"
            f"  • Over 180 days: AED {b180_plus:,.2f}\n\n"
            f"**Top Suppliers by Open Balance**:\n{top_sup_str}\n\n"
            f"*Source: SAP S/4HANA*"
        )
    
    if result_type == "ReceivablesAging":
        total_open = 0.0
        b0_30 = 0.0
        b31_90 = 0.0
        b91_180 = 0.0
        b180_plus = 0.0
        cust_totals: dict[str, float] = {}
        
        for r in records:
            amt = abs(float(r.get("OpenAmount") or 0.0))
            total_open += amt
            days = int(r.get("DaysOverdue") or 0)
            if days <= 30:
                b0_30 += amt
            elif days <= 90:
                b31_90 += amt
            elif days <= 180:
                b91_180 += amt
            else:
                b180_plus += amt
            
            cust_name = r.get("CustomerName") or r.get("Customer") or "Unknown Customer"
            cust_totals[cust_name] = cust_totals.get(cust_name, 0.0) + amt
            
        top_customers = sorted(cust_totals.items(), key=lambda x: x[1], reverse=True)[:5]
        top_cust_str = "\n".join([f"  • {name}: AED {amt:,.2f}" for name, amt in top_customers]) or "  • None reported"
        
        return (
            f"### SAP S/4HANA Accounts Receivable Aging Summary\n"
            f"• **Company Code**: {comp_code}\n"
            f"• **Total Open Records**: {total_count:,}\n"
            f"• **Sampled Open Balance**: AED {total_open:,.2f}\n\n"
            f"**Aging Buckets**:\n"
            f"  • Current (0–30 days): AED {b0_30:,.2f}\n"
            f"  • 31–90 days: AED {b31_90:,.2f}\n"
            f"  • 91–180 days: AED {b91_180:,.2f}\n"
            f"  • Over 180 days: AED {b180_plus:,.2f}\n\n"
            f"**Top Customers by Balance**:\n{top_cust_str}\n\n"
            f"*Source: SAP S/4HANA*"
        )
        
    return json.dumps(data, ensure_ascii=False, default=str)


def response(data: dict[str, Any]) -> CallToolResult:
    data = decorate_with_card(data)
    text_summary = build_text_summary(data)
    if "result" not in data:
        data["result"] = dict(data)
    return CallToolResult(
        content=[TextContent(type="text", text=text_summary)],
        structuredContent=data,
        isError=data.get("status") == "error",
    )


def live_key_date_error(key_date: str | None) -> dict[str, Any] | None:
    if not key_date:
        return None
    try:
        requested = date.fromisoformat(key_date)
    except ValueError:
        return {"status": "error", "code": "INVALID_KEY_DATE", "message": "Key date must use YYYY-MM-DD."}
    if requested != date.today():
        return {
            "status": "error",
            "code": "HISTORICAL_AGING_UNAVAILABLE",
            "message": "This SAP aging service supports only the current live key date.",
        }
    return None


async def s4__get_receivables_aging(
    company_code: str | None = None,
    key_date: str | None = None,
    customer: str | None = None,
    currency: str | None = None,
    correlation_id: str | None = None,
    top: int = 100,
) -> Any:
    """Return allowlisted S/4HANA receivables-aging records for an executive summary."""
    comp = company_code or "1000"
    cust = customer
    curr = currency
    date_val = key_date
    if key_date_error := live_key_date_error(date_val):
        return response(key_date_error)
    
    filters = {"CompanyCode": str(comp)}
    if cust:
        filters["Customer"] = str(cust)
    if curr:
        filters["Currency"] = str(curr)
    return response(await client.query(
        client.settings.s4_ar_entity,
        "ReceivablesAging",
        filters,
        period=date_val,
        currency=curr,
        correlation_id=correlation_id,
        top=top,
    ))


async def s4__get_payables_aging(
    company_code: str | None = None,
    key_date: str | None = None,
    supplier: str | None = None,
    currency: str | None = None,
    correlation_id: str | None = None,
    top: int = 100,
) -> Any:
    """Return allowlisted S/4HANA payables-aging records for an executive summary."""
    comp = company_code or "1000"
    supp = supplier
    curr = currency
    date_val = key_date
    if key_date_error := live_key_date_error(date_val):
        return response(key_date_error)
    
    filters = {"CompanyCode": str(comp)}
    if supp:
        filters["Supplier"] = str(supp)
    if curr:
        filters["Currency"] = str(curr)
    return response(await client.query(
        client.settings.s4_ap_entity,
        "PayablesAging",
        filters,
        period=date_val,
        currency=curr,
        correlation_id=correlation_id,
        top=top,
    ))


async def s4__get_profit_and_loss(
    company_code: str | None = None,
    fiscal_year: str | None = None,
    fiscal_period: str | None = None,
    ledger: str = "0L",
    currency: str | None = None,
    profit_center: str | None = None,
    correlation_id: str | None = None,
    top: int = 100,
) -> Any:
    """Return an allowlisted S/4HANA profit-and-loss view for the requested period."""
    comp = company_code or "1000"
    today = date.today()
    year = fiscal_year or str(today.year)
    period_val = fiscal_period or f"{today.month:03d}"
    try:
        result = await client.query_profit_and_loss(
            company_code=comp,
            fiscal_year=year,
            fiscal_period=period_val,
            ledger=ledger,
            profit_center=profit_center,
            correlation_id=correlation_id,
            top=top,
        )
    except (TypeError, ValueError):
        result = {
            "status": "error",
            "code": "INVALID_FISCAL_PERIOD",
            "message": "Fiscal year must contain four digits and fiscal period must be between 1 and 16.",
        }
    return response(result)


async def s4__get_budget_variance(
    company_code: str | None = None,
    fiscal_year: str | None = None,
    fiscal_period: str | None = None,
    plan_version: str | None = None,
    currency: str | None = None,
    cost_center: str | None = None,
    correlation_id: str | None = None,
    top: int = 100,
) -> Any:
    """Return allowlisted S/4HANA budget-versus-actual records for the requested period."""
    comp = company_code or "1000"
    today = date.today()
    year = fiscal_year or str(today.year)
    period_val = fiscal_period or f"{today.month:03d}"
    period = f"{year}-{period_val}"
    if len(year) != 4 or not year.isdigit():
        return response({
            "status": "error",
            "code": "INVALID_FISCAL_YEAR",
            "message": "Fiscal year must contain four digits.",
        })
    try:
        period_number = int(period_val)
    except (TypeError, ValueError):
        return response({
            "status": "error",
            "code": "INVALID_FISCAL_PERIOD",
            "message": "Fiscal period must be between 1 and 16.",
        })
    if period_number < 1 or period_number > 16:
        return response({
            "status": "error",
            "code": "INVALID_FISCAL_PERIOD",
            "message": "Fiscal period must be between 1 and 16.",
        })
    filters = {"CompanyCode": str(comp)}
    if year:
        filters["FinMgmtAreaFiscalYear"] = str(year)
    if period_val:
        filters["FinMgmtAreaPeriod"] = str(period_number)
    if plan_version and plan_version != "0":
        filters["BudgetVersion"] = plan_version
    if cost_center:
        filters["CostCenter"] = cost_center
    if currency:
        filters["Currency"] = currency
    return response(await client.query(
        client.settings.s4_budget_entity,
        "BudgetVariance",
        filters,
        period=period,
        currency=currency,
        correlation_id=correlation_id,
        top=top,
        override_base_url=client.settings.s4_budget_api_url or None,
    ))




TOOL_SPECS = [
    ("s4__get_receivables_aging", "Retrieve permission-trimmed accounts-receivable aging from SAP S/4HANA.", s4__get_receivables_aging),
    ("s4__get_payables_aging", "Retrieve permission-trimmed accounts-payable aging from SAP S/4HANA.", s4__get_payables_aging),
    ("s4__get_profit_and_loss", "Retrieve a sourced profit-and-loss view from SAP S/4HANA.", s4__get_profit_and_loss),
    ("s4__get_budget_variance", "Retrieve sourced budget-versus-actual variance records from SAP S/4HANA.", s4__get_budget_variance),
]
