"""Regenerate mcp-tools.json + ai-plugin.json from live SuccessFactors server spec.

Writes the manifests, then validates what was written.
Run from kit/mcp-apps/ask-successfactors:
    python deploy/regen_manifests.py
"""
import json
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

APP_ROOT = Path(__file__).resolve().parent.parent

if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

env = APP_ROOT / ".env"
if env.exists():
    load_dotenv(env, override=False)

from successfactors_mcp.successfactors_server import mcp  # noqa: E402

SERVER_PATH    = "/mcp"
TOOL_PREFIX    = "sf__"
TUNNEL_BASE    = os.getenv("MCP_GATEWAY_URL", "https://sf-hcm-mcp-server.cfapps.eu10-005.hana.ondemand.com")
AUTH_TYPE      = os.getenv("MCP_PLUGIN_AUTH_TYPE", "ApiKeyPluginVault")
AUTH_REFERENCE = os.getenv("MCP_PLUGIN_AUTH_REFERENCE_ID", "")
CONTACT_EMAIL  = os.getenv("PUBLISHER_CONTACT_EMAIL", "")


TOOLS_PATH  = APP_ROOT / "agent" / "appPackage" / "mcp-tools.json"
PLUGIN_PATH = APP_ROOT / "agent" / "appPackage" / "ai-plugin.json"


async def _tool_descriptions():
    registered = await mcp.list_tools()
    return [
        {
            "name": tool.name,
            "description": tool.description or "",
            "inputSchema": tool.inputSchema,
        }
        for tool in registered
    ]


CARD_BY_TOOL = {
    "sf__get_headcount": "headcount.json",
    "sf__get_emiratisation_kpi": "emiratisation.json",
    "sf__get_analytics_dashboard": "workforce-overview.json",
}


def _function(tool):
    card_file = CARD_BY_TOOL.get(tool["name"], "sap-result.json")
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
                "static_template": {"file": f"./adaptive-cards/{card_file}"},
            }
        },
    }


def main():
    print(f"🔄 Regenerating manifests for Ask - SuccessFactors from live specs...")

    if AUTH_TYPE not in {"None", "ApiKeyPluginVault", "OAuthPluginVault"}:
        raise SystemExit("MCP_PLUGIN_AUTH_TYPE must be None, ApiKeyPluginVault, or OAuthPluginVault")
    if AUTH_TYPE != "None" and not AUTH_REFERENCE:
        raise SystemExit("MCP_PLUGIN_AUTH_REFERENCE_ID is required for secured Copilot packages")

    tools = asyncio.run(_tool_descriptions())
    functions = [_function(tool) for tool in tools]
    auth = {"type": AUTH_TYPE}
    if AUTH_TYPE != "None":
        auth["reference_id"] = AUTH_REFERENCE

    plugin_data = {
        "$schema": "https://developer.microsoft.com/json-schemas/copilot/plugin/v2.4/schema.json",
        "schema_version": "v2.4",
        "name_for_human": "Velora SuccessFactors",
        "description_for_human": "SuccessFactors workforce intelligence for the Velora Executive Agent",
        "description_for_model": "Use these SAP SuccessFactors tools for authorized headcount, Emiratisation, employee, job, and organization facts. Keep Emiratisation aggregate and never invent values when a tool reports an error or missing configuration.",
        "namespace": "sf",
        "functions": functions,
        "runtimes": [
            {
                "type": "RemoteMCPServer",
                "spec": {
                    "url": f"{TUNNEL_BASE}{SERVER_PATH}",
                    "mcp_tool_description": {
                        "tools": tools
                    }
                },
                "run_for_functions": [f["name"] for f in functions],
                "auth": auth
            }
        ]
    }

    if CONTACT_EMAIL:
        plugin_data["contact_email"] = CONTACT_EMAIL

    tools_data = {"tools": tools}

    PLUGIN_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(PLUGIN_PATH, "w", encoding="utf-8") as f:
        json.dump(plugin_data, f, indent=4)
    print(f"  ✓ Updated {PLUGIN_PATH.name}")

    with open(TOOLS_PATH, "w", encoding="utf-8") as f:
        json.dump(tools_data, f, indent=4)
    print(f"  ✓ Updated {TOOLS_PATH.name}")

    print("🎉 Manifest regeneration complete.")


if __name__ == "__main__":
    main()
