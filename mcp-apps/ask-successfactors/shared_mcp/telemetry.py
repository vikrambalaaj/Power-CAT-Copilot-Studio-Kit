"""App Insights telemetry for LOB MCP tool calls — no SDK, pure HTTP REST."""
from __future__ import annotations

import asyncio
import functools
import json
import os
import time
from datetime import datetime, timezone

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    httpx = None
    HAS_HTTPX = False


from .logger import get_logger

_log = get_logger("shared_mcp.telemetry")

_CONN_STR  = os.getenv("APPINSIGHTS_CONNECTION_STRING", "")
_ROLE_NAME = os.getenv("APPINSIGHTS_ROLE_NAME", "lob-mcp")


def _parse_conn_str(conn_str: str) -> tuple[str, str]:
    if not conn_str:
        return "", ""
    parts = dict(p.split("=", 1) for p in conn_str.split(";") if "=" in p)
    ikey     = parts.get("InstrumentationKey", "")
    endpoint = parts.get("IngestionEndpoint", "https://dc.services.visualstudio.com").rstrip("/")
    return ikey, f"{endpoint}/v2/track"


_IKEY, _ENDPOINT = _parse_conn_str(_CONN_STR)
_ENABLED = bool(_IKEY)


def _ms_to_duration(ms: float) -> str:
    total_s = ms / 1000
    h, rem  = divmod(int(total_s), 3600)
    m, s    = divmod(rem, 60)
    frac    = int((ms % 1000) * 10000)
    return f"0.{h:02d}:{m:02d}:{s:02d}.{frac:07d}"


def _payload(
    tool_name: str,
    duration_ms: float,
    success: bool,
    result_type: str = "",
    record_count: int = 0,
    error: str = "",
) -> list[dict]:
    lob = tool_name.split("__")[0] if "__" in tool_name else "unknown"
    target = {
        "sf": "successfactors-hcm",
        "sn": "servicenow-itsm",
        "sf_hcm": "successfactors-hcm",
    }.get(lob, lob)
    return [{
        "ver": 1,
        "name": "Microsoft.ApplicationInsights.RemoteDependency",
        "time": datetime.now(timezone.utc).isoformat(),
        "sampleRate": 100.0,
        "iKey": _IKEY,
        "tags": {
            "ai.cloud.role":         _ROLE_NAME,
            "ai.cloud.roleInstance": target,
            "ai.internal.sdkVersion": "mcp-shared:0.5.0",
        },
        "data": {
            "baseType": "RemoteDependencyData",
            "baseData": {
                "ver":      2,
                "name":     tool_name,
                "duration": _ms_to_duration(duration_ms),
                "success":  success,
                "type":     "MCP Tool",
                "target":   target,
                "data":     result_type,
                "properties": {
                    "recordCount": str(record_count),
                    "error":       error,
                },
            },
        },
    }]


async def _ship(data: list[dict]) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                _ENDPOINT,
                content=json.dumps(data),
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code not in (200, 202):
                _log.debug("telemetry_dropped status=%d", resp.status_code)
    except Exception as exc:
        _log.debug("telemetry_send_error %s: %s", type(exc).__name__, exc)


def track_tool(name: str):
    def decorator(fn):
        if not _ENABLED:
            return fn

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            start     = time.monotonic()
            error_msg = ""
            result    = None
            try:
                result = await fn(*args, **kwargs)
                return result
            except Exception as exc:
                error_msg = str(exc)
                raise
            finally:
                duration_ms = (time.monotonic() - start) * 1000
                sc          = getattr(result, "structuredContent", None) or {}
                asyncio.ensure_future(_ship(_payload(
                    tool_name    = name,
                    duration_ms  = duration_ms,
                    success      = not error_msg and not sc.get("error"),
                    result_type  = sc.get("type", ""),
                    record_count = int(sc.get("total", 0) or 0),
                    error        = error_msg or str(sc.get("message", "")),
                )))
        return wrapper
    return decorator


def wrap_specs(specs: list[dict]) -> list[dict]:
    return [
        {**spec, "handler": track_tool(spec["name"])(spec.get("handler") or spec["func"])}
        for spec in specs
    ]
