"""Secured S/4HANA finance MCP server."""
from __future__ import annotations

import hmac
import logging
import sys

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route

from .client import S4Client
from .settings import get_settings
from .tools import TOOL_SPECS

settings = get_settings()
log = logging.getLogger("s4_finance")

mcp = FastMCP(
    "velora-s4-finance",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[value.strip() for value in settings.allowed_hosts.split(",") if value.strip()],
        allowed_origins=[value.strip() for value in settings.allowed_origins.split(",") if value.strip()],
    ),
)

for name, description, handler in TOOL_SPECS:
    mcp.tool(name=name, description=description)(handler)


class ApiKeyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path", "").startswith("/mcp"):
            if not settings.allow_anonymous:
                headers = {key.lower(): value for key, value in scope.get("headers", [])}
                supplied = headers.get(b"x-api-key", b"").decode("utf-8")
                bearer = headers.get(b"authorization", b"").decode("utf-8")
                if not supplied and bearer.lower().startswith("bearer "):
                    supplied = bearer[7:].strip()
                if not settings.mcp_api_key or not hmac.compare_digest(supplied, settings.mcp_api_key):
                    await JSONResponse({"error": "Unauthorized"}, status_code=401)(scope, receive, send)
                    return
        await self.app(scope, receive, send)


async def health(_request):
    return JSONResponse({"status": "ok", "service": "s4-finance-mcp-server", "version": "1.0.0"})


async def list_tools_endpoint(_request):
    tools = [
        {"name": name, "description": desc, "parameters": {}}
        for name, desc, _ in TOOL_SPECS
    ]
    return JSONResponse({"tools": tools})


def _extract_args(request):
    pass


async def handle_tool_rest(request):
    path = request.url.path.strip("/").split("/")[-1]
    tool_entry = next((item for item in TOOL_SPECS if item[0] == path), None)
    if not tool_entry:
        return JSONResponse({"error": f"Tool '{path}' not found"}, status_code=404)
    _, _, handler = tool_entry

    # Extract args from query or body
    args = dict(request.query_params)
    if request.method == "POST":
        try:
            body = await request.json()
            if isinstance(body, dict):
                args.update(body.get("arguments", body.get("params", body)))
        except Exception:
            pass

    try:
        res = await handler(**args)
        if hasattr(res, "structuredContent") and res.structuredContent:
            return JSONResponse(res.structuredContent)
        elif hasattr(res, "content") and res.content:
            import json
            return JSONResponse(json.loads(res.content[0].text))
        return JSONResponse({"result": res, "status": "success"})
    except Exception as ex:
        log.error(f"Error executing tool {path}: {ex}", exc_info=True)
        return JSONResponse({"error": str(ex), "status": "error"}, status_code=500)


def create_app():
    app = mcp.streamable_http_app()
    app.routes.append(Route("/health", health, methods=["GET"]))
    app.routes.append(Route("/mcp/tools", list_tools_endpoint, methods=["GET"]))
    for name, _, _ in TOOL_SPECS:
        app.routes.append(Route(f"/{name}", handle_tool_rest, methods=["GET", "POST"]))
        app.routes.append(Route(f"/tools/{name}", handle_tool_rest, methods=["GET", "POST"]))
    app.add_middleware(ApiKeyMiddleware)
    origins = [value.strip() for value in settings.cors_origins.split(",") if value.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-API-Key", "mcp-session-id"],
        )
    return app


def main() -> None:
    errors = S4Client(settings).validate()
    if not settings.mcp_api_key and not settings.allow_anonymous:
        errors.append("MCP_API_KEY is required unless ALLOW_ANONYMOUS=true")
    if errors:
        for error in errors:
            log.warning(f"S4 Configuration Warning: {error}")
        if not settings.allow_anonymous:
            sys.exit(1)
    uvicorn.run(create_app(), host="0.0.0.0", port=settings.port)
