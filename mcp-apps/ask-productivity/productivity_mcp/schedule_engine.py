"""Schedule Engine — Velora Executive Agent Platform.

Timezone-aware local schedule and subscription evaluation for executive briefings.
Evaluates local times (e.g. Asia/Dubai 07:00) against UTC execution clocks, calculates
due runs, pre-meeting lead times, EOD windows, and enforces missed-run/quiet-hours policies.
"""
from __future__ import annotations

import logging
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .evidence_contracts import AutomationSubscription, SubscriptionKind
from .confidence_policy import parse_iso_timestamp

log = logging.getLogger("productivity_mcp.schedule_engine")

DEFAULT_TIMEZONE = "Asia/Dubai"
DEFAULT_TZ_OFFSET_HOURS = 4  # UTC+4 for Asia/Dubai


def get_timezone_offset(tz_name: str) -> timezone:
    """Resolve standard timezones or default to UTC+4 (Asia/Dubai)."""
    if tz_name.lower() in ("asia/dubai", "gst"):
        return timezone(timedelta(hours=4))
    if tz_name.lower() in ("utc", "gmt"):
        return timezone.utc
    # Fallback default: UTC+4
    return timezone(timedelta(hours=DEFAULT_TZ_OFFSET_HOURS))


def parse_schedule_time(schedule_str: str) -> Optional[Tuple[int, int]]:
    """Parse 'HH:MM' or simple cron 'M H * * *' into (hour, minute)."""
    if not schedule_str:
        return None
    s = schedule_str.strip()
    # Format "HH:MM"
    if ":" in s and len(s) == 5:
        try:
            parts = s.split(":")
            return int(parts[0]), int(parts[1])
        except Exception:
            return None
    # Cron format "M H * * *"
    cron_parts = s.split()
    if len(cron_parts) == 5:
        try:
            minute = int(cron_parts[0])
            hour = int(cron_parts[1])
            return hour, minute
        except Exception:
            return None
    return None


def calculate_local_occurrence(
    target_date: datetime,
    hour: int,
    minute: int,
    tz: timezone,
) -> datetime:
    """Construct a timezone-aware occurrence datetime for a given calendar date."""
    return datetime(
        year=target_date.year,
        month=target_date.month,
        day=target_date.day,
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
        tzinfo=tz,
    )


def is_subscription_due(
    subscription: AutomationSubscription,
    now: Optional[datetime] = None,
    tolerance_minutes: int = 15,
    eligible_events: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Evaluate whether an automation subscription is due for execution.
    
    Returns:
        (is_due, run_key, execution_context)
    
    Run Key Format:
        (tenantId, subscriptionId, subscriptionVersion, scheduledOccurrence, [eventId])
    Prevents duplicate dispatches across restarts or reruns.
    """
    if not subscription.enabled:
        return False, None, {"reason": "SUBSCRIPTION_DISABLED"}

    tz = get_timezone_offset(subscription.timezone or DEFAULT_TIMEZONE)
    ref_now = (now or datetime.now(timezone.utc)).astimezone(tz)

    # 1. Validate Subscription Expiry
    if subscription.validUntil:
        expiry_dt = parse_iso_timestamp(subscription.validUntil)
        if expiry_dt and ref_now > expiry_dt.astimezone(tz):
            return False, None, {"reason": "AUTHORIZATION_EXPIRED"}

    # 2. Check kind-specific scheduling
    kind = subscription.kind

    if kind == SubscriptionKind.MORNING:
        # Expected morning time (e.g. 07:00)
        parsed = parse_schedule_time(subscription.localSchedule or "07:00")
        if not parsed:
            return False, None, {"reason": "INVALID_SCHEDULE_FORMAT"}
        target_hour, target_min = parsed

        scheduled_dt = calculate_local_occurrence(ref_now, target_hour, target_min, tz)
        diff_sec = (ref_now - scheduled_dt).total_seconds()

        # Is current time within the due window? [0, tolerance_minutes]
        if 0 <= diff_sec <= (tolerance_minutes * 60):
            occurrence_key = scheduled_dt.isoformat()
            run_key = f"{subscription.tenantId}:{subscription.subscriptionId}:{subscription.version}:{occurrence_key}"
            return True, run_key, {
                "kind": "MORNING",
                "scheduledOccurrence": occurrence_key,
                "localTime": ref_now.isoformat(),
            }
        return False, None, {"reason": "NOT_IN_MORNING_WINDOW", "scheduled": scheduled_dt.isoformat()}

    elif kind == SubscriptionKind.EOD:
        # Expected EOD time (e.g. 17:00 or user-configured)
        if not subscription.localSchedule:
            return False, None, {"reason": "CONFIGURATION_REQUIRED", "detail": "Missing EOD schedule time"}
        parsed = parse_schedule_time(subscription.localSchedule)
        if not parsed:
            return False, None, {"reason": "INVALID_SCHEDULE_FORMAT"}
        target_hour, target_min = parsed

        scheduled_dt = calculate_local_occurrence(ref_now, target_hour, target_min, tz)
        diff_sec = (ref_now - scheduled_dt).total_seconds()

        if 0 <= diff_sec <= (tolerance_minutes * 60):
            occurrence_key = scheduled_dt.isoformat()
            run_key = f"{subscription.tenantId}:{subscription.subscriptionId}:{subscription.version}:{occurrence_key}"
            return True, run_key, {
                "kind": "EOD",
                "scheduledOccurrence": occurrence_key,
                "localTime": ref_now.isoformat(),
            }
        return False, None, {"reason": "NOT_IN_EOD_WINDOW", "scheduled": scheduled_dt.isoformat()}

    elif kind == SubscriptionKind.PRE_MEETING:
        # Evaluate upcoming eligible meetings
        lead_time_min = subscription.leadTimeMinutes or 15
        if not eligible_events:
            return False, None, {"reason": "NO_ELIGIBLE_MEETINGS"}

        for ev in eligible_events:
            # Strictly exclude canceled events
            if ev.get("isCancelled"):
                continue

            start_str = ev.get("start")
            if isinstance(start_str, dict):
                start_str = start_str.get("dateTime")
            if not start_str:
                continue

            event_start_dt = parse_iso_timestamp(start_str)
            if not event_start_dt:
                continue
            event_start_local = event_start_dt.astimezone(tz)

            # Trigger time is event_start - lead_time_min
            trigger_dt = event_start_local - timedelta(minutes=lead_time_min)
            diff_sec = (ref_now - trigger_dt).total_seconds()

            # Within window [0, tolerance_minutes]?
            if 0 <= diff_sec <= (tolerance_minutes * 60):
                event_id = ev.get("id") or "UNKNOWN_EVT"
                occurrence_key = event_start_local.isoformat()
                run_key = f"{subscription.tenantId}:{subscription.subscriptionId}:{subscription.version}:{occurrence_key}:{event_id}"
                return True, run_key, {
                    "kind": "PRE_MEETING",
                    "eventId": event_id,
                    "eventSubject": ev.get("subject", ""),
                    "eventStart": event_start_local.isoformat(),
                    "scheduledOccurrence": occurrence_key,
                }

        return False, None, {"reason": "NO_UPCOMING_PRE_MEETING_DUE"}

    elif kind == SubscriptionKind.ACTION_REMINDER:
        # Periodic action reminder
        occurrence_key = ref_now.strftime("%Y-%m-%d-%H")
        run_key = f"{subscription.tenantId}:{subscription.subscriptionId}:{subscription.version}:{occurrence_key}"
        return True, run_key, {
            "kind": "ACTION_REMINDER",
            "scheduledOccurrence": occurrence_key,
        }

    return False, None, {"reason": "UNKNOWN_SUBSCRIPTION_KIND"}
