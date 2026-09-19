"""Briefing Service — Velora Executive Agent Platform.

Unified synthesis engine for executive briefings:
1. MORNING: Calendar schedule, upcoming & overdue Planner tasks, unread attention items (via CASE triage), pending approvals.
2. PRE_MEETING: Upcoming non-canceled meeting dossier, attendees, agenda, cross-referenced related emails and tasks.
3. END_OF_DAY: Completed tasks & meetings (truthful attribution: never counts emails as completed tasks), remaining actions, tomorrow's preview.

Enforces:
- Deterministic SHA-256 snapshot content hashing for cryptographic binding.
- Attributed claims, sources, and weakest-link confidence evaluation.
- Strict cancellation filtering (excludes isCancelled=True).
- Non-zero executive HTML rendering with modern dark/light Velora aesthetic.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .confidence_policy import (
    derive_composite_confidence,
    evaluate_confidence,
    parse_iso_timestamp,
)
from .evidence_contracts import (
    ClaimKind,
    ConfidenceLabel,
    EvidenceSource,
    MaterialClaim,
    OperationStatus,
    decimal_serializer,
)
from .m365_client import Microsoft365Client
from .schedule_engine import DEFAULT_TIMEZONE, get_timezone_offset
from .triage_engine import TEST_EQUAL_WEIGHTS_RUBRIC, score_candidates_pipeline

log = logging.getLogger("productivity_mcp.briefing_service")


def compute_content_hash(data: Dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash of a briefing snapshot dictionary."""
    canonical = json.dumps(data, sort_keys=True, default=decimal_serializer)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
VELORA_LOGO_BASE64 = (
    "data:image/png;base64,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"
)


class BriefingService:
    """High-assurance briefing synthesis engine for Velora One."""

    def __init__(self, tz_name: str = DEFAULT_TIMEZONE):
        self.tz_name = tz_name
        self.tz = get_timezone_offset(tz_name)

    def get_morning_briefing(
        self,
        client: Microsoft365Client,
        user_email: str,
        reference_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Synthesize Morning Executive Briefing."""
        ref_now = (reference_time or datetime.now(timezone.utc)).astimezone(self.tz)
        now_iso = ref_now.isoformat()
        date_str = ref_now.strftime("%A, %B %d, %Y")
        exec_name = user_email.split("@")[0].replace(".", " ").title() if "@" in user_email else "Executive"

        warnings: List[str] = []
        claims: List[MaterialClaim] = []
        sources: List[EvidenceSource] = []

        # 1. Calendar Events (exclude canceled)
        meetings = []
        try:
            raw_events = client.list_calendar_events()
            for ev in raw_events:
                if ev.get("isCancelled"):
                    continue
                meetings.append(ev)
            cal_src_id = f"calendar-{user_email}"
            sources.append(EvidenceSource(
                sourceId=cal_src_id,
                system="MICROSOFT_GRAPH",
                businessTitle="Executive Calendar Schedule",
                retrievedAt=now_iso,
                url="https://graph.microsoft.com/v1.0/me/calendarView",
            ))
            claims.append(MaterialClaim(
                claimId=f"claim-cal-{ref_now.strftime('%Y%m%d')}",
                text=f"{len(meetings)} meetings scheduled today for {exec_name}",
                kind=ClaimKind.FACT,
                sourceIds=[cal_src_id],
            ))
        except Exception as ex:
            warnings.append(f"Calendar: {ex}")

        # 2. Tasks & Overdue Items
        tasks = []
        overdue_tasks = []
        try:
            tasks = client.list_planner_tasks(my_tasks_only=True)
            for t in tasks:
                due_dt = parse_iso_timestamp(t.get("dueDateTime"))
                percent = t.get("percentComplete", 0)
                if due_dt and due_dt < ref_now and percent < 100:
                    overdue_tasks.append(t)
            planner_src_id = f"planner-{user_email}"
            sources.append(EvidenceSource(
                sourceId=planner_src_id,
                system="MICROSOFT_PLANNER",
                businessTitle="Executive Planner Tasks",
                retrievedAt=now_iso,
                url="https://graph.microsoft.com/v1.0/me/planner/tasks",
            ))
            claims.append(MaterialClaim(
                claimId=f"claim-tasks-{ref_now.strftime('%Y%m%d')}",
                text=f"{len(tasks)} active tasks ({len(overdue_tasks)} overdue) in Microsoft Planner",
                kind=ClaimKind.FACT,
                sourceIds=[planner_src_id],
            ))
        except Exception as ex:
            warnings.append(f"Planner: {ex}")

        # 3. Contextual Attention Items (CASE Triage Engine)
        scored_attention: List[Dict[str, Any]] = []
        try:
            recent_mails = client.search_mail(query="") or client.summarize_priority_mail()
            scored_items = score_candidates_pipeline(
                mail_candidates=recent_mails,
                calendar_candidates=meetings,
                task_candidates=tasks,
                rubric=TEST_EQUAL_WEIGHTS_RUBRIC,
                now=ref_now,
                maximum_results=5,
                default_tz_offset="+04:00",
            )
            scored_attention = [c.model_dump() for c in scored_items if c.totalScore >= 60]
            triage_src_id = "case-rubric-v1"
            sources.append(EvidenceSource(
                sourceId=triage_src_id,
                system="TRIAGE_ENGINE",
                businessTitle="CASE Attention Triage Rubric",
                retrievedAt=now_iso,
            ))
        except Exception as ex:
            warnings.append(f"Attention Engine: {ex}")

        # 4. Approvals
        approvals = []
        try:
            approvals = client.list_pending_approvals()
            if approvals:
                appr_src_id = "approvals-pending"
                sources.append(EvidenceSource(
                    sourceId=appr_src_id,
                    system="DATAVERSE_APPROVALS",
                    businessTitle="Pending Executive Sign-offs",
                    retrievedAt=now_iso,
                ))
        except Exception:
            # Source may be unavailable if not configured; graceful handling
            pass

        # Weakest-link confidence
        conf_eval = evaluate_confidence(
            sources=sources,
            now=ref_now,
            has_conflicts=False,
            is_materially_complete=len(warnings) == 0,
        )

        summary_text = (
            f"Executive Morning Briefing for {date_str}:\n"
            f"• 📅 Scheduled Meetings: {len(meetings)} session(s)\n"
            f"• 📋 Tasks: {len(tasks)} active ({len(overdue_tasks)} overdue)\n"
            f"• ⚡ Priority Attention Items: {len(scored_attention)} items requiring review\n"
            f"• ⏳ Approvals: {len(approvals)} pending sign-off."
        )

        snapshot_data = {
            "kind": "MORNING",
            "date": date_str,
            "executive_name": exec_name,
            "executive_email": user_email,
            "summary_text": summary_text,
            "meetings_count": len(meetings),
            "tasks_count": len(tasks),
            "overdue_count": len(overdue_tasks),
            "attention_count": len(scored_attention),
            "approvals_count": len(approvals),
            "meetings": meetings,
            "tasks": tasks,
            "overdue_tasks": overdue_tasks,
            "attention_items": scored_attention,
            "approvals": approvals,
            "warnings": warnings,
        }
        content_hash = compute_content_hash(snapshot_data)
        html_body = self.generate_morning_html(snapshot_data, content_hash)

        return {
            "status": OperationStatus.SUCCESS.value if not warnings else OperationStatus.PARTIAL.value,
            "kind": "MORNING",
            "date": date_str,
            "executive_name": exec_name,
            "executive_email": user_email,
            "summary_text": summary_text,
            "meetings": meetings,
            "tasks": tasks,
            "overdue_tasks": overdue_tasks,
            "attention_items": scored_attention,
            "approvals": approvals,
            "claims": [c.model_dump() for c in claims],
            "sources": [s.model_dump() for s in sources],
            "confidence": conf_eval.model_dump(),
            "contentHash": content_hash,
            "renderedHtml": html_body,
            "warnings": warnings,
        }

    def get_pre_meeting_briefing(
        self,
        client: Microsoft365Client,
        user_email: str,
        event_id: Optional[str] = None,
        lead_time_minutes: int = 15,
        reference_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Synthesize Pre-Meeting Dossier Briefing for the upcoming or designated meeting."""
        ref_now = (reference_time or datetime.now(timezone.utc)).astimezone(self.tz)
        now_iso = ref_now.isoformat()
        exec_name = user_email.split("@")[0].replace(".", " ").title() if "@" in user_email else "Executive"

        raw_events = client.list_calendar_events()
        # Strictly exclude canceled events
        eligible_events = [ev for ev in raw_events if not ev.get("isCancelled")]

        target_event: Optional[Dict[str, Any]] = None
        if event_id:
            for ev in eligible_events:
                if ev.get("id") == event_id:
                    target_event = ev
                    break
        else:
            # Find next upcoming event starting after ref_now or within lead time
            upcoming = []
            for ev in eligible_events:
                start_dt = parse_iso_timestamp(ev.get("start"))
                if start_dt:
                    start_local = start_dt.astimezone(self.tz)
                    # Include if starts in the future or started within last 15 min
                    if start_local >= (ref_now - timedelta(minutes=15)):
                        upcoming.append((start_local, ev))
            upcoming.sort(key=lambda x: x[0])
            if upcoming:
                target_event = upcoming[0][1]

        if not target_event:
            empty_snapshot = {
                "kind": "PRE_MEETING",
                "status": "NO_ELIGIBLE_MEETING",
                "executive_name": exec_name,
                "message": "No eligible upcoming meetings found on calendar.",
            }
            content_hash = compute_content_hash(empty_snapshot)
            conf_eval = evaluate_confidence(sources=[], now=ref_now)
            return {
                "status": OperationStatus.SUCCESS.value,
                "kind": "PRE_MEETING",
                "summary_text": "No upcoming non-canceled executive meetings detected for pre-meeting briefing.",
                "targetEvent": None,
                "claims": [],
                "sources": [],
                "confidence": conf_eval.model_dump(),
                "contentHash": content_hash,
                "renderedHtml": "<p>No upcoming meetings requiring pre-meeting briefing.</p>",
            }

        # Target event found
        subject = target_event.get("subject", "Executive Meeting")
        start_time_str = target_event.get("start", "")
        end_time_str = target_event.get("end", "")
        attendees = target_event.get("attendees", [])
        join_url = target_event.get("onlineMeetingUrl") or (target_event.get("onlineMeeting") or {}).get("joinUrl") or ""
        body_preview = target_event.get("bodyPreview") or ""

        # Cross-reference related emails and tasks
        related_mails = []
        try:
            search_terms = subject.split()[:2]
            for term in search_terms:
                if len(term) > 3:
                    mails = client.search_mail(query=term)
                    for m in mails:
                        if m.get("id") not in [rm.get("id") for rm in related_mails]:
                            related_mails.append(m)
        except Exception:
            pass

        related_tasks = []
        try:
            all_tasks = client.list_planner_tasks(my_tasks_only=True)
            for t in all_tasks:
                if any(w.lower() in t.get("title", "").lower() for w in subject.split() if len(w) > 3):
                    related_tasks.append(t)
        except Exception:
            pass

        evt_src_id = target_event.get("id") or "event-target"
        sources = [
            EvidenceSource(
                sourceId=evt_src_id,
                system="MICROSOFT_GRAPH_CALENDAR",
                businessTitle=f"Calendar Event: {subject}",
                retrievedAt=now_iso,
            )
        ]
        if related_mails:
            mail_src_id = f"mail-ref-{len(related_mails)}"
            sources.append(EvidenceSource(
                sourceId=mail_src_id,
                system="MICROSOFT_GRAPH_MAIL",
                businessTitle="Related Executive Email Threads",
                retrievedAt=now_iso,
            ))

        claims = [
            MaterialClaim(
                claimId=f"claim-evt-{target_event.get('id', 'evt')}",
                text=f"Meeting '{subject}' starts at {start_time_str} with {len(attendees)} attendees",
                kind=ClaimKind.FACT,
                sourceIds=[evt_src_id],
            )
        ]

        conf_eval = evaluate_confidence(sources=sources, now=ref_now, has_conflicts=False)

        summary_text = (
            f"Pre-Meeting Briefing: '{subject}' ({start_time_str} - {end_time_str})\n"
            f"• Attendees: {len(attendees)} participant(s)\n"
            f"• Related Mail Context: {len(related_mails)} thread(s)\n"
            f"• Action Items / Planner Tasks: {len(related_tasks)} item(s)."
        )

        snapshot_data = {
            "kind": "PRE_MEETING",
            "eventId": target_event.get("id"),
            "subject": subject,
            "start": start_time_str,
            "end": end_time_str,
            "attendees": attendees,
            "joinUrl": join_url,
            "bodyPreview": body_preview,
            "related_mails_count": len(related_mails),
            "related_tasks_count": len(related_tasks),
            "executive_name": exec_name,
            "summary_text": summary_text,
        }
        content_hash = compute_content_hash(snapshot_data)
        html_body = self.generate_pre_meeting_html(snapshot_data, related_mails, related_tasks, content_hash)

        return {
            "status": OperationStatus.SUCCESS.value,
            "kind": "PRE_MEETING",
            "targetEvent": target_event,
            "summary_text": summary_text,
            "attendees": attendees,
            "relatedMails": related_mails,
            "relatedTasks": related_tasks,
            "claims": [c.model_dump() for c in claims],
            "sources": [s.model_dump() for s in sources],
            "confidence": conf_eval.model_dump(),
            "contentHash": content_hash,
            "renderedHtml": html_body,
        }

    def get_end_of_day_digest(
        self,
        client: Microsoft365Client,
        user_email: str,
        local_schedule: Optional[str] = None,
        reference_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Synthesize End-of-Day Digest.
        
        Strict Invariants:
        - Evaluates observed completed tasks and meetings from real source evidence.
        - NEVER labels sent emails as completed tasks.
        - Identifies open overdue items and tomorrow's upcoming commitments.
        - Missing EOD schedule requires explicit configuration (CONFIGURATION_REQUIRED).
        """
        ref_now = (reference_time or datetime.now(timezone.utc)).astimezone(self.tz)
        now_iso = ref_now.isoformat()
        date_str = ref_now.strftime("%A, %B %d, %Y")
        exec_name = user_email.split("@")[0].replace(".", " ").title() if "@" in user_email else "Executive"

        # Check configuration requirement if local_schedule is explicitly requested
        if local_schedule is not None and not local_schedule:
            conf_eval = evaluate_confidence(sources=[], now=ref_now, limiting_factors_override=["MISSING_LOCAL_SCHEDULE"])
            return {
                "status": OperationStatus.CONFIGURATION_REQUIRED.value,
                "kind": "END_OF_DAY",
                "summary_text": "CONFIGURATION_REQUIRED: Missing explicit EOD local schedule definition (e.g. '17:30').",
                "claims": [],
                "sources": [],
                "confidence": conf_eval.model_dump(),
                "contentHash": "",
                "renderedHtml": "<p>CONFIGURATION_REQUIRED: Set an explicit EOD schedule time.</p>",
            }

        warnings: List[str] = []
        sources: List[EvidenceSource] = []
        claims: List[MaterialClaim] = []

        # 1. Observed Completed Tasks from Planner
        completed_tasks = []
        pending_tasks = []
        overdue_tasks = []
        try:
            all_tasks = client.list_planner_tasks(my_tasks_only=True)
            for t in all_tasks:
                percent = t.get("percentComplete", 0)
                due_dt = parse_iso_timestamp(t.get("dueDateTime"))
                if percent >= 100 or t.get("completedDateTime"):
                    completed_tasks.append(t)
                else:
                    pending_tasks.append(t)
                    if due_dt and due_dt < ref_now:
                        overdue_tasks.append(t)
            planner_src_id = f"planner-{user_email}"
            sources.append(EvidenceSource(
                sourceId=planner_src_id,
                system="MICROSOFT_PLANNER",
                businessTitle="Planner Task Execution History",
                retrievedAt=now_iso,
                url="https://graph.microsoft.com/v1.0/me/planner/tasks",
            ))
            claims.append(MaterialClaim(
                claimId=f"claim-completed-tasks-{ref_now.strftime('%Y%m%d')}",
                text=f"{len(completed_tasks)} Planner tasks completed, {len(pending_tasks)} pending ({len(overdue_tasks)} overdue)",
                kind=ClaimKind.FACT,
                sourceIds=[planner_src_id],
            ))
        except Exception as ex:
            warnings.append(f"Planner: {ex}")

        # 2. Observed Held Meetings Today
        held_meetings = []
        tomorrow_meetings = []
        try:
            raw_events = client.list_calendar_events()
            for ev in raw_events:
                if ev.get("isCancelled"):
                    continue
                start_dt = parse_iso_timestamp(ev.get("start"))
                end_dt = parse_iso_timestamp(ev.get("end"))
                if start_dt and end_dt:
                    start_local = start_dt.astimezone(self.tz)
                    end_local = end_dt.astimezone(self.tz)
                    # Held today: started today and ended before now
                    if start_local.date() == ref_now.date() and end_local <= ref_now:
                        held_meetings.append(ev)
                    # Tomorrow: starts tomorrow
                    elif start_local.date() == (ref_now.date() + timedelta(days=1)):
                        tomorrow_meetings.append(ev)
            cal_src_id = f"calendar-{user_email}"
            sources.append(EvidenceSource(
                sourceId=cal_src_id,
                system="MICROSOFT_GRAPH_CALENDAR",
                businessTitle="Calendar Concluded Sessions",
                retrievedAt=now_iso,
            ))
        except Exception as ex:
            warnings.append(f"Calendar: {ex}")

        # 3. Tomorrow's Commitments
        tomorrow_commitments = [
            f"📅 Meeting: {m.get('subject')} at {m.get('start', '').split('T')[-1][:5]}"
            for m in tomorrow_meetings
        ]
        tomorrow_date = (ref_now + timedelta(days=1)).date()
        for t in pending_tasks:
            due_dt = parse_iso_timestamp(t.get("dueDateTime"))
            if due_dt and due_dt.astimezone(self.tz).date() == tomorrow_date:
                tomorrow_commitments.append(f"📋 Task Due: {t.get('title')}")

        conf_eval = evaluate_confidence(sources=sources, now=ref_now, has_conflicts=False)

        summary_text = (
            f"Executive End-of-Day Digest for {date_str}:\n"
            f"• ✅ Completed Tasks: {len(completed_tasks)} item(s) (Planner ground truth)\n"
            f"• 🤝 Concluded Meetings: {len(held_meetings)} session(s)\n"
            f"• ⏳ Open / Overdue Tasks: {len(pending_tasks)} pending ({len(overdue_tasks)} overdue)\n"
            f"• 🌅 Tomorrow's Horizon: {len(tomorrow_commitments)} scheduled commitment(s)."
        )

        snapshot_data = {
            "kind": "END_OF_DAY",
            "date": date_str,
            "executive_name": exec_name,
            "executive_email": user_email,
            "summary_text": summary_text,
            "completed_tasks_count": len(completed_tasks),
            "held_meetings_count": len(held_meetings),
            "pending_tasks_count": len(pending_tasks),
            "overdue_tasks_count": len(overdue_tasks),
            "tomorrow_commitments_count": len(tomorrow_commitments),
            "completed_tasks": completed_tasks,
            "held_meetings": held_meetings,
            "pending_tasks": pending_tasks,
            "overdue_tasks": overdue_tasks,
            "tomorrow_commitments": tomorrow_commitments,
        }
        content_hash = compute_content_hash(snapshot_data)
        html_body = self.generate_eod_html(snapshot_data, content_hash)

        return {
            "status": OperationStatus.SUCCESS.value if not warnings else OperationStatus.PARTIAL.value,
            "kind": "END_OF_DAY",
            "date": date_str,
            "executive_name": exec_name,
            "executive_email": user_email,
            "summary_text": summary_text,
            "completed_tasks": completed_tasks,
            "held_meetings": held_meetings,
            "pending_tasks": pending_tasks,
            "overdue_tasks": overdue_tasks,
            "tomorrow_commitments": tomorrow_commitments,
            "claims": [c.model_dump() for c in claims],
            "sources": [s.model_dump() for s in sources],
            "confidence": conf_eval.model_dump(),
            "contentHash": content_hash,
            "renderedHtml": html_body,
            "warnings": warnings,
        }

    # -------------------------------------------------------------------------
    # HTML Rendering Engines
    # -------------------------------------------------------------------------

    def generate_morning_html(self, data: Dict[str, Any], content_hash: str) -> str:
        """Render responsive executive morning briefing HTML."""
        meetings = data.get("meetings", [])
        tasks = data.get("tasks", [])
        attention = data.get("attention_items", [])
        date_str = data.get("date", "")
        exec_name = data.get("executive_name", "Executive")

        meeting_rows = "".join([
            f"""<tr>
                <td style="padding:8px 12px;border-bottom:1px solid #23394D;font-weight:600;color:#FFFFFF;white-space:nowrap;">
                    {m.get('start', '').split('T')[-1][:5]}
                </td>
                <td style="padding:8px 12px;border-bottom:1px solid #23394D;color:#E1E7EC;">
                    {m.get('subject', 'Untitled')}
                </td>
                <td style="padding:8px 12px;border-bottom:1px solid #23394D;color:#8EA0B0;font-size:11px;">
                    {len(m.get('attendees', []))} attendees
                </td>
            </tr>""" for m in meetings[:5]
        ]) or "<tr><td colspan='3' style='padding:10px;color:#8EA0B0;'>No meetings scheduled today.</td></tr>"

        attention_rows = "".join([
            f"""<div style="background:#101E2B;border:1px solid #203547;border-radius:6px;padding:10px;margin-bottom:8px;">
                <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                    <strong style="color:#FFFFFF;font-size:12px;">{att.get('subject', 'Item')}</strong>
                    <span style="background:rgba(19,166,166,0.2);color:#13A6A6;font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;">
                        P{att.get('rank', 1)} • Score {att.get('totalScore', 0)}
                    </span>
                </div>
                <div style="color:#8EA0B0;font-size:11px;">From: {att.get('sender', 'Unknown')}</div>
            </div>""" for att in attention[:3]
        ]) or "<div style='color:#8EA0B0;font-size:12px;'>Zero urgent attention items detected.</div>"

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0B1924; color: #E1E7EC; margin:0; padding:20px; }}
  .card {{ background: #142433; border: 1px solid #23394D; border-radius: 10px; padding: 20px; max-width: 680px; margin: 0 auto; }}
  .header {{ border-bottom: 1px solid #23394D; padding-bottom: 12px; margin-bottom: 16px; }}
  .title {{ font-size: 16px; font-weight: 700; color: #FFFFFF; }}
  .hash {{ font-family: monospace; font-size: 10px; color: #60A5FA; margin-top: 4px; }}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <table style="width:100%;border-collapse:collapse;">
      <tr>
        <td style="vertical-align:middle;">
          <div class="title">🌅 Velora Executive Morning Briefing — {date_str}</div>
          <div style="font-size:12px;color:#8EA0B0;margin-top:2px;">Prepared for {exec_name}</div>
          <div class="hash">Snapshot SHA-256: {content_hash[:16]}...</div>
        </td>
        <td style="vertical-align:middle;text-align:right;width:120px;">
          <img src="{VELORA_LOGO_BASE64}" alt="Velora Logo" style="height:36px;max-width:110px;display:inline-block;" />
        </td>
      </tr>
    </table>
  </div>
  <div style="margin-bottom:16px;">
    <h4 style="font-size:13px;color:#13A6A6;text-transform:uppercase;margin-bottom:8px;">📅 Today's Agenda ({len(meetings)} meetings)</h4>
    <table style="width:100%;border-collapse:collapse;font-size:12px;">
      {meeting_rows}
    </table>
  </div>
  <div style="margin-bottom:16px;">
    <h4 style="font-size:13px;color:#FBBF24;text-transform:uppercase;margin-bottom:8px;">⚡ Executive Attention Items ({len(attention)})</h4>
    {attention_rows}
  </div>
</div>
</body>
</html>"""

    def generate_pre_meeting_html(
        self,
        data: Dict[str, Any],
        related_mails: List[Dict[str, Any]],
        related_tasks: List[Dict[str, Any]],
        content_hash: str,
    ) -> str:
        """Render responsive Pre-Meeting Briefing HTML matching Gap 2 UI mockup."""
        subject = data.get("subject", "Executive Meeting")
        start = data.get("start", "")
        end = data.get("end", "")
        attendees = data.get("attendees", [])
        join_url = data.get("joinUrl", "")
        attendee_list = []
        for a in attendees[:4]:
            if isinstance(a, dict):
                addr = a.get("emailAddress", {}).get("address", "") or a.get("name", "")
                if addr:
                    attendee_list.append(addr)
            elif isinstance(a, str):
                attendee_list.append(a)
        attendees_str = ", ".join(attendee_list) or "Internal Team"

        mail_items = "".join([
            f"<li style='margin-bottom:4px;'><strong style='color:#FFFFFF;'>{m.get('subject', '')}</strong> ({m.get('from', '')})</li>"
            for m in related_mails[:3]
        ]) or "<li>No prior email threads directly cross-referenced.</li>"

        join_btn = f"""<a href="{join_url}" style="display:inline-block;background:#13A6A6;color:#FFFFFF;text-decoration:none;font-size:12px;font-weight:700;padding:8px 16px;border-radius:6px;margin-top:12px;">Join Teams Meeting</a>""" if join_url else ""

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0B1924; color: #E1E7EC; margin:0; padding:20px; }}
  .card {{ background: #142433; border: 1px solid #23394D; border-radius: 10px; padding: 20px; max-width: 680px; margin: 0 auto; }}
  .badge {{ background: #13A6A6; color: #FFFFFF; font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 4px; text-transform: uppercase; }}
</style>
</head>
<body>
<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #23394D;padding-bottom:12px;margin-bottom:16px;">
    <span class="badge">T-15 MIN AUTONOMOUS DOSSIER</span>
    <span style="font-family:monospace;font-size:10px;color:#60A5FA;">SHA: {content_hash[:16]}...</span>
  </div>
  <h3 style="color:#FFFFFF;margin-bottom:4px;font-size:16px;">{subject}</h3>
  <p style="color:#8EA0B0;font-size:12px;margin-bottom:12px;">Time: {start} – {end} | Attendees: {attendees_str}</p>
  <div style="background:#101E2B;border:1px solid #203547;border-radius:8px;padding:12px;margin-bottom:14px;font-size:12px;">
    <strong style="color:#13A6A6;">Cross-Referenced Correspondence:</strong>
    <ul style="margin:6px 0 0 16px;padding:0;color:#CBD5E1;">
      {mail_items}
    </ul>
  </div>
  {join_btn}
</div>
</body>
</html>"""

    def generate_eod_html(self, data: Dict[str, Any], content_hash: str) -> str:
        """Render responsive End-of-Day Digest HTML matching Gap 3 UI mockup."""
        date_str = data.get("date", "")
        exec_name = data.get("executive_name", "Executive")
        completed = data.get("completed_tasks", [])
        held = data.get("held_meetings", [])
        overdue = data.get("overdue_tasks", [])
        tomorrow = data.get("tomorrow_commitments", [])

        completed_rows = "".join([
            f"""<tr>
                <td style="padding:8px 10px;border-bottom:1px solid #1C3042;color:#FFFFFF;">{t.get('title', 'Task')}</td>
                <td style="padding:8px 10px;border-bottom:1px solid #1C3042;color:#4ADE80;font-weight:700;font-size:10px;">COMPLETED</td>
            </tr>""" for t in completed[:5]
        ]) or "<tr><td colspan='2' style='padding:8px;color:#8EA0B0;'>Zero tasks marked 100% complete today.</td></tr>"

        overdue_rows = "".join([
            f"""<tr>
                <td style="padding:8px 10px;border-bottom:1px solid #1C3042;color:#F87171;">{t.get('title', 'Task')}</td>
                <td style="padding:8px 10px;border-bottom:1px solid #1C3042;color:#F87171;font-weight:700;font-size:10px;">OVERDUE</td>
            </tr>""" for t in overdue[:5]
        ])

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0B1924; color: #E1E7EC; margin:0; padding:20px; }}
  .card {{ background: #142433; border: 1px solid #23394D; border-radius: 10px; padding: 20px; max-width: 680px; margin: 0 auto; }}
  .badge {{ background: #D68A1E; color: #FFFFFF; font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 4px; text-transform: uppercase; }}
</style>
</head>
<body>
<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #23394D;padding-bottom:12px;margin-bottom:16px;">
    <span class="badge">DAILY EXECUTIVE WRAP-UP</span>
    <span style="font-family:monospace;font-size:10px;color:#60A5FA;">SHA: {content_hash[:16]}...</span>
  </div>
  <h3 style="color:#FFFFFF;font-size:16px;margin-bottom:4px;">Closed-Loop Digest — {date_str}</h3>
  <p style="color:#8EA0B0;font-size:12px;margin-bottom:14px;">Prepared for {exec_name} • Strict Evidence Grounding</p>
  <table style="width:100%;border-collapse:collapse;font-size:12px;background:#0E1A24;border:1px solid #1E3447;border-radius:6px;margin-bottom:14px;">
    <thead>
      <tr style="background:#0A131A;color:#8EA0B0;font-size:10px;text-transform:uppercase;">
        <th style="text-align:left;padding:8px 10px;">Item / Stream</th>
        <th style="text-align:left;padding:8px 10px;">Status</th>
      </tr>
    </thead>
    <tbody>
      {completed_rows}
      {overdue_rows}
    </tbody>
  </table>
  <div style="background:#101E2B;border:1px solid #203547;border-radius:6px;padding:12px;font-size:12px;">
    <strong style="color:#60A5FA;">🌅 Tomorrow's Horizon ({len(tomorrow)} commitments):</strong>
    <ul style="margin:6px 0 0 16px;padding:0;color:#CBD5E1;">
      {"".join([f"<li>{c}</li>" for c in tomorrow[:4]]) or "<li>No immediate morning commitments scheduled.</li>"}
    </ul>
  </div>
</div>
</body>
</html>"""


_BRIEFING_SERVICE: Optional[BriefingService] = None

def get_briefing_service() -> BriefingService:
    global _BRIEFING_SERVICE
    if _BRIEFING_SERVICE is None:
        _BRIEFING_SERVICE = BriefingService()
    return _BRIEFING_SERVICE
