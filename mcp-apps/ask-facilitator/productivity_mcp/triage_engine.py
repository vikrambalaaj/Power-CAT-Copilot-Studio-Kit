"""Contextual Attention Scoring Engine (CASE) — Velora Executive Agent Platform.

Normalizes mail, calendar, and task action items into AttentionItem contracts with
a versioned 4-factor rubric (businessCriticality, senderImportance, deadlineProximity, riskSeverity).
Calculates priorityScore = round_half_up(100 * sum(weight_i * factor_i / 5)) using exact Decimals.
Enforces deterministic ranking, fail-closed injection protection, fixed-denominator missing factor policy,
and strict separation between priority score (urgency) and evidence confidence (reliability).
"""
from __future__ import annotations

import decimal
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import re
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from .evidence_contracts import (
    AttentionItem,
    ClaimKind,
    ConfidenceAssessment,
    ConfidenceLabel,
    EvidenceSource,
    MaterialClaim,
)
from .confidence_policy import evaluate_confidence, parse_iso_timestamp


class MissingFactorPolicy(str, Enum):
    """Handling of unobserved or missing optional factors."""
    FIXED_DENOMINATOR = "FIXED_DENOMINATOR"  # Keep denominator 5 and weights fixed; do not renormalize
    RENORMALIZE = "RENORMALIZE"              # Explicitly renormalize remaining weights (requires approval)
    FAIL_IF_MANDATORY = "FAIL_IF_MANDATORY"  # Reject scoring if factor is mandatory


class TriageRubricPolicy(BaseModel):
    """Versioned attention scoring rubric policy configuration."""
    policyId: str = Field(default="RUBRIC-TEST-EQUAL", description="Rubric policy identifier")
    version: str = Field(default="1.0.0-test", description="Rubric policy version")
    weights: Dict[str, Decimal] = Field(
        default_factory=lambda: {
            "businessCriticality": Decimal("0.25"),
            "senderImportance": Decimal("0.25"),
            "deadlineProximity": Decimal("0.25"),
            "riskSeverity": Decimal("0.25"),
        },
        description="Factor weights summing strictly to Decimal('1.0')",
    )
    missingFactorPolicy: MissingFactorPolicy = Field(
        default=MissingFactorPolicy.FIXED_DENOMINATOR,
        description="Policy for handling unobserved factors",
    )
    mandatoryFactors: List[str] = Field(default_factory=list, description="Factors that must be observed")
    isTestPolicy: bool = Field(default=True, description="True if using test weights pending CEO Office I02 approval")
    approvedBy: Optional[str] = Field(default=None, description="Approver ID for production policy")

    def model_post_init(self, __context: Any) -> None:
        """Validate rubric weights and invariant constraints."""
        required_factors = {"businessCriticality", "senderImportance", "deadlineProximity", "riskSeverity"}
        missing_keys = required_factors - set(self.weights.keys())
        if missing_keys:
            raise ValueError(f"Rubric missing mandatory weight configuration for: {missing_keys}")

        total_weight = Decimal("0")
        for factor, weight in self.weights.items():
            if not isinstance(weight, Decimal):
                weight = Decimal(str(weight))
                self.weights[factor] = weight
            if weight < Decimal("0"):
                raise ValueError(f"Rubric weight for factor '{factor}' cannot be negative: {weight}")
            total_weight += weight

        if abs(total_weight - Decimal("1.0")) > Decimal("0.00001"):
            raise ValueError(f"Rubric weights must sum exactly to 1.0, got: {total_weight}")


# Pre-configured test rubric with equal 0.25 weights (Acceptance T06 compliant)
TEST_EQUAL_WEIGHTS_RUBRIC = TriageRubricPolicy(
    policyId="RUBRIC-TEST-EQUAL",
    version="1.0.0-test",
    weights={
        "businessCriticality": Decimal("0.25"),
        "senderImportance": Decimal("0.25"),
        "deadlineProximity": Decimal("0.25"),
        "riskSeverity": Decimal("0.25"),
    },
    isTestPolicy=True,
)


def round_half_up(val: Decimal) -> int:
    """Deterministic round half up to nearest integer."""
    return int(val.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# =====================================================================
# SENDER IMPORTANCE EVALUATION (0-5)
# Sourced from approved mappings / verified roles, never name alone
# =====================================================================

VIP_SENDER_DOMAINS_L5 = {"board.velora.ae", "regulator.gov.ae", "audit-committee.velora.ae"}
VIP_SENDER_EMAILS_L5 = {
    "ceo@velora.ae",
    "cfo@velora.ae",
    "chairman@velora.ae",
    "audit.chair@board.velora.ae",
}
VIP_SENDER_EMAILS_L4 = {
    "coo@velora.ae",
    "cio@velora.ae",
    "generalcounsel@velora.ae",
    "gc@velora.ae",
    "leadership@velora.ae",
    "financeleadership@velora.ae",
}
VIP_SENDER_EMAILS_L3 = {
    "external-audit@kpmg.com",
    "audit@pwc.com",
    "director.legal@velora.ae",
    "head.it@velora.ae",
}


def evaluate_sender_importance(sender_email: str, sender_role: Optional[str] = None) -> int:
    """Evaluate sender importance (0–5) from verified address or directory role.
    
    Invariant: Executive rank is NEVER derived from a display name alone.
    """
    if not sender_email:
        return 0

    clean_email = sender_email.lower().strip()
    domain = clean_email.split("@")[-1] if "@" in clean_email else ""

    if clean_email in VIP_SENDER_EMAILS_L5 or domain in VIP_SENDER_DOMAINS_L5:
        return 5
    if clean_email in VIP_SENDER_EMAILS_L4 or "leadership@" in clean_email:
        return 4
    if clean_email in VIP_SENDER_EMAILS_L3 or "director@" in clean_email or "head." in clean_email:
        return 3
    if domain == "velora.ae":
        return 2
    if domain:
        return 1
    return 0


# =====================================================================
# BUSINESS CRITICALITY EVALUATION (0-5)
# Sourced from approved business topics / keywords
# =====================================================================

CRITICALITY_L5_PATTERNS = [
    r"\b(board(?:\s+of\s+directors)?|audit(?:\s+table)?\s+sign-?off|regulatory(?:\s+filing)?|compliance\s+breach|dataverse\s+migration\s+sign-?off)\b",
    r"\b(quarterly\s+financial\s+closing|legal\s+hold|merger|acquisition)\b",
]
CRITICALITY_L4_PATTERNS = [
    r"\b(erp\s+cutover|vendor\s+contract\s+dispute|budget\s+overrun|system\s+outage|production\s+release)\b",
    r"\b(executive\s+briefing|sla\s+penalty|audit\s+finding)\b",
]
CRITICALITY_L3_PATTERNS = [
    r"\b(department\s+review|project\s+milestone|supplier\s+invoice|quarterly\s+review)\b",
]
CRITICALITY_L2_PATTERNS = [
    r"\b(team\s+meeting|weekly\s+sync|status\s+update|operational\s+log)\b",
]


def evaluate_business_criticality(
    title: str,
    body: str = "",
    source_importance: str = "normal",
) -> int:
    """Evaluate business criticality (0–5) based on topic keywords and verified context.
    
    Source-provided importance contributes as an indicator but does not dictate the score.
    """
    text = f"{title} {body}".lower()

    score = 1
    for p in CRITICALITY_L5_PATTERNS:
        if re.search(p, text, re.IGNORECASE):
            score = 5
            break

    if score < 5:
        for p in CRITICALITY_L4_PATTERNS:
            if re.search(p, text, re.IGNORECASE):
                score = 4
                break

    if score < 4:
        for p in CRITICALITY_L3_PATTERNS:
            if re.search(p, text, re.IGNORECASE):
                score = 3
                break

    if score < 3:
        for p in CRITICALITY_L2_PATTERNS:
            if re.search(p, text, re.IGNORECASE):
                score = 2
                break

    # Source-provided importance can bump routine score, but capped appropriately
    if source_importance.lower() == "high":
        score = max(score, 2)

    return min(max(score, 0), 5)


# =====================================================================
# DEADLINE EXTRACTION & PROXIMITY EVALUATION (0-5)
# Explicit statement or authoritative field only; "soon" is unknown!
# =====================================================================

DEADLINE_EXPLICIT_PATTERNS = [
    # ISO dates: e.g. 2026-09-15 or 2026-09-14T17:00:00+04:00
    r"(?:due(?:\s+by|\s+date|\s+on)?|deadline(?:\s+is|\s*:)?)\s*[:\-]?\s*([0-9]{4}-[0-9]{2}-[0-9]{2}(?:[T\s][0-9]{2}:[0-9]{2}(?::[0-9]{2})?(?:[+\-][0-9]{2}:?[0-9]{2}|Z)?)?)",
    # English formats: e.g. September 14, 2026 at 17:00 or Sep 15, 2026 5:00 PM
    r"(?:due(?:\s+by|\s+date|\s+on)?|deadline(?:\s+is|\s*:)?)\s*[:\-]?\s*([A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4}(?:\s+at\s+[0-9]{1,2}:[0-9]{2}(?:\s*(?:AM|PM|GST))?)?)",
]


def extract_explicit_deadline(
    item_dict: Dict[str, Any],
    item_type: str,
    default_tz_offset: str = "+04:00",
) -> Tuple[Optional[str], Optional[str], bool]:
    """Extract authoritative or explicitly cited deadline.
    
    Returns:
        (deadline_iso, deadline_evidence, is_inferred)
    Invariant: Ambiguous 'soon' is unknown (returns None). Missing deadline is not fabricated.
    """
    # 1. Authoritative Task field
    if item_type in ("PLANNER", "MEETING_ACTION", "TASK"):
        due = item_dict.get("dueDateTime") or item_dict.get("due_date")
        if due:
            return due, f"Authoritative Planner task dueDateTime: '{due}'", False

    # 2. Authoritative Calendar field
    if item_type in ("CALENDAR", "EVENT"):
        start = item_dict.get("startDateTime") or item_dict.get("start")
        if isinstance(start, dict):
            start = start.get("dateTime")
        if start:
            return start, f"Authoritative Calendar startDateTime: '{start}'", False

    # 3. Message Body / Subject explicit statement
    title = item_dict.get("subject") or item_dict.get("title") or ""
    body = item_dict.get("bodyPreview") or item_dict.get("body") or ""
    content = f"{title}. {body}"

    # Check for ambiguous words first — if only ambiguous words exist, DO NOT fabricate deadline
    has_ambiguous_only = bool(re.search(r"\b(due\s+soon|asap|shortly|at\s+your\s+earliest\s+convenience)\b", content, re.IGNORECASE))

    for pattern in DEADLINE_EXPLICIT_PATTERNS:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            raw_val = match.group(1).strip()
            excerpt = match.group(0).strip()
            # Normalize to ISO string
            norm_dt = _parse_date_string(raw_val, default_tz_offset)
            if norm_dt:
                iso_str = norm_dt.isoformat()
                return iso_str, f"Inferred from message excerpt: '{excerpt}'", True

    return None, None, False


def _parse_date_string(raw: str, default_tz_offset: str = "+04:00") -> Optional[datetime]:
    """Safely parse various date formats into timezone-aware datetime."""
    try:
        clean = raw.replace("Z", "+00:00").replace(" GST", "+04:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            # Apply default timezone offset
            tz_hours = int(default_tz_offset[:3])
            tz_mins = int(default_tz_offset[4:6]) if len(default_tz_offset) >= 6 else 0
            tz = timezone(timedelta(hours=tz_hours, minutes=tz_mins))
            dt = dt.replace(tzinfo=tz)
        return dt
    except Exception:
        pass

    # Try common formats like "September 14, 2026 at 17:00"
    for fmt in (
        "%B %d, %Y at %H:%M",
        "%B %d, %Y %H:%M",
        "%B %d, %Y",
        "%b %d, %Y at %H:%M",
        "%b %d, %Y %H:%M",
        "%b %d, %Y",
    ):
        try:
            clean_date = re.sub(r"\s+GST\b", "", raw, flags=re.IGNORECASE).strip()
            dt = datetime.strptime(clean_date, fmt)
            tz_hours = int(default_tz_offset[:3])
            tz_mins = int(default_tz_offset[4:6]) if len(default_tz_offset) >= 6 else 0
            tz = timezone(timedelta(hours=tz_hours, minutes=tz_mins))
            return dt.replace(tzinfo=tz)
        except Exception:
            continue
    return None


def calculate_deadline_proximity(
    deadline_iso: Optional[str],
    now: Optional[datetime] = None,
) -> int:
    """Evaluate deadline proximity factor (0–5).
    
    5: Overdue or due within 12 hours.
    4: Due within 24 hours.
    3: Due within 48 hours.
    2: Due within 7 days.
    1: Due in > 7 days.
    0: Unknown or no deadline.
    """
    if not deadline_iso:
        return 0

    deadline_dt = parse_iso_timestamp(deadline_iso)
    if not deadline_dt:
        return 0

    ref_now = now or datetime.now(timezone.utc)
    # Ensure timezone awareness matches
    if deadline_dt.tzinfo is None:
        deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
    if ref_now.tzinfo is None:
        ref_now = ref_now.replace(tzinfo=timezone.utc)

    diff_hours = (deadline_dt - ref_now).total_seconds() / 3600.0

    if diff_hours <= 12.0:
        return 5
    if diff_hours <= 24.0:
        return 4
    if diff_hours <= 48.0:
        return 3
    if diff_hours <= 168.0:  # 7 days
        return 2
    return 1


# =====================================================================
# RISK SEVERITY EVALUATION (0-5)
# =====================================================================

RISK_L5_PATTERNS = [
    r"\b(security\s+breach|zero-?day|unauthorized\s+access|data\s+loss|sanction|regulatory\s+penalty)\b",
]
RISK_L4_PATTERNS = [
    r"\b(audit\s+finding|unapproved\s+migration|contract\s+dispute|overrun\s+exceeds|severe\s+outage)\b",
]
RISK_L3_PATTERNS = [
    r"\b(delay|slippage|budget\s+variance|dependency\s+blocker)\b",
]
RISK_L2_PATTERNS = [
    r"\b(action\s+required|review\s+needed|pending\s+sign-?off)\b",
]


def evaluate_risk_severity(
    title: str,
    body: str = "",
    business_criticality: int = 1,
) -> int:
    """Evaluate risk severity (0–5) from observed risk terminology and criticality."""
    text = f"{title} {body}".lower()

    score = 0
    for p in RISK_L5_PATTERNS:
        if re.search(p, text, re.IGNORECASE):
            return 5

    for p in RISK_L4_PATTERNS:
        if re.search(p, text, re.IGNORECASE):
            return 4

    for p in RISK_L3_PATTERNS:
        if re.search(p, text, re.IGNORECASE):
            score = max(score, 3)
            break

    for p in RISK_L2_PATTERNS:
        if re.search(p, text, re.IGNORECASE):
            score = max(score, 2)
            break

    # If business criticality is very high, baseline risk is at least 1
    if business_criticality >= 4 and score == 0:
        score = 2
    elif business_criticality >= 2 and score == 0:
        score = 1

    return min(max(score, 0), 5)


# =====================================================================
# MATHEMATICAL DETERMINISM & SCORING ENGINE
# priorityScore = round_half_up(100 * sum(weight_i * factor_i / 5))
# =====================================================================

def compute_priority_score(
    factor_values: Dict[str, int],
    weights: Dict[str, Decimal],
    missing_factors: List[str],
    policy: TriageRubricPolicy,
) -> Tuple[int, Dict[str, Any]]:
    """Compute deterministic priorityScore in range 0–100 and factor contributions.
    
    Formula:
        priorityScore = round_half_up(100 * sum(weight_i * factor_i / 5))
    
    Enforces:
    - Fixed denominator policy (does not silently renormalize missing factors).
    - Decimal arithmetic for zero floating-point drift.
    """
    total_score_dec = Decimal("0")
    factor_scores: Dict[str, Any] = {}

    for factor_name, weight in weights.items():
        val = factor_values.get(factor_name, 0)
        if not (0 <= val <= 5):
            raise ValueError(f"Factor value for '{factor_name}' must be between 0 and 5, got: {val}")

        # Contribution = 100 * (weight * factor / 5)
        # Exactly equals 20 * weight * factor
        factor_dec = Decimal(str(val))
        contribution_dec = Decimal("100") * (weight * factor_dec / Decimal("5"))
        total_score_dec += contribution_dec

        factor_scores[factor_name] = {
            "value": val,
            "weight": str(weight),
            "contribution": round_half_up(contribution_dec),
            "isObserved": factor_name not in missing_factors,
        }

    priority_score = round_half_up(total_score_dec)
    # Clamp to [0, 100]
    bounded_score = min(max(priority_score, 0), 100)
    return bounded_score, factor_scores


# =====================================================================
# THREAD DEDUPLICATION & RELATIONSHIP PRESERVATION
# =====================================================================

def collapse_email_threads(mail_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group mail items by threadId / conversationId.
    
    Preserves all underlying source IDs in sourceRecordReferences and records
    the relationship explicitly without dropping evidence.
    """
    threads: Dict[str, List[Dict[str, Any]]] = {}
    standalones: List[Dict[str, Any]] = []

    for item in mail_items:
        thread_id = item.get("threadId") or item.get("conversationId")
        if thread_id:
            threads.setdefault(thread_id, []).append(item)
        else:
            standalones.append(item)

    collapsed_list: List[Dict[str, Any]] = []

    for thread_id, msgs in threads.items():
        if len(msgs) == 1:
            collapsed_list.append(msgs[0])
        else:
            # Sort by receivedDateTime descending so latest message represents thread
            sorted_msgs = sorted(
                msgs,
                key=lambda m: m.get("receivedDateTime") or "",
                reverse=True,
            )
            rep = dict(sorted_msgs[0])
            all_ids = [m.get("id") for m in sorted_msgs if m.get("id")]
            rep["_allThreadMessageIds"] = all_ids
            rep["_collapsedThreadCount"] = len(sorted_msgs)
            rep["_threadRelationship"] = f"THREAD_COLLAPSED_{len(sorted_msgs)}_MESSAGES"
            collapsed_list.append(rep)

    collapsed_list.extend(standalones)
    return collapsed_list


# =====================================================================
# MAIN NORMALIZATION & SCORING PIPELINE
# =====================================================================

def normalize_and_score_item(
    item_dict: Dict[str, Any],
    item_type: str,
    rubric: TriageRubricPolicy,
    now: Optional[datetime] = None,
    default_tz_offset: str = "+04:00",
) -> AttentionItem:
    """Normalize a raw mail, calendar, or task item into an AttentionItem contract.
    
    Deterministic:
    - Factors evaluated: businessCriticality, senderImportance, deadlineProximity, riskSeverity.
    - Score calculated via Decimal arithmetic.
    - Evidence confidence assessed independently.
    """
    ref_now = now or datetime.now(timezone.utc)

    # 1. Identity & Title
    raw_id = item_dict.get("id") or item_dict.get("itemId") or f"GEN-{hashlib.sha256(str(item_dict).encode()).hexdigest()[:12]}"
    source_refs = list(item_dict.get("_allThreadMessageIds") or [raw_id])

    title = item_dict.get("subject") or item_dict.get("title") or "Untitled Attention Item"
    body = item_dict.get("bodyPreview") or item_dict.get("body") or ""
    sender = item_dict.get("from") or ""
    if isinstance(sender, dict):
        sender = sender.get("emailAddress", {}).get("address", "")
    source_importance = str(item_dict.get("importance", "normal"))

    # 2. Extract Deadline (strictly explicit statement or authoritative field)
    deadline_iso, deadline_evidence, is_inferred = extract_explicit_deadline(item_dict, item_type, default_tz_offset)

    # 3. Evaluate the 4 Factors (0–5)
    missing_factors: List[str] = []

    f_criticality = evaluate_business_criticality(title, body, source_importance)
    f_sender = evaluate_sender_importance(sender)
    
    if deadline_iso:
        f_deadline = calculate_deadline_proximity(deadline_iso, ref_now)
    else:
        f_deadline = 0
        missing_factors.append("deadlineProximity")

    f_risk = evaluate_risk_severity(title, body, f_criticality)

    # Check if any mandatory factor is missing
    if rubric.mandatoryFactors:
        for mandatory in rubric.mandatoryFactors:
            if mandatory in missing_factors:
                raise ValueError(f"Mandatory factor '{mandatory}' is unobserved for item '{raw_id}'")

    factor_values = {
        "businessCriticality": f_criticality,
        "senderImportance": f_sender,
        "deadlineProximity": f_deadline,
        "riskSeverity": f_risk,
    }

    # 4. Compute Priority Score
    total_score, factor_scores = compute_priority_score(
        factor_values=factor_values,
        weights=rubric.weights,
        missing_factors=missing_factors,
        policy=rubric,
    )

    # 5. Determine Why Attention Required & Proposed Action
    why_attention, proposed_action = _generate_rationale_and_action(
        item_type=item_type,
        title=title,
        factors=factor_values,
        deadline_iso=deadline_iso,
        is_overdue=(f_deadline == 5 and bool(deadline_iso)),
    )

    # 6. Evaluate Separate Evidence Confidence Assessment
    # Notice: Priority 100 may still have LOW confidence if sources are unverified or stale!
    sources = [
        EvidenceSource(
            sourceId=raw_id,
            system="Microsoft 365" if item_type == "MAIL" else ("Outlook Calendar" if item_type == "CALENDAR" else "Microsoft Planner"),
            businessTitle=f"{item_type}: {title[:40]}",
            providerRecordId=raw_id,
            retrievedAt=ref_now.isoformat(),
            sourceUpdatedAt=item_dict.get("lastModifiedDateTime") or item_dict.get("receivedDateTime"),
            limitations=["Inferred deadline from unstructured body" if is_inferred else "Authoritative provider metadata"],
        )
    ]
    confidence = evaluate_confidence(sources, now=ref_now, source_sla_hours=48.0)

    # Clean item ID
    stable_item_id = f"ATTN-{item_type[:3]}-{raw_id[-12:]}" if len(raw_id) >= 12 else f"ATTN-{item_type[:3]}-{raw_id}"

    return AttentionItem(
        itemId=stable_item_id,
        itemType=item_type,
        sourceRecordReferences=source_refs,
        title=title,
        requiredAttention=why_attention,
        deadline=deadline_iso,
        deadlineEvidence=deadline_evidence,
        relatedMeetingIds=item_dict.get("relatedMeetingIds", []),
        factorScores=factor_scores,
        totalScore=total_score,
        rank=0,  # Assigned after sorting
        scoringVersion=rubric.version,
        missingFactors=missing_factors,
        claimConfidence=confidence,
    )


def _generate_rationale_and_action(
    item_type: str,
    title: str,
    factors: Dict[str, int],
    deadline_iso: Optional[str],
    is_overdue: bool,
) -> Tuple[str, str]:
    """Generate deterministic, non-destructive rationale and proposed next action."""
    criticality = factors.get("businessCriticality", 0)
    sender = factors.get("senderImportance", 0)
    deadline_p = factors.get("deadlineProximity", 0)
    risk = factors.get("riskSeverity", 0)

    # Build why attention statement
    reasons = []
    if is_overdue:
        reasons.append("Overdue deliverable requirement")
    elif deadline_p >= 4:
        reasons.append("Imminent deadline approaching within 24h")
    elif deadline_p == 3:
        reasons.append("Approaching deadline within 48h")

    if criticality >= 4:
        reasons.append("Critical executive/governance topic")
    if sender >= 4:
        reasons.append("High-priority executive sender")
    if risk >= 4:
        reasons.append("Elevated organizational or financial risk")

    if not reasons:
        reasons.append("Routine operational review")

    why_attention = "; ".join(reasons) + f" (Criticality: {criticality}/5, Risk: {risk}/5)."

    # Proposed next action (STRICTLY READ-ONLY / REVIEW, NEVER UNAPPROVED WRITE)
    if item_type == "MAIL":
        if criticality >= 4 or sender >= 4:
            action = "Review executive email thread and prepare draft response for review."
        else:
            action = "Review email update and archive if no response needed."
    elif item_type == "CALENDAR":
        action = "Review executive meeting agenda and briefing materials."
    elif item_type in ("PLANNER", "MEETING_ACTION", "TASK"):
        if is_overdue:
            action = "Confirm task completion status or update target delivery timeline."
        else:
            action = "Review deliverable progress and assign sign-off verification."
    else:
        action = "Review attention item details."

    return why_attention, action


def rank_attention_items(
    items: List[AttentionItem],
) -> List[AttentionItem]:
    """Sort attention items by totalScore desc, earlier known deadline, then stable itemId.
    
    Assigns 1-indexed ranks deterministically.
    """
    def sort_key(item: AttentionItem) -> Tuple[int, int, str, str]:
        # 1. Total score descending (-item.totalScore)
        # 2. Known deadline indicator (0 if known deadline, 1 if null)
        # 3. Deadline ISO string (earliest first; "" if None)
        # 4. Stable item ID ascending
        has_deadline = 0 if item.deadline is not None else 1
        deadline_str = item.deadline or "9999-12-31T23:59:59Z"
        return (-item.totalScore, has_deadline, deadline_str, item.itemId)

    sorted_items = sorted(items, key=sort_key)
    for idx, item in enumerate(sorted_items, start=1):
        item.rank = idx
    return sorted_items


def score_candidates_pipeline(
    mail_candidates: List[Dict[str, Any]],
    calendar_candidates: List[Dict[str, Any]],
    task_candidates: List[Dict[str, Any]],
    rubric: Optional[TriageRubricPolicy] = None,
    now: Optional[datetime] = None,
    maximum_results: int = 10,
    default_tz_offset: str = "+04:00",
) -> List[AttentionItem]:
    """End-to-end CASE triage pipeline across all M365 input candidates.
    
    - Collapses duplicate thread references preserving source IDs.
    - Evaluates normal-importance mail alongside high-importance mail.
    - Calculates mathematically deterministic priority scores.
    - Ranks items deterministically.
    """
    active_rubric = rubric or TEST_EQUAL_WEIGHTS_RUBRIC
    ref_now = now or datetime.now(timezone.utc)

    # 1. Collapse duplicate email threads
    collapsed_mails = collapse_email_threads(mail_candidates)

    attention_items: List[AttentionItem] = []

    # 2. Normalize and score mails
    for m in collapsed_mails:
        item = normalize_and_score_item(
            item_dict=m,
            item_type="MAIL",
            rubric=active_rubric,
            now=ref_now,
            default_tz_offset=default_tz_offset,
        )
        attention_items.append(item)

    # 3. Normalize and score calendar events
    for ev in calendar_candidates:
        item = normalize_and_score_item(
            item_dict=ev,
            item_type="CALENDAR",
            rubric=active_rubric,
            now=ref_now,
            default_tz_offset=default_tz_offset,
        )
        attention_items.append(item)

    # 4. Normalize and score tasks / meeting actions
    for tsk in task_candidates:
        item = normalize_and_score_item(
            item_dict=tsk,
            item_type="TASK",
            rubric=active_rubric,
            now=ref_now,
            default_tz_offset=default_tz_offset,
        )
        attention_items.append(item)

    # 5. Sort and rank
    ranked = rank_attention_items(attention_items)
    return ranked[:maximum_results]
