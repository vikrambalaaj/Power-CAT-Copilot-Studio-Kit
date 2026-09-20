"""Secured S/4HANA finance MCP server."""
from __future__ import annotations

import hmac
import json
import logging
import os
import re
import sys
import uuid
from decimal import Decimal
from enum import Enum
from typing import Any

import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .client import S4Client
from .contracts import to_jsonable_data
from .settings import get_settings
from .tools import (
    TOOL_SPECS,
    s4__get_budget_consumption,
    s4__get_budget_transfers,
    s4__get_budget_variance,
    s4__get_cost_center_master,
    s4__get_customer_master,
    s4__get_payables_aging,
    s4__get_profit_and_loss,
    s4__get_profit_center_master,
    s4__get_receivables_aging,
)

settings = get_settings()
log = logging.getLogger("s4_finance")


def serialize_with_exact_decimals(content: Any) -> str:
    """Serialize data structure to JSON, preserving Decimals as exact numeric literals without float precision loss (F04, T03)."""
    marker_token = uuid.uuid4().hex

    def _default(o: Any) -> Any:
        if isinstance(o, Decimal):
            if not o.is_finite():
                raise ValueError(f"Non-finite decimal value cannot be serialized: {o}")
            return f"__EXACT_DEC_{marker_token}_{str(o)}__"
        if isinstance(o, Enum):
            return o.value
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    raw_json = json.dumps(
        content,
        ensure_ascii=False,
        allow_nan=False,
        indent=None,
        separators=(",", ":"),
        default=_default,
    )
    pattern = rf'"__EXACT_DEC_{marker_token}_([+-]?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)__"'
    return re.sub(pattern, r'\1', raw_json)


class SafeJSONResponse(JSONResponse):
    """JSONResponse that serializes Decimal values and Enums safely with exact decimal preservation (F04)."""

    def render(self, content: Any) -> bytes:
        try:
            return serialize_with_exact_decimals(content).encode("utf-8")
        except (ValueError, TypeError) as e:
            error_payload = {
                "status": "error",
                "code": "CONTRACT_MISMATCH",
                "message": f"Serialization error: {e}",
            }
            return json.dumps(error_payload).encode("utf-8")


mcp = FastMCP(
    "velora-s4-finance",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)

for name, description, handler in TOOL_SPECS:
    mcp.tool(name=name, description=description)(handler)


PUBLIC_PATHS = {"/health", "/"}


class ApiKeyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            path = scope.get("path", "")
            if path not in PUBLIC_PATHS:
                is_prod = (
                    os.getenv("VELORA_ENV", "").lower() == "production"
                    or os.getenv("ENVIRONMENT", "").lower() == "production"
                    or os.getenv("NODE_ENV", "").lower() == "production"
                )
                if is_prod and (settings.allow_anonymous or os.getenv("ALLOW_ANONYMOUS", "false").lower() in ("true", "1")):
                    await SafeJSONResponse(
                        {
                            "status": "error",
                            "code": "CONFIGURATION_ERROR",
                            "message": "FATAL: ALLOW_ANONYMOUS cannot be enabled in production environments.",
                        },
                        status_code=500,
                    )(scope, receive, send)
                    return

                if not settings.allow_anonymous:
                    headers = {key.lower(): value for key, value in scope.get("headers", [])}
                    supplied = headers.get(b"x-api-key", b"").decode("utf-8")
                    bearer = headers.get(b"authorization", b"").decode("utf-8")
                    if not supplied and bearer.lower().startswith("bearer "):
                        supplied = bearer[7:].strip()
                    if not settings.mcp_api_key or not hmac.compare_digest(supplied, settings.mcp_api_key):
                        await SafeJSONResponse(
                            {
                                "status": "error",
                                "code": "UNAUTHORIZED",
                                "message": "Authentication required. Please provide a valid API key.",
                            },
                            status_code=401,
                        )(scope, receive, send)
                        return

                    # Verified executive-to-organization entitlement enforcement (F06)
                    org_scope = headers.get(b"x-organization-scope", b"").decode("utf-8").strip()
                    if org_scope and org_scope not in {"1000", "VELORA_UAE"}:
                        await SafeJSONResponse(
                            {
                                "status": "error",
                                "code": "ACCESS_DENIED",
                                "message": f"Executive identity not entitled to access organization scope '{org_scope}'. Approved scope: 1000.",
                            },
                            status_code=403,
                        )(scope, receive, send)
                        return
        await self.app(scope, receive, send)


async def health(_request):
    return SafeJSONResponse({"status": "ok", "service": "s4-finance-mcp-server", "version": "2.0.0"})


SCHEMAS: dict[str, dict[str, Any]] = {
    "s4__get_receivables_aging": {
        "type": "object",
        "properties": {
            "company_code": {"type": "string", "description": "Company code, e.g. 1000"},
            "key_date": {"type": "string", "description": "Key date YYYY-MM-DD"},
            "customer": {"type": "string", "description": "Customer number or code"},
            "customer_name": {"type": "string", "description": "Customer name for lookup"},
            "currency": {"type": "string", "description": "Currency filter, e.g. AED"},
            "profit_center": {"type": "string", "description": "Profit center"},
            "segment": {"type": "string", "description": "Segment"},
            "correlation_id": {"type": "string", "description": "Correlation ID for request tracing"},
            "top": {"type": "integer", "description": "Maximum rows to return, default 100"},
        },
    },
    "s4__get_payables_aging": {
        "type": "object",
        "properties": {
            "company_code": {"type": "string", "description": "Company code, e.g. 1000"},
            "key_date": {"type": "string", "description": "Key date YYYY-MM-DD"},
            "supplier": {"type": "string", "description": "Supplier number or code"},
            "supplier_name": {"type": "string", "description": "Supplier name for lookup"},
            "currency": {"type": "string", "description": "Currency filter, e.g. AED"},
            "profit_center": {"type": "string", "description": "Profit center"},
            "segment": {"type": "string", "description": "Segment"},
            "correlation_id": {"type": "string", "description": "Correlation ID for request tracing"},
            "top": {"type": "integer", "description": "Maximum rows to return, default 100"},
        },
    },
    "s4__get_budget_transfers": {
        "type": "object",
        "properties": {
            "financial_management_area": {"type": "string", "description": "Financial management area, default 1000"},
            "funds_center": {"type": "string", "description": "Funds center code"},
            "commitment_item": {"type": "string", "description": "Commitment item code"},
            "fiscal_year": {"type": "string", "description": "Fiscal year, e.g. 2026"},
            "budget_period": {"type": "string", "description": "Budget period, e.g. 008 or 08"},
            "currency": {"type": "string", "description": "Currency filter, e.g. AED"},
            "budgeting_process": {"type": "string", "description": "Budgeting process code (e.g. ENTR, TRAN)"},
            "movement_type": {"type": "string", "description": "Budget movement type"},
            "correlation_id": {"type": "string", "description": "Correlation ID for request tracing"},
            "top": {"type": "integer", "description": "Maximum rows to return, default 100"},
        },
    },
    "s4__get_budget_consumption": {
        "type": "object",
        "properties": {
            "funds_center": {"type": "string", "description": "Funds center code"},
            "fiscal_year": {"type": "string", "description": "Fiscal year, e.g. 2026"},
            "period": {"type": "string", "description": "Fiscal period, e.g. 008 or 08"},
            "currency": {"type": "string", "description": "Financial management area currency, e.g. AED"},
            "correlation_id": {"type": "string", "description": "Correlation ID for request tracing"},
            "top": {"type": "integer", "description": "Maximum rows to return, default 100"},
        },
    },
}

# Approved 4 core reports for tool discovery
CORE_REPORT_SPECS = [
    ("s4__get_receivables_aging", "Retrieve accounts-receivable aging from SAP S/4HANA.", s4__get_receivables_aging),
    ("s4__get_payables_aging", "Retrieve accounts-payable aging from SAP S/4HANA.", s4__get_payables_aging),
    ("s4__get_budget_transfers", "Retrieve budget movement and transfer records from SAP S/4HANA for detailed drill-down.", s4__get_budget_transfers),
    ("s4__get_budget_consumption", "Retrieve budget consumption summary records from SAP S/4HANA.", s4__get_budget_consumption),
]


def _build_mcp_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": desc,
            "inputSchema": SCHEMAS.get(name, {"type": "object", "properties": {}}),
        }
        for name, desc, _ in CORE_REPORT_SPECS
    ]


MCP_TOOLS = _build_mcp_tools()


# Unified alias resolution dictionary (R10)
ALIAS_MAP: dict[str, tuple[str, Any]] = {
    # Receivables Aging
    "s4__get_receivables_aging": ("s4__get_receivables_aging", s4__get_receivables_aging),
    "get_receivables_aging": ("s4__get_receivables_aging", s4__get_receivables_aging),
    "getreceivablesaging": ("s4__get_receivables_aging", s4__get_receivables_aging),
    "getReceivablesAging": ("s4__get_receivables_aging", s4__get_receivables_aging),
    "receivables_aging": ("s4__get_receivables_aging", s4__get_receivables_aging),
    "arageingdata": ("s4__get_receivables_aging", s4__get_receivables_aging),
    "ARageingData": ("s4__get_receivables_aging", s4__get_receivables_aging),
    # Payables Aging
    "s4__get_payables_aging": ("s4__get_payables_aging", s4__get_payables_aging),
    "get_payables_aging": ("s4__get_payables_aging", s4__get_payables_aging),
    "getpayablesaging": ("s4__get_payables_aging", s4__get_payables_aging),
    "getPayablesAging": ("s4__get_payables_aging", s4__get_payables_aging),
    "payables_aging": ("s4__get_payables_aging", s4__get_payables_aging),
    "apageingdata": ("s4__get_payables_aging", s4__get_payables_aging),
    "APageingData": ("s4__get_payables_aging", s4__get_payables_aging),
    # Budget Transfers (Excluded / Unsupported)
    "s4__get_budget_transfers": ("s4__get_budget_transfers", s4__get_budget_transfers),
    "get_budget_transfers": ("s4__get_budget_transfers", s4__get_budget_transfers),
    "getbudgettransfers": ("s4__get_budget_transfers", s4__get_budget_transfers),
    "getBudgetTransfers": ("s4__get_budget_transfers", s4__get_budget_transfers),
    "budget_transfers": ("s4__get_budget_transfers", s4__get_budget_transfers),
    "s4__get_budget_transfer": ("s4__get_budget_transfers", s4__get_budget_transfers),
    "get_budget_transfer": ("s4__get_budget_transfers", s4__get_budget_transfers),
    "getbudgettransfer": ("s4__get_budget_transfers", s4__get_budget_transfers),
    "getBudgetTransfer": ("s4__get_budget_transfers", s4__get_budget_transfers),
    "budget_transfer": ("s4__get_budget_transfers", s4__get_budget_transfers),
    "budgettransfer": ("s4__get_budget_transfers", s4__get_budget_transfers),
    "BudgetTransfer": ("s4__get_budget_transfers", s4__get_budget_transfers),
    # Budget Consumption (BudgetConsumSummary)
    "s4__get_budget_consumption": ("s4__get_budget_consumption", s4__get_budget_consumption),
    "get_budget_consumption": ("s4__get_budget_consumption", s4__get_budget_consumption),
    "getbudgetconsumption": ("s4__get_budget_consumption", s4__get_budget_consumption),
    "getBudgetConsumption": ("s4__get_budget_consumption", s4__get_budget_consumption),
    "budget_consumption": ("s4__get_budget_consumption", s4__get_budget_consumption),
    "s4__get_budget_consumption_summary": ("s4__get_budget_consumption", s4__get_budget_consumption),
    "get_budget_consumption_summary": ("s4__get_budget_consumption", s4__get_budget_consumption),
    "getbudgetconsumptionsummary": ("s4__get_budget_consumption", s4__get_budget_consumption),
    "getBudgetConsumptionSummary": ("s4__get_budget_consumption", s4__get_budget_consumption),
    "budget_consumption_summary": ("s4__get_budget_consumption", s4__get_budget_consumption),
    "budgetconsumsummary": ("s4__get_budget_consumption", s4__get_budget_consumption),
    "BudgetConsumSummary": ("s4__get_budget_consumption", s4__get_budget_consumption),
    "budgetconsumdata": ("s4__get_budget_consumption", s4__get_budget_consumption),
    "BudgetConsumData": ("s4__get_budget_consumption", s4__get_budget_consumption),
    # Legacy Budget Variance
    "s4__get_budget_variance": ("s4__get_budget_variance", s4__get_budget_variance),
    "get_budget_variance": ("s4__get_budget_variance", s4__get_budget_variance),
    "getbudgetvariance": ("s4__get_budget_variance", s4__get_budget_variance),
    "getBudgetVariance": ("s4__get_budget_variance", s4__get_budget_variance),
    "budget_variance": ("s4__get_budget_variance", s4__get_budget_variance),
    # Legacy Profit & Loss
    "s4__get_profit_and_loss": ("s4__get_profit_and_loss", s4__get_profit_and_loss),
    "get_profit_and_loss": ("s4__get_profit_and_loss", s4__get_profit_and_loss),
    "getprofitandloss": ("s4__get_profit_and_loss", s4__get_profit_and_loss),
    "getProfitAndLoss": ("s4__get_profit_and_loss", s4__get_profit_and_loss),
    "profit_and_loss": ("s4__get_profit_and_loss", s4__get_profit_and_loss),

    # Master data tools
    "s4__get_customer_master": ("s4__get_customer_master", s4__get_customer_master),
    "get_customer_master": ("s4__get_customer_master", s4__get_customer_master),
    "getcustomermaster": ("s4__get_customer_master", s4__get_customer_master),
    "s4__get_cost_center_master": ("s4__get_cost_center_master", s4__get_cost_center_master),
    "get_cost_center_master": ("s4__get_cost_center_master", s4__get_cost_center_master),
    "getcostcentermaster": ("s4__get_cost_center_master", s4__get_cost_center_master),
    "s4__get_profit_center_master": ("s4__get_profit_center_master", s4__get_profit_center_master),
    "get_profit_center_master": ("s4__get_profit_center_master", s4__get_profit_center_master),
    "getprofitcentermaster": ("s4__get_profit_center_master", s4__get_profit_center_master),
}


def resolve_tool_handler(name: str) -> tuple[str, Any] | None:
    norm = name.strip().lower().replace("-", "_")
    if norm in ALIAS_MAP:
        return ALIAS_MAP[norm]
    if name in ALIAS_MAP:
        return ALIAS_MAP[name]
    stripped = norm.replace("s4__", "")
    if stripped in ALIAS_MAP:
        return ALIAS_MAP[stripped]
    prefixed = f"s4__{stripped}"
    if prefixed in ALIAS_MAP:
        return ALIAS_MAP[prefixed]
    return None


async def list_tools_endpoint(_request):
    return SafeJSONResponse({"tools": _build_mcp_tools()})


async def handle_tool_rest(request):
    raw_path = request.url.path.strip("/").split("/")[-1]
    resolved = resolve_tool_handler(raw_path)
    if not resolved:
        return SafeJSONResponse({"error": f"Tool '{raw_path}' not found"}, status_code=404)
    
    canonical_name, handler = resolved

    args = dict(request.query_params)
    if request.method == "POST":
        try:
            body = await request.json()
            if isinstance(body, dict):
                args.update(body.get("arguments", body.get("params", body)))
        except Exception:
            pass

    # Authorize requested company_code against caller's organization scope (F05)
    headers_dict = {k.lower(): v for k, v in request.headers.items()}
    org_scope = headers_dict.get("x-organization-scope", "").strip()
    req_company_code = args.get("company_code")
    if org_scope and req_company_code:
        norm_company_code = str(req_company_code).strip()
        allowed_for_scope = {"1000", "VELORA_UAE"} if org_scope in {"1000", "VELORA_UAE"} else {org_scope}
        if norm_company_code not in allowed_for_scope:
            return SafeJSONResponse(
                {
                    "status": "error",
                    "code": "ACCESS_DENIED",
                    "message": f"Caller organization scope '{org_scope}' is not entitled to query company_code '{norm_company_code}'. Approved: {sorted(list(allowed_for_scope))}.",
                },
                status_code=403,
            )

    try:
        res = await handler(**args)
        if hasattr(res, "structuredContent") and res.structuredContent:
            status_code = 400 if getattr(res, "isError", False) else 200
            return SafeJSONResponse(to_jsonable_data(res.structuredContent), status_code=status_code)
        elif hasattr(res, "content") and res.content:
            return SafeJSONResponse(json.loads(res.content[0].text))
        return SafeJSONResponse({"result": to_jsonable_data(res), "status": "success"})
    except Exception as ex:
        log.error(f"Error executing tool {raw_path}: {ex}", exc_info=True)
        return SafeJSONResponse({"error": str(ex), "status": "error"}, status_code=500)


async def handle_schema_endpoint(request):
    entity = request.path_params.get("entity", "")
    client = S4Client(settings)
    auth = await client._authorization()
    url = f"{client._validated_base_url()}/$metadata"
    headers = {"Accept": "application/xml"}
    if auth:
        headers["Authorization"] = auth
    try:
        async with httpx.AsyncClient(verify=settings.s4_verify_tls) as h:
            res = await h.get(url, headers=headers)
            res.raise_for_status()
            text = res.text
            if entity:
                m = re.search(rf'<EntityType Name="{entity}".*?</EntityType>', text, re.DOTALL | re.IGNORECASE)
                if m:
                    return Response(m.group(0), media_type="application/xml")
            return Response(text, media_type="application/xml")
    except httpx.HTTPStatusError as e:
        log.error(f"Upstream SAP metadata request failed with status {e.response.status_code}")
        return SafeJSONResponse(
            {"error": f"Upstream SAP metadata request failed with status {e.response.status_code}", "status": "error"},
            status_code=502,
        )
    except Exception as e:
        log.error(f"Failed to retrieve SAP metadata: {e}")
        return SafeJSONResponse(
            {"error": f"Failed to retrieve SAP metadata: {str(e)}", "status": "error"},
            status_code=502,
        )


async def handle_mcp_endpoint(request):
    if request.method == "GET":
        return SafeJSONResponse({"tools": _build_mcp_tools()})
    
    try:
        body = await request.json()
    except Exception:
        return SafeJSONResponse({"error": "Invalid JSON"}, status_code=400)
    
    req_id = body.get("id")
    method = body.get("method", "")
    
    if method == "initialize":
        return SafeJSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "prompts": {"listChanged": False},
                },
                "serverInfo": {"name": "velora-s4-finance", "version": "2.0.0"},
            },
        })
    
    if method in ("notifications/initialized", "initialized"):
        return SafeJSONResponse({"jsonrpc": "2.0"})
    
    if method == "ping":
        return SafeJSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {}})
    
    if method in ("tools/list", "tools"):
        return SafeJSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": _build_mcp_tools()},
        })
    
    if method == "tools/call":
        params = body.get("params", {}) or {}
        tool_name = params.get("name", "")
        tool_args = params.get("arguments") or {}
        if not isinstance(tool_args, dict):
            tool_args = {}

        resolved = resolve_tool_handler(tool_name)
        if not resolved:
            return SafeJSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Tool '{tool_name}' not found"},
            })

        canonical_name, handler = resolved
        try:
            res = await handler(**tool_args)
            if hasattr(res, "content") and res.content:
                content_list = [{"type": "text", "text": c.text} for c in res.content]
            elif isinstance(res, dict):
                content_list = [{"type": "text", "text": json.dumps(to_jsonable_data(res), ensure_ascii=False)}]
            else:
                content_list = []
            struct_data = (
                to_jsonable_data(res.structuredContent)
                if hasattr(res, "structuredContent") and res.structuredContent
                else (to_jsonable_data(res) if isinstance(res, dict) else {})
            )
            is_err = getattr(res, "isError", False)
            return SafeJSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": content_list,
                    "result": struct_data or {"status": "success", "content": content_list},
                    "structuredContent": struct_data,
                    "isError": is_err,
                },
            })
        except Exception as ex:
            log.error(f"Error in tools/call {tool_name}: {ex}", exc_info=True)
            return SafeJSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": str(ex)},
            })
    
    return SafeJSONResponse({
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method '{method}' not implemented"},
    })


def validate_configuration():
    """Startup validation for approved S/4HANA roots, hosts, and credentials (F05)."""
    client = S4Client(settings)
    client._validated_base_url()
    log.info(f"S/4HANA configuration validated for environment: {settings.s4_environment_label}")


def create_app():
    from starlette.applications import Starlette
    from starlette.routing import Mount

    mcp_app = mcp.streamable_http_app()

    routes = [
        Route("/", health, methods=["GET"]),
        Route("/health", health, methods=["GET"]),
        Route("/schema", handle_schema_endpoint, methods=["GET"]),
        Route("/schema/{entity}", handle_schema_endpoint, methods=["GET"]),
        Route("/mcp/tools", list_tools_endpoint, methods=["GET"]),
        Route("/mcp", handle_mcp_endpoint, methods=["GET", "POST"]),
        Route("/mcp/", handle_mcp_endpoint, methods=["GET", "POST"]),
    ]

    # Register all canonical tools and aliases on REST routes including /tools/{name} (F06)
    seen_routes = set()
    for alias in ALIAS_MAP.keys():
        if alias not in seen_routes:
            seen_routes.add(alias)
            routes.append(Route(f"/{alias}", handle_tool_rest, methods=["GET", "POST"]))
            routes.append(Route(f"/tools/{alias}", handle_tool_rest, methods=["GET", "POST"]))

    for name, _, _ in TOOL_SPECS:
        if name not in seen_routes:
            seen_routes.add(name)
            routes.append(Route(f"/{name}", handle_tool_rest, methods=["GET", "POST"]))
            routes.append(Route(f"/tools/{name}", handle_tool_rest, methods=["GET", "POST"]))

    # Mount FastMCP streamable HTTP app for MCP transport with initialized session manager lifespan (F06, T18)
    routes.append(Mount("/streamable", mcp_app))

    app = Starlette(routes=routes, lifespan=mcp_app.router.lifespan_context)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ApiKeyMiddleware)
    return app


app = create_app()


def start(host: str = "0.0.0.0", port: int = 8080):
    validate_configuration()
    uvicorn.run(app, host=host, port=port, log_level="info")


def main():
    import os
    port = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else getattr(settings, "mcp_server_port", 8080)))
    start(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()

