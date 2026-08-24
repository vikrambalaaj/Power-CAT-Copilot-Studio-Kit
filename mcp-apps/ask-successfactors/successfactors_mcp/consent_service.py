"""Velora Confidentiality Consent Service.

Manages legally approved confidentiality notices, first-use consent gating,
blocking Adaptive Cards, and consent audit logging in `cre2f_veloraagentauditlog`.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

from .dataverse_audit import (
    DataverseAuditRecord,
    RECORD_TYPE_CONSENT,
    get_dataverse_client,
)
from shared_mcp.logger import get_logger

log = get_logger("consent_service")

CURRENT_NOTICE_VERSION = "2026.1"
NOTICE_URL = os.getenv("VELORA_CONFIDENTIALITY_NOTICE_URL", "https://compliance.velora.ae/governance/data-confidentiality-notice-v1.html")

CONFIDENTIALITY_NOTICE_TITLE = "🔒 Velora Enterprise Confidentiality & Acceptable Use Consent"
CONFIDENTIALITY_NOTICE_SUMMARY = (
    "This AI Assistant provides access to Velora proprietary business metrics and authorized SAP SuccessFactors employee information. "
    "By proceeding, you acknowledge and agree that:\n"
    "• **Confidentiality:** All accessed workforce data is strictly Velora Confidential.\n"
    "• **Authorized Use:** Data may only be used for legitimate, authorized business purposes within your role.\n"
    "• **Prohibition on Sharing:** Unauthorized copying, exporting, or external dissemination is strictly prohibited.\n"
    "• **Audit & Memory:** In accordance with UAE Federal Decree-Law No. 45/2021 on Personal Data Protection, all conversation turns, queries, and policy decisions are logged, and a 30-day personalized memory snapshot is maintained in Microsoft Dataverse for session continuity."
)


def build_consent_adaptive_card(notice_version: str = CURRENT_NOTICE_VERSION) -> Dict[str, Any]:
    """Generate a blocking Adaptive Card v1.5 requiring explicit checkbox selection to proceed."""
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {
                "type": "TextBlock",
                "text": "🛡️ Velora Confidentiality & Acceptable Use Gate",
                "weight": "Bolder",
                "size": "Medium",
                "color": "Accent",
            },
            {
                "type": "TextBlock",
                "text": f"Notice Version: {notice_version} · Effective: January 2026",
                "size": "Small",
                "isSubtle": True,
                "spacing": "None",
            },
            {
                "type": "TextBlock",
                "text": CONFIDENTIALITY_NOTICE_SUMMARY,
                "wrap": True,
                "spacing": "Medium",
            },
            {
                "type": "Input.Toggle",
                "id": "consent_agreement",
                "title": "I understand and agree to the Velora Data Confidentiality & Acceptable Use Policy.",
                "value": "false",
                "isRequired": True,
                "errorMessage": "You must select the agreement checkbox before continuing.",
                "spacing": "Medium",
            },
            {
                "type": "TextBlock",
                "text": f"[Review Complete Velora Data Governance & Privacy Policy]({NOTICE_URL})",
                "size": "Small",
                "isSubtle": True,
                "spacing": "Small",
            },
        ],
        "actions": [
            {
                "type": "Action.Submit",
                "title": "Agree & Continue",
                "style": "positive",
                "data": {
                    "action": "submit_consent",
                    "consent_version": notice_version,
                    "consent_decision": "ACCEPTED",
                },
            },
            {
                "type": "Action.Submit",
                "title": "Decline",
                "style": "destructive",
                "data": {
                    "action": "submit_consent",
                    "consent_version": notice_version,
                    "consent_decision": "DECLINED",
                },
            },
        ],
    }


class ConsentService:
    """Evaluates and records user confidentiality consent."""

    def __init__(self, dataverse_client=None):
        self.client = dataverse_client or get_dataverse_client()

    async def verify_user_consent(
        self,
        user_object_id: str,
        user_email: str,
        notice_version: str = CURRENT_NOTICE_VERSION,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Check if the user has an active, valid consent event in Dataverse."""
        if not user_object_id and not user_email:
            # Anonymous context requires consent gate
            return False, build_consent_adaptive_card(notice_version)

        consent_record = await self.client.query_user_consent(
            user_object_id=user_object_id,
            user_email=user_email,
            notice_version=notice_version,
        )

        if consent_record:
            log.info("user_consent_verified", user_email=user_email, version=notice_version)
            return True, None

        log.info("user_consent_required", user_email=user_email, version=notice_version)
        return False, build_consent_adaptive_card(notice_version)

    async def record_user_consent(
        self,
        user_object_id: str,
        user_email: str,
        accepted: bool,
        notice_version: str = CURRENT_NOTICE_VERSION,
        channel: str = "copilot_studio",
        correlation_id: str = "",
    ) -> Dict[str, Any]:
        """Record the user's consent decision in `cre2f_veloraagentauditlog`."""
        status = "ACCEPTED" if accepted else "DECLINED"
        record = DataverseAuditRecord(
            record_type=RECORD_TYPE_CONSENT,
            user_object_id=user_object_id,
            user_email=user_email,
            consent_version=notice_version,
            consent_status=status,
            channel=channel,
            correlation_id=correlation_id,
            message_summary=f"User {status.lower()} confidentiality consent notice v{notice_version}",
            content_classification="INTERNAL_AUDIT",
        )
        res = await self.client.create_audit_record(record)
        return {
            "status": "RECORDED",
            "consent_status": status,
            "consent_version": notice_version,
            "audit_id": res.get("id"),
        }


_global_consent_service = ConsentService()


def get_consent_service() -> ConsentService:
    return _global_consent_service
