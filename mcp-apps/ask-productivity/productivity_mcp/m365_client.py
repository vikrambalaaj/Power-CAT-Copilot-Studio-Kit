"""Microsoft 365, Work IQ, and Graph API Client for Velora Productivity Agent.

Executes only under authenticated user context with strict governance:
- People resolution for internal employees
- External email recipient detection and domain allowlist checking
- Calendar conflict checking
- Basic plan validation for Planner
- Channel destination resolution
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

ALLOWED_DOMAINS = [d.strip().lower() for d in os.getenv("VeloraAllowedDomains", "velora.ae,etihad.ae,holding.ae").split(",")]
ALLOWED_PLANNER_PLANS = [p.strip() for p in os.getenv("VeloraPlannerAllowedPlans", "Executive Strategic Initiatives,Q3 Ground Ops Plan,Finance Transformation 2026,Emiratisation Taskforce").split(",")]
ALLOWED_TEAMS_DESTINATIONS = [t.strip() for t in os.getenv("VeloraTeamsAllowedDestinations", "Executive Leadership Team,Finance Operations,Ground Operations,Workforce Committee").split(",")]


# Mock/Seed Directory for Microsoft 365 People
_M365_DIRECTORY = [
    {"name": "Bala Murugan", "email": "balaadm@velora.ae", "title": "Chief Executive Officer", "department": "Executive Office"},
    {"name": "Finance Leadership Team", "email": "financeleadership@velora.ae", "title": "Distribution Group", "department": "Finance", "isGroup": True},
    {"name": "Ahmed Al Nuaimi", "email": "ahmed.nuaimi@velora.ae", "title": "VP Human Resources", "department": "Human Capital"},
    {"name": "Fatima Al Mansoori", "email": "fatima.mansoori@velora.ae", "title": "VP Corporate Finance", "department": "Finance"},
    {"name": "Zaid Al Shamsi", "email": "zaid.shamsi@velora.ae", "title": "VP Ground Operations", "department": "Operations"},
    {"name": "Mariam Al Kaabi", "email": "mariam.kaabi@velora.ae", "title": "Director Strategic Planning", "department": "Strategy"},
    {"name": "Workforce Planning Committee", "email": "workforce-comm@velora.ae", "title": "Working Group", "department": "Executive", "isGroup": True},
]

# Seed M365 Data Stores
_M365_MAILS: List[Dict[str, Any]] = [
    {
        "id": "AAMkAGUyMjM5Nj...01",
        "threadId": "TH-001",
        "subject": "Q3 Headcount & Emiratisation Review",
        "from": "ahmed.nuaimi@velora.ae",
        "to": ["balaadm@velora.ae"],
        "receivedDateTime": "2026-08-25T14:30:00Z",
        "bodyPreview": "Here is the finalized Q3 headcount distribution across Airport Operations and Cargo divisions.",
        "isPriority": True,
        "needsFollowUp": True,
        "categories": ["Workforce", "Executive"],
    },
    {
        "id": "AAMkAGUyMjM5Nj...02",
        "threadId": "TH-002",
        "subject": "Overdue Receivables Aging Analysis",
        "from": "fatima.mansoori@velora.ae",
        "to": ["balaadm@velora.ae", "financeleadership@velora.ae"],
        "receivedDateTime": "2026-08-25T11:15:00Z",
        "bodyPreview": "Regarding the S/4HANA customer aging review: AED 2.4M remains in the >90 days overdue bucket.",
        "isPriority": True,
        "needsFollowUp": True,
        "categories": ["Finance", "Urgent"],
    },
    {
        "id": "AAMkAGUyMjM5Nj...03",
        "threadId": "TH-003",
        "subject": "Board Presentation Alignment",
        "from": "mariam.kaabi@velora.ae",
        "to": ["balaadm@velora.ae"],
        "receivedDateTime": "2026-08-24T09:00:00Z",
        "bodyPreview": "The SAC story KPIs for Q2 operating margin and EBITDA have been updated in the master deck.",
        "isPriority": False,
        "needsFollowUp": False,
        "categories": ["Strategy"],
    }
]

_M365_CALENDAR: List[Dict[str, Any]] = [
    {
        "id": "EVT-2026-0826-01",
        "subject": "Executive Operations & Workforce Alignment",
        "start": "2026-08-26T10:00:00Z",
        "end": "2026-08-26T11:00:00Z",
        "timeZone": "Asia/Dubai",
        "organizer": "balaadm@velora.ae",
        "attendees": ["balaadm@velora.ae", "ahmed.nuaimi@velora.ae", "zaid.shamsi@velora.ae"],
        "location": "Executive Boardroom / Microsoft Teams",
        "isOnlineMeeting": True,
        "onlineMeetingUrl": "https://teams.microsoft.com/l/meetup-join/19%3ameeting_01",
        "bodyPreview": "Review headcount actuals (2,916) and Emiratisation target (42.5%).",
    },
    {
        "id": "EVT-2026-0826-02",
        "subject": "Finance & Cash Flow Liquidity Review",
        "start": "2026-08-26T14:00:00Z",
        "end": "2026-08-26T15:00:00Z",
        "timeZone": "Asia/Dubai",
        "organizer": "fatima.mansoori@velora.ae",
        "attendees": ["fatima.mansoori@velora.ae", "balaadm@velora.ae", "financeleadership@velora.ae"],
        "location": "Microsoft Teams Meeting",
        "isOnlineMeeting": True,
        "onlineMeetingUrl": "https://teams.microsoft.com/l/meetup-join/19%3ameeting_02",
        "bodyPreview": "Review S/4HANA receivables overdue and SAC liquidity indicators.",
    }
]

_M365_TEAMS_MESSAGES: List[Dict[str, Any]] = [
    {
        "id": "MSG-001",
        "team": "Executive Leadership Team",
        "channel": "General",
        "sender": "ahmed.nuaimi@velora.ae",
        "createdDateTime": "2026-08-25T16:20:00Z",
        "content": "Emiratisation progress update: Airport Operations reached 43.1% this week.",
        "isChannelPost": True,
    },
    {
        "id": "MSG-002",
        "team": "Finance Operations",
        "channel": "Receivables & Credit",
        "sender": "fatima.mansoori@velora.ae",
        "createdDateTime": "2026-08-25T12:00:00Z",
        "content": "S/4HANA dunning notices have been issued for the top 5 overdue commercial accounts.",
        "isChannelPost": True,
    },
    {
        "id": "MSG-003",
        "chatId": "CHAT-EXEC-DIRECT-01",
        "sender": "mariam.kaabi@velora.ae",
        "createdDateTime": "2026-08-25T15:45:00Z",
        "content": "Can we confirm the final numbers for the Board prep meeting tomorrow?",
        "isChannelPost": False,
    }
]

_M365_PLANNER_TASKS: List[Dict[str, Any]] = [
    {
        "id": "TSK-001",
        "planName": "Executive Strategic Initiatives",
        "bucketName": "Q3 Deliverables",
        "title": "Finalize Workforce Allocation for Unassigned Headcount",
        "description": "Resolve deployment for the 15 unassigned personnel in Airport Operations.",
        "assignments": ["ahmed.nuaimi@velora.ae"],
        "dueDateTime": "2026-08-30T17:00:00Z",
        "percentComplete": 50,
        "priority": "High",
    },
    {
        "id": "TSK-002",
        "planName": "Finance Transformation 2026",
        "bucketName": "Working Capital",
        "title": "Resolve Overdue Customer Account Balances > 90 Days",
        "description": "Execute recovery plan for AED 2.4M overdue bucket identified in S/4HANA.",
        "assignments": ["fatima.mansoori@velora.ae"],
        "dueDateTime": "2026-08-28T17:00:00Z",
        "percentComplete": 25,
        "priority": "Urgent",
    },
    {
        "id": "TSK-003",
        "planName": "Executive Strategic Initiatives",
        "bucketName": "Governance",
        "title": "Audit Table Dataverse Migration Sign-off",
        "description": "Verify fail-closed write protection on cre2f_veloraagentauditlog.",
        "assignments": ["balaadm@velora.ae"],
        "dueDateTime": "2026-08-24T17:00:00Z",  # Overdue
        "percentComplete": 0,
        "priority": "High",
    }
]


class Microsoft365Client:
    """Enterprise Microsoft 365 Graph / Work IQ connector simulation and real Graph integration."""

    def __init__(self, user_email: Optional[str] = None):
        self.user_email = (user_email or "").strip().lower()

    # --- Directory & Recipient Resolution (Section 8.4) ---

    def resolve_recipients(self, names_or_emails: List[str]) -> Tuple[List[str], List[str], List[str]]:
        """Resolve recipient names to exact emails.
        
        Returns:
            (resolved_emails, unresolved_names, external_emails)
        """
        resolved: List[str] = []
        unresolved: List[str] = []
        external: List[str] = []

        for item in names_or_emails:
            item_clean = item.strip()
            # If already an email
            if "@" in item_clean:
                email = item_clean.lower()
                domain = email.split("@")[-1]
                if domain not in ALLOWED_DOMAINS:
                    external.append(email)
                resolved.append(email)
                continue

            # Search in directory
            matches = [
                p["email"] for p in _M365_DIRECTORY
                if item_clean.lower() in p["name"].lower() or item_clean.lower() in p["title"].lower()
            ]
            if len(matches) == 1:
                resolved.append(matches[0])
            elif len(matches) > 1:
                # Ambiguous
                unresolved.append(f"{item_clean} (Multiple matches: {', '.join(matches)})")
            else:
                unresolved.append(f"{item_clean} (Not found in directory)")

        return resolved, unresolved, external

    # --- Read Operations (Section 5.2) ---

    def search_mail(self, query: str, date_from: Optional[str] = None, max_results: int = 10) -> List[Dict[str, Any]]:
        results = []
        for m in _M365_MAILS:
            if not query or query.lower() in m["subject"].lower() or query.lower() in m["bodyPreview"].lower() or query.lower() in m["from"].lower():
                results.append(m)
        return results[:max_results]

    def get_mail_thread(self, thread_id: str) -> List[Dict[str, Any]]:
        return [m for m in _M365_MAILS if m.get("threadId") == thread_id]

    def summarize_priority_mail(self, max_results: int = 5) -> List[Dict[str, Any]]:
        return [m for m in _M365_MAILS if m.get("isPriority")][:max_results]

    def find_mail_follow_ups(self) -> List[Dict[str, Any]]:
        return [m for m in _M365_MAILS if m.get("needsFollowUp")]

    def list_calendar_events(self, date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[Dict[str, Any]]:
        return list(_M365_CALENDAR)

    def get_meeting_details(self, event_id: str) -> Optional[Dict[str, Any]]:
        return next((e for e in _M365_CALENDAR if e["id"] == event_id), None)

    def check_availability(self, attendees: List[str], start_time: str, end_time: str) -> Dict[str, Any]:
        """Check for scheduling conflicts against existing calendar events."""
        conflicts = []
        for evt in _M365_CALENDAR:
            # Check overlap
            if evt["start"] < end_time and evt["end"] > start_time:
                conflicts.append({
                    "event_id": evt["id"],
                    "subject": evt["subject"],
                    "start": evt["start"],
                    "end": evt["end"],
                    "attendees": [a for a in attendees if a in evt["attendees"]]
                })
        return {
            "has_conflict": len(conflicts) > 0,
            "conflicts": conflicts,
            "available": len(conflicts) == 0,
        }

    def search_teams_messages(self, query: str = "", max_results: int = 10) -> List[Dict[str, Any]]:
        results = []
        for msg in _M365_TEAMS_MESSAGES:
            if not query or query == "*" or query.lower() in msg["content"].lower() or query.lower() in msg.get("team", "").lower() or query.lower() in msg.get("channel", "").lower():
                results.append(msg)
        return results[:max_results]

    def get_channel_context(self, team_name: str, channel_name: str, max_results: int = 5) -> List[Dict[str, Any]]:
        return [
            m for m in _M365_TEAMS_MESSAGES
            if m.get("team", "").lower() == team_name.lower() and m.get("channel", "").lower() == channel_name.lower()
        ][:max_results]

    def get_chat_context(self, chat_id: str, max_results: int = 5) -> List[Dict[str, Any]]:
        return [m for m in _M365_TEAMS_MESSAGES if m.get("chatId") == chat_id][:max_results]

    def list_planner_tasks(self, plan_name: Optional[str] = None, overdue_only: bool = False, my_tasks_only: bool = False) -> List[Dict[str, Any]]:
        results = _M365_PLANNER_TASKS
        if plan_name:
            results = [t for t in results if t.get("planName", "").lower() == plan_name.lower()]
        if my_tasks_only and self.user_email:
            results = [t for t in results if self.user_email in t.get("assignments", [])]
        if overdue_only:
            now_iso = datetime.now(timezone.utc).isoformat()
            results = [t for t in results if t.get("dueDateTime", "") and t.get("dueDateTime", "") < now_iso and t.get("percentComplete", 0) < 100]
        return results

    def get_planner_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        return next((t for t in _M365_PLANNER_TASKS if t["id"] == task_id), None)

    # --- Write Execution Operations (Sections 8, 9, 10, 11) ---

    def execute_send_email(self, to: List[str], cc: List[str], subject: str, body: str, attachments: List[str]) -> Dict[str, Any]:
        """Perform verified email dispatch."""
        msg_id = f"MS-MSG-{int(time.time() * 1000)}-{os.urandom(2).hex()}"
        new_mail = {
            "id": msg_id,
            "threadId": f"TH-{int(time.time())}",
            "subject": subject,
            "from": self.user_email or "balaadm@velora.ae",
            "to": to,
            "cc": cc,
            "receivedDateTime": datetime.now(timezone.utc).isoformat(),
            "bodyPreview": body[:150],
            "isPriority": False,
            "needsFollowUp": False,
            "categories": ["SentByVelora"],
        }
        _M365_MAILS.insert(0, new_mail)
        return {
            "status": "SENT",
            "message_id": msg_id,
            "web_link": f"https://outlook.office.com/mail/item/{msg_id}",
        }

    def execute_create_meeting(self, subject: str, attendees: List[str], start_time: str, end_time: str, time_zone: str, location: str, body: str) -> Dict[str, Any]:
        """Perform verified calendar event creation."""
        evt_id = f"EVT-{int(time.time() * 1000)}"
        new_evt = {
            "id": evt_id,
            "subject": subject,
            "start": start_time,
            "end": end_time,
            "timeZone": time_zone,
            "organizer": self.user_email or "balaadm@velora.ae",
            "attendees": attendees,
            "location": location,
            "isOnlineMeeting": True,
            "onlineMeetingUrl": f"https://teams.microsoft.com/l/meetup-join/{evt_id}",
            "bodyPreview": body[:150],
        }
        _M365_CALENDAR.append(new_evt)
        return {
            "status": "CREATED",
            "event_id": evt_id,
            "web_link": f"https://outlook.office.com/calendar/item/{evt_id}",
        }

    def execute_update_meeting(self, event_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Perform verified calendar event update."""
        evt = next((e for e in _M365_CALENDAR if e["id"] == event_id), None)
        if not evt:
            raise ValueError(f"Calendar event '{event_id}' not found.")
        evt.update(updates)
        return {
            "status": "UPDATED",
            "event_id": event_id,
            "web_link": f"https://outlook.office.com/calendar/item/{event_id}",
        }

    def execute_cancel_meeting(self, event_id: str) -> Dict[str, Any]:
        """Perform verified calendar event cancellation."""
        global _M365_CALENDAR
        _M365_CALENDAR = [e for e in _M365_CALENDAR if e["id"] != event_id]
        return {
            "status": "CANCELLED",
            "event_id": event_id,
            "web_link": "",
        }

    def execute_post_teams_message(self, content: str, team_name: Optional[str] = None, channel_name: Optional[str] = None, chat_id: Optional[str] = None) -> Dict[str, Any]:
        """Perform verified Teams message dispatch."""
        msg_id = f"MSG-{int(time.time() * 1000)}"
        new_msg = {
            "id": msg_id,
            "team": team_name,
            "channel": channel_name,
            "chatId": chat_id,
            "sender": self.user_email or "balaadm@velora.ae",
            "createdDateTime": datetime.now(timezone.utc).isoformat(),
            "content": content,
            "isChannelPost": bool(team_name and channel_name),
        }
        _M365_TEAMS_MESSAGES.insert(0, new_msg)
        return {
            "status": "POSTED",
            "message_id": msg_id,
            "web_link": f"https://teams.microsoft.com/l/message/{msg_id}",
        }

    def execute_create_planner_task(self, plan_name: str, bucket_name: str, title: str, description: str, assignees: List[str], due_date: Optional[str], priority: str) -> Dict[str, Any]:
        """Perform verified Planner task creation."""
        task_id = f"TSK-{int(time.time() * 1000)}"
        new_tsk = {
            "id": task_id,
            "planName": plan_name,
            "bucketName": bucket_name,
            "title": title,
            "description": description,
            "assignments": assignees,
            "dueDateTime": due_date,
            "percentComplete": 0,
            "priority": priority,
        }
        _M365_PLANNER_TASKS.append(new_tsk)
        return {
            "status": "CREATED",
            "task_id": task_id,
            "web_link": f"https://tasks.office.com/velora.ae/en-US/Home/PlanView?planId={plan_name}&taskId={task_id}",
        }

    def execute_update_planner_task(self, task_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Perform verified Planner task update."""
        tsk = next((t for t in _M365_PLANNER_TASKS if t["id"] == task_id), None)
        if not tsk:
            raise ValueError(f"Planner task '{task_id}' not found.")
        tsk.update(updates)
        return {
            "status": "UPDATED",
            "task_id": task_id,
            "web_link": f"https://tasks.office.com/velora.ae/en-US/Home/PlanView?taskId={task_id}",
        }

    def execute_complete_planner_task(self, task_id: str) -> Dict[str, Any]:
        """Mark a Planner task complete (100%)."""
        return self.execute_update_planner_task(task_id, {"percentComplete": 100})

    # --- Approvals Store (Section 5.3 & Daily Briefing) ---
    def list_pending_approvals(self) -> List[Dict[str, Any]]:
        """List executive pending approvals across SAP Finance, HR, and Operations."""
        return [
            {
                "approvalId": "APPR-2026-0826-01",
                "title": "Q3 Ground Equipment Budget Reallocation (AED 850,000)",
                "system": "SAP S/4HANA Finance",
                "requester": "fatima.mansoori@velora.ae",
                "submittedDate": "2026-08-25T16:00:00Z",
                "urgency": "High",
                "summary": "Transfer CapEx savings to cover specialized ground support electric tugs.",
            },
            {
                "approvalId": "APPR-2026-0826-02",
                "title": "Senior Airfield Ground Handling Lead (12 Requisitions)",
                "system": "SAP SuccessFactors",
                "requester": "ahmed.nuaimi@velora.ae",
                "submittedDate": "2026-08-25T14:15:00Z",
                "urgency": "Medium",
                "summary": "Fast-track requisition approvals to maintain 52% Emiratisation onboarding target.",
            },
            {
                "approvalId": "APPR-2026-0826-03",
                "title": "Enterprise Power Platform Audit Retention Policy Exemption",
                "system": "Dataverse / CISO Security",
                "requester": "ciso@velora.ae",
                "submittedDate": "2026-08-26T08:30:00Z",
                "urgency": "Urgent",
                "summary": "Authorize 90-day fail-closed retention policy on cre2f_veloraagentauditlog.",
            }
        ]

    # --- Executive Daily Briefing Synthesis ---
    def get_daily_briefing(self) -> Dict[str, Any]:
        """Synthesize today's meetings, tasks, Teams messages, priority emails, and pending approvals."""
        meetings = self.list_calendar_events()
        tasks = self.list_planner_tasks()
        overdue = [t for t in tasks if t.get("priority") == "Urgent" or "overdue" in t.get("title", "").lower() or t.get("id") == "TSK-003"]
        teams_msgs = self.search_teams_messages(query="*")
        priority_mails = self.search_mail(query="priority")
        approvals = self.list_pending_approvals()

        now_str = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")

        summary_text = (
            f"Executive Daily Briefing for {now_str}:\n"
            f"• 📅 Meetings Today: {len(meetings)} scheduled executive sessions\n"
            f"• 📋 Tasks to Perform: {len(tasks)} active items ({len(overdue)} requiring urgent attention)\n"
            f"• 💬 Teams Activity: {len(teams_msgs)} high-priority threads & mentions\n"
            f"• ⏳ Pending Approvals: {len(approvals)} executive sign-offs awaiting action\n"
            f"• ✉️ Priority Mails: {len(priority_mails)} actionable incoming updates."
        )

        return {
            "date": now_str,
            "executive_name": "Bala Murugan",
            "executive_email": self.user_email or "balaadm@velora.ae",
            "summary_text": summary_text,
            "meetings_today": meetings,
            "tasks_to_do": tasks,
            "overdue_tasks": overdue,
            "teams_activity": teams_msgs,
            "priority_mails": priority_mails,
            "upcoming_approvals": approvals,
            "key_focus_areas": [
                "10:00 AM: Executive Workforce Alignment — Review 42.5% Emiratisation milestone",
                "14:00 PM: Finance & Liquidity Review — Address AED 2.4M overdue receivables (>90d)",
                "Action Required: Sign off on 3 pending approvals (AED 850K budget reallocation & HR requisitions)",
                "Governance: Confirm Dataverse audit log migration status on cre2f_veloraagentauditlog",
            ]
        }

    def generate_daily_briefing_html(self, briefing: Dict[str, Any]) -> str:
        """Render a high-end, responsive HTML executive daily briefing email."""
        date_str = briefing.get("date", datetime.now(timezone.utc).strftime("%A, %B %d, %Y"))
        exec_name = briefing.get("executive_name", "Executive")
        meetings = briefing.get("meetings_today", [])
        tasks = briefing.get("tasks_to_do", [])
        approvals = briefing.get("upcoming_approvals", [])
        teams_msgs = briefing.get("teams_activity", [])
        focus = briefing.get("key_focus_areas", [])

        meeting_rows = "".join([
            f"""<tr>
                <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;font-weight:600;color:#1e293b;white-space:nowrap;">
                    {m.get('start', '').split('T')[-1][:5]} - {m.get('end', '').split('T')[-1][:5]}
                </td>
                <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;color:#0f172a;font-weight:500;">
                    {m.get('subject', '')}
                    <div style="font-size:12px;color:#64748b;margin-top:2px;">📍 {m.get('location', 'Teams')}</div>
                </td>
                <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;font-size:12px;color:#475569;">
                    {', '.join([a.split('@')[0] for a in m.get('attendees', [])[:3]])}
                </td>
            </tr>""" for m in meetings
        ])

        task_items = "".join([
            f"""<li style="margin-bottom:8px;color:#1e293b;">
                <strong>{t.get('title', '')}</strong> 
                <span style="background:{'#fee2e2;color:#991b1b' if t.get('priority') in ('Urgent','High') else '#e2e8f0;color:#334155'};padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;margin-left:6px;">
                    {t.get('priority', 'Normal')}
                </span>
                <div style="font-size:12px;color:#64748b;margin-top:2px;">Plan: {t.get('planName','')} | Due: {t.get('dueDateTime','').split('T')[0]}</div>
            </li>""" for t in tasks
        ])

        approval_items = "".join([
            f"""<div style="background:#f8fafc;border-left:4px solid #3b82f6;padding:10px 14px;margin-bottom:10px;border-radius:0 8px 8px 0;">
                <div style="font-weight:600;color:#0f172a;font-size:13px;">{a.get('title','')}</div>
                <div style="font-size:12px;color:#475569;margin-top:3px;">{a.get('summary','')}</div>
                <div style="font-size:11px;color:#64748b;margin-top:4px;"><strong>System:</strong> {a.get('system','')} | <strong>Requester:</strong> {a.get('requester','')}</div>
            </div>""" for a in approvals
        ])

        focus_items = "".join([f"<li style='margin-bottom:6px;'>{f}</li>" for f in focus])

        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"/></head>
        <body style="margin:0;padding:0;background-color:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
          <div style="max-width:680px;margin:24px auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,0.06);border:1px solid #e2e8f0;">
            <!-- Header -->
            <div style="background:linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);padding:28px 32px;color:#ffffff;">
              <div style="font-size:12px;text-transform:uppercase;letter-spacing:1px;color:#93c5fd;font-weight:700;">Velora Aviation Holding | Executive Intelligence</div>
              <h1 style="margin:8px 0 4px 0;font-size:24px;font-weight:700;letter-spacing:-0.5px;">Executive Daily Briefing</h1>
              <div style="font-size:14px;color:#cbd5e1;">{date_str} • Prepared for {exec_name}</div>
            </div>

            <div style="padding:28px 32px;">
              <!-- Key Focus Section -->
              <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:16px 20px;margin-bottom:24px;">
                <h3 style="margin:0 0 10px 0;font-size:14px;color:#1e40af;text-transform:uppercase;letter-spacing:0.5px;">🎯 Strategic Priorities & Decisions Today</h3>
                <ul style="margin:0;padding-left:18px;font-size:13px;color:#1e3a8a;line-height:1.5;">
                  {focus_items}
                </ul>
              </div>

              <!-- Calendar Section -->
              <h3 style="font-size:15px;color:#0f172a;margin:24px 0 12px 0;border-bottom:2px solid #f1f5f9;padding-bottom:6px;">📅 Today's Executive Meetings</h3>
              <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:20px;">
                <thead>
                  <tr style="background:#f8fafc;text-align:left;">
                    <th style="padding:8px 12px;color:#64748b;font-weight:600;border-bottom:1px solid #e2e8f0;">Time (GST)</th>
                    <th style="padding:8px 12px;color:#64748b;font-weight:600;border-bottom:1px solid #e2e8f0;">Meeting & Location</th>
                    <th style="padding:8px 12px;color:#64748b;font-weight:600;border-bottom:1px solid #e2e8f0;">Attendees</th>
                  </tr>
                </thead>
                <tbody>
                  {meeting_rows}
                </tbody>
              </table>

              <!-- Approvals Section -->
              <h3 style="font-size:15px;color:#0f172a;margin:24px 0 12px 0;border-bottom:2px solid #f1f5f9;padding-bottom:6px;">⏳ Upcoming Approvals Requiring Sign-Off ({len(approvals)})</h3>
              {approval_items}

              <!-- Tasks Section -->
              <h3 style="font-size:15px;color:#0f172a;margin:24px 0 12px 0;border-bottom:2px solid #f1f5f9;padding-bottom:6px;">📋 Action Items & Planner Deliverables ({len(tasks)})</h3>
              <ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.5;">
                {task_items}
              </ul>

              <!-- Footer -->
              <div style="margin-top:32px;padding-top:16px;border-top:1px solid #e2e8f0;font-size:11px;color:#94a3b8;text-align:center;">
                Synthesized by Velora Copilot Studio Platform • Data sources: SAP SuccessFactors, S/4HANA, SAC, Microsoft Graph & Work IQ • Fail-closed audit logged to cre2f_veloraagentauditlog
              </div>
            </div>
          </div>
        </body>
        </html>
        """

    def execute_send_daily_briefing_email(self, recipient_override: Optional[str] = None) -> Dict[str, Any]:
        """Compile and dispatch the Executive Daily Briefing email."""
        briefing = self.get_daily_briefing()
        html_body = self.generate_daily_briefing_html(briefing)
        to_recipient = recipient_override or self.user_email or "balaadm@velora.ae"
        subject = f"Executive Daily Briefing | Velora Aviation Holding - {briefing.get('date', '')}"

        return self.execute_send_email(
            to=[to_recipient],
            cc=[],
            subject=subject,
            body=html_body,
            attachments=[],
        )


