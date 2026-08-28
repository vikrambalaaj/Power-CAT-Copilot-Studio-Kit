import unittest
from datetime import date
from types import SimpleNamespace

from mcp.types import CallToolResult

import s4hana_mcp.server as server
import s4hana_mcp.tools as tools
from s4hana_mcp.client import S4Client, bounded_top, escape_odata, validate_relative_entity


class FakeSettings:
    s4_api_url = "https://s4.example.invalid/sap/opu/odata/sap"
    s4_auth_mode = "basic"
    s4_token_url = ""
    s4_client_id = ""
    s4_client_secret = ""
    s4_username = "reader"
    s4_password = "secret"
    s4_ar_entity = "AR_SRV/Set"
    s4_ap_entity = "AP_SRV/Set"
    s4_pl_entity = "PL_SRV/Set"
    s4_pl_api_url = "https://s4.example.invalid/sap/opu/odata/pl"
    s4_pl_gl_account_hierarchy = "ZVOP"
    s4_pl_planning_category = "ACT01"
    s4_budget_api_url = "https://s4.example.invalid/sap/opu/odata/budget"
    s4_budget_entity = "BUDGET_SRV/Set"
    executing_identity = "velora-s4-finance-test-reader"
    authorization_model = "MAKER_SERVICE_CREDENTIAL"


class CapturingClient(S4Client):
    def __init__(self):
        super().__init__(FakeSettings())
        self.call = None
        self.call_count = 0

    async def _request(self, entity, params, base_url=None):
        self.call_count += 1
        self.call = (entity, params)
        return {"rows": [{"Amount": 10}], "count": 1}



class ClientTests(unittest.IsolatedAsyncioTestCase):
    def test_validates_https_and_entities(self):
        self.assertEqual(S4Client(FakeSettings()).validate(), [])
        self.assertEqual(validate_relative_entity("SERVICE/EntitySet"), "SERVICE/EntitySet")
        with self.assertRaises(ValueError):
            validate_relative_entity("../private")
        with self.assertRaises(ValueError):
            validate_relative_entity("https://attacker.example/collect")

    def test_escaping_and_bounds(self):
        self.assertEqual(escape_odata("O'Reilly"), "O''Reilly")
        self.assertEqual(bounded_top(9999), 500)

    async def test_query_builds_allowlisted_filter_and_envelope(self):
        client = CapturingClient()
        result = await client.query("AR_SRV/Set", "ReceivablesAging", {"CompanyCode": "1000", "Customer": "O'Reilly"})
        self.assertIn("O''Reilly", client.call[1]["$filter"])
        self.assertEqual(result["source"]["system"], "SAP S/4HANA")
        self.assertEqual(result["data"]["total"], 1)

    async def test_identical_queries_use_cache_and_preserve_source_time(self):
        client = CapturingClient()
        first = await client.query("AR_SRV/Set", "ReceivablesAging", {"CompanyCode": "1000"})
        second = await client.query("AR_SRV/Set", "ReceivablesAging", {"CompanyCode": "1000"})
        self.assertEqual(client.call_count, 1)
        self.assertEqual(first["cache"]["status"], "miss")
        self.assertEqual(second["cache"]["status"], "hit")
        self.assertEqual(first["source"]["asOf"], second["source"]["asOf"])


class ToolTests(unittest.IsolatedAsyncioTestCase):
    def test_exactly_four_read_tools_are_exposed(self):
        self.assertEqual(
            {item[0] for item in tools.TOOL_SPECS},
            {
                "s4__get_receivables_aging",
                "s4__get_payables_aging",
                "s4__get_profit_and_loss",
                "s4__get_budget_variance",
            },
        )

    async def test_tool_schemas_do_not_require_variadic_kwargs(self):
        exposed = await server.mcp.list_tools()
        for tool in exposed:
            self.assertNotIn("kwargs", tool.inputSchema.get("properties", {}))
            self.assertNotIn("kwargs", tool.inputSchema.get("required", []))

    async def test_tool_returns_structured_content(self):
        original = tools.client
        fake = CapturingClient()
        tools.client = fake
        try:
            result = await tools.s4__get_receivables_aging("1000", date.today().isoformat())
            self.assertIsInstance(result, CallToolResult)
            self.assertFalse(result.isError)
            self.assertEqual(result.structuredContent["type"], "ReceivablesAging")
            self.assertEqual(result.structuredContent["adaptiveCard"]["type"], "AdaptiveCard")
            self.assertEqual(result.structuredContent["adaptiveCard"]["version"], "1.5")
        finally:
            tools.client = original

    async def test_upstream_error_is_reported_as_mcp_error(self):
        result = tools.response({"status": "error", "code": "S4_UPSTREAM_ERROR", "message": "failed"})
        self.assertTrue(result.isError)

    async def test_historical_aging_date_fails_closed(self):
        result = await tools.s4__get_receivables_aging("1000", "2020-01-01")
        self.assertTrue(result.isError)
        self.assertEqual(result.structuredContent["code"], "HISTORICAL_AGING_UNAVAILABLE")

    async def test_invalid_finance_periods_return_structured_errors(self):
        pl_result = await tools.s4__get_profit_and_loss(fiscal_year="20x6", fiscal_period="abc")
        budget_result = await tools.s4__get_budget_variance(fiscal_period="17")
        self.assertTrue(pl_result.isError)
        self.assertEqual(pl_result.structuredContent["code"], "INVALID_FISCAL_PERIOD")
        self.assertTrue(budget_result.isError)
        self.assertEqual(budget_result.structuredContent["code"], "INVALID_FISCAL_PERIOD")

    async def test_budget_uses_live_service_field_names(self):
        original = tools.client
        fake = CapturingClient()
        tools.client = fake
        try:
            await tools.s4__get_budget_variance("1000", "2026", "008", "0")
            filters = fake.call[1]["$filter"]
            self.assertIn("FinMgmtAreaFiscalYear eq '2026'", filters)
            self.assertIn("FinMgmtAreaPeriod eq '8'", filters)
            self.assertNotIn("PlanVersion", filters)
        finally:
            tools.client = original


class MiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def _invoke(self, headers):
        called = False
        messages = []

        async def downstream(_scope, _receive, send):
            nonlocal called
            called = True
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = server.ApiKeyMiddleware(downstream)

        async def send(message):
            messages.append(message)

        await middleware({"type": "http", "path": "/mcp", "headers": headers}, lambda: None, send)
        return called, messages

    async def test_api_key(self):
        original = server.settings
        server.settings = SimpleNamespace(allow_anonymous=False, mcp_api_key="test-secret")
        try:
            called, messages = await self._invoke([])
            self.assertFalse(called)
            self.assertEqual(messages[0]["status"], 401)
            called, _ = await self._invoke([(b"x-api-key", b"test-secret")])
            self.assertTrue(called)
        finally:
            server.settings = original


class AppRouteTests(unittest.TestCase):
    def test_native_mcp_and_legacy_rest_routes_are_available(self):
        app = server.create_app()
        route_paths = {getattr(route, "path", "") for route in app.routes}
        self.assertIn("/mcp/tools", route_paths)
        self.assertIn("/s4__get_payables_aging", route_paths)
        self.assertIn("/tools/s4__get_payables_aging", route_paths)
        self.assertIn("/", route_paths)


if __name__ == "__main__":
    unittest.main()
