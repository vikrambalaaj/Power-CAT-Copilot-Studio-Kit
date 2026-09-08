"""Comprehensive tests for financial calculation validation and error propagation (Defect 6).

Verifies:
1. Malformed strings, nulls, missing required amounts, NaN, and infinity trigger CONTRACT_MISMATCH.
2. Valid zero and valid empty datasets are handled correctly without generating false errors.
3. Multi-currency input with one invalid partition marks the overall result CONTRACT_MISMATCH.
4. Large decimal values, credits, and negative balances are preserved with exact decimal arithmetic.
5. Full tool response assertions: text summary, adaptive card, structuredContent, and isError agree.
"""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Any
import pytest

from s4hana_mcp.contracts import ReportStatus
from s4hana_mcp.report_calculations import (
    calculate_aging_buckets,
    calculate_budget_consumption,
    calculate_budget_movements,
)
from s4hana_mcp.tools import response


def test_malformed_string_triggers_contract_mismatch():
    """Records with string amounts that cannot parse to decimals must return CONTRACT_MISMATCH."""
    bad_records = [
        {"Customer": "CUST1", "OpenAmount": "not-money", "DaysOverdue": 15, "CompanyCodeCurrency": "AED"}
    ]
    res = calculate_aging_buckets(bad_records, is_receivable=True)
    assert res["status"] == "ERROR"
    assert res["code"] == "CONTRACT_MISMATCH"
    assert res["is_valid"] is False
    assert res["total_open_signed"] is None
    assert res["buckets"]["bucket_1_30"]["amount"] is None


def test_missing_required_amount_triggers_contract_mismatch():
    """Records completely lacking a monetary amount must not default to zero; must trigger CONTRACT_MISMATCH."""
    missing_records = [
        {"Customer": "CUST2", "DaysOverdue": 10, "CompanyCodeCurrency": "AED"}
    ]
    res = calculate_aging_buckets(missing_records, is_receivable=True)
    assert res["status"] == "ERROR"
    assert res["code"] == "CONTRACT_MISMATCH"
    assert res["is_valid"] is False
    assert res["total_open_signed"] is None


def test_nan_and_infinity_trigger_contract_mismatch():
    """Non-finite float values (NaN, Inf) must be rejected and trigger CONTRACT_MISMATCH."""
    nan_records = [
        {"Supplier": "SUPP1", "AmountInDisplayCurrency": float("nan"), "DaysOverdue": 5, "DisplayCurrency": "USD"}
    ]
    res_nan = calculate_aging_buckets(nan_records, is_receivable=False)
    assert res_nan["status"] == "ERROR"
    assert res_nan["code"] == "CONTRACT_MISMATCH"
    assert res_nan["is_valid"] is False

    inf_records = [
        {"Supplier": "SUPP2", "AmountInDisplayCurrency": float("inf"), "DaysOverdue": 5, "DisplayCurrency": "USD"}
    ]
    res_inf = calculate_aging_buckets(inf_records, is_receivable=False)
    assert res_inf["status"] == "ERROR"
    assert res_inf["code"] == "CONTRACT_MISMATCH"
    assert res_inf["is_valid"] is False


def test_valid_zero_is_distinguished_and_accepted():
    """A legitimate zero amount (0.00) must be accepted as valid, not treated as missing/error."""
    zero_records = [
        {"Customer": "CUST_ZERO", "OpenAmount": "0.00", "DaysOverdue": 0, "CompanyCodeCurrency": "AED"}
    ]
    res = calculate_aging_buckets(zero_records, is_receivable=True)
    assert res.get("status") != "ERROR"
    assert res.get("is_valid", True) is True
    assert res["total_open_signed"] == Decimal("0.00")
    assert res["buckets"]["due_today"]["amount"] == Decimal("0.00")
    assert res["buckets"]["due_today"]["count"] == 1


def test_valid_empty_dataset():
    """An empty record list represents a valid empty result, not an invalid source contract."""
    res = calculate_aging_buckets([], is_receivable=True)
    assert res.get("status") != "ERROR"
    assert res.get("is_valid", True) is True
    assert res["total_open_signed"] == Decimal("0.00")
    assert res["bucket_sum"] == Decimal("0.00")


def test_multi_currency_with_one_invalid_partition():
    """In a multi-currency dataset, if one partition has invalid amounts, the entire calculation fails closed."""
    records = [
        {"Customer": "CUST_AED", "OpenAmount": "500.00", "DaysOverdue": 10, "CompanyCodeCurrency": "AED"},
        {"Customer": "CUST_EUR", "OpenAmount": "corrupt_val", "DaysOverdue": 10, "CompanyCodeCurrency": "EUR"},
    ]
    res = calculate_aging_buckets(records, is_receivable=True)
    assert res["is_multi_currency"] is True
    assert res["status"] == "ERROR"
    assert res["code"] == "CONTRACT_MISMATCH"
    assert res["is_valid"] is False
    assert "[EUR]" in res["error"]


def test_large_decimals_and_credits_exact_arithmetic():
    """Large decimal amounts and negative balances (credits) preserve exact decimal precision."""
    records = [
        {"Customer": "BIG_CORP", "OpenAmount": "100000000.55", "DaysOverdue": 45, "CompanyCodeCurrency": "AED"},
        {"Customer": "CREDIT_USER", "OpenAmount": "-25000000.20", "DaysOverdue": -5, "CompanyCodeCurrency": "AED"},
    ]
    res = calculate_aging_buckets(records, is_receivable=True)
    assert res["total_open_signed"] == Decimal("75000000.35")
    assert res["gross_debit"] == Decimal("100000000.55")
    assert res["gross_credit"] == Decimal("-25000000.20")
    assert res["overdue_exposure"] == Decimal("100000000.55")
    assert res["buckets"]["bucket_31_60"]["amount"] == Decimal("100000000.55")
    assert res["buckets"]["not_yet_due"]["amount"] == Decimal("-25000000.20")


def test_full_tool_response_agreement_on_contract_mismatch():
    """Ensure isError, report status, text summary, and Adaptive Card agree on CONTRACT_MISMATCH."""
    bad_data = {
        "status": ReportStatus.CONTRACT_MISMATCH.value,
        "code": "CONTRACT_MISMATCH",
        "message": "Invalid monetary amount in source record: 'NaN'",
        "type": "ReceivablesAging",
        "calculations": {
            "status": "ERROR",
            "code": "CONTRACT_MISMATCH",
            "is_valid": False,
            "total_open_signed": None,
        },
        "data": {"records": [{"Customer": "BAD"}]},
    }
    tool_result = response(bad_data)

    # 1. isError must be True
    assert tool_result.isError is True

    # 2. Text content must identify the error and explain unavailable totals
    text = tool_result.content[0].text
    assert "CONTRACT_MISMATCH" in text
    assert "unavailable due to contract validation failure" in text

    # 3. Structured data must contain error code and CONTRACT_MISMATCH status
    structured = tool_result.structuredContent
    assert structured["status"] == ReportStatus.CONTRACT_MISMATCH.value
    assert structured["code"] == "CONTRACT_MISMATCH"

    # 4. Adaptive Card must display the error rather than a 0.00 balance
    card = structured.get("adaptiveCard", {})
    card_str = str(card)
    assert "CONTRACT_MISMATCH" in card_str
    assert "Validation Error" in card_str
    assert "0.00" not in card_str
