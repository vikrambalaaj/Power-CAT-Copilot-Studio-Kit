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
        enable_dns_rebinding_protection=False,
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


MCP_TOOLS = [
    {
        "name": "s4__get_receivables_aging",
        "description": "Retrieve permission-trimmed accounts-receivable aging from SAP S/4HANA.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "company_code": {"type": "string", "description": "Company code, e.g. 1000"},
                "key_date": {"type": "string", "description": "Key date YYYY-MM-DD"},
                "customer": {"type": "string", "description": "Customer number or name"},
                "currency": {"type": "string", "description": "Currency, default AED"},
            },
        },
    },
    {
        "name": "s4__get_payables_aging",
        "description": "Retrieve permission-trimmed accounts-payable aging from SAP S/4HANA.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "company_code": {"type": "string", "description": "Company code, e.g. 1000"},
                "key_date": {"type": "string", "description": "Key date YYYY-MM-DD"},
                "supplier": {"type": "string", "description": "Supplier number or name"},
                "currency": {"type": "string", "description": "Currency, default AED"},
            },
        },
    },
    {
        "name": "s4__get_profit_and_loss",
        "description": "Retrieve a sourced profit-and-loss view from SAP S/4HANA.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "company_code": {"type": "string", "description": "Company code, e.g. 1000"},
                "fiscal_year": {"type": "string", "description": "Fiscal year, e.g. 2026"},
                "fiscal_period": {"type": "string", "description": "Fiscal period, e.g. 008"},
                "ledger": {"type": "string", "description": "Ledger, default 0L"},
                "currency": {"type": "string", "description": "Currency, default AED"},
            },
        },
    },
    {
        "name": "s4__get_budget_variance",
        "description": "Retrieve sourced budget-versus-actual variance records from SAP S/4HANA.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "company_code": {"type": "string", "description": "Company code, e.g. 1000"},
                "fiscal_year": {"type": "string", "description": "Fiscal year, e.g. 2026"},
                "fiscal_period": {"type": "string", "description": "Fiscal period, e.g. 008"},
                "plan_version": {"type": "string", "description": "Plan version, default 0"},
            },
        },
    },
]


async def handle_mcp_endpoint(request):
    if request.method == "GET":
        return JSONResponse({"tools": MCP_TOOLS})
    
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    
    req_id = body.get("id")
    method = body.get("method", "")
    
    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "prompts": {"listChanged": False},
                },
                "serverInfo": {"name": "velora-s4-finance", "version": "1.0.0"},
            },
        })
    
    if method in ("notifications/initialized", "initialized"):
        return JSONResponse({"jsonrpc": "2.0"})
    
    if method == "ping":
        return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {}})
    
    if method in ("tools/list", "tools"):
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": MCP_TOOLS},
        })
    
    if method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        tool_entry = next((item for item in TOOL_SPECS if item[0] == tool_name), None)
        if not tool_entry:
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Tool '{tool_name}' not found"},
            })
        _, _, handler = tool_entry
        try:
            res = await handler(**tool_args)
            import json as _json
            if hasattr(res, "content") and res.content:
                content_list = [{"type": "text", "text": c.text} for c in res.content]
            elif isinstance(res, dict):
                content_list = [{"type": "text", "text": _json.dumps(res, ensure_ascii=False, default=str)}]
            else:
                content_list = [{"type": "text", "text": str(res)}]
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": content_list,
                    "isError": False,
                },
            })
        except Exception as ex:
            log.error(f"Error in tools/call {tool_name}: {ex}", exc_info=True)
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": str(ex)},
            })
    
    return JSONResponse({
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method '{method}' not implemented"},
    })


def create_app():
    from starlette.applications import Starlette
    app = Starlette()
    app.routes.append(Route("/", health, methods=["GET", "HEAD"]))
    app.routes.append(Route("/health", health, methods=["GET", "HEAD"]))
    app.routes.append(Route("/mcp", handle_mcp_endpoint, methods=["GET", "POST", "OPTIONS"]))
    app.routes.append(Route("/mcp/", handle_mcp_endpoint, methods=["GET", "POST", "OPTIONS"]))
    app.routes.append(Route("/mcp/tools", list_tools_endpoint, methods=["GET"]))
    for name, _, _ in TOOL_SPECS:
        app.routes.append(Route(f"/{name}", handle_tool_rest, methods=["GET", "POST", "OPTIONS"]))
        app.routes.append(Route(f"/tools/{name}", handle_tool_rest, methods=["GET", "POST", "OPTIONS"]))
        # Also alias camelCase operationIds from swagger
        camel = "".join(part.capitalize() for part in name.replace("s4__", "").split("_"))
        camel_op = "get" + camel.replace("Get", "")
        if camel_op:
            app.routes.append(Route(f"/{camel_op}", handle_tool_rest, methods=["GET", "POST", "OPTIONS"]))
    app.add_middleware(ApiKeyMiddleware)
    origins = [value.strip() for value in settings.cors_origins.split(",") if value.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "OPTIONS", "HEAD"],
            allow_headers=["Content-Type", "Authorization", "X-API-Key", "mcp-session-id", "Accept"],
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
