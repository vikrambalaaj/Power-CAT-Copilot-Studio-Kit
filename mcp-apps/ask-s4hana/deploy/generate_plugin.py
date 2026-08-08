"""Generate the S/4HANA Copilot Remote MCP plugin from live FastMCP schemas."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
REPO_APP = APP_ROOT.parent / "ask-successfactors" / "agent" / "appPackage"
sys.path.insert(0, str(APP_ROOT))

from s4hana_mcp.server import mcp  # noqa: E402


async def tool_descriptions():
    return [
        {"name": tool.name, "description": tool.description or "", "inputSchema": tool.inputSchema}
        for tool in await mcp.list_tools()
    ]


CARD_BY_TOOL = {
    "s4__get_receivables_aging": "receivables-aging.json",
    "s4__get_payables_aging": "payables-aging.json",
    "s4__get_profit_and_loss": "profit-and-loss.json",
    "s4__get_budget_variance": "budget-variance.json",
}


def function_manifest(tool):
    return {
        "name": tool["name"],
        "description": tool["description"],
        "capabilities": {
            "response_semantics": {
                "data_path": "$",
                "properties": {
                    "title": "$.cardTitle",
                    "subtitle": "$.cardSubtitle",
                    "template_selector": "$.adaptiveCard",
                },
                "static_template": {"file": f"./adaptive-cards/{CARD_BY_TOOL[tool['name']]}"},
            }
        },
    }


def main() -> None:
    tools = asyncio.run(tool_descriptions())
    functions = [function_manifest(tool) for tool in tools]
    base_url = os.getenv(
        "S4_MCP_GATEWAY_URL",
        "https://s4-finance-mcp-server.cfapps.eu10-005.hana.ondemand.com",
    ).rstrip("/")
    auth_type = os.getenv("S4_PLUGIN_AUTH_TYPE", "ApiKeyPluginVault")
    reference = os.getenv("S4_PLUGIN_AUTH_REFERENCE_ID", "REPLACE_WITH_S4_PLUGIN_VAULT_REFERENCE_ID")
    if auth_type not in {"None", "ApiKeyPluginVault", "OAuthPluginVault"}:
        raise SystemExit("S4_PLUGIN_AUTH_TYPE is invalid")
    auth = {"type": auth_type}
    if auth_type != "None":
        auth["reference_id"] = reference
    plugin = {
        "$schema": "https://developer.microsoft.com/json-schemas/copilot/plugin/v2.4/schema.json",
        "schema_version": "v2.4",
        "name_for_human": "Velora S/4HANA Finance",
        "description_for_human": "S/4HANA finance intelligence for the Velora Executive Agent",
        "description_for_model": "Use these read-only SAP S/4HANA tools for receivables, payables, P&L, and budget variance. Preserve periods, currencies, sources, warnings, and authorization boundaries.",
        "namespace": "s4",
        "functions": functions,
        "runtimes": [{
            "type": "RemoteMCPServer",
            "spec": {"url": f"{base_url}/mcp", "mcp_tool_description": {"tools": tools}},
            "run_for_functions": [item["name"] for item in functions],
            "auth": auth,
        }],
    }
    REPO_APP.mkdir(parents=True, exist_ok=True)
    (REPO_APP / "s4hana-plugin.json").write_text(json.dumps(plugin, indent=4) + "\n", encoding="utf-8")
    (REPO_APP / "s4hana-mcp-tools.json").write_text(json.dumps({"tools": tools}, indent=4) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
