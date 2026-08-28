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
    """Build a clean greeting card that simply greets the user and says hi without listing capabilities."""
    salutation = get_time_aware_salutation(user_timezone)
    name = (user_display_name or "").split()[0] if user_display_name else ""
    
    if name:
        greeting_text = f"Hi, {name}! {salutation}."
    else:
        greeting_text = f"Hi! {salutation}."

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {
                "type": "TextBlock",
                "text": greeting_text,
                "weight": "Bolder",
                "size": "Medium",
                "color": "Accent",
                "wrap": True,
            }
        ],
    }


def build_greeting_card(
    user_display_name: Optional[str] = None,
    user_timezone: Optional[str] = None,
) -> Dict[str, Any]:
    """Alias for build_capabilities_card returning a concise, friendly greeting card."""
    return build_capabilities_card(user_display_name=user_display_name, user_timezone=user_timezone)


class GreetingService:
    """Manages session greeting generation and asynchronous background pre-warming."""

    def __init__(self, memory_service=None, consent_service=None):
        self._memory_service = memory_service
        self._consent_service = consent_service

    def _get_memory_service(self):
        if self._memory_service is None:
            from .memory_service import get_memory_service
            self._memory_service = get_memory_service()
        return self._memory_service

    def _get_consent_service(self):
        if self._consent_service is None:
            from .consent_service import get_consent_service
            self._consent_service = get_consent_service()
        return self._consent_service

    def set_memory_service(self, memory_service) -> None:
        self._memory_service = memory_service

    def set_consent_service(self, consent_service) -> None:
        self._consent_service = consent_service

    async def get_session_greeting(
        self,
        user_object_id: str,
        user_email: str,
        user_display_name: str = "",
        user_timezone: str = FALLBACK_TIMEZONE,
    ) -> Dict[str, Any]:
        """Generate greeting card immediately and spawn background memory pre-load."""
        # 1. Check user confidentiality consent gate
        consent_svc = self._get_consent_service()
        is_consented, consent_card = await consent_svc.verify_user_consent(
            user_object_id=user_object_id,
            user_email=user_email,
        )

        if not is_consented and consent_card:
            return {
                "type": "ConsentRequired",
                "is_consented": False,
                "salutation": get_time_aware_salutation(user_timezone),
                "user_display_name": user_display_name,
                "fallback_text": "Please review and accept the Velora Enterprise Confidentiality & Acceptable Use Consent to proceed.",
                "adaptiveCard": consent_card,
            }

        # 2. Spawn non-blocking background 30-day memory load
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

        # 3. Build clean greeting immediately
        card = build_capabilities_card(
            user_display_name=user_display_name,
            user_timezone=user_timezone,
        )
        salutation = get_time_aware_salutation(user_timezone)
        name = (user_display_name or "").split()[0] if user_display_name else ""
        fallback = f"Hi, {name}! {salutation}." if name else f"Hi! {salutation}."

        return {
            "type": "SessionGreeting",
            "is_consented": True,
            "salutation": salutation,
            "user_display_name": user_display_name,
            "fallback_text": fallback,
            "adaptiveCard": card,
        }


_global_greeting_service = GreetingService()


def get_greeting_service() -> GreetingService:
    return _global_greeting_service
