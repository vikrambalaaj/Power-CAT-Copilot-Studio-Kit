"""Allowlisted, read-only S/4HANA OData client."""
from __future__ import annotations

import base64
import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone
from time import monotonic
from typing import Any
from urllib.parse import urlparse

import httpx

from .settings import Settings, get_settings
from .cache import AsyncTTLCache


def escape_odata(value: str) -> str:
    return value.replace("'", "''")


def bounded_top(value: int) -> int:
    return max(1, min(int(value), 500))


def validate_relative_entity(value: str) -> str:
    entity = value.strip().strip("/")
    if not entity or not re.fullmatch(r"[A-Za-z0-9_./-]+", entity) or ".." in entity:
        raise ValueError("Configured S/4HANA entity path is invalid")
    return entity


class S4Client:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.base_url = self.settings.s4_api_url.rstrip("/")
        self._read_cache = AsyncTTLCache[dict[str, Any]](
            enabled=getattr(self.settings, "cache_enabled", True),
            ttl_seconds=getattr(self.settings, "cache_ttl_seconds", 60),
            max_entries=getattr(self.settings, "cache_max_entries", 512),
        )
        self._oauth_token = ""
        self._oauth_token_expires_at = 0.0
        self._oauth_lock = asyncio.Lock()

    def validate(self) -> list[str]:
        errors: list[str] = []
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            errors.append("S4_API_URL must be HTTPS and must not contain credentials")
        if self.settings.s4_auth_mode not in {"oauth", "basic"}:
            errors.append("S4_AUTH_MODE must be oauth or basic")
        if self.settings.s4_auth_mode == "oauth":
            token = urlparse(self.settings.s4_token_url)
            if token.scheme != "https" or not token.hostname:
                errors.append("S4_TOKEN_URL must be HTTPS for OAuth mode")
            if not self.settings.s4_client_id or not self.settings.s4_client_secret:
                errors.append("S4_CLIENT_ID and S4_CLIENT_SECRET are required for OAuth mode")
        if self.settings.s4_auth_mode == "basic" and (
            not self.settings.s4_username or not self.settings.s4_password
        ):
            errors.append("S4_USERNAME and S4_PASSWORD are required for basic mode")
        for name in ("s4_ar_entity", "s4_ap_entity", "s4_pl_entity", "s4_budget_entity"):
            try:
                validate_relative_entity(getattr(self.settings, name))
            except ValueError:
                errors.append(f"{name.upper()} is missing or invalid")
        return errors

    async def _authorization(self) -> str:
        if self.settings.s4_auth_mode == "basic":
            value = f"{self.settings.s4_username}:{self.settings.s4_password}"
            return "Basic " + base64.b64encode(value.encode()).decode()
        if self._oauth_token and monotonic() < self._oauth_token_expires_at:
            return f"Bearer {self._oauth_token}"
        async with self._oauth_lock:
            if self._oauth_token and monotonic() < self._oauth_token_expires_at:
                return f"Bearer {self._oauth_token}"
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    self.settings.s4_token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.settings.s4_client_id,
                        "client_secret": self.settings.s4_client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            response.raise_for_status()
            payload = response.json()
            token = payload.get("access_token")
            if not token:
                raise RuntimeError("OAuth response did not contain an access token")
            expires_in = max(1, int(payload.get("expires_in", 300)))
            skew = max(0, int(getattr(self.settings, "oauth_token_cache_skew_seconds", 30)))
            self._oauth_token = token
            self._oauth_token_expires_at = monotonic() + max(1, expires_in - skew)
            return f"Bearer {token}"

    async def _request(self, entity: str, params: dict[str, Any]) -> dict[str, Any]:
        path = validate_relative_entity(entity)
        url = f"{self.base_url}/{path}"
        safe_params = dict(params)
        safe_params.setdefault("$format", "json")
        try:
            authorization = await self._authorization()
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    params=safe_params,
                    headers={"Authorization": authorization, "Accept": "application/json"},
                )
            if response.status_code >= 400:
                return {
                    "status": "error",
                    "code": "S4_UPSTREAM_ERROR",
                    "message": f"S/4HANA request failed with status {response.status_code}",
                    "retryable": response.status_code in {408, 429, 500, 502, 503, 504},
                }
            payload = response.json()
            data = payload.get("d", payload)
            rows = data.get("results", []) if isinstance(data, dict) else []
            return {"rows": rows, "count": int(data.get("__count", len(rows))) if isinstance(data, dict) else 0}
        except (httpx.HTTPError, ValueError, RuntimeError) as error:
            return {
                "status": "error",
                "code": "S4_CONNECTION_ERROR",
                "message": f"S/4HANA connection failed: {type(error).__name__}",
                "retryable": isinstance(error, httpx.HTTPError),
            }

    async def query(
        self,
        entity: str,
        capability: str,
        filters: dict[str, str | None],
        period: str | None = None,
        currency: str | None = None,
        correlation_id: str | None = None,
        top: int = 100,
    ) -> dict[str, Any]:
        clauses = [f"{key} eq '{escape_odata(value)}'" for key, value in filters.items() if value]
        params: dict[str, Any] = {"$top": bounded_top(top), "$inlinecount": "allpages"}
        if clauses:
            params["$filter"] = " and ".join(clauses)
        key_payload = {
            "baseUrl": self.base_url,
            "authMode": self.settings.s4_auth_mode,
            "entity": entity,
            "params": params,
        }
        cache_key = hashlib.sha256(
            json.dumps(key_payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        result, cache_info = await self._read_cache.get_or_load(
            cache_key,
            lambda: self._request(entity, params),
            cacheable=lambda value: value.get("status") != "error",
        )
        if result.get("status") == "error":
            result["audit"] = {"correlationId": correlation_id or ""}
            result["cache"] = cache_info.as_dict()
            return result
        return {
            "status": "success",
            "data": {"records": result["rows"], "total": result["count"]},
            "source": {
                "system": "SAP S/4HANA",
                "object": validate_relative_entity(entity),
                "asOf": cache_info.stored_at or datetime.now(timezone.utc).isoformat(),
            },
            "query": {"filters": {k: v for k, v in filters.items() if v}, "period": period, "currency": currency},
            "quality": {"complete": len(result["rows"]) >= result["count"], "sampled": len(result["rows"]) < result["count"], "confidence": "high", "warnings": []},
            "audit": {
                "correlationId": correlation_id or "",
                "authorizationModel": "configured-s4-identity",
            },
            "cache": cache_info.as_dict(),
            "type": capability,
        }
