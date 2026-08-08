"""SAP SuccessFactors HCM MCP Server — bootstrap and tool registration."""
import hmac
import sys
from pathlib import Path

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route

from .successfactors_settings import get_settings
from .successfactors_tools import PROMPT_SPECS, TOOL_SPECS
from shared_mcp.logger import get_logger
from shared_mcp.telemetry import wrap_specs
from shared_mcp.file_logger import wrap_specs_logging

TOOL_SPECS = wrap_specs_logging(wrap_specs(TOOL_SPECS))

log = get_logger("sf_hcm")
settings = get_settings()

WIDGET_URI = "ui://widget/successfactors.html"
WIDGET_HTML = (Path(__file__).parent / "web" / "widget.html").read_text(encoding="utf-8")

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

for _spec in TOOL_SPECS:
    if _spec["name"] in MUTATING_TOOLS and not settings.enable_mutating_tools:
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

    print("  ┌─ Environment (SuccessFactors) ────────────────")
    print(f"  │ SF_API_URL       {'✓ ' + api_url if api_url else '✗ MISSING'}")
    print(f"  │ SF_COMPANY_ID    {'✓ set' if company else '✗ MISSING'}")
    print(f"  │ SF_USERNAME      {'✓ set' if user else '✗ MISSING'}")
    print(f"  │ SF_PASSWORD      {'✓ set' if pwd else '✗ MISSING'}")
    print("  └────────────────────────────────────────────────")

    missing = []
    if not api_url: missing.append("SF_API_URL")
    if not company: missing.append("SF_COMPANY_ID")
    if not user: missing.append("SF_USERNAME")
    if not pwd: missing.append("SF_PASSWORD")
    if not auth_configured: missing.append("MCP_API_KEY (or explicitly set ALLOW_ANONYMOUS=true for local development)")

    if missing:
        log.error("missing_env_vars", vars=missing)
        print(f"\n  ❌ Missing required env vars: {', '.join(missing)}")
        sys.exit(1)


class ApiKeyMiddleware:
    """Protect the MCP endpoint with a vault-managed API key."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path", "").startswith("/mcp"):
            if not settings.allow_anonymous:
                headers = {key.lower(): value for key, value in scope.get("headers", [])}
                supplied = headers.get(b"x-api-key", b"").decode("utf-8")
                authorization = headers.get(b"authorization", b"").decode("utf-8")
                if not supplied and authorization.lower().startswith("bearer "):
                    supplied = authorization[7:].strip()
                if not settings.mcp_api_key or not hmac.compare_digest(supplied, settings.mcp_api_key):
                    response = JSONResponse({"error": "Unauthorized"}, status_code=401)
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)


async def health(_request):
    return JSONResponse({"status": "ok"})


def create_app():
    app = mcp.streamable_http_app()
    app.routes.append(Route("/health", health, methods=["GET"]))
    app.add_middleware(ApiKeyMiddleware)
    cors_origins = [item.strip() for item in settings.cors_origins.split(",") if item.strip()]
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-API-Key", "mcp-session-id"],
        )
    return app


def main() -> None:
    _validate_env()
    log.info("starting", port=settings.port)
    print(f"⚓ GTC — SAP SuccessFactors MCP Server starting on port {settings.port}")
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
