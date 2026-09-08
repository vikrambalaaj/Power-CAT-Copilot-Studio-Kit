"""Typed contracts and models for S/4HANA Finance reports."""
from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any


class ReportStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    EMPTY = "EMPTY"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    ACCESS_DENIED = "ACCESS_DENIED"
    CONTRACT_MISMATCH = "CONTRACT_MISMATCH"
    UNSUPPORTED_FILTER = "UNSUPPORTED_FILTER"
    HISTORICAL_DATA_UNAVAILABLE = "HISTORICAL_DATA_UNAVAILABLE"
    CONFIGURATION_REQUIRED = "CONFIGURATION_REQUIRED"
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
    ERROR = "ERROR"


def safe_decimal(
    value: Any,
    default: Decimal | None = Decimal("0.00"),
    allow_none: bool = False,
    reject_nonfinite: bool = True,
) -> Decimal | None:
    """Parse value to Decimal preserving exact precision without binary float distortion (F04)."""
    if value is None:
        return None if allow_none else (default if default is not None else Decimal("0.00"))
    if isinstance(value, Decimal):
        if reject_nonfinite and not value.is_finite():
            return None if allow_none else default
        return value
    if isinstance(value, float):
        import math
        if reject_nonfinite and (math.isnan(value) or math.isinf(value)):
            return None if allow_none else default
        return Decimal(str(value))
    str_val = str(value).strip()
    if not str_val:
        return None if allow_none else (default if default is not None else Decimal("0.00"))
    try:
        dec = Decimal(str_val)
        if reject_nonfinite and not dec.is_finite():
            return None if allow_none else default
        return dec
    except InvalidOperation:
        return None if allow_none else (default if default is not None else Decimal("0.00"))


def format_decimal(value: Decimal | float | int | str | None, places: int = 2) -> str:
    """Format decimal value into string representation preserving scale."""
    dec = safe_decimal(value)
    if dec is None:
        return "0.00"
    fmt = f"{{:.{places}f}}"
    return fmt.format(dec)


def to_jsonable_data(obj: Any) -> Any:
    """Recursively convert Enums and structures for JSON serialization, preserving exact Decimals (F04)."""
    if isinstance(obj, Decimal):
        if not obj.is_finite():
            raise ValueError(f"Non-finite decimal value cannot be serialized: {obj}")
        return obj
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: to_jsonable_data(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable_data(item) for item in obj]
    return obj


def create_coverage(
    rows_read: int,
    rows_displayed: int,
    page_count: int,
    declared_total: int | None = None,
    completion_state: str = "COMPLETE",
    incomplete_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "rowsRead": rows_read,
        "rowsDisplayed": rows_displayed,
        "pageCount": page_count,
        "declaredTotal": declared_total if declared_total is not None else rows_read,
        "completionState": completion_state,
        "incompleteReason": incomplete_reason or "",
    }


def create_source_record(
    source_id: str,
    business_title: str,
    description: str,
    environment: str = "Production",
    organization_scope: str = "1000",
    report_period: str = "",
    currency: str = "",
    source_updated_time: str | None = None,
    retrieved_at: str = "",
    measurement_date: str | None = None,
    completeness: str = "COMPLETE",
    known_limitations: list[str] | None = None,
    evidence_ref: str = "",
) -> dict[str, Any]:
    return {
        "sourceId": source_id,
        "businessTitle": business_title,
        "description": description,
        "environment": environment,
        "organizationScope": organization_scope,
        "reportPeriod": report_period,
        "currency": currency,
        "sourceUpdatedTime": source_updated_time,  # Keep None if not provided by source (R09)
        "retrievedAt": retrieved_at,
        "measurementDate": measurement_date,
        "completeness": completeness,
        "knownLimitations": known_limitations or [],
        "evidenceRef": evidence_ref or f"SAP-ODATA4-{source_id}-{uuid.uuid4().hex[:8]}",
    }

