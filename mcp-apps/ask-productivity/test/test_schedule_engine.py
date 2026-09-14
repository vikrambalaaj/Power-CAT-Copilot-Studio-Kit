"""Unit and Acceptance Tests for Schedule Engine (W07 / Acceptance T07).

Validates:
1. Timezone-aware local schedule evaluation against UTC clocks (Asia/Dubai UTC+4).
2. Morning briefing window detection (07:00 GST / 03:00 UTC).
3. Pre-meeting lead time evaluation (e.g. T-15 min) with strictly excluded canceled meetings.
4. EOD schedule evaluation requiring explicit configuration (CONFIGURATION_REQUIRED).
5. Deterministic, collision-free run_key construction preventing duplicate runs across restarts.
6. Fail-closed handling of disabled and expired subscriptions.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from productivity_mcp.evidence_contracts import AutomationSubscription, SubscriptionKind
from productivity_mcp.schedule_engine import (
    calculate_local_occurrence,
    get_timezone_offset,
    is_subscription_due,
    parse_schedule_time,
)


class TestScheduleEngine(unittest.TestCase):
    def setUp(self):
        self.tz_dubai = get_timezone_offset("Asia/Dubai")

    def test_timezone_resolution(self):
        tz = get_timezone_offset("Asia/Dubai")
        # Asia/Dubai is UTC+4
        test_utc = datetime(2026, 9, 14, 3, 0, 0, tzinfo=timezone.utc)
        test_local = test_utc.astimezone(tz)
        self.assertEqual(test_local.hour, 7)
        self.assertEqual(test_local.minute, 0)

    def test_parse_schedule_time(self):
        self.assertEqual(parse_schedule_time("07:00"), (7, 0))
        self.assertEqual(parse_schedule_time("17:30"), (17, 30))
        self.assertEqual(parse_schedule_time("30 17 * * *"), (17, 30))
        self.assertIsNone(parse_schedule_time("invalid"))
        self.assertIsNone(parse_schedule_time(""))

    def test_morning_schedule_due_evaluation(self):
        sub = AutomationSubscription(
            subscriptionId="SUB-MORN-001",
            version="1.0.0",
            tenantId="velora-tenant",
            owner="user-1",
            mailbox="exec@velora.ae",
            sender="agent@velora.ae",
            recipients=["exec@velora.ae"],
            kind=SubscriptionKind.MORNING,
            timezone="Asia/Dubai",
            localSchedule="07:00",
            enabled=True,
            authorizedBy="user-1",
            authorizedAt="2026-09-01T00:00:00Z",
        )

        # 07:05 GST on 2026-09-14 (within 15 min tolerance)
        now_due = datetime(2026, 9, 14, 7, 5, 0, tzinfo=self.tz_dubai)
        is_due, run_key, ctx = is_subscription_due(sub, now=now_due, tolerance_minutes=15)

        self.assertTrue(is_due)
        self.assertIsNotNone(run_key)
        self.assertIn("velora-tenant:SUB-MORN-001:1.0.0", run_key)
        self.assertEqual(ctx["kind"], "MORNING")

        # 08:30 GST (outside tolerance)
        now_late = datetime(2026, 9, 14, 8, 30, 0, tzinfo=self.tz_dubai)
        is_due_late, run_key_late, ctx_late = is_subscription_due(sub, now=now_late, tolerance_minutes=15)
        self.assertFalse(is_due_late)
        self.assertIsNone(run_key_late)
        self.assertEqual(ctx_late["reason"], "NOT_IN_MORNING_WINDOW")

    def test_eod_schedule_requires_configuration(self):
        sub_missing_config = AutomationSubscription(
            subscriptionId="SUB-EOD-001",
            version="1.0.0",
            tenantId="velora-tenant",
            owner="user-1",
            mailbox="exec@velora.ae",
            sender="agent@velora.ae",
            recipients=["exec@velora.ae"],
            kind=SubscriptionKind.EOD,
            timezone="Asia/Dubai",
            localSchedule="",  # Missing local schedule!
            enabled=True,
            authorizedBy="user-1",
            authorizedAt="2026-09-01T00:00:00Z",
        )
        now_test = datetime(2026, 9, 14, 17, 30, 0, tzinfo=self.tz_dubai)
        is_due, run_key, ctx = is_subscription_due(sub_missing_config, now=now_test)
        self.assertFalse(is_due)
        self.assertEqual(ctx.get("reason"), "CONFIGURATION_REQUIRED")

        # Configured EOD at 17:30
        sub_configured = AutomationSubscription(
            subscriptionId="SUB-EOD-002",
            version="1.0.0",
            tenantId="velora-tenant",
            owner="user-1",
            mailbox="exec@velora.ae",
            sender="agent@velora.ae",
            recipients=["exec@velora.ae"],
            kind=SubscriptionKind.EOD,
            timezone="Asia/Dubai",
            localSchedule="17:30",
            enabled=True,
            authorizedBy="user-1",
            authorizedAt="2026-09-01T00:00:00Z",
        )
        now_eod_due = datetime(2026, 9, 14, 17, 35, 0, tzinfo=self.tz_dubai)
        is_due_eod, run_key_eod, ctx_eod = is_subscription_due(sub_configured, now=now_eod_due, tolerance_minutes=15)
        self.assertTrue(is_due_eod)
        self.assertIn("SUB-EOD-002:1.0.0", run_key_eod)

    def test_pre_meeting_lead_time_and_canceled_exclusion(self):
        sub_pre = AutomationSubscription(
            subscriptionId="SUB-PRE-001",
            version="1.0.0",
            tenantId="velora-tenant",
            owner="user-1",
            mailbox="exec@velora.ae",
            sender="agent@velora.ae",
            recipients=["exec@velora.ae"],
            kind=SubscriptionKind.PRE_MEETING,
            timezone="Asia/Dubai",
            localSchedule="",
            leadTimeMinutes=15,
            enabled=True,
            authorizedBy="user-1",
            authorizedAt="2026-09-01T00:00:00Z",
        )

        # Event A: Canceled event starting at 09:00 GST
        # Event B: Active event starting at 09:30 GST
        events = [
            {
                "id": "EVT-CANCELED-01",
                "subject": "Canceled Board Pre-check",
                "start": "2026-09-14T09:00:00+04:00",
                "isCancelled": True,
            },
            {
                "id": "EVT-ACTIVE-02",
                "subject": "Operations Alignment",
                "start": "2026-09-14T09:30:00+04:00",
                "isCancelled": False,
            }
        ]

        # Case 1: At 08:45 (T-15 of canceled event) -> Should NOT fire for canceled event
        now_845 = datetime(2026, 9, 14, 8, 46, 0, tzinfo=self.tz_dubai)
        is_due, run_key, ctx = is_subscription_due(sub_pre, now=now_845, eligible_events=events)
        # Event A is canceled, Event B is 44 mins away (not within 15 min tolerance)
        self.assertFalse(is_due)

        # Case 2: At 09:16 (T-14 before Event B at 09:30) -> Should fire for Event B
        now_916 = datetime(2026, 9, 14, 9, 16, 0, tzinfo=self.tz_dubai)
        is_due_b, run_key_b, ctx_b = is_subscription_due(sub_pre, now=now_916, eligible_events=events)
        self.assertTrue(is_due_b)
        self.assertIn("EVT-ACTIVE-02", run_key_b)
        self.assertEqual(ctx_b["eventId"], "EVT-ACTIVE-02")
        self.assertEqual(ctx_b["eventSubject"], "Operations Alignment")

    def test_run_key_determinism_and_collision_prevention(self):
        sub_pre = AutomationSubscription(
            subscriptionId="SUB-PRE-MULTI",
            version="1.0.0",
            tenantId="velora-tenant",
            owner="user-1",
            mailbox="exec@velora.ae",
            sender="agent@velora.ae",
            recipients=["exec@velora.ae"],
            kind=SubscriptionKind.PRE_MEETING,
            timezone="Asia/Dubai",
            localSchedule="",
            leadTimeMinutes=15,
            enabled=True,
            authorizedBy="user-1",
            authorizedAt="2026-09-01T00:00:00Z",
        )

        evt1 = [{"id": "EVT-1", "subject": "Meeting 1", "start": "2026-09-14T10:00:00+04:00", "isCancelled": False}]
        evt2 = [{"id": "EVT-2", "subject": "Meeting 2", "start": "2026-09-14T14:00:00+04:00", "isCancelled": False}]

        now_evt1 = datetime(2026, 9, 14, 9, 45, 0, tzinfo=self.tz_dubai)
        now_evt2 = datetime(2026, 9, 14, 13, 45, 0, tzinfo=self.tz_dubai)

        _, key1, _ = is_subscription_due(sub_pre, now=now_evt1, eligible_events=evt1)
        _, key1_repeat, _ = is_subscription_due(sub_pre, now=now_evt1, eligible_events=evt1)
        _, key2, _ = is_subscription_due(sub_pre, now=now_evt2, eligible_events=evt2)

        # Determinism
        self.assertEqual(key1, key1_repeat)
        # Different meetings on same day must have distinct run keys!
        self.assertNotEqual(key1, key2)
        self.assertIn("EVT-1", key1)
        self.assertIn("EVT-2", key2)

    def test_disabled_and_expired_subscription(self):
        # Disabled
        sub_disabled = AutomationSubscription(
            subscriptionId="SUB-DIS-001",
            version="1.0.0",
            tenantId="velora-tenant",
            owner="user-1",
            mailbox="exec@velora.ae",
            sender="agent@velora.ae",
            recipients=["exec@velora.ae"],
            kind=SubscriptionKind.MORNING,
            timezone="Asia/Dubai",
            localSchedule="07:00",
            enabled=False,  # Disabled!
            authorizedBy="user-1",
            authorizedAt="2026-09-01T00:00:00Z",
        )
        now = datetime(2026, 9, 14, 7, 5, 0, tzinfo=self.tz_dubai)
        is_due, key, ctx = is_subscription_due(sub_disabled, now=now)
        self.assertFalse(is_due)
        self.assertEqual(ctx.get("reason"), "SUBSCRIPTION_DISABLED")

        # Expired
        sub_expired = AutomationSubscription(
            subscriptionId="SUB-EXP-001",
            version="1.0.0",
            tenantId="velora-tenant",
            owner="user-1",
            mailbox="exec@velora.ae",
            sender="agent@velora.ae",
            recipients=["exec@velora.ae"],
            kind=SubscriptionKind.MORNING,
            timezone="Asia/Dubai",
            localSchedule="07:00",
            enabled=True,
            validUntil="2026-09-10T00:00:00Z",  # In the past
            authorizedBy="user-1",
            authorizedAt="2026-09-01T00:00:00Z",
        )
        is_due_exp, key_exp, ctx_exp = is_subscription_due(sub_expired, now=now)
        self.assertFalse(is_due_exp)
        self.assertEqual(ctx_exp.get("reason"), "AUTHORIZATION_EXPIRED")


if __name__ == "__main__":
    unittest.main()
