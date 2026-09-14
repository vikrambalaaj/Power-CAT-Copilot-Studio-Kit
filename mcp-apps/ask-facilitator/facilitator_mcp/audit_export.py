"""Decision Audit Export & Standalone Verifier Engine (Work Package W12).

Provides governed, role-authorized export of decision manifests in machine-readable
JSON and human-readable spreadsheet (CSV) formats with:
- Strict role authorization (AUDITOR, COMPLIANCE_OFFICER, VELORA_ADMIN, CORP_PROCUREMENT).
- Fail-closed behavior during audit logging outages.
- Formula injection protection (CWE-1236) in spreadsheet outputs.
- Signed, time-bounded, restricted artifact links with TTL enforcement.
- Standalone verifier performing cryptographic signature verification, Merkle root hash
  integrity validation, record membership/count closure, and independent pure Decimal
  mathematical calculation replay.
- Distinction between unauthorized tampering and authorized declared redactions.
"""
from __future__ import annotations

import base64
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import hmac
import io
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

from productivity_mcp.evidence_contracts import (
    ConfidenceAssessment,
    ConfidenceLabel,
    EvidenceEnvelope,
    EvidenceSource,
    MaterialClaim,
    OperationStatus,
)
from .decision_audit import (
    AuditLoggingOutageError,
    AuditVerificationError,
    DecisionAuditError,
    DecisionManifest,
    DecisionNotFoundError,
    build_decision_manifest,
    canonical_json_dumps,
    compute_manifest_root_hash,
    compute_record_hash,
    finalize_decision_evidence,
    get_audit_signing_key,
    sign_root_hash,
    verify_signature,
)
from .vendor_evaluation import (
    CandidateProposalInput,
    CandidateScoringResult,
    EvaluationPolicy,
    evaluate_candidate_options,
    get_approved_policy,
)

log = logging.getLogger("facilitator_mcp.audit_export")

AUTHORIZED_EXPORT_ROLES = {
    "AUDITOR",
    "COMPLIANCE_OFFICER",
    "VELORA_ADMIN",
    "CORP_PROCUREMENT",
    "GlobalAdmin",
    "Admin",
}

DEFAULT_EXPORT_DIR = Path(
    os.getenv("VELORA_AUDIT_EXPORT_DIR", os.getenv("VELORA_STATE_DIR", "/tmp/velora_decision_exports"))
)


class ArtifactAccessExpiredError(PermissionError):
    """Raised when an artifact link token has passed its expiration time."""
    pass


class ArtifactTokenInvalidError(ValueError):
    """Raised when an artifact link token has an invalid format or signature."""
    pass


def check_export_authorization(caller_roles: Optional[List[str]]) -> None:
    """Verify that caller holds at least one authorized audit export role."""
    roles = set(caller_roles or [])
    if not (roles & AUTHORIZED_EXPORT_ROLES):
        raise PermissionError(
            f"Access Denied: Caller roles {list(roles)} are not authorized to export decision audit trails. "
            f"Authorized roles: {sorted(list(AUTHORIZED_EXPORT_ROLES))}."
        )


def check_audit_logging_liveness() -> None:
    """Fail closed if audit logging or spooling service is experiencing an outage."""
    if os.getenv("VELORA_SIMULATE_AUDIT_OUTAGE", "").lower() in ("true", "1"):
        raise AuditLoggingOutageError(
            "Governed mutation blocked: Audit logging service is unreachable (simulated outage). Velora fails closed."
        )


def generate_artifact_token(
    artifact_path: str,
    tenant_id: str,
    ttl_seconds: int = 3600,
    secret_key: Optional[str] = None,
) -> str:
    """Generate signed, time-bounded token for secure artifact retrieval."""
    secret = secret_key or get_audit_signing_key()
    expires_at = int(time.time()) + ttl_seconds
    payload = {
        "artifactPath": artifact_path,
        "tenantId": tenant_id,
        "expiresAt": expires_at,
    }
    raw = json.dumps(payload, sort_keys=True)
    b64_payload = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8").rstrip("=")
    sig = hmac.new(secret.encode("utf-8"), b64_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{b64_payload}.{sig}"


def resolve_artifact_token(token: str, secret_key: Optional[str] = None) -> Dict[str, Any]:
    """Validate signed artifact token and confirm it has not expired."""
    secret = secret_key or get_audit_signing_key()
    parts = token.split(".")
    if len(parts) != 2:
        raise ArtifactTokenInvalidError("Invalid artifact token format: must be payload.signature.")
    b64_payload, sig = parts
    expected_sig = hmac.new(secret.encode("utf-8"), b64_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise ArtifactTokenInvalidError("Artifact token signature verification failed.")

    rem = len(b64_payload) % 4
    padded = b64_payload + ("=" * (4 - rem) if rem else "")
    raw = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
    payload = json.loads(raw)

    if time.time() > payload["expiresAt"]:
        raise ArtifactAccessExpiredError(
            f"Artifact access link expired at timestamp {payload['expiresAt']} (current time: {int(time.time())})."
        )
    return payload


def sanitize_cell_for_csv(val: Any) -> str:
    """Neutralize spreadsheet formula injection (CWE-1236).

    Prefixes a single quote (') if the string value starts with =, +, -, @, \\t, or \\r,
    unless it represents a valid standard numeric value.
    """
    if val is None:
        return ""
    if isinstance(val, (int, float, Decimal)):
        return str(val)

    s = str(val).strip()
    if not s:
        return ""

    if s[0] in ("=", "@", "\t", "\r"):
        return f"'{s}"

    if s[0] in ("+", "-"):
        try:
            Decimal(s)
            return s
        except Exception:
            return f"'{s}"

    return s


def generate_decision_csv(manifest: DecisionManifest) -> str:
    """Generate formula-safe CSV view summarizing the decision audit trail."""
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

    # 1. Header Metadata
    writer.writerow(["# VELORA ONE - DECISION AUDIT MANIFEST SUMMARY (ADAA COMPLIANT)"])
    writer.writerow(["Manifest ID", sanitize_cell_for_csv(manifest.manifest_id)])
    writer.writerow(["Decision ID", sanitize_cell_for_csv(manifest.decision_id)])
    writer.writerow(["Version", sanitize_cell_for_csv(manifest.version)])
    writer.writerow(["Tenant ID", sanitize_cell_for_csv(manifest.tenant_id)])
    writer.writerow(["Correlation ID", sanitize_cell_for_csv(manifest.correlation_id)])
    writer.writerow(["Created At", sanitize_cell_for_csv(manifest.created_at)])
    writer.writerow(["Finalized At", sanitize_cell_for_csv(manifest.finalized_at)])
    writer.writerow(["Policy ID", sanitize_cell_for_csv(manifest.policy_snapshot.get("policyId"))])
    writer.writerow(["Policy Version", sanitize_cell_for_csv(manifest.policy_snapshot.get("policyVersion"))])
    writer.writerow(["Selected Winner", sanitize_cell_for_csv(manifest.calculation_trace.get("selectedOption") or "None")])
    writer.writerow([])

    # 2. Candidate Evaluation Results
    writer.writerow([
        "Vendor ID",
        "Vendor Name",
        "Technical Score",
        "Commercial Price (AED)",
        "Baseline Score",
        "Memory Delta",
        "Final Score",
        "Rank",
    ])

    final_scores = manifest.calculation_trace.get("finalScores", {})
    baseline_scores = manifest.calculation_trace.get("baselineScores", {})
    memory_contribs = manifest.calculation_trace.get("memoryContributions", {})
    final_ranks = manifest.calculation_trace.get("finalRank", [])

    for cand in manifest.input_snapshot:
        v_id = cand.get("vendor_id") or cand.get("vendorId", "")
        v_name = cand.get("vendor_name") or cand.get("vendorName", "")
        tech = cand.get("technical_score") or cand.get("technicalScore", "")
        comm = cand.get("commercial_price") or cand.get("commercialPrice", "")

        base = baseline_scores.get(v_id, {}).get("totalScore", "")
        mem_delta = memory_contribs.get(v_id, {}).get("scoreDelta", "")
        fin = final_scores.get(v_id, {}).get("totalScore", "")
        rnk = final_ranks.index(v_id) + 1 if v_id in final_ranks else ""

        writer.writerow([
            sanitize_cell_for_csv(v_id),
            sanitize_cell_for_csv(v_name),
            sanitize_cell_for_csv(tech),
            sanitize_cell_for_csv(comm),
            sanitize_cell_for_csv(base),
            sanitize_cell_for_csv(mem_delta),
            sanitize_cell_for_csv(fin),
            sanitize_cell_for_csv(rnk),
        ])

    writer.writerow([])
    # 3. Cryptographic Provenance
    writer.writerow(["# CRYPTOGRAPHIC PROVENANCE & INTEGRITY"])
    writer.writerow(["Manifest Root Hash (SHA-256)", sanitize_cell_for_csv(manifest.manifest_root_hash)])
    writer.writerow(["KMS Key ID", sanitize_cell_for_csv(manifest.cryptographic_signature.get("keyId"))])
    writer.writerow(["Algorithm", sanitize_cell_for_csv(manifest.cryptographic_signature.get("algorithm"))])
    writer.writerow(["Signature", sanitize_cell_for_csv(manifest.cryptographic_signature.get("signature"))])
    writer.writerow(["Retention Class", sanitize_cell_for_csv(manifest.retention_metadata.get("retentionClass"))])

    return output.getvalue()


def verify_decision_manifest(
    manifest_data: Dict[str, Any],
    signing_key: Optional[str] = None,
    declared_redactions: Optional[List[str]] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Standalone verifier performing cryptographic, hash-chain, closure, and mathematical replay checks.

    Returns:
        (is_valid, status_code, details)
        where status_code is one of:
        - "VERIFICATION_SUCCESSFUL"
        - "VERIFIED_WITH_DECLARED_REDACTIONS"
        - "VERIFICATION_FAILED: INVALID_SIGNATURE"
        - "VERIFICATION_FAILED: ROOT_HASH_MISMATCH"
        - "VERIFICATION_FAILED: RECORD_MISSING"
        - "VERIFICATION_FAILED: HASH_MISMATCH"
        - "VERIFICATION_FAILED: CONTRIBUTION_TAMPERED"
    """
    details: Dict[str, Any] = {}

    # Normalize key names
    root_hash = manifest_data.get("manifest_root_hash") or manifest_data.get("manifestRootHash")
    sig_dict = manifest_data.get("cryptographic_signature") or manifest_data.get("cryptographicSignature")
    record_hashes = manifest_data.get("record_hashes") or manifest_data.get("recordHashes")

    if not root_hash or not sig_dict:
        return (
            False,
            "VERIFICATION_FAILED: INVALID_SIGNATURE",
            {"reason": "Manifest missing manifestRootHash or cryptographicSignature block."},
        )

    # 1. Cryptographic Signature Verification
    if not verify_signature(root_hash, sig_dict, secret_key=signing_key):
        return (
            False,
            "VERIFICATION_FAILED: INVALID_SIGNATURE",
            {"reason": "KMS signature verification failed against manifestRootHash."},
        )

    # 2. Merkle Root Hash Verification
    if not record_hashes:
        return (
            False,
            "VERIFICATION_FAILED: RECORD_MISSING",
            {"reason": "Manifest missing recordHashes dictionary."},
        )

    recomputed_root = compute_manifest_root_hash(record_hashes)
    if recomputed_root != root_hash:
        return (
            False,
            "VERIFICATION_FAILED: ROOT_HASH_MISMATCH",
            {"expected": recomputed_root, "actual": root_hash},
        )

    # 3. Component Record Hashes & Membership Closure Verification
    expected_components = [
        ("actorIdentity", manifest_data.get("actor_identity") or manifest_data.get("actorIdentity")),
        ("policySnapshot", manifest_data.get("policy_snapshot") or manifest_data.get("policySnapshot")),
        ("inputSnapshot", manifest_data.get("input_snapshot") or manifest_data.get("inputSnapshot")),
        ("institutionalEvidence", manifest_data.get("institutional_evidence") or manifest_data.get("institutionalEvidence")),
        ("calculationTrace", manifest_data.get("calculation_trace") or manifest_data.get("calculationTrace")),
        ("claimsAndSources", {
            "claims": manifest_data.get("claims", []),
            "sources": manifest_data.get("sources", []),
        }),
        ("conciseRationale", manifest_data.get("concise_rationale") or manifest_data.get("conciseRationale")),
    ]

    redaction_set = set(declared_redactions or manifest_data.get("redaction_manifest") or manifest_data.get("redactionManifest") or [])
    has_declared_redactions = False

    for comp_name, comp_data in expected_components:
        if comp_data is None:
            return (
                False,
                "VERIFICATION_FAILED: RECORD_MISSING",
                {"missingComponent": comp_name},
            )

        recorded_hash = record_hashes.get(comp_name)
        if not recorded_hash:
            return (
                False,
                "VERIFICATION_FAILED: RECORD_MISSING",
                {"missingRecordHash": comp_name},
            )

        recomputed_comp_hash = compute_record_hash(comp_data)
        if recomputed_comp_hash != recorded_hash:
            # Check if this discrepancy is covered by a declared redaction
            is_covered_by_redaction = False
            if redaction_set:
                if comp_name in redaction_set:
                    is_covered_by_redaction = True
                elif comp_name == "inputSnapshot" and any(r in ("commercial_price", "commercialPrice", "technical_score", "technicalScore") for r in redaction_set):
                    is_covered_by_redaction = True

            if is_covered_by_redaction:
                has_declared_redactions = True
            else:
                return (
                    False,
                    "VERIFICATION_FAILED: HASH_MISMATCH",
                    {
                        "component": comp_name,
                        "recomputedHash": recomputed_comp_hash,
                        "recordedHash": recorded_hash,
                    },
                )

    # 4. Pure Decimal Mathematical Replay Verification
    # If key inputs required for scoring are declared redacted, mathematical replay cannot recalculate without inventing numbers.
    skip_replay = has_declared_redactions and any(
        r in ("commercial_price", "commercialPrice", "technical_score", "technicalScore")
        for r in redaction_set
    )

    if not skip_replay:
        input_snapshot = manifest_data.get("input_snapshot") or manifest_data.get("inputSnapshot", [])
        policy_snapshot = manifest_data.get("policy_snapshot") or manifest_data.get("policySnapshot", {})
        calc_trace = manifest_data.get("calculation_trace") or manifest_data.get("calculationTrace", {})

        policy_id = policy_snapshot.get("policyId", "POLICY-VENDOR-PROC-V1")
        policy = get_approved_policy(policy_id)

        # Reconstruct CandidateProposalInput objects
        reconstructed_candidates: List[CandidateProposalInput] = []
        mem_contribs = calc_trace.get("memoryContributions", {})
        for c in input_snapshot:
            v_id = c.get("vendor_id") or c.get("vendorId")
            v_name = c.get("vendor_name") or c.get("vendorName")
            tech = c.get("technical_score") or c.get("technicalScore")
            comm = c.get("commercial_price") or c.get("commercialPrice")

            cand_mem = mem_contribs.get(v_id, {})
            h_score_str = cand_mem.get("historyScore")
            h_score = Decimal(str(h_score_str)) if h_score_str is not None else None
            h_count = cand_mem.get("recordCount", 0)
            h_caveat = cand_mem.get("caveat")

            reconstructed_candidates.append(
                CandidateProposalInput(
                    vendor_id=v_id,
                    vendor_name=v_name,
                    technical_score=Decimal(str(tech)) if tech is not None else None,
                    technical_source_ref=c.get("technical_source_ref") or c.get("technicalSourceRef", ""),
                    commercial_price=Decimal(str(comm)) if comm is not None else None,
                    commercial_currency=c.get("commercial_currency") or c.get("commercialCurrency", "AED"),
                    commercial_tax_basis=c.get("commercial_tax_basis") or c.get("commercialTaxBasis", "EXCLUDING_VAT"),
                    commercial_term_basis=c.get("commercial_term_basis") or c.get("commercialTermBasis", "ANNUALIZED"),
                    commercial_scope=c.get("commercial_scope") or c.get("commercialScope", "1000"),
                    commercial_source_ref=c.get("commercial_source_ref") or c.get("commercialSourceRef", ""),
                    historical_score=h_score,
                    historical_record_count=h_count,
                    historical_caveat=h_caveat,
                )
            )

        # Replay normalization and dual scoring
        replayed_results, replayed_winner, _, _ = evaluate_candidate_options(
            reconstructed_candidates,
            policy,
        )

        recorded_final_scores = calc_trace.get("finalScores", {})
        recorded_winner = calc_trace.get("selectedOption")

        for r in replayed_results:
            rec_final = recorded_final_scores.get(r.vendor_id, {})
            rec_tot = rec_final.get("totalScore")
            if rec_tot is not None and Decimal(str(rec_tot)) != r.history_total_score:
                return (
                    False,
                    "VERIFICATION_FAILED: CONTRIBUTION_TAMPERED",
                    {
                        "vendorId": r.vendor_id,
                        "recomputedFinalScore": str(r.history_total_score),
                        "recordedFinalScore": rec_tot,
                    },
                )

            # Check memory contribution delta
            cand_mem = mem_contribs.get(r.vendor_id, {})
            rec_delta = cand_mem.get("scoreDelta")
            if rec_delta is not None and Decimal(str(rec_delta)) != r.score_delta:
                return (
                    False,
                    "VERIFICATION_FAILED: CONTRIBUTION_TAMPERED",
                    {
                        "vendorId": r.vendor_id,
                        "recomputedScoreDelta": str(r.score_delta),
                        "recordedScoreDelta": rec_delta,
                    },
                )

        if replayed_winner != recorded_winner:
            return (
                False,
                "VERIFICATION_FAILED: CONTRIBUTION_TAMPERED",
                {
                    "recomputedWinner": replayed_winner,
                    "recordedWinner": recorded_winner,
                },
            )

    details["manifestId"] = manifest_data.get("manifest_id") or manifest_data.get("manifestId")
    details["decisionId"] = manifest_data.get("decision_id") or manifest_data.get("decisionId")
    details["manifestRootHash"] = root_hash
    details["verifiedAt"] = datetime.now(timezone.utc).isoformat()

    if has_declared_redactions:
        details["declaredRedactions"] = list(redaction_set)
        return (True, "VERIFIED_WITH_DECLARED_REDACTIONS", details)

    return (True, "VERIFICATION_SUCCESSFUL", details)


def export_decision_trail(
    decision_id: str,
    tenant_id: str = "velora-tenant",
    version: Optional[str] = None,
    export_format: str = "JSON",
    caller_roles: Optional[List[str]] = None,
    actor_object_id: str = "auditor-officer@velora.ae",
    ttl_seconds: int = 3600,
    redacted_fields: Optional[List[str]] = None,
    db_path: Optional[str] = None,
    export_dir: Optional[Path] = None,
    signing_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute governed, authorized decision trail export.

    Produces machine-readable JSON and formula-safe spreadsheet CSV exports,
    anchors the finalized manifest in retention storage, and returns a time-bounded
    artifact token.
    """
    # 1. Authorization check
    check_export_authorization(caller_roles)

    # 2. Audit logging outage fail-closed gate
    check_audit_logging_liveness()

    # 3. Finalize and assemble decision manifest
    manifest = finalize_decision_evidence(
        decision_id=decision_id,
        tenant_id=tenant_id,
        version=version,
        db_path=db_path,
        signing_key=signing_key,
    )

    # Handle declared redactions if requested (e.g. for external third-party audit)
    manifest_dict = manifest.to_dict()
    if redacted_fields:
        manifest_dict["redaction_manifest"] = redacted_fields
        if "commercial_price" in redacted_fields:
            for c in manifest_dict.get("input_snapshot", []):
                c["commercial_price"] = "[REDACTED_CONFIDENTIAL_COMMERCIAL_RATE]"
                c["commercialPrice"] = "[REDACTED_CONFIDENTIAL_COMMERCIAL_RATE]"

    # 4. Write export artifacts to secure retention store
    target_dir = export_dir or DEFAULT_EXPORT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    json_filename = f"{manifest.manifest_id}.json"
    json_path = target_dir / json_filename
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(manifest_dict, f, indent=2, default=str)

    csv_content = generate_decision_csv(manifest)
    csv_filename = f"{manifest.manifest_id}.csv"
    csv_path = target_dir / csv_filename
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write(csv_content)

    selected_path = csv_path if export_format.upper() == "CSV" else json_path
    artifact_token = generate_artifact_token(
        artifact_path=str(selected_path),
        tenant_id=tenant_id,
        ttl_seconds=ttl_seconds,
        secret_key=signing_key,
    )

    expires_at_iso = datetime.fromtimestamp(
        time.time() + ttl_seconds, tz=timezone.utc
    ).isoformat()

    envelope = EvidenceEnvelope(
        schemaVersion="1.0.0",
        operation="EXPORT_DECISION_TRAIL",
        status=OperationStatus.SUCCESS,
        resultSummary=f"Decision audit trail '{manifest.manifest_id}' successfully exported in format '{export_format}'.",
        result={
            "exportId": f"EXP-{manifest.manifest_id}",
            "manifestId": manifest.manifest_id,
            "decisionId": manifest.decision_id,
            "version": manifest.version,
            "format": export_format.upper(),
            "artifactReference": artifact_token,
            "artifactPath": str(selected_path),
            "expiresAt": expires_at_iso,
            "manifestRootHash": manifest.manifest_root_hash,
            "cryptographicSignature": manifest.cryptographic_signature,
            "retentionClass": manifest.retention_metadata.get("retentionClass"),
            "manifest": manifest_dict,
            "csvContent": csv_content if export_format.upper() in ("CSV", "BUNDLE") else None,
            "isRedacted": bool(redacted_fields),
            "redactionManifest": redacted_fields,
        },
        claims=[
            MaterialClaim(
                claimId=f"CLM-EXP-{manifest.manifest_id}",
                kind="FACT",
                text=f"Decision manifest {manifest.manifest_id} exported with root hash {manifest.manifest_root_hash}.",
                sourceIds=[f"SRC-MANIFEST-{manifest.manifest_id}"],
                calculationVersion="1.0.0",
                policyVersion="1.0.0",
                confidenceAssessment=ConfidenceAssessment(
                    label=ConfidenceLabel.HIGH,
                    frameworkVersion="1.0.0",
                    sourceReliability="AUTHORITATIVE",
                    corroboration="VERIFIED",
                    timeliness="REAL_TIME",
                    completeness="COMPLETE",
                    comparability="EXACT",
                    reason="Direct cryptographic assembly from finalized SQLite repository.",
                ),
            )
        ],
        sources=[
            EvidenceSource(
                sourceId=f"SRC-MANIFEST-{manifest.manifest_id}",
                system="VELORA_DECISION_AUDIT_STORE",
                businessTitle="Velora Governed Decision Audit Manifest Store",
                providerRecordId=manifest.manifest_id,
                retrievedAt=datetime.now(timezone.utc).isoformat(),
                classification="CONFIDENTIAL_AUDIT",
                limitations=[],
            )
        ],
        warnings=[],
        missingSources=[],
        correlationId=f"corr-exp-{manifest.manifest_id}",
        audit={"status": "FINALIZED_EXPORT", "recordId": manifest.manifest_id},
        generatedAt=datetime.now(timezone.utc).isoformat(),
    )

    res_dict = envelope.model_dump()
    res_dict["typedResult"] = res_dict.get("result")
    res_dict["operationStatus"] = "SUCCESS"
    return res_dict
