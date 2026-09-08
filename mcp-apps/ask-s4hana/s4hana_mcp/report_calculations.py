"""Deterministic calculation engine for S/4HANA Finance reports."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from .contracts import format_decimal, safe_decimal


def _get_record_currency(r: dict[str, Any], entity_type: str | None = None) -> str:
    """Extract currency from S/4 OData record using exact per-entity field names (F01)."""
    if entity_type == "ReceivablesAging" or "CompanyCodeCurrency" in r:
        val = r.get("CompanyCodeCurrency")
        if val:
            return str(val).strip().upper()
    if entity_type == "PayablesAging" or "DisplayCurrency" in r:
        val = r.get("DisplayCurrency")
        if val:
            return str(val).strip().upper()
    if entity_type == "BudgetTransfer" or "TransactionCurrency" in r:
        val = r.get("TransactionCurrency")
        if val:
            return str(val).strip().upper()
    if entity_type == "BudgetConsumption" or "FinancialManagementAreaCrcy" in r:
        val = r.get("FinancialManagementAreaCrcy")
        if val:
            return str(val).strip().upper()

    return str(
        r.get("CompanyCodeCurrency")
        or r.get("DisplayCurrency")
        or r.get("TransactionCurrency")
        or r.get("FinancialManagementAreaCrcy")
        or r.get("Currency")
        or r.get("DocumentCurrency")
        or ""
    ).strip().upper()


def _calculate_single_currency_aging(records: list[dict[str, Any]], is_receivable: bool = True) -> dict[str, Any]:
    buckets = {
        "not_yet_due": {"label": "Not yet due", "amount": Decimal("0.00"), "count": 0},
        "due_today": {"label": "Due today", "amount": Decimal("0.00"), "count": 0},
        "bucket_1_30": {"label": "1–30 days overdue", "amount": Decimal("0.00"), "count": 0},
        "bucket_31_60": {"label": "31–60 days overdue", "amount": Decimal("0.00"), "count": 0},
        "bucket_61_90": {"label": "61–90 days overdue", "amount": Decimal("0.00"), "count": 0},
        "bucket_91_180": {"label": "91–180 days overdue", "amount": Decimal("0.00"), "count": 0},
        "bucket_over_180": {"label": "Over 180 days overdue", "amount": Decimal("0.00"), "count": 0},
        "unaged": {"label": "Age unavailable", "amount": Decimal("0.00"), "count": 0},
    }
    
    total_open_signed = Decimal("0.00")
    gross_debit = Decimal("0.00")
    gross_credit = Decimal("0.00")
    overdue_exposure = Decimal("0.00")
    party_totals: dict[str, dict[str, Any]] = {}
    party_id_key = "Customer" if is_receivable else "Supplier"
    party_name_key = "CustomerName" if is_receivable else "SupplierName"
    detected_currency = ""

    entity_type = "ReceivablesAging" if is_receivable else "PayablesAging"
    has_invalid_amount = False
    invalid_reason = ""

    for r in records:
        if not detected_currency:
            detected_currency = _get_record_currency(r, entity_type=entity_type)
        raw_amt = (
            r.get("OpenAmount")
            if r.get("OpenAmount") is not None
            else (
                r.get("AmountInCompanyCodeCurrency")
                if r.get("AmountInCompanyCodeCurrency") is not None
                else (
                    r.get("AmountInDisplayCurrency")
                    if r.get("AmountInDisplayCurrency") is not None
                    else r.get("Amount")
                )
            )
        )
        if raw_amt is None:
            has_invalid_amount = True
            invalid_reason = f"Missing required monetary amount in {entity_type} record"
            break
        open_amt = safe_decimal(raw_amt, allow_none=True, reject_nonfinite=True)
        if open_amt is None:
            has_invalid_amount = True
            invalid_reason = f"Invalid monetary amount in source record: {raw_amt!r}"
            break

        total_open_signed += open_amt
        
        if open_amt > Decimal("0.00"):
            gross_debit += open_amt
        elif open_amt < Decimal("0.00"):
            gross_credit += open_amt


        # Age parsing
        days_raw = r.get("DaysOverdue")
        if days_raw is None or str(days_raw).strip() == "":
            bucket_key = "unaged"
        else:
            try:
                days = int(float(str(days_raw)))
                if days < 0:
                    bucket_key = "not_yet_due"
                elif days == 0:
                    bucket_key = "due_today"
                elif 1 <= days <= 30:
                    bucket_key = "bucket_1_30"
                elif 31 <= days <= 60:
                    bucket_key = "bucket_31_60"
                elif 61 <= days <= 90:
                    bucket_key = "bucket_61_90"
                elif 91 <= days <= 180:
                    bucket_key = "bucket_91_180"
                else:
                    bucket_key = "bucket_over_180"
            except (ValueError, TypeError):
                bucket_key = "unaged"

        buckets[bucket_key]["amount"] += open_amt
        buckets[bucket_key]["count"] += 1

        if bucket_key not in {"not_yet_due", "due_today", "unaged"} and open_amt > Decimal("0.00"):
            overdue_exposure += open_amt

        party_id = str(r.get(party_id_key) or "").strip()
        party_name = str(r.get(party_name_key) or party_id or "Unknown").strip()
        key = party_id or party_name
        if key:
            if key not in party_totals:
                party_totals[key] = {"id": party_id, "name": party_name, "amount": Decimal("0.00"), "count": 0}
            party_totals[key]["amount"] += open_amt
            party_totals[key]["count"] += 1

    if has_invalid_amount:
        return {
            "currency": detected_currency,
            "total_open_signed": None,
            "gross_debit": None,
            "gross_credit": None,
            "overdue_exposure": None,
            "bucket_sum": None,
            "buckets": {
                k: {"label": v["label"], "amount": None, "count": 0}
                for k, v in buckets.items()
            },
            "top_parties": [],
            "status": "ERROR",
            "code": "CONTRACT_MISMATCH",
            "is_valid": False,
            "error": invalid_reason,
        }

    bucket_sum = sum((b["amount"] for b in buckets.values()), Decimal("0.00"))
    top_parties = sorted(party_totals.values(), key=lambda x: x["amount"], reverse=True)[:10]

    return {
        "currency": detected_currency,
        "total_open_signed": total_open_signed,
        "gross_debit": gross_debit,
        "gross_credit": gross_credit,
        "overdue_exposure": overdue_exposure,
        "bucket_sum": bucket_sum,
        "buckets": {k: {"label": v["label"], "amount": v["amount"], "count": v["count"]} for k, v in buckets.items()},
        "top_parties": top_parties,
    }


def calculate_aging_buckets(
    records: list[dict[str, Any]],
    is_receivable: bool = True,
    requested_currency: str | None = None,
) -> dict[str, Any]:
    """
    Calculate deterministic aging buckets from AR/AP records.
    Partitions strictly by source currency to prevent unapproved mixed-currency summation (R02, F01).
    """
    entity_type = "ReceivablesAging" if is_receivable else "PayablesAging"
    # Group records by currency
    currencies: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        c = _get_record_currency(r, entity_type=entity_type) or (requested_currency.upper() if requested_currency else "UNSPECIFIED")
        currencies.setdefault(c, []).append(r)

    if not currencies:
        base = _calculate_single_currency_aging([], is_receivable)
        base["currency"] = requested_currency or ""
        base["is_multi_currency"] = False
        return base

    # If single currency or requested currency explicitly supplied
    if len(currencies) == 1:
        c_code, c_records = next(iter(currencies.items()))
        res = _calculate_single_currency_aging(c_records, is_receivable)
        res["currency"] = c_code if c_code != "UNSPECIFIED" else (requested_currency or "")
        res["is_multi_currency"] = False
        return res

    # Multiple currencies present: do NOT sum them together into AED (R02, F01)
    by_currency: dict[str, dict[str, Any]] = {}
    any_partition_error = False
    partition_error_messages: list[str] = []

    for c_code, c_records in currencies.items():
        sub_res = _calculate_single_currency_aging(c_records, is_receivable)
        sub_res["currency"] = c_code
        if sub_res.get("status") == "ERROR" or not sub_res.get("is_valid", True):
            any_partition_error = True
            partition_error_messages.append(f"[{c_code}] {sub_res.get('error', 'Calculation error')}")
        by_currency[c_code] = sub_res

    res = {
        "is_multi_currency": True,
        "currencies_present": list(currencies.keys()),
        "by_currency": by_currency,
        "warning": "Multiple currencies present in source records. Amounts partitioned by currency; unified aggregation disallowed without approved exchange rates.",
    }
    if any_partition_error:
        res["status"] = "ERROR"
        res["code"] = "CONTRACT_MISMATCH"
        res["is_valid"] = False
        res["error"] = "; ".join(partition_error_messages)
    return res


def calculate_budget_movements(
    records: list[dict[str, Any]],
    requested_currency: str | None = None,
) -> dict[str, Any]:
    """
    Classify budget entries into original budget vs transfers vs supplements/returns.
    Supports two-sided movement analysis to prevent double counting (C16, R02, F01).
    """
    # Partition by currency if multiple currencies exist
    currencies: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        c = _get_record_currency(r, entity_type="BudgetTransfer") or (requested_currency.upper() if requested_currency else "UNSPECIFIED")
        currencies.setdefault(c, []).append(r)

    if len(currencies) > 1 and not requested_currency:
        by_curr: dict[str, Any] = {}
        any_err = False
        err_msgs: list[str] = []
        for c_code, c_recs in currencies.items():
            sub = calculate_budget_movements(c_recs, requested_currency=c_code)
            if sub.get("status") == "ERROR" or not sub.get("is_valid", True):
                any_err = True
                err_msgs.append(f"[{c_code}] {sub.get('error')}")
            by_curr[c_code] = sub
        res = {
            "is_multi_currency": True,
            "currencies_present": list(currencies.keys()),
            "by_currency": by_curr,
            "currency": "MULTI",
            "total_movement_amount": None if any_err else Decimal("0.00"),
            "transfer_gross_volume": None if any_err else Decimal("0.00"),
            "transfer_net_movement": None if any_err else Decimal("0.00"),
            "categories": {},
            "documents": [],
        }
        if any_err:
            res["status"] = "ERROR"
            res["code"] = "CONTRACT_MISMATCH"
            res["is_valid"] = False
            res["error"] = "; ".join(err_msgs)
        return res

    categories: dict[str, dict[str, Any]] = {
        "ORIGINAL_BUDGET": {"label": "Original Budget", "amount": Decimal("0.00"), "count": 0},
        "TRANSFER": {"label": "Budget Transfer", "amount": Decimal("0.00"), "count": 0},
        "SUPPLEMENT": {"label": "Budget Supplement", "amount": Decimal("0.00"), "count": 0},
        "RETURN": {"label": "Budget Return", "amount": Decimal("0.00"), "count": 0},
        "OTHER": {"label": "Other Budget Movement", "amount": Decimal("0.00"), "count": 0},
    }
    
    total_movement_amount = Decimal("0.00")
    transfer_send_volume = Decimal("0.00")
    transfer_receive_volume = Decimal("0.00")
    documents: dict[str, dict[str, Any]] = {}
    detected_currency = requested_currency or ""
    has_invalid_mvt = False
    invalid_mvt_reason = ""

    for r in records:
        if not detected_currency:
            detected_currency = _get_record_currency(r, entity_type="BudgetTransfer")
        raw_amt = r.get("BudgetAmountInTransactionCrcy") if r.get("BudgetAmountInTransactionCrcy") is not None else r.get("Amount")
        if raw_amt is None:
            has_invalid_mvt = True
            invalid_mvt_reason = "Missing required budget movement amount in record"
            break
        amt = safe_decimal(raw_amt, allow_none=True, reject_nonfinite=True)
        if amt is None:
            has_invalid_mvt = True
            invalid_mvt_reason = f"Invalid budget movement amount: {raw_amt!r}"
            break
        total_movement_amount += amt
        
        proc = str(r.get("BudgetingProcess") or "").strip().upper()
        mvt = str(r.get("BudgetMovementType") or "").strip().upper()
        doc_type = str(r.get("BudgetEntryDocumentType") or "").strip().upper()

        if proc == "ENTR" or mvt == "ENTR" or "ORIGINAL" in str(r.get("BudgetingProcessText") or "").upper():
            cat_key = "ORIGINAL_BUDGET"
        elif proc in {"TRAN", "TRFR"} or mvt in {"TRAN", "TRFR"}:
            cat_key = "TRANSFER"
            if amt < Decimal("0.00"):
                transfer_send_volume += abs(amt)
            else:
                transfer_receive_volume += amt
        elif proc in {"SUPL", "SUPP"} or mvt in {"SUPL", "SUPP"}:
            cat_key = "SUPPLEMENT"
        elif proc in {"RETN", "RETR"} or mvt in {"RETN", "RETR"}:
            cat_key = "RETURN"
        else:
            cat_key = "OTHER"

        categories[cat_key]["amount"] += amt
        categories[cat_key]["count"] += 1

        doc_id = str(r.get("BudgetChangeDocument") or r.get("BudgetEntryDocument") or "").strip()
        if doc_id:
            if doc_id not in documents:
                documents[doc_id] = {
                    "document": doc_id,
                    "year": str(r.get("FinMgmtAreaFiscalYear") or r.get("BudgetDocumentYear") or "").strip(),
                    "funds_center": str(r.get("FundsCenter") or "").strip(),
                    "commitment_item": str(r.get("CommitmentItem") or "").strip(),
                    "amount": Decimal("0.00"),
                    "category": categories[cat_key]["label"],
                }
            documents[doc_id]["amount"] += amt

    if has_invalid_mvt:
        return {
            "currency": detected_currency or (next(iter(currencies.keys())) if currencies else ""),
            "total_movement_amount": None,
            "transfer_gross_volume": None,
            "transfer_net_movement": None,
            "categories": {k: {"label": v["label"], "amount": None, "count": 0} for k, v in categories.items()},
            "documents": [],
            "status": "ERROR",
            "code": "CONTRACT_MISMATCH",
            "is_valid": False,
            "error": invalid_mvt_reason,
        }

    return {
        "currency": detected_currency or (next(iter(currencies.keys())) if currencies else ""),
        "total_movement_amount": total_movement_amount,
        "transfer_gross_volume": max(transfer_send_volume, transfer_receive_volume) if (transfer_send_volume > 0 or transfer_receive_volume > 0) else categories["TRANSFER"]["amount"],
        "transfer_net_movement": categories["TRANSFER"]["amount"],
        "categories": categories,
        "documents": list(documents.values())[:20],
    }


def calculate_budget_consumption(
    records: list[dict[str, Any]],
    mapping_approved: bool = False,
    requested_currency: str | None = None,
) -> dict[str, Any]:
    """
    Calculate budget consumption measures.
    Enforces unified additive grain reconciliation between headline and detail breakdown (F01, F02, R02, R03).
    """
    currencies: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        c = _get_record_currency(r, entity_type="BudgetConsumption") or (requested_currency.upper() if requested_currency else "UNSPECIFIED")
        currencies.setdefault(c, []).append(r)

    if len(currencies) > 1 and not requested_currency:
        by_curr: dict[str, Any] = {}
        any_err = False
        err_msgs: list[str] = []
        for c_code, c_recs in currencies.items():
            sub = calculate_budget_consumption(c_recs, mapping_approved=mapping_approved, requested_currency=c_code)
            if sub.get("status") == "ERROR" or not sub.get("is_valid", True):
                any_err = True
                err_msgs.append(f"[{c_code}] {sub.get('error')}")
            by_curr[c_code] = sub
        res = {
            "is_multi_currency": True,
            "currencies_present": list(currencies.keys()),
            "by_currency": by_curr,
            "currency": "MULTI",
            "raw_budget": None if any_err else Decimal("0.00"),
            "raw_commitments": None if any_err else Decimal("0.00"),
            "raw_actuals": None if any_err else Decimal("0.00"),
            "raw_controlling": None if any_err else Decimal("0.00"),
            "funds_centers": [],
            "mapping_approved": False,
            "mapping_status": "CONFIGURATION_REQUIRED",
            "configuration_notice": (
                "Finance-approved value-type mapping and additive budget grain are required "
                "before calculating aggregate budget variance and utilization."
            ),
        }
        if any_err:
            res["status"] = "ERROR"
            res["code"] = "CONTRACT_MISMATCH"
            res["is_valid"] = False
            res["error"] = "; ".join(err_msgs)
        return res

    total_budget = Decimal("0.00")
    total_commitments = Decimal("0.00")
    total_actuals = Decimal("0.00")
    total_controlling = Decimal("0.00")
    funds_centers: dict[str, dict[str, Any]] = {}
    detected_currency = requested_currency or ""
    has_invalid_consump = False
    invalid_consump_reason = ""

    for r in records:
        if not detected_currency:
            detected_currency = _get_record_currency(r, entity_type="BudgetConsumption")
        for raw_val, name in [
            (r.get("BudgetAmountInFMACrcy"), "Budget"),
            (r.get("CmtmtOpenItemAmountInFMACrcy"), "Commitments"),
            (r.get("ActualAmountInFMACrcy"), "Actuals"),
            (r.get("CtrlgItemAmountInFMACrcy"), "Controlling"),
        ]:
            if raw_val is not None:
                dec_check = safe_decimal(raw_val, allow_none=True, reject_nonfinite=True)
                if dec_check is None:
                    has_invalid_consump = True
                    invalid_consump_reason = f"Invalid {name} monetary amount: {raw_val!r}"
                    break
        if has_invalid_consump:
            break

        b_amt = safe_decimal(r.get("BudgetAmountInFMACrcy"), default=Decimal("0.00"), reject_nonfinite=True) or Decimal("0.00")
        c_amt = safe_decimal(r.get("CmtmtOpenItemAmountInFMACrcy"), default=Decimal("0.00"), reject_nonfinite=True) or Decimal("0.00")
        a_amt = safe_decimal(r.get("ActualAmountInFMACrcy"), default=Decimal("0.00"), reject_nonfinite=True) or Decimal("0.00")
        ctrl_amt = safe_decimal(r.get("CtrlgItemAmountInFMACrcy"), default=Decimal("0.00"), reject_nonfinite=True) or Decimal("0.00")

        # Reconcile headline and funds-center detail from the exact same validated inputs (F02)
        total_budget += b_amt
        total_commitments += c_amt
        total_actuals += a_amt
        total_controlling += ctrl_amt

        fc_id = str(r.get("FundsCenter") or "Unassigned").strip()
        fc_desc = str(r.get("FundsCenterDescription") or fc_id).strip()
        if fc_id not in funds_centers:
            funds_centers[fc_id] = {
                "funds_center": fc_id,
                "description": fc_desc,
                "budget": Decimal("0.00"),
                "commitments": Decimal("0.00"),
                "actuals": Decimal("0.00"),
            }
        funds_centers[fc_id]["budget"] += b_amt
        funds_centers[fc_id]["commitments"] += c_amt
        funds_centers[fc_id]["actuals"] += a_amt

    if has_invalid_consump:
        return {
            "currency": detected_currency or (next(iter(currencies.keys())) if currencies else ""),
            "raw_budget": None,
            "raw_commitments": None,
            "raw_actuals": None,
            "raw_controlling": None,
            "funds_centers": [],
            "status": "ERROR",
            "code": "CONTRACT_MISMATCH",
            "is_valid": False,
            "error": invalid_consump_reason,
            "mapping_approved": False,
            "mapping_status": "CONFIGURATION_REQUIRED",
        }

    res: dict[str, Any] = {
        "currency": detected_currency or (next(iter(currencies.keys())) if currencies else ""),
        "raw_budget": total_budget,
        "raw_commitments": total_commitments,
        "raw_actuals": total_actuals,
        "raw_controlling": total_controlling,
        "funds_centers": list(funds_centers.values())[:20],
        "mapping_approved": mapping_approved,
    }

    if not mapping_approved:
        # R03 / F02: Withhold unverified aggregate business metrics and communicate CONFIGURATION_REQUIRED
        res["mapping_status"] = "CONFIGURATION_REQUIRED"
        res["configuration_notice"] = (
            "Finance-approved value-type mapping and additive budget grain are required "
            "before calculating aggregate budget variance and utilization."
        )
    else:
        variance = total_actuals - total_budget
        available = total_budget - total_actuals - total_commitments
        if total_budget > Decimal("0.00"):
            utilization_pct = (total_actuals / total_budget) * Decimal("100.0")
            encumbered_pct = ((total_actuals + total_commitments) / total_budget) * Decimal("100.0")
        else:
            utilization_pct = None
            encumbered_pct = None
        res.update({
            "approved_budget": total_budget,
            "actual_expenditure": total_actuals,
            "open_commitments": total_commitments,
            "available_budget": available,
            "variance": variance,
            "utilization_pct": utilization_pct,
            "encumbered_pct": encumbered_pct,
            "mapping_status": "APPROVED",
        })
    return res
