"""Facilitator MCP Server with Strict Identity, Authorization, and Governed Writes."""
from __future__ import annotations

import asyncio
import logging
import os
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route

from shared_mcp.identity import (
    AuthenticationError,
    AuthorizationError,
    extract_verified_identity,
)
from .tools import TOOL_SPECS, FACILITATOR_AUTO_SEND_GUIDE

log = logging.getLogger("facilitator_mcp")

# Side-effect tools that MUST NOT be invoked via GET
MUTATING_TOOLS = {
    "send_executive_email_via_graph",
    "configure_auto_send_policy",
    "export_meeting_to_loop_notebook",
    "process_calendar_meeting_workflow",
    "ingest_chat_to_knowledge_graph",
    "ingest_vendor_performance_record",
    "evaluate_vendor_options",
    "export_decision_trail",
}

# Admin-only tools
ADMIN_ONLY_TOOLS = {
    "configure_auto_send_policy",
}

allowed_hosts = [
    value.strip()
    for value in os.getenv(
        "ALLOWED_HOSTS",
        "teams.microsoft.com,copilotstudio.microsoft.com,localhost,127.0.0.1",
    ).split(",")
    if value.strip()
]
allowed_origins = [
    value.strip()
    for value in os.getenv(
        "CORS_ORIGINS",
        "https://teams.microsoft.com,https://copilotstudio.microsoft.com",
    ).split(",")
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

from shared_mcp.kill_switch import check_kill_switch, KillSwitchActiveError


def _wrap_tool_handler(tool_name: str, fn):
    async def wrapped(*args, **kwargs):
        # Enforce kill switch evaluation
        check_kill_switch(tool_name=tool_name)

        if tool_name in ADMIN_ONLY_TOOLS:
            # Body-supplied role or __caller_role__ must NEVER grant administration
            kwargs.pop("__caller_role__", None)
            caller_role = os.getenv("MCP_CALLER_ROLE", "")
            if caller_role not in ("Velora_Admin", "GlobalAdmin", "Admin"):
                raise PermissionError(f"Tool '{tool_name}' requires Velora_Admin or GlobalAdmin role.")
        if asyncio.iscoroutinefunction(fn):
            return await fn(*args, **kwargs)
        return fn(*args, **kwargs)
    wrapped.__name__ = fn.__name__
    wrapped.__doc__ = fn.__doc__
    return wrapped

for name, description, handler in TOOL_SPECS:
    mcp.tool(name=name, description=description)(_wrap_tool_handler(name, handler))


async def health(_request):
    return JSONResponse({"status": "ok", "service": "facilitator-mcp-server"})


async def guide_endpoint(request):
    # Enforce authentication
    try:
        extract_verified_identity(dict(request.headers))
    except (AuthenticationError, AuthorizationError) as e:
        return JSONResponse({"error": "Unauthorized", "detail": str(e)}, status_code=401)
    return JSONResponse({
        "service": "facilitator",
        "guide": FACILITATOR_AUTO_SEND_GUIDE,
    })


async def list_tools_endpoint(request):
    try:
        extract_verified_identity(dict(request.headers))
    except (AuthenticationError, AuthorizationError) as e:
        return JSONResponse({"error": "Unauthorized", "detail": str(e)}, status_code=401)
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
    name, _, handler = tool_entry

    # 1. Enforce Authentication (never permit anonymous bypass in production)
    is_prod = os.getenv("ENVIRONMENT", "").lower() == "production" or os.getenv("NODE_ENV") == "production"
    allow_anon = (not is_prod) and (os.getenv("ALLOW_ANONYMOUS", "false").lower() in ("true", "1"))
    identity = None
    if not allow_anon:
        try:
            identity = extract_verified_identity(dict(request.headers))
        except AuthenticationError as e:
            return JSONResponse({"error": "Unauthorized", "message": str(e)}, status_code=401)
        except AuthorizationError as e:
            return JSONResponse({"error": "Forbidden", "message": str(e)}, status_code=403)

    # 2. Enforce Kill-Switch Check
    try:
        check_kill_switch(
            tool_name=name,
            client_id=identity.client_application_id if identity else None,
            tenant_id=identity.tenant_id if identity else None,
        )
    except KillSwitchActiveError as k_err:
        return JSONResponse({"error": "Forbidden", "message": k_err.message}, status_code=403)

    # 3. Enforce HTTP method restriction: GET must not trigger mutating tools
    if request.method == "GET" and name in MUTATING_TOOLS:
        return JSONResponse(
            {
                "error": "Method Not Allowed",
                "message": f"Tool '{name}' modifies state and cannot be invoked via GET. Use POST.",
            },
            status_code=405,
        )

    # 4. Enforce Role-Based Authorization
    if name in ADMIN_ONLY_TOOLS:
        if not identity or not identity.is_admin:
            return JSONResponse(
                {
                    "error": "Forbidden",
                    "message": f"Tool '{name}' requires administrator privileges (Velora_Admin role).",
                },
                status_code=403,
            )

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
    app = mcp.streamable_http_app()
    app.routes.append(Route("/health", health, methods=["GET"]))
    app.routes.append(Route("/guide", guide_endpoint, methods=["GET"]))
    app.routes.append(Route("/mcp/tools", list_tools_endpoint, methods=["GET"]))
    for name, _, _ in TOOL_SPECS:
        app.routes.append(Route(f"/{name}", handle_facilitator_tool_rest, methods=["GET", "POST"]))
        app.routes.append(Route(f"/tools/{name}", handle_facilitator_tool_rest, methods=["GET", "POST"]))
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins if allowed_origins else ["https://copilotstudio.microsoft.com"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8085"))
    uvicorn.run("facilitator_mcp.server:app", host="0.0.0.0", port=port, reload=False)
