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
    entity = value.strip()
    entity = entity.strip("/")
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

    def _validated_base_url(self, value: str | None = None) -> str:
        requested = (value or self.base_url).rstrip("/")
        parsed = urlparse(requested)
        configured = {
            candidate.rstrip("/")
            for candidate in (
                self.base_url,
                getattr(self.settings, "s4_budget_api_url", ""),
                getattr(self.settings, "s4_pl_api_url", ""),
            )
            if candidate
        }
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or requested not in configured
        ):
            raise ValueError("S/4HANA base URL is not allowlisted")
        return requested

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
        for name in ("s4_ar_entity", "s4_ap_entity"):
            val = getattr(self.settings, name, "")
            if val:
                try:
                    validate_relative_entity(val)
                except ValueError:
                    errors.append(f"{name.upper()} is invalid")
            else:
                errors.append(f"{name.upper()} is missing")
        for name in ("s4_pl_entity", "s4_budget_entity"):
            val = getattr(self.settings, name, "")
            if val:
                try:
                    validate_relative_entity(val)
                except ValueError:
                    errors.append(f"{name.upper()} is invalid")
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

    async def _request(self, entity: str, params: dict[str, Any], base_url: str | None = None) -> dict[str, Any]:
        if entity == "$metadata":
            url = f"{self._validated_base_url(base_url)}/$metadata"
            params = {}
        elif entity:
            path = validate_relative_entity(entity)
            effective_base = self._validated_base_url(base_url)
            url = f"{effective_base}/{path}"
        else:
            url = self._validated_base_url(base_url)
            params = {}
        safe_params = dict(params)
        if getattr(self.settings, "s4_sap_client", ""):
            safe_params.setdefault("sap-client", self.settings.s4_sap_client)
        try:
            authorization = await self._authorization()
            verify_opt = self.settings.s4_ca_bundle if self.settings.s4_ca_bundle else self.settings.s4_verify_tls
            async with httpx.AsyncClient(timeout=30.0, verify=verify_opt) as client:
                response = await client.get(
                    url,
                    params=safe_params,
                    headers={
                        "Authorization": authorization,
                        "Accept": "application/json",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VeloraS4MCP/1.0",
                    },
                )
            if response.status_code >= 400:
                return {
                    "status": "error",
                    "code": "S4_UPSTREAM_ERROR",
                    "message": "S/4HANA request failed",
                    "retryable": response.status_code in {408, 429, 500, 502, 503, 504},
                }
            payload = response.json()
            if isinstance(payload, dict):
                if "value" in payload and isinstance(payload["value"], list):
                    rows = payload["value"]
                    count = int(payload.get("@odata.count", len(rows)))
                elif "d" in payload:
                    data = payload["d"]
                    if isinstance(data, dict):
                        rows = data.get("results", [])
                        count = int(data.get("__count", len(rows)))
                    elif isinstance(data, list):
                        rows = data
                        count = len(rows)
                    else:
                        rows = []
                        count = 0
                else:
                    rows = payload.get("results", [])
                    count = int(payload.get("__count", len(rows)))
            elif isinstance(payload, list):
                rows = payload
                count = len(rows)
            else:
                rows = []
                count = 0
            return {"rows": rows, "count": count}
        except (httpx.HTTPError, ValueError, RuntimeError, json.JSONDecodeError) as error:
            return {
                "status": "error",
                "code": "S4_CONNECTION_ERROR",
                "message": "S/4HANA request failed",
                "retryable": isinstance(error, httpx.HTTPError),
            }

    async def query_profit_and_loss(
        self,
        *,
        company_code: str,
        fiscal_year: str,
        fiscal_period: str,
        ledger: str,
        profit_center: str | None = None,
        correlation_id: str | None = None,
        top: int = 100,
    ) -> dict[str, Any]:
        """Query the allowlisted SAP financial-statement KPI analytical service."""
        if not re.fullmatch(r"\d{4}", fiscal_year):
            raise ValueError("Fiscal year must contain four digits")
        period_number = int(fiscal_period)
        if period_number < 1 or period_number > 16:
            raise ValueError("Fiscal period must be between 1 and 16")

        base_url = self._validated_base_url(self.settings.s4_pl_api_url)
        entity = validate_relative_entity(self.settings.s4_pl_entity)
        planning_category = escape_odata(self.settings.s4_pl_planning_category)
        path = (
            f"{entity}(P_ToFiscalPeriod='{period_number}',"
            f"P_PlanningCategory='{planning_category}')/Results"
        )
        filters: dict[str, str | None] = {
            "CompanyCode": company_code,
            "Ledger": ledger,
            "LedgerFiscalYear": fiscal_year,
            "GLAccountHierarchy": self.settings.s4_pl_gl_account_hierarchy,
            "ProfitCenter": profit_center,
        }
        clauses = [f"{key} eq '{escape_odata(value)}'" for key, value in filters.items() if value]
        params: dict[str, Any] = {
            "$top": bounded_top(top),
            "$inlinecount": "allpages",
            "$format": "json",
            "$filter": " and ".join(clauses),
        }
        cache_key = hashlib.sha256(
            json.dumps({"baseUrl": base_url, "path": path, "params": params}, sort_keys=True).encode()
        ).hexdigest()
        result, cache_info = await self._read_cache.get_or_load(
            cache_key,
            lambda: self._request_parameterized(path, params, base_url),
            cacheable=lambda value: value.get("status") != "error",
        )
        if result.get("status") == "error":
            result["correlationId"] = correlation_id or ""
            result["audit"] = {
                "correlationId": correlation_id or "",
                "executingIdentity": self.settings.executing_identity,
                "authorizationModel": self.settings.authorization_model,
            }
            result["cache"] = cache_info.as_dict()
            return result
        return {
            "status": "success",
            "data": {"records": result["rows"], "total": result["count"]},
            "source": {
                "system": "SAP S/4HANA",
                "object": entity,
                "asOf": cache_info.stored_at or datetime.now(timezone.utc).isoformat(),
            },
            "query": {
                "filters": {key: value for key, value in filters.items() if value},
                "period": f"{fiscal_year}-{period_number:03d}",
            },
            "quality": {
                "complete": len(result["rows"]) >= result["count"],
                "sampled": len(result["rows"]) < result["count"],
                "confidence": "high",
                "warnings": [],
            },
            "audit": {
                "correlationId": correlation_id or "",
                "executingIdentity": self.settings.executing_identity,
                "authorizationModel": self.settings.authorization_model,
            },
            "cache": cache_info.as_dict(),
            "type": "ProfitAndLoss",
        }

    async def _request_parameterized(
        self,
        path: str,
        params: dict[str, Any],
        base_url: str,
    ) -> dict[str, Any]:
        """Execute a server-constructed analytical path against an allowlisted SAP service."""
        if not path.startswith(f"{validate_relative_entity(self.settings.s4_pl_entity)}(") or not path.endswith(")/Results"):
            raise ValueError("Parameterized S/4HANA path is invalid")
        url = f"{self._validated_base_url(base_url)}/{path}"
        try:
            authorization = await self._authorization()
            verify_opt = self.settings.s4_ca_bundle if self.settings.s4_ca_bundle else self.settings.s4_verify_tls
            safe_params = dict(params)
            if self.settings.s4_sap_client:
                safe_params.setdefault("sap-client", self.settings.s4_sap_client)
            async with httpx.AsyncClient(timeout=60.0, verify=verify_opt) as client:
                response = await client.get(
                    url,
                    params=safe_params,
                    headers={"Authorization": authorization, "Accept": "application/json"},
                )
            if response.status_code >= 400:
                return {
                    "status": "error",
                    "code": "S4_UPSTREAM_ERROR",
                    "message": "S/4HANA request failed",
                    "retryable": response.status_code in {408, 429, 500, 502, 503, 504},
                }
            payload = response.json().get("d", {})
            rows = payload.get("results", [])
            return {"rows": rows, "count": int(payload.get("__count", len(rows)))}
        except (httpx.HTTPError, ValueError, RuntimeError, json.JSONDecodeError) as error:
            return {
                "status": "error",
                "code": "S4_CONNECTION_ERROR",
                "message": "S/4HANA request failed",
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
        override_base_url: str | None = None,
    ) -> dict[str, Any]:
        clauses = [f"{key} eq '{escape_odata(value)}'" for key, value in filters.items() if value]
        params: dict[str, Any] = {"$top": bounded_top(top), "$count": "true"}
        if clauses:
            params["$filter"] = " and ".join(clauses)
        effective_base = self._validated_base_url(override_base_url)
        key_payload = {
            "baseUrl": effective_base,
            "authMode": self.settings.s4_auth_mode,
            "entity": entity,
            "params": params,
        }
        cache_key = hashlib.sha256(
            json.dumps(key_payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        result, cache_info = await self._read_cache.get_or_load(
            cache_key,
            lambda: self._request(entity, params, base_url=effective_base),
            cacheable=lambda value: value.get("status") != "error",
        )
        if result.get("status") == "error":
            result["correlationId"] = correlation_id or ""
            result["audit"] = {
                "correlationId": correlation_id or "",
                "executingIdentity": self.settings.executing_identity,
                "authorizationModel": self.settings.authorization_model,
            }
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
                "executingIdentity": self.settings.executing_identity,
                "authorizationModel": self.settings.authorization_model,
            },
            "cache": cache_info.as_dict(),
            "type": capability,
        }
