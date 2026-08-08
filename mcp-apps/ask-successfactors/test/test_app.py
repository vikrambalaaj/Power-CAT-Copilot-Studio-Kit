import json
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace

from mcp.types import CallToolResult

import successfactors_mcp.successfactors_server as server
import successfactors_mcp.successfactors_tools as tools_module
from successfactors_mcp.successfactors_client import SuccessFactorsClient
from successfactors_mcp.cache import AsyncTTLCache
from shared_mcp.file_logger import _result_payload


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
    async def test_cache_hits_are_isolated_and_errors_are_not_cached(self):
        cache = AsyncTTLCache(enabled=True, ttl_seconds=30, max_entries=2)
        calls = 0

        async def load_success():
            nonlocal calls
            calls += 1
            return {"results": [{"value": 1}]}

        first, first_info = await cache.get_or_load("same", load_success)
        first["results"][0]["value"] = 99
        second, second_info = await cache.get_or_load("same", load_success)
        self.assertEqual(calls, 1)
        self.assertEqual(first_info.status, "miss")
        self.assertEqual(second_info.status, "hit")
        self.assertEqual(second["results"][0]["value"], 1)

        async def load_error():
            nonlocal calls
            calls += 1
            return {"error": True}

        await cache.get_or_load("error", load_error, cacheable=lambda value: not value.get("error"))
        await cache.get_or_load("error", load_error, cacheable=lambda value: not value.get("error"))
        self.assertEqual(calls, 3)

    async def test_cache_coalesces_simultaneous_misses(self):
        cache = AsyncTTLCache(enabled=True, ttl_seconds=30, max_entries=2)
        calls = 0

        async def load():
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            return {"value": 1}

        results = await asyncio.gather(
            cache.get_or_load("same", load),
            cache.get_or_load("same", load),
        )
        self.assertEqual(calls, 1)
        self.assertEqual({item[1].status for item in results}, {"miss", "coalesced"})

    async def test_odata_literals_are_escaped_and_top_is_bounded(self):
        client = CapturingClient()
        await client.list_users(query="O'Reilly", top=99999)
        params = client.calls[0][2]
        self.assertIn("O''Reilly", params["$filter"])
        self.assertEqual(params["$top"], 1000)

    async def test_headcount_as_of_date_is_forwarded(self):
        client = CapturingClient()
        await client.list_emp_jobs(as_of_date="2026-08-08")
        self.assertEqual(client.calls[0][2]["asOfDate"], "2026-08-08")

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
        self.assertEqual(result.structuredContent["adaptiveCard"]["type"], "AdaptiveCard")
        self.assertEqual(result.structuredContent["adaptiveCard"]["version"], "1.5")

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

    def test_file_log_drops_hcm_record_payloads(self):
        result = tools_module._json_response({
            "type": "User",
            "total": 1,
            "results": [{"firstName": "Private", "email": "private@example.com"}],
        })
        payload = _result_payload(result)
        self.assertEqual(payload, {"type": "User", "total": 1})

    async def test_headcount_is_aggregate_and_marks_sampling(self):
        original = tools_module._client

        class HeadcountClient:
            async def list_emp_jobs(self, **_kwargs):
                return {"total": 3, "results": [{"department": "IT"}, {"department": "IT"}]}

        try:
            tools_module._client = HeadcountClient()
            result = await tools_module.sf__get_headcount(as_of_date="2026-08-08")
            self.assertEqual(result.structuredContent["total_headcount"], 3)
            self.assertTrue(result.structuredContent["sampled"])
            self.assertEqual(result.structuredContent["department_breakdown_sample"]["IT"], 2)
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
    def test_plugins_and_mcp_descriptions_match(self):
        package = Path(__file__).parents[1] / "agent" / "appPackage"
        for plugin_name, descriptions_name in (
            ("ai-plugin.json", "mcp-tools.json"),
            ("s4hana-plugin.json", "s4hana-mcp-tools.json"),
        ):
            plugin = json.loads((package / plugin_name).read_text())
            descriptions = json.loads((package / descriptions_name).read_text())
            names = {item["name"] for item in plugin["functions"]}
            tool_names = {item["name"] for item in descriptions["tools"]}
            runtime_names = set(plugin["runtimes"][0]["run_for_functions"])
            self.assertEqual(names, tool_names)
            self.assertEqual(names, runtime_names)
            for tool in descriptions["tools"]:
                self.assertTrue({"name", "description", "inputSchema"}.issubset(tool))
            for function in plugin["functions"]:
                semantics = function["capabilities"]["response_semantics"]
                self.assertEqual(semantics["properties"]["template_selector"], "$.adaptiveCard")
                self.assertTrue(semantics["static_template"]["file"].startswith("./adaptive-cards/"))

        agent = json.loads((package / "declarativeAgent.json").read_text())
        self.assertEqual(
            {action["file"] for action in agent["actions"]},
            {"ai-plugin.json", "s4hana-plugin.json"},
        )
        self.assertEqual(
            {capability["name"] for capability in agent["capabilities"]},
            {
                "OneDriveAndSharePoint",
                "TeamsMessages",
                "Email",
                "EmailActions",
                "People",
                "Meetings",
                "CodeInterpreter",
            },
        )
        self.assertLessEqual(len(agent["conversation_starters"]), 12)
        self.assertLessEqual(len((package / "instruction.txt").read_text()), 8000)
        cards = list((package / "adaptive-cards").glob("*.json"))
        self.assertGreaterEqual(len(cards), 14)
        for card_path in cards:
            card = json.loads(card_path.read_text())
            self.assertEqual(card["type"], "AdaptiveCard")
            self.assertEqual(card["version"], "1.5")

    def test_scheduled_prompt_catalog_is_complete(self):
        root = Path(__file__).parents[1]
        config = json.loads((root / "automation" / "scheduled-prompts.json").read_text())
        schedules = config["schedules"]
        self.assertEqual(
            {item["id"] for item in schedules},
            {"daily-plan", "midday-follow-ups", "end-of-day", "weekly-executive-brief"},
        )
        self.assertEqual(config["timeZone"], "Asia/Dubai")
        self.assertEqual(config["delivery"]["emailMode"], "draft_only_until_user_confirmation")
        for item in schedules:
            self.assertTrue((root / "automation" / item["promptFile"]).is_file())
            self.assertTrue((root / "automation" / item["cardTemplate"]).resolve().is_file())
            self.assertIn("{targetUser}", item["deduplicationKey"])


if __name__ == "__main__":
    unittest.main()
