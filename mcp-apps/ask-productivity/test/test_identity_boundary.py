"""Acceptance tests for Verified Identity Boundary (Section 2).

Tests:
1. Reject absent, malformed, expired, wrong-tenant, wrong-audience, wrong-issuer tokens
2. Reject tokens lacking required scope or role
3. Reject forged principal headers (x-ms-client-principal)
4. Reject valid application token on user-only operation
5. Reject body identity that conflicts with verified user
6. Verify authorized user token passes with correct tenant and object ID binding
"""
import base64
import hmac
import hashlib
import json
import os
import time
import unittest

from shared_mcp.identity import (
    VerifiedIdentity,
    AuthenticationError,
    AuthorizationError,
    extract_verified_identity,
    verify_bearer_token,
    verify_gateway_assertion,
    verify_body_identity_binding,
)

TEST_SECRET = "test-secret-key-32-chars-long-abc"


def make_test_jwt(
    payload: dict,
    secret: str = TEST_SECRET,
    alg: str = "HS256",
    kid: str = "test-key-1",
) -> str:
    header = {"alg": alg, "typ": "JWT", "kid": kid}
    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode("utf-8")).decode("utf-8").rstrip("=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    signed_content = f"{h_b64}.{p_b64}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed_content, hashlib.sha256).digest()
    s_b64 = base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
    return f"{h_b64}.{p_b64}.{s_b64}"


class TestIdentityBoundary(unittest.TestCase):
    def setUp(self):
        os.environ["ALLOW_OFFLINE_TEST_TOKENS"] = "true"
        os.environ["TEST_JWT_SECRET"] = TEST_SECRET
        os.environ["ENTRA_TENANT_ID"] = "7d167021-f5e9-4331-9b75-d44d55a1ce9b"
        os.environ["API_AUDIENCE"] = "https://api.velora.ae"

    def test_reject_absent_token(self):
        with self.assertRaises(AuthenticationError) as ctx:
            extract_verified_identity({}, test_secret=TEST_SECRET)
        self.assertIn("Missing Authorization", str(ctx.exception))

    def test_reject_malformed_token(self):
        with self.assertRaises(AuthenticationError):
            verify_bearer_token("not.a.valid.jwt.token", test_secret=TEST_SECRET)

    def test_reject_tampered_signature(self):
        now = int(time.time())
        token = make_test_jwt({
            "tid": "7d167021-f5e9-4331-9b75-d44d55a1ce9b",
            "oid": "user-123",
            "aud": "https://api.velora.ae",
            "exp": now + 3600,
            "sub": "user-123",
        })
        tampered = token[:-4] + "AAAA"
        with self.assertRaises(AuthenticationError) as ctx:
            verify_bearer_token(tampered, test_secret=TEST_SECRET)
        self.assertIn("signature", str(ctx.exception).lower())

    def test_reject_expired_token(self):
        now = int(time.time())
        token = make_test_jwt({
            "tid": "7d167021-f5e9-4331-9b75-d44d55a1ce9b",
            "oid": "user-123",
            "aud": "https://api.velora.ae",
            "exp": now - 60,  # Expired 1 min ago
            "sub": "user-123",
        })
        with self.assertRaises(AuthenticationError) as ctx:
            verify_bearer_token(token, test_secret=TEST_SECRET)
        self.assertIn("expired", str(ctx.exception).lower())

    def test_reject_wrong_tenant(self):
        now = int(time.time())
        token = make_test_jwt({
            "tid": "wrong-tenant-id-000",
            "oid": "user-123",
            "aud": "https://api.velora.ae",
            "exp": now + 3600,
            "sub": "user-123",
        })
        with self.assertRaises(AuthenticationError) as ctx:
            verify_bearer_token(token, test_secret=TEST_SECRET)
        self.assertIn("tenant", str(ctx.exception).lower())

    def test_reject_wrong_audience(self):
        now = int(time.time())
        token = make_test_jwt({
            "tid": "7d167021-f5e9-4331-9b75-d44d55a1ce9b",
            "oid": "user-123",
            "aud": "https://other-service.com",
            "exp": now + 3600,
            "sub": "user-123",
        })
        with self.assertRaises(AuthenticationError) as ctx:
            verify_bearer_token(token, expected_audience="https://api.velora.ae", test_secret=TEST_SECRET)
        self.assertIn("audience", str(ctx.exception).lower())

    def test_reject_missing_required_scope(self):
        now = int(time.time())
        token = make_test_jwt({
            "tid": "7d167021-f5e9-4331-9b75-d44d55a1ce9b",
            "oid": "user-123",
            "aud": "https://api.velora.ae",
            "scp": "User.Read",
            "exp": now + 3600,
            "sub": "user-123",
        })
        with self.assertRaises(AuthorizationError) as ctx:
            verify_bearer_token(token, required_scope="Executive.Write", test_secret=TEST_SECRET)
        self.assertIn("scope", str(ctx.exception).lower())

    def test_reject_missing_required_role(self):
        now = int(time.time())
        token = make_test_jwt({
            "tid": "7d167021-f5e9-4331-9b75-d44d55a1ce9b",
            "oid": "user-123",
            "aud": "https://api.velora.ae",
            "roles": ["Standard_User"],
            "exp": now + 3600,
            "sub": "user-123",
        })
        with self.assertRaises(AuthorizationError) as ctx:
            verify_bearer_token(token, required_role="Velora_Admin", test_secret=TEST_SECRET)
        self.assertIn("role", str(ctx.exception).lower())

    def test_reject_forged_principal_header_without_gateway_signature(self):
        headers = {
            "x-ms-client-principal": base64.b64encode(json.dumps({
                "claims": [{"typ": "roles", "val": "Velora_Admin"}]
            }).encode("utf-8")).decode("utf-8"),
            "x-user-roles": "Velora_Admin",
        }
        with self.assertRaises(AuthenticationError) as ctx:
            extract_verified_identity(headers, test_secret=TEST_SECRET)
        self.assertIn("unverified", str(ctx.exception).lower())

    def test_reject_application_token_on_user_only_operation(self):
        now = int(time.time())
        app_token = make_test_jwt({
            "tid": "7d167021-f5e9-4331-9b75-d44d55a1ce9b",
            "oid": "service-principal-999",
            "idtyp": "app",
            "aud": "https://api.velora.ae",
            "roles": ["Velora_Admin"],
            "exp": now + 3600,
            "sub": "service-principal-999",
        })
        with self.assertRaises(AuthorizationError) as ctx:
            verify_bearer_token(app_token, require_user_principal=True, test_secret=TEST_SECRET)
        self.assertIn("user principal", str(ctx.exception).lower())

    def test_reject_body_identity_conflict(self):
        identity = VerifiedIdentity(
            tenant_id="7d167021-f5e9-4331-9b75-d44d55a1ce9b",
            object_id="user-real-123",
            principal_type="user",
            client_application_id="app-1",
            display_email="balaadm@velora.ae",
        )
        # 1. Matching identity passes
        verify_body_identity_binding(identity, body_user_id="user-real-123", body_email="balaadm@velora.ae")

        # 2. Conflicting user ID fails
        with self.assertRaises(AuthorizationError) as ctx:
            verify_body_identity_binding(identity, body_user_id="user-attacker-666", body_email="balaadm@velora.ae")
        self.assertIn("identity conflicts", str(ctx.exception))

        # 3. Conflicting email fails
        with self.assertRaises(AuthorizationError) as ctx:
            verify_body_identity_binding(identity, body_user_id="user-real-123", body_email="victim@velora.ae")
        self.assertIn("email conflicts", str(ctx.exception))

    def test_verified_delegated_user_token_success(self):
        now = int(time.time())
        token = make_test_jwt({
            "tid": "7d167021-f5e9-4331-9b75-d44d55a1ce9b",
            "oid": "user-bala-123",
            "aud": "https://api.velora.ae",
            "scp": "Executive.Send Mail.ReadWrite",
            "roles": ["Velora_Executive", "Velora_Admin"],
            "preferred_username": "balaadm@velora.ae",
            "name": "Bala Admin",
            "exp": now + 3600,
            "sub": "user-bala-123",
        })
        identity = verify_bearer_token(
            token,
            required_scope="Executive.Send",
            required_role="Velora_Executive",
            require_user_principal=True,
            test_secret=TEST_SECRET,
        )
        self.assertEqual(identity.tenant_id, "7d167021-f5e9-4331-9b75-d44d55a1ce9b")
        self.assertEqual(identity.object_id, "user-bala-123")
        self.assertTrue(identity.is_user)
        self.assertTrue(identity.is_admin)
        self.assertEqual(identity.display_email, "balaadm@velora.ae")
        self.assertEqual(identity.identity_tuple, ("7d167021-f5e9-4331-9b75-d44d55a1ce9b", "user-bala-123"))

    def test_handoff_rejects_missing_auth(self):
        from starlette.testclient import TestClient
        from productivity_mcp.server import app
        client = TestClient(app)
        res = client.post("/handoff", json={
            "task": "Search priority mail",
            "operation": "SEARCH_MAIL",
            "rootCorrelationId": "corr-1",
            "conversationId": "conv-1",
            "turnId": "turn-1",
            "parameters": {"query": "test"},
            "userObjectId": "user-123",
            "userEmail": "user@velora.ae",
        })
        self.assertEqual(res.status_code, 401)

    def test_handoff_rejects_unverified_principal_headers(self):
        from starlette.testclient import TestClient
        from productivity_mcp.server import app
        client = TestClient(app)
        res = client.post("/handoff", json={
            "task": "Search priority mail",
            "operation": "SEARCH_MAIL",
            "rootCorrelationId": "corr-1",
            "conversationId": "conv-1",
            "turnId": "turn-1",
            "parameters": {"query": "test"},
            "userObjectId": "user-123",
            "userEmail": "user@velora.ae",
        }, headers={"x-ms-client-principal": "fake-header"})
        self.assertEqual(res.status_code, 401)

    def test_handoff_rejects_body_identity_conflict(self):
        from starlette.testclient import TestClient
        from productivity_mcp.server import app
        client = TestClient(app)
        now = int(time.time())
        token = make_test_jwt({
            "tid": "7d167021-f5e9-4331-9b75-d44d55a1ce9b",
            "oid": "user-bala-123",
            "aud": "https://api.velora.ae",
            "preferred_username": "balaadm@velora.ae",
            "exp": now + 3600,
            "sub": "user-bala-123",
        })
        # Token says user-bala-123, body requests attacker-666
        res = client.post("/handoff", json={
            "task": "Search priority mail",
            "operation": "SEARCH_MAIL",
            "rootCorrelationId": "corr-1",
            "conversationId": "conv-1",
            "turnId": "turn-1",
            "parameters": {"query": "test"},
            "userObjectId": "attacker-666",
            "userEmail": "balaadm@velora.ae",
        }, headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 403)


if __name__ == "__main__":
    unittest.main()
