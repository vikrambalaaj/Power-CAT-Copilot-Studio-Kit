"""Facilitator MCP Server with Strict Identity, Authorization, and Governed Writes."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import inspect
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple, Union
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


def _authorize_arguments(tool_name, handler, arguments, identity):
    """Apply the same verified authorization boundary on REST and native MCP."""
    args = dict(arguments)
    if identity is None:
        raise AuthenticationError("Missing verified request identity")
    if "db_path" in args or "__caller_role__" in args:
        raise AuthorizationError("Client cannot specify internal execution parameters")
    if tool_name in ADMIN_ONLY_TOOLS and not identity.is_admin:
        raise AuthorizationError("Tool requires administrator privileges (Velora_Admin role)")
    if tool_name == "export_decision_trail" and not (identity.is_admin or "AUDITOR" in identity.roles):
        raise AuthorizationError("Tool requires AUDITOR or Administrator role")
    check_kill_switch(tool_name=tool_name, client_id=identity.client_application_id,
                      tenant_id=identity.tenant_id)
    from shared_mcp.policy_matrix import enforce_mcp_policy
    enforce_mcp_policy(identity=identity, mcp_server="ask-facilitator", tool_name=tool_name)
    params = inspect.signature(handler).parameters
    bindings = {"tenant_id": identity.tenant_id, "actor_object_id": identity.object_id,
                "user_object_id": identity.object_id, "recorded_by": identity.object_id}
    for key, verified in bindings.items():
        supplied = args.get(key)
        if supplied and supplied != verified:
            raise AuthorizationError(f"Supplied {key} conflicts with authenticated identity")
        if key in params:
            args[key] = verified
        else:
            args.pop(key, None)
    if "user_email" in params:
        supplied = args.get("user_email")
        if not identity.display_email or (supplied and supplied.lower() != identity.display_email.lower()):
            raise AuthorizationError("User email must match authenticated identity")
        args["user_email"] = identity.display_email
    for key, verified in (("caller_roles", identity.roles), ("caller_entity_scopes", identity.scopes)):
        supplied = args.get(key)
        if supplied is not None:
            values = [supplied] if isinstance(supplied, str) else supplied
            if not isinstance(values, (list, tuple, set)) or not all(isinstance(v, str) for v in values):
                raise AuthorizationError(f"Invalid {key}")
            if not set(values).issubset(verified):
                raise AuthorizationError(f"Caller is not authorized for requested {key}")
        if key in params:
            args[key] = sorted(verified)
        else:
            args.pop(key, None)
    return args


def _wrap_tool_handler(tool_name: str, fn):
    from functools import wraps
    sig = inspect.signature(fn, eval_str=True)
    tool_sig = sig.replace(parameters=[p for p in sig.parameters.values()
                                      if p.name not in ("db_path", "__caller_role__")])

    @wraps(fn)
    async def wrapped(*args, **kwargs):
        try:
            request = mcp.get_context().request_context.request
            identity = getattr(request.state, "identity", None)
        except (ValueError, AttributeError):
            identity = None
        bound = tool_sig.bind(*args, **kwargs)
        call_args = _authorize_arguments(tool_name, fn, bound.arguments, identity)
        if asyncio.iscoroutinefunction(fn):
            return await fn(**call_args)
        return await asyncio.to_thread(fn, **call_args)

    wrapped.__signature__ = tool_sig
    return wrapped

for name, description, handler in TOOL_SPECS:
    mcp.tool(name=name, description=description)(_wrap_tool_handler(name, handler))


async def health(_request):
    return JSONResponse({"status": "ok", "service": "facilitator-mcp-server"})


def _require_request_identity(request):
    identity = getattr(request.state, "identity", None)
    if identity is None:
        raise AuthenticationError("Missing verified request identity")
    return identity


async def guide_endpoint(request):
    # Enforce authentication
    try:
        _require_request_identity(request)
    except (AuthenticationError, AuthorizationError) as e:
        return JSONResponse({"error": "Unauthorized", "detail": str(e)}, status_code=401)
    return JSONResponse({
        "service": "facilitator",
        "guide": FACILITATOR_AUTO_SEND_GUIDE,
    })


async def list_tools_endpoint(request):
    try:
        _require_request_identity(request)
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
    is_prod = (
        os.getenv("VELORA_ENV", "").lower() in ("production", "prod")
        or os.getenv("ENVIRONMENT", "").lower() in ("production", "prod")
        or os.getenv("NODE_ENV", "").lower() in ("production", "prod")
    )
    allow_anon = (not is_prod) and (os.getenv("ALLOW_ANONYMOUS", "false").lower() in ("true", "1"))
    identity = getattr(request.state, "identity", None) if hasattr(request, "state") else None
    if not identity and not allow_anon:
        try:
            identity = _require_request_identity(request)
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

    if name == "export_decision_trail":
        if not identity or not ("AUDITOR" in identity.roles or identity.is_admin):
            return JSONResponse(
                {
                    "error": "Forbidden",
                    "message": "Tool 'export_decision_trail' requires AUDITOR or Administrator role.",
                },
                status_code=403,
            )

    # 5. Enforce Dataverse MCP Priority Matrix
    try:
        from shared_mcp.policy_matrix import enforce_mcp_policy
        enforce_mcp_policy(identity=identity, mcp_server="ask-facilitator", tool_name=name)
    except AuthorizationError as e:
        return JSONResponse({"error": "Forbidden", "message": str(e)}, status_code=403)

    args = dict(request.query_params)
    if request.method == "POST":
        try:
            body = await request.json()
            if isinstance(body, dict):
                args.update(body.get("arguments", body.get("params", body)))
        except Exception:
            pass

    try:
        args = _authorize_arguments(name, handler, args, identity)
    except (AuthenticationError, AuthorizationError, KillSwitchActiveError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=getattr(exc, "status_code", 403))

    try:
        if asyncio.iscoroutinefunction(handler):
            res = await handler(**args)
        else:
            res = await asyncio.to_thread(handler, **args)
        return JSONResponse(res if isinstance(res, dict) else {"result": res, "status": "success"})
    except Exception as ex:
        log.error(f"Error executing tool {path}: {ex}", exc_info=True)
        return JSONResponse({"error": str(ex), "status": "error"}, status_code=500)


class McpAuthMiddleware:
    """Protect native MCP endpoints and REST transports with verified identity."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path in ("/health", "/healthz") or scope.get("method") == "OPTIONS":
                await self.app(scope, receive, send)
                return

            is_prod = (
                os.getenv("VELORA_ENV", "").lower() in ("production", "prod")
                or os.getenv("ENVIRONMENT", "").lower() in ("production", "prod")
                or os.getenv("NODE_ENV", "").lower() in ("production", "prod")
            )
            allow_anon = (not is_prod) and (os.getenv("ALLOW_ANONYMOUS", "false").lower() in ("true", "1"))

            if not allow_anon:
                raw_headers = scope.get("headers", [])
                norm_headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in raw_headers}
                try:
                    chunks = []
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunks.append(message.get("body", b""))
                        if not message.get("more_body", False):
                            break
                    body_bytes = b"".join(chunks)
                    request_path = path
                    if scope.get("query_string"):
                        request_path += "?" + scope["query_string"].decode("latin1")
                    identity = extract_verified_identity(norm_headers, method=scope.get("method"),
                                                         path=request_path, body=body_bytes)
                    original_receive = receive
                    replayed = False
                    async def replay_receive():
                        nonlocal replayed
                        if not replayed:
                            replayed = True
                            return {"type": "http.request", "body": body_bytes, "more_body": False}
                        return await original_receive()
                    receive = replay_receive
                    if "state" not in scope:
                        scope["state"] = {}
                    scope["state"]["identity"] = identity
                except (AuthenticationError, AuthorizationError) as e:
                    status = 401 if isinstance(e, AuthenticationError) else 403
                    body = json.dumps({"error": "Unauthorized" if status == 401 else "Forbidden", "message": str(e)}).encode("utf-8")
                    await send({
                        "type": "http.response.start",
                        "status": status,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode("latin1")),
                        ],
                    })
                    await send({
                        "type": "http.response.body",
                        "body": body,
                    })
                    return

        await self.app(scope, receive, send)


def create_app():
    app = mcp.streamable_http_app()
    app.routes.append(Route("/health", health, methods=["GET"]))
    app.routes.append(Route("/guide", guide_endpoint, methods=["GET"]))
    app.routes.append(Route("/mcp/tools", list_tools_endpoint, methods=["GET"]))
    for name, _, _ in TOOL_SPECS:
        app.routes.append(Route(f"/{name}", handle_facilitator_tool_rest, methods=["GET", "POST"]))
        app.routes.append(Route(f"/tools/{name}", handle_facilitator_tool_rest, methods=["GET", "POST"]))

    app.add_middleware(McpAuthMiddleware)
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
