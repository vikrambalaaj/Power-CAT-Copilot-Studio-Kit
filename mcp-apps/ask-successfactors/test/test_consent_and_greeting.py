"""Unit and integration tests for Confidentiality Consent & Session Greeting Services."""
import asyncio
import unittest
from datetime import datetime, timezone

from successfactors_mcp.consent_service import ConsentService, CURRENT_NOTICE_VERSION
from successfactors_mcp.greeting_service import (
    GreetingService,
    get_time_aware_salutation,
    build_capabilities_card,
)
from successfactors_mcp.dataverse_audit import DataverseClient
from successfactors_mcp.memory_service import MemoryService


class ConsentAndGreetingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dv_client = DataverseClient()
        self.dv_client.clear_all_for_testing()
        self.consent_service = ConsentService(dataverse_client=self.dv_client)
        self.memory_service = MemoryService(dataverse_client=self.dv_client)
        self.greeting_service = GreetingService(
            memory_service=self.memory_service,
            consent_service=self.consent_service,
        )

    async def test_first_use_consent_gate_blocks_until_accepted(self):
        # 1. First-time check -> should return False and blocking card
        is_consented, card = await self.consent_service.verify_user_consent(
            user_object_id="entra-u10",
            user_email="newuser@velora.ae",
        )
        self.assertFalse(is_consented)
        self.assertIsNotNone(card)
        self.assertEqual(card["type"], "AdaptiveCard")
        self.assertIn("Velora Confidentiality", card["body"][0]["text"])

        # 2. User agrees -> record consent
        res = await self.consent_service.record_user_consent(
            user_object_id="entra-u10",
            user_email="newuser@velora.ae",
            accepted=True,
        )
        self.assertEqual(res["status"], "RECORDED")
        self.assertEqual(res["consent_status"], "ACCEPTED")

        # 3. Subsequent check -> should return True and no blocking card
        is_consented_now, card_now = await self.consent_service.verify_user_consent(
            user_object_id="entra-u10",
            user_email="newuser@velora.ae",
        )
        self.assertTrue(is_consented_now)
        self.assertIsNone(card_now)

    async def test_consent_version_upgrade_reprompts_user(self):
        # Accept version 2026.1
        await self.consent_service.record_user_consent(
            user_object_id="entra-u11",
            user_email="user11@velora.ae",
            accepted=True,
            notice_version="2026.1",
        )

        # Check for upgraded version 2026.2
        is_consented, card = await self.consent_service.verify_user_consent(
            user_object_id="entra-u11",
            user_email="user11@velora.ae",
            notice_version="2026.2",
        )
        self.assertFalse(is_consented)
        self.assertIsNotNone(card)

    def test_time_aware_greeting_salutation(self):
        # Salutation function respects fallback timezone
        salutation = get_time_aware_salutation("Asia/Dubai")
        self.assertIn(salutation, ["Good morning", "Good afternoon", "Good evening", "Welcome"])

        # Clean greeting card simply greets and says hi without capability prompt clutter
        card = build_capabilities_card(user_display_name="Vikram Bala", user_timezone="Asia/Dubai")
        self.assertEqual(card["type"], "AdaptiveCard")
        self.assertIn("Vikram", card["body"][0]["text"])
        self.assertIn("Hi", card["body"][0]["text"])

    async def test_session_greeting_triggers_memory_prewarm(self):
        # 1. Unconsented user receives consent gate on greeting
        greeting_gate = await self.greeting_service.get_session_greeting(
            user_object_id="entra-u12",
            user_email="user12@velora.ae",
            user_display_name="Sarah Al Zaabi",
        )
        self.assertEqual(greeting_gate["type"], "ConsentRequired")
        self.assertFalse(greeting_gate["is_consented"])
        self.assertIsNotNone(greeting_gate.get("adaptiveCard"))

        # 2. After user consents, greeting returns clean session greeting
        await self.consent_service.record_user_consent(
            user_object_id="entra-u12",
            user_email="user12@velora.ae",
            accepted=True,
        )
        greeting_res = await self.greeting_service.get_session_greeting(
            user_object_id="entra-u12",
            user_email="user12@velora.ae",
            user_display_name="Sarah Al Zaabi",
        )
        self.assertEqual(greeting_res["type"], "SessionGreeting")
        self.assertTrue(greeting_res["is_consented"])
        self.assertIn("Sarah", greeting_res["fallback_text"])
        self.assertIsNotNone(greeting_res.get("adaptiveCard"))


if __name__ == "__main__":
    unittest.main()
