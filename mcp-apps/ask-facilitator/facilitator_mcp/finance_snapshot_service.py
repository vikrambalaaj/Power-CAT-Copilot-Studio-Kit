"""Finance Snapshot Service for Velora Executive Platform (W08, R04, R05).

Bridges SAP S/4HANA financial sources to structured, verified KPI snapshots.
- Maps RECEIVABLES strictly to overdue >90 days aging buckets (bucket_91_180 + bucket_over_180).
- Maps PAYABLES to overdue liabilities.
- Enforces unapproved mapping protection for BUDGET_CONSUMPTION.
- Persists verified snapshots into durable Business Repository.
- Dispatches snapshots to internal EVALUATE_VERIFIED_KPI_SNAPSHOT operation with signed workload identity.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

log = logging.getLogger("facilitator_mcp.finance_snapshot_service")


async def generate_finance_snapshot(
    kpi_code: str,
    company_code: str = "1000",
    key_date: Optional[str] = None,
    currency: str = "AED",
    correlation_id: Optional[str] = None,
    tenant_id: str = "velora-aviation",
    db_path: Optional[str] = None,
    s4_tool_override: Optional[Any] = None,
) -> Dict[str, Any]:
    """Generate verified KPI snapshot from authoritative SAP S/4HANA financial data."""
    corr_id = correlation_id or f"corr-snap-{int(time.time() * 1000)}"
    kpi_upper = kpi_code.upper()
    now_iso = datetime.now(timezone.utc).isoformat()
    period_str = key_date or datetime.now(timezone.utc).strftime("%Y-%m")

    # 1. Unapproved mapping guard for Budget Consumption (W08 requirement 2 / Acceptance T08)
    if kpi_upper in ("BUDGET", "BUDGET_CONSUMPTION"):
        log.info(f"finance_snapshot_unapproved_budget_mapping_blocked kpi={kpi_code}")
        snap_dict = {
            "snapshot_id": f"SNAP-BUDGET-{int(time.time() * 1000)}",
            "kpi_code": "BUDGET_CONSUMPTION",
            "organization_scope": company_code,
            "period": period_str,
            "value": Decimal("0.00"),
            "unit": "percent",
            "currency": "",
            "source_updated_time": now_iso,
            "retrieved_at": now_iso,
            "completeness": "PARTIAL",
            "unapproved_mapping": True,
            "evidence_ref": "UNAPPROVED_MAPPING",
            "input_hash": hashlib.sha256(b"UNAPPROVED_MAPPING_BUDGET").hexdigest(),
            "limitations": [
                "Chart of accounts mapping for budget recommendations is unapproved by Finance and CEO Office."
            ],
            "tenant_id": tenant_id,
        }
        _persist_snapshot_if_possible(snap_dict, tenant_id=tenant_id, db_path=db_path)
        return snap_dict

    # 2. Invoke SAP S/4HANA tool
    s4_result = None
    if s4_tool_override is not None:
        try:
            if callable(s4_tool_override):
                res = s4_tool_override(company_code=company_code, key_date=key_date, currency=currency)
                if hasattr(res, "__await__"):
                    import asyncio
                    s4_result = await res
                else:
                    s4_result = res
        except Exception as ex:
            log.error(f"s4_tool_override_failed: {ex}")
            s4_result = {"status": "error", "error": str(ex)}
    else:
        try:
            from s4hana_mcp.tools import s4__get_receivables_aging, s4__get_payables_aging
            if kpi_upper == "RECEIVABLES":
                s4_result = await s4__get_receivables_aging(
                    company_code=company_code,
                    key_date=key_date,
                    currency=currency,
                    correlation_id=corr_id,
                )
            elif kpi_upper == "PAYABLES":
                s4_result = await s4__get_payables_aging(
                    company_code=company_code,
                    key_date=key_date,
                    currency=currency,
                    correlation_id=corr_id,
                )
            else:
                return {
                    "status": "ERROR",
                    "error": f"Unsupported KPI code for finance snapshot adapter: {kpi_code}",
                    "completeness": "EMPTY",
                }
        except Exception as ex:
            log.error(f"s4_adapter_call_failed: {ex}")
            s4_result = {"status": "error", "error": str(ex)}

    # 3. Unpack CallToolResult or dictionary
    data_payload: Dict[str, Any] = {}
    is_error = False
    if hasattr(s4_result, "structuredContent") and isinstance(s4_result.structuredContent, dict):
        data_payload = s4_result.structuredContent
        is_error = getattr(s4_result, "isError", False)
    elif isinstance(s4_result, dict):
        data_payload = s4_result
        is_error = data_payload.get("status") in ("error", "ERROR", "CONTRACT_MISMATCH")

    # 4. Handle S/4HANA Outage or Error
    if is_error or data_payload.get("status") in ("error", "ERROR", "CONTRACT_MISMATCH"):
        err_msg = data_payload.get("message") or data_payload.get("error") or "SAP S/4HANA service outage or contract failure."
        log.warning(f"finance_snapshot_s4_outage kpi={kpi_code} error={err_msg}")
        snap_dict = {
            "snapshot_id": f"SNAP-{kpi_upper}-OUTAGE-{int(time.time() * 1000)}",
            "kpi_code": kpi_upper,
            "organization_scope": company_code,
            "period": period_str,
            "value": Decimal("0.00"),
            "unit": "currency",
            "currency": currency,
            "source_updated_time": None,
            "retrieved_at": now_iso,
            "completeness": "EMPTY",
            "evidence_ref": f"S4_OUTAGE_{corr_id}",
            "input_hash": hashlib.sha256(f"OUTAGE:{err_msg}".encode("utf-8")).hexdigest(),
            "limitations": [err_msg],
            "tenant_id": tenant_id,
        }
        _persist_snapshot_if_possible(snap_dict, tenant_id=tenant_id, db_path=db_path)
        return snap_dict

    # 5. Extract and independently calculate KPI value
    calcs = data_payload.get("calculations") or {}
    coverage = data_payload.get("coverage") or {}
    source_rec = data_payload.get("sourceRecord") or {}
    records = data_payload.get("data", {}).get("records", [])

    is_complete = coverage.get("completionState") == "COMPLETE"
    completeness_str = "COMPLETE" if is_complete else "PARTIAL"
    limitations: List[str] = []
    if not is_complete:
        limitations.append(coverage.get("incompleteReason") or "Incomplete dataset from SAP S/4HANA")

    measured_val = Decimal("0.00")

    if kpi_upper == "RECEIVABLES":
        # CRITICAL W08 REQUIREMENT 2 & ACCEPTANCE T08:
        # AR overdue beyond 90 days isolates strictly overdue aging buckets:
        # bucket_91_180 + bucket_over_180.
        # NEVER feed total receivables (total_open_signed or gross_debit) merely because KPI is RECEIVABLES!
        buckets = calcs.get("buckets") or {}
        b_91_180 = buckets.get("bucket_91_180", {})
        b_over_180 = buckets.get("bucket_over_180", {})

        amt_91 = Decimal(str(b_91_180.get("amount") or "0.00"))
        amt_over = Decimal(str(b_over_180.get("amount") or "0.00"))
        measured_val = amt_91 + amt_over
        log.info(f"ar_overdue_90d_calculated amount_91_180={amt_91} amount_over_180={amt_over} total={measured_val}")

    elif kpi_upper == "PAYABLES":
        # Payables: urgent liabilities due / overdue exposure
        overdue_exposure = calcs.get("overdue_exposure")
        if overdue_exposure is not None:
            measured_val = Decimal(str(overdue_exposure))
        else:
            buckets = calcs.get("buckets") or {}
            due_today = Decimal(str(buckets.get("due_today", {}).get("amount") or "0.00"))
            b_1_30 = Decimal(str(buckets.get("bucket_1_30", {}).get("amount") or "0.00"))
            measured_val = due_today + b_1_30

    # Currency validation
    detected_currency = calcs.get("currency") or currency
    if detected_currency.upper() != currency.upper():
        limitations.append(f"Currency mismatch: expected {currency}, received {detected_currency}")
        completeness_str = "PARTIAL"

    # Deterministic SHA-256 hash of underlying source data
    canonical_bytes = json.dumps(
        {
            "kpi": kpi_upper,
            "scope": company_code,
            "currency": detected_currency,
            "period": period_str,
            "records_count": len(records),
            "measured_val": str(measured_val),
            "calcs": calcs,
        },
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    input_hash = hashlib.sha256(canonical_bytes).hexdigest()

    evidence_ref = source_rec.get("sourceId") or f"S4HANA-{kpi_upper}-{company_code}-{period_str}"
    retrieved_at = source_rec.get("retrievedAt") or now_iso

    snap_dict = {
        "snapshot_id": f"SNAP-{kpi_upper}-{int(time.time() * 1000)}",
        "kpi_code": kpi_upper,
        "organization_scope": company_code,
        "period": period_str,
        "value": measured_val,
        "unit": "currency",
        "currency": detected_currency,
        "source_updated_time": retrieved_at,
        "retrieved_at": retrieved_at,
        "completeness": completeness_str,
        "evidence_ref": evidence_ref,
        "input_hash": input_hash,
        "limitations": limitations,
        "tenant_id": tenant_id,
    }

    _persist_snapshot_if_possible(snap_dict, tenant_id=tenant_id, db_path=db_path)
    return snap_dict


async def evaluate_finance_snapshot(
    kpi_code: Optional[str] = None,
    snapshot: Optional[Dict[str, Any]] = None,
    company_code: str = "1000",
    key_date: Optional[str] = None,
    currency: str = "AED",
    correlation_id: Optional[str] = None,
    tenant_id: str = "velora-aviation",
    recipient: Optional[str] = None,
    outbox_dir: Optional[str] = None,
    db_path: Optional[str] = None,
    s4_tool_override: Optional[Any] = None,
) -> Dict[str, Any]:
    """Generate and evaluate verified finance snapshot through Productivity recommendation engine."""
    corr_id = correlation_id or f"corr-eval-fin-{int(time.time() * 1000)}"

    # 1. Acquire snapshot
    snap = snapshot
    if snap is None:
        if not kpi_code:
            return {
                "status": "ERROR",
                "message": "Either 'snapshot' or 'kpi_code' must be provided.",
                "correlationId": corr_id,
            }
        snap = await generate_finance_snapshot(
            kpi_code=kpi_code,
            company_code=company_code,
            key_date=key_date,
            currency=currency,
            correlation_id=corr_id,
            tenant_id=tenant_id,
            db_path=db_path,
            s4_tool_override=s4_tool_override,
        )

    # 2. Dispatch to Productivity internal operation
    try:
        from productivity_mcp.tools_recommendations import evaluate_verified_kpi_snapshot
        eval_res = await evaluate_verified_kpi_snapshot(
            snapshot=snap,
            caller_role="WORKLOAD_AUTHORIZED",
            rootCorrelationId=corr_id,
            tenantId=tenant_id,
            engine_outbox_dir=outbox_dir,
        )
        return eval_res
    except Exception as ex:
        log.error(f"evaluate_verified_kpi_snapshot_failed: {ex}", exc_info=True)
        return {
            "status": "ERROR",
            "message": f"Failed to evaluate KPI snapshot: {ex}",
            "correlationId": corr_id,
            "snapshot": snap,
        }


def _persist_snapshot_if_possible(snap_dict: Dict[str, Any], tenant_id: str, db_path: Optional[str] = None) -> None:
    """Save snapshot into durable Business Repository if available."""
    try:
        from productivity_mcp.business_repository import (
            KPISnapshotRecord,
            get_business_repository_client,
        )
        repo = get_business_repository_client(db_path=db_path)
        rec = KPISnapshotRecord(
            kpi_snapshot_id=snap_dict["snapshot_id"],
            tenant_id=tenant_id,
            snapshot_id=snap_dict["snapshot_id"],
            kpi_code=snap_dict["kpi_code"],
            organization_scope=snap_dict["organization_scope"],
            period=snap_dict["period"],
            metric_value=Decimal(str(snap_dict["value"])),
            unit=snap_dict.get("unit", "currency"),
            currency=snap_dict.get("currency", "AED"),
            source_updated_time=snap_dict.get("source_updated_time"),
            retrieved_at=snap_dict.get("retrieved_at", datetime.now(timezone.utc).isoformat()),
            completeness=snap_dict.get("completeness", "COMPLETE"),
            evidence_ref=snap_dict.get("evidence_ref", ""),
            input_hash=snap_dict.get("input_hash", ""),
        )
        repo.save_kpi_snapshot(rec)
        log.info(f"finance_snapshot_persisted id={rec.snapshot_id} kpi={rec.kpi_code}")
    except Exception as ex:
        log.warning(f"could_not_persist_kpi_snapshot: {ex}")
