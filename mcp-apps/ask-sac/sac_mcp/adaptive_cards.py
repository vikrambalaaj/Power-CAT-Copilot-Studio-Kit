from typing import Any, Dict


def build_sac_kpi_card(kpi_data: Dict[str, Any]) -> Dict[str, Any]:
    facts = []
    for kpi in kpi_data.get("kpis", []):
        facts.append({"title": kpi.get("title", "Metric"), "value": f"{kpi.get('value')} (Target: {kpi.get('target')}) | Var: {kpi.get('variance')}"})

    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5",
        "body": [
            {
                "type": "Container",
                "style": "emphasis",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "📊 SAP Analytics Cloud (SAC) — Executive KPIs",
                        "weight": "Bolder",
                        "size": "Medium",
                        "color": "Accent",
                    },
                    {
                        "type": "TextBlock",
                        "text": f"Domain: {kpi_data.get('domain')} | As of: {kpi_data.get('as_of')}",
                        "isSubtle": True,
                        "spacing": "None",
                    },
                ],
            },
            {
                "type": "FactSet",
                "facts": facts,
            },
            {
                "type": "TextBlock",
                "text": kpi_data.get("executive_summary", ""),
                "wrap": True,
                "spacing": "Medium",
            },
        ],
    }


def build_sac_story_card(story_data: Dict[str, Any]) -> Dict[str, Any]:
    insights_items = []
    for page in story_data.get("pages", []):
        for insight in page.get("primary_insights", []):
            insights_items.append({"type": "TextBlock", "text": f"• {insight}", "wrap": True})

    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5",
        "body": [
            {
                "type": "TextBlock",
                "text": f"📈 {story_data.get('story_title', 'SAC Story Analytics')}",
                "weight": "Bolder",
                "size": "Medium",
            },
            {
                "type": "TextBlock",
                "text": f"Refreshed: {story_data.get('last_refreshed')} | Currency: {story_data.get('currency')}",
                "isSubtle": True,
            },
            {
                "type": "Container",
                "items": insights_items,
                "spacing": "Medium",
            },
        ],
    }
