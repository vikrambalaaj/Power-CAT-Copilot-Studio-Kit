"""Bounded Institutional Memory Service for Vendor History (W10).

Implements:
- Strict separation of conversation memory from approved institutional records.
- Authoritative vendor performance history repository with canonical vendor ID indexing.
- Multi-subsidiary and legal entity boundary enforcement.
- Prompt injection defenses: untrusted text sanitization for contracts and notes.
- Provenance tracking: original event date preserved distinct from ingestion timestamp.
- Double-import idempotency and deterministic source hash deduplication.
- Temporal coverage and chronological gap analysis.
- Conflict detection between concurrent positive and negative records.
- Mandatory caveat disclosure: absence of complaints != confirmed good performance.
- Dynamic permission re-checking.
"""
from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import time
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

from productivity_mcp.business_repository import (
    SqliteBusinessRepository,
    VendorPerformanceHistoryRecord,
    get_business_repository_client,
)
from shared_mcp.logger import get_logger

log = get_logger("institutional_memory")

ALLOWED_EVENT_TYPES: Set[str] = {
    "DELIVERY_DELAY",
    "QUALITY_DEFECT",
    "SLA_BREACH",
    "MILESTONE_SUCCESS",
    "AUDIT_NONCOMPLIANCE",
    "CONTRACT_FULFILLMENT",
    "PRICE_VARIANCE",
    "SECURITY_INCIDENT",
}

ALLOWED_SEVERITIES: Set[str] = {
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRITICAL",
}

ALLOWED_VERIFICATION_STATUSES: Set[str] = {
    "VERIFIED",
    "UNVERIFIED",
    "PENDING_REVIEW",
    "SUPERSEDED",
}

ALLOWED_ACCESS_SCOPES: Set[str] = {
    "CORP_PROCUREMENT",
    "FACILITY_MANAGEMENT",
    "RESTRICTED_LEGAL",
    "EXECUTIVE_ONLY",
}

# Detection patterns for prompt injection attempts in narrative text
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt\s*:", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a", re.IGNORECASE),
    re.compile(r"override\s+all\s+(weights|scores|rules)", re.IGNORECASE),
    re.compile(r"set\s+(weight|score)\s+to\s+100", re.IGNORECASE),
    re.compile(r"execute_tool\s*\(", re.IGNORECASE),
]

MANDATORY_PERFORMANCE_CAVEAT = (
    "MANDATORY AUDIT CAVEAT: Absence of documented negative events or complaints cannot be "
    "interpreted as confirmed satisfactory performance. Supplier evaluation must be grounded "
    "strictly in verified, positive evidence."
)


class InstitutionalMemoryError(Exception):
    """Base exception for institutional memory operations."""
    pass


class InstitutionalMemoryValidationError(InstitutionalMemoryError):
    """Raised on invalid schema or input values."""
    pass


class InstitutionalMemoryAccessDeniedError(InstitutionalMemoryError):
    """Raised on unauthorized cross-subsidiary or restricted scope access."""
    pass


class InstitutionalMemoryPersistenceError(InstitutionalMemoryError):
    """Raised when repository write or readback fails."""
    pass


def sanitize_untrusted_narrative(text: Optional[str]) -> str:
    """Sanitize narrative text to prevent prompt injection and markup attacks.
    
    Treats historical notes, vendor emails, and contract dispute narratives as untrusted text.
    Replaces detected prompt-injection attempts with safe security notices.
    """
    if not text:
        return ""
    clean = str(text).strip()
    
    # Check for active prompt injection attempts
    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern.search(clean):
            log.warning("prompt_injection_attempt_detected", pattern=pattern.pattern)
            clean = pattern.sub("[FILTERED: UNTRUSTED PROMPT INJECTION PAYLOAD REMOVED]", clean)

    # HTML-escape to prevent rendering injection
    return html.escape(clean)


def compute_source_hash(source_content: str | bytes | dict) -> str:
    """Compute deterministic SHA-256 hash of raw source material."""
    if isinstance(source_content, dict):
        raw = json.dumps(source_content, sort_keys=True).encode("utf-8")
    elif isinstance(source_content, str):
        raw = source_content.encode("utf-8")
    else:
        raw = bytes(source_content)
    return hashlib.sha256(raw).hexdigest()


async def ingest_institutional_record(
    vendor_id: str,
    vendor_name: str,
    entity_scope: str,
    contract_ref: str,
    period_start: str,
    period_end: str,
    event_type: str,
    severity: str,
    summary: str,
    source_doc_ref: str,
    original_event_date: str,
    details: Optional[str] = None,
    numeric_value: Optional[Decimal | float | str] = None,
    unit: str = "",
    currency: str = "",
    source_hash: Optional[str] = None,
    source_system: str = "S4HANA",
    recorded_by: Optional[str] = None,
    verification_status: str = "VERIFIED",
    access_scope: str = "CORP_PROCUREMENT",
    retention_policy: str = "7_YEARS_STANDARD",
    legal_hold: bool = False,
    tenant_id: str = "velora-tenant",
    verified_identity: Optional[Any] = None,
    user_email: Optional[str] = None,
    db_path: Optional[str] = None,
    repo: Optional[SqliteBusinessRepository] = None,
) -> Dict[str, Any]:
    """Ingest an approved institutional record for vendor performance history.
    
    Acceptance Criteria T10:
    - Retains original event date separately from ingestion timestamp.
    - Preserves source document reference and deterministic source SHA-256 hash.
    - Idempotent: re-ingesting identical record returns existing record without duplicate rows.
    - Validates schema against strict allowlists.
    - Neutralizes prompt-injection payloads in narrative text.
    - Readback verification ensures durable SQLite persistence.
    """
    # 1. Identity Resolution
    authoritative_recorder = None
    if verified_identity is not None:
        authoritative_recorder = (
            getattr(verified_identity, "display_email", None)
            or getattr(verified_identity, "email", None)
            or getattr(verified_identity, "object_id", None)
        )
    if not authoritative_recorder:
        authoritative_recorder = user_email or recorded_by or "system-ingestion"

    # 2. Schema Validation
    if not vendor_id or not str(vendor_id).strip():
        raise InstitutionalMemoryValidationError("Missing required parameter: 'vendor_id'.")
    v_id = str(vendor_id).strip().upper()

    if not vendor_name or not str(vendor_name).strip():
        raise InstitutionalMemoryValidationError("Missing required parameter: 'vendor_name'.")
    v_name = str(vendor_name).strip()

    if not entity_scope or not str(entity_scope).strip():
        raise InstitutionalMemoryValidationError("Missing required parameter: 'entity_scope'.")
    e_scope = str(entity_scope).strip()

    if not contract_ref or not str(contract_ref).strip():
        raise InstitutionalMemoryValidationError("Missing required parameter: 'contract_ref'.")
    c_ref = str(contract_ref).strip()

    ev_type = str(event_type).strip().upper()
    if ev_type not in ALLOWED_EVENT_TYPES:
        raise InstitutionalMemoryValidationError(
            f"Invalid event_type '{event_type}'. Must be one of: {sorted(list(ALLOWED_EVENT_TYPES))}."
        )

    sev = str(severity).strip().upper()
    if sev not in ALLOWED_SEVERITIES:
        raise InstitutionalMemoryValidationError(
            f"Invalid severity '{severity}'. Must be one of: {sorted(list(ALLOWED_SEVERITIES))}."
        )

    verif_status = str(verification_status).strip().upper()
    if verif_status not in ALLOWED_VERIFICATION_STATUSES:
        raise InstitutionalMemoryValidationError(
            f"Invalid verification_status '{verification_status}'. Must be one of: {sorted(list(ALLOWED_VERIFICATION_STATUSES))}."
        )

    acc_scope = str(access_scope).strip().upper()
    if acc_scope not in ALLOWED_ACCESS_SCOPES:
        raise InstitutionalMemoryValidationError(
            f"Invalid access_scope '{access_scope}'. Must be one of: {sorted(list(ALLOWED_ACCESS_SCOPES))}."
        )

    if not source_doc_ref or not str(source_doc_ref).strip():
        raise InstitutionalMemoryValidationError("Missing required parameter: 'source_doc_ref'.")
    doc_ref = str(source_doc_ref).strip()

    if not original_event_date or not str(original_event_date).strip():
        raise InstitutionalMemoryValidationError("Missing required parameter: 'original_event_date'.")
    orig_date = str(original_event_date).strip()

    # 3. Numeric Value Sanitization
    num_dec: Optional[Decimal] = None
    if numeric_value is not None and str(numeric_value).strip():
        try:
            num_dec = Decimal(str(numeric_value).strip())
        except Exception as ex:
            raise InstitutionalMemoryValidationError(f"Invalid numeric_value '{numeric_value}': {ex}")

    # 4. Source Hash Resolution
    effective_hash = str(source_hash).strip() if source_hash and str(source_hash).strip() else ""
    if not effective_hash:
        # Generate hash from core attributes
        effective_hash = compute_source_hash(f"{v_id}:{e_scope}:{c_ref}:{ev_type}:{orig_date}:{summary}")

    # 5. Prompt Injection Defense & Sanitization
    clean_summary = sanitize_untrusted_narrative(summary)
    clean_details = sanitize_untrusted_narrative(details)

    # 6. Deterministic Idempotency Key & Record ID
    seed = f"{tenant_id}:{v_id}:{e_scope}:{doc_ref}:{effective_hash}:{orig_date}"
    record_id = f"VPH-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"

    repository = repo or get_business_repository_client(db_path=db_path)

    # Check for existing record (Double-import idempotency)
    existing = repository.get_vendor_performance_history(record_id, tenant_id)
    if existing:
        log.info("vendor_history_idempotent_duplicate", record_id=record_id, vendor_id=v_id)
        return {
            "status": "ALREADY_COMMITTED",
            "recordId": existing.record_id,
            "vendorId": existing.vendor_id,
            "vendorName": existing.vendor_name,
            "entityScope": existing.entity_scope,
            "sourceHash": existing.source_hash,
            "originalEventDate": existing.original_event_date,
            "ingestedAt": existing.ingested_at,
            "isDuplicate": True,
            "message": "Institutional vendor performance record already ingested.",
        }

    # 7. Construct and Persist Record
    now_iso = datetime.now(timezone.utc).isoformat()
    record = VendorPerformanceHistoryRecord(
        record_id=record_id,
        tenant_id=tenant_id,
        vendor_id=v_id,
        vendor_name=v_name,
        entity_scope=e_scope,
        contract_ref=c_ref,
        period_start=str(period_start).strip(),
        period_end=str(period_end).strip(),
        event_type=ev_type,
        severity=sev,
        numeric_value=num_dec,
        unit=str(unit).strip(),
        currency=str(currency).strip(),
        summary=clean_summary,
        details=clean_details,
        source_doc_ref=doc_ref,
        source_hash=effective_hash,
        source_system=str(source_system).strip(),
        recorded_by=authoritative_recorder,
        verification_status=verif_status,
        access_scope=acc_scope,
        retention_policy=str(retention_policy).strip(),
        legal_hold=bool(legal_hold),
        original_event_date=orig_date,
        ingested_at=now_iso,
        version=1,
    )

    try:
        repository.save_vendor_performance_history(record)
    except Exception as exc:
        log.error("vendor_history_persistence_failed", error=str(exc), record_id=record_id)
        raise InstitutionalMemoryPersistenceError(f"Failed to persist vendor history: {exc}")

    # 8. Immediate Readback Verification
    readback = repository.get_vendor_performance_history(record_id, tenant_id)
    if not readback:
        raise InstitutionalMemoryPersistenceError(
            f"Readback verification failed: record '{record_id}' not found on disk."
        )
    if (
        readback.vendor_id != v_id
        or readback.source_hash != effective_hash
        or readback.original_event_date != orig_date
    ):
        raise InstitutionalMemoryPersistenceError(
            f"Readback mismatch on record '{record_id}': attributes do not match ingested payload."
        )

    return {
        "status": "INGESTED",
        "recordId": record_id,
        "vendorId": v_id,
        "vendorName": v_name,
        "entityScope": e_scope,
        "contractRef": c_ref,
        "eventType": ev_type,
        "severity": sev,
        "sourceHash": effective_hash,
        "originalEventDate": orig_date,
        "ingestedAt": now_iso,
        "isDuplicate": False,
        "message": "Approved institutional record ingested and verified successfully.",
    }


def get_vendor_history(
    vendor_id: str,
    tenant_id: str = "velora-tenant",
    caller_entity_scopes: Optional[List[str]] = None,
    caller_roles: Optional[List[str]] = None,
    include_superseded: bool = False,
    db_path: Optional[str] = None,
    repo: Optional[SqliteBusinessRepository] = None,
) -> Dict[str, Any]:
    """Retrieve historical vendor performance profile with scope filtering, gap analysis, and caveats.
    
    Acceptance Criteria T10:
    - Exact canonical vendor ID matching: same-name vendors stay strictly separate.
    - Subsidiary scoping: another subsidiary's restricted records are never returned.
    - Role re-checking: dynamic permission revocation takes effect.
    - Bounded relevant events with original evidence, temporal coverage, and gap detection.
    - Mandatory caveat: absence of complaints != clean performance record.
    - Truthful empty state: zero fabricated facts if no history exists.
    """
    if not vendor_id or not str(vendor_id).strip():
        raise InstitutionalMemoryValidationError("Parameter 'vendor_id' is required.")
    v_id = str(vendor_id).strip().upper()

    repository = repo or get_business_repository_client(db_path=db_path)

    # 1. Fetch all raw records for this canonical vendor ID
    raw_records = repository.list_vendor_history(v_id, tenant_id)

    if not raw_records:
        return {
            "status": "NO_HISTORY_FOUND",
            "vendorId": v_id,
            "totalRecords": 0,
            "records": [],
            "coverageStart": None,
            "coverageEnd": None,
            "gapsIdentified": ["No performance records on file for this vendor."],
            "conflictsIdentified": [],
            "disclaimer": MANDATORY_PERFORMANCE_CAVEAT,
            "summary": f"No historical performance records found for vendor '{v_id}'. Zero facts fabricated.",
        }

    # 2. Subsidiary Scope Filtering (Multi-subsidiary isolation)
    scoped_records: List[VendorPerformanceHistoryRecord] = []
    scopes_set = set(caller_entity_scopes) if caller_entity_scopes else None
    has_wildcard_scope = scopes_set is not None and ("*" in scopes_set or "CORP_ALL" in scopes_set)

    for r in raw_records:
        if scopes_set is not None and not has_wildcard_scope:
            if r.entity_scope not in scopes_set:
                # Strictly exclude other subsidiary's records
                continue
        scoped_records.append(r)

    # 3. Access Scope & Role Authorization (Dynamic permission revocation)
    authorized_records: List[VendorPerformanceHistoryRecord] = []
    roles_set = set(caller_roles or ["CORP_PROCUREMENT"])

    for r in scoped_records:
        if r.access_scope == "RESTRICTED_LEGAL":
            if "LEGAL_AUDIT" not in roles_set and "EXECUTIVE_OFFICE" not in roles_set:
                log.info("restricted_legal_record_filtered", record_id=r.record_id, vendor_id=v_id)
                continue
        elif r.access_scope == "EXECUTIVE_ONLY":
            if "EXECUTIVE_OFFICE" not in roles_set and "C_SUITE" not in roles_set:
                log.info("executive_only_record_filtered", record_id=r.record_id, vendor_id=v_id)
                continue

        if not include_superseded and r.verification_status == "SUPERSEDED":
            continue

        authorized_records.append(r)

    if not authorized_records:
        return {
            "status": "NO_HISTORY_FOUND",
            "vendorId": v_id,
            "totalRecords": 0,
            "records": [],
            "coverageStart": None,
            "coverageEnd": None,
            "gapsIdentified": ["No records accessible within caller's entity and role scope."],
            "conflictsIdentified": [],
            "disclaimer": MANDATORY_PERFORMANCE_CAVEAT,
            "summary": f"Vendor '{v_id}' has records in other scopes, but none are authorized for caller.",
        }

    # 4. Chronological Sorting & Temporal Coverage
    # Sort by original_event_date ascending for temporal analysis
    sorted_records = sorted(authorized_records, key=lambda x: x.original_event_date)
    coverage_start = sorted_records[0].original_event_date
    coverage_end = sorted_records[-1].original_event_date

    # 5. Gap Identification (Detect missing performance periods > 180 days)
    gaps: List[str] = []
    for i in range(len(sorted_records) - 1):
        try:
            d1 = datetime.fromisoformat(sorted_records[i].original_event_date.replace("Z", "+00:00"))
            d2 = datetime.fromisoformat(sorted_records[i + 1].original_event_date.replace("Z", "+00:00"))
            diff_days = (d2 - d1).days
            if diff_days > 180:
                gaps.append(
                    f"Performance data gap of {diff_days} days detected between {sorted_records[i].original_event_date[:10]} "
                    f"and {sorted_records[i + 1].original_event_date[:10]}."
                )
        except Exception:
            pass

    # 6. Conflict Detection (Concurrent positive and negative events)
    conflicts: List[str] = []
    positive_events = [r for r in sorted_records if r.event_type in ("MILESTONE_SUCCESS", "CONTRACT_FULFILLMENT")]
    negative_events = [r for r in sorted_records if r.severity in ("HIGH", "CRITICAL") or r.event_type in ("SLA_BREACH", "QUALITY_DEFECT")]
    
    if positive_events and negative_events:
        for p in positive_events:
            for n in negative_events:
                if p.contract_ref == n.contract_ref:
                    conflicts.append(
                        f"Contract conflict detected on {p.contract_ref}: concurrent positive event '{p.event_type}' "
                        f"({p.original_event_date[:10]}) coexists with negative event '{n.event_type}' "
                        f"({n.original_event_date[:10]}, severity: {n.severity})."
                    )

    # 7. Formulate Bounded Records Payload
    records_out = []
    for r in sorted_records:
        records_out.append({
            "recordId": r.record_id,
            "vendorId": r.vendor_id,
            "vendorName": r.vendor_name,
            "entityScope": r.entity_scope,
            "contractRef": r.contract_ref,
            "eventType": r.event_type,
            "severity": r.severity,
            "numericValue": str(r.numeric_value) if r.numeric_value is not None else None,
            "unit": r.unit,
            "currency": r.currency,
            "summary": r.summary,
            "details": r.details,
            "sourceDocRef": r.source_doc_ref,
            "sourceHash": r.source_hash,
            "sourceSystem": r.source_system,
            "recordedBy": r.recorded_by,
            "verificationStatus": r.verification_status,
            "accessScope": r.access_scope,
            "originalEventDate": r.original_event_date,
            "ingestedAt": r.ingested_at,
        })

    return {
        "status": "SUCCESS",
        "vendorId": v_id,
        "vendorName": sorted_records[0].vendor_name,
        "totalRecords": len(records_out),
        "records": records_out,
        "coverageStart": coverage_start,
        "coverageEnd": coverage_end,
        "gapsIdentified": gaps,
        "conflictsIdentified": conflicts,
        "disclaimer": MANDATORY_PERFORMANCE_CAVEAT,
        "summary": (
            f"Retrieved {len(records_out)} verified institutional record(s) for vendor {v_id} ({sorted_records[0].vendor_name}) "
            f"covering {coverage_start[:10]} to {coverage_end[:10]}. {len(gaps)} gap(s) and {len(conflicts)} conflict(s) detected."
        ),
    }
