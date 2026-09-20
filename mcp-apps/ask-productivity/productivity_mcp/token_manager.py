"""HMAC-based Cryptographic Approval Token Manager & Durable State Machine for Two-Step Transactions."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .operation_store import (
    OperationRecord,
    OperationState,
    compute_payload_checksum,
    get_operation_store,
    normalize_operation_type,
)

log = logging.getLogger("productivity_mcp.token_manager")


def get_hmac_secret() -> str:
    secret = os.getenv("VELORA_APPROVAL_HMAC_SECRET")
    is_prod = any(os.getenv(k, "").lower() in ("production", "prod") for k in ("VELORA_ENV", "ENVIRONMENT", "NODE_ENV"))
    if is_prod and (not secret or secret == "velora-test-approval-hmac-secret-key-32ch"):
        raise ValueError("Explicit production VELORA_APPROVAL_HMAC_SECRET is required")
    if not secret:
        is_test_env = (
            os.getenv("ALLOW_OFFLINE_TEST_TOKENS", "").lower() in ("1", "true", "yes")
            or os.getenv("PYTEST_CURRENT_TEST") is not None
        )
        if is_test_env:
            return "velora-test-approval-hmac-secret-key-32ch"
        raise ValueError("VELORA_APPROVAL_HMAC_SECRET must be configured in environment/KeyVault")
    return secret


def compute_preview_checksum(preview_data: Dict[str, Any]) -> str:
    """Compute deterministic SHA-256 checksum of core preview dictionary, excluding volatile timestamp fields."""
    return compute_payload_checksum(preview_data)


def compute_token_hash_for_dataverse(token: str) -> str:
    """Compute secure HMAC-SHA256 hash of the approval token for audit storage."""
    if not token:
        return ""
    secret = get_hmac_secret()
    return hmac.new(secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


class InvalidTokenError(Exception):
    """Raised when an approval confirmation token is invalid, expired, or tampered with."""
    pass


class TokenManager:
    """Manages generation, validation, and integrity checking of short-lived approval tokens."""

    def __init__(self, secret: Optional[str] = None, default_expiry_minutes: int = 10):
        self._secret = secret
        self.default_expiry_minutes = int(os.getenv("VELORA_CONFIRMATION_EXPIRY_MINUTES", str(default_expiry_minutes)))
        self.operation_store = get_operation_store()
        self._consumed_nonces: set[str] = set()

        storage_base = (
            os.getenv("AZURE_STORAGE_MOUNT_PATH")
            or os.getenv("VELORA_OUTBOX_DIR")
            or os.getenv("FACILITATOR_STORAGE_DIR")
            or "/mnt/velora"
        )
        self._persistence_file: Optional[Path] = None
        try:
            p_dir = Path(storage_base)
            if not p_dir.exists() and not storage_base.startswith("/mnt"):
                p_dir.mkdir(parents=True, exist_ok=True)
            if p_dir.exists():
                self._persistence_file = p_dir / "consumed_approval_nonces.jsonl"
            else:
                local_data = Path(__file__).resolve().parent.parent / "data"
                local_data.mkdir(parents=True, exist_ok=True)
                self._persistence_file = local_data / "consumed_approval_nonces.jsonl"

            if self._persistence_file.exists():
                with open(self._persistence_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                                if isinstance(data, dict) and "nonce" in data:
                                    self._consumed_nonces.add(data["nonce"])
                                elif isinstance(data, str):
                                    self._consumed_nonces.add(data)
                            except Exception:
                                pass
        except Exception as exc:
            log.warning(f"Could not load fallback nonce persistence file: {exc}")

    @property
    def secret(self) -> bytes:
        sec = self._secret or get_hmac_secret()
        return sec.encode("utf-8")

    def create_approval_token(
        self,
        operation: str,
        user_object_id: str,
        user_email: str,
        preview_data: Dict[str, Any],
        idempotency_key: str,
        root_correlation_id: str,
        tenant_id: str = "velora-tenant",
        expiry_minutes: Optional[int] = None,
    ) -> Tuple[str, str]:
        """Generate a tamper-evident, time-bound approval token bound to user identity and nonce."""
        if not user_object_id and not user_email:
            raise ValueError("Authenticated user identity (oid or email) is required for approval tokens")

        mins = expiry_minutes if expiry_minutes is not None else self.default_expiry_minutes
        now = datetime.now(timezone.utc)
        expires_on = now + timedelta(minutes=mins)
        expires_on_iso = expires_on.isoformat()
        expires_ts = int(expires_on.timestamp())
        nonce = str(uuid.uuid4())

        canonical_op = normalize_operation_type(operation)
        preview_checksum = compute_preview_checksum(preview_data)

        payload = {
            "oid": user_object_id or "",
            "tid": tenant_id or "velora-tenant",
            "operation": canonical_op,
            "previewChecksum": preview_checksum,
            "idempotencyKey": idempotency_key,
            "nonce": nonce,
            "iat": int(now.timestamp()),
            "exp": expires_ts,
            "uem": (user_email or "").strip().lower(),
            "cid": root_correlation_id,
        }

        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")
        signature = hmac.new(self.secret, payload_bytes, hashlib.sha256).digest()
        sig_b64 = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
        token = f"velora_appr.{payload_b64}.{sig_b64}"

        # Persist operation in durable store in PREPARED state (Fail-Closed: never issue token if storage fails)
        try:
            self.operation_store.prepare_operation(
                operation_type=canonical_op,
                tenant_id=tenant_id or "velora-tenant",
                user_object_id=user_object_id or user_email,
                user_email=user_email,
                proposed_payload=preview_data,
                approval_id=token,
                approval_token=token,
                expiry_minutes=mins,
            )
        except Exception as exc:
            log.error(f"Approval preparation persistence failed (fail-closed): {exc}")
            raise RuntimeError(f"Approval preparation persistence failed: {exc}") from exc

        return token, expires_on_iso

    def verify_approval_token(
        self,
        token: str,
        expected_operation: str,
        user_object_id: str,
        user_email: str,
        current_preview_data: Optional[Dict[str, Any]] = None,
        consume_nonce: bool = False,
        tenant_id: Optional[str] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Verify token cryptographic signature, expiry, user identity, and preview checksum."""
        if not token or not token.startswith("velora_appr."):
            return False, "Invalid token format: missing 'velora_appr.' prefix.", {}

        parts = token.split(".")
        if len(parts) != 3:
            return False, "Malformed token structure.", {}

        _, payload_b64, sig_b64 = parts

        try:
            rem = len(payload_b64) % 4
            if rem:
                payload_b64 += "=" * (4 - rem)
            payload_bytes = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
            payload = json.loads(payload_bytes.decode("utf-8"))
        except Exception as ex:
            return False, f"Corrupt token payload: {str(ex)}", {}

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

        # Check Nonce Replay
        nonce = payload.get("nonce", "")
        if nonce in self._consumed_nonces:
            return False, "Approval token nonce has already been consumed (replay blocked).", payload

        # Check Operation Match using strict canonical mapping
        token_op = payload.get("operation") or payload.get("op", "")
        try:
            canonical_token_op = normalize_operation_type(str(token_op))
            canonical_expected_op = normalize_operation_type(str(expected_operation))
        except ValueError as e:
            return False, str(e), payload

        if canonical_token_op != canonical_expected_op:
            return False, f"Token operation mismatch: issued for '{token_op}', presented for '{expected_operation}'.", payload

        # Check Tenant Binding if supplied
        token_tid = payload.get("tid")
        if tenant_id and token_tid and tenant_id != token_tid:
            return False, f"Tenant mismatch: token issued for tenant '{token_tid}', presented for '{tenant_id}'.", payload

        # Check User Identity Binding: empty caller identity is strictly REJECTED
        sanitized_email = (user_email or "").strip().lower()
        sanitized_uid = (user_object_id or "").strip()
        token_email = (payload.get("uem") or "").strip().lower()
        token_uid = (payload.get("oid") or payload.get("uid", "")).strip()

        if not sanitized_email and not sanitized_uid:
            return False, "Caller identity (user_object_id or user_email) cannot be empty.", payload

        user_matches = False
        if token_email and sanitized_email and token_email == sanitized_email:
            user_matches = True
        elif token_uid and sanitized_uid and token_uid == sanitized_uid:
            user_matches = True

        if not user_matches:
            return False, f"User identity mismatch: token issued to '{token_uid or token_email}', presented by '{sanitized_uid or sanitized_email}'.", payload

        # Check Preview Checksum Integrity if preview supplied
        if current_preview_data is not None:
            current_checksum = compute_preview_checksum(current_preview_data)
            chk = payload.get("previewChecksum") or payload.get("chk")
            if chk and chk != current_checksum:
                return False, "Preview data has changed since approval was requested. A new approval is required.", payload

        if consume_nonce and nonce:
            self._consumed_nonces.add(nonce)
            if self._persistence_file:
                try:
                    with open(self._persistence_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"nonce": nonce, "consumed_at": int(time.time()), "operation": canonical_token_op}) + "\n")
                except Exception:
                    pass

        return True, "", payload

    def consume_token(self, token: str) -> None:
        """Mark token nonce as consumed after successful execution."""
        parts = token.split(".")
        if len(parts) == 3:
            try:
                rem = len(parts[1]) % 4
                padded = parts[1] + ("=" * (4 - rem) if rem else "")
                payload = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))
                nonce = payload.get("nonce")
                if nonce:
                    self._consumed_nonces.add(nonce)
                    if self._persistence_file:
                        with open(self._persistence_file, "a", encoding="utf-8") as f:
                            f.write(json.dumps({"nonce": nonce, "consumed_at": int(time.time())}) + "\n")
            except Exception:
                pass


# Global token manager
_token_manager = TokenManager()


def get_token_manager() -> TokenManager:
    return _token_manager
