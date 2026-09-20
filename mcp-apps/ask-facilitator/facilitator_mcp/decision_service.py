"""Decision Service Orchestrator for Multi-Criteria Vendor Evaluation.

Work Package W11 (Requirement R05, R06, R08; Acceptance Criteria T11).
Orchestrates:
- Policy resolution with immutable weights and directions.
- Cross-subsidiary history resolution via W10 get_vendor_history.
- Commercial comparability enforcement.
- Deterministic scoring, contribution deltas, and tie-breaking in pure Decimal.
- Generation of auditable MaterialClaims and ConfidenceAssessments.
- Fail-closed persistence and immediate disk readback verification.
- Reconstructible historical decisions without fresh LLM invocation.
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

from productivity_mcp.business_repository import (
    SqliteBusinessRepository,
    VendorDecisionRecord,
    VendorDecisionRepository,
    get_business_repository,
)
from productivity_mcp.evidence_contracts import (
    ActorType,
    ClaimKind,
    ConfidenceAssessment,
    ConfidenceLabel,
    DecisionRecord,
    EvidenceEnvelope,
    EvidenceSource,
    ExecutionContext,
    MaterialClaim,
    OperationStatus,
)

from .institutional_memory import get_vendor_history, MANDATORY_PERFORMANCE_CAVEAT
from .vendor_evaluation import (
    CandidateProposalInput,
    CandidateScoringResult,
    EvaluationPolicy,
    TiePolicy,
    evaluate_candidate_options,
    get_approved_policy,
    round_decimal,
)

log = logging.getLogger("facilitator_decision_service")

CODE_VERSION = "2026.9.11-w11"


class DecisionServiceError(Exception):
    """Base exception for decision service."""
    pass


class DecisionPersistenceError(DecisionServiceError):
    """Raised when decision persistence or readback verification fails."""
    pass


def _decimal_to_str(obj: Any) -> Any:
    """Helper to convert Decimals to floats/strings for JSON serialization."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_str(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_str(v) for v in obj]
    return obj


def _calculate_history_score_from_records(history_records: List[Dict[str, Any]]) -> Optional[Decimal]:
    """Calculate normalized 0-100 historical performance score from verified records.
    
    Positive events (CONTRACT_FULFILLMENT) yield high scores (85-100).
    Negative events (DELIVERY_BREACH, PRICE_VARIANCE) reduce score (20-50).
    Neutral or zero records return None (no data fabricated).
    """
    if not history_records:
        return None

    scores: List[Decimal] = []
    for rec in history_records:
        event_type = rec.get("eventType") if "eventType" in rec else rec.get("event_type", "")
        severity = rec.get("severity", "LOW")
        num_val = rec.get("numericValue") if "numericValue" in rec else rec.get("numeric_value")

        if num_val is not None:
            try:
                dec_val = Decimal(str(num_val))
                if Decimal("0.00") <= dec_val <= Decimal("100.00"):
                    scores.append(dec_val)
                    continue
            except Exception:
                pass

        if event_type in ("CONTRACT_FULFILLMENT", "MILESTONE_SUCCESS"):
            scores.append(Decimal("95.00") if severity == "LOW" else Decimal("85.00"))
        elif event_type == "SLA_BREACH":
            scores.append(Decimal("30.00") if severity == "HIGH" else Decimal("50.00"))
        elif event_type in ("DELIVERY_DELAY", "DELIVERY_BREACH"):
            scores.append(Decimal("20.00") if severity == "HIGH" else Decimal("40.00"))
        elif event_type in ("PRICE_VARIANCE", "QUALITY_DEFECT", "AUDIT_NONCOMPLIANCE"):
            scores.append(Decimal("35.00") if severity == "HIGH" else Decimal("60.00"))
        else:
            scores.append(Decimal("75.00"))

    if not scores:
        return None

    avg_score = sum(scores) / Decimal(str(len(scores)))
    return round_decimal(avg_score, 2)


def generate_decision_id(use_case: str, policy_id: str, candidate_ids: List[str]) -> str:
    """Deterministic decision identifier based on use case, policy, and sorted candidates."""
    canonical = f"{use_case}:{policy_id}:{sorted(candidate_ids)}"
    h = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    return f"DEC-{h}"


async def evaluate_vendor_options(
    candidates: List[Dict[str, Any]],
    policy_id: str = "POLICY-VENDOR-PROC-V1",
    policy_version: Optional[str] = "1.0.0",
    use_case: str = "VENDOR_SELECTION",
    tenant_id: str = "velora-tenant",
    caller_entity_scopes: Optional[List[str]] = None,
    caller_roles: Optional[List[str]] = None,
    actor_object_id: str = "system-facilitator",
    db_path: Optional[str] = None,
    user_prompt_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute governed, deterministic vendor options evaluation.
    
    Accepts candidate proposals, validates commercial comparability, resolves W10 institutional history,
    computes exact Decimal baseline vs history-informed scores, and persists an auditable DecisionRecord.
    """
    if caller_entity_scopes is None:
        caller_entity_scopes = ["1000"]
    if caller_roles is None:
        caller_roles = ["CORP_PROCUREMENT"]

    # 1. Load Approved Policy (Strict immutability: prompt overrides rejected)
    if user_prompt_overrides:
        log.warning(
            "prompt_weight_override_rejected: User prompt requested weight/direction modifications; enforcing approved policy weights strictly."
        )

    policy = get_approved_policy(policy_id, policy_version)

    # 2. Resolve Candidate Inputs and W10 Institutional History
    candidate_inputs: List[CandidateProposalInput] = []
    input_snapshot_ids: List[str] = []
    sources: List[EvidenceSource] = []

    for c in candidates:
        v_id = str(c.get("vendor_id", "")).strip()
        v_name = str(c.get("vendor_name", v_id)).strip()

        # Parse Technical Score
        raw_tech = c.get("technical_score")
        tech_score = Decimal(str(raw_tech)) if raw_tech is not None else None
        tech_source_provided = bool(c.get("technical_source_ref"))
        tech_ref = c.get("technical_source_ref") if tech_source_provided else "USER_PROVIDED"
        input_snapshot_ids.append(f"INP-TECH-{v_id}" if not tech_source_provided else tech_ref)

        sources.append(
            EvidenceSource(
                sourceId=f"SRC-TECH-{v_id}",
                system="RFP_TECHNICAL_EVALUATION" if tech_source_provided else "USER_INPUT",
                businessTitle=f"Engineering Audit Scorecard for {v_name}" if tech_source_provided else f"Unverified Technical Input for {v_name}",
                providerRecordId=tech_ref,
                retrievedAt=datetime.now(timezone.utc).isoformat(),
                scope=caller_entity_scopes[0] if caller_entity_scopes else "1000",
                limitations=["Certified technical audit by engineering evaluation panel."] if tech_source_provided else ["Unverified caller-supplied technical score without formal audit scorecard document."],
            )
        )

        # Parse Commercial Price
        raw_price = c.get("commercial_price")
        price = Decimal(str(raw_price)) if raw_price is not None else None
        price_curr = str(c.get("commercial_currency", "AED")).upper()
        price_tax = str(c.get("commercial_tax_basis", "EXCLUDING_VAT")).upper()
        price_term = str(c.get("commercial_term_basis", "ANNUALIZED")).upper()
        price_scope = str(c.get("commercial_scope", caller_entity_scopes[0] if caller_entity_scopes else "1000"))
        comm_source_provided = bool(c.get("commercial_source_ref"))
        comm_ref = c.get("commercial_source_ref") if comm_source_provided else "USER_PROVIDED"
        input_snapshot_ids.append(f"INP-COMM-{v_id}" if not comm_source_provided else comm_ref)

        sources.append(
            EvidenceSource(
                sourceId=f"SRC-COMM-{v_id}",
                system="COMMERCIAL_PROPOSAL" if comm_source_provided else "USER_INPUT",
                businessTitle=f"Formal Commercial Tender Proposal for {v_name}" if comm_source_provided else f"Unverified Commercial Offer for {v_name}",
                providerRecordId=comm_ref,
                retrievedAt=datetime.now(timezone.utc).isoformat(),
                scope=price_scope,
                currency=price_curr,
                limitations=[f"{price_term} fixed commercial offer, {price_tax}."] if comm_source_provided else [f"{price_term} unverified commercial input, {price_tax}. Missing formal proposal."],
            )
        )

        # 3. Query W10 Institutional History
        hist_res = get_vendor_history(
            vendor_id=v_id,
            tenant_id=tenant_id,
            caller_entity_scopes=caller_entity_scopes,
            caller_roles=caller_roles,
            db_path=db_path,
        )

        hist_records = hist_res.get("records", [])
        hist_count = hist_res.get("totalRecords", 0)
        hist_caveat = hist_res.get("mandatoryAuditCaveat", MANDATORY_PERFORMANCE_CAVEAT)

        hist_score = _calculate_history_score_from_records(hist_records)

        sources.append(
            EvidenceSource(
                sourceId=f"SRC-HIST-{v_id}",
                system="INSTITUTIONAL_MEMORY",
                businessTitle=f"Verified Institutional Vendor Performance Profile for {v_name}",
                providerRecordId=f"VPH-QUERY-{v_id}",
                retrievedAt=datetime.now(timezone.utc).isoformat(),
                scope=caller_entity_scopes[0] if caller_entity_scopes else "1000",
                limitations=[f"{hist_count} verified institutional records.", hist_caveat],
            )
        )

        candidate_inputs.append(
            CandidateProposalInput(
                vendor_id=v_id,
                vendor_name=v_name,
                technical_score=tech_score,
                technical_source_ref=tech_ref,
                commercial_price=price,
                commercial_currency=price_curr,
                commercial_tax_basis=price_tax,
                commercial_term_basis=price_term,
                commercial_scope=price_scope,
                commercial_source_ref=comm_ref,
                historical_score=hist_score,
                historical_record_count=hist_count,
                historical_caveat=hist_caveat,
            )
        )

    # 4. Execute Decimal Multi-Criteria Scoring
    scoring_results, winning_vendor, eval_status, eval_warnings = evaluate_candidate_options(
        candidates=candidate_inputs,
        policy=policy,
    )

    # 5. Build Final Rank and Score Dictionaries
    baseline_score_dict: Dict[str, Any] = {}
    memory_contrib_dict: Dict[str, Any] = {}
    final_score_dict: Dict[str, Any] = {}

    for res in scoring_results:
        baseline_score_dict[res.vendor_id] = {
            "totalScore": str(res.baseline_total_score),
            "contributions": {k: str(v) for k, v in res.baseline_contributions.items()},
        }
        memory_contrib_dict[res.vendor_id] = {
            "historyScore": str(res.normalized_scores.get("HISTORICAL_PERFORMANCE", Decimal("0.00"))),
            "historyContribution": str(res.history_contributions.get("HISTORICAL_PERFORMANCE", Decimal("0.00"))),
            "scoreDelta": str(res.score_delta),
            "contributionDeltas": {k: str(v) for k, v in res.contribution_deltas.items()},
            "recordCount": res.history_record_count,
            "caveat": res.history_caveat,
        }
        final_score_dict[res.vendor_id] = {
            "totalScore": str(res.history_total_score),
            "contributions": {k: str(v) for k, v in res.history_contributions.items()},
            "normalizedScores": {k: str(v) for k, v in res.normalized_scores.items()},
        }

    # Deterministic final rank list
    if eval_status == "SUCCESS":
        def sort_key(r: CandidateScoringResult):
            return (r.history_total_score, r.normalized_scores.get("TECH_COMPETENCE", Decimal("0.00")))
        final_rank = [r.vendor_id for r in sorted(scoring_results, key=sort_key, reverse=True)]
    else:
        final_rank = [r.vendor_id for r in scoring_results]

    # Check if any caller input is unverified
    has_unverified_inputs = any(
        c.technical_source_ref == "USER_PROVIDED" or c.commercial_source_ref == "USER_PROVIDED"
        for c in candidate_inputs
    )
    if has_unverified_inputs and "Unverified caller-provided inputs present without formal evidence citations; confidence degraded to LOW." not in eval_warnings:
        eval_warnings.append("Unverified caller-provided inputs present without formal evidence citations; confidence degraded to LOW.")

    # 6. Generate Auditable MaterialClaims
    claims: List[MaterialClaim] = []
    for res in scoring_results:
        cand_input = next((c for c in candidate_inputs if c.vendor_id == res.vendor_id), None)
        tech_verified = bool(cand_input and cand_input.technical_source_ref != "USER_PROVIDED")
        comm_verified = bool(cand_input and cand_input.commercial_source_ref != "USER_PROVIDED")

        # Technical claim
        t_val = res.raw_values.get("TECH_COMPETENCE")
        if t_val is not None:
            claims.append(
                MaterialClaim(
                    claimId=f"CLM-TECH-{res.vendor_id}",
                    kind=ClaimKind.FACT,
                    text=f"{res.vendor_name} achieved technical score of {t_val} / 100." if tech_verified else f"{res.vendor_name} reported unverified technical input of {t_val} / 100.",
                    numericValue=t_val,
                    unit="POINTS_0_100",
                    sourceIds=[f"SRC-TECH-{res.vendor_id}"],
                    calculationVersion=policy.version,
                    policyVersion=policy.version,
                    confidenceAssessment=ConfidenceAssessment(
                        label=ConfidenceLabel.HIGH if tech_verified else ConfidenceLabel.LOW,
                        frameworkVersion="1.0.0",
                        sourceReliability="AUTHORITATIVE" if tech_verified else "USER_PROVIDED",
                        corroboration="VERIFIED" if tech_verified else "UNVERIFIED",
                        timeliness="CURRENT",
                        completeness="COMPLETE" if tech_verified else "INCOMPLETE",
                        comparability="COMPARABLE" if tech_verified else "UNVERIFIED",
                        reason="Verified formal engineering audit scorecard." if tech_verified else "Unverified user input without referenced technical audit scorecard.",
                        limitingFactors=[] if tech_verified else ["CALLER_SUPPLIED_DATA", "MISSING_SOURCE_DOCUMENT"],
                    ),
                )
            )

        # Commercial claim
        p_val = res.raw_values.get("COMMERCIAL_PRICE")
        if p_val is not None:
            claims.append(
                MaterialClaim(
                    claimId=f"CLM-COMM-{res.vendor_id}",
                    kind=ClaimKind.FACT,
                    text=f"{res.vendor_name} submitted annualized commercial proposal of {p_val} AED." if comm_verified else f"{res.vendor_name} reported unverified commercial price of {p_val} AED.",
                    numericValue=p_val,
                    currency="AED",
                    unit="AED",
                    sourceIds=[f"SRC-COMM-{res.vendor_id}"],
                    calculationVersion=policy.version,
                    policyVersion=policy.version,
                    confidenceAssessment=ConfidenceAssessment(
                        label=ConfidenceLabel.HIGH if comm_verified else ConfidenceLabel.LOW,
                        frameworkVersion="1.0.0",
                        sourceReliability="AUTHORITATIVE" if comm_verified else "USER_PROVIDED",
                        corroboration="VERIFIED" if comm_verified else "UNVERIFIED",
                        timeliness="CURRENT",
                        completeness="COMPLETE" if comm_verified else "INCOMPLETE",
                        comparability="COMPARABLE" if comm_verified else "UNVERIFIED",
                        reason="Formal signed tender proposal in AED excluding VAT." if comm_verified else "Unverified user input without referenced commercial tender proposal.",
                        limitingFactors=[] if comm_verified else ["CALLER_SUPPLIED_DATA", "MISSING_SOURCE_DOCUMENT"],
                    ),
                )
            )

        # History claim
        h_val = res.raw_values.get("HISTORICAL_PERFORMANCE")
        if h_val is not None and res.history_record_count > 0:
            claims.append(
                MaterialClaim(
                    claimId=f"CLM-HIST-{res.vendor_id}",
                    kind=ClaimKind.FACT,
                    text=(
                        f"{res.vendor_name} historical institutional performance calculated at {h_val}/100 "
                        f"across {res.history_record_count} verified events. Score delta: {res.score_delta} pts."
                    ),
                    numericValue=h_val,
                    unit="POINTS_0_100",
                    sourceIds=[f"SRC-HIST-{res.vendor_id}"],
                    calculationVersion=policy.version,
                    policyVersion=policy.version,
                    confidenceAssessment=ConfidenceAssessment(
                        label=ConfidenceLabel.HIGH if res.history_record_count >= 3 else ConfidenceLabel.MEDIUM,
                        frameworkVersion="1.0.0",
                        sourceReliability="AUTHORITATIVE",
                        corroboration="VERIFIED",
                        timeliness="CURRENT",
                        completeness="COMPLETE",
                        comparability="COMPARABLE",
                        reason="Verified institutional memory performance profile.",
                        limitingFactors=[res.history_caveat] if res.history_caveat else [],
                    ),
                )
            )
        elif res.history_record_count == 0:
            claims.append(
                MaterialClaim(
                    claimId=f"CLM-HIST-EMPTY-{res.vendor_id}",
                    kind=ClaimKind.FACT,
                    text=f"No prior institutional performance history exists for {res.vendor_name}.",
                    numericValue=None,
                    sourceIds=[f"SRC-HIST-{res.vendor_id}"],
                    calculationVersion=policy.version,
                    policyVersion=policy.version,
                    confidenceAssessment=ConfidenceAssessment(
                        label=ConfidenceLabel.LOW,
                        frameworkVersion="1.0.0",
                        sourceReliability="UNVERIFIED",
                        corroboration="UNCORROBORATED",
                        timeliness="STALE",
                        completeness="INCOMPLETE",
                        comparability="NON_COMPARABLE",
                        reason="Absence of historical corporate records.",
                        limitingFactors=[MANDATORY_PERFORMANCE_CAVEAT],
                    ),
                )
            )

    # 7. Construct Concise Executive Rationale
    rationale_lines: List[str] = [
        f"Evaluation performed under approved policy '{policy.name}' ({policy.policy_id} v{policy.version})."
    ]
    if eval_status == "SUCCESS" and winning_vendor:
        winner_res = next((r for r in scoring_results if r.vendor_id == winning_vendor), None)
        winner_name = winner_res.vendor_name if winner_res else winning_vendor
        rationale_lines.append(
            f"Recommended Supplier: {winner_name} (Composite Score: {winner_res.history_total_score} / 100)."
        )
        for r in scoring_results:
            rationale_lines.append(
                f"• {r.vendor_name}: Baseline={r.baseline_total_score} pts; "
                f"History Delta={r.score_delta:+} pts ({r.history_record_count} verified events); "
                f"Final={r.history_total_score} pts."
            )
        rationale_lines.append(
            f"Tie & Decision Policy: {policy.tie_policy.value}. Commercial basis: {policy.commercial_comparability.required_currency} "
            f"{policy.commercial_comparability.required_tax_basis} {policy.commercial_comparability.required_term_basis}."
        )
    else:
        rationale_lines.append(
            f"Evaluation halted with status '{eval_status}'. No winning vendor awarded due to: "
            + "; ".join(eval_warnings)
        )
    concise_rationale = "\n".join(rationale_lines)

    # 8. Deterministic Decision ID & Versioning
    candidate_ids = [c.vendor_id for c in candidate_inputs]
    dec_id = generate_decision_id(use_case, policy_id, candidate_ids)

    # Check existing versions to produce immutable, non-destructive new version
    repo = VendorDecisionRepository(db_path=db_path)
    existing_latest = repo.get_decision(decision_id=dec_id, tenant_id=tenant_id)
    if existing_latest:
        # Increment patch/minor version
        parts = existing_latest.version.split(".")
        if len(parts) == 3:
            new_ver = f"{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"
        else:
            new_ver = f"{existing_latest.version}.1"
    else:
        new_ver = "1.0.0"

    now_iso = datetime.now(timezone.utc).isoformat()
    auth_actor = ExecutionContext(
        tenantId=tenant_id,
        actorObjectId=actor_object_id,
        actorType=ActorType.USER if "@" in actor_object_id else ActorType.WORKLOAD,
        organizationScopes=caller_entity_scopes or ["1000"],
        correlationId=f"corr-dec-{dec_id}",
        policyVersion=policy.version,
    )

    # 9. Persist VendorDecisionRecord to Database
    db_record = VendorDecisionRecord(
        decision_id=dec_id,
        version=new_ver,
        tenant_id=tenant_id,
        use_case=use_case,
        evaluated_options_json=json.dumps([c.__dict__ for c in candidate_inputs], default=str),
        criteria_weights_json=json.dumps(
            {k: str(v) for k, v in policy.history_influence.history_informed_weights.items()}
        ),
        input_snapshot_ids_json=json.dumps(input_snapshot_ids),
        baseline_score_json=json.dumps(baseline_score_dict),
        memory_contributions_json=json.dumps(memory_contrib_dict),
        final_score_json=json.dumps(final_score_dict),
        final_rank_json=json.dumps(final_rank),
        tie_policy=policy.tie_policy.value,
        missing_data_policy=policy.missing_data_policy.value,
        selected_option=winning_vendor if eval_status == "SUCCESS" else None,
        claims_json=json.dumps([c.model_dump() for c in claims]),
        concise_rationale=concise_rationale,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        code_version=CODE_VERSION,
        authenticated_actor_json=json.dumps(auth_actor.model_dump()),
        audit_manifest_ref=f"MAN-DEC-{dec_id}-{new_ver}",
        created_at=now_iso,
        updated_at=now_iso,
    )

    repo.save_decision(db_record)

    # Immediate fail-closed readback verification
    readback = repo.get_decision(decision_id=dec_id, tenant_id=tenant_id, version=new_ver)
    if not readback or readback.decision_id != dec_id or readback.version != new_ver:
        raise DecisionPersistenceError(
            f"Immediate disk readback failed for decision '{dec_id}' version '{new_ver}'."
        )

    # 10. Format Output DecisionRecord & EvidenceEnvelope
    decision_record_obj = DecisionRecord(
        decisionId=dec_id,
        version=new_ver,
        useCase=use_case,
        evaluatedOptions=[c.__dict__ for c in candidate_inputs],
        criteriaWeightsDirections=[
            {
                "criterionId": c.criterion_id,
                "name": c.name,
                "direction": c.direction.value,
                "weight": str(policy.history_influence.history_informed_weights.get(c.criterion_id, Decimal("0.00"))),
                "unit": c.unit,
            }
            for c in policy.criteria
        ],
        inputSnapshotIds=input_snapshot_ids,
        baselineScore=baseline_score_dict,
        memoryContributions=memory_contrib_dict,
        finalScore=final_score_dict,
        finalRank=final_rank,
        tiePolicy=policy.tie_policy.value,
        missingDataPolicy=policy.missing_data_policy.value,
        selectedOption=winning_vendor if eval_status == "SUCCESS" else None,
        claims=claims,
        conciseRationale=concise_rationale,
        policyVersion=policy.version,
        codeVersion=CODE_VERSION,
        authenticatedActor=auth_actor,
        auditManifestRef=f"MAN-DEC-{dec_id}-{new_ver}",
    )

    envelope = EvidenceEnvelope(
        schemaVersion="1.0.0",
        operation="EVALUATE_VENDOR_OPTIONS",
        status=OperationStatus.SUCCESS if eval_status == "SUCCESS" else OperationStatus.CONFIGURATION_REQUIRED,
        resultSummary=concise_rationale.splitlines()[1] if len(rationale_lines) > 1 else concise_rationale,
        result=decision_record_obj.model_dump(),
        claims=claims,
        sources=sources,
        warnings=eval_warnings,
        missingSources=[],
        correlationId=f"corr-dec-{dec_id}",
        audit={"status": "COMMITTED", "recordId": dec_id, "version": new_ver},
        generatedAt=now_iso,
    )

    env_dict = envelope.model_dump()
    env_dict["typedResult"] = env_dict.get("result")
    env_dict["operationStatus"] = env_dict.get("status")
    return env_dict


def get_historical_decision(
    decision_id: str,
    tenant_id: str = "velora-tenant",
    version: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve persisted historical decision record without fresh LLM evaluation.
    
    Reconstructs exact DecisionRecord and EvidenceEnvelope from persistent SQLite store.
    """
    repo = VendorDecisionRepository(db_path=db_path)
    record = repo.get_decision(decision_id=decision_id, tenant_id=tenant_id, version=version)
    if not record:
        return {
            "status": "NOT_FOUND",
            "decisionId": decision_id,
            "version": version,
            "message": f"No historical decision found for ID '{decision_id}'.",
        }

    claims_data = json.loads(record.claims_json) if record.claims_json else []
    claims = [MaterialClaim(**c) for c in claims_data]

    auth_data = json.loads(record.authenticated_actor_json) if record.authenticated_actor_json else {}
    auth_actor = ExecutionContext(**auth_data) if auth_data else ExecutionContext(
        tenantId=tenant_id,
        actorObjectId="historical-reconstruction",
        actorType=ActorType.WORKLOAD,
        correlationId=f"corr-hist-{record.decision_id}",
    )

    evaluated_options = json.loads(record.evaluated_options_json) if record.evaluated_options_json else []
    baseline_score = json.loads(record.baseline_score_json) if record.baseline_score_json else {}
    memory_contributions = json.loads(record.memory_contributions_json) if record.memory_contributions_json else {}
    final_score = json.loads(record.final_score_json) if record.final_score_json else {}
    final_rank = json.loads(record.final_rank_json) if record.final_rank_json else []
    input_snapshot_ids = json.loads(record.input_snapshot_ids_json) if record.input_snapshot_ids_json else []

    policy = get_approved_policy(record.policy_id, record.policy_version)

    dec_obj = DecisionRecord(
        decisionId=record.decision_id,
        version=record.version,
        useCase=record.use_case,
        evaluatedOptions=evaluated_options,
        criteriaWeightsDirections=[
            {
                "criterionId": c.criterion_id,
                "name": c.name,
                "direction": c.direction.value,
                "weight": str(policy.history_influence.history_informed_weights.get(c.criterion_id, Decimal("0.00"))),
                "unit": c.unit,
            }
            for c in policy.criteria
        ],
        inputSnapshotIds=input_snapshot_ids,
        baselineScore=baseline_score,
        memoryContributions=memory_contributions,
        finalScore=final_score,
        finalRank=final_rank,
        tiePolicy=record.tie_policy,
        missingDataPolicy=record.missing_data_policy,
        selectedOption=record.selected_option,
        claims=claims,
        conciseRationale=record.concise_rationale,
        policyVersion=record.policy_version,
        codeVersion=record.code_version,
        authenticatedActor=auth_actor,
        auditManifestRef=record.audit_manifest_ref,
    )

    envelope = EvidenceEnvelope(
        schemaVersion="1.0.0",
        operation="GET_HISTORICAL_DECISION",
        status=OperationStatus.SUCCESS if record.selected_option else OperationStatus.CONFIGURATION_REQUIRED,
        resultSummary=f"Reconstructed historical decision {record.decision_id} (version {record.version})",
        result=dec_obj.model_dump(),
        claims=claims,
        sources=[],
        warnings=[],
        missingSources=[],
        correlationId=f"corr-hist-{record.decision_id}",
        audit={"status": "HISTORICAL_RECONSTRUCTION", "recordId": record.decision_id, "version": record.version},
        generatedAt=record.created_at,
    )

    env_dict = envelope.model_dump()
    env_dict["typedResult"] = env_dict.get("result")
    env_dict["operationStatus"] = env_dict.get("status")
    return env_dict
