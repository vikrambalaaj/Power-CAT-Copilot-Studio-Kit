"""HMAC-based Cryptographic Approval Token Manager for Two-Step Transactions."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple

HMAC_SECRET = os.getenv("VELORA_APPROVAL_HMAC_SECRET", "velora-prod-executive-secret-key-2026")
DEFAULT_EXPIRY_MINUTES = int(os.getenv("VeloraConfirmationExpiryMinutes", "15"))


def compute_preview_checksum(preview_data: Dict[str, Any]) -> str:
    """Compute deterministic SHA-256 checksum of core preview dictionary, excluding volatile timestamp fields."""
    volatile_fields = {"approvalExpiresOn", "expiresOn", "correlationId"}
    filtered = {k: v for k, v in preview_data.items() if k not in volatile_fields}
    normalized = json.dumps(filtered, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_token_hash_for_dataverse(token: str) -> str:
    """Compute secure HMAC-SHA256 hash of the approval token for audit storage."""
    if not token:
        return ""
    return hmac.new(HMAC_SECRET.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


class TokenManager:
    """Manages generation, validation, and integrity checking of short-lived approval tokens."""

    def __init__(self, secret: Optional[str] = None, default_expiry_minutes: int = DEFAULT_EXPIRY_MINUTES):
        self.secret = (secret or HMAC_SECRET).encode("utf-8")
        self.default_expiry_minutes = default_expiry_minutes

    def create_approval_token(
        self,
        operation: str,
        user_object_id: str,
        user_email: str,
        preview_data: Dict[str, Any],
        idempotency_key: str,
        root_correlation_id: str,
        expiry_minutes: Optional[int] = None,
    ) -> Tuple[str, str]:
        """Generate a tamper-evident, time-bound approval token.
        
        Returns:
            (token, expires_on_iso)
        """
        mins = expiry_minutes if expiry_minutes is not None else self.default_expiry_minutes
        now = datetime.now(timezone.utc)
        expires_on = now + timedelta(minutes=mins)
        expires_on_iso = expires_on.isoformat()
        expires_ts = int(expires_on.timestamp())

        preview_checksum = compute_preview_checksum(preview_data)

        payload = {
            "op": operation,
            "uid": user_object_id or "",
            "uem": (user_email or "").strip().lower(),
            "exp": expires_ts,
            "chk": preview_checksum,
            "idk": idempotency_key,
            "cid": root_correlation_id,
            "iat": int(now.timestamp()),
        }

        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")
        
        signature = hmac.new(self.secret, payload_bytes, hashlib.sha256).digest()
        sig_b64 = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")

        token = f"velora_appr.{payload_b64}.{sig_b64}"
        return token, expires_on_iso

    def verify_approval_token(
        self,
        token: str,
        expected_operation: str,
        user_object_id: str,
        user_email: str,
        current_preview_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Verify token cryptographic signature, expiry, user identity, and preview checksum.
        
        Returns:
            (is_valid, error_reason, token_payload)
        """
        if not token or not token.startswith("velora_appr."):
            return False, "Invalid token format: missing 'velora_appr.' prefix.", {}

        parts = token.split(".")
        if len(parts) != 3:
            return False, "Malformed token structure.", {}

        _, payload_b64, sig_b64 = parts

        # Decode payload
        try:
            rem = len(payload_b64) % 4
            if rem:
                payload_b64 += "=" * (4 - rem)
            payload_bytes = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
            payload = json.loads(payload_bytes.decode("utf-8"))
        except Exception as ex:
            return False, f"Corrupt token payload: {str(ex)}", {}

        # Verify signature
        try:
            expected_sig = hmac.new(self.secret, payload_bytes, hashlib.sha256).digest()
            expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).decode("utf-8").rstrip("=")
            if not hmac.compare_digest(sig_b64, expected_sig_b64):
                return False, "Token signature verification failed. Token has been tampered with.", payload
        except Exception as ex:
            return False, f"Signature verification error: {str(ex)}", payload

        # Check Expiration
        now_ts = int(time.time())
        exp_ts = payload.get("exp", 0)
        if now_ts > exp_ts:
            return False, f"Approval token has expired at timestamp {exp_ts} (current: {now_ts}).", payload

        # Check Operation Match
        token_op = payload.get("op", "").upper()
        expected_op = expected_operation.upper()
        
        def normalize_op(op_name: str) -> str:
            clean = op_name.replace("_", "").replace("-", "").upper()
            for prefix in ("SENDAPPROVED", "CREATEAPPROVED", "UPDATEAPPROVED", "CANCELAPPROVED", "COMPLETEAPPROVED", "PREPARE"):
                if clean.startswith(prefix):
                    clean = clean[len(prefix):]
                    break
            return clean

        if token_op != expected_op and normalize_op(token_op) != normalize_op(expected_op):
            return False, f"Token operation mismatch: issued for '{token_op}', presented for '{expected_operation}'.", payload

        # Check User Identity Binding
        sanitized_email = (user_email or "").strip().lower()
        token_email = (payload.get("uem") or "").strip().lower()
        token_uid = payload.get("uid", "")
        
        user_matches = False
        if token_email and sanitized_email and token_email == sanitized_email:
            user_matches = True
        elif token_uid and user_object_id and token_uid == user_object_id:
            user_matches = True
        elif not token_email and not token_uid:
            user_matches = True

        if not user_matches:
            return False, f"User identity mismatch: token issued to '{token_email}', presented by '{sanitized_email}'.", payload

        # Check Preview Checksum Integrity if preview supplied
        if current_preview_data is not None:
            current_checksum = compute_preview_checksum(current_preview_data)
            if payload.get("chk") and payload.get("chk") != current_checksum:
                return False, "Preview data has changed since approval was requested. A new approval is required.", payload

        return True, "", payload


# Global token manager
_token_manager = TokenManager()


def get_token_manager() -> TokenManager:
    return _token_manager
