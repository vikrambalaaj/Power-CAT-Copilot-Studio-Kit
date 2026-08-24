"""Velora HCM Agent Greeting & Capability Service.

Generates time-aware executive greetings, capability starter cards, and asynchronously
triggers the 30-day memory snapshot pre-load on session start.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from shared_mcp.logger import get_logger

log = get_logger("greeting_service")

FALLBACK_TIMEZONE = "Asia/Dubai"


def get_time_aware_salutation(user_timezone: Optional[str] = None) -> str:
    """Return time-appropriate salutation based on user timezone or Asia/Dubai."""
    tz_str = user_timezone or FALLBACK_TIMEZONE
    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        tz = ZoneInfo(FALLBACK_TIMEZONE)

    current_hour = datetime.now(tz).hour
    if 5 <= current_hour < 12:
        return "Good morning"
    elif 12 <= current_hour < 17:
        return "Good afternoon"
    elif 17 <= current_hour < 23:
        return "Good evening"
    else:
        return "Welcome"


def build_capabilities_card(
    user_display_name: Optional[str] = None,
    user_timezone: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a rich Adaptive Card v1.5 with personalized greeting and starter prompts."""
    salutation = get_time_aware_salutation(user_timezone)
    name = (user_display_name or "").split()[0] if user_display_name else "there"
    greeting_text = f"{salutation}, {name}! How can I help you today?"

    capabilities = [
        {"title": "👥 Workforce Headcount", "desc": "Current verified active headcount & department breakdowns"},
        {"title": "🔍 Group Drill-Down", "desc": "Who are the 15 employees in the Unassigned department?"},
        {"title": "🇦🇪 Emiratisation KPI", "desc": "Nationalization ratio, target compliance, and nationality aggregates"},
        {"title": "📈 Joiners & Attrition", "desc": "Period new-hires, departures, and annual attrition trends"},
        {"title": "💼 Executive Dashboard", "desc": "Comprehensive multi-KPI workforce health overview"},
        {"title": "🧠 30-Day Memory", "desc": "Recall previous discussion topics, decisions, and follow-up items"},
    ]

    body: List[Dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": greeting_text,
            "weight": "Bolder",
            "size": "Medium",
            "color": "Accent",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": "I am your Velora HCM AI Assistant, connected directly to SAP SuccessFactors and enterprise Dataverse governance.",
            "isSubtle": True,
            "wrap": True,
            "spacing": "Small",
        },
        {
            "type": "TextBlock",
            "text": "💡 **Quick Starters**",
            "weight": "Bolder",
            "size": "Small",
            "spacing": "Medium",
        },
    ]

    for item in capabilities:
        body.append({
            "type": "TextBlock",
            "text": f"• **{item['title']}**: {item['desc']}",
            "wrap": True,
            "spacing": "Small",
        })

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": body,
        "actions": [
            {
                "type": "Action.Submit",
                "title": "Headcount Overview",
                "data": {"query": "What is our current total headcount and department breakdown?"},
            },
            {
                "type": "Action.Submit",
                "title": "Unassigned Drill-Down",
                "data": {"query": "There are 15 employees in the Unassigned department. Who are they?"},
            },
            {
                "type": "Action.Submit",
                "title": "Emiratisation Ratio",
                "data": {"query": "Show me our Emiratisation KPI and nationality distribution"},
            },
        ],
    }


class GreetingService:
    """Manages session greeting generation and asynchronous background pre-warming."""

    def __init__(self, memory_service=None):
        self._memory_service = memory_service

    def _get_memory_service(self):
        if self._memory_service is None:
            from .memory_service import get_memory_service
            self._memory_service = get_memory_service()
        return self._memory_service

    def set_memory_service(self, memory_service) -> None:
        self._memory_service = memory_service

    async def get_session_greeting(
        self,
        user_object_id: str,
        user_email: str,
        user_display_name: str = "",
        user_timezone: str = FALLBACK_TIMEZONE,
    ) -> Dict[str, Any]:
        """Generate greeting card immediately and spawn background memory pre-load."""
        # 1. Spawn non-blocking background 30-day memory load
        mem_svc = self._get_memory_service()
        if mem_svc:
            try:
                asyncio.create_task(
                    mem_svc.prewarm_user_memory_snapshot(
                        user_object_id=user_object_id,
                        user_email=user_email,
                    )
                )
            except Exception as exc:
                log.debug("memory_prewarm_task_failed", error=str(exc))

        # 2. Build greeting immediately
        card = build_capabilities_card(
            user_display_name=user_display_name,
            user_timezone=user_timezone,
        )
        salutation = get_time_aware_salutation(user_timezone)
        name = (user_display_name or "").split()[0] if user_display_name else "there"
        fallback = f"{salutation}, {name}! How can I assist you with Velora workforce intelligence today?"

        return {
            "type": "SessionGreeting",
            "salutation": salutation,
            "user_display_name": user_display_name,
            "fallback_text": fallback,
            "adaptiveCard": card,
        }


_global_greeting_service = GreetingService()


def get_greeting_service() -> GreetingService:
    return _global_greeting_service
