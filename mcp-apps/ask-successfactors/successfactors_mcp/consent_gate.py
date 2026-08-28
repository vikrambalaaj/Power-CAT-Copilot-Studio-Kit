"""Server-side confidentiality consent enforcement for the Velora SuccessFactors MCP.

The declarative agent is instructed to open every session with the consent gate,
but instructions are advisory: a model that skips the check must still not be able
to disclose employee-level records. This module wraps the affected tool specs so
the gate is enforced in the server and the blocking Adaptive Card is returned in
place of the requested data.

Scope note: enforcement is limited to tools that receive the caller identity
(`user_object_id` / `user_email`), because consent is stored per user. Aggregate
tools such as `sf__get_headcount` carry no identity, so gating them here would
block them permanently instead of prompting; session-start consent for those is
handled by the mandatory `sf__get_session_greeting` call in the agent
instructions.
"""
from __future__ import annotations

import functools
from typing import Any, Dict, List

from .successfactors_settings import get_settings
from shared_mcp.logger import get_logger

log = get_logger("consent_gate")

# Employee-level disclosure tools. Every entry must accept `user_object_id` and
# `user_email`, otherwise consent can never be resolved for it.
CONSENT_REQUIRED_TOOLS = {
    "sf__get_workforce_drilldown",  # individual employee records
    "sf__recall_user_memory",       # the user's own 30-day conversation partition
}


def require_consent(name: str):
    """Decorator gating one tool handler behind an accepted confidentiality notice."""

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            # Imported lazily so tool wiring never depends on Dataverse import order.
            from .consent_service import CURRENT_NOTICE_VERSION, get_consent_service
            from .successfactors_tools import _json_response

            user_object_id = str(kwargs.get("user_object_id") or "")
            user_email = str(kwargs.get("user_email") or "")

            svc = get_consent_service()
            is_consented, card = await svc.verify_user_consent(
                user_object_id=user_object_id,
                user_email=user_email,
            )
            if is_consented:
                return await fn(*args, **kwargs)

            log.info("consent_gate_blocked", tool=name, user_email=user_email)
            return _json_response({
                "type": "ConsentRequired",
                "is_consented": False,
                "blocked_tool": name,
                "consent_version": CURRENT_NOTICE_VERSION,
                "adaptiveCard": card,
                "cardTitle": "Consent required",
                "cardSubtitle": "Velora Enterprise Confidentiality & Acceptable Use",
                "fallback_text": (
                    "Please review and accept the Velora Enterprise Confidentiality & "
                    "Acceptable Use Consent to proceed."
                ),
                "message": (
                    "Confidentiality consent is required before Velora employee records "
                    "can be disclosed. Present the consent card and record the decision "
                    "with sf__check_and_record_consent."
                ),
            })

        return wrapper

    return decorator


def wrap_specs_consent(specs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Gate the employee-level disclosure tools behind the consent check."""
    if not get_settings().enforce_consent_gate:
        return specs
    wrapped = []
    for spec in specs:
        name = spec["name"]
        if name not in CONSENT_REQUIRED_TOOLS:
            wrapped.append(spec)
            continue
        handler = spec.get("handler") or spec["func"]
        wrapped.append({**spec, "handler": require_consent(name)(handler)})
    return wrapped
