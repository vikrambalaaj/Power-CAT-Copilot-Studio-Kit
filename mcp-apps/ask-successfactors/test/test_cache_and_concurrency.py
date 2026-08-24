"""Unit and integration tests for Multi-Layer In-Process Caching & SWR."""
import asyncio
import unittest
from time import monotonic

from successfactors_mcp.cache import MultiLayerCache, AsyncTTLCache
from successfactors_mcp.policy_admin import PolicyAdminService
from successfactors_mcp.dataverse_audit import DataverseClient


class CacheAndConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cache_mgr = MultiLayerCache(enabled=True)
        self.dv_client = DataverseClient()
        self.dv_client.clear_all_for_testing()
        self.policy_admin = PolicyAdminService(
            dataverse_client=self.dv_client,
            cache=self.cache_mgr,
        )

    async def test_aggregate_cache_stale_while_revalidate(self):
        # Short TTL for test: 1s TTL, 5s stale window
        cache = AsyncTTLCache[dict](
            enabled=True,
            ttl_seconds=1,
            max_entries=10,
            allow_stale=True,
            stale_ttl_seconds=5,
        )
        fetch_count = 0

        async def fetch_aggregate():
            nonlocal fetch_count
            fetch_count += 1
            await asyncio.sleep(0.02)
            return {"headcount": 1000 + fetch_count}

        # 1. First fetch -> miss
        val1, info1 = await cache.get_or_load("agg:headcount", fetch_aggregate)
        self.assertEqual(info1.status, "miss")
        self.assertEqual(val1["headcount"], 1001)
        self.assertEqual(fetch_count, 1)

        # 2. Immediate second fetch -> hit
        val2, info2 = await cache.get_or_load("agg:headcount", fetch_aggregate)
        self.assertEqual(info2.status, "hit")
        self.assertEqual(val2["headcount"], 1001)
        self.assertEqual(fetch_count, 1)

        # 3. Wait for TTL expiry (1.1s), but within stale window (< 5s)
        await asyncio.sleep(1.1)
        val3, info3 = await cache.get_or_load("agg:headcount", fetch_aggregate)
        self.assertEqual(info3.status, "stale_hit")
        self.assertEqual(val3["headcount"], 1001)  # Returns stale data immediately

        # 4. Wait for background revalidation task to complete
        await asyncio.sleep(0.1)
        self.assertEqual(fetch_count, 2)

        # 5. Next fetch receives fresh revalidated value
        val4, info4 = await cache.get_or_load("agg:headcount", fetch_aggregate)
        self.assertEqual(info4.status, "hit")
        self.assertEqual(val4["headcount"], 1002)

    async def test_drilldown_cache_never_uses_stale_while_revalidate(self):
        self.assertFalse(self.cache_mgr.drilldown_cache.allow_stale)

    async def test_drilldown_cache_key_isolation_by_user_and_policy(self):
        k1 = self.cache_mgr.build_drilldown_cache_key(
            environment="Production",
            user_object_id="user-A",
            policy_id="POL-01",
            policy_version="1.0.0",
            field_profile="workforce_drilldown",
            department="Unassigned",
        )
        k2 = self.cache_mgr.build_drilldown_cache_key(
            environment="Production",
            user_object_id="user-B",
            policy_id="POL-01",
            policy_version="1.0.0",
            field_profile="workforce_drilldown",
            department="Unassigned",
        )
        k3 = self.cache_mgr.build_drilldown_cache_key(
            environment="Production",
            user_object_id="user-A",
            policy_id="POL-01",
            policy_version="1.0.1",  # Upgraded version
            field_profile="workforce_drilldown",
            department="Unassigned",
        )

        self.assertNotEqual(k1, k2)
        self.assertNotEqual(k1, k3)

    async def test_policy_activation_purges_policy_and_drilldown_caches(self):
        # Populate policy and drilldown caches
        await self.cache_mgr.policy_cache.get_or_load("pol:active", lambda: asyncio.sleep(0, {"policy": "v1"}))
        await self.cache_mgr.drilldown_cache.get_or_load("drill:unassigned", lambda: asyncio.sleep(0, {"data": 1}))

        # Create and activate new policy version
        draft_res = await self.policy_admin.create_or_update_policy(
            policy_name="Executive Drilldown V2",
            policy_code="POL_SF_WORKFORCE_V2",
            version="2.0.0",
            allowed_fields=["userId", "name", "country"],
            is_active=False,
        )
        new_pol_id = draft_res["policy"]["cre2f_veloradatadisclosurepolicyid"]

        # Activate policy -> triggers cache purge
        await self.policy_admin.activate_policy(new_pol_id)

        # Verify caches are purged
        self.assertEqual(len(self.cache_mgr.policy_cache._entries), 0)
        self.assertEqual(len(self.cache_mgr.drilldown_cache._entries), 0)


if __name__ == "__main__":
    unittest.main()
