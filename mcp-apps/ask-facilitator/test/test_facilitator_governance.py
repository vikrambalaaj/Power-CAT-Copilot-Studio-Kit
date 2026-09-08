"""Acceptance tests for Facilitator Governance, Write Protection, and Truthful Endpoints (Section 4).

Tests:
1. Direct unauthenticated invocation cannot access business tools (401 Unauthorized)
2. Health check remains accessible without auth
3. Mutating tools reject GET requests (405 Method Not Allowed)
4. Authenticated non-admin cannot configure policy (403 Forbidden)
5. Strict HTML escaping prevents XSS / prompt injection in meeting summaries
6. Recipient policy rejects unapproved external domains
7. Email send requires verified approval confirmation token
"""
import os
import unittest
from starlette.testclient import TestClient

from facilitator_mcp.server import app
from facilitator_mcp.tools import (
    draft_meeting_summary_email,
    validate_recipient_policy,
    send_executive_email_via_graph,
)
from shared_mcp.identity import verify_bearer_token

TEST_SECRET = "test-secret-facilitator-32-chars"


import base64
import hmac
import hashlib
import json
import time

def make_test_jwt(payload: dict, secret: str = TEST_SECRET) -> str:
    header = {"alg": "HS256", "typ": "JWT", "kid": "test-key"}
    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode("utf-8")).decode("utf-8").rstrip("=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    signed_content = f"{h_b64}.{p_b64}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed_content, hashlib.sha256).digest()
    s_b64 = base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
    return f"{h_b64}.{p_b64}.{s_b64}"


class TestFacilitatorGovernance(unittest.TestCase):
    def setUp(self):
        os.environ["ALLOW_ANONYMOUS"] = "false"
        os.environ["ALLOW_OFFLINE_TEST_TOKENS"] = "true"
        os.environ["TEST_JWT_SECRET"] = TEST_SECRET
        self.client = TestClient(app)

    def test_health_accessible_unauthenticated(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "ok")

    def test_unauthenticated_tool_rejected(self):
        res = self.client.get("/get_facilitator_guide")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["error"], "Unauthorized")

    def test_mutating_tool_rejects_get(self):
        # Even with valid auth, GET on a mutating tool is 405
        token = make_test_jwt({
            "tid": "7d167021-f5e9-4331-9b75-d44d55a1ce9b",
            "oid": "admin-1",
            "aud": "https://api.velora.ae",
            "roles": ["Velora_Admin"],
            "exp": int(time.time()) + 3600,
            "sub": "admin-1",
        }, secret=TEST_SECRET)

        res = self.client.get(
            "/send_executive_email_via_graph",
            headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(res.status_code, 405)
        self.assertIn("Method Not Allowed", res.json()["error"])

    def test_non_admin_cannot_configure_policy(self):
        user_token = make_test_jwt({
            "tid": "7d167021-f5e9-4331-9b75-d44d55a1ce9b",
            "oid": "user-standard",
            "aud": "https://api.velora.ae",
            "roles": ["Standard_User"],
            "exp": int(time.time()) + 3600,
            "sub": "user-standard",
        }, secret=TEST_SECRET)


        res = self.client.post(
            "/configure_auto_send_policy",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"agent_name": "TestAgent"},
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("Velora_Admin", res.json()["message"])


    def test_html_escaping_in_draft_email(self):
        xss_payload = "<script>alert('pwned')</script>"
        res = draft_meeting_summary_email(
            topic=xss_payload,
            attendees=["victim@velora.ae", "<b>attacker</b>@velora.ae"],
            key_decisions=["<img src=x onerror=alert(1)>", "Valid decision"],
            action_items=[{"task": "<script>evil()</script>", "owner": "<iframe src='evil.com'>", "due": "2026-10-01"}],
            notes="<style>body{display:none}</style>",
        )
        body = res["body_html"]
        # Raw tags must not appear unescaped
        self.assertNotIn("<script>", body)
        self.assertNotIn("<img src=x", body)
        self.assertNotIn("<iframe", body)
        self.assertNotIn("<style>", body)
        # Escaped entities must appear
        self.assertIn("&lt;script&gt;", body)
        self.assertIn("&lt;img src=x", body)

    def test_recipient_policy_rejects_unapproved_domain(self):
        valid, violations = validate_recipient_policy(["attacker@external-evil.com"])
        self.assertFalse(valid)
        self.assertTrue(any("external-evil.com" in v for v in violations))

        # Approved domain passes
        valid2, _ = validate_recipient_policy(["executive@velora.ae"])
        self.assertTrue(valid2)

    def test_send_executive_email_requires_confirmation_token(self):
        res = send_executive_email_via_graph(
            to_recipients=["executive@velora.ae"],
            subject="Important",
            body_html="<p>Test</p>",
            confirmation_token=None,
        )
        self.assertEqual(res["status"], "APPROVAL_REQUIRED")
        self.assertIn("verified confirmation token", res["message"])


if __name__ == "__main__":
    unittest.main()
