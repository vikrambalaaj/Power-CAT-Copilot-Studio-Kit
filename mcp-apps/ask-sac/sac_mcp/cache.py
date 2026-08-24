import time
from typing import Any, Dict, Optional
from sac_mcp.settings import settings


class TTLCache:
    def __init__(self, max_entries: int = 512, default_ttl: int = 120):
        self._max_entries = max_entries
        self._default_ttl = default_ttl
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        if not settings.cache_enabled:
            return None
        entry = self._cache.get(key)
        if not entry:
            return None
        if time.time() > entry["expires_at"]:
            del self._cache[key]
            return None
        return entry["value"]

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if not settings.cache_enabled:
            return
        if len(self._cache) >= self._max_entries:
            # simple eviction of oldest expired or arbitrary key
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k]["expires_at"])
            del self._cache[oldest_key]
        expiry = time.time() + (ttl or self._default_ttl)
        self._cache[key] = {"value": value, "expires_at": expiry}

    def clear(self) -> None:
        self._cache.clear()


cache = TTLCache(
    max_entries=settings.cache_max_entries,
    default_ttl=settings.cache_ttl_seconds,
)
