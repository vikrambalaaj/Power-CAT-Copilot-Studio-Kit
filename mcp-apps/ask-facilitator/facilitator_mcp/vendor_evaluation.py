"""Vendor Evaluation Domain Models, Evaluation Policies, and Pure Decimal Scoring Engine.

Work Package W11 (Requirement R05, R06, R08; Acceptance Criteria T11).
Enforces:
- Approved policy immutability: Prompt text cannot overwrite weights or directions.
- Strict commercial comparability (scope, currency, tax basis, duration).
- Deterministic calculation in Decimal with exact contribution breakdown.
- Dual baseline and history-informed evaluation using approved comparison methods.
- Documented tie-breaking and fail-closed missing evidence handling.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class CriterionDirection(str, Enum):
    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"
    LOWER_IS_BETTER = "LOWER_IS_BETTER"


class TiePolicy(str, Enum):
    HIGHER_TECHNICAL_WINS = "HIGHER_TECHNICAL_WINS"
    LOWER_RISK_WINS = "LOWER_RISK_WINS"
    LOWER_PRICE_WINS = "LOWER_PRICE_WINS"
    EARLIEST_PROPOSAL_WINS = "EARLIEST_PROPOSAL_WINS"


class MissingDataPolicy(str, Enum):
    FAIL_CLOSED_NO_WINNER = "FAIL_CLOSED_NO_WINNER"
    EXCLUDE_INCOMPLETE_CANDIDATE = "EXCLUDE_INCOMPLETE_CANDIDATE"


def round_decimal(val: Decimal, places: int = 2) -> Decimal:
    """Round Decimal using ROUND_HALF_UP to exact places."""
    target = Decimal("10") ** (-places)
    return val.quantize(target, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class EvaluationCriterion:
    """Individual scoring criterion within an approved evaluation policy."""
    criterion_id: str
    name: str
    direction: CriterionDirection
    unit: str
    is_mandatory: bool = True
    min_val: Optional[Decimal] = None
    max_val: Optional[Decimal] = None
    description: str = ""


@dataclass(frozen=True)
class CommercialComparabilityBasis:
    """Required parameters for commercial proposals to be comparable."""
    required_currency: str = "AED"
    required_tax_basis: str = "EXCLUDING_VAT"
    required_term_basis: str = "ANNUALIZED"
    required_scope: str = "1000"


@dataclass(frozen=True)
class HistoryInfluencePolicy:
    """Explicit, approved rules for incorporating historical performance."""
    history_criterion_id: str = "HISTORICAL_PERFORMANCE"
    history_weight: Decimal = Decimal("0.20")
    baseline_weights: Dict[str, Decimal] = field(default_factory=lambda: {
        "TECH_COMPETENCE": Decimal("0.50"),
        "COMMERCIAL_PRICE": Decimal("0.50"),
    })
    history_informed_weights: Dict[str, Decimal] = field(default_factory=lambda: {
        "TECH_COMPETENCE": Decimal("0.40"),
        "COMMERCIAL_PRICE": Decimal("0.40"),
        "HISTORICAL_PERFORMANCE": Decimal("0.20"),
    })


@dataclass(frozen=True)
class EvaluationPolicy:
    """Approved evaluation policy with immutable criteria, weights, and comparability rules."""
    policy_id: str
    version: str
    name: str
    description: str
    criteria: List[EvaluationCriterion]
    commercial_comparability: CommercialComparabilityBasis
    history_influence: HistoryInfluencePolicy
    tie_policy: TiePolicy = TiePolicy.HIGHER_TECHNICAL_WINS
    missing_data_policy: MissingDataPolicy = MissingDataPolicy.FAIL_CLOSED_NO_WINNER


# Standard Approved Policy Registry (Input I04 baseline)
_STANDARD_CRITERIA_V1 = [
    EvaluationCriterion(
        criterion_id="TECH_COMPETENCE",
        name="Technical Competence & Capability",
        direction=CriterionDirection.HIGHER_IS_BETTER,
        unit="POINTS_0_100",
        is_mandatory=True,
        min_val=Decimal("0.00"),
        max_val=Decimal("100.00"),
        description="Formal technical evaluation score assessed by engineering audit",
    ),
    EvaluationCriterion(
        criterion_id="COMMERCIAL_PRICE",
        name="Commercial Price",
        direction=CriterionDirection.LOWER_IS_BETTER,
        unit="AED",
        is_mandatory=True,
        description="Annualized contract price excluding VAT in AED",
    ),
    EvaluationCriterion(
        criterion_id="HISTORICAL_PERFORMANCE",
        name="Historical Delivery & Institutional Performance",
        direction=CriterionDirection.HIGHER_IS_BETTER,
        unit="POINTS_0_100",
        is_mandatory=False,
        min_val=Decimal("0.00"),
        max_val=Decimal("100.00"),
        description="Verified past performance records from institutional memory",
    ),
]

POLICY_VENDOR_PROC_V1 = EvaluationPolicy(
    policy_id="POLICY-VENDOR-PROC-V1",
    version="1.0.0",
    name="Standard Technical and Commercial Procurement Policy",
    description="Standard enterprise policy for vendor selection in UAE aviation maintenance.",
    criteria=_STANDARD_CRITERIA_V1,
    commercial_comparability=CommercialComparabilityBasis(
        required_currency="AED",
        required_tax_basis="EXCLUDING_VAT",
        required_term_basis="ANNUALIZED",
        required_scope="1000",
    ),
    history_influence=HistoryInfluencePolicy(
        history_criterion_id="HISTORICAL_PERFORMANCE",
        history_weight=Decimal("0.20"),
        baseline_weights={
            "TECH_COMPETENCE": Decimal("0.50"),
            "COMMERCIAL_PRICE": Decimal("0.50"),
        },
        history_informed_weights={
            "TECH_COMPETENCE": Decimal("0.40"),
            "COMMERCIAL_PRICE": Decimal("0.40"),
            "HISTORICAL_PERFORMANCE": Decimal("0.20"),
        },
    ),
    tie_policy=TiePolicy.HIGHER_TECHNICAL_WINS,
    missing_data_policy=MissingDataPolicy.FAIL_CLOSED_NO_WINNER,
)

APPROVED_POLICY_CATALOGUE: Dict[str, EvaluationPolicy] = {
    "POLICY-VENDOR-PROC-V1": POLICY_VENDOR_PROC_V1,
}


def get_approved_policy(policy_id: str, version: Optional[str] = None) -> EvaluationPolicy:
    """Retrieve approved evaluation policy by ID and version.
    
    Fails closed if policy is unapproved or unrecognized.
    """
    if policy_id not in APPROVED_POLICY_CATALOGUE:
        raise ValueError(f"Unapproved or unrecognized evaluation policy ID: '{policy_id}'.")
    policy = APPROVED_POLICY_CATALOGUE[policy_id]
    if version and policy.version != version:
        raise ValueError(
            f"Policy version mismatch for '{policy_id}': requested '{version}', active approved is '{policy.version}'."
        )
    return policy


@dataclass
class CandidateProposalInput:
    """Typed candidate proposal input."""
    vendor_id: str
    vendor_name: str
    technical_score: Optional[Decimal]
    technical_source_ref: Optional[str]
    commercial_price: Optional[Decimal]
    commercial_currency: str
    commercial_tax_basis: str
    commercial_term_basis: str
    commercial_scope: str
    commercial_source_ref: Optional[str]
    historical_score: Optional[Decimal] = None
    historical_record_count: int = 0
    historical_caveat: Optional[str] = None


@dataclass
class CandidateScoringResult:
    """Computed scoring breakdown for a single candidate."""
    vendor_id: str
    vendor_name: str
    is_eligible: bool
    eligibility_errors: List[str]
    raw_values: Dict[str, Optional[Decimal]]
    normalized_scores: Dict[str, Decimal]
    baseline_contributions: Dict[str, Decimal]
    baseline_total_score: Decimal
    history_contributions: Dict[str, Decimal]
    history_total_score: Decimal
    contribution_deltas: Dict[str, Decimal]
    score_delta: Decimal
    history_record_count: int
    history_caveat: Optional[str]


def validate_commercial_comparability(
    candidates: List[CandidateProposalInput],
    comparability: CommercialComparabilityBasis,
) -> Tuple[bool, List[str]]:
    """Validate that all candidate proposals conform to required comparability parameters.
    
    Prevents implicit currency conversions or incomparable commercial proposals.
    """
    errors: List[str] = []
    for cand in candidates:
        if cand.commercial_currency != comparability.required_currency:
            errors.append(
                f"Candidate '{cand.vendor_id}' currency mismatch: proposal is in '{cand.commercial_currency}', "
                f"policy requires '{comparability.required_currency}'. Implicit conversion disallowed."
            )
        if cand.commercial_tax_basis != comparability.required_tax_basis:
            errors.append(
                f"Candidate '{cand.vendor_id}' tax basis mismatch: proposal is '{cand.commercial_tax_basis}', "
                f"policy requires '{comparability.required_tax_basis}'."
            )
        if cand.commercial_term_basis != comparability.required_term_basis:
            errors.append(
                f"Candidate '{cand.vendor_id}' term basis mismatch: proposal is '{cand.commercial_term_basis}', "
                f"policy requires '{comparability.required_term_basis}'."
            )
        if cand.commercial_scope != comparability.required_scope:
            errors.append(
                f"Candidate '{cand.vendor_id}' scope mismatch: proposal scope '{cand.commercial_scope}', "
                f"policy requires '{comparability.required_scope}'."
            )
    return len(errors) == 0, errors


def compute_normalized_scores(
    candidates: List[CandidateProposalInput],
    policy: EvaluationPolicy,
) -> Dict[str, Dict[str, Decimal]]:
    """Compute normalized 0-100 scores in pure Decimal for all candidates across policy criteria.
    
    For LOWER_IS_BETTER (e.g. price in AED):
      normalized = 100 * (P_max - P_i) / (P_max - P_min) if P_max > P_min else 100.
    For HIGHER_IS_BETTER (e.g. technical, history 0-100):
      normalized = raw_score clamped to 0-100.
    """
    # Collect all valid commercial prices for relative price normalization
    prices = [c.commercial_price for c in candidates if c.commercial_price is not None]
    min_price = min(prices) if prices else Decimal("0.00")
    max_price = max(prices) if prices else Decimal("0.00")
    price_span = max_price - min_price

    results: Dict[str, Dict[str, Decimal]] = {}
    for cand in candidates:
        cand_scores: Dict[str, Decimal] = {}
        # 1. Technical competence
        if cand.technical_score is not None:
            t_score = cand.technical_score
            if t_score < Decimal("0.00"):
                t_score = Decimal("0.00")
            elif t_score > Decimal("100.00"):
                t_score = Decimal("100.00")
            cand_scores["TECH_COMPETENCE"] = round_decimal(t_score, 2)
        else:
            cand_scores["TECH_COMPETENCE"] = Decimal("0.00")

        # 2. Commercial price
        if cand.commercial_price is not None:
            if price_span == Decimal("0.00"):
                cand_scores["COMMERCIAL_PRICE"] = Decimal("100.00")
            else:
                p_norm = Decimal("100.00") * (max_price - cand.commercial_price) / price_span
                cand_scores["COMMERCIAL_PRICE"] = round_decimal(p_norm, 2)
        else:
            cand_scores["COMMERCIAL_PRICE"] = Decimal("0.00")

        # 3. Historical performance
        if cand.historical_score is not None:
            h_score = cand.historical_score
            if h_score < Decimal("0.00"):
                h_score = Decimal("0.00")
            elif h_score > Decimal("100.00"):
                h_score = Decimal("100.00")
            cand_scores["HISTORICAL_PERFORMANCE"] = round_decimal(h_score, 2)
        else:
            cand_scores["HISTORICAL_PERFORMANCE"] = Decimal("0.00")

        results[cand.vendor_id] = cand_scores

    return results


def evaluate_candidate_options(
    candidates: List[CandidateProposalInput],
    policy: EvaluationPolicy,
) -> Tuple[List[CandidateScoringResult], Optional[str], str, List[str]]:
    """Execute complete deterministic dual evaluation (baseline + history-informed) in Decimal.
    
    Returns:
      (scoring_results, winning_vendor_id, evaluation_status, system_warnings)
    """
    warnings: List[str] = []

    # 1. Check commercial comparability
    is_comparable, comp_errors = validate_commercial_comparability(candidates, policy.commercial_comparability)
    if not is_comparable:
        warnings.extend(comp_errors)

    # 2. Check mandatory data completeness
    has_mandatory_failures = False
    candidate_errors: Dict[str, List[str]] = {}
    for cand in candidates:
        errs: List[str] = []
        if cand.technical_score is None:
            errs.append(f"Missing mandatory technical competence score for '{cand.vendor_id}'.")
        if cand.commercial_price is None:
            errs.append(f"Missing mandatory commercial price proposal for '{cand.vendor_id}'.")
        candidate_errors[cand.vendor_id] = errs
        if errs:
            has_mandatory_failures = True
            warnings.extend(errs)

    # Compute normalized scores
    normalized_all = compute_normalized_scores(candidates, policy)

    scoring_results: List[CandidateScoringResult] = []
    base_weights = policy.history_influence.baseline_weights
    hist_weights = policy.history_influence.history_informed_weights

    for cand in candidates:
        c_errs = candidate_errors.get(cand.vendor_id, [])
        is_eligible = (len(c_errs) == 0) and is_comparable
        norm = normalized_all.get(cand.vendor_id, {})

        # Baseline calculation
        base_contrib: Dict[str, Decimal] = {}
        base_total = Decimal("0.00")
        for crit_id, w in base_weights.items():
            val = norm.get(crit_id, Decimal("0.00"))
            contrib = round_decimal(w * val, 2)
            base_contrib[crit_id] = contrib
            base_total += contrib
        base_total = round_decimal(base_total, 2)

        # History-informed calculation
        hist_contrib: Dict[str, Decimal] = {}
        hist_total = Decimal("0.00")
        for crit_id, w in hist_weights.items():
            val = norm.get(crit_id, Decimal("0.00"))
            contrib = round_decimal(w * val, 2)
            hist_contrib[crit_id] = contrib
            hist_total += contrib
        hist_total = round_decimal(hist_total, 2)

        # Contribution deltas
        contrib_deltas: Dict[str, Decimal] = {}
        for crit_id in hist_weights.keys():
            h_c = hist_contrib.get(crit_id, Decimal("0.00"))
            b_c = base_contrib.get(crit_id, Decimal("0.00"))
            contrib_deltas[crit_id] = round_decimal(h_c - b_c, 2)

        score_delta = round_decimal(hist_total - base_total, 2)

        scoring_results.append(
            CandidateScoringResult(
                vendor_id=cand.vendor_id,
                vendor_name=cand.vendor_name,
                is_eligible=is_eligible,
                eligibility_errors=c_errs,
                raw_values={
                    "TECH_COMPETENCE": cand.technical_score,
                    "COMMERCIAL_PRICE": cand.commercial_price,
                    "HISTORICAL_PERFORMANCE": cand.historical_score,
                },
                normalized_scores=norm,
                baseline_contributions=base_contrib,
                baseline_total_score=base_total,
                history_contributions=hist_contrib,
                history_total_score=hist_total,
                contribution_deltas=contrib_deltas,
                score_delta=score_delta,
                history_record_count=cand.historical_record_count,
                history_caveat=cand.historical_caveat,
            )
        )

    # Determine status and winner
    if not is_comparable or has_mandatory_failures:
        status = "INSUFFICIENT_EVIDENCE"
        winner = None
        return scoring_results, winner, status, warnings

    # Sort candidates by final history-informed score descending
    # Apply tie policy if scores are equal
    def sort_key(res: CandidateScoringResult):
        score = res.history_total_score
        tech_score = res.normalized_scores.get("TECH_COMPETENCE", Decimal("0.00"))
        # Primary sort: history_total_score descending
        # Tie breaker: HIGHER_TECHNICAL_WINS -> tech_score descending
        return (score, tech_score)

    sorted_results = sorted(scoring_results, key=sort_key, reverse=True)
    winner = sorted_results[0].vendor_id if sorted_results else None
    status = "SUCCESS"

    return scoring_results, winner, status, warnings
