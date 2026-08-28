"""SAP SuccessFactors HCM MCP Server — bootstrap and tool registration."""
import hmac
import inspect
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .successfactors_settings import get_settings
from .successfactors_tools import PROMPT_SPECS, TOOL_SPECS, _json_response
from .successfactors_tools import sf__get_headcount, sf__get_joiners
from .chart_images import get_chart
from shared_mcp.logger import get_logger
from shared_mcp.telemetry import wrap_specs
from shared_mcp.file_logger import wrap_specs_logging

TOOL_SPECS = wrap_specs_logging(wrap_specs(TOOL_SPECS))

log = get_logger("sf_hcm")
settings = get_settings()

WIDGET_URI = "ui://widget/successfactors.html"
WIDGET_HTML = (Path(__file__).parent / "web" / "widget.html").read_text(encoding="utf-8")
COPILOT_OPENAPI = json.loads(
    (Path(__file__).parent.parent / "deploy" / "copilot-workforce-card-openapi.json").read_text(encoding="utf-8")
)

mcp = FastMCP(
    "gtc-successfactors-hcm",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[item.strip() for item in settings.allowed_hosts.split(",") if item.strip()],
        allowed_origins=[item.strip() for item in settings.allowed_origins.split(",") if item.strip()],
    ),
)


@mcp.resource(WIDGET_URI, mime_type="text/html;profile=mcp-app")
async def successfactors_widget() -> str:
    return WIDGET_HTML


NO_WIDGET_TOOLS = {"sf__get_org_units"}

MUTATING_TOOLS = {"sf__create_emp_job", "sf__update_emp_job", "sf__update_user", "sf__execute_odata"}
PERSONAL_INFO_TOOLS = {"sf__get_personal_info"}

for _spec in TOOL_SPECS:
    if _spec["name"] in MUTATING_TOOLS and not settings.enable_mutating_tools:
        continue
    if _spec["name"] in PERSONAL_INFO_TOOLS and not settings.enable_personal_info_tool:
        continue
    kwargs: dict = {
        "name": _spec["name"],
        "description": _spec["description"],
    }
    if settings.enable_widget and _spec["name"] not in NO_WIDGET_TOOLS:
        kwargs["meta"] = {"ui": {"resourceUri": WIDGET_URI}}
    mcp.tool(**kwargs)(_spec["handler"])

for _spec in PROMPT_SPECS:
    mcp.prompt(name=_spec["name"], description=_spec["description"])(_spec["handler"])


def _validate_env() -> None:
    api_url = settings.sf_api_url
    company = settings.sf_company_id
    user = settings.sf_username
    pwd = settings.sf_password
    auth_configured = bool(settings.mcp_api_key) or settings.allow_anonymous
    parsed_api_url = urlparse(api_url)

    print("  ┌─ Environment (SuccessFactors) ────────────────")
    print(f"  │ SF_API_URL       {'✓ ' + api_url if api_url else '✗ MISSING'}")
    print(f"  │ SF_COMPANY_ID    {'✓ set' if company else '✗ MISSING'}")
    print(f"  │ SF_USERNAME      {'✓ set' if user else '✗ MISSING'}")
    print(f"  │ SF_PASSWORD      {'✓ set' if pwd else '✗ MISSING'}")
    print("  └────────────────────────────────────────────────")

    missing = []
    if not api_url: missing.append("SF_API_URL")
    elif parsed_api_url.scheme != "https" or not parsed_api_url.hostname or parsed_api_url.username or parsed_api_url.password:
        missing.append("SF_API_URL (must be HTTPS without embedded credentials)")
    if not company: missing.append("SF_COMPANY_ID")
    if not user: missing.append("SF_USERNAME")
    if not pwd: missing.append("SF_PASSWORD")
    if not auth_configured: missing.append("MCP_API_KEY (or explicitly set ALLOW_ANONYMOUS=true for local development)")

    if missing:
        log.error("missing_env_vars", vars=missing)
        print(f"\n  ❌ Missing required env vars: {', '.join(missing)}")
        sys.exit(1)


PUBLIC_PATHS = {"/health", "/", "/copilot/logo.png"}


class ApiKeyMiddleware:
    """Protect all non-health endpoints with vault-managed API key."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            path = scope.get("path", "")
            if path not in PUBLIC_PATHS:
                if not settings.allow_anonymous:
                    headers = {key.lower(): value for key, value in scope.get("headers", [])}
                    supplied = headers.get(b"x-api-key", b"").decode("utf-8")
                    authorization = headers.get(b"authorization", b"").decode("utf-8")
                    if not supplied and authorization.lower().startswith("bearer "):
                        supplied = authorization[7:].strip()
                    if not settings.mcp_api_key or not hmac.compare_digest(supplied, settings.mcp_api_key):
                        response = JSONResponse(
                            {
                                "status": "error",
                                "code": "UNAUTHORIZED",
                                "message": "Authentication required. Please provide a valid API key.",
                            },
                            status_code=401,
                        )
                        await response(scope, receive, send)
                        return
        await self.app(scope, receive, send)



class CopilotStudioAcceptMiddleware:
    """Make Power Platform connector calls compatible with Streamable HTTP.

    Copilot Studio's generic connector can send ``Accept: application/json``
    even though the MCP Streamable HTTP transport requires clients to accept
    both JSON and server-sent events. Preserve the caller's accepted media
    types and add ``text/event-stream`` for MCP requests when it is missing.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path", "").startswith("/mcp"):
            headers = list(scope.get("headers", []))
            original_accept = next(
                (value.lower() for key, value in headers if key.lower() == b"accept"),
                b"",
            )
            user_agent = next(
                (value.lower() for key, value in headers if key.lower() == b"user-agent"),
                b"",
            )
            accept_index = next(
                (index for index, (key, _value) in enumerate(headers) if key.lower() == b"accept"),
                None,
            )
            if accept_index is None:
                headers.append((b"accept", b"application/json, text/event-stream"))
            else:
                key, value = headers[accept_index]
                if b"text/event-stream" not in value.lower():
                    headers[accept_index] = (key, value + b", text/event-stream")
            if scope.get("method") == "POST":
                json_only_connector = b"copilotstudio" in user_agent or b"text/event-stream" not in original_accept
                if not json_only_connector:
                    # A conforming MCP client already accepts the streamable
                    # transport. Do not consume/replay its body: FastMCP owns
                    # the receive channel, including disconnect handling.
                    scope = {**scope, "headers": headers}
                    await self.app(scope, receive, send)
                    return
                upstream_receive = receive
                chunks = []
                more_body = True
                while more_body:
                    message = await upstream_receive()
                    chunks.append(message.get("body", b""))
                    more_body = message.get("more_body", False)
                body = b"".join(chunks)
                try:
                    payload = json.loads(body)
                    if isinstance(payload, dict):
                        for key in ("jsonrpc", "id", "method"):
                            value = payload.get(key)
                            if isinstance(value, str) and value.startswith('"'):
                                payload[key] = json.loads(value)
                        params = payload.get("params")
                        if isinstance(params, str):
                            payload["params"] = json.loads(params)
                        for key in ("result", "error", "sessionId", "Session Id"):
                            if payload.get(key) in (None, ""):
                                payload.pop(key, None)
                        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                        headers = [(key, value) for key, value in headers if key.lower() != b"content-length"]
                        headers.append((b"content-length", str(len(body)).encode("ascii")))
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass

                # Power Platform's connector expects one JSON response and
                # cannot consume the event stream used by Streamable HTTP.
                # Serve aggregate tools directly for that
                # JSON-only connector shape; regular MCP clients continue
                # through the standard transport below.
                if json_only_connector:
                    try:
                        direct_payload = json.loads(body)
                        params = direct_payload.get("params", {})
                        method = direct_payload.get("method")
                        request_id = direct_payload.get("id")
                        if method == "initialize":
                            response = JSONResponse({
                                "jsonrpc": "2.0", "id": request_id,
                                "result": {
                                    "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                                    "capabilities": {"tools": {"listChanged": False}},
                                    "serverInfo": {"name": "gtc-successfactors-hcm", "version": "1.0.0"},
                                },
                            })
                            await response(scope, receive, send)
                            return
                        if method == "tools/list":
                            registered_tools = await mcp.list_tools()
                            response = JSONResponse({
                                "jsonrpc": "2.0", "id": request_id,
                                "result": {"tools": [tool.model_dump(mode="json", by_alias=True, exclude_none=True) for tool in registered_tools]},
                            })
                            await response(scope, receive, send)
                            return
                        if method == "ping":
                            response = JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": {}})
                            await response(scope, receive, send)
                            return
                        if method == "notifications/initialized":
                            response = Response(status_code=202)
                            await response(scope, receive, send)
                            return
                        direct_handlers = {}
                        for spec in TOOL_SPECS:
                            sname = spec["name"]
                            shandler = spec["handler"]
                            direct_handlers[sname] = shandler
                            direct_handlers[sname.replace("sf__", "sf_")] = shandler
                            direct_handlers[sname.replace("_", "")] = shandler

                        tool_name = str(params.get("name") or "")
                        handler = direct_handlers.get(tool_name) or direct_handlers.get(tool_name.replace("sf_", "sf__")) or direct_handlers.get(tool_name.replace("_", ""))
                        if method == "tools/call":
                            class _DirectContext:
                                async def report_progress(self, *_args, **_kwargs):
                                    return None

                            arguments = params.get("arguments") or {}
                            
                            # Extract user context headers
                            headers_dict = {k.decode("latin1").lower(): v.decode("latin1") for k, v in headers}
                            user_obj_id = headers_dict.get("x-user-object-id", "")
                            user_email_hdr = headers_dict.get("x-user-email", "")
                            user_display_name_hdr = headers_dict.get("x-user-display-name", "")
                            user_roles_hdr = [r.strip() for r in headers_dict.get("x-user-roles", "").split(",") if r.strip()]

                            if handler:
                                try:
                                    parameters = inspect.signature(handler).parameters
                                    # Inject user identity if parameter accepted and not already supplied
                                    if "user_object_id" in parameters and "user_object_id" not in arguments and user_obj_id:
                                        arguments["user_object_id"] = user_obj_id
                                    if "user_email" in parameters and "user_email" not in arguments and user_email_hdr:
                                        arguments["user_email"] = user_email_hdr
                                    if "user_display_name" in parameters and "user_display_name" not in arguments and user_display_name_hdr:
                                        arguments["user_display_name"] = user_display_name_hdr

                                    if "ctx" in parameters:
                                        tool_result = await handler(_DirectContext(), **arguments)
                                    else:
                                        tool_result = await handler(**arguments)
                                    result_data = tool_result.model_dump(
                                        mode="json", by_alias=True, exclude_none=True
                                    )
                                except Exception as exc:
                                    log.error("direct_tool_call_failed", tool=tool_name, error=str(exc))
                                    error_result = _json_response({
                                        "error": True,
                                        "error_category": "tool_execution",
                                        "tool": tool_name,
                                        "message": str(exc),
                                    })
                                    result_data = error_result.model_dump(
                                        mode="json", by_alias=True, exclude_none=True
                                    )
                            else:
                                error_result = _json_response({
                                    "error": True,
                                    "error_category": "validation",
                                    "tool": tool_name,
                                    "message": "Unknown or unavailable SuccessFactors tool.",
                                })
                                result_data = error_result.model_dump(
                                    mode="json", by_alias=True, exclude_none=True
                                )
                            response = JSONResponse(
                                {
                                    "jsonrpc": "2.0",
                                    "id": direct_payload.get("id"),
                                    "result": result_data,
                                }
                            )
                            await response(scope, receive, send)
                            return
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass

                sent = False

                async def normalized_receive():
                    nonlocal sent
                    if sent:
                        # After the replayed body, wait for the real client
                        # disconnect. Returning an immediate empty request on
                        # every read creates a tight loop in MCP's disconnect
                        # listener and can consume the entire app instance.
                        return await upstream_receive()
                    sent = True
                    return {"type": "http.request", "body": body, "more_body": False}

                receive = normalized_receive
            scope = {**scope, "headers": headers}
        await self.app(scope, receive, send)


async def health(_request):
    from .connection_manager import get_connection_manager
    mgr = get_connection_manager()
    conns = mgr.list_connections()
    return JSONResponse({
        "status": "healthy",
        "service": "sf-hcm-mcp-server",
        "connections_managed": len(conns),
        "connections": [
            {
                "id": c.connection_id,
                "name": c.connection_name,
                "status": c.status.value,
                "enabled": c.enabled,
            }
            for c in conns
        ],
    })


async def copilot_openapi(_request):
    return JSONResponse(COPILOT_OPENAPI)


async def copilot_plugin_manifest(_request):
    base_url = settings.public_base_url.rstrip("/")
    return JSONResponse({
        "schema_version": "v1",
        "name_for_human": "Velora SuccessFactors Workforce Cards",
        "name_for_model": "velora_successfactors_workforce_cards",
        "description_for_human": "Verified SuccessFactors workforce metrics rendered as Adaptive Cards with text fallback.",
        "description_for_model": "Use for aggregate headcount, Emiratisation, joiners, leavers, attrition, workforce trends, and dashboard requests. Prefer adaptiveCard; use fallbackText if the channel cannot render it.",
        "auth": {"type": "none"},
        "api": {
            "type": "openapi",
            "url": f"{base_url}/copilot/openapi.json",
            "is_user_authenticated": False,
        },
        "logo_url": f"{base_url}/copilot/logo.png",
        "contact_email": "support@velora.ai",
        "legal_info_url": "https://velora.ai/",
    })


async def copilot_logo(_request):
    # A standards-based 1x1 transparent PNG keeps plugin import independent of
    # an external asset host. Copilot Studio replaces it with the agent icon.
    return Response(
        bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360606060000000050001a5f645400000000049454e44ae426082"),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


async def chart_image(request):
    chart_id = request.path_params.get("chart_id", "")
    image = get_chart(chart_id)
    if image is None:
        return Response(status_code=404)
    return Response(
        image,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=900", "X-Content-Type-Options": "nosniff"},
    )


class _CopilotContext:
    """No-op progress context for synchronous Agent Flow HTTP calls."""

    async def report_progress(self, *_args, **_kwargs):
        return None


COPILOT_CARD_TOOLS = {
    "headcount": "sf__get_headcount",
    "emiratisation": "sf__get_emiratisation_kpi",
    "emiratization": "sf__get_emiratisation_kpi",
    "joiners": "sf__get_joiners",
    "leavers": "sf__get_leavers",
    "attrition": "sf__get_attrition",
    "trend": "sf__get_joiners_leavers_trend",
    "joiners_leavers_trend": "sf__get_joiners_leavers_trend",
    "analytics_dashboard": "sf__get_analytics_dashboard",
    "dashboard": "sf__get_analytics_dashboard",
}


def _copilot_card_payload(structured: dict, metric: str) -> dict:
    """Flatten an MCP card into fields that Agent Flow can bind reliably."""
    card = structured.get("adaptiveCard") if isinstance(structured, dict) else None
    card = card if isinstance(card, dict) else {}
    title = "SuccessFactors workforce result"
    subtitle = "SAP SuccessFactors"
    status = ""
    note = ""
    facts: list[dict[str, str]] = []
    for element in card.get("body", []):
        if not isinstance(element, dict):
            continue
        element_type = element.get("type")
        text = str(element.get("text") or "").strip()
        if element_type == "TextBlock":
            if text and title == "SuccessFactors workforce result":
                title = text
            elif text and subtitle == "SAP SuccessFactors":
                subtitle = text
            elif text and element.get("weight") == "Bolder" and not status:
                status = text
            elif text and element.get("isSubtle") and element.get("separator"):
                note = text
        elif element_type == "FactSet":
            for fact in element.get("facts", []):
                if isinstance(fact, dict):
                    facts.append({
                        "title": str(fact.get("title") or ""),
                        "value": str(fact.get("value") or "—"),
                    })

    is_error = bool(structured.get("error"))
    if is_error and not note:
        note = str(structured.get("message") or "The requested workforce data could not be verified.")
    readable = [title]
    if subtitle:
        readable.append(subtitle)
    if status:
        readable.append(status)
    readable.extend(f"{fact['title']}: {fact['value']}" for fact in facts[:6] if fact["title"])
    if note:
        readable.append(note)

    payload = {
        "success": not is_error,
        "metric": metric,
        "cardTitle": title,
        "cardSubtitle": subtitle,
        "cardStatus": status,
        "cardNote": note,
        "fallbackText": "\n".join(readable),
        "adaptiveCard": card,
        "adaptiveCardJson": json.dumps(card, separators=(",", ":")),
        "presentationPreference": "adaptive_card",
        "fallbackPresentation": "text",
    }
    for index in range(6):
        fact = facts[index] if index < len(facts) else {"title": "", "value": ""}
        payload[f"fact{index + 1}Title"] = fact["title"]
        payload[f"fact{index + 1}Value"] = fact["value"]
    return payload


async def copilot_workforce_card(request):
    """Typed HTTP action for Copilot Studio Adaptive Card completions."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, TypeError, ValueError):
        body = {}
    body = body if isinstance(body, dict) else {}
    metric = str(body.pop("metric", "")).strip().lower().replace("-", "_").replace(" ", "_")
    tool_name = COPILOT_CARD_TOOLS.get(metric)
    handlers = {spec["name"]: spec["handler"] for spec in TOOL_SPECS}
    handler = handlers.get(tool_name or "")
    if handler is None:
        structured = {
            "error": True,
            "message": "Choose a supported aggregate metric: headcount, emiratisation, joiners, leavers, attrition, trend, or dashboard.",
        }
        return JSONResponse(_copilot_card_payload(structured, metric or "unknown"))

    allowed = set(inspect.signature(handler).parameters) - {"ctx"}
    arguments = {key: value for key, value in body.items() if key in allowed and value not in (None, "")}
    try:
        if "ctx" in inspect.signature(handler).parameters:
            result = await handler(_CopilotContext(), **arguments)
        else:
            result = await handler(**arguments)
        structured = result.structuredContent or {}
    except Exception as exc:
        log.error("copilot_card_call_failed", metric=metric, error=str(exc))
        structured = {
            "error": True,
            "error_category": "service",
            "message": "I couldn't retrieve that information right now. Please try again shortly.",
        }
    return JSONResponse(_copilot_card_payload(structured, metric))


async def api_policies(request):
    """REST API for Dataverse policy listing and management."""
    from .policy_admin import get_policy_admin
    admin = get_policy_admin()
    if request.method == "POST":
        try:
            body = await request.json()
        except Exception:
            body = {}
        action = body.get("action", "create")
        if action == "activate":
            res = await admin.activate_policy(body.get("policy_id", ""))
        else:
            res = await admin.create_or_update_policy(
                policy_name=body.get("policy_name", "Custom Policy"),
                policy_code=body.get("policy_code", "POL_CUSTOM"),
                version=body.get("version", "1.0.0"),
                allowed_fields=body.get("allowed_fields", []),
                is_active=body.get("is_active", False),
            )
        return JSONResponse(res)
    policies = await admin.list_policies()
    return JSONResponse({"policies": policies, "total": len(policies)})


async def api_policy_preview(request):
    """REST API for disclosure policy output simulation."""
    from .policy_admin import get_policy_admin
    admin = get_policy_admin()
    try:
        body = await request.json()
    except Exception:
        body = {}
    query = body.get("sample_query", "Who are the 15 employees in Unassigned?")
    profile = body.get("profile", "workforce_drilldown")
    res = admin.preview_policy_output(sample_query=query, profile=profile)
    return JSONResponse(res)


async def api_consent(request):
    """REST API for consent verification and recording."""
    from .consent_service import get_consent_service
    svc = get_consent_service()
    if request.method == "POST":
        try:
            body = await request.json()
        except Exception:
            body = {}
        res = await svc.record_user_consent(
            user_object_id=body.get("user_object_id", ""),
            user_email=body.get("user_email", ""),
            accepted=bool(body.get("accepted", False)),
            notice_version=body.get("notice_version", "2026.1"),
        )
        return JSONResponse(res)
    user_object_id = request.query_params.get("user_object_id", "")
    user_email = request.query_params.get("user_email", "")
    is_consented, card = await svc.verify_user_consent(user_object_id, user_email)
    return JSONResponse({"is_consented": is_consented, "card": card})


async def api_memory(request):
    """REST API for 30-day user memory recall."""
    from .memory_service import get_memory_service
    svc = get_memory_service()
    user_object_id = request.query_params.get("user_object_id", "")
    user_email = request.query_params.get("user_email", "")
    topic = request.query_params.get("topic")
    res = await svc.recall_user_context(user_object_id, user_email, topic_query=topic)
    return JSONResponse(res)


async def api_connections(request):
    """REST API for listing and registering managed enterprise connections."""
    from .connection_admin import get_connection_admin_service
    admin_svc = get_connection_admin_service()
    env = request.query_params.get("environment")
    conns = admin_svc.list_connections_for_user(user_roles=["Admin"], environment=env)
    return JSONResponse({"connections": conns, "total": len(conns)})


async def api_connection_test(request):
    """REST API for testing an enterprise connection."""
    from .connection_admin import get_connection_admin_service
    admin_svc = get_connection_admin_service()
    conn_id = request.path_params.get("conn_id", "")
    res = await admin_svc.test_connection(conn_id, user_roles=["Admin"])
    return JSONResponse(res)


async def api_connection_toggle(request):
    """REST API for toggling connection enabled/disabled status."""
    from .connection_admin import get_connection_admin_service
    admin_svc = get_connection_admin_service()
    admin_email = "platform-admin@velora.ae"
    conn_id = request.path_params.get("conn_id", "")
    try:
        body = await request.json()
    except Exception:
        body = {}
    enabled = bool(body.get("enabled", True))
    res = admin_svc.toggle_connection_status(conn_id, enabled=enabled, admin_email=admin_email, user_roles=["Admin"])
    return JSONResponse(res)


async def api_connection_rotate(request):
    """REST API for rotating secret references."""
    from .connection_admin import get_connection_admin_service
    admin_svc = get_connection_admin_service()
    admin_email = "platform-admin@velora.ae"
    conn_id = request.path_params.get("conn_id", "")
    try:
        body = await request.json()
    except Exception:
        body = {}
    new_secret_ref = body.get("new_secret_ref", "")
    res = admin_svc.rotate_secret_reference(conn_id, new_secret_ref=new_secret_ref, admin_email=admin_email, user_roles=["Admin"])
    return JSONResponse(res)



async def api_cache_purge(request):
    """REST API for purging all in-process cache tiers."""
    from .cache import get_multi_layer_cache
    cache_mgr = get_multi_layer_cache()
    await cache_mgr.purge_all()
    return JSONResponse({"status": "SUCCESS", "message": "All cache tiers purged successfully."})


def create_app():
    app = mcp.streamable_http_app()
    app.routes.append(Route("/health", health, methods=["GET"]))
    app.routes.append(Route("/charts/{chart_id}.png", chart_image, methods=["GET"]))
    app.routes.append(Route("/copilot/ai-plugin.json", copilot_plugin_manifest, methods=["GET"]))
    app.routes.append(Route("/copilot/openapi.json", copilot_openapi, methods=["GET"]))
    app.routes.append(Route("/copilot/logo.png", copilot_logo, methods=["GET"]))
    app.routes.append(Route("/copilot/workforce-card", copilot_workforce_card, methods=["POST"]))
    app.routes.append(Route("/api/policies", api_policies, methods=["GET", "POST"]))
    app.routes.append(Route("/api/policies/preview", api_policy_preview, methods=["POST"]))
    app.routes.append(Route("/api/consent", api_consent, methods=["GET", "POST"]))
    app.routes.append(Route("/api/memory", api_memory, methods=["GET"]))
    app.routes.append(Route("/api/cache/purge", api_cache_purge, methods=["POST"]))
    app.routes.append(Route("/api/connections", api_connections, methods=["GET"]))
    app.routes.append(Route("/api/connections/{conn_id}/test", api_connection_test, methods=["POST"]))
    app.routes.append(Route("/api/connections/{conn_id}/toggle", api_connection_toggle, methods=["POST"]))
    app.routes.append(Route("/api/connections/{conn_id}/rotate", api_connection_rotate, methods=["POST"]))
    app.add_middleware(CopilotStudioAcceptMiddleware)
    app.add_middleware(ApiKeyMiddleware)
    cors_origins = [item.strip() for item in settings.cors_origins.split(",") if item.strip()]
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-API-Key", "mcp-session-id", "X-User-Object-ID", "X-User-Email", "X-User-Roles", "X-User-Display-Name"],
        )
    return app


def main() -> None:
    _validate_env()
    log.info("starting", port=settings.port)
    print(f"⚓ GTC — SAP SuccessFactors MCP Server starting on port {settings.port}")
    
    # Start background logger
    from .background_logger import get_background_logger
    get_background_logger().start()

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
