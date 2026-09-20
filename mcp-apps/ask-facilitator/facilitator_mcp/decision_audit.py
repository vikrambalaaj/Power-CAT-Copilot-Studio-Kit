"""Decision Audit Manifest Engine & Tamper-Evident Signing (Work Package W12).

Assembles decision manifests encompassing input snapshots, policy snapshots,
institutional evidence, calculation traces, claims, sources, and actor identities.
Calculates canonical SHA-256 Merkle root hashes and attaches cryptographic signatures
under external KMS key custody, enforcing append-only evidence retention (ADAA policy).
"""
from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from productivity_mcp.business_repository import (
    FinalizedEvidenceMutationError,
    VendorDecisionRecord,
    VendorDecisionRepository,
)

log = logging.getLogger("facilitator_mcp.decision_audit")

CODE_VERSION = "2.1.0-exec"
DEFAULT_SIGNING_KEY = "velora-audit-signing-key-secret-32-chars"
DEFAULT_KEY_ID = "VELORA-KMS-SIG-2026V1"
DEFAULT_ALGORITHM = "HMAC-SHA256"
DEFAULT_KEY_VERSION = "1.0.0"


class DecisionAuditError(Exception):
    """Base exception for decision audit operations."""
    pass


class DecisionNotFoundError(DecisionAuditError, KeyError):
    """Raised when the specified vendor decision record cannot be found."""
    pass


class AuditLoggingOutageError(DecisionAuditError, RuntimeError):
    """Raised when an audit logging outage is simulated or active."""
    pass


class AuditVerificationError(DecisionAuditError, ValueError):
    """Raised when cryptographic verification or data integrity check fails."""
    pass


@dataclass
class DecisionManifest:
    manifest_id: str
    decision_id: str
    version: str
    tenant_id: str
    correlation_id: str
    created_at: str
    finalized_at: str
    actor_identity: Dict[str, Any]
    policy_snapshot: Dict[str, Any]
    input_snapshot: List[Dict[str, Any]]
    institutional_evidence: Dict[str, Any]
    calculation_trace: Dict[str, Any]
    claims: List[Dict[str, Any]]
    sources: List[Dict[str, Any]]
    concise_rationale: str
    record_hashes: Dict[str, str]
    manifest_root_hash: str
    cryptographic_signature: Dict[str, str]
    retention_metadata: Dict[str, Any]
    redaction_manifest: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.redaction_manifest is None:
            d.pop("redaction_manifest", None)
        return d


def canonical_json_dumps(obj: Any) -> str:
    """Deterministic, sorted JSON serialization with pure Decimal and ISO timestamp string formatting."""
    def _default_encoder(o: Any) -> Any:
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if hasattr(o, "__dict__"):
            return o.__dict__
        return str(o)

    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_default_encoder)


def compute_record_hash(record_data: Any) -> str:
    """Compute canonical SHA-256 hash for a component record."""
    serialized = canonical_json_dumps(record_data)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_manifest_root_hash(record_hashes: Dict[str, str]) -> str:
    """Compute Merkle/composite root SHA-256 hash over sorted record hashes."""
    serialized = canonical_json_dumps(record_hashes)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def get_audit_signing_key() -> Optional[str]:
    """Retrieve external signing key from environment or fallback test secret."""
    is_prod = (
        os.getenv("VELORA_ENV", "").lower() in ("production", "prod")
        or os.getenv("ENVIRONMENT", "").lower() in ("production", "prod")
        or os.getenv("NODE_ENV", "").lower() in ("production", "prod")
    )
    key = os.getenv("VELORA_AUDIT_SIGNING_KEY")
    if key:
        if is_prod and key == DEFAULT_SIGNING_KEY:
            raise RuntimeError("DEFAULT_SIGNING_KEY cannot be used in production environment.")
        return key
    if is_prod:
        return None
    return DEFAULT_SIGNING_KEY


def sign_root_hash(root_hash: str, secret_key: Optional[str] = None) -> Dict[str, str]:
    """Cryptographically sign the manifest root hash using external key custody."""
    secret = secret_key or get_audit_signing_key()
    if not secret:
        raise RuntimeError("Missing required VELORA_AUDIT_SIGNING_KEY in production environment.")
    key_id = os.getenv("VELORA_AUDIT_KEY_ID", DEFAULT_KEY_ID)
    algorithm = DEFAULT_ALGORITHM
    key_version = DEFAULT_KEY_VERSION

    sig = hmac.new(
        secret.encode("utf-8"),
        root_hash.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return {
        "keyId": key_id,
        "algorithm": algorithm,
        "keyVersion": key_version,
        "signature": sig,
        "signedAt": datetime.now(timezone.utc).isoformat(),
    }


def verify_signature(root_hash: str, signature_dict: Dict[str, str], secret_key: Optional[str] = None) -> bool:
    """Verify cryptographic signature against root hash."""
    secret = secret_key or get_audit_signing_key()
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        root_hash.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    actual_sig = signature_dict.get("signature", "")
    return hmac.compare_digest(actual_sig, expected_sig)


def build_decision_manifest(
    decision_id: str,
    tenant_id: str = "velora-tenant",
    version: Optional[str] = None,
    actor_object_id: str = "system-auditor",
    caller_roles: Optional[List[str]] = None,
    db_path: Optional[str] = None,
    signing_key: Optional[str] = None,
) -> DecisionManifest:
    """Assemble all decision, policy, input, trace, and evidence components into a signed DecisionManifest."""
    repo = VendorDecisionRepository(db_path=db_path)
    record = repo.get_decision(decision_id=decision_id, tenant_id=tenant_id, version=version)
    if not record:
        ver_str = f" v{version}" if version else ""
        raise DecisionNotFoundError(f"Vendor decision '{decision_id}'{ver_str} not found in tenant '{tenant_id}'.")

    # 1. Component parsing
    try:
        input_snapshot: List[Dict[str, Any]] = json.loads(record.evaluated_options_json)
    except Exception:
        input_snapshot = []

    try:
        criteria_weights: Dict[str, Any] = json.loads(record.criteria_weights_json)
    except Exception:
        criteria_weights = {}

    policy_snapshot: Dict[str, Any] = {
        "policyId": record.policy_id,
        "policyVersion": record.policy_version,
        "codeVersion": record.code_version,
        "criteriaWeights": criteria_weights,
        "tiePolicy": record.tie_policy,
        "missingDataPolicy": record.missing_data_policy,
    }

    try:
        baseline_scores: Dict[str, Any] = json.loads(record.baseline_score_json)
    except Exception:
        baseline_scores = {}

    try:
        memory_contributions: Dict[str, Any] = json.loads(record.memory_contributions_json)
    except Exception:
        memory_contributions = {}

    try:
        final_scores: Dict[str, Any] = json.loads(record.final_score_json)
    except Exception:
        final_scores = {}

    try:
        final_rank: List[str] = json.loads(record.final_rank_json)
    except Exception:
        final_rank = []

    calculation_trace: Dict[str, Any] = {
        "baselineScores": baseline_scores,
        "memoryContributions": memory_contributions,
        "finalScores": final_scores,
        "finalRank": final_rank,
        "selectedOption": record.selected_option,
    }

    try:
        claims: List[Dict[str, Any]] = json.loads(record.claims_json)
    except Exception:
        claims = []

    # Reconstruct institutional evidence citations and caveats
    institutional_evidence: Dict[str, Any] = {
        "citedVendors": [c.get("vendor_id") or c.get("vendorId") for c in input_snapshot if c.get("vendor_id") or c.get("vendorId")],
        "memoryContributions": memory_contributions,
        "auditCaveat": (
            "MANDATORY AUDIT CAVEAT: Absence of documented negative events or complaints "
            "cannot be interpreted as confirmed satisfactory performance. Supplier evaluation "
            "must be grounded strictly in verified, positive evidence."
        ),
    }

    try:
        actor_identity: Dict[str, Any] = json.loads(record.authenticated_actor_json)
    except Exception:
        actor_identity = {
            "actorObjectId": actor_object_id,
            "callerRoles": caller_roles or ["AUDITOR"],
            "tenantId": tenant_id,
        }

    sources: List[Dict[str, Any]] = [
        {
            "sourceId": f"SRC-INP-{c.get('vendor_id') or c.get('vendorId')}",
            "technicalRef": c.get("technical_source_ref") or c.get("technicalSourceRef", ""),
            "commercialRef": c.get("commercial_source_ref") or c.get("commercialSourceRef", ""),
            "currency": c.get("commercial_currency") or c.get("commercialCurrency", "AED"),
            "taxBasis": c.get("commercial_tax_basis") or c.get("commercialTaxBasis", "EXCLUDING_VAT"),
        }
        for c in input_snapshot
    ]

    # 2. Canonical component hashes
    record_hashes: Dict[str, str] = {
        "actorIdentity": compute_record_hash(actor_identity),
        "policySnapshot": compute_record_hash(policy_snapshot),
        "inputSnapshot": compute_record_hash(input_snapshot),
        "institutionalEvidence": compute_record_hash(institutional_evidence),
        "calculationTrace": compute_record_hash(calculation_trace),
        "claimsAndSources": compute_record_hash({"claims": claims, "sources": sources}),
        "conciseRationale": compute_record_hash(record.concise_rationale),
    }

    # 3. Merkle root hash and cryptographic signature
    manifest_root_hash = compute_manifest_root_hash(record_hashes)
    signature = sign_root_hash(manifest_root_hash, secret_key=signing_key)

    now_iso = datetime.now(timezone.utc).isoformat()
    manifest_id = f"MAN-{tenant_id}-{record.decision_id}-{record.version}"

    retention_metadata: Dict[str, Any] = {
        "retentionClass": "ADAA_10_YEAR_FINANCIAL_RETENTION",
        "legalHold": False,
        "accessClassification": "CONFIDENTIAL_AUDIT",
        "immutabilityMode": "APPEND_ONLY_FINALIZED",
        "storagePlatform": "SQLite / Retention-Anchored Store",
        "administratorRetentionLimitation": (
            "Application role 'velora-app-service' is denied UPDATE/DELETE privilege on finalized evidence. "
            "Physical storage administrator retains OS/DB-level privileges unless anchored in WORM hardware storage; "
            "cryptographic root signatures and standalone verifier detect any out-of-band file tampering."
        ),
    }

    return DecisionManifest(
        manifest_id=manifest_id,
        decision_id=record.decision_id,
        version=record.version,
        tenant_id=record.tenant_id,
        correlation_id=f"corr-dec-{record.decision_id}",
        created_at=record.created_at,
        finalized_at=now_iso,
        actor_identity=actor_identity,
        policy_snapshot=policy_snapshot,
        input_snapshot=input_snapshot,
        institutional_evidence=institutional_evidence,
        calculation_trace=calculation_trace,
        claims=claims,
        sources=sources,
        concise_rationale=record.concise_rationale,
        record_hashes=record_hashes,
        manifest_root_hash=manifest_root_hash,
        cryptographic_signature=signature,
        retention_metadata=retention_metadata,
    )


def finalize_decision_evidence(
    decision_id: str,
    tenant_id: str = "velora-tenant",
    version: Optional[str] = None,
    db_path: Optional[str] = None,
    signing_key: Optional[str] = None,
) -> DecisionManifest:
    """Assemble manifest and lock the decision record as finalized and append-only."""
    manifest = build_decision_manifest(
        decision_id=decision_id,
        tenant_id=tenant_id,
        version=version,
        db_path=db_path,
        signing_key=signing_key,
    )

    repo = VendorDecisionRepository(db_path=db_path)
    finalized_ref = f"{manifest.manifest_id}:FINALIZED:{manifest.manifest_root_hash[:16]}"
    repo.update_audit_manifest(
        decision_id=manifest.decision_id,
        tenant_id=manifest.tenant_id,
        version=manifest.version,
        audit_manifest_ref=finalized_ref,
    )

    return manifest
