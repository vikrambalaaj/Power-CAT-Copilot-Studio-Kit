import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from mcp.types import CallToolResult

import successfactors_mcp.successfactors_server as server
import successfactors_mcp.successfactors_tools as tools_module
from successfactors_mcp.successfactors_client import SuccessFactorsClient


class FakeSettings:
    sf_api_url = "https://example.invalid/odata/v2"
    sf_company_id = "company"
    sf_username = "service-user"
    sf_password = "secret"
    sf_emirati_filter = "nationality eq 'Emirati'"
    sf_emiratisation_target = 40.0


class CapturingClient(SuccessFactorsClient):
    def __init__(self, responses=None, settings=None):
        super().__init__(settings or FakeSettings())
        self.calls = []
        self.responses = list(responses or [])

    async def _request(self, method, endpoint, params=None, json_data=None, executive_id=None):
        self.calls.append((method, endpoint, params, json_data))
        if self.responses:
            return self.responses.pop(0)
        return {"results": [], "__count": "0"}


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_odata_literals_are_escaped_and_top_is_bounded(self):
        client = CapturingClient()
        await client.list_users(query="O'Reilly", top=99999)
        params = client.calls[0][2]
        self.assertIn("O''Reilly", params["$filter"])
        self.assertEqual(params["$top"], 1000)

    async def test_emiratisation_uses_real_aggregate_counts(self):
        client = CapturingClient([
            {"results": [{"userId": "one"}], "__count": "200"},
            {"results": [{"userId": "one"}], "__count": "90"},
        ])
        result = await client.get_emiratisation_kpi(company="company")
        self.assertEqual(result["total_headcount"], 200)
        self.assertEqual(result["emirati_national_count"], 90)
        self.assertEqual(result["emiratisation_ratio_percent"], 45.0)
        self.assertEqual(result["target_compliance"], "ON_TRACK")

    async def test_emiratisation_refuses_to_invent_data_without_filter(self):
        settings = FakeSettings()
        settings.sf_emirati_filter = ""
        client = CapturingClient(settings=settings)
        result = await client.get_emiratisation_kpi()
        self.assertTrue(result["error"])
        self.assertEqual(client.calls, [])


class ToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_response_contains_structured_content(self):
        result = tools_module._json_response({"total": 1, "results": [{"name": "Example"}]})
        self.assertIsInstance(result, CallToolResult)
        self.assertEqual(result.structuredContent["total"], 1)
        self.assertEqual(json.loads(result.content[0].text)["total"], 1)

    async def test_dashboard_propagates_backend_error(self):
        original = tools_module._client

        class ErrorClient:
            async def list_users(self, **_kwargs):
                return {"error": True, "message": "backend unavailable"}

        try:
            tools_module._client = ErrorClient()
            result = await tools_module.sf__get_analytics_dashboard()
            self.assertTrue(result.isError)
            self.assertEqual(result.structuredContent["message"], "backend unavailable")
        finally:
            tools_module._client = original


class ApiKeyMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def _invoke(self, headers):
        called = False

        async def downstream(_scope, _receive, send):
            nonlocal called
            called = True
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        messages = []
        async def send(message):
            messages.append(message)
        middleware = server.ApiKeyMiddleware(downstream)
        scope = {"type": "http", "path": "/mcp", "headers": headers}
        await middleware(scope, lambda: None, send)
        return called, messages

    async def test_rejects_missing_key_and_accepts_valid_key(self):
        original = server.settings
        server.settings = SimpleNamespace(allow_anonymous=False, mcp_api_key="test-secret")
        try:
            called, messages = await self._invoke([])
            self.assertFalse(called)
            self.assertEqual(messages[0]["status"], 401)

            called, messages = await self._invoke([(b"x-api-key", b"test-secret")])
            self.assertTrue(called)
            self.assertEqual(messages[0]["status"], 204)
        finally:
            server.settings = original


class ManifestTests(unittest.TestCase):
    def test_plugin_and_mcp_descriptions_match(self):
        package = Path(__file__).parents[1] / "agent" / "appPackage"
        plugin = json.loads((package / "ai-plugin.json").read_text())
        descriptions = json.loads((package / "mcp-tools.json").read_text())
        names = {item["name"] for item in plugin["functions"]}
        tool_names = {item["name"] for item in descriptions["tools"]}
        runtime_names = set(plugin["runtimes"][0]["run_for_functions"])
        self.assertEqual(names, tool_names)
        self.assertEqual(names, runtime_names)
        for tool in descriptions["tools"]:
            self.assertTrue({"name", "description", "inputSchema"}.issubset(tool))


if __name__ == "__main__":
    unittest.main()
