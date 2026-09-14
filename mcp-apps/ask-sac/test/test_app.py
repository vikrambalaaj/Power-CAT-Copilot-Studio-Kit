import asyncio
import unittest
from unittest.mock import patch, AsyncMock
import httpx
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

    @patch("sac_mcp.client.SACClient.get_token", new_callable=AsyncMock, return_value="mock-token-123")
    def test_get_sac_kpis(self, mock_token):
        mock_resp = httpx.Response(200, json={"domain": "FINANCE", "kpis": [{"name": "OperatingMargin", "value": 24.5}]}, request=httpx.Request("GET", "https://example.invalid"))
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            res = asyncio.run(get_sac_kpis(domain="FINANCE"))
            self.assertIn("structuredContent", res)
            self.assertIn("adaptiveCard", res)
            self.assertEqual(res["structuredContent"]["domain"], "FINANCE")
            self.assertTrue(len(res["structuredContent"]["kpis"]) > 0)

    @patch("sac_mcp.client.SACClient.get_token", new_callable=AsyncMock, return_value="mock-token-123")
    def test_get_sac_story_analytics(self, mock_token):
        mock_resp = httpx.Response(200, json={"story_id": "VELORA_CORP_PERF_2026", "pages": [{"page_name": "Executive Overview"}]}, request=httpx.Request("GET", "https://example.invalid"))
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            res = asyncio.run(get_sac_story_analytics(story_id="VELORA_CORP_PERF_2026"))
            self.assertIn("structuredContent", res)
            self.assertEqual(res["structuredContent"]["story_id"], "VELORA_CORP_PERF_2026")
            self.assertIn("adaptiveCard", res)

    @patch("sac_mcp.client.SACClient.get_token", new_callable=AsyncMock, return_value="mock-token-123")
    def test_get_sac_model_data(self, mock_token):
        mock_resp = httpx.Response(200, json={"status": "SUCCESS", "records_count": 12}, request=httpx.Request("POST", "https://example.invalid"))
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            res = asyncio.run(get_sac_model_data(model_id="M_CORP_PLAN_2026", measures=["GrossRevenue", "NetMargin"]))
            self.assertIn("structuredContent", res)
            self.assertEqual(res["structuredContent"]["status"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
