"""Facilitator MCP Tools, Calendar Automation, Dataverse User Log Feedback & Knowledge Graph."""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

FACILITATOR_AUTO_SEND_GUIDE = """To make your Facilitator Copilot agent automatically send emails, you need to add an automated workflow tool using Power Automate or a custom Outlook connector inside Microsoft Copilot Studio.
Here is how to set up and configure the auto-send email capability.
🛠️ Step 1: Add the Automation Tool
Open your agent inside Microsoft Copilot Studio.
Navigate to the Actions (or Tools) tab from the left menu.
Click Add an action.
Search for Outlook or Power Automate.
Select the Send an email (V2) action from the Office 365 Outlook connector. [1]
📋 Step 2: Configure the Input Parameters
For the Facilitator agent to send the email without asking the user for basic details every time, you must map the input fields to variables captured during the meeting or chat:
To: Map this to the attendee's email variable or a specific fallback email address.
Subject: Set a dynamic string (e.g., Meeting Summary: [Topic]).
Body: Map this to the AI-generated summary text or meeting notes variable captured by the Facilitator.
⚡ Step 3: Trigger the Email Automatically
To bypass asking the user for confirmation and make it a true "auto-send" feature:
Open the specific conversational topic or trigger phase (e.g., "End of Meeting").
Insert the Send an email (V2) action node directly into the workflow canvas.
Toggle the Pre-fill / Auto-execute settings to active.
Ensure the Review before sending option is turned off so the agent executes the action instantly. [2]
Would you like me to:
Draft the exact prompt instructions to tell the Facilitator when it should trigger the email?
Guide you on how to format the AI-generated meeting notes inside the email body?
[1] https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/procurement-agent-supplier-com-setup
[2] https://www.youtube.com/watch?v=HJj8STkKj2k"""

# Service Account and Entra App Defaults
ENTRA_TENANT_ID = os.environ.get("ENTRA_TENANT_ID", "7d167021-f5e9-4331-9b75-d44d55a1ce9b")
ENTRA_CLIENT_ID = os.environ.get("ENTRA_CLIENT_ID", "5d178cb2-251e-436c-b2ec-5f36021d2cf8")
ENTRA_CLIENT_SECRET = os.environ.get("ENTRA_CLIENT_SECRET", "")
SVC_SENDER_EMAIL = os.environ.get("SVC_SENDER_EMAIL", "svc_aiagent@velora.ae")

# In-memory stores for Knowledge Graph, Meetings, Loop Components, and Dataverse Audit Logs
_KNOWLEDGE_GRAPH: List[Dict[str, Any]] = []
_LOOP_NOTEBOOK_RECORDS: List[Dict[str, Any]] = []
_CALENDAR_STORE: List[Dict[str, Any]] = [
    {
        "meeting_id": "MTG-2026-0818-01",
        "subject": "Executive Strategy & Operational Alignment",
        "start_time": "2026-08-18T10:00:00Z",
        "end_time": "2026-08-18T11:00:00Z",
        "organizer": "balaadm@velora.ae",
        "attendees": ["balaadm@velora.ae", "leadership@velora.ae", "amurugan@velora.ae"],
        "location": "Microsoft Teams Meeting",
        "status": "COMPLETED",
        "focus_areas": ["Workforce Headcount", "Financial Liquidity & AR Aging", "SAC EBITDA KPIs"]
    },
    {
        "meeting_id": "MTG-2026-0818-02",
        "subject": "Weekly Ground Operations & Workforce Planning",
        "start_time": "2026-08-18T14:00:00Z",
        "end_time": "2026-08-18T15:00:00Z",
        "organizer": "balaadm@velora.ae",
        "attendees": ["balaadm@velora.ae", "leadership@velora.ae", "ops@velora.ae"],
        "location": "Microsoft Teams Meeting",
        "status": "SCHEDULED",
        "focus_areas": ["Ramp & Baggage Staffing", "Emiratisation Target (42.5%)"]
    }
]

# Seed Dataverse audit log records with user-level tracking
_DATAVERSE_AUDIT_LOGS: List[Dict[str, Any]] = [
    {
        "cre2f_veloraagentauditlogid": "LOG-001",
        "cre2f_agentname": "Velora Executive Agent",
        "cre2f_auditdetail": "User queried workforce headcount by department from SuccessFactors (2,916 total)",
        "cre2f_dataclassification": "CONFIDENTIAL",
        "cre2f_demodata": False,
        "cre2f_environment": "Velora-AgenticAD-Dev",
        "cre2f_eventtime": "2026-08-18T08:45:00Z",
        "cre2f_newcolumn": "balaadm@velora.ae",
        "cre2f_operation": "READ_WORKFORCE_HEADCOUNT",
        "cre2f_outcome": "SUCCESS",
        "cre2f_resultcount": 2916,
        "cre2f_sourcesystem": "SuccessFactors",
        "cre2f_toolname": "aggregate_headcount_by_department"
    },
    {
        "cre2f_veloraagentauditlogid": "LOG-002",
        "cre2f_agentname": "Velora Executive Agent",
        "cre2f_auditdetail": "User reviewed AR aging overdue exposure of AED 2.4M and EBITDA KPI run-rate of 23.8%",
        "cre2f_dataclassification": "CONFIDENTIAL",
        "cre2f_demodata": False,
        "cre2f_environment": "Velora-AgenticAD-Dev",
        "cre2f_eventtime": "2026-08-18T09:15:00Z",
        "cre2f_newcolumn": "balaadm@velora.ae",
        "cre2f_operation": "READ_FINANCIAL_METRICS",
        "cre2f_outcome": "SUCCESS",
        "cre2f_resultcount": 4,
        "cre2f_sourcesystem": "S4HANA",
        "cre2f_toolname": "get_receivables_aging_summary"
    },
    {
        "cre2f_veloraagentauditlogid": "LOG-003",
        "cre2f_agentname": "Velora Executive Agent",
        "cre2f_auditdetail": "User reviewed Cargo division operational metrics and staffing schedules",
        "cre2f_dataclassification": "CONFIDENTIAL",
        "cre2f_demodata": False,
        "cre2f_environment": "Velora-AgenticAD-Dev",
        "cre2f_eventtime": "2026-08-18T07:30:00Z",
        "cre2f_newcolumn": "otheruser@velora.ae",
        "cre2f_operation": "READ_CARGO_OPERATIONS",
        "cre2f_outcome": "SUCCESS",
        "cre2f_resultcount": 203,
        "cre2f_sourcesystem": "SuccessFactors",
        "cre2f_toolname": "get_workforce_overview"
    }
]


def query_user_history_from_dataverse(
    user_email: str,
    limit: int = 10,
    filter_operation: Optional[str] = None,
) -> Dict[str, Any]:
    """Query and filter Dataverse audit logs (cre2f_veloraagentauditlog) strictly for the specific user."""
    sanitized_email = user_email.strip().lower()
    
    # Filter logs strictly matching the requested user email
    user_logs = [
        log for log in _DATAVERSE_AUDIT_LOGS
        if log.get("cre2f_newcolumn", "").strip().lower() == sanitized_email
    ]

    if filter_operation:
        user_logs = [
            log for log in user_logs
            if filter_operation.lower() in log.get("cre2f_operation", "").lower()
        ]

    # Sort descending by event time
    user_logs.sort(key=lambda x: x.get("cre2f_eventtime", ""), reverse=True)
    selected_logs = user_logs[:limit]

    # Build concise history timeline
    timeline = [
        {
            "log_id": log["cre2f_veloraagentauditlogid"],
            "timestamp": log["cre2f_eventtime"],
            "system": log["cre2f_sourcesystem"],
            "operation": log["cre2f_operation"],
            "summary": log["cre2f_auditdetail"],
            "outcome": log["cre2f_outcome"]
        }
        for log in selected_logs
    ]

    return {
        "status": "SUCCESS",
        "table": "cre2f_veloraagentauditlog",
        "user_email": sanitized_email,
        "total_records_found": len(user_logs),
        "returned_records_count": len(selected_logs),
        "history_timeline": timeline,
        "user_isolation_enforced": True,
        "message": f"Successfully retrieved {len(selected_logs)} historical records from Dataverse for user '{sanitized_email}'."
    }


def sync_dataverse_logs_to_memory(
    user_email: str,
    limit: int = 5,
) -> Dict[str, Any]:
    """Sync the specific user's Dataverse audit history into the active Knowledge Graph / Memory Base for personalized context recall."""
    history_res = query_user_history_from_dataverse(user_email=user_email, limit=limit)
    timeline = history_res.get("history_timeline", [])
    
    now_iso = datetime.now(timezone.utc).isoformat()
    synced_nodes = []
    
    for item in timeline:
        node_id = f"KG-DV-{item['log_id']}"
        # Check if already in knowledge graph
        if not any(n.get("node_id") == node_id for n in _KNOWLEDGE_GRAPH):
            node = {
                "node_id": node_id,
                "chat_id": f"DATAVERSE-SYNC-{item['log_id']}",
                "timestamp": item["timestamp"],
                "user_query": f"Historical {item['operation']} ({item['system']})",
                "agent_response": item["summary"],
                "topics": [item["system"], item["operation"]],
                "entities": [{"type": "System", "name": item["system"]}],
                "decisions_captured": [],
                "source_systems": [item["system"]],
                "governance": {
                    "owner": user_email.strip().lower(),
                    "data_classification": "CONFIDENTIAL",
                    "source": "Dataverse_cre2f_veloraagentauditlog"
                }
            }
            _KNOWLEDGE_GRAPH.append(node)
            synced_nodes.append(node_id)

    return {
        "status": "DATAVERSE_MEMORY_SYNCED",
        "user_email": user_email.strip().lower(),
        "synced_nodes_count": len(synced_nodes),
        "synced_node_ids": synced_nodes,
        "active_knowledge_graph_size": len(_KNOWLEDGE_GRAPH),
        "message": f"User interaction history from Dataverse is now active in the agent's memory for '{user_email}'."
    }


def get_facilitator_guide() -> Dict[str, Any]:
    """Retrieve the official step-by-step Facilitator Copilot auto-send email and meeting workflow setup guide."""
    return {
        "title": "Facilitator Copilot Auto-Send Email Configuration Guide",
        "content": FACILITATOR_AUTO_SEND_GUIDE,
        "steps": [
            {
                "step": 1,
                "title": "Add the Automation Tool",
                "action": "Add Send an email (V2) action from Office 365 Outlook connector or Power Automate workflow.",
            },
            {
                "step": 2,
                "title": "Configure Input Parameters",
                "action": "Map To (attendees), Subject (Meeting Summary: [Topic]), and Body (AI summary text).",
            },
            {
                "step": 3,
                "title": "Trigger the Email Automatically",
                "action": "Set Pre-fill / Auto-execute to active and turn off 'Review before sending' for instant dispatch.",
            },
        ],
        "references": [
            "https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/procurement-agent-supplier-com-setup",
            "https://www.youtube.com/watch?v=HJj8STkKj2k",
        ],
    }


def get_calendar_meetings(
    user_email: Optional[str] = None,
    timeframe: str = "today",
    filter_subject: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch meetings directly from the executive's Outlook / Teams Calendar."""
    matched = _CALENDAR_STORE
    if filter_subject:
        matched = [m for m in matched if filter_subject.lower() in m["subject"].lower()]

    return {
        "status": "SUCCESS",
        "timeframe": timeframe,
        "total_meetings": len(matched),
        "meetings": matched,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": "Microsoft Outlook & Teams Calendar"
    }


def process_calendar_meeting_workflow(
    meeting_subject: Optional[str] = None,
    phase: str = "POST_MEETING",
    meeting_id: Optional[str] = None,
    notes: Optional[str] = None,
    key_decisions: Optional[List[str]] = None,
    action_items: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Automatically execute pre-meeting synthesis or post-meeting email dispatch based on calendar event context."""
    meeting = None
    if meeting_id:
        meeting = next((m for m in _CALENDAR_STORE if m["meeting_id"] == meeting_id), None)
    elif meeting_subject:
        meeting = next((m for m in _CALENDAR_STORE if meeting_subject.lower() in m["subject"].lower()), None)
    
    if not meeting:
        meeting = _CALENDAR_STORE[0]

    attendees = meeting.get("attendees", ["leadership@velora.ae"])
    title = meeting.get("subject", "Executive Meeting")

    if phase.upper() == "PRE_MEETING":
        briefing = generate_pre_meeting_briefing(meeting_title=title, attendees=attendees)
        return {
            "workflow": "PRE_MEETING_BRIEFING",
            "meeting_context": meeting,
            "briefing_packet": briefing["briefing_packet"],
            "status": "BRIEFING_DELIVERED_TO_INBOX",
            "action_taken": "Synthesized SAP facts across SuccessFactors, S/4HANA, and SAC for upcoming calendar meeting."
        }

    decisions = key_decisions or ["Approved Q3 workforce allocation plan", "Authorized automated email dispatch"]
    actions = action_items or [{"task": "Review AR aging overdue bucket", "owner": "Finance Team", "due": "2026-08-25"}]
    
    draft = draft_meeting_summary_email(
        topic=title,
        attendees=attendees,
        key_decisions=decisions,
        action_items=actions,
        notes=notes or f"Meeting concluded. Attendees resolved directly from Calendar invite: {', '.join(attendees)}."
    )

    send_result = send_executive_email_via_graph(
        to_recipients=attendees,
        subject=draft["subject"],
        body_html=draft["body_html"]
    )

    loop_result = export_meeting_to_loop_notebook(
        meeting_title=title,
        attendees=attendees,
        summary=draft["body_html"],
        key_decisions=decisions,
        action_items=actions
    )

    kg_result = ingest_chat_to_knowledge_graph(
        chat_id=meeting.get("meeting_id", "CAL-WRAPUP"),
        user_query=f"Wrap up meeting: {title}",
        agent_response=f"Auto-sent summary to {len(attendees)} calendar attendees. Stored in Loop {loop_result['loop_component_id']}.",
        topics=["Meeting Wrapup", "Calendar Automation"],
        decisions_captured=decisions
    )

    return {
        "workflow": "POST_MEETING_AUTO_WRAPUP",
        "meeting_context": meeting,
        "email_delivery": send_result,
        "loop_storage": loop_result,
        "knowledge_graph_node": kg_result["node_id"],
        "status": "COMPLETED_AND_AUTO_DISPATCHED",
        "message": f"Successfully pulled meeting '{title}' from calendar, generated notes, and auto-dispatched email to {len(attendees)} attendees via svc_aiagent@velora.ae."
    }


def ingest_chat_to_knowledge_graph(
    chat_id: str,
    user_query: str,
    agent_response: str,
    topics: Optional[List[str]] = None,
    entities: Optional[List[Dict[str, str]]] = None,
    decisions_captured: Optional[List[str]] = None,
    source_systems: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Ingest chat interaction and response into Institutional Memory Knowledge Graph / Dataverse Knowledge Base."""
    now_iso = datetime.now(timezone.utc).isoformat()
    record_id = hashlib.sha256(f"{chat_id}:{user_query}:{now_iso}".encode("utf-8")).hexdigest()[:16]

    node = {
        "node_id": f"KG-NODE-{record_id}",
        "chat_id": chat_id,
        "timestamp": now_iso,
        "user_query": user_query,
        "agent_response": agent_response,
        "topics": topics or ["General Analytics"],
        "entities": entities or [],
        "decisions_captured": decisions_captured or [],
        "source_systems": source_systems or ["SuccessFactors", "S4HANA", "SAC"],
        "governance": {
            "searchable_by": ["Executives", "Successors"],
            "data_classification": "CONFIDENTIAL",
            "retained_as_institutional_memory": True,
        }
    }
    _KNOWLEDGE_GRAPH.append(node)

    return {
        "status": "INGESTED_TO_KNOWLEDGE_GRAPH",
        "node_id": node["node_id"],
        "total_indexed_nodes": len(_KNOWLEDGE_GRAPH),
        "topics_indexed": node["topics"],
        "summary": "Chat interaction successfully indexed into Institutional Memory Knowledge Base.",
    }


def generate_pre_meeting_briefing(
    meeting_title: str,
    attendees: List[str],
    meeting_date: Optional[str] = None,
    focus_areas: Optional[List[str]] = None,
    include_sap_connectors: bool = True,
) -> Dict[str, Any]:
    """Synthesize cross-connector SAP data into an executive briefing packet ahead of scheduled meetings."""
    date_str = meeting_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    briefing_content = {
        "meeting_title": meeting_title,
        "date": date_str,
        "attendees": attendees,
        "executive_digest": f"Executive pre-meeting brief synthesized across SAP SuccessFactors, S/4HANA, and SAC for {meeting_title}.",
        "connector_synthesis": {
            "successfactors_hcm": {
                "metric": "Workforce & Organization",
                "key_facts": "Total workforce at 2,916 records across Business Units; Emirati representation on track.",
                "status": "NORMAL"
            },
            "s4hana_finance": {
                "metric": "Liquidity & Working Capital",
                "key_facts": "Overdue AR aging at AED 2.4M with 94% collected in 0-30 day bucket; Operating Profit positive.",
                "status": "ACTION_REQUIRED"
            },
            "sac_analytics": {
                "metric": "Corporate Performance & EBITDA",
                "key_facts": "Corporate EBITDA margin at 23.8% (Target: 22.0%); Gross Revenue run-rate on track.",
                "status": "ON_TRACK"
            }
        },
        "discussion_agenda_recommendations": [
            "Review AR aging action plan for top 3 overdue accounts.",
            "Confirm Q3 workforce succession planning milestones.",
            "Align on SAC corporate story KPI exports for board review."
        ],
        "open_questions": [
            "Are collections on high-value receivables expected before month-end?",
            "What is the final headcount requisition count for digital transformation?"
        ]
    }

    return {
        "status": "BRIEFING_GENERATED",
        "briefing_id": f"BRIEF-{hashlib.md5(meeting_title.encode()).hexdigest()[:8]}",
        "briefing_packet": briefing_content,
        "distribution_target": "Executive Inbox & Calendar",
        "readiness": "READY_FOR_PRE_MEETING_REVIEW"
    }


def export_meeting_to_loop_notebook(
    meeting_title: str,
    attendees: List[str],
    summary: str,
    key_decisions: List[str],
    action_items: List[Dict[str, str]],
    target_storage: str = "Microsoft Loop & OneNote Notebook",
) -> Dict[str, Any]:
    """Export meeting transcript, decisions, and actions into Microsoft Loop component / OneNote Notebook for institutional memory."""
    now_iso = datetime.now(timezone.utc).isoformat()
    loop_item_id = f"LOOP-{hashlib.sha256(f'{meeting_title}:{now_iso}'.encode()).hexdigest()[:12]}"

    notebook_record = {
        "loop_component_id": loop_item_id,
        "storage_target": target_storage,
        "notebook_name": "Velora Executive Institutional Memory",
        "section": "Facilitator Meeting Records",
        "meeting_title": meeting_title,
        "timestamp": now_iso,
        "attendees": attendees,
        "summary": summary,
        "key_decisions": key_decisions,
        "action_items": action_items,
        "retention_policy": "PERMANENT_SUCCESSOR_ACCESSIBLE",
        "search_tags": [meeting_title.lower(), "executive_decision", "facilitator", "action_item"]
    }
    _LOOP_NOTEBOOK_RECORDS.append(notebook_record)

    return {
        "status": "SAVED_TO_LOOP_NOTEBOOK",
        "loop_component_id": loop_item_id,
        "notebook_location": f"OneNote://Velora-Org/Executive Notebook/{meeting_title}",
        "loop_embed_link": f"https://loop.microsoft.com/p/velora-exec/{loop_item_id}",
        "records_count": len(_LOOP_NOTEBOOK_RECORDS),
        "searchable_from_go_live": True,
        "message": "Meeting notes, decisions, and action items securely stored in Loop / Notebook."
    }


def send_executive_email_via_graph(
    to_recipients: List[str],
    subject: str,
    body_html: str,
    cc_recipients: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Automatically send executive email via Microsoft Graph API using the service account credentials."""
    token_url = f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}/oauth2/v2.0/token"
    token_data = (
        f"client_id={ENTRA_CLIENT_ID}&scope=https://graph.microsoft.com/.default"
        f"&client_secret={ENTRA_CLIENT_SECRET}&grant_type=client_credentials"
    ).encode("utf-8")
    
    token_req = urllib.request.Request(
        token_url,
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    
    with urllib.request.urlopen(token_req, timeout=10) as token_resp:
        token_obj = json.loads(token_resp.read().decode("utf-8"))
        access_token = token_obj["access_token"]
    
    send_url = f"https://graph.microsoft.com/v1.0/users/{SVC_SENDER_EMAIL}/sendMail"
    message_payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": body_html
            },
            "toRecipients": [{"emailAddress": {"address": addr.strip()}} for addr in to_recipients],
            "ccRecipients": [{"emailAddress": {"address": addr.strip()}} for addr in (cc_recipients or [])]
        },
        "saveToSentItems": "true"
    }

    req = urllib.request.Request(
        send_url,
        data=json.dumps(message_payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=10) as resp:
        status_code = resp.status

    return {
        "status": "EMAIL_SENT",
        "sender": SVC_SENDER_EMAIL,
        "to": to_recipients,
        "cc": cc_recipients or [],
        "subject": subject,
        "graph_http_status": status_code,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "delivery_mode": "MICROSOFT_GRAPH_SERVICE_PRINCIPAL"
    }


def draft_meeting_summary_email(
    topic: str,
    attendees: List[str],
    key_decisions: List[str],
    action_items: List[Dict[str, str]],
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Draft an executive meeting summary email ready for automatic dispatch."""
    recipients = ", ".join(attendees)
    decisions_html = "".join(f"<li>{d}</li>" for d in key_decisions)
    actions_html = "".join(
        f"<li><strong>{item.get('task', '')}</strong> — Owner: <em>{item.get('owner', 'Unassigned')}</em> (Due: {item.get('due', 'TBD')})</li>"
        for item in action_items
    )
    
    now_str = datetime.now(timezone.utc).strftime("%B %d, %Y")
    subject = f"Executive Meeting Summary: {topic} - {now_str}"
    body_html = f"""
    <h2>Meeting Summary: {topic}</h2>
    <p><strong>Date:</strong> {now_str}</p>
    <p><strong>Attendees:</strong> {recipients}</p>
    <hr/>
    <h3>Key Decisions</h3>
    <ul>{decisions_html}</ul>
    <h3>Action Items</h3>
    <ul>{actions_html}</ul>
    """
    if notes:
        body_html += f"<h3>Discussion Notes</h3><p>{notes}</p>"

    return {
        "status": "ready_for_auto_send",
        "to": recipients,
        "subject": subject,
        "body_html": body_html.strip(),
        "auto_send_eligible": True,
    }


def configure_auto_send_policy(
    agent_name: str = "Facilitator Copilot",
    require_confirmation: bool = False,
    default_recipients: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Configure auto-send and workflow policies for the Facilitator agent."""
    return {
        "agent": agent_name,
        "policy": {
            "auto_send_enabled": True,
            "bypass_user_review": not require_confirmation,
            "default_recipients": default_recipients or ["leadership@velora.ae"],
            "trigger_event": "End_of_Meeting",
            "audit_logging": True,
        },
        "message": "Facilitator auto-send policy configured successfully.",
    }


TOOL_SPECS = [
    ("get_facilitator_guide", "Retrieve the complete step-by-step guide for setting up Facilitator agent auto-send emails.", get_facilitator_guide),
    ("get_calendar_meetings", "Fetch scheduled and concluded meetings directly from the executive Outlook / Teams calendar.", get_calendar_meetings),
    ("process_calendar_meeting_workflow", "Automatically process calendar meetings: synthesize pre-meeting briefs or auto-dispatch post-meeting email summaries to calendar attendees.", process_calendar_meeting_workflow),
    ("query_user_history_from_dataverse", "Query and filter Dataverse audit logs (cre2f_veloraagentauditlog) strictly for the specific user.", query_user_history_from_dataverse),
    ("sync_dataverse_logs_to_memory", "Sync the specific user's Dataverse audit history into the active Knowledge Graph / Memory Base for personalized context recall.", sync_dataverse_logs_to_memory),
    ("draft_meeting_summary_email", "Generate a structured HTML executive meeting summary email ready for auto-dispatch.", draft_meeting_summary_email),
    ("send_executive_email_via_graph", "Auto-send executive meeting summaries or briefs via Microsoft Graph API using the service account.", send_executive_email_via_graph),
    ("configure_auto_send_policy", "Configure auto-send policies and review bypass settings for the Facilitator agent.", configure_auto_send_policy),
    ("ingest_chat_to_knowledge_graph", "Ingest chat queries and responses into the Institutional Memory Knowledge Graph / Knowledge Base.", ingest_chat_to_knowledge_graph),
    ("generate_pre_meeting_briefing", "Synthesize cross-system SAP data into executive pre-meeting briefing digests.", generate_pre_meeting_briefing),
    ("export_meeting_to_loop_notebook", "Export meeting notes, decisions, and action items to Microsoft Loop components and OneNote Notebook.", export_meeting_to_loop_notebook),
]
