import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
APP_PKG_DIR = BASE_DIR.parent / "ask-successfactors" / "agent" / "appPackage"

PLUGIN_AUTH_TYPE = os.getenv("MCP_PLUGIN_AUTH_TYPE", "None")
PLUGIN_AUTH_REF = os.getenv("SAC_PLUGIN_AUTH_REFERENCE_ID", "velora-sac-vault-ref")
GATEWAY_URL = os.getenv("SAC_GATEWAY_URL", "https://sac-analytics-mcp-server.cfapps.eu10-005.hana.ondemand.com")


def generate():
    tools_json = {
        "tools": [
            {
                "name": "get_sac_kpis",
                "description": "Retrieve executive financial, operational, and strategic KPIs from SAP Analytics Cloud (SAC).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "domain": {
                            "type": "string",
                            "description": "Domain of interest (e.g. FINANCE, OPERATIONS, WORKFORCE, STRATEGY). Default is FINANCE.",
                        }
                    },
                },
            },
            {
                "name": "get_sac_story_analytics",
                "description": "Fetch high-level business intelligence story insights, charts, and variances from SAP Analytics Cloud.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "story_id": {
                            "type": "string",
                            "description": "Identifier of the SAC Story (e.g. VELORA_CORP_PERF_2026).",
                        }
                    },
                },
            },
            {
                "name": "get_sac_model_data",
                "description": "Query data export model structures and aggregated metric values directly from SAP Analytics Cloud models.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "model_id": {
                            "type": "string",
                            "description": "Model ID in SAP Analytics Cloud.",
                        },
                        "measures": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of measure field names to query.",
                        },
                    },
                    "required": ["model_id"],
                },
            },
        ]
    }

    plugin_json = {
        "schema_version": "v2.1",
        "name_for_human": "SAP Analytics Cloud (SAC) Plugin",
        "name_for_model": "sapAnalyticsCloudPlugin",
        "description_for_human": "Delivers executive financial, KPI, and BI story insights from SAP Analytics Cloud.",
        "description_for_model": "Query enterprise KPIs, executive performance dashboards, and analytical models live from SAP Analytics Cloud (SAC).",
        "auth": {
            "type": PLUGIN_AUTH_TYPE,
            "reference_id": PLUGIN_AUTH_REF if PLUGIN_AUTH_TYPE != "None" else None,
        },
        "functions": [
            {
                "name": "get_sac_kpis",
                "description": "Retrieve executive financial, operational, and strategic KPIs from SAP Analytics Cloud (SAC).",
                "parameters": tools_json["tools"][0]["parameters"],
            },
            {
                "name": "get_sac_story_analytics",
                "description": "Fetch high-level business intelligence story insights, charts, and variances from SAP Analytics Cloud.",
                "parameters": tools_json["tools"][1]["parameters"],
            },
            {
                "name": "get_sac_model_data",
                "description": "Query data export model structures and aggregated metric values directly from SAP Analytics Cloud models.",
                "parameters": tools_json["tools"][2]["parameters"],
            },
        ],
        "runtimes": [
            {
                "type": "RemoteMcp",
                "auth": {
                    "type": PLUGIN_AUTH_TYPE,
                    "reference_id": PLUGIN_AUTH_REF if PLUGIN_AUTH_TYPE != "None" else None,
                },
                "spec": {
                    "url": f"{GATEWAY_URL}/mcp",
                },
                "run_for_functions": [
                    "get_sac_kpis",
                    "get_sac_story_analytics",
                    "get_sac_model_data",
                ],
            }
        ],
    }

    APP_PKG_DIR.mkdir(parents=True, exist_ok=True)
    with open(APP_PKG_DIR / "sac-mcp-tools.json", "w") as f:
        json.dump(tools_json, f, indent=4)

    with open(APP_PKG_DIR / "sac-plugin.json", "w") as f:
        json.dump(plugin_json, f, indent=4)

    print("Generated sac-mcp-tools.json and sac-plugin.json in appPackage.")


if __name__ == "__main__":
    generate()
