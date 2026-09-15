"""Stable finance tool contracts for the Velora Executive Agent."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from mcp.types import CallToolResult, TextContent

from .client import S4Client
from .contracts import ReportStatus, format_decimal, safe_decimal, to_jsonable_data
from .field_mappings import (
    build_ap_filters,
    build_ar_filters,
    build_budget_consumption_filters,
    build_budget_transfer_filters,
)
from .report_calculations import (
    _get_record_currency,
    calculate_aging_buckets,
    calculate_budget_consumption,
    calculate_budget_movements,
)
from .adaptive_cards import decorate as decorate_with_card

client = S4Client()


def response(data: dict[str, Any]) -> CallToolResult:
    decorated = decorate_with_card(data)
    text = build_text_summary(decorated)
    # Serialize for transport (R01): recursively convert Decimal instances to JSON-compatible types
    jsonable = to_jsonable_data(decorated)
    status_str = str(decorated.get("status", "")).upper()
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structuredContent=jsonable,
        isError=status_str in {
            ReportStatus.ERROR.value,
            "ERROR",
            ReportStatus.CONTRACT_MISMATCH.value,
            "CONTRACT_MISMATCH",
            ReportStatus.UNSUPPORTED_FILTER.value,
            ReportStatus.HISTORICAL_DATA_UNAVAILABLE.value,
        },
    )


def live_key_date_error(key_date_value: str | None) -> dict[str, Any] | None:
    if not key_date_value:
        return None
    try:
        requested = date.fromisoformat(key_date_value)
    except ValueError:
        return {
            "status": "error",
            "code": "INVALID_KEY_DATE",
            "message": "Key date must use ISO format YYYY-MM-DD.",
        }
    try:
        dubai_tz = ZoneInfo("Asia/Dubai")
    except Exception:
        dubai_tz = timezone.utc
    today = datetime.now(dubai_tz).date()

    if requested < today:
        return {
            "status": "error",
            "code": ReportStatus.HISTORICAL_DATA_UNAVAILABLE.value,
            "message": f"Historical key date {key_date_value} is not supported. Live S/4HANA open-item aging reflects current receivables as of {today}.",
        }
    if requested > today:
        return {
            "status": "error",
            "code": ReportStatus.UNSUPPORTED_FILTER.value,
            "message": f"Future key date {key_date_value} is not supported. Live S/4HANA open-item aging reflects current receivables as of {today}.",
        }
    return None



def build_text_summary(data: dict[str, Any]) -> str:
    status_str = str(data.get("status", "")).upper()
    if status_str in {ReportStatus.ERROR.value, "ERROR", ReportStatus.CONTRACT_MISMATCH.value, "CONTRACT_MISMATCH"}:
        msg = data.get("message") or "Unable to process records."
        code = data.get("code") or status_str
        return f"### SAP S/4HANA Error ({code})\n• {msg}\n• Aggregate totals and aging bucket balances are unavailable due to contract validation failure."

    result_type = data.get("type", "")
    records = data.get("data", {}).get("records", [])
    total_count = data.get("data", {}).get("total", len(records))
    filters = data.get("query", {}).get("filters", {})
    comp_code = filters.get("CompanyCode") or filters.get("FinancialManagementArea", "1000")
    coverage = data.get("coverage", {})
    cov_str = f"{coverage.get('rowsRead', len(records))} rows retrieved (declared: {total_count})"

    def _resolve_display_currency(calc_dict: dict[str, Any], query_dict: dict[str, Any], recs: list[dict[str, Any]]) -> str:
        calc_curr = calc_dict.get("currency")
        if calc_curr and calc_curr != "MULTI":
            return calc_curr
        query_curr = query_dict.get("currency")
        if query_curr:
            return query_curr
        for r in recs:
            c = _get_record_currency(r, entity_type=result_type)
            if c:
                return c
        return "AED"

    if result_type == "ReceivablesAging":
        calc = data.get("calculations") or calculate_aging_buckets(records, is_receivable=True)
        if calc.get("is_multi_currency"):
            curr_lines = [f"  • {c}: Net {format_decimal(d.get('total_open_signed'))}" for c, d in calc.get("by_currency", {}).items()]
            multi_summary = "\n".join(curr_lines) or "  • None reported"
            return (
                f"### SAP S/4HANA Accounts Receivable Aging Summary (Multi-Currency)\n"
                f"• **Company Code**: {comp_code}\n"
                f"• **Coverage**: {cov_str}\n\n"
                f"**Balances by Currency**:\n{multi_summary}\n\n"
                f"*{calc.get('warning', 'Partitioned by currency.')}*"
            )

        currency = _resolve_display_currency(calc, data.get("query", {}), records)
        total_open = format_decimal(calc.get("total_open_signed", Decimal("0.00")))
        gross_debit = format_decimal(calc.get("gross_debit", Decimal("0.00")))
        gross_credit = format_decimal(calc.get("gross_credit", Decimal("0.00")))
        overdue_exposure = format_decimal(calc.get("overdue_exposure", Decimal("0.00")))
        buckets = calc.get("buckets", {})

        bucket_lines = []
        for b_key in ["not_yet_due", "due_today", "bucket_1_30", "bucket_31_60", "bucket_61_90", "bucket_91_180", "bucket_over_180", "unaged"]:
            b = buckets.get(b_key, {"label": b_key, "amount": Decimal("0.00"), "count": 0})
            bucket_lines.append(f"  • {b['label']}: {currency} {format_decimal(b['amount'])} ({b['count']} items)")

        top_cust_lines = []
        for p in calc.get("top_parties", [])[:5]:
            p_name = p.get("name") or p.get("id") or "Unknown"
            top_cust_lines.append(f"  • {p_name} ({p.get('id', '')}): {currency} {format_decimal(p['amount'])}")
        top_cust_str = "\n".join(top_cust_lines) or "  • None reported"

        return (
            f"### SAP S/4HANA Accounts Receivable Aging Summary\n"
            f"• **Company Code**: {comp_code}\n"
            f"• **Net Open Balance**: {currency} {total_open}\n"
            f"• **Gross Receivables (Debit)**: {currency} {gross_debit}\n"
            f"• **Credits / Prepayments**: {currency} {gross_credit}\n"
            f"• **Overdue Exposure (>0 days)**: {currency} {overdue_exposure}\n"
            f"• **Coverage**: {cov_str}\n\n"
            f"**Aging Buckets**:\n" + "\n".join(bucket_lines) + "\n\n"
            f"**Top Customers by Balance**:\n{top_cust_str}\n\n"
            f"*Source: Finance's customer open-invoice report in SAP. Credits treated according to Finance policy.*"
        )

    if result_type == "PayablesAging":
        calc = data.get("calculations") or calculate_aging_buckets(records, is_receivable=False)
        if calc.get("is_multi_currency"):
            curr_lines = [f"  • {c}: Open {format_decimal(d.get('total_open_signed'))}" for c, d in calc.get("by_currency", {}).items()]
            multi_summary = "\n".join(curr_lines) or "  • None reported"
            return (
                f"### SAP S/4HANA Accounts Payable Aging Summary (Multi-Currency)\n"
                f"• **Company Code**: {comp_code}\n"
                f"• **Coverage**: {cov_str}\n\n"
                f"**Balances by Currency**:\n{multi_summary}\n\n"
                f"*{calc.get('warning', 'Partitioned by currency.')}*"
            )

        currency = _resolve_display_currency(calc, data.get("query", {}), records)
        total_open = format_decimal(calc.get("total_open_signed", Decimal("0.00")))
        overdue_exposure = format_decimal(calc.get("overdue_exposure", Decimal("0.00")))
        buckets = calc.get("buckets", {})

        bucket_lines = []
        for b_key in ["not_yet_due", "due_today", "bucket_1_30", "bucket_31_60", "bucket_61_90", "bucket_91_180", "bucket_over_180", "unaged"]:
            b = buckets.get(b_key, {"label": b_key, "amount": Decimal("0.00"), "count": 0})
            bucket_lines.append(f"  • {b['label']}: {currency} {format_decimal(b['amount'])} ({b['count']} items)")

        top_sup_lines = []
        for p in calc.get("top_parties", [])[:5]:
            p_name = p.get("name") or p.get("id") or "Unknown"
            top_sup_lines.append(f"  • {p_name} ({p.get('id', '')}): {currency} {format_decimal(p['amount'])}")
        top_sup_str = "\n".join(top_sup_lines) or "  • None reported"

        return (
            f"### SAP S/4HANA Accounts Payable Aging Summary\n"
            f"• **Company Code**: {comp_code}\n"
            f"• **Total Open Balance**: {currency} {total_open}\n"
            f"• **Overdue Obligations**: {currency} {overdue_exposure}\n"
            f"• **Coverage**: {cov_str}\n\n"
            f"**Aging Buckets**:\n" + "\n".join(bucket_lines) + "\n\n"
            f"**Top Suppliers by Open Balance**:\n{top_sup_str}\n\n"
            f"*Source: Finance's unpaid-supplier report in SAP. This is an informational report, not payment approval.*"
        )

    if result_type == "BudgetTransfer":
        calc = data.get("calculations") or calculate_budget_movements(records)
        if calc.get("is_multi_currency"):
            curr_lines = []
            for c, sub_calc in calc.get("by_currency", {}).items():
                tot_c = format_decimal(sub_calc.get("total_movement_amount", Decimal("0.00")))
                curr_lines.append(f"  • **Currency {c}**: Total Movements = {c} {tot_c}")
                for cat_k, cat in sub_calc.get("categories", {}).items():
                    if isinstance(cat, dict) and cat.get("count", 0) > 0:
                        curr_lines.append(f"      - {cat['label']}: {c} {format_decimal(cat.get('amount', Decimal('0.00')))} ({cat['count']} items)")
            multi_summary = "\n".join(curr_lines) or "  • None reported"
            return (
                f"### SAP S/4HANA Budget Movements Register (Multi-Currency)\n"
                f"• **Funds Management Area**: {comp_code}\n"
                f"• **Coverage**: {cov_str}\n\n"
                f"**Movements by Currency**:\n{multi_summary}\n\n"
                f"*Source: Finance's budget-entry and movement register. Partitioned by transaction currency.*"
            )

        currency = _resolve_display_currency(calc, data.get("query", {}), records)
        tot_amt = format_decimal(calc.get("total_movement_amount", Decimal("0.00")))
        cat_lines = []
        for cat_k, cat in calc.get("categories", {}).items():
            if isinstance(cat, dict) and cat.get("count", 0) > 0:
                cat_lines.append(f"  • {cat['label']}: {currency} {format_decimal(cat.get('amount', Decimal('0.00')))} ({cat['count']} items)")
        cat_str = "\n".join(cat_lines) or "  • No movements recorded"

        doc_lines = []
        for d in calc.get("documents", [])[:5]:
            doc_lines.append(f"  • Doc {d['document']} ({d['category']}): {currency} {format_decimal(d['amount'])} [Funds Center: {d['funds_center']}]")
        doc_str = "\n".join(doc_lines) or "  • None reported"

        return (
            f"### SAP S/4HANA Budget Movements Register\n"
            f"• **Funds Management Area**: {comp_code}\n"
            f"• **Total Movement Amount**: {currency} {tot_amt}\n"
            f"• **Coverage**: {cov_str}\n\n"
            f"**Movement Breakdown**:\n{cat_str}\n\n"
            f"**Recent Documents**:\n{doc_str}\n\n"
            f"*Source: Finance's budget-entry and movement register. Original budget entries remain distinct from transfers.*"
        )

    if result_type == "BudgetConsumption":
        calc = data.get("calculations") or calculate_budget_consumption(records, mapping_approved=False)
        if calc.get("is_multi_currency"):
            curr_lines = []
            for c, sub_calc in calc.get("by_currency", {}).items():
                b_val = format_decimal(sub_calc.get("raw_budget", Decimal("0.00")))
                a_val = format_decimal(sub_calc.get("raw_actuals", Decimal("0.00")))
                c_val = format_decimal(sub_calc.get("raw_commitments", Decimal("0.00")))
                curr_lines.append(f"  • **Currency {c}**: Budget={c} {b_val}, Actuals={c} {a_val}, Commitments={c} {c_val}")
            multi_summary = "\n".join(curr_lines) or "  • None reported"
            return (
                f"### SAP S/4HANA Budget & Expenditure Report (Multi-Currency)\n"
                f"• **Funds Management Area**: {comp_code}\n"
                f"• **Coverage**: {cov_str}\n\n"
                f"**Breakdown by Currency**:\n{multi_summary}\n\n"
                f"*Source: S/4HANA Funds Management. Partitioned by currency; unified aggregation disallowed without approved exchange rates.*"
            )

        currency = _resolve_display_currency(calc, data.get("query", {}), records)
        raw_b = format_decimal(calc.get("raw_budget", Decimal("0.00")))
        raw_a = format_decimal(calc.get("raw_actuals", Decimal("0.00")))
        raw_c = format_decimal(calc.get("raw_commitments", Decimal("0.00")))
        raw_ctrl = format_decimal(calc.get("raw_controlling", Decimal("0.00")))

        fc_lines = []
        for fc in calc.get("funds_centers", [])[:5]:
            fc_lines.append(f"  • {fc['description']} ({fc['funds_center']}): Budget={currency} {format_decimal(fc['budget'])}, Actual={currency} {format_decimal(fc['actuals'])}")
        fc_str = "\n".join(fc_lines) or "  • None reported"

        return (
            f"### SAP S/4HANA Budget & Expenditure Report\n"
            f"• **Funds Management Area**: {comp_code}\n"
            f"• **Budget Amount (FMA Crcy)**: {currency} {raw_b}\n"
            f"• **Actual Expenditure (FMA Crcy)**: {currency} {raw_a}\n"
            f"• **Open Commitments (FMA Crcy)**: {currency} {raw_c}\n"
            f"• **Controlling Items**: {currency} {raw_ctrl}\n"
            f"• **Status**: Budget interpretation awaiting Finance mapping approval\n"
            f"• **Coverage**: {cov_str}\n\n"
            f"**Funds Center Breakdown**:\n{fc_str}\n\n"
            f"*Source: Finance's budget and expenditure report. Derived utilization metrics require confirmed business mapping.*"
        )

    return json.dumps(data, ensure_ascii=False, default=str)


async def s4__get_receivables_aging(
    company_code: str | None = None,
    key_date: str | None = None,
    customer: str | None = None,
    customer_name: str | None = None,
    currency: str | None = None,
    profit_center: str | None = None,
    segment: str | None = None,
    correlation_id: str | None = None,
    top: int = 100,
) -> Any:
    """Retrieve accounts-receivable aging from SAP S/4HANA OData v4 service."""
    comp = company_code or "1000"
    if key_date_error := live_key_date_error(key_date):
        return response(key_date_error)

    filters = build_ar_filters(
        company_code=comp,
        customer=customer,
        customer_name=customer_name,
        currency=currency,
        profit_center=profit_center,
        segment=segment,
    )
    result = await client.query(
        client.settings.s4_ar_entity,
        "ReceivablesAging",
        filters,
        period=key_date,
        currency=currency,
        correlation_id=correlation_id,
        top=top,
    )
    if result.get("status") != "error":
        calc = calculate_aging_buckets(
            result.get("data", {}).get("records", []),
            is_receivable=True,
            requested_currency=currency,
        )
        result["calculations"] = calc
        if calc.get("status") == "ERROR" or not calc.get("is_valid", True):
            result["status"] = ReportStatus.CONTRACT_MISMATCH.value
            result["code"] = calc.get("code") or "CONTRACT_MISMATCH"
            result["message"] = calc.get("error") or "Contract validation failed on AR aging records."
    return response(result)


async def s4__get_payables_aging(
    company_code: str | None = None,
    key_date: str | None = None,
    supplier: str | None = None,
    supplier_name: str | None = None,
    currency: str | None = None,
    profit_center: str | None = None,
    segment: str | None = None,
    correlation_id: str | None = None,
    top: int = 100,
) -> Any:
    """Retrieve accounts-payable aging from SAP S/4HANA OData v4 service."""
    comp = company_code or "1000"
    if key_date_error := live_key_date_error(key_date):
        return response(key_date_error)

    filters = build_ap_filters(
        company_code=comp,
        supplier=supplier,
        supplier_name=supplier_name,
        currency=currency,
        profit_center=profit_center,
        segment=segment,
    )
    result = await client.query(
        client.settings.s4_ap_entity,
        "PayablesAging",
        filters,
        period=key_date,
        currency=currency,
        correlation_id=correlation_id,
        top=top,
    )
    if result.get("status") != "error":
        calc = calculate_aging_buckets(
            result.get("data", {}).get("records", []),
            is_receivable=False,
            requested_currency=currency,
        )
        result["calculations"] = calc
        if calc.get("status") == "ERROR" or not calc.get("is_valid", True):
            result["status"] = ReportStatus.CONTRACT_MISMATCH.value
            result["code"] = calc.get("code") or "CONTRACT_MISMATCH"
            result["message"] = calc.get("error") or "Contract validation failed on AP aging records."
    return response(result)


async def s4__get_budget_transfers(**kwargs: Any) -> Any:
    """Legacy endpoint: Budget Transfer report is excluded from S/4HANA service scope."""
    return response({
        "status": ReportStatus.ERROR.value,
        "code": ReportStatus.UNSUPPORTED_OPERATION.value,
        "message": "Budget Transfer report is excluded from S/4HANA service scope. Only Budget Consumption Summary (BudgetConsumSummary) is supported.",
        "type": "BudgetTransfer",
    })



async def s4__get_budget_consumption(
    financial_management_area: str | None = None,
    funds_center: str | None = None,
    commitment_item: str | None = None,
    fiscal_year: str | None = None,
    period: str | None = None,
    currency: str | None = None,
    budget_version: str | None = None,
    company_code: str | None = None,
    correlation_id: str | None = None,
    top: int = 100,
) -> Any:
    """Retrieve budget, commitment, and actual expenditure records from SAP S/4HANA."""
    entity = getattr(client.settings, "s4_budget_consumption_entity", "")
    is_summary = entity == "BudgetConsumSummary"
    fma = financial_management_area if financial_management_area is not None else (None if is_summary else "1000")
    filters = build_budget_consumption_filters(
        financial_management_area=fma,
        funds_center=funds_center,
        commitment_item=commitment_item,
        fiscal_year=fiscal_year,
        period=period,
        currency=currency,
        budget_version=budget_version,
        company_code=company_code,
    )
    result = await client.query(
        client.settings.s4_budget_consumption_entity,
        "BudgetConsumption",
        filters,
        period=fiscal_year,
        currency=currency,
        correlation_id=correlation_id,
        top=top,
    )
    if result.get("status") != "error":
        calc = calculate_budget_consumption(
            result.get("data", {}).get("records", []),
            mapping_approved=False,
            requested_currency=currency,
        )
        result["calculations"] = calc
        if calc.get("status") == "ERROR" or not calc.get("is_valid", True):
            result["status"] = ReportStatus.CONTRACT_MISMATCH.value
            result["code"] = calc.get("code") or "CONTRACT_MISMATCH"
            result["message"] = calc.get("error") or "Contract validation failed on budget consumption records."
        # R03: If mapping is not approved, communicate CONFIGURATION_REQUIRED
        elif not calc.get("mapping_approved"):
            result["status"] = ReportStatus.CONFIGURATION_REQUIRED.value
            if "quality" in result:
                result["quality"]["confidence"] = "Low (Configuration Required)"
                result["quality"]["confidenceReason"] = calc.get(
                    "configuration_notice",
                    "Finance-approved value-type mapping and additive budget grain are required.",
                )
                if "warnings" in result["quality"]:
                    result["quality"]["warnings"].append(
                        calc.get("configuration_notice", "Configuration required for budget aggregation.")
                    )
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
    """Compatibility adapter routing legacy budget requests to budget consumption."""
    # R06: Reject unsupported cost_center filter instead of silently discarding
    if cost_center:
        return response({
            "status": "error",
            "code": ReportStatus.UNSUPPORTED_FILTER.value,
            "message": f"Filtering by cost_center ('{cost_center}') is not supported by Budget Consumption; use funds_center instead.",
        })

    # R06: Validate organization mapping instead of assuming arbitrary company code equals FMA
    comp = company_code or "1000"
    if company_code and company_code != "1000":
        return response({
            "status": "error",
            "code": ReportStatus.UNSUPPORTED_FILTER.value,
            "message": f"Company code '{company_code}' has no approved Financial Management Area mapping.",
        })

    return await s4__get_budget_consumption(
        financial_management_area=comp,
        fiscal_year=fiscal_year,
        period=fiscal_period,
        budget_version=plan_version,
        currency=currency,
        company_code=comp,
        correlation_id=correlation_id,
        top=top,
    )



async def s4__get_profit_and_loss(**kwargs: Any) -> Any:
    """Legacy endpoint: P&L is removed from S/4HANA service scope. Returns truthful unsupported response."""
    return response({
        "status": ReportStatus.ERROR.value,
        "code": ReportStatus.UNSUPPORTED_OPERATION.value,
        "message": "P&L report is excluded from S/4HANA service scope.",
        "type": "ProfitAndLoss",
    })


# Master data tools (isolated from 4 main financial reports)
async def s4__get_customer_master(
    customer: str | None = None,
    customer_name: str | None = None,
    city: str | None = None,
    country: str | None = None,
    correlation_id: str | None = None,
    top: int = 50,
) -> Any:
    filters: dict[str, str | None] = {}
    if customer:
        filters["Customer"] = str(customer)
    if customer_name:
        filters["CustomerName"] = str(customer_name)
    if city:
        filters["City"] = str(city)
    if country:
        filters["Country"] = str(country)
    return response(await client.query(
        client.settings.s4_customer_entity,
        "CustomerMaster",
        filters,
        correlation_id=correlation_id,
        top=top,
        override_base_url=client.settings.s4_customer_api_url or None,
    ))


async def s4__get_cost_center_master(
    company_code: str | None = None,
    cost_center: str | None = None,
    description: str | None = None,
    correlation_id: str | None = None,
    top: int = 50,
) -> Any:
    comp = company_code or "1000"
    filters: dict[str, str | None] = {"CompanyCode": str(comp)}
    if cost_center:
        filters["CostCenter"] = str(cost_center)
    if description:
        filters["CostCenterDescription"] = str(description)
    return response(await client.query(
        client.settings.s4_costcenter_entity,
        "CostCenterMaster",
        filters,
        correlation_id=correlation_id,
        top=top,
        override_base_url=client.settings.s4_costcenter_api_url or None,
    ))


async def s4__get_profit_center_master(
    company_code: str | None = None,
    profit_center: str | None = None,
    name: str | None = None,
    correlation_id: str | None = None,
    top: int = 50,
) -> Any:
    comp = company_code or "1000"
    filters: dict[str, str | None] = {"CompanyCode": str(comp)}
    if profit_center:
        filters["ProfitCenter"] = str(profit_center)
    if name:
        filters["ProfitCenterLongName"] = str(name)
    return response(await client.query(
        client.settings.s4_profitcenter_entity,
        "ProfitCenterMaster",
        filters,
        correlation_id=correlation_id,
        top=top,
        override_base_url=client.settings.s4_profitcenter_api_url or None,
    ))


# Authoritative tool specifications: exactly 3 primary finance reports + master data tools
# (s4__get_profit_and_loss and s4__get_budget_transfers are explicitly excluded from discovery)
TOOL_SPECS = [
    ("s4__get_receivables_aging", "Retrieve permission-trimmed accounts-receivable aging from SAP S/4HANA.", s4__get_receivables_aging),
    ("s4__get_payables_aging", "Retrieve permission-trimmed accounts-payable aging from SAP S/4HANA.", s4__get_payables_aging),
    ("s4__get_budget_consumption", "Retrieve budget consumption summary records from SAP S/4HANA.", s4__get_budget_consumption),
    ("s4__get_customer_master", "Retrieve customer master records from SAP S/4HANA.", s4__get_customer_master),
    ("s4__get_cost_center_master", "Retrieve cost center master records from SAP S/4HANA.", s4__get_cost_center_master),
    ("s4__get_profit_center_master", "Retrieve profit center master records from SAP S/4HANA.", s4__get_profit_center_master),
]
