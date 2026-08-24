from typing import Any, Dict, List, Optional
from sac_mcp.client import sac_client
from sac_mcp.adaptive_cards import build_sac_kpi_card, build_sac_story_card


async def get_sac_kpis(domain: str = "FINANCE") -> Dict[str, Any]:
    """Retrieve executive financial, operational, and strategic KPIs from SAP Analytics Cloud (SAC)."""
    raw = await sac_client.get_executive_kpis(domain=domain)
    card = build_sac_kpi_card(raw)
    return {
        "structuredContent": raw,
        "adaptiveCard": card,
    }


async def get_sac_story_analytics(story_id: str = "VELORA_CORP_PERF_2026") -> Dict[str, Any]:
    """Fetch high-level business intelligence story insights, charts, and variances from SAP Analytics Cloud."""
    raw = await sac_client.get_story_analytics(story_id=story_id)
    card = build_sac_story_card(raw)
    return {
        "structuredContent": raw,
        "adaptiveCard": card,
    }


async def get_sac_model_data(model_id: str, measures: Optional[List[str]] = None) -> Dict[str, Any]:
    """Query data export model structures and aggregated metric values directly from SAP Analytics Cloud models."""
    raw = await sac_client.get_model_data(model_id=model_id, measures=measures)
    return {
        "structuredContent": raw,
    }


ALL_TOOLS = [
    {
        "name": "get_sac_kpis",
        "description": "Retrieve executive financial, operational, and strategic KPIs from SAP Analytics Cloud (SAC).",
        "parameters": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain of interest (e.g. FINANCE, OPERATIONS, WORKFORCE, STRATEGY). Default is FINANCE.",
                    "default": "FINANCE",
                }
            },
        },
        "handler": get_sac_kpis,
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
                    "default": "VELORA_CORP_PERF_2026",
                }
            },
        },
        "handler": get_sac_story_analytics,
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
        "handler": get_sac_model_data,
    },
]
