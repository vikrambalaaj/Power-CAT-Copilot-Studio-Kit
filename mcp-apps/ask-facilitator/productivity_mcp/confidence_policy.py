"""Confidence Assessment Policy v1 — Velora Executive Agent Platform.

Deterministic, evidence-grounded confidence evaluation adhering to strict conservative rules.
Zero LLM self-grading: confidence is evaluated strictly from observed source timeliness,
completeness, corroboration, definition compatibility, and source SLAs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from .evidence_contracts import (
    ConfidenceAssessment,
    ConfidenceLabel,
    EvidenceSource,
    MaterialClaim,
)

# Hierarchy ranking for weakest-link derivation: lower index = weaker confidence
LABEL_RANKS = {
    ConfidenceLabel.UNASSESSED: 0,
    ConfidenceLabel.LOW: 1,
    ConfidenceLabel.MEDIUM: 2,
    ConfidenceLabel.HIGH: 3,
}
RANK_TO_LABEL = {v: k for k, v in LABEL_RANKS.items()}


def parse_iso_timestamp(ts: Optional[str]) -> Optional[datetime]:
    """Safely parse ISO timestamp with timezone support."""
    if not ts:
        return None
    try:
        # Handle trailing Z
        clean = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def evaluate_confidence(
    sources: List[EvidenceSource],
    now: Optional[datetime] = None,
    source_sla_hours: float = 24.0,
    required_corroboration: int = 1,
    is_authoritative_single_source: bool = False,
    is_definition_compatible: bool = True,
    has_conflicts: bool = False,
    is_materially_complete: bool = True,
    limiting_factors_override: Optional[List[str]] = None,
) -> ConfidenceAssessment:
    """Pure, clock-injected deterministic confidence assessment v1.

    Rules:
    - UNASSESSED when no valid sources or assessment cannot be made.
    - LOW when evidence is stale beyond SLA, materially incomplete, conflicting without resolution,
      or definitions are noncomparable.
    - HIGH only when required inputs are verified, sufficiently complete, fresh within SLA,
      applicable definitions agree, and required corroboration is satisfied (or authoritative single source).
    - Otherwise MEDIUM.
    """
    evaluation_time = now or datetime.now(timezone.utc)
    limiting_factors: List[str] = list(limiting_factors_override or [])

    if not sources:
        return ConfidenceAssessment(
            label=ConfidenceLabel.UNASSESSED,
            frameworkVersion="v1.0",
            sourceReliability="UNVERIFIED",
            corroboration="NONE",
            timeliness="UNKNOWN",
            completeness="EMPTY",
            comparability="UNKNOWN",
            reason="No underlying evidence sources provided for assessment.",
            limitingFactors=["NO_SOURCES_PROVIDED"],
        )

    # 1. Evaluate Source Reliability
    systems = {s.system.upper() for s in sources}
    if is_authoritative_single_source or any(sys in ("S4HANA", "SUCCESSFACTORS", "DATAVERSE") for sys in systems):
        source_reliability = "AUTHORITATIVE"
    elif any(sys in ("OUTLOOK", "TEAMS", "PLANNER") for sys in systems):
        source_reliability = "PRIMARY_M365"
    else:
        source_reliability = "SECONDARY"

    # 2. Evaluate Corroboration
    distinct_sources_count = len(sources)
    if distinct_sources_count >= max(2, required_corroboration):
        corroboration = "MULTI_SOURCE_CONFIRMED"
    elif distinct_sources_count >= required_corroboration or is_authoritative_single_source:
        corroboration = "SATISFIED"
    else:
        corroboration = "SINGLE_SOURCE_UNCORROBORATED"
        limiting_factors.append("INSUFFICIENT_CORROBORATION")

    # 3. Evaluate Timeliness & Freshness SLA
    stale_count = 0
    unknown_update_time_count = 0
    fresh_count = 0

    for src in sources:
        # Crucial invariant: sourceUpdatedAt=None means source update time is unknown.
        # Retrieval time CANNOT prove source freshness.
        updated_dt = parse_iso_timestamp(src.sourceUpdatedAt)
        if updated_dt is None:
            unknown_update_time_count += 1
        else:
            age_hours = (evaluation_time - updated_dt).total_seconds() / 3600.0
            if age_hours > source_sla_hours:
                stale_count += 1
            else:
                fresh_count += 1

    if stale_count > 0:
        timeliness = "STALE_EXCEEDS_SLA"
        limiting_factors.append(f"{stale_count}_SOURCES_EXCEED_SLA")
    elif unknown_update_time_count == len(sources):
        timeliness = "UNVERIFIED_SOURCE_UPDATE_TIME"
        limiting_factors.append("SOURCE_UPDATE_TIME_UNKNOWN")
    elif unknown_update_time_count > 0:
        timeliness = "PARTIALLY_VERIFIED"
        limiting_factors.append("PARTIAL_SOURCE_TIMESTAMP_COVERAGE")
    else:
        timeliness = "FRESH_WITHIN_SLA"

    # 4. Evaluate Completeness
    if not is_materially_complete:
        completeness = "INCOMPLETE"
        limiting_factors.append("MATERIAL_EXTRACTION_GAPS")
    elif any(src.limitations for src in sources):
        completeness = "BOUNDED_WITH_LIMITATIONS"
        for src in sources:
            limiting_factors.extend(src.limitations)
    else:
        completeness = "COMPLETE"

    # 5. Evaluate Comparability & Conflicts
    if not is_definition_compatible:
        comparability = "NON_COMPARABLE_DEFINITIONS"
        limiting_factors.append("NON_COMPARABLE_DEFINITIONS")
    elif has_conflicts:
        comparability = "CONFLICTING_INPUTS"
        limiting_factors.append("UNRESOLVED_DATA_CONFLICT")
    else:
        comparability = "COMPATIBLE"

    # Deduplicate limiting factors preserving order
    deduped_limiting_factors: List[str] = []
    for factor in limiting_factors:
        if factor not in deduped_limiting_factors:
            deduped_limiting_factors.append(factor)

    # 6. Determine Deterministic Label
    # Any critical flaw forces LOW confidence
    critical_flaws = {
        "STALE_EXCEEDS_SLA",
        "MATERIAL_EXTRACTION_GAPS",
        "NON_COMPARABLE_DEFINITIONS",
        "UNRESOLVED_DATA_CONFLICT",
    }
    has_critical_flaw = (
        timeliness == "STALE_EXCEEDS_SLA"
        or any(flaw in deduped_limiting_factors for flaw in critical_flaws)
        or any("EXCEED_SLA" in factor for factor in deduped_limiting_factors)
    )

    if has_critical_flaw:
        label = ConfidenceLabel.LOW
        reason = f"Confidence is LOW due to critical constraints: {', '.join(deduped_limiting_factors)}."
    elif (
        source_reliability == "AUTHORITATIVE"
        and timeliness == "FRESH_WITHIN_SLA"
        and completeness == "COMPLETE"
        and comparability == "COMPATIBLE"
        and (corroboration == "SATISFIED" or corroboration == "MULTI_SOURCE_CONFIRMED")
    ):
        label = ConfidenceLabel.HIGH
        reason = "Confidence is HIGH: Verified authoritative source, fresh within SLA, complete coverage, and compatible definitions."
    else:
        label = ConfidenceLabel.MEDIUM
        reason = f"Confidence is MEDIUM: Operable evidence with noted factors: {', '.join(deduped_limiting_factors) or 'General secondary observation'}."

    return ConfidenceAssessment(
        label=label,
        frameworkVersion="v1.0",
        sourceReliability=source_reliability,
        corroboration=corroboration,
        timeliness=timeliness,
        completeness=completeness,
        comparability=comparability,
        reason=reason,
        limitingFactors=deduped_limiting_factors,
    )


def derive_composite_confidence(assessments: List[ConfidenceAssessment]) -> ConfidenceAssessment:
    """Derive composite decision confidence applying the weakest-link principle.

    Derived decision confidence cannot exceed the weakest material input required
    to support the recommendation.
    """
    if not assessments:
        return ConfidenceAssessment(
            label=ConfidenceLabel.UNASSESSED,
            frameworkVersion="v1.0",
            sourceReliability="NONE",
            corroboration="NONE",
            timeliness="UNKNOWN",
            completeness="EMPTY",
            comparability="UNKNOWN",
            reason="No input claim assessments provided to derive composite confidence.",
            limitingFactors=["NO_INPUT_ASSESSMENTS"],
        )

    min_rank = min(LABEL_RANKS[a.label] for a in assessments)
    weakest_label = RANK_TO_LABEL[min_rank]

    all_limiting_factors: List[str] = []
    for a in assessments:
        for factor in a.limitingFactors:
            if factor not in all_limiting_factors:
                all_limiting_factors.append(factor)

    weakest_reasons = [a.reason for a in assessments if a.label == weakest_label]

    return ConfidenceAssessment(
        label=weakest_label,
        frameworkVersion="v1.0",
        sourceReliability="COMPOSITE",
        corroboration="COMPOSITE",
        timeliness="COMPOSITE",
        completeness="COMPOSITE",
        comparability="COMPOSITE",
        reason=f"Composite confidence limited to {weakest_label.value} by weakest supporting claim: {weakest_reasons[0]}",
        limitingFactors=all_limiting_factors,
    )
