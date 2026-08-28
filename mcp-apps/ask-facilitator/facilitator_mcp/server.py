"""Facilitator MCP Server."""
from __future__ import annotations

import logging
import os
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route

from .tools import TOOL_SPECS, FACILITATOR_AUTO_SEND_GUIDE

log = logging.getLogger("facilitator_mcp")

allowed_hosts = [
    value.strip()
    for value in os.getenv(
        "ALLOWED_HOSTS",
        "localhost:*,127.0.0.1:*",
    ).split(",")
    if value.strip()
]
allowed_origins = [
    value.strip()
    for value in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if value.strip()
]

mcp = FastMCP(
    "facilitator",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    ),
)

for name, description, handler in TOOL_SPECS:
    mcp.tool(name=name, description=description)(handler)


async def health(_request):
    return JSONResponse({"status": "ok", "service": "facilitator-mcp-server"})


async def guide_endpoint(_request):
    return JSONResponse({
        "service": "facilitator",
        "guide": FACILITATOR_AUTO_SEND_GUIDE,
    })


async def list_tools_endpoint(_request):
    tools = [
        {"name": name, "description": desc, "parameters": {}}
        for name, desc, _ in TOOL_SPECS
    ]
    return JSONResponse({"tools": tools})


async def handle_facilitator_tool_rest(request):
    path = request.url.path.strip("/").split("/")[-1]
    tool_entry = next((item for item in TOOL_SPECS if item[0] == path), None)
    if not tool_entry:
        return JSONResponse({"error": f"Tool '{path}' not found"}, status_code=404)
    _, _, handler = tool_entry

    args = dict(request.query_params)
    if request.method == "POST":
        try:
            body = await request.json()
            if isinstance(body, dict):
                args.update(body.get("arguments", body.get("params", body)))
        except Exception:
            pass

    try:
        if asyncio.iscoroutinefunction(handler):
            res = await handler(**args)
        else:
            res = handler(**args)
        return JSONResponse(res if isinstance(res, dict) else {"result": res, "status": "success"})
    except Exception as ex:
        log.error(f"Error executing tool {path}: {ex}", exc_info=True)
        return JSONResponse({"error": str(ex), "status": "error"}, status_code=500)


def create_app():
    import asyncio
    app = mcp.streamable_http_app()
    app.routes.append(Route("/health", health, methods=["GET"]))
    app.routes.append(Route("/guide", guide_endpoint, methods=["GET"]))
    app.routes.append(Route("/mcp/tools", list_tools_endpoint, methods=["GET"]))
    for name, _, _ in TOOL_SPECS:
        app.routes.append(Route(f"/{name}", handle_facilitator_tool_rest, methods=["GET", "POST"]))
        app.routes.append(Route(f"/tools/{name}", handle_facilitator_tool_rest, methods=["GET", "POST"]))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("facilitator_mcp.server:app", host="0.0.0.0", port=8000, reload=False)
