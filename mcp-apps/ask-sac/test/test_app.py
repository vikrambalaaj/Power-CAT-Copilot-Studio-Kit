import asyncio
import unittest
from sac_mcp.tools import get_sac_kpis, get_sac_story_analytics, get_sac_model_data
from sac_mcp.cache import cache
from sac_mcp.settings import settings


class TestSACServer(unittest.TestCase):
    def setUp(self):
        self.original_demo_mode = settings.demo_mode
        settings.demo_mode = True
        cache.clear()

    def tearDown(self):
        cache.clear()
        settings.demo_mode = self.original_demo_mode

    def test_get_sac_kpis(self):
        res = asyncio.run(get_sac_kpis(domain="FINANCE"))
        self.assertIn("structuredContent", res)
        self.assertIn("adaptiveCard", res)
        self.assertEqual(res["structuredContent"]["domain"], "FINANCE")
        self.assertTrue(len(res["structuredContent"]["kpis"]) > 0)

    def test_get_sac_story_analytics(self):
        res = asyncio.run(get_sac_story_analytics(story_id="VELORA_CORP_PERF_2026"))
        self.assertIn("structuredContent", res)
        self.assertEqual(res["structuredContent"]["story_id"], "VELORA_CORP_PERF_2026")
        self.assertIn("adaptiveCard", res)

    def test_get_sac_model_data(self):
        res = asyncio.run(get_sac_model_data(model_id="M_CORP_PLAN_2026", measures=["GrossRevenue", "NetMargin"]))
        self.assertIn("structuredContent", res)
        self.assertEqual(res["structuredContent"]["status"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
