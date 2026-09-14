"""Per-Recommendation Feedback Service for Velora Executive Platform (W09).

Implements:
- Server-verified identity binding (preventing body-supplied reviewer overrides).
- Cross-tenant boundary isolation.
- Fail-closed persistence and immediate readback verification.
- Original recommendation immutability verification.
- Double-click idempotency.
- Separation of feedback from lifecycle actions (acknowledge / dismiss).
- Safe rule aggregation statistics without automated retuning.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

from .audit_client import (
    AuditCommitStatus,
    DataverseAuditRecord,
    RECORD_TYPE_TOOL_EXECUTION_END,
    get_productivity_audit_service,
)
from .business_repository import (
    RecommendationEntityRecord,
    RecommendationFeedbackRecord,
    SqliteBusinessRepository,
    get_business_repository_client,
)
from shared_mcp.logger import get_logger

log = get_logger("feedback_service")

ALLOWED_FEEDBACK_TYPES: Set[str] = {
    "TIMELY_AND_ACCURATE",
    "ACTIONABLE",
    "FALSE_POSITIVE",
    "IRRELEVANT",
    "INCORRECT_THRESHOLD",
    "OTHER",
}

MAX_COMMENT_LENGTH = 1000


class FeedbackValidationError(ValueError):
    """Raised when feedback input fails semantic validation."""
    pass


class FeedbackAccessDeniedError(PermissionError):
    """Raised when feedback is submitted across tenant boundaries or with forged identity."""
    pass


class FeedbackNotFoundError(KeyError):
    """Raised when the target recommendation does not exist."""
    pass


class FeedbackPersistenceError(RuntimeError):
    """Raised when persistence or readback verification fails."""
    pass


def _compute_rec_state_hash(rec: RecommendationEntityRecord) -> str:
    """Compute hash of recommendation content to verify immutability."""
    payload = {
        "rec_id": rec.rec_id,
        "tenant_id": rec.tenant_id,
        "kpi_code": rec.kpi_code,
        "observed_value": str(rec.observed_value),
        "threshold": str(rec.threshold),
        "confidence": rec.confidence,
        "confidence_reason": rec.confidence_reason,
        "impact": rec.impact,
        "explanation": rec.explanation,
        "suggested_action": rec.suggested_action,
        "status": rec.status,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


async def record_recommendation_feedback(
    recommendation_id: str,
    is_useful: bool,
    feedback_type: str,
    comment: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    verified_identity: Optional[Any] = None,
    user_email: Optional[str] = None,
    user_object_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    body_reviewer: Optional[str] = None,
    root_correlation_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    db_path: Optional[str] = None,
    repo: Optional[SqliteBusinessRepository] = None,
    audit_service: Optional[Any] = None,
) -> Dict[str, Any]:
    """Record verified per-recommendation feedback with strict isolation and immutability.
    
    Acceptance Criteria T09:
    1. Bind reviewer identity strictly to server-verified authentication context.
       Reject conflicting body-supplied reviewer overrides.
    2. Enforce strict tenant boundary checks. Cross-tenant feedback is blocked.
    3. Validate feedback_type against allowlist and bound comment length <= 1000.
    4. Provide double-click idempotency (duplicate calls return ALREADY_COMMITTED).
    5. Perform immediate readback verification: any mismatch returns FAILED.
    6. Verify that the original recommendation content, claims, and status are IMMUTABLE.
    7. Record Dataverse audit log for compliance.
    """
    corr_id = root_correlation_id or f"corr-fb-{int(time.time() * 1000)}"

    # 1. Identity Resolution & Impersonation Prevention
    verified_reviewer = None
    if verified_identity is not None:
        verified_reviewer = (
            getattr(verified_identity, "display_email", None)
            or getattr(verified_identity, "email", None)
            or getattr(verified_identity, "object_id", None)
        )
    if not verified_reviewer:
        verified_reviewer = user_email or user_object_id

    if not verified_reviewer:
        raise FeedbackAccessDeniedError(
            "Unauthenticated: A verified user principal (email or object_id) is required to submit feedback."
        )

    # Impersonation Prevention: Body-supplied reviewer override is strictly prohibited
    if body_reviewer is not None and str(body_reviewer).strip():
        body_norm = str(body_reviewer).strip().lower()
        verified_norm = str(verified_reviewer).strip().lower()
        email_norm = str(user_email).strip().lower() if user_email else ""
        oid_norm = str(user_object_id).strip().lower() if user_object_id else ""
        
        if body_norm not in (verified_norm, email_norm, oid_norm):
            log.warning(
                "feedback_impersonation_blocked",
                body_reviewer=body_reviewer,
                verified_reviewer=verified_reviewer,
            )
            raise FeedbackAccessDeniedError(
                f"Impersonation attempt detected: body-supplied reviewer '{body_reviewer}' "
                f"does not match verified caller identity '{verified_reviewer}'."
            )

    # 2. Input Validation
    if not recommendation_id or not str(recommendation_id).strip():
        raise FeedbackValidationError("Missing required parameter: 'recommendation_id'.")
    rec_id_clean = str(recommendation_id).strip()

    if not isinstance(is_useful, bool):
        raise FeedbackValidationError(
            f"Parameter 'is_useful' must be a boolean (True/False), received: {type(is_useful).__name__}."
        )

    fb_type_clean = str(feedback_type).strip().upper() if feedback_type else ""
    if fb_type_clean not in ALLOWED_FEEDBACK_TYPES:
        raise FeedbackValidationError(
            f"Invalid feedback_type '{feedback_type}'. Must be one of: {sorted(list(ALLOWED_FEEDBACK_TYPES))}."
        )

    comment_clean = str(comment).strip() if comment is not None else ""
    if len(comment_clean) > MAX_COMMENT_LENGTH:
        raise FeedbackValidationError(
            f"Feedback comment exceeds maximum allowable length of {MAX_COMMENT_LENGTH} characters "
            f"(received {len(comment_clean)} chars)."
        )

    # 3. Tenant Boundary & Repository Resolution
    active_tenant = (
        tenant_id
        or (getattr(verified_identity, "tenant_id", None) if verified_identity else None)
        or "velora-tenant"
    )

    repository = repo or get_business_repository_client(db_path=db_path)

    # 4. Verify Recommendation Existence and Tenant Isolation
    target_rec = repository.get_recommendation(rec_id_clean, active_tenant)
    if not target_rec:
        # Check if the recommendation belongs to a different tenant
        cross_tenant_rec = repository.get_recommendation_any_tenant(rec_id_clean)
        if cross_tenant_rec:
            log.warning(
                "feedback_cross_tenant_access_denied",
                recommendation_id=rec_id_clean,
                caller_tenant=active_tenant,
                resource_tenant=cross_tenant_rec.tenant_id,
            )
            raise FeedbackAccessDeniedError(
                f"Cross-tenant access violation: recommendation '{rec_id_clean}' belongs to tenant "
                f"'{cross_tenant_rec.tenant_id}', not caller tenant '{active_tenant}'."
            )
        raise FeedbackNotFoundError(
            f"Recommendation '{rec_id_clean}' not found for tenant '{active_tenant}'."
        )

    # Capture initial hash of recommendation to verify immutability
    rec_hash_before = _compute_rec_state_hash(target_rec)

    # 5. Deterministic Idempotency Key & Deduplication
    if idempotency_key and str(idempotency_key).strip():
        seed = f"{active_tenant}:{rec_id_clean}:{verified_reviewer}:{idempotency_key.strip()}"
    else:
        seed = f"{active_tenant}:{rec_id_clean}:{verified_reviewer}:{fb_type_clean}:{is_useful}"
    
    feedback_id = f"FB-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"

    # Double-click idempotency check
    existing_fb = repository.get_recommendation_feedback(feedback_id, active_tenant)
    if existing_fb is not None:
        log.info(
            "feedback_double_click_idempotent",
            feedback_id=feedback_id,
            recommendation_id=rec_id_clean,
            reviewer=verified_reviewer,
        )
        # Verify recommendation immutability even on idempotent duplicate
        rec_after_idempotent = repository.get_recommendation(rec_id_clean, active_tenant)
        if rec_after_idempotent and _compute_rec_state_hash(rec_after_idempotent) != rec_hash_before:
            raise FeedbackPersistenceError(
                f"Immutability breach: recommendation '{rec_id_clean}' mutated during idempotent call."
            )

        return {
            "status": "ALREADY_COMMITTED",
            "feedbackId": existing_fb.feedback_id,
            "recommendationId": existing_fb.recommendation_id,
            "reviewer": existing_fb.reviewer,
            "isUseful": existing_fb.is_useful,
            "feedbackType": existing_fb.feedback_type,
            "comment": existing_fb.comment,
            "recordedAt": existing_fb.recorded_at,
            "isDuplicate": True,
            "correlationId": corr_id,
            "auditStatus": "PERSISTED",
            "message": "Feedback already recorded with identical idempotency key.",
        }

    # 6. Construct & Persist Feedback Record
    now_iso = datetime.now(timezone.utc).isoformat()
    record = RecommendationFeedbackRecord(
        recommendation_feedback_id=feedback_id,
        tenant_id=active_tenant,
        feedback_id=feedback_id,
        recommendation_id=rec_id_clean,
        reviewer=verified_reviewer,
        is_useful=is_useful,
        feedback_type=fb_type_clean,
        comment=comment_clean,
        recorded_at=now_iso,
        version=1,
    )

    try:
        repository.save_recommendation_feedback(record)
    except Exception as exc:
        log.error("feedback_persistence_write_failed", error=str(exc), feedback_id=feedback_id)
        return {
            "status": "FAILED",
            "feedbackId": feedback_id,
            "recommendationId": rec_id_clean,
            "error": f"Database write failed: {exc}",
            "correlationId": corr_id,
            "auditStatus": "FAILED",
        }

    # 7. Immediate Readback Verification
    readback = repository.get_recommendation_feedback(feedback_id, active_tenant)
    if not readback:
        log.error("feedback_readback_not_found", feedback_id=feedback_id)
        raise FeedbackPersistenceError(
            f"Readback verification failed: feedback record '{feedback_id}' could not be confirmed on disk."
        )
    if (
        readback.feedback_id != feedback_id
        or readback.is_useful != is_useful
        or readback.feedback_type != fb_type_clean
        or readback.reviewer != verified_reviewer
    ):
        log.error("feedback_readback_mismatch", readback=readback, expected=record)
        raise FeedbackPersistenceError(
            f"Readback verification mismatch: persisted feedback data differs from requested payload."
        )

    # 8. Recommendation Immutability Verification
    # Ensure that recording feedback did NOT mutate the recommendation itself
    rec_after_write = repository.get_recommendation(rec_id_clean, active_tenant)
    if not rec_after_write or _compute_rec_state_hash(rec_after_write) != rec_hash_before:
        log.critical("recommendation_immutability_violation", rec_id=rec_id_clean)
        raise FeedbackPersistenceError(
            f"Integrity violation: recommendation '{rec_id_clean}' attributes mutated during feedback write."
        )

    # 9. Dataverse Audit Logging
    audit_svc = audit_service or get_productivity_audit_service()
    audit_status = "PERSISTED"
    try:
        audit_rec = DataverseAuditRecord(
            record_type=RECORD_TYPE_TOOL_EXECUTION_END,
            root_correlation_id=corr_id,
            conversation_id=conversation_id or "",
            turn_id=turn_id or "",
            invocation_id=f"fb-{feedback_id}",
            idempotency_key=idempotency_key or feedback_id,
            user_object_id=user_object_id or (verified_identity.object_id if verified_identity else ""),
            user_email=verified_reviewer,
            calling_agent="Velora Copilot Studio Parent",
            executing_agent="Velora Productivity Agent",
            agent_name="Velora Productivity Agent",
            agent_version="1.0.0",
            environment=os.getenv("DATAVERSE_ENVIRONMENT", "PROD"),
            capability="RecommendationFeedback",
            operation="RECORD_RECOMMENDATION_FEEDBACK",
            transaction_type="FEEDBACK_WRITE",
            source_system="Velora_RecommendationEngine",
            message_summary=f"Feedback recorded for {rec_id_clean}: is_useful={is_useful}, type={fb_type_clean}",
            audit_detail=json.dumps({
                "feedback_id": feedback_id,
                "recommendation_id": rec_id_clean,
                "is_useful": is_useful,
                "feedback_type": fb_type_clean,
                "comment_length": len(comment_clean),
                "rule_code": target_rec.rule_code,
                "kpi_code": target_rec.kpi_code,
            }),
        )
        res = await audit_svc.dv_client.create_audit_record(audit_rec)
        if isinstance(res, dict) and res.get("status") == "FAIL_CLOSED_BLOCKED":
            audit_status = "FAIL_CLOSED_BLOCKED"
    except Exception as audit_err:
        log.warning("feedback_audit_warn", error=str(audit_err))
        audit_status = "BUFFERED"

    return {
        "status": "PERSISTED",
        "feedbackId": feedback_id,
        "recommendationId": rec_id_clean,
        "reviewer": verified_reviewer,
        "isUseful": is_useful,
        "feedbackType": fb_type_clean,
        "comment": comment_clean,
        "recordedAt": now_iso,
        "isDuplicate": False,
        "correlationId": corr_id,
        "auditStatus": audit_status,
        "message": "Feedback recorded and verified successfully.",
    }


def get_recommendation_feedback(
    feedback_id: str,
    tenant_id: str = "velora-tenant",
    db_path: Optional[str] = None,
    repo: Optional[SqliteBusinessRepository] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve single feedback record by feedback_id and tenant_id."""
    repository = repo or get_business_repository_client(db_path=db_path)
    fb = repository.get_recommendation_feedback(feedback_id, tenant_id)
    if not fb:
        return None
    return {
        "feedbackId": fb.feedback_id,
        "recommendationId": fb.recommendation_id,
        "reviewer": fb.reviewer,
        "isUseful": fb.is_useful,
        "feedbackType": fb.feedback_type,
        "comment": fb.comment,
        "recordedAt": fb.recorded_at,
        "tenantId": fb.tenant_id,
    }


def list_feedback_for_recommendation(
    recommendation_id: str,
    tenant_id: str = "velora-tenant",
    db_path: Optional[str] = None,
    repo: Optional[SqliteBusinessRepository] = None,
) -> List[Dict[str, Any]]:
    """List all feedback recorded for a specific recommendation."""
    repository = repo or get_business_repository_client(db_path=db_path)
    items = repository.list_feedback_for_recommendation(recommendation_id, tenant_id)
    return [
        {
            "feedbackId": it.feedback_id,
            "recommendationId": it.recommendation_id,
            "reviewer": it.reviewer,
            "isUseful": it.is_useful,
            "feedbackType": it.feedback_type,
            "comment": it.comment,
            "recordedAt": it.recorded_at,
            "tenantId": it.tenant_id,
        }
        for it in items
    ]


def get_rule_feedback_summary(
    rule_code: str,
    tenant_id: str = "velora-tenant",
    db_path: Optional[str] = None,
    repo: Optional[SqliteBusinessRepository] = None,
) -> Dict[str, Any]:
    """Provide rule-level feedback aggregation statistics without automated model retuning.
    
    Used strictly for human review, governance dashboards, and offline evaluation.
    """
    repository = repo or get_business_repository_client(db_path=db_path)
    summary = repository.get_feedback_summary_by_rule(rule_code, tenant_id)
    return {
        "status": "SUCCESS",
        "ruleCode": summary.get("rule_code", rule_code),
        "tenantId": summary.get("tenant_id", tenant_id),
        "totalFeedback": summary.get("total_feedback", 0),
        "usefulCount": summary.get("useful_count", 0),
        "notUsefulCount": summary.get("not_useful_count", 0),
        "usefulRatio": summary.get("useful_ratio", 0.0),
        "feedbackTypeBreakdown": summary.get("feedback_type_breakdown", {}),
        "requiresHumanReview": True,
        "automatedRetuningApplied": False,
    }
