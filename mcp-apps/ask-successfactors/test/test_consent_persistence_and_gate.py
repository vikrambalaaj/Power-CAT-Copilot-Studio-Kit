"""Tests for durable consent storage in Dataverse and server-side gate enforcement."""
import unittest
from typing import Any, Dict, List, Optional

from successfactors_mcp.consent_service import ConsentService, CURRENT_NOTICE_VERSION
from successfactors_mcp.consent_gate import CONSENT_REQUIRED_TOOLS, require_consent
from successfactors_mcp.dataverse_audit import (
    AUDIT_LOG_COLUMNS,
    CONSENT_COLUMNS,
    CONSENT_ENTITY_SET,
    DataverseAuditRecord,
    DataverseClient,
    RECORD_TYPE_CONSENT,
    RECORD_TYPE_USER_TURN,
)


class FakeDataverseClient(DataverseClient):
    """DataverseClient with the HTTP transport replaced by a recording fake."""

    def __init__(self):
        super().__init__(
            base_url="https://velora.crm4.dynamics.com",
            tenant_id="tenant-guid",
            client_id="client-guid",
            client_secret="secret",
        )
        self.rows: List[Dict[str, Any]] = []
        self.requests: List[Dict[str, Any]] = []
        self.fail_next_write = False

    async def _get_access_token(self) -> str:
        return "fake-token"

    async def _request(self, method, path, *, json_body=None, params=None):
        self.requests.append({"method": method, "path": path, "params": params})
        if method == "POST":
            if self.fail_next_write:
                raise RuntimeError("Dataverse 503")
            row = dict(json_body or {})
            row["cre2f_botuserconsentid"] = f"guid-{len(self.rows) + 1}"
            self.rows.append(row)
            return row
        # GET: apply the consent filter against stored rows.
        matches = [
            row for row in self.rows
            if row.get("cre2f_consentgranted") is True
            and row.get("cre2f_consentversion") == self._version_in(params)
        ]
        return {"value": matches[-1:]}

    @staticmethod
    def _version_in(params: Optional[Dict[str, str]]) -> str:
        expr = (params or {}).get("$filter", "")
        marker = "cre2f_consentversion eq '"
        start = expr.index(marker) + len(marker)
        return expr[start:expr.index("'", start)]


class ConsentPersistenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = FakeDataverseClient()
        self.svc = ConsentService(dataverse_client=self.client)

    async def test_consent_is_written_to_the_audit_table(self):
        res = await self.svc.record_user_consent(
            user_object_id="entra-a1", user_email="exec@velora.ae", accepted=True)
        self.assertEqual(res["status"], "RECORDED")
        self.assertEqual(res["persisted_to"], "cre2f_veloraagentauditlog")

        posts = [r for r in self.client.requests if r["method"] == "POST"]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["path"], CONSENT_ENTITY_SET)

        row = self.client.rows[0]
        self.assertTrue(row["cre2f_consentgranted"])
        self.assertEqual(row["cre2f_consentversion"], CURRENT_NOTICE_VERSION)
        self.assertEqual(row["cre2f_userobjectid"], "entra-a1")
        # Every column sent must exist on cre2f_botuserconsent.
        self.assertTrue(set(row) - {"cre2f_botuserconsentid"} <= CONSENT_COLUMNS)
        # Dataverse assigns the primary key, so the id on the row is the one it
        # returned, not the locally generated AUD- placeholder.
        self.assertEqual(row["cre2f_botuserconsentid"], "guid-1")
        self.assertEqual(res["audit_id"], "guid-1")

    async def test_second_session_does_not_reprompt(self):
        await self.svc.record_user_consent(
            user_object_id="entra-a1", user_email="exec@velora.ae", accepted=True)

        # A fresh process: no in-memory buffer, only the Dataverse rows survive.
        restarted = FakeDataverseClient()
        restarted.rows = self.client.rows
        svc2 = ConsentService(dataverse_client=restarted)

        is_consented, card = await svc2.verify_user_consent(
            user_object_id="entra-a1", user_email="exec@velora.ae")
        self.assertTrue(is_consented)
        self.assertIsNone(card)
        self.assertEqual(restarted._audit_store, [])

    async def test_new_notice_version_reprompts_once(self):
        await self.svc.record_user_consent(
            user_object_id="entra-a1", user_email="exec@velora.ae", accepted=True)
        is_consented, card = await self.svc.verify_user_consent(
            user_object_id="entra-a1", user_email="exec@velora.ae",
            notice_version="2027.1")
        self.assertFalse(is_consented)
        self.assertEqual(card["type"], "AdaptiveCard")

    async def test_failed_write_reports_failure_and_stays_blocked(self):
        self.client.fail_next_write = True
        res = await self.svc.record_user_consent(
            user_object_id="entra-a2", user_email="other@velora.ae", accepted=True)
        self.assertEqual(res["status"], "FAILED")
        self.assertTrue(res["error"])

        is_consented, card = await self.svc.verify_user_consent(
            user_object_id="entra-a2", user_email="other@velora.ae")
        self.assertFalse(is_consented)
        self.assertIsNotNone(card)

    async def test_no_write_names_a_column_the_table_lacks(self):
        """The defect that broke both consent paths: sending unknown columns."""
        consent = DataverseAuditRecord(
            record_type=RECORD_TYPE_CONSENT, user_object_id="u1",
            user_email="a@velora.ae", consent_version="2026.1",
            consent_status="ACCEPTED", channel="copilot_studio")
        self.assertTrue(set(consent.to_consent_payload()) <= CONSENT_COLUMNS)

        turn = DataverseAuditRecord(
            record_type=RECORD_TYPE_USER_TURN, user_email="a@velora.ae",
            operation="headcount", outcome="SUCCESS", tool_name="sf__get_headcount",
            message_summary="How many staff?")
        audit = turn.to_audit_log_payload()
        self.assertTrue(set(audit) <= AUDIT_LOG_COLUMNS)
        # The record type has no column, so it survives on the detail field.
        self.assertIn(RECORD_TYPE_USER_TURN, audit["cre2f_auditdetail"])

    async def test_unreadable_consent_table_fails_closed(self):
        async def boom(*args, **kwargs):
            raise RuntimeError("Dataverse unreachable")
        self.client._request = boom
        record = await self.client.query_user_consent(
            "entra-a1", "exec@velora.ae", CURRENT_NOTICE_VERSION)
        self.assertIsNone(record)

    async def test_anonymous_rows_do_not_satisfy_each_other(self):
        offline = DataverseClient()  # no credentials -> in-memory buffer path
        svc = ConsentService(dataverse_client=offline)
        await svc.record_user_consent(user_object_id="", user_email="", accepted=True)
        self.assertIsNone(
            offline._match_consent_in_buffer("", "", CURRENT_NOTICE_VERSION))


class ConsentGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_gate_blocks_then_allows(self):
        client = FakeDataverseClient()
        svc = ConsentService(dataverse_client=client)

        import successfactors_mcp.consent_service as cs
        original = cs._global_consent_service
        cs._global_consent_service = svc
        try:
            async def handler(user_object_id="", user_email="", **_):
                return "EMPLOYEE_DATA"

            gated = require_consent("sf__get_workforce_drilldown")(handler)

            blocked = await gated(user_object_id="entra-b1", user_email="b1@velora.ae")
            self.assertEqual(blocked.structuredContent["type"], "ConsentRequired")
            self.assertEqual(
                blocked.structuredContent["blocked_tool"], "sf__get_workforce_drilldown")

            await svc.record_user_consent(
                user_object_id="entra-b1", user_email="b1@velora.ae", accepted=True)

            allowed = await gated(user_object_id="entra-b1", user_email="b1@velora.ae")
            self.assertEqual(allowed, "EMPLOYEE_DATA")
        finally:
            cs._global_consent_service = original

    def test_gated_tools_all_accept_identity(self):
        import inspect
        from successfactors_mcp import successfactors_tools as tools
        handlers = {spec["name"]: spec["handler"] for spec in tools.TOOL_SPECS}
        for name in CONSENT_REQUIRED_TOOLS:
            params = inspect.signature(handlers[name]).parameters
            self.assertIn("user_object_id", params, name)
            self.assertIn("user_email", params, name)


if __name__ == "__main__":
    unittest.main()
