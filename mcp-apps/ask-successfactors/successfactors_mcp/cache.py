"""Small, bounded async TTL cache for permission-scoped SAP reads."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
from typing import Awaitable, Callable, Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class CacheInfo:
    status: str
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
    """In-process TTL cache with deep-copy isolation and miss coalescing."""

    def __init__(self, *, enabled: bool, ttl_seconds: int, max_entries: int):
        self.enabled = enabled and ttl_seconds > 0 and max_entries > 0
        self.ttl_seconds = max(0, int(ttl_seconds))
        self.max_entries = max(0, int(max_entries))
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
        async with self._lock:
            entry = self._entries.get(key)
            if entry and now - entry[0] < self.ttl_seconds:
                return deepcopy(entry[2]), CacheInfo("hit", now - entry[0], self.ttl_seconds, entry[1])
            if entry:
                self._entries.pop(key, None)
            future = self._inflight.get(key)
            owner = future is None
            if owner:
                future = asyncio.get_running_loop().create_future()
                self._inflight[key] = future

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

    async def clear(self) -> None:
        async with self._lock:
            self._entries.clear()
