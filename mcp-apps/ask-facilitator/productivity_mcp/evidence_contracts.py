"""Common Contracts v1 — Velora Executive Agent Platform.

Deterministic evidence envelopes, material claims, attribution, execution context,
and confidence assessments ensuring institutional traceability and strict grounding.
"""
from __future__ import annotations

import decimal
import json
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_serializer, field_validator


class ActorType(str, Enum):
    USER = "USER"
    WORKLOAD = "WORKLOAD"


class ClaimKind(str, Enum):
    FACT = "FACT"
    EVALUATION = "EVALUATION"
    SUGGESTION = "SUGGESTION"
    RECOMMENDATION = "RECOMMENDATION"
    BENCHMARK = "BENCHMARK"


class ConfidenceLabel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNASSESSED = "UNASSESSED"


class OperationStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CONFIGURATION_REQUIRED = "CONFIGURATION_REQUIRED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


class SubscriptionKind(str, Enum):
    MORNING = "MORNING"
    PRE_MEETING = "PRE_MEETING"
    EOD = "EOD"
    ACTION_REMINDER = "ACTION_REMINDER"


def decimal_serializer(obj: Any) -> Any:
    """Deterministic JSON serializer preserving exact Decimal financial precision."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


class ExecutionContext(BaseModel):
    """Authenticated context established from server-side verified tokens, never client body alone."""
    tenantId: str = Field(description="Directory tenant identifier")
    actorObjectId: str = Field(description="Authenticated Entra object ID of caller")
    actorType: ActorType = Field(default=ActorType.USER, description="USER or WORKLOAD identity")
    onBehalfOfUserObjectId: Optional[str] = Field(default=None, description="Delegated user object ID when WORKLOAD acts on-behalf")
    organizationScopes: List[str] = Field(default_factory=list, description="Authorized business units / company codes")
    correlationId: str = Field(description="Root correlation tracking ID")
    conversationId: Optional[str] = Field(default=None, description="Copilot conversation ID")
    turnId: Optional[str] = Field(default=None, description="Copilot turn ID")
    policyVersion: str = Field(default="1.0.0", description="Applicable security and business policy version")


class ConfidenceAssessment(BaseModel):
    """Conservative, deterministic confidence assessment v1 based on evidence factors, not LLM self-rating."""
    label: ConfidenceLabel = Field(description="HIGH, MEDIUM, LOW, or UNASSESSED")
    frameworkVersion: str = Field(default="v1.0", description="Confidence evaluation policy version")
    sourceReliability: str = Field(description="Evaluation of source authority (e.g. AUTHORITATIVE, REPUTABLE, UNVERIFIED)")
    corroboration: str = Field(description="Level of cross-source corroboration")
    timeliness: str = Field(description="Freshness evaluation against source SLA")
    completeness: str = Field(description="Data completeness evaluation")
    comparability: str = Field(description="Semantic and structural comparability across datasets")
    reason: str = Field(description="Concise human-readable rationale for confidence assessment")
    limitingFactors: List[str] = Field(default_factory=list, description="Explanatory limiting factors (staleness, missing fields, etc.)")
    score: Optional[float] = Field(default=None, description="Optional calibrated score; disabled until verified")


class EvidenceSource(BaseModel):
    """Authoritative source record reference guaranteeing traceability to underlying ERP/M365 data."""
    sourceId: str = Field(description="Unique stable reference ID in response or evidence repository")
    system: str = Field(description="Source platform (e.g. S4HANA, Outlook, Teams, Planner, Dataverse)")
    businessTitle: str = Field(description="Business title of entity/dataset (e.g. AR Aging Report CoCode 1000)")
    providerRecordId: Optional[str] = Field(default=None, description="Platform native record ID or protected snapshot hash")
    url: Optional[str] = Field(default=None, description="Nullable real verified link; null if no direct link exists")
    retrievedAt: str = Field(description="ISO-8601 timestamp when data was fetched by adapter")
    sourceUpdatedAt: Optional[str] = Field(default=None, description="Nullable source modified timestamp. Remains null if unknown!")
    measurementPeriod: Optional[str] = Field(default=None, description="Time window covered by source (e.g. 2026-Q3)")
    scope: Optional[str] = Field(default=None, description="Organizational or entity scope (e.g. CoCode 1000, Plant 1AD1)")
    currency: Optional[str] = Field(default=None, description="ISO-4217 currency if applicable")
    unit: Optional[str] = Field(default=None, description="Unit of measurement if applicable")
    coverage: Optional[str] = Field(default=None, description="Coverage assessment (e.g. 100% of open items)")
    limitations: List[str] = Field(default_factory=list, description="Known exclusions, filters, or missing segments")
    classification: str = Field(default="CONFIDENTIAL", description="Data sensitivity classification")
    accessScopeReference: Optional[str] = Field(default=None, description="Access control partition reference")
    contentHash: Optional[str] = Field(default=None, description="Deterministic SHA-256 hash of retrieved payload")
    version: str = Field(default="1.0.0", description="Contract or snapshot schema version")


class MaterialClaim(BaseModel):
    """An individual structured claim with explicit attribution and confidence rating."""
    claimId: str = Field(description="Unique identifier for the claim within the response")
    kind: ClaimKind = Field(description="Classification: FACT, EVALUATION, SUGGESTION, RECOMMENDATION, BENCHMARK")
    text: str = Field(description="Plain executive language statement")
    numericValue: Optional[Decimal] = Field(default=None, description="Exact financial or metric value; preserved without float conversion")
    unit: Optional[str] = Field(default=None, description="Unit of measure (e.g. Headcount, Days, Ratio)")
    currency: Optional[str] = Field(default=None, description="Currency code (e.g. AED, USD)")
    sourceIds: List[str] = Field(default_factory=list, description="Must be non-empty for factual assertions; references EvidenceSource.sourceId")
    derivedFromClaimIds: List[str] = Field(default_factory=list, description="IDs of underlying claims if this claim is derived/calculated")
    calculationVersion: Optional[str] = Field(default=None, description="Algorithm or rule version used to calculate value")
    policyVersion: Optional[str] = Field(default=None, description="Policy version evaluated")
    confidenceAssessment: Optional[ConfidenceAssessment] = Field(default=None, description="Deterministic confidence rating")
    limitations: List[str] = Field(default_factory=list, description="Specific claim caveats or boundaries")

    @field_serializer("numericValue")
    def serialize_numeric_value(self, v: Optional[Decimal]) -> Optional[str]:
        return str(v) if v is not None else None

    @field_validator("sourceIds")
    @classmethod
    def validate_factual_sources(cls, v: List[str], info: Any) -> List[str]:
        # Factual claims must have at least one source
        data = info.data
        if data.get("kind") == ClaimKind.FACT and not v:
            raise ValueError("Factual assertions must cite at least one valid sourceId")
        return v


class EvidenceEnvelope(BaseModel):
    """Comprehensive output envelope preserving claims, sources, warnings, and audit status across routes."""
    schemaVersion: str = Field(default="1.0.0", description="Envelope contract version")
    operation: str = Field(description="Canonical operation identifier")
    status: OperationStatus = Field(description="Standardized operation execution status")
    resultSummary: str = Field(description="Executive plain language summary grounded in claims")
    result: Any = Field(default=None, description="Typed operation payload or structured view")
    claims: List[MaterialClaim] = Field(default_factory=list, description="Attributed material claims")
    sources: List[EvidenceSource] = Field(default_factory=list, description="Referenced underlying sources")
    warnings: List[str] = Field(default_factory=list, description="Operational, governance, or freshness warnings")
    missingSources: List[str] = Field(default_factory=list, description="Enumerated unavailable sources if status is PARTIAL")
    correlationId: str = Field(description="End-to-end correlation ID")
    audit: Dict[str, Any] = Field(default_factory=lambda: {"status": "PERSISTED", "recordId": None})
    generatedAt: str = Field(description="ISO-8601 generation timestamp")

    def to_canonical_json(self) -> str:
        """Deterministic, sorted-key JSON representation for cryptographic signing and hashing."""
        return json.dumps(self.model_dump(), sort_keys=True, default=decimal_serializer)


class DecisionRecord(BaseModel):
    """Auditable multi-criteria decision record with recorded inputs, weights, and deterministic scoring."""
    decisionId: str = Field(description="Unique decision identifier")
    version: str = Field(default="1.0.0", description="Decision version (new evaluations produce new versions)")
    useCase: str = Field(description="Business decision context (e.g. VENDOR_SELECTION, CREDIT_LIMIT_FREEZE)")
    evaluatedOptions: List[Dict[str, Any]] = Field(description="Candidate options/vendors evaluated")
    criteriaWeightsDirections: List[Dict[str, Any]] = Field(description="Criteria definitions, weights (summing to 1.0), and directions")
    inputSnapshotIds: List[str] = Field(description="IDs of underlying ERP/M365 data snapshots used")
    baselineScore: Dict[str, Any] = Field(description="Current-evidence baseline scores and contributions")
    memoryContributions: Dict[str, Any] = Field(default_factory=dict, description="Institutional history contributions and score deltas")
    finalScore: Dict[str, Any] = Field(description="Final composite scores")
    finalRank: List[str] = Field(description="Ranked candidate identifiers")
    tiePolicy: str = Field(description="Documented tie-breaking policy")
    missingDataPolicy: str = Field(description="Handling of missing mandatory criteria")
    selectedOption: Optional[str] = Field(default=None, description="Recommended winning option or null if inconclusive")
    claims: List[MaterialClaim] = Field(default_factory=list, description="Supporting material claims with confidence")
    conciseRationale: str = Field(description="Plain executive rationale explaining decisive factors and gaps")
    policyVersion: str = Field(description="Approved evaluation policy version")
    codeVersion: str = Field(description="Code version that executed the evaluation")
    authenticatedActor: ExecutionContext = Field(description="Verified caller who triggered or approved evaluation")
    auditManifestRef: Optional[str] = Field(default=None, description="Detached SHA-256 audit manifest reference")


class AttentionItem(BaseModel):
    """Ranked attention item across inbox, calendar, and meetings with transparent factor contributions."""
    itemId: str = Field(description="Stable item identifier")
    itemType: str = Field(description="MAIL, CALENDAR, or MEETING_ACTION")
    sourceRecordReferences: List[str] = Field(description="Underlying Graph or Planner provider IDs")
    title: str = Field(description="Item subject or task title")
    requiredAttention: str = Field(description="Concise description of required executive action")
    deadline: Optional[str] = Field(default=None, description="ISO-8601 deadline if explicitly cited; null if unknown")
    deadlineEvidence: Optional[str] = Field(default=None, description="Direct excerpt proving deadline")
    relatedMeetingIds: List[str] = Field(default_factory=list, description="Verified related meeting IDs")
    factorScores: Dict[str, Any] = Field(description="Factor values (0-5) and weighted score contributions")
    totalScore: int = Field(description="Computed priority score (0-100)")
    rank: int = Field(description="Deterministic ranking position")
    scoringVersion: str = Field(default="1.0.0", description="Priority rubric version")
    missingFactors: List[str] = Field(default_factory=list, description="Explicit list of unobserved factors")
    claimConfidence: Optional[ConfidenceAssessment] = Field(default=None, description="Evidence confidence rating")


class AutomationSubscription(BaseModel):
    """Governed recurring automation subscription with explicit approval, schedule, and scope."""
    subscriptionId: str = Field(description="Unique subscription identifier")
    version: str = Field(default="1.0.0", description="Subscription version")
    tenantId: str = Field(description="Directory tenant")
    owner: str = Field(description="Subscribing executive user ID")
    mailbox: str = Field(description="Target mailbox address")
    sender: str = Field(description="Authorized sending service principal or mailbox")
    recipients: List[str] = Field(description="Authorized recipient addresses")
    kind: SubscriptionKind = Field(description="MORNING, PRE_MEETING, EOD, or ACTION_REMINDER")
    timezone: str = Field(description="IANA timezone e.g. Asia/Dubai")
    localSchedule: str = Field(description="Local cron or time definition (e.g. '07:00' or '0 7 * * 1-5')")
    meetingFilters: Dict[str, Any] = Field(default_factory=dict, description="Meeting selection criteria (all, remaining, VIP)")
    leadTimeMinutes: int = Field(default=15, description="Pre-meeting brief lead time in minutes")
    horizonHours: int = Field(default=24, description="Look-ahead / look-back window in hours")
    channel: str = Field(default="EMAIL", description="Delivery channel (EMAIL, TEAMS_NOTIFICATION)")
    enabled: bool = Field(default=False, description="Explicit enablement toggle (defaults to false)")
    validUntil: Optional[str] = Field(default=None, description="Standing authorization expiration timestamp")
    authorizedBy: str = Field(description="User ID who explicitly authorized this standing subscription")
    authorizedAt: str = Field(description="Timestamp when authorization was recorded")
    allowedDataScope: List[str] = Field(default_factory=list, description="Authorized company codes or data scopes")
    lastRunAt: Optional[str] = Field(default=None, description="Timestamp of last execution")
    nextRunAt: Optional[str] = Field(default=None, description="Calculated next run timestamp")
    quietHoursPolicy: str = Field(default="SUPPRESS", description="Policy during quiet hours: SUPPRESS or DEFER")
    missedRunPolicy: str = Field(default="SKIP", description="Policy after service downtime: SKIP or RUN_ONCE")


class DeliveryReceipt(BaseModel):
    """Truthful provider delivery receipt distinguishing provider acceptance from actual inbox delivery."""
    actualProviderStatus: str = Field(description="Provider HTTP or API response status e.g. '202 Accepted'")
    requestId: Optional[str] = Field(default=None, description="Provider transaction/request trace identifier")
    messageId: Optional[str] = Field(default=None, description="Nullable actual mailbox item ID (null for Graph sendMail)")
    verifiedUrl: Optional[str] = Field(default=None, description="Nullable verified item deep link (null if not returned)")
    acceptedAt: str = Field(description="ISO-8601 timestamp of provider acceptance")
    independentDeliveryObserved: bool = Field(default=False, description="Whether delivery was independently verified in recipient mailbox")
    simulationFlag: bool = Field(default=False, description="True if run against mock/offline fixture; must be false in live")
    failureCategory: Optional[str] = Field(default=None, description="Categorized failure if rejected or failed")
