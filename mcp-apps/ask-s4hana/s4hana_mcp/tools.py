"""Stable finance tool contracts for the Velora Executive Agent."""
from __future__ import annotations

import json
from typing import Any

from mcp.types import CallToolResult, TextContent

from .client import S4Client
from .adaptive_cards import decorate as decorate_with_card

client = S4Client()


def response(data: dict[str, Any]) -> CallToolResult:
    data = decorate_with_card(data)
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, ensure_ascii=False, default=str))],
        structuredContent=data,
        isError=data.get("status") == "error",
    )


async def s4__get_receivables_aging(
    company_code: str,
    key_date: str,
    customer: str | None = None,
    currency: str | None = None,
    correlation_id: str | None = None,
    top: int = 100,
) -> Any:
    """Return allowlisted S/4HANA receivables-aging records for an executive summary."""
    return response(await client.query(
        client.settings.s4_ar_entity,
        "ReceivablesAging",
        {"CompanyCode": company_code, "KeyDate": key_date, "Customer": customer, "Currency": currency},
        period=key_date,
        currency=currency,
        correlation_id=correlation_id,
        top=top,
    ))


async def s4__get_payables_aging(
    company_code: str,
    key_date: str,
    supplier: str | None = None,
    currency: str | None = None,
    correlation_id: str | None = None,
    top: int = 100,
) -> Any:
    """Return allowlisted S/4HANA payables-aging records for an executive summary."""
    return response(await client.query(
        client.settings.s4_ap_entity,
        "PayablesAging",
        {"CompanyCode": company_code, "KeyDate": key_date, "Supplier": supplier, "Currency": currency},
        period=key_date,
        currency=currency,
        correlation_id=correlation_id,
        top=top,
    ))


async def s4__get_profit_and_loss(
    company_code: str,
    fiscal_year: str,
    fiscal_period: str,
    ledger: str = "0L",
    currency: str | None = None,
    profit_center: str | None = None,
    correlation_id: str | None = None,
    top: int = 100,
) -> Any:
    """Return an allowlisted S/4HANA profit-and-loss view for the requested period."""
    period = f"{fiscal_year}-{fiscal_period}"
    return response(await client.query(
        client.settings.s4_pl_entity,
        "ProfitAndLoss",
        {"CompanyCode": company_code, "FiscalYear": fiscal_year, "FiscalPeriod": fiscal_period, "Ledger": ledger, "Currency": currency, "ProfitCenter": profit_center},
        period=period,
        currency=currency,
        correlation_id=correlation_id,
        top=top,
    ))


async def s4__get_budget_variance(
    company_code: str,
    fiscal_year: str,
    fiscal_period: str,
    plan_version: str,
    currency: str | None = None,
    cost_center: str | None = None,
    correlation_id: str | None = None,
    top: int = 100,
) -> Any:
    """Return allowlisted S/4HANA budget-versus-actual records for the requested period."""
    period = f"{fiscal_year}-{fiscal_period}"
    return response(await client.query(
        client.settings.s4_budget_entity,
        "BudgetVariance",
        {"CompanyCode": company_code, "FiscalYear": fiscal_year, "FiscalPeriod": fiscal_period, "PlanVersion": plan_version, "Currency": currency, "CostCenter": cost_center},
        period=period,
        currency=currency,
        correlation_id=correlation_id,
        top=top,
    ))


TOOL_SPECS = [
    ("s4__get_receivables_aging", "Retrieve permission-trimmed accounts-receivable aging from SAP S/4HANA.", s4__get_receivables_aging),
    ("s4__get_payables_aging", "Retrieve permission-trimmed accounts-payable aging from SAP S/4HANA.", s4__get_payables_aging),
    ("s4__get_profit_and_loss", "Retrieve a sourced profit-and-loss view from SAP S/4HANA.", s4__get_profit_and_loss),
    ("s4__get_budget_variance", "Retrieve sourced budget-versus-actual variance records from SAP S/4HANA.", s4__get_budget_variance),
]
