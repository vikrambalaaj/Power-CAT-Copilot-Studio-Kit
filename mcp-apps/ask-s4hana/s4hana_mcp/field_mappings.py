"""Field mappings and OData filter translations for S/4HANA Finance reports."""
from __future__ import annotations

from typing import Any

# Canonical field maps from provided-field-inventory.csv

AR_FIELDS = {
    "company_code": "CompanyCode",
    "fiscal_year": "FiscalYear",
    "document": "AccountingDocument",
    "customer": "Customer",
    "customer_name": "CustomerName",
    "gl_account": "GLAccount",
    "profit_center": "ProfitCenter",
    "segment": "Segment",
    "currency": "CompanyCodeCurrency",
    "net_due_date": "NetDueDate",
    "posting_date": "PostingDate",
    "document_date": "DocumentDate",
    "open_amount": "OpenAmount",
    "days_overdue": "DaysOverdue",
}

AP_FIELDS = {
    "company_code": "CompanyCode",
    "fiscal_year": "FiscalYear",
    "document": "AccountingDocument",
    "supplier": "Supplier",
    "supplier_name": "SupplierName",
    "gl_account": "GLAccount",
    "profit_center": "ProfitCenter",
    "segment": "Segment",
    "currency": "DisplayCurrency",
    "net_due_date": "NetDueDate",
    "posting_date": "PostingDate",
    "document_date": "DocumentDate",
    "open_amount": "OpenAmount",
    "days_overdue": "DaysOverdue",
}

BUDGET_TRANSFER_FIELDS = {
    "financial_management_area": "FinancialManagementArea",
    "fiscal_year": "FinMgmtAreaFiscalYear",
    "budget_document_year": "BudgetDocumentYear",
    "budget_category": "BudgetCategory",
    "budget_period": "BudgetPeriod",
    "funds_center": "FundsCenter",
    "funds_center_desc": "FundsCenterDescription",
    "commitment_item": "CommitmentItem",
    "commitment_item_desc": "CommitmentItemDescription",
    "currency": "TransactionCurrency",
    "amount": "BudgetAmountInTransactionCrcy",
    "budgeting_process": "BudgetingProcess",
    "budgeting_process_text": "BudgetingProcessText",
    "movement_type": "BudgetMovementType",
    "movement_type_text": "BudgetMovementTypeText",
    "document_type": "BudgetEntryDocumentType",
    "creation_date": "CreationDate",
    "document_date": "BudgetEntryDocumentDate",
}

BUDGET_CONSUMPTION_FIELDS = {
    "financial_management_area": "FinancialManagementArea",
    "fiscal_year": "FinMgmtAreaFiscalYear",
    "period": "FinMgmtAreaPeriod",
    "funds_center": "FundsCenter",
    "funds_center_desc": "FundsCenterDescription",
    "commitment_item": "CommitmentItem",
    "commitment_item_desc": "CommitmentItemDescription",
    "currency": "FinancialManagementAreaCrcy",
    "budget_amount": "BudgetAmountInFMACrcy",
    "commitment_amount": "CmtmtOpenItemAmountInFMACrcy",
    "actual_amount": "ActualAmountInFMACrcy",
    "controlling_amount": "CtrlgItemAmountInFMACrcy",
    "budget_version": "BudgetVersion",
    "budget_value_type": "BudgetValueType",
    "company_code": "CompanyCode",
    "profit_center": "ProfitCenter",
    "segment": "Segment",
}


def build_ar_filters(
    company_code: str | None = None,
    customer: str | None = None,
    customer_name: str | None = None,
    currency: str | None = None,
    profit_center: str | None = None,
    segment: str | None = None,
) -> dict[str, str]:
    filters: dict[str, str] = {}
    if company_code:
        filters["CompanyCode"] = str(company_code).strip()
    if customer:
        filters["Customer"] = str(customer).strip()
    if customer_name:
        filters["CustomerName"] = str(customer_name).strip()
    if currency:
        filters["CompanyCodeCurrency"] = str(currency).strip()
    if profit_center:
        filters["ProfitCenter"] = str(profit_center).strip()
    if segment:
        filters["Segment"] = str(segment).strip()
    return filters


def build_ap_filters(
    company_code: str | None = None,
    supplier: str | None = None,
    supplier_name: str | None = None,
    currency: str | None = None,
    profit_center: str | None = None,
    segment: str | None = None,
) -> dict[str, str]:
    filters: dict[str, str] = {}
    if company_code:
        filters["CompanyCode"] = str(company_code).strip()
    if supplier:
        filters["Supplier"] = str(supplier).strip()
    if supplier_name:
        filters["SupplierName"] = str(supplier_name).strip()
    if currency:
        filters["DisplayCurrency"] = str(currency).strip()
    if profit_center:
        filters["ProfitCenter"] = str(profit_center).strip()
    if segment:
        filters["Segment"] = str(segment).strip()
    return filters


def build_budget_transfer_filters(
    financial_management_area: str | None = None,
    funds_center: str | None = None,
    commitment_item: str | None = None,
    fiscal_year: str | None = None,
    budget_period: str | None = None,
    currency: str | None = None,
    budgeting_process: str | None = None,
    movement_type: str | None = None,
) -> dict[str, str]:
    filters: dict[str, str] = {}
    if financial_management_area:
        filters["FinancialManagementArea"] = str(financial_management_area).strip()
    if funds_center:
        filters["FundsCenter"] = str(funds_center).strip()
    if commitment_item:
        filters["CommitmentItem"] = str(commitment_item).strip()
    if fiscal_year:
        filters["FinMgmtAreaFiscalYear"] = str(fiscal_year).strip()
    if budget_period is not None and str(budget_period).strip() != "":
        filters["BudgetPeriod"] = str(budget_period).strip()
    if currency:
        filters["TransactionCurrency"] = str(currency).strip()
    if budgeting_process:
        filters["BudgetingProcess"] = str(budgeting_process).strip()
    if movement_type:
        filters["BudgetMovementType"] = str(movement_type).strip()
    return filters


def build_budget_consumption_filters(
    financial_management_area: str | None = None,
    funds_center: str | None = None,
    commitment_item: str | None = None,
    fiscal_year: str | None = None,
    period: str | None = None,
    currency: str | None = None,
    budget_version: str | None = None,
    company_code: str | None = None,
) -> dict[str, str]:
    filters: dict[str, str] = {}
    if financial_management_area:
        filters["FinancialManagementArea"] = str(financial_management_area).strip()
    if funds_center:
        filters["FundsCenter"] = str(funds_center).strip()
    if commitment_item:
        filters["CommitmentItem"] = str(commitment_item).strip()
    if fiscal_year:
        filters["FinMgmtAreaFiscalYear"] = str(fiscal_year).strip()
    if period:
        filters["FinMgmtAreaPeriod"] = str(period).strip()
    if currency:
        filters["FinancialManagementAreaCrcy"] = str(currency).strip()
    if budget_version is not None:
        filters["BudgetVersion"] = str(budget_version).strip()
    if company_code:
        filters["CompanyCode"] = str(company_code).strip()
    return filters

