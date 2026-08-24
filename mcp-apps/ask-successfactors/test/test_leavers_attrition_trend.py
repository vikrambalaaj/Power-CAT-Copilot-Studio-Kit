"""Deterministic tests for verified leaver, attrition, and movement-trend contracts."""
import unittest
from datetime import date

import successfactors_mcp.successfactors_tools as tools_module
from successfactors_mcp.successfactors_client import SuccessFactorsClient
from successfactors_mcp.adaptive_cards import decorate


class FakeSettings:
    sf_api_url = "https://example.invalid/odata/v2"
    sf_company_id = "company"
    sf_username = "service-user"
    sf_password = "secret"
    sf_emiratisation_target = 40.0
    sf_nationality_entity = "PerPersonal"
    sf_nationality_person_id_field = "personIdExternal"
    sf_nationality_field = "nationality"
    sf_uae_nationality_codes = "ARE"
    sf_active_user_statuses = "t"
    sf_metric_rule_version = "test-v2"
    sf_small_group_threshold = 1


class LeaverClient(SuccessFactorsClient):
    def __init__(self):
        super().__init__(FakeSettings())

    async def _fetch_all(self, entity, **_kwargs):
        if entity != "EmpEmployment":
            raise AssertionError(entity)
        return {
            "results": [
                {"userId": "one", "endDate": "/Date(1785542400000)/"},
                {"userId": "two", "endDate": "/Date(1785628800000)/"},
            ],
            "complete": True,
            "page_caches": [],
        }


class AttritionClient(SuccessFactorsClient):
    def __init__(self):
        super().__init__(FakeSettings())

    async def aggregate_headcount_by_department(self, **_kwargs):
        return {"active_headcount": 100, "active_population_definition": "test active population"}

    async def aggregate_leavers(self, **_kwargs):
        return {
            "total_leavers": 2,
            "voluntary_leavers": None,
            "involuntary_leavers": None,
            "unclassified_leavers": 2,
            "warnings": ["Reasons unavailable"],
        }

    async def _fetch_all(self, entity, **_kwargs):
        if entity == "EmpEmployment":
            return {"results": [{"userId": "one"}, {"userId": "two"}], "complete": True}
        if entity == "EmpJob":
            return {"results": [{"userId": "one"}, {"userId": "three"}], "complete": True}
        raise AssertionError(entity)

    async def _nationality_map(self, **_kwargs):
        return {"mapping": {"one": "ARE", "two": "IND", "three": "ARE"}}

    async def _active_user_ids(self, **_kwargs):
        return {"ids": {"one", "three"}}


class TrendClient(SuccessFactorsClient):
    def __init__(self):
        super().__init__(FakeSettings())

    async def aggregate_joiners(self, **_kwargs):
        return {
            "total_joiners": 3,
            "uae_national_joiners": 2,
            "breakdown": [
                {"period": "2026-01", "joiners": 1},
                {"period": "2026-02", "joiners": 2},
            ],
            "warnings": [],
        }

    async def aggregate_leavers(self, **_kwargs):
        return {
            "total_leavers": 1,
            "breakdown": [{"period": "2026-02", "leavers": 1}],
            "warnings": ["Reasons unavailable"],
        }

    async def _fetch_all(self, entity, **_kwargs):
        return {"results": [{"userId": "leaver"}], "complete": True}

    async def _nationality_map(self, **_kwargs):
        return {"mapping": {"leaver": "ARE"}}


class TestSuccessFactorsLeaversAttritionTrend(unittest.IsolatedAsyncioTestCase):
    async def test_aggregate_leavers_keeps_unavailable_reasons_unclassified(self):
        res = await LeaverClient().aggregate_leavers(
            start_date="2026-08-01", end_date="2026-08-07", group_by="day"
        )
        self.assertEqual(res["total_leavers"], 2)
        self.assertIsNone(res["voluntary_leavers"])
        self.assertEqual(res["unclassified_leavers"], 2)
        self.assertTrue(res["reconciliation"]["passed"])
        self.assertIsNone(res["top_separation_reason"])
        self.assertEqual(decorate(res)["cardTitle"], "Employee leavers & separations")

    async def test_attrition_uses_verified_numerator_and_denominator(self):
        res = await AttritionClient().aggregate_attrition(
            start_date="2026-01-01", end_date="2026-08-22"
        )
        self.assertEqual(res["type"], "AttritionAnalytics")
        self.assertEqual(res["overall_attrition_rate_pct"], 2.0)
        self.assertEqual(res["uae_national_leavers"], 1)
        self.assertEqual(res["uae_national_headcount"], 2)
        self.assertEqual(res["uae_national_attrition_rate_pct"], 50.0)
        self.assertIsNone(res["voluntary_leavers"])

    async def test_trend_is_built_from_reconciled_period_rows(self):
        res = await TrendClient().aggregate_joiners_leavers_trend(
            start_date="2026-01-01", end_date="2026-02-28", granularity="month"
        )
        self.assertEqual(res["net_talent_growth"], 2)
        self.assertEqual(res["talent_replacement_ratio"], 3.0)
        self.assertEqual(res["uae_national_net_growth"], 1)
        self.assertEqual(sum(row["joiners"] for row in res["monthly_trend"]), 3)
        self.assertEqual(sum(row["leavers"] for row in res["monthly_trend"]), 1)
        self.assertTrue(res["reconciliation"]["passed"])

    async def test_trend_defaults_to_current_year_to_date(self):
        res = await TrendClient().aggregate_joiners_leavers_trend()
        self.assertEqual(res["start_date"], f"{date.today().year}-01-01")
        self.assertEqual(res["end_date"], date.today().isoformat())
        self.assertTrue(res["reconciliation"]["passed"])

    def test_registered_fastmcp_tool_specs(self):
        tool_names = [spec["name"] for spec in tools_module.TOOL_SPECS]
        for name in (
            "sf__get_leavers", "sf__get_attrition", "sf__get_joiners_leavers_trend",
            "sf__get_headcount", "sf__get_joiners", "sf__get_emiratisation_kpi",
        ):
            self.assertIn(name, tool_names)


if __name__ == "__main__":
    unittest.main()
