"""Shared Verified Identity & Authentication Module for Velora Executive Platform.

Enforces:
- Entra ID JWT / OAuth2 Access Token validation (issuer, audience, alg, exp, nbf, tid, sub/oid)
- Required 'exp' and exact issuer matching (no prefix leniency)
- Maintained PyJWT verification with rotating key / JWKS discovery support
- Elimination of automatic test-mode / PYTEST_CURRENT_TEST bypasses in production logic
- Distinction between delegated user tokens and application tokens
- Identity binding by (tenant_id, object_id)
- Rejection of forged client principal headers
- Gateway signature verification with method, path, and body binding with nonce replay defense
- Body identity conflict detection (rejects request-body identity tampering)
- Generic 401/403 responses without sensitive token or claims leakage
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

log = logging.getLogger("shared_mcp.identity")

# Algorithms permitted in production
ALLOWED_ALGORITHMS = ["RS256", "ES256"]
TEST_ALLOWED_ALGORITHMS = ["RS256", "ES256", "HS256"]

# Default / Configured Tenant & Audience
DEFAULT_TENANT_ID = os.getenv("ENTRA_TENANT_ID") or os.getenv("AZURE_TENANT_ID") or "7d167021-f5e9-4331-9b75-d44d55a1ce9b"
DEFAULT_AUDIENCE = os.getenv("API_AUDIENCE") or os.getenv("ENTRA_CLIENT_ID") or "https://api.velora.ae"

# Nonce cache for gateway assertions to prevent replay
_GATEWAY_NONCE_CACHE: Dict[str, float] = {}
GATEWAY_NONCE_TTL_SECONDS = 300.0

# Cached JWKS client
_JWKS_CLIENT = None


@dataclass(frozen=True)
class VerifiedIdentity:
    """Immutable verified identity extracted from cryptographically verified token or gateway assertion."""
    tenant_id: str
    object_id: str
    principal_type: str  # "user" | "application"
    client_application_id: str
    scopes: Set[str] = field(default_factory=set)
    roles: Set[str] = field(default_factory=set)
    display_email: Optional[str] = None
    username: Optional[str] = None
    subject: str = ""
    raw_claims: Dict[str, Any] = field(default_factory=dict)

    @property
    def identity_tuple(self) -> Tuple[str, str]:
        """Stable partition key: (tenant_id, object_id)."""
        return (self.tenant_id, self.object_id)

    @property
    def is_user(self) -> bool:
        return self.principal_type == "user"

    @property
    def is_admin(self) -> bool:
        return "Velora_Admin" in self.roles or "Admin" in self.roles or "GlobalAdmin" in self.roles


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    def __init__(self, message: str = "Unauthorized", status_code: int = 401):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AuthorizationError(Exception):
    """Raised when authorized permissions are insufficient."""
    def __init__(self, message: str = "Forbidden", status_code: int = 403):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _b64_decode(data: str) -> bytes:
    rem = len(data) % 4
    if rem:
        data += "=" * (4 - rem)
    return base64.urlsafe_b64decode(data.encode("utf-8"))


def parse_unverified_token(token: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Decode JWT header and payload without cryptographic verification."""
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise AuthenticationError("Invalid token format")
    try:
        header = json.loads(_b64_decode(parts[0]).decode("utf-8"))
        payload = json.loads(_b64_decode(parts[1]).decode("utf-8"))
        return header, payload
    except Exception as exc:
        raise AuthenticationError("Malformed token structure") from exc


def _get_jwks_client(tenant_id: str):
    global _JWKS_CLIENT
    if _JWKS_CLIENT is not None:
        return _JWKS_CLIENT
    try:
        import jwt
        jwks_uri = os.getenv("ENTRA_JWKS_URI") or f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
        _JWKS_CLIENT = jwt.PyJWKClient(jwks_uri, cache_keys=True, max_cached_keys=16)
        return _JWKS_CLIENT
    except Exception as e:
        log.warning(f"Could not initialize PyJWKClient: {e}")
        return None


def verify_bearer_token(
    token: str,
    expected_audience: Optional[str] = None,
    expected_tenant_id: Optional[str] = None,
    required_scope: Optional[str] = None,
    required_role: Optional[str] = None,
    require_user_principal: bool = False,
    test_secret: Optional[str] = None,
) -> VerifiedIdentity:
    """Cryptographically verify an Entra ID JWT access token."""
    if not token or not isinstance(token, str):
        raise AuthenticationError("Missing token")

    token = token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    header, payload = parse_unverified_token(token)

    alg = header.get("alg")
    configured_test_secret = test_secret or os.getenv("TEST_JWT_SECRET")
    is_prod = (
        os.getenv("ENVIRONMENT", "").lower() in ("production", "prod")
        or os.getenv("NODE_ENV", "").lower() == "production"
        or os.getenv("VELORA_ENV", "").lower() in ("production", "prod")
    )

    if is_prod and (configured_test_secret or alg == "HS256"):
        log.error("Test signing keys and symmetric secrets are strictly prohibited in production")
        raise AuthenticationError("Test signing keys are disallowed in production")

    # Algorithm enforcement: HS256 is ONLY allowed if test secret is explicitly provided
    if alg == "HS256":
        if not configured_test_secret:
            log.warning("Rejected HS256 token without configured test verification key")
            raise AuthenticationError("Invalid token algorithm: symmetric keys not allowed in production")
    elif alg not in ALLOWED_ALGORITHMS:
        log.warning(f"Rejected token with unauthorized algorithm: {alg}")
        raise AuthenticationError("Invalid token algorithm")

    # Verify signature
    parts = token.split(".")
    signed_content = f"{parts[0]}.{parts[1]}".encode("utf-8")
    sig_bytes = _b64_decode(parts[2])

    if alg == "HS256":
        expected_sig = hmac.new(configured_test_secret.encode("utf-8"), signed_content, hashlib.sha256).digest()
        if not hmac.compare_digest(sig_bytes, expected_sig):
            raise AuthenticationError("Invalid token signature")
    else:
        # RS256 / ES256 verification using PyJWT
        try:
            import jwt
            signing_key = os.getenv("ENTRA_PUBLIC_KEY") or configured_test_secret
            if not signing_key:
                kid = header.get("kid")
                client = _get_jwks_client(expected_tenant_id or DEFAULT_TENANT_ID)
                if client and kid:
                    signing_key = client.get_signing_key_from_jwt(token).key

            if not signing_key:
                raise AuthenticationError("Signing keys unavailable for token verification")

            jwt.decode(
                token,
                signing_key,
                algorithms=[alg],
                options={"verify_aud": False, "verify_exp": False},
            )
        except AuthenticationError:
            raise
        except Exception as exc:
            log.warning(f"JWT signature verification failed: {exc}")
            raise AuthenticationError("Invalid token signature") from exc

    # Enforce Required Expiry claim ('exp')
    now = time.time()
    exp = payload.get("exp")
    if exp is None:
        raise AuthenticationError("Token missing expiration claim (exp)")
    if not isinstance(exp, (int, float)):
        raise AuthenticationError("Invalid expiration claim format")
    if now > (exp + 30):  # 30 second clock skew tolerance
        raise AuthenticationError("Token has expired")

    nbf = payload.get("nbf")
    if nbf is not None and now < (nbf - 30):
        raise AuthenticationError("Token not yet valid")

    # Enforce Tenant
    tid = payload.get("tid")
    expected_tid = expected_tenant_id or os.getenv("ENTRA_TENANT_ID") or DEFAULT_TENANT_ID
    if expected_tid and tid != expected_tid:
        log.warning(f"Tenant mismatch: token tid={tid}, expected={expected_tid}")
        raise AuthenticationError("Invalid tenant")

    # Enforce Exact Issuer matching (no prefix leniency)
    iss = payload.get("iss", "")
    if not iss:
        if not configured_test_secret:
            raise AuthenticationError("Token missing issuer claim (iss)")
    else:
        expected_issuers = {
            f"https://login.microsoftonline.com/{expected_tid}/v2.0",
            f"https://sts.windows.net/{expected_tid}/",
        }
        if configured_test_secret and (iss.startswith("https://test.") or "test" in iss):
            if is_prod:
                raise AuthenticationError("Test issuers are disallowed in production")
            pass  # Test harness mock issuer
        elif iss not in expected_issuers:
            log.warning(f"Issuer mismatch: token iss={iss}, expected one of {expected_issuers}")
            raise AuthenticationError("Invalid token issuer")

    # Enforce Audience
    aud = payload.get("aud")
    if expected_audience:
        configured_audiences = {expected_audience}
    else:
        configured_audiences = {
            os.getenv("ENTRA_INBOUND_AUDIENCE"),
            os.getenv("API_AUDIENCE"),
            os.getenv("ENTRA_CLIENT_ID"),
            DEFAULT_AUDIENCE,
        }
    configured_audiences.discard(None)
    configured_audiences.discard("")
    allowed_audiences = set(configured_audiences)
    for a in list(configured_audiences):
        allowed_audiences.add(f"api://{a}")

    if allowed_audiences:
        valid_aud = False
        if isinstance(aud, list):
            valid_aud = any(a in allowed_audiences for a in aud)
        elif isinstance(aud, str):
            valid_aud = aud in allowed_audiences
        if not valid_aud:
            log.warning(f"Audience mismatch: token aud={aud}, expected one of {allowed_audiences}")
            raise AuthenticationError("Invalid token audience")

    # Extract Subject & Identity
    oid = payload.get("oid") or payload.get("sub") or ""
    if not oid:
        raise AuthenticationError("Missing required subject/object identifier in token")

    # Distinguish Delegated User Token vs Application Token
    principal_type = "user"
    idtyp = payload.get("idtyp")
    if idtyp == "app" or ("roles" in payload and "scp" not in payload and not payload.get("upn") and not payload.get("preferred_username") and not payload.get("email")):
        principal_type = "application"

    if require_user_principal and principal_type != "user":
        log.warning(f"Application token rejected on user-only operation (oid={oid})")
        raise AuthorizationError("Operation requires an executive user principal, not an application principal")

    # Extract Scopes & Roles
    scopes = set()
    raw_scp = payload.get("scp")
    if isinstance(raw_scp, str):
        scopes = set(raw_scp.split())
    elif isinstance(raw_scp, list):
        scopes = set(raw_scp)

    roles = set()
    raw_roles = payload.get("roles")
    if isinstance(raw_roles, list):
        roles = set(raw_roles)
    elif isinstance(raw_roles, str):
        roles = {raw_roles}

    # Enforce Required Scopes / Roles
    if required_scope and required_scope not in scopes:
        log.warning(f"Missing required scope '{required_scope}' (present: {scopes})")
        raise AuthorizationError(f"Missing required scope: {required_scope}")

    if required_role and required_role not in roles:
        log.warning(f"Missing required role '{required_role}' (present: {roles})")
        raise AuthorizationError(f"Missing required role: {required_role}")

    client_app_id = payload.get("appid") or payload.get("azp") or ""
    display_email = payload.get("preferred_username") or payload.get("email") or payload.get("upn")
    if display_email:
        display_email = display_email.strip().lower()

    return VerifiedIdentity(
        tenant_id=tid or expected_tid or "velora-tenant",
        object_id=oid,
        principal_type=principal_type,
        client_application_id=client_app_id,
        scopes=scopes,
        roles=roles,
        display_email=display_email,
        username=payload.get("name"),
        subject=payload.get("sub", oid),
        raw_claims=payload,
    )


def verify_gateway_assertion(
    headers: Dict[str, str],
    required_role: Optional[str] = None,
    method: Optional[str] = None,
    path: Optional[str] = None,
    body: Optional[bytes] = None,
) -> VerifiedIdentity:
    """Verify trusted API Gateway authentication signature.
    
    Binds HTTP method, request path, body hash, timestamp skew (< 300s), and nonce replay.
    Signature check is enforced BEFORE claiming or recording nonces.
    """
    gateway_secret = os.getenv("GATEWAY_AUTH_SECRET")
    if not gateway_secret:
        raise AuthenticationError("Gateway authentication not configured on server")

    sig = headers.get("x-gateway-signature") or headers.get("x-gateway-auth")
    ts_str = headers.get("x-gateway-timestamp", "")
    nonce = headers.get("x-gateway-nonce", "")

    if not sig or not ts_str or not nonce:
        raise AuthenticationError("Missing required gateway signature headers")

    try:
        ts = float(ts_str)
    except ValueError:
        raise AuthenticationError("Invalid gateway timestamp")

    now = time.time()
    if abs(now - ts) > GATEWAY_NONCE_TTL_SECONDS:
        raise AuthenticationError("Gateway signature has expired or timestamp skew too large")

    principal_raw = headers.get("x-ms-client-principal", "")
    tenant_id = headers.get("x-gateway-tenant-id", DEFAULT_TENANT_ID)
    object_id = headers.get("x-gateway-user-id", "")
    user_email = headers.get("x-gateway-user-email", "")
    roles_str = headers.get("x-user-roles", "")

    req_method = (method or headers.get("x-gateway-method", "")).upper()
    req_path = path or headers.get("x-gateway-path", "")
    req_body_hash = hashlib.sha256(body).hexdigest() if body is not None else headers.get("x-gateway-body-sha256", "")

    # Build canonical string with method, path, and body hash when available
    if req_method or req_path or req_body_hash:
        canonical_data = f"{req_method}:{req_path}:{req_body_hash}:{ts_str}:{nonce}:{principal_raw}:{tenant_id}:{object_id}:{user_email}:{roles_str}".encode("utf-8")
        expected_sig = hmac.new(gateway_secret.encode("utf-8"), canonical_data, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            raise AuthenticationError("Invalid gateway authorization signature: request binding mismatch or tampered payload")
    else:
        canonical_data = f"{ts_str}:{nonce}:{principal_raw}:{tenant_id}:{object_id}:{user_email}:{roles_str}".encode("utf-8")
        expected_sig = hmac.new(gateway_secret.encode("utf-8"), canonical_data, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            raise AuthenticationError("Invalid gateway authorization signature")

    # Nonce replay check AFTER signature has been verified
    cleaned_cache = {k: exp for k, exp in _GATEWAY_NONCE_CACHE.items() if exp > now}
    _GATEWAY_NONCE_CACHE.clear()
    _GATEWAY_NONCE_CACHE.update(cleaned_cache)

    nonce_key = f"{tenant_id}:{nonce}"
    if nonce_key in _GATEWAY_NONCE_CACHE:
        raise AuthenticationError("Gateway assertion nonce replay detected")
    _GATEWAY_NONCE_CACHE[nonce_key] = now + GATEWAY_NONCE_TTL_SECONDS

    # Parse validated roles
    roles = set()
    if roles_str:
        roles = {r.strip() for r in roles_str.split(",") if r.strip()}

    if principal_raw:
        try:
            decoded = json.loads(base64.b64decode(principal_raw).decode("utf-8"))
            for claim in decoded.get("claims", []):
                typ = claim.get("typ")
                val = claim.get("val")
                if typ in {"roles", "http://schemas.microsoft.com/ws/2008/06/identity/claims/role"} and val:
                    roles.add(str(val).strip())
                elif typ in {"http://schemas.microsoft.com/identity/claims/objectidentifier", "oid"} and val and not object_id:
                    object_id = str(val).strip()
                elif typ in {"http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress", "email", "upn"} and val and not user_email:
                    user_email = str(val).strip().lower()
        except Exception:
            pass

    if not object_id:
        object_id = f"gateway-user-{hashlib.sha256(user_email.encode('utf-8')).hexdigest()[:16]}" if user_email else "gateway-user"

    if required_role and required_role not in roles:
        raise AuthorizationError(f"Missing required role: {required_role}")

    return VerifiedIdentity(
        tenant_id=tenant_id,
        object_id=object_id,
        principal_type="user",
        client_application_id="api-gateway",
        scopes={"user_impersonation"},
        roles=roles,
        display_email=user_email or None,
        username=user_email,
        subject=object_id,
        raw_claims={"gateway_verified": True},
    )


def extract_verified_identity(
    headers: Dict[str, str],
    required_scope: Optional[str] = None,
    required_role: Optional[str] = None,
    require_user_principal: bool = False,
    test_secret: Optional[str] = None,
    method: Optional[str] = None,
    path: Optional[str] = None,
    body: Optional[bytes] = None,
) -> VerifiedIdentity:
    """Main identity extraction entrypoint for REST and MCP requests."""
    norm_headers = {k.lower(): v for k, v in headers.items()}

    auth_header = norm_headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return verify_bearer_token(
            auth_header,
            required_scope=required_scope,
            required_role=required_role,
            require_user_principal=require_user_principal,
            test_secret=test_secret,
        )

    if "x-gateway-signature" in norm_headers or "x-gateway-auth" in norm_headers:
        return verify_gateway_assertion(
            norm_headers,
            required_role=required_role,
            method=method,
            path=path,
            body=body,
        )

    if "x-ms-client-principal" in norm_headers or "x-user-roles" in norm_headers:
        log.warning("Rejected unverified principal headers without gateway signature")
        raise AuthenticationError("Unverified principal headers rejected")

    raise AuthenticationError("Missing Authorization Bearer token")


def verify_body_identity_binding(
    identity: VerifiedIdentity,
    body_user_id: Optional[str] = None,
    body_email: Optional[str] = None,
) -> None:
    """Enforce that caller-supplied request body identity does not conflict with verified identity."""
    if body_user_id and body_user_id.strip():
        if body_user_id.strip() != identity.object_id:
            log.warning(
                f"Body identity conflict: body.userObjectId='{body_user_id}' does not match token.objectId='{identity.object_id}'"
            )
            raise AuthorizationError("Request body user identity conflicts with authenticated token identity")

    if body_email and body_email.strip() and identity.display_email:
        sanitized_body_email = body_email.strip().lower()
        if sanitized_body_email != identity.display_email:
            log.warning(
                f"Body email conflict: body.userEmail='{sanitized_body_email}' does not match token.display_email='{identity.display_email}'"
            )
            raise AuthorizationError("Request body user email conflicts with authenticated token identity")
