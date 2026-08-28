import json
import asyncio
import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace

from mcp.types import CallToolResult

import successfactors_mcp.successfactors_server as server
import successfactors_mcp.successfactors_tools as tools_module
from successfactors_mcp.adaptive_cards import decorate
from successfactors_mcp.chart_images import get_chart, HAS_PIL
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
    sf_nationality_entity = "PerPersonal"
    sf_nationality_person_id_field = "personIdExternal"
    sf_nationality_field = "nationality"
    sf_uae_nationality_codes = "ARE"
    sf_active_user_statuses = "t"
    sf_metric_rule_version = "test-v2"
    sf_small_group_threshold = 1
    enable_personal_info_tool = False


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
        self.assertEqual(params["$top"], 20)

    async def test_headcount_as_of_date_is_forwarded(self):
        client = CapturingClient()
        await client.list_emp_jobs(company="company", as_of_date="2026-08-08")
        self.assertEqual(client.calls[0][2]["asOfDate"], "2026-08-08")

    async def test_emp_job_queries_use_tenant_metadata_sequence_field(self):
        client = CapturingClient()
        await client.list_emp_jobs(company="company")
        self.assertIn("seqNumber", client.calls[0][2]["$select"])
        self.assertNotIn("seqNum,", client.calls[0][2]["$select"])

        await client.get_emp_job("employee-1", seq_num=2)
        self.assertIn("seqNumber eq 2", client.calls[1][2]["$filter"])

        await client.update_emp_job("employee-1", "2026-08-01T00:00:00", 2, {"jobTitle": "Test"})
        self.assertIn("startDate=datetime'2026-08-01T00:00:00'", client.calls[2][1])
        self.assertIn("seqNumber=2L", client.calls[2][1])

    async def test_emp_job_query_supports_exact_job_code_filter(self):
        client = CapturingClient()
        await client.list_emp_jobs(job_code="AV-ENG-04")
        self.assertIn("jobCode eq 'AV-ENG-04'", client.calls[0][2]["$filter"])

    async def test_headcount_aggregation_pages_all_rows_and_uses_department_names(self):
        client = CapturingClient([
            {"results": [
                {"externalCode": "DEP1", "name": "Finance"},
                {"externalCode": "DEP2", "name": "People & Culture"},
            ]},
            {"results": [{"userId": "one", "department": "DEP1"}, {"userId": "two", "department": "DEP2"}], "__count": "3"},
            {"results": [{"userId": "three", "department": "DEP1"}], "__count": "3"},
            {"results": [{"userId": "one", "status": "t"}, {"userId": "two", "status": "t"}, {"userId": "three", "status": "t"}], "__count": "3"},
        ])
        progress = []

        async def record_progress(value, message):
            progress.append((value, message))

        result = await client.aggregate_headcount_by_department(progress_callback=record_progress)
        self.assertEqual(result["total_headcount"], 3)
        self.assertEqual(result["rows_evaluated"], 3)
        self.assertTrue(result["aggregation_complete"])
        self.assertEqual(result["department_breakdown"][0], {
            "department": "Finance", "headcount": 2, "percentage": 66.7,
        })
        self.assertNotIn("DEP1", json.dumps(result))
        self.assertEqual(client.calls[1][2]["$skip"], 0)
        self.assertEqual(client.calls[2][2]["$skip"], 2)
        self.assertTrue(progress)

    async def test_fetch_all_continues_without_inline_count_until_short_page(self):
        client = CapturingClient([
            {"results": [{"userId": "one"}, {"userId": "two"}]},
            {"results": [{"userId": "three"}]},
        ])
        result = await client._fetch_all("User", select="userId", page_size=2)
        self.assertEqual(result["rows_returned"], 3)
        self.assertEqual(result["total_available"], 3)
        self.assertTrue(result["complete"])
        self.assertEqual(client.calls[1][2]["$skip"], 2)

    async def test_joiner_aggregation_deduplicates_and_uses_department_descriptions(self):
        client = CapturingClient([
            {"results": [{"externalCode": "DEP1", "name": "Finance"}]},
            {"results": [
                {"userId": "one", "hireDate": "/Date(1785542400000)/", "department": "DEP1"},
                {"userId": "one", "hireDate": "/Date(1785542400000)/", "department": "DEP1"},
                {"userId": "two", "hireDate": "/Date(1785628800000)/", "department": "DEP1"},
            ], "__count": "3"},
            {"results": [{"personIdExternal": "one", "nationality": "ARE"}, {"personIdExternal": "two", "nationality": "IND"}], "__count": "2"},
        ])
        result = await client.aggregate_joiners("2026-08-01", "2026-08-07", group_by="department")
        self.assertEqual(result["total_joiners"], 2)
        self.assertEqual(result["breakdown"], [{"department": "Finance", "joiners": 2}])
        self.assertIn("hireDate ge datetime'2026-08-01T00:00:00'", client.calls[1][2]["$filter"])
        self.assertIn("hireDate lt datetime'2026-08-08T00:00:00'", client.calls[1][2]["$filter"])

    async def test_joiner_aggregate_cache_avoids_repeating_odata_calls(self):
        client = CapturingClient([
            {"results": [{"externalCode": "DEP1", "name": "Finance"}]},
            {"results": [{"userId": "one", "hireDate": "/Date(1785542400000)/", "department": "DEP1"}], "__count": "1"},
            {"results": [{"personIdExternal": "one", "nationality": "ARE"}], "__count": "1"},
        ])
        first = await client.aggregate_joiners("2026-08-01", "2026-08-07", group_by="month")
        second = await client.aggregate_joiners("2026-08-01", "2026-08-07", group_by="month")
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(first["aggregate_cache"]["status"], "miss")
        self.assertEqual(second["aggregate_cache"]["status"], "hit")

    async def test_emiratisation_uses_real_aggregate_counts(self):
        client = CapturingClient([
            {"results": [{"userId": "one"}, {"userId": "two"}], "__count": "2"},
            {"results": [{"personIdExternal": "one", "nationality": "ARE"}, {"personIdExternal": "two", "nationality": "IND"}], "__count": "2"},
            {"results": [{"userId": "one", "status": "t"}, {"userId": "two", "status": "t"}], "__count": "2"},
        ])
        result = await client.get_emiratisation_kpi(company="company")
        self.assertEqual(result["total_headcount"], 2)
        self.assertEqual(result["emirati_national_count"], 1)
        self.assertEqual(result["emiratisation_ratio_percent"], 50.0)
        self.assertEqual(result["target_compliance"], "ON_TRACK")
        self.assertTrue(result["reconciliation"]["passed"])

    async def test_emiratisation_refuses_to_invent_data_without_mapping(self):
        settings = FakeSettings()
        settings.sf_nationality_entity = ""
        client = CapturingClient(settings=settings)
        result = await client.get_emiratisation_kpi()
        self.assertTrue(result["error"])
        self.assertNotIn("emiratisation_ratio_percent", result)


class ToolTests(unittest.IsolatedAsyncioTestCase):
    def test_aggregate_tool_handlers_do_not_require_conversational_filters(self):
        aggregate_names = {
            "sf__get_joiners",
            "sf__get_leavers",
            "sf__get_attrition",
            "sf__get_joiners_leavers_trend",
            "sf__get_headcount",
            "sf__get_analytics_dashboard",
            "sf__get_emiratisation_kpi",
        }
        specs = {spec["name"]: spec for spec in tools_module.TOOL_SPECS}
        for name in aggregate_names:
            signature = inspect.signature(specs[name]["handler"])
            required = [
                param_name
                for param_name, parameter in signature.parameters.items()
                if param_name != "ctx" and parameter.default is inspect.Parameter.empty
            ]
            self.assertEqual(required, [], name)

    def test_headcount_card_has_chart_image_and_text_fallbacks(self):
        original = tools_module._client.settings.public_base_url if hasattr(tools_module._client.settings, "public_base_url") else ""
        tools_module._client.settings.public_base_url = "https://charts.example"
        try:
            result = decorate({
                "type": "Headcount", "total_headcount": 3, "department_count": 2,
                "rows_evaluated": 3, "aggregation_complete": True,
                "department_breakdown": [
                    {"department": "Technology", "headcount": 2, "percentage": 66.7},
                    {"department": "Finance", "headcount": 1, "percentage": 33.3},
                ],
            })
            chart = result["adaptiveCard"]["body"][3]
            self.assertEqual(chart["type"], "Image")
            self.assertEqual(chart["fallback"]["type"], "TextBlock")
            self.assertEqual(json.loads(result["adaptiveCardJson"])["type"], "AdaptiveCard")
            self.assertEqual(result["visualizationSpec"]["template"], "ranked_horizontal_bar")
            chart_id = chart["url"].split("/")[-1].removesuffix(".png")
            chart_bytes = get_chart(chart_id)
            if HAS_PIL:
                self.assertTrue(chart_bytes.startswith(b"\x89PNG"))
            else:
                self.assertIsInstance(chart_bytes, bytes)
        finally:
            tools_module._client.settings.public_base_url = original

    def test_joiners_card_has_native_png_and_text_fallbacks(self):
        original = tools_module._client.settings.public_base_url if hasattr(tools_module._client.settings, "public_base_url") else ""
        tools_module._client.settings.public_base_url = "https://charts.example"
        try:
            result = decorate({
                "type": "JoinerAnalytics", "start_date": "2026-08-01", "end_date": "2026-08-13",
                "total_joiners": 3, "group_by": "day", "aggregation_complete": True,
                "breakdown": [{"period": "2026-08-01", "joiners": 2}, {"period": "2026-08-02", "joiners": 1}],
            })
            chart = result["adaptiveCard"]["body"][3]
            self.assertEqual(chart["type"], "Image")
            self.assertEqual(chart["fallback"]["type"], "TextBlock")
            self.assertEqual(result["chartImageUrl"], chart["url"])
            self.assertEqual(result["visualizationSpec"]["template"], "period_comparison")
            chart_id = result["chartImageUrl"].split("/")[-1].removesuffix(".png")
            chart_bytes = get_chart(chart_id)
            if HAS_PIL:
                self.assertTrue(chart_bytes.startswith(b"\x89PNG"))
            else:
                self.assertIsInstance(chart_bytes, bytes)
        finally:
            tools_module._client.settings.public_base_url = original

    async def test_tool_response_contains_structured_content(self):
        result = tools_module._json_response({"total": 1, "results": [{"name": "Example"}]})
        self.assertIsInstance(result, CallToolResult)
        self.assertEqual(result.structuredContent["total"], 1)
        self.assertIn("Records: 1", result.content[0].text)
        self.assertNotIn("adaptiveCard", result.content[0].text)
        self.assertNotIn('"type"', result.content[0].text)
        self.assertEqual(result.structuredContent["presentationPreference"], "adaptive_card")
        self.assertEqual(result.structuredContent["fallbackPresentation"], "text")
        self.assertEqual(result.structuredContent["adaptiveCard"]["type"], "AdaptiveCard")
        self.assertEqual(result.structuredContent["adaptiveCard"]["version"], "1.5")

    async def test_error_response_has_card_and_clean_fallback(self):
        result = tools_module._json_response({"error": True, "message": "backend unavailable"})
        self.assertTrue(result.isError)
        self.assertNotIn("backend unavailable", result.content[0].text)
        self.assertIn("couldn't retrieve", result.content[0].text)
        self.assertEqual(result.structuredContent["adaptiveCard"]["type"], "AdaptiveCard")
        self.assertEqual(json.loads(result.structuredContent["adaptiveCardJson"])["type"], "AdaptiveCard")
        self.assertEqual(result.structuredContent["cardDeliveryMode"], "copilot_response_semantics")

    async def test_dashboard_propagates_backend_error(self):
        original = tools_module._client

        class ErrorClient:
            async def aggregate_headcount_by_department(self, **_kwargs):
                return {"error": True, "message": "backend unavailable"}

        try:
            tools_module._client = ErrorClient()
            result = await tools_module.sf__get_analytics_dashboard()
            self.assertTrue(result.isError)
            self.assertEqual(
                result.structuredContent["message"],
                "I couldn't retrieve that information right now. Please try again shortly.",
            )
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

    async def test_headcount_is_complete_aggregate_with_visualization(self):
        original = tools_module._client

        class HeadcountClient:
            async def aggregate_headcount_by_department(self, **_kwargs):
                return {
                    "type": "Headcount",
                    "total_headcount": 3,
                    "rows_evaluated": 3,
                    "department_count": 2,
                    "aggregation_complete": True,
                    "department_breakdown": [
                        {"department": "Technology", "headcount": 2, "percentage": 66.7},
                        {"department": "Finance", "headcount": 1, "percentage": 33.3},
                    ],
                    "chart_bars": [
                        {"department": "Technology", "headcount": 2, "percentage": 66.7},
                        {"department": "Finance", "headcount": 1, "percentage": 33.3},
                    ],
                    "source": "SAP SuccessFactors · EmpJob and FODepartment",
                }

        class FakeContext:
            async def report_progress(self, *_args, **_kwargs):
                return None

        try:
            tools_module._client = HeadcountClient()
            result = await tools_module.sf__get_headcount(FakeContext(), as_of_date="2026-08-08")
            self.assertEqual(result.structuredContent["total_headcount"], 3)
            self.assertTrue(result.structuredContent["aggregation_complete"])
            self.assertEqual(result.structuredContent["department_breakdown"][0]["department"], "Technology")
            card_text = json.dumps(result.structuredContent["adaptiveCard"])
            self.assertIn("Technology", card_text)
            self.assertNotIn("UAE Preview test tenant", card_text)
        finally:
            tools_module._client = original


class ApiKeyMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def _invoke(self, headers, path="/mcp"):
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
        scope = {"type": "http", "path": path, "headers": headers}
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

            called, messages = await self._invoke([], path="/copilot/workforce-card")
            self.assertFalse(called)
            self.assertEqual(messages[0]["status"], 401)
        finally:
            server.settings = original


class CopilotCardActionTests(unittest.TestCase):
    def test_flattens_adaptive_card_and_builds_text_fallback(self):
        structured = {
            "type": "EmiratisationKPI",
            "adaptiveCard": {
                "type": "AdaptiveCard",
                "version": "1.5",
                "body": [
                    {"type": "TextBlock", "text": "Emiratisation KPI", "weight": "Bolder"},
                    {"type": "TextBlock", "text": "Aggregate workforce measure", "isSubtle": True},
                    {"type": "TextBlock", "text": "Below target", "weight": "Bolder"},
                    {"type": "FactSet", "facts": [
                        {"title": "Emiratisation", "value": "7.37%"},
                        {"title": "UAE Nationals", "value": "42"},
                    ]},
                ],
            },
        }
        payload = server._copilot_card_payload(structured, "emiratisation")
        self.assertTrue(payload["success"])
        self.assertEqual(payload["cardTitle"], "Emiratisation KPI")
        self.assertEqual(payload["fact1Value"], "7.37%")
        self.assertIn("Emiratisation: 7.37%", payload["fallbackText"])
        self.assertEqual(json.loads(payload["adaptiveCardJson"])["version"], "1.5")

    def test_error_payload_always_has_readable_fallback(self):
        payload = server._copilot_card_payload({"error": True, "message": "Source unavailable"}, "headcount")
        self.assertFalse(payload["success"])
        self.assertIn("Source unavailable", payload["fallbackText"])
        self.assertEqual(payload["fallbackPresentation"], "text")

    def test_public_plugin_manifest_points_to_deployed_openapi(self):
        self.assertEqual(server.COPILOT_OPENAPI["openapi"], "3.0.1")
        self.assertIn("/copilot/workforce-card", server.COPILOT_OPENAPI["paths"])


class ManifestTests(unittest.TestCase):
    def test_plugins_and_mcp_descriptions_match(self):
        package = Path(__file__).parents[1] / "agent" / "appPackage"
        for plugin_name, descriptions_name in (
            ("ai-plugin.json", "mcp-tools.json"),
            ("s4hana-plugin.json", "s4hana-mcp-tools.json"),
            ("sac-plugin.json", "sac-mcp-tools.json"),
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
                self.assertTrue(semantics["static_template"]["file"].startswith("adaptive-cards/") or semantics["static_template"]["file"].startswith("./adaptive-cards/"))

        agent = json.loads((package / "declarativeAgent.json").read_text())
        self.assertEqual(
            {action["file"] for action in agent["actions"]},
            {"ai-plugin.json", "s4hana-plugin.json", "sac-plugin.json", "facilitator-plugin.json", "productivity-plugin.json"},
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
        for plugin_name in ("ai-plugin.json", "s4hana-plugin.json", "sac-plugin.json", "facilitator-plugin.json"):
            plugin = json.loads((package / plugin_name).read_text())
            for function in plugin["functions"]:
                semantics = function["capabilities"]["response_semantics"]
                self.assertEqual(semantics["properties"]["template_selector"], "$.adaptiveCard")
                template = semantics["static_template"]["file"]
                self.assertTrue((package / template.removeprefix("./")).is_file())
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
