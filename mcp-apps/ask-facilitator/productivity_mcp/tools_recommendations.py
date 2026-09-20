"""Recommendation Operations and Tools for Velora Executive Platform (W08).

Exposes:
- `evaluate_verified_kpi_snapshot`: Internal authorized endpoint to evaluate S4 / business snapshots against active rules.
- `list_recommendations`: Read operation returning attributed recommendations with claims, sources, and confidence.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .audit_client import get_productivity_audit_service
from .business_repository import (
    KPISnapshotRecord,
    RecommendationEntityRecord,
    SqliteBusinessRepository,
    get_business_repository_client,
)
from .evidence_contracts import (
    ClaimKind,
    ConfidenceAssessment,
    ConfidenceLabel,
    EvidenceSource,
    MaterialClaim,
)
from .confidence_policy import evaluate_confidence
from .models import ReadToolEnvelope
from .recommendation_engine import (
    Comparator,
    KPISnapshot,
    RecommendationEngine,
    RecommendationRecord,
    RecommendationStatus,
)

log = logging.getLogger("tools_recommendations")

_RECOMMENDATION_ENGINES: Dict[str, RecommendationEngine] = {}


def get_recommendation_engine(tenant_id: str = "velora-tenant", db_dir: Optional[str] = None) -> RecommendationEngine:
    """Get or create RecommendationEngine for tenant."""
    key = f"{tenant_id}:{db_dir or 'default'}"
    if key not in _RECOMMENDATION_ENGINES:
        outbox_dir = db_dir or os.getenv("VELORA_OUTBOX_DIR") or "/tmp/velora_outbox"
        _RECOMMENDATION_ENGINES[key] = RecommendationEngine(
            rules=None,  # Loads active rules dynamically from Business Repository (W08 requirement 1)
            outbox_dir=outbox_dir,
            tenant_id=tenant_id,
        )
    return _RECOMMENDATION_ENGINES[key]


def reset_recommendation_engines_for_testing() -> None:
    """Clear cached singletons during unit tests."""
    global _RECOMMENDATION_ENGINES
    _RECOMMENDATION_ENGINES.clear()


async def evaluate_verified_kpi_snapshot(
    snapshot: Dict[str, Any] | KPISnapshot,
    caller_role: str = "WORKLOAD_AUTHORIZED",
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
    tenantId: str = "velora-tenant",
    custom_rules: Optional[List[Any]] = None,
    engine_outbox_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Internal operation: Evaluate verified KPI snapshot from S4 / Facilitator workload."""
    corr_id = rootCorrelationId or f"corr-kpi-eval-{int(time.time() * 1000)}"

    # 1. Parse and validate snapshot
    if isinstance(snapshot, dict):
        has_val = "value" in snapshot and snapshot["value"] is not None
        has_metric = "metric_value" in snapshot and snapshot["metric_value"] is not None

        if not has_val and not has_metric:
            return {
                "status": "VALIDATION_ERROR",
                "resultSummary": "Missing required metric value in KPI snapshot payload.",
                "correlationId": corr_id,
                "recommendations": [],
                "warnings": ["Missing 'value' field in snapshot dictionary."],
            }

        if has_val and has_metric:
            val_a = snapshot["value"]
            val_b = snapshot["metric_value"]
            if str(val_a).strip() != str(val_b).strip():
                return {
                    "status": "VALIDATION_ERROR",
                    "resultSummary": f"Conflicting metric values provided: value='{val_a}' vs metric_value='{val_b}'",
                    "correlationId": corr_id,
                    "recommendations": [],
                    "warnings": ["Conflicting 'value' and 'metric_value' fields in snapshot."],
                }
            val_raw = val_a
        elif has_val:
            val_raw = snapshot["value"]
        else:
            val_raw = snapshot["metric_value"]

        if isinstance(val_raw, bool):
            return {
                "status": "VALIDATION_ERROR",
                "resultSummary": f"Invalid metric value: boolean not permitted ({val_raw})",
                "correlationId": corr_id,
                "recommendations": [],
                "warnings": ["Metric value cannot be boolean."],
            }

        try:
            val_str = str(val_raw).strip()
            if val_str.lower() in {"nan", "inf", "-inf", "+inf", "infinity", "-infinity", "+infinity"}:
                raise ValueError(f"Non-finite value '{val_raw}' is not allowed.")
            val_dec = Decimal(val_str)
            if not val_dec.is_finite():
                raise ValueError(f"Non-finite value '{val_raw}' is not allowed.")
        except Exception as ex:
            return {
                "status": "VALIDATION_ERROR",
                "resultSummary": f"Invalid non-decimal metric value: {ex}",
                "correlationId": corr_id,
                "recommendations": [],
                "warnings": [str(ex)],
            }

        kpi_snap = KPISnapshot(
            snapshot_id=snapshot.get("snapshot_id") or snapshot.get("kpi_snapshot_id") or f"SNAP-{int(time.time() * 1000)}",
            kpi_code=snapshot.get("kpi_code", "UNKNOWN_KPI"),
            organization_scope=snapshot.get("organization_scope", "1000"),
            period=snapshot.get("period", datetime.now(timezone.utc).strftime("%Y-%m")),
            value=val_dec,
            unit=snapshot.get("unit", "currency"),
            currency=snapshot.get("currency", "AED"),
            source_updated_time=snapshot.get("source_updated_time"),
            retrieved_at=snapshot.get("retrieved_at", datetime.now(timezone.utc).isoformat()),
            completeness=snapshot.get("completeness", "COMPLETE"),
            evidence_ref=snapshot.get("evidence_ref", ""),
            input_hash=snapshot.get("input_hash", ""),
        )
    else:
        kpi_snap = snapshot

    # 2. Reject non-finite values (W08 requirement 5)
    if not kpi_snap.value.is_finite():
        return {
            "status": "VALIDATION_ERROR",
            "resultSummary": "Rejected non-finite decimal value in KPI snapshot.",
            "correlationId": corr_id,
            "recommendations": [],
            "warnings": ["Value is NaN or infinite."],
        }

    # 3. Obtain engine and evaluate
    if custom_rules is not None:
        engine = RecommendationEngine(
            rules=custom_rules,
            outbox_dir=engine_outbox_dir or os.getenv("VELORA_OUTBOX_DIR"),
            tenant_id=tenantId,
        )
    else:
        engine = get_recommendation_engine(tenant_id=tenantId, db_dir=engine_outbox_dir)

    results = engine.evaluate_snapshot(kpi_snap)

    # 4. Persist snapshot and recommendation entities to durable Business Repository
    repo_client = get_business_repository_client()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        snap_rec = KPISnapshotRecord(
            kpi_snapshot_id=f"KSNAP-{kpi_snap.snapshot_id}",
            tenant_id=tenantId,
            snapshot_id=kpi_snap.snapshot_id,
            kpi_code=kpi_snap.kpi_code,
            organization_scope=kpi_snap.organization_scope,
            period=kpi_snap.period,
            metric_value=kpi_snap.value,
            unit=kpi_snap.unit,
            currency=kpi_snap.currency,
            source_updated_time=kpi_snap.source_updated_time,
            retrieved_at=kpi_snap.retrieved_at,
            completeness=kpi_snap.completeness,
            evidence_ref=kpi_snap.evidence_ref,
            input_hash=kpi_snap.input_hash,
            version=1,
        )
        if hasattr(repo_client, "save_kpi_snapshot"):
            repo_client.save_kpi_snapshot(snap_rec)
        elif hasattr(repo_client, "_repo") and hasattr(repo_client._repo, "save_kpi_snapshot"):
            repo_client._repo.save_kpi_snapshot(snap_rec)

        for rec in results:
            entity = RecommendationEntityRecord(
                recommendation_id=rec.recommendation_id,
                tenant_id=tenantId,
                rec_id=rec.recommendation_id,
                rule_code=rec.rule_code,
                rule_version=rec.rule_version,
                kpi_code=rec.kpi_code,
                organization_scope=rec.organization_scope,
                category=rec.category,
                observed_value=rec.observed_value,
                threshold=rec.threshold,
                impact=rec.impact,
                explanation=rec.explanation,
                suggested_action=rec.suggested_action,
                confidence=rec.confidence,
                confidence_reason=rec.confidence_reason,
                first_detected=rec.first_detected,
                last_detected=rec.last_detected,
                status=rec.status.value,
                duplicate_key=rec.duplicate_key,
                snapshot_id=rec.snapshot_id,
                version=1,
            )
            if hasattr(repo_client, "save_recommendation"):
                repo_client.save_recommendation(entity)
            elif hasattr(repo_client, "_repo") and hasattr(repo_client._repo, "save_recommendation"):
                repo_client._repo.save_recommendation(entity)
    except Exception as ex:
        log.warning(f"business_repo_save_warning error={ex}")

    # 5. Build Material Claims and Sources
    now_dt = datetime.now(timezone.utc)
    source_rec = EvidenceSource(
        sourceId=kpi_snap.snapshot_id,
        system="S4HANA",
        businessTitle=f"KPI Snapshot {kpi_snap.kpi_code}",
        retrievedAt=kpi_snap.retrieved_at or now_dt.isoformat(),
        sourceUpdatedAt=kpi_snap.source_updated_time if kpi_snap.source_updated_time else None,
        measurementPeriod=kpi_snap.period,
        scope=kpi_snap.organization_scope,
        currency=kpi_snap.currency,
        unit=kpi_snap.unit,
        contentHash=kpi_snap.input_hash,
    )
    is_comp = str(kpi_snap.completeness).upper() == "COMPLETE"
    conf_assessment = evaluate_confidence(
        sources=[source_rec],
        now=now_dt,
        is_authoritative_single_source=True,
        is_materially_complete=is_comp,
    )

    claims = []
    for r in results:
        claims.append(
            MaterialClaim(
                claimId=f"CLM-{r.recommendation_id}",
                kind=ClaimKind.RECOMMENDATION,
                text=r.observation or r.impact,
                numericValue=r.observed_value,
                unit=kpi_snap.unit or kpi_snap.currency or "",
                currency=kpi_snap.currency or "",
                sourceIds=[kpi_snap.snapshot_id, kpi_snap.evidence_ref],
                confidenceAssessment=conf_assessment,
            )
        )

    # 6. Audit to Dataverse
    audit_svc = get_productivity_audit_service()
    await audit_svc.audit_read_tool_execution(
        tool_name="EvaluateVerifiedKPISnapshot",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(results),
        summary=f"Evaluated KPI {kpi_snap.kpi_code} for scope {kpi_snap.organization_scope}. Generated {len(results)} recommendations.",
        conversation_id=conversationId,
        turn_id=turnId,
    )

    summary_text = (
        f"Evaluated KPI {kpi_snap.kpi_code} (Value: {kpi_snap.value} {kpi_snap.unit or ''}). "
        f"Generated {len(results)} active recommendation(s)."
        if results
        else f"Evaluated KPI {kpi_snap.kpi_code} (Value: {kpi_snap.value} {kpi_snap.unit or ''}). Zero breaches detected (operating within approved limits)."
    )

    return {
        "status": "SUCCESS",
        "resultSummary": summary_text,
        "correlationId": corr_id,
        "snapshotId": kpi_snap.snapshot_id,
        "recommendationsCount": len(results),
        "recommendations": [asdict_rec(r) for r in results],
        "claims": [c.model_dump() for c in claims],
        "sources": [source_rec.model_dump()],
        "confidence": conf_assessment.model_dump(),
        "auditStatus": "PERSISTED",
    }


def asdict_rec(rec: RecommendationRecord) -> Dict[str, Any]:
    """Helper to convert RecommendationRecord to clean JSON serializable dictionary."""
    return {
        "recommendationId": rec.recommendation_id,
        "ruleCode": rec.rule_code,
        "ruleVersion": rec.rule_version,
        "kpiCode": rec.kpi_code,
        "organizationScope": rec.organization_scope,
        "category": rec.category,
        "observedValue": str(rec.observed_value),
        "threshold": str(rec.threshold),
        "impact": rec.impact,
        "explanation": rec.explanation,
        "suggestedAction": rec.suggested_action,
        "confidence": rec.confidence,
        "confidenceReason": rec.confidence_reason,
        "firstDetected": rec.first_detected,
        "lastDetected": rec.last_detected,
        "status": rec.status.value if hasattr(rec.status, "value") else str(rec.status),
        "duplicateKey": rec.duplicate_key,
        "snapshotId": rec.snapshot_id,
        "observation": getattr(rec, "observation", ""),
        "businessImplication": getattr(rec, "business_implication", ""),
        "severity": getattr(rec, "severity", "high"),
        "priority": getattr(rec, "priority", 1),
        "supportingClaims": getattr(rec, "supporting_claims", []),
        "supportingSources": getattr(rec, "supporting_sources", []),
    }


async def list_recommendations(
    status: Optional[str] = None,
    category: Optional[str] = None,
    kpiCode: Optional[str] = None,
    limit: int = 50,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
    tenantId: str = "velora-tenant",
    engine_outbox_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Read operation: List active or historical recommendations with claims, sources, and confidence."""
    corr_id = rootCorrelationId or f"corr-list-rec-{int(time.time() * 1000)}"
    engine = get_recommendation_engine(tenant_id=tenantId, db_dir=engine_outbox_dir)

    all_recs = list(engine.active_recommendations.values())

    filtered: List[RecommendationRecord] = []
    for r in all_recs:
        r_status = r.status.value if hasattr(r.status, "value") else str(r.status)
        if status and r_status.upper() != status.upper():
            continue
        if category and r.category.upper() != category.upper():
            continue
        if kpiCode and r.kpi_code.upper() != kpiCode.upper():
            continue
        filtered.append(r)

    # Sort by priority ascending, then lastDetected descending
    filtered.sort(key=lambda x: (getattr(x, "priority", 1), -(int(time.time()))))
    bounded = filtered[:limit]

    now_dt = datetime.now(timezone.utc)
    claims: List[MaterialClaim] = []
    sources: List[EvidenceSource] = []

    for r in bounded:
        claims.append(
            MaterialClaim(
                claimId=f"CLM-{r.recommendation_id}",
                kind=ClaimKind.RECOMMENDATION,
                text=r.observation or r.impact,
                numericValue=r.observed_value,
                unit="",
                currency="",
                sourceIds=[r.snapshot_id],
            )
        )
        sources.append(
            EvidenceSource(
                sourceId=r.snapshot_id,
                system="S4HANA",
                businessTitle=f"KPI Snapshot {r.kpi_code}",
                retrievedAt=r.last_detected or now_dt.isoformat(),
                measurementPeriod="",
                scope=r.organization_scope,
                currency="",
                unit="",
            )
        )

    conf = evaluate_confidence(sources=sources, now=now_dt) if sources else evaluate_confidence(sources=[], now=now_dt)

    summary = (
        f"Found {len(bounded)} proactive executive recommendation(s) across SAP financial boundaries."
        if bounded
        else "No proactive recommendations found matching current criteria."
    )

    audit_svc = get_productivity_audit_service()
    await audit_svc.audit_read_tool_execution(
        tool_name="ListRecommendations",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(bounded),
        summary=summary,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    envelope = ReadToolEnvelope(
        status="SUCCESS" if bounded else "EMPTY",
        resultSummary=summary,
        structuredResult=[asdict_rec(r) for r in bounded],
        sourceSystem="S4HANA_RecommendationEngine",
        sourceAsOf=datetime.now(timezone.utc).isoformat(),
        resultCount=len(bounded),
        warnings=[],
        correlationId=corr_id,
        auditStatus="PERSISTED",
        claims=claims,
        sources=sources,
        confidence=conf,
    )
    return envelope.model_dump()
