from __future__ import annotations

import hmac
import json
import logging
import os
from typing import Any, Dict, List, Optional
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route

from sac_mcp.settings import settings
from sac_mcp.tools import (
    ALL_TOOLS,
    get_sac_kpis,
    get_sac_story_analytics,
    get_sac_model_data,
)

log = logging.getLogger("sac_mcp")

allowed_hosts = [
    h.strip()
    for h in os.getenv("ALLOWED_HOSTS", "teams.microsoft.com,copilotstudio.microsoft.com,localhost,127.0.0.1,testserver").split(",")
    if h.strip()
]
if "testserver" not in allowed_hosts:
    allowed_hosts.append("testserver")
allowed_origins = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "https://teams.microsoft.com,https://copilotstudio.microsoft.com,*").split(",")
    if o.strip()
]

mcp = FastMCP(
    "sac-analytics",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    ),
)


@mcp.tool(
    name="get_sac_kpis",
    description="Retrieve executive financial, operational, and strategic KPIs from SAP Analytics Cloud (SAC).",
)
async def tool_get_sac_kpis(domain: str = "FINANCE") -> Dict[str, Any]:
    """Retrieve executive financial, operational, and strategic KPIs from SAP Analytics Cloud (SAC)."""
    return await get_sac_kpis(domain=domain)


@mcp.tool(
    name="get_sac_story_analytics",
    description="Fetch high-level business intelligence story insights, charts, and variances from SAP Analytics Cloud.",
)
async def tool_get_sac_story_analytics(story_id: str = "VELORA_CORP_PERF_2026") -> Dict[str, Any]:
    """Fetch high-level business intelligence story insights, charts, and variances from SAP Analytics Cloud."""
    return await get_sac_story_analytics(story_id=story_id)


@mcp.tool(
    name="get_sac_model_data",
    description="Query data export model structures and aggregated metric values directly from SAP Analytics Cloud models.",
)
async def tool_get_sac_model_data(model_id: str, measures: Optional[List[str]] = None) -> Dict[str, Any]:
    """Query data export model structures and aggregated metric values directly from SAP Analytics Cloud models."""
    return await get_sac_model_data(model_id=model_id, measures=measures)


async def health(request):
    return JSONResponse({"status": "ok", "service": "sac-analytics-mcp-server", "version": "0.1.0"})


async def list_tools_endpoint(request):
    return JSONResponse({
        "tools": [
            {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            }
            for t in ALL_TOOLS
        ]
    })


async def call_mcp_rest(request):
    body = await request.json()
    tool_name = body.get("name") or body.get("method")
    args = body.get("arguments") or body.get("params") or {}

    tool = next((t for t in ALL_TOOLS if t["name"] == tool_name), None)
    if not tool:
        return JSONResponse({"error": f"Tool '{tool_name}' not found"}, status_code=404)

    try:
        result = await tool["handler"](**args)
        return JSONResponse({"result": result, "status": "success"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def rest_get_sac_kpis(request):
    domain = "FINANCE"
    if request.method == "POST":
        try:
            b = await request.json()
            domain = b.get("domain", domain)
        except Exception:
            pass
    else:
        domain = request.query_params.get("domain", domain)
    res = await get_sac_kpis(domain=domain)
    return JSONResponse(res)


async def rest_get_sac_story(request):
    story_id = "VELORA_CORP_PERF_2026"
    if request.method == "POST":
        try:
            b = await request.json()
            story_id = b.get("story_id", story_id)
        except Exception:
            pass
    else:
        story_id = request.query_params.get("story_id", story_id)
    res = await get_sac_story_analytics(story_id=story_id)
    return JSONResponse(res)


async def rest_get_sac_model(request):
    model_id = ""
    measures = None
    if request.method == "POST":
        try:
            b = await request.json()
            model_id = b.get("model_id", model_id)
            measures = b.get("measures")
        except Exception:
            pass
    else:
        model_id = request.query_params.get("model_id", model_id)
        raw_m = request.query_params.get("measures")
        if raw_m:
            measures = [x.strip() for x in raw_m.split(",")]
    res = await get_sac_model_data(model_id=model_id, measures=measures)
    return JSONResponse(res)


class McpAuthMiddleware:
    """Authentication middleware protecting MCP and REST endpoints."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            method = scope.get("method", "")
            if path in ("/health", "/healthz") or method == "OPTIONS":
                await self.app(scope, receive, send)
                return

            is_prod = (
                os.getenv("VELORA_ENV", "").lower() in ("production", "prod")
                or os.getenv("ENVIRONMENT", "").lower() in ("production", "prod")
                or os.getenv("NODE_ENV", "").lower() in ("production", "prod")
            )
            allow_anon = (not is_prod) and (
                os.getenv("ALLOW_ANONYMOUS", "false").lower() in ("true", "1") or settings.allow_anonymous
            )
            if is_prod and (os.getenv("ALLOW_ANONYMOUS", "false").lower() in ("true", "1") or settings.allow_anonymous):
                status = 500
                body = json.dumps({"error": "ConfigurationError", "message": "FATAL: ALLOW_ANONYMOUS cannot be enabled in production environments."}).encode("utf-8")
                await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("latin1"))]})
                await send({"type": "http.response.body", "body": body})
                return

            if not allow_anon:
                raw_headers = scope.get("headers", [])
                norm_headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in raw_headers}
                supplied = norm_headers.get("x-api-key", "")
                auth_header = norm_headers.get("authorization", "")
                if not supplied and auth_header.lower().startswith("bearer "):
                    supplied = auth_header[7:].strip()

                expected_key = settings.mcp_api_key or os.getenv("MCP_API_KEY", "")
                if not expected_key or not supplied or not hmac.compare_digest(supplied, expected_key):
                    status = 401
                    body = json.dumps({"error": "Unauthorized", "message": "Authentication required. Please provide a valid API key."}).encode("utf-8")
                    await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("latin1"))]})
                    await send({"type": "http.response.body", "body": body})
                    return

            raw_headers = scope.get("headers", [])
            norm_headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in raw_headers}
            accept_header = norm_headers.get("accept", "")
            prefer_json = "application/json" in accept_header and not (accept_header.strip() == "text/event-stream")
            if path == "/mcp" and method == "POST" and prefer_json:
                response_status = 200
                response_headers = []
                response_chunks = []

                async def custom_send(message):
                    nonlocal response_status, response_headers, response_chunks
                    if message["type"] == "http.response.start":
                        response_status = message["status"]
                        response_headers = list(message.get("headers", []))
                    elif message["type"] == "http.response.body":
                        response_chunks.append(message.get("body", b""))
                        if not message.get("more_body", False):
                            full_body = b"".join(response_chunks)
                            content_type = dict(response_headers).get(b"content-type", b"").decode("latin1")
                            if "text/event-stream" in content_type:
                                body_str = full_body.decode("utf-8", errors="replace")
                                for line in body_str.splitlines():
                                    if line.startswith("data: "):
                                        json_part = line[6:].strip().encode("utf-8")
                                        new_headers = [
                                            (k, v) for k, v in response_headers
                                            if k.lower() not in (b"content-type", b"content-length")
                                        ]
                                        new_headers.append((b"content-type", b"application/json"))
                                        new_headers.append((b"content-length", str(len(json_part)).encode("latin1")))
                                        await send({"type": "http.response.start", "status": response_status, "headers": new_headers})
                                        await send({"type": "http.response.body", "body": json_part, "more_body": False})
                                        return
                            await send({"type": "http.response.start", "status": response_status, "headers": response_headers})
                            await send({"type": "http.response.body", "body": full_body, "more_body": False})

                await self.app(scope, receive, custom_send)
                return

        await self.app(scope, receive, send)


def create_app():
    app = mcp.streamable_http_app()
    app.routes.append(Route("/health", health, methods=["GET"]))
    app.routes.append(Route("/mcp/tools", list_tools_endpoint, methods=["GET"]))
    app.routes.append(Route("/mcp/call", call_mcp_rest, methods=["POST"]))
    app.routes.append(Route("/get_sac_kpis", rest_get_sac_kpis, methods=["GET", "POST"]))
    app.routes.append(Route("/tools/get_sac_kpis", rest_get_sac_kpis, methods=["GET", "POST"]))
    app.routes.append(Route("/get_sac_story_analytics", rest_get_sac_story, methods=["GET", "POST"]))
    app.routes.append(Route("/tools/get_sac_story_analytics", rest_get_sac_story, methods=["GET", "POST"]))
    app.routes.append(Route("/get_sac_model_data", rest_get_sac_model, methods=["GET", "POST"]))
    app.routes.append(Route("/tools/get_sac_model_data", rest_get_sac_model, methods=["GET", "POST"]))

    app.add_middleware(McpAuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins if allowed_origins else ["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    return app


app = create_app()


def main():
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    main()
