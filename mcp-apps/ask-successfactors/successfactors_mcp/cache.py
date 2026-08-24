"""Velora Multi-Layer In-Process Asynchronous Cache.

Provides 5 distinct caching tiers without requiring external Azure services (e.g. Redis):
1. Policy Cache (TTL 30-60s)
2. SuccessFactors OData Page Cache (TTL 120s)
3. Aggregate Results Cache (TTL 5-15 mins with Stale-While-Revalidate)
4. Employee Drill-Down Cache (TTL 30-60s, strictly user-isolated, NO SWR, strictly in-memory)
5. Memory Snapshot Cache (TTL 5-10 mins, strictly user-isolated)

Includes startup pre-warming for common aggregate metrics.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Awaitable, Callable, Dict, Generic, List, Optional, Tuple, TypeVar

from shared_mcp.logger import get_logger

log = get_logger("cache")

T = TypeVar("T")


@dataclass(frozen=True)
class CacheInfo:
    status: str  # "hit", "miss", "coalesced", "stale_hit", "disabled"
    age_seconds: float
    ttl_seconds: int
    stored_at: str

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "ageSeconds": round(self.age_seconds, 3),
            "ttlSeconds": self.ttl_seconds,
            "storedAt": self.stored_at,
        }


class AsyncTTLCache(Generic[T]):
    """In-process TTL cache with deep-copy isolation, miss coalescing, and optional Stale-While-Revalidate (SWR)."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        ttl_seconds: int = 120,
        max_entries: int = 200,
        allow_stale: bool = False,
        stale_ttl_seconds: int = 0,
    ):
        self.enabled = enabled and ttl_seconds > 0 and max_entries > 0
        self.ttl_seconds = max(0, int(ttl_seconds))
        self.max_entries = max(0, int(max_entries))
        self.allow_stale = allow_stale
        self.stale_ttl_seconds = max(self.ttl_seconds, int(stale_ttl_seconds or (ttl_seconds * 2)))
        self._entries: dict[str, tuple[float, str, T]] = {}
        self._inflight: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    async def get_or_load(
        self,
        key: str,
        loader: Callable[[], Awaitable[T]],
        *,
        cacheable: Callable[[T], bool] | None = None,
    ) -> tuple[T, CacheInfo]:
        if not self.enabled:
            value = await loader()
            return value, CacheInfo("disabled", 0, self.ttl_seconds, "")

        now = monotonic()
        stale_hit_entry: Optional[tuple[float, str, T]] = None

        async with self._lock:
            entry = self._entries.get(key)
            if entry:
                age = now - entry[0]
                if age < self.ttl_seconds:
                    return deepcopy(entry[2]), CacheInfo("hit", age, self.ttl_seconds, entry[1])
                elif self.allow_stale and age < self.stale_ttl_seconds:
                    stale_hit_entry = entry

            future = self._inflight.get(key)
            owner = future is None
            if owner:
                try:
                    future = asyncio.get_running_loop().create_future()
                except RuntimeError:
                    # In sync / non-eventloop testing fallback
                    value = await loader()
                    return value, CacheInfo("miss", 0, self.ttl_seconds, datetime.now(timezone.utc).isoformat())
                self._inflight[key] = future

        # If SWR is enabled and we have a valid stale entry, return it immediately and revalidate in background
        if stale_hit_entry is not None:
            if owner:
                asyncio.create_task(self._revalidate(key, loader, cacheable, future))
            return deepcopy(stale_hit_entry[2]), CacheInfo("stale_hit", now - stale_hit_entry[0], self.ttl_seconds, stale_hit_entry[1])

        if not owner:
            value, stored_at = await asyncio.shield(future)
            return deepcopy(value), CacheInfo("coalesced", 0, self.ttl_seconds, stored_at)

        try:
            value = await loader()
            stored_at = ""
            if cacheable is None or cacheable(value):
                stored_at = datetime.now(timezone.utc).isoformat()
                async with self._lock:
                    if len(self._entries) >= self.max_entries:
                        oldest = min(self._entries, key=lambda item: self._entries[item][0])
                        self._entries.pop(oldest, None)
                    self._entries[key] = (monotonic(), stored_at, deepcopy(value))
            future.set_result((deepcopy(value), stored_at))
            return value, CacheInfo("miss", 0, self.ttl_seconds, stored_at)
        except BaseException as error:
            future.set_exception(error)
            future.exception()
            raise
        finally:
            async with self._lock:
                self._inflight.pop(key, None)

    async def _revalidate(
        self,
        key: str,
        loader: Callable[[], Awaitable[T]],
        cacheable: Callable[[T], bool] | None,
        future: asyncio.Future,
    ) -> None:
        """Background revalidation for Stale-While-Revalidate."""
        try:
            value = await loader()
            stored_at = ""
            if cacheable is None or cacheable(value):
                stored_at = datetime.now(timezone.utc).isoformat()
                async with self._lock:
                    self._entries[key] = (monotonic(), stored_at, deepcopy(value))
            if not future.done():
                future.set_result((deepcopy(value), stored_at))
            log.debug("cache_swr_revalidated", key=key)
        except Exception as exc:
            log.warning("cache_swr_revalidation_failed", key=key, error=str(exc))
            if not future.done():
                future.set_exception(exc)
        finally:
            async with self._lock:
                self._inflight.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._entries.clear()

    async def clear_matching(self, prefix: str) -> None:
        async with self._lock:
            keys_to_remove = [k for k in self._entries if k.startswith(prefix)]
            for k in keys_to_remove:
                self._entries.pop(k, None)


class MultiLayerCache:
    """Manages all 5 caching tiers with composite key construction and pre-warming."""

    def __init__(self, enabled: bool = True):
        # Layer 1: Policy Cache (TTL 30-60s)
        self.policy_cache = AsyncTTLCache[Dict[str, Any]](
            enabled=enabled, ttl_seconds=60, max_entries=50
        )
        # Layer 2: OData Page Cache (TTL 120s)
        self.odata_cache = AsyncTTLCache[Dict[str, Any]](
            enabled=enabled, ttl_seconds=120, max_entries=500
        )
        # Layer 3: Aggregate Results Cache (TTL 300s / 5m with SWR up to 15m)
        self.aggregate_cache = AsyncTTLCache[Dict[str, Any]](
            enabled=enabled, ttl_seconds=300, max_entries=200, allow_stale=True, stale_ttl_seconds=900
        )
        # Layer 4: Employee Drill-Down Cache (TTL 45s, NO SWR, strictly memory-only, user-isolated)
        self.drilldown_cache = AsyncTTLCache[Dict[str, Any]](
            enabled=enabled, ttl_seconds=45, max_entries=100, allow_stale=False
        )
        # Layer 5: Memory Snapshot Cache (TTL 600s / 10m, user-isolated)
        self.memory_cache = AsyncTTLCache[Dict[str, Any]](
            enabled=enabled, ttl_seconds=600, max_entries=200
        )

    def build_drilldown_cache_key(
        self,
        environment: str,
        user_object_id: str,
        policy_id: str,
        policy_version: str,
        field_profile: str,
        department: Optional[str] = None,
        top: int = 20,
        page: int = 1,
    ) -> str:
        """Construct secure composite cache key for employee-level drill-down."""
        raw = {
            "env": environment,
            "user": user_object_id or "anon",
            "policy": f"{policy_id}:{policy_version}",
            "profile": field_profile,
            "department": department or "all",
            "top": top,
            "page": page,
        }
        return "drilldown:" + hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()

    async def prewarm_common_aggregates(self, client: Any) -> None:
        """Pre-load standard aggregate queries on startup. NEVER pre-load employee personal info."""
        log.info("prewarming_common_aggregates_start")
        try:
            # 1. Total Headcount & Department Distribution
            await client.aggregate_headcount_by_department()
            # 2. Emiratisation KPI
            await client.get_emiratisation_kpi()
            # 3. YTD Joiners & Leavers
            await client.get_joiners_leavers_trend()
            log.info("prewarming_common_aggregates_complete")
        except Exception as exc:
            log.warning("prewarming_common_aggregates_failed", error=str(exc))


_global_cache = MultiLayerCache()


def get_multi_layer_cache() -> MultiLayerCache:
    return _global_cache
