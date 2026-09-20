"""Facilitator MCP Tools, Calendar Automation, Dataverse User Log Feedback & Knowledge Graph."""
from __future__ import annotations

import base64
import hashlib
import html
import hmac
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import concurrent.futures

from .finance_snapshot_service import generate_finance_snapshot, evaluate_finance_snapshot
from .institutional_memory import ingest_institutional_record, get_vendor_history
from .decision_service import evaluate_vendor_options as _evaluate_vendor_options, get_historical_decision

log = logging.getLogger(__name__)

FACILITATOR_AUTO_SEND_GUIDE = (
    'To make your Facilitator Copilot agent send emails, you must configure a governed workflow '
    'using Microsoft Copilot Studio with mandatory human-in-the-loop confirmation.\n'
    'Here is how to set up and configure the approved email dispatch capability.\n'
    '🛠️ Step 1: Add the Action Tool\n'
    'Open your agent inside Microsoft Copilot Studio.\n'
    'Navigate to the Actions (or Tools) tab from the left menu.\n'
    'Click Add an action.\n'
    'Select the Send an email (V2) action from the Office 365 Outlook connector.\n'
    '📋 Step 2: Configure the Input Parameters\n'
    'Map the preview fields so the executive can review before sending:\n'
    'To: Map this to the verified attendee email variable.\n'
    'Subject: Set a structured subject (e.g., Executive Meeting Summary: [Topic]).\n'
    'Body: Map this to the AI-generated summary draft for human confirmation.\n'
    '⚡ Step 3: Enforce Human Confirmation\n'
    'To ensure executive control and prevent unintended email dispatch:\n'
    'Ensure the "Review before sending" option is strictly TURNED ON.\n'
    'The agent presents an Adaptive Card preview with explicit Send / Cancel action buttons.\n'
    'No automated background email dispatch is permitted without executive preview and confirmation.\n'
)

try:
    from dotenv import load_dotenv
    _fac_env = Path(__file__).resolve().parent.parent / ".env"
    if _fac_env.exists():
        load_dotenv(_fac_env)
    else:
        load_dotenv()
except Exception:
    pass

ENTRA_TENANT_ID = os.environ.get('ENTRA_TENANT_ID') or os.environ.get('AZURE_TENANT_ID') or '7d167021-f5e9-4331-9b75-d44d55a1ce9b'
ENTRA_CLIENT_ID = os.environ.get('ENTRA_CLIENT_ID') or os.environ.get('AZURE_CLIENT_ID') or 'c659609b-76db-49b1-8470-3205a6c35ecb'
ENTRA_CLIENT_SECRET = os.environ.get('ENTRA_CLIENT_SECRET') or os.environ.get('AZURE_CLIENT_SECRET') or ''
SVC_SENDER_EMAIL = os.environ.get('SVC_SENDER_EMAIL') or os.environ.get('M365_USER_EMAIL') or 'svc_aiagent@velora.ae'

_DEFAULT_FACILITATOR_DIR = (
    os.environ.get('AZURE_STORAGE_MOUNT_PATH')
    or os.environ.get('VELORA_STATE_DIR')
    or str(Path.home() / '.velora' / 'facilitator_store')
)
FACILITATOR_STORAGE_DIR = Path(os.environ.get('FACILITATOR_STORAGE_DIR', _DEFAULT_FACILITATOR_DIR))

# Configurable Recipient Policy
DEFAULT_ALLOWED_DOMAINS = {"velora.ae", "etihadairp.ae", "microsoft.com"}


def get_allowed_recipient_domains() -> set[str]:
    raw = os.environ.get("ALLOWED_RECIPIENT_DOMAINS", "")
    if raw:
        return {d.strip().lower() for d in raw.split(",") if d.strip()}
    return DEFAULT_ALLOWED_DOMAINS


def validate_recipient_policy(recipients: List[str]) -> Tuple[bool, List[str]]:
    """Validate recipients against authorized domain policy."""
    allowed_domains = get_allowed_recipient_domains()
    violations = []
    for r in recipients:
        r_clean = r.strip().lower()
        if "@" not in r_clean:
            violations.append(f"Invalid email: '{r}'")
            continue
        domain = r_clean.split("@")[-1]
        if domain not in allowed_domains:
            violations.append(f"Recipient domain '{domain}' not in approved domain policy ({allowed_domains})")
    return len(violations) == 0, violations


def _load_durable_jsonl(filename: str) -> List[Dict[str, Any]]:
    path = FACILITATOR_STORAGE_DIR / filename
    if not path.exists():
        return []
    records = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        pass
    return records


def _append_durable_jsonl(filename: str, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        FACILITATOR_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        path = FACILITATOR_STORAGE_DIR / filename
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record) + '\n')
        return {'status': 'COMMITTED', 'path': str(path)}
    except Exception:
        return None


_KNOWLEDGE_GRAPH: List[Dict[str, Any]] = _load_durable_jsonl('knowledge_graph.jsonl')
_LOOP_NOTEBOOK_RECORDS: List[Dict[str, Any]] = _load_durable_jsonl('loop_records.jsonl')


def seed_test_facilitator_data() -> None:
    """Reset / seed test data for test fixture isolation."""
    global _KNOWLEDGE_GRAPH, _LOOP_NOTEBOOK_RECORDS
    _KNOWLEDGE_GRAPH = []
    _LOOP_NOTEBOOK_RECORDS = []


def query_user_history_from_dataverse(user_email: str, limit: int = 10, filter_operation: Optional[str] = None) -> Dict[str, Any]:
    return {
        'status': 'SOURCE_UNAVAILABLE',
        'message': 'This operation requires a verified live integration. No generated business facts or destination links are returned.',
        'source': None,
    }


def sync_dataverse_logs_to_memory(user_email: str, limit: int = 5) -> Dict[str, Any]:
    return {
        'status': 'SOURCE_UNAVAILABLE',
        'message': 'This operation requires a verified live integration. No generated business facts or destination links are returned.',
        'source': None,
    }


def get_facilitator_guide() -> Dict[str, Any]:
    """Retrieve the official step-by-step Facilitator Copilot auto-send email and meeting workflow setup guide."""
    return {
        'title': 'Facilitator Copilot Auto-Send Email Configuration Guide',
        'content': FACILITATOR_AUTO_SEND_GUIDE,
        'steps': [
            {'step': 1, 'title': 'Add the Automation Tool', 'action': 'Add Send an email (V2) action from Office 365 Outlook connector or Power Automate workflow.'},
            {'step': 2, 'title': 'Configure Input Parameters', 'action': 'Map To (attendees), Subject (Meeting Summary: [Topic]), and Body (AI summary text).'},
            {'step': 3, 'title': 'Trigger the Email Automatically', 'action': "Set Pre-fill / Auto-execute to active and turn off 'Review before sending' for instant dispatch."},
        ],
        'references': [
            'https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/procurement-agent-supplier-com-setup',
            'https://www.youtube.com/watch?v=HJj8STkKj2k',
        ],
    }


def get_calendar_meetings(user_email: Optional[str] = None, timeframe: str = 'today', filter_subject: Optional[str] = None) -> Dict[str, Any]:
    return {
        'status': 'SOURCE_UNAVAILABLE',
        'message': 'This operation requires a verified live integration. No generated business facts or destination links are returned.',
        'source': None,
    }


def process_calendar_meeting_workflow(
    meeting_subject: Optional[str] = None,
    phase: str = 'POST_MEETING',
    meeting_id: Optional[str] = None,
    notes: Optional[str] = None,
    key_decisions: Optional[List[str]] = None,
    action_items: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    return {
        'status': 'SOURCE_UNAVAILABLE',
        'message': 'This operation requires a verified live integration. No generated business facts or destination links are returned.',
        'source': None,
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
    record_id = hashlib.sha256(f'{chat_id}:{user_query}:{now_iso}'.encode('utf-8')).hexdigest()[:16]
    node = {
        'node_id': f'KG-NODE-{record_id}',
        'chat_id': chat_id,
        'timestamp': now_iso,
        'user_query': user_query,
        'agent_response': agent_response,
        'topics': topics or ['General Analytics'],
        'entities': entities or [],
        'decisions_captured': decisions_captured or [],
        'source_systems': source_systems or ['SuccessFactors', 'S4HANA', 'SAC'],
        'governance': {
            'searchable_by': ['Executives', 'Successors'],
            'data_classification': 'CONFIDENTIAL',
            'retained_as_institutional_memory': True,
        },
    }
    _KNOWLEDGE_GRAPH.append(node)
    _append_durable_jsonl('knowledge_graph.jsonl', node)
    return {
        'status': 'INGESTED_TO_KNOWLEDGE_GRAPH',
        'node_id': node['node_id'],
        'total_indexed_nodes': len(_KNOWLEDGE_GRAPH),
        'topics_indexed': node['topics'],
        'summary': 'Chat interaction successfully indexed into Institutional Memory Knowledge Base.',
    }


def generate_pre_meeting_briefing(
    meeting_title: str,
    attendees: List[str],
    meeting_date: Optional[str] = None,
    focus_areas: Optional[List[str]] = None,
    include_sap_connectors: bool = True,
) -> Dict[str, Any]:
    return {
        'status': 'SOURCE_UNAVAILABLE',
        'message': 'This operation requires a verified live integration. No generated business facts or destination links are returned.',
        'source': None,
    }


def export_meeting_to_loop_notebook(
    meeting_title: str,
    attendees: List[str],
    summary: str,
    key_decisions: List[str],
    action_items: List[Dict[str, str]],
    target_storage: str = 'Microsoft Loop & OneNote Notebook',
) -> Dict[str, Any]:
    return {
        'status': 'SOURCE_UNAVAILABLE',
        'message': 'This operation requires a verified live integration. No generated business facts or destination links are returned.',
        'source': None,
    }


def send_executive_email_via_graph(
    to_recipients: List[str],
    subject: str,
    body_html: str,
    cc_recipients: Optional[List[str]] = None,
    confirmation_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Send executive email via Microsoft Graph API with recipient policy check and confirmation governance."""
    # 1. Recipient Policy Check
    all_recipients = to_recipients + (cc_recipients or [])
    policy_ok, violations = validate_recipient_policy(all_recipients)
    if not policy_ok:
        return {
            'status': 'RECIPIENT_POLICY_VIOLATION',
            'message': f'Email dispatch blocked by recipient policy: {", ".join(violations)}',
            'violations': violations,
        }

    # 2. Confirmation Check: Governed writes require confirmed approval
    require_confirmation = os.getenv("REQUIRE_GOVERNED_WRITE_CONFIRMATION", "true").lower() in ("true", "1")
    if require_confirmation and not confirmation_token:
        return {
            'status': 'APPROVAL_REQUIRED',
            'message': 'Executive email dispatch requires verified confirmation token.',
            'to': to_recipients,
            'subject': subject,
        }

    # 3. Dispatch via Graph API
    try:
        token_url = f'https://login.microsoftonline.com/{ENTRA_TENANT_ID}/oauth2/v2.0/token'
        token_data = (
            f'client_id={ENTRA_CLIENT_ID}&scope=https://graph.microsoft.com/.default&client_secret={ENTRA_CLIENT_SECRET}&grant_type=client_credentials'
        ).encode('utf-8')
        token_req = urllib.request.Request(token_url, data=token_data, headers={'Content-Type': 'application/x-www-form-urlencoded'})
        with urllib.request.urlopen(token_req, timeout=10) as token_resp:
            token_obj = json.loads(token_resp.read().decode('utf-8'))
            access_token = token_obj['access_token']

        send_url = f'https://graph.microsoft.com/v1.0/users/{SVC_SENDER_EMAIL}/sendMail'
        message_payload = {
            'message': {
                'subject': subject,
                'body': {'contentType': 'HTML', 'content': body_html},
                'toRecipients': [{'emailAddress': {'address': addr.strip()}} for addr in to_recipients],
                'ccRecipients': [{'emailAddress': {'address': addr.strip()}} for addr in cc_recipients or []],
            },
            'saveToSentItems': 'true',
        }
        req = urllib.request.Request(
            send_url,
            data=json.dumps(message_payload).encode('utf-8'),
            headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            status_code = resp.status
            request_id = resp.headers.get('request-id') if hasattr(resp, 'headers') and resp.headers else f'GRAPH-REQ-{int(time.time() * 1000)}'

        return {
            'status': 'EMAIL_SENT',
            'sender': SVC_SENDER_EMAIL,
            'to': to_recipients,
            'cc': cc_recipients or [],
            'subject': subject,
            'message_id': None,
            'web_link': None,
            'requestId': request_id,
            'graph_http_status': status_code,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'delivery_mode': 'MICROSOFT_GRAPH_LIVE',
        }
    except urllib.error.HTTPError as he:
        err_body = ''
        try:
            err_body = he.read().decode('utf-8')
        except Exception:
            pass
        log.error(f"Graph API sendMail error ({he.code}): {he.reason}. Returning truthful failure receipt.")
        return {
            'status': 'FAILED',
            'sender': SVC_SENDER_EMAIL,
            'to': to_recipients,
            'cc': cc_recipients or [],
            'subject': subject,
            'message_id': None,
            'web_link': None,
            'graph_http_status': he.code,
            'graph_error': he.reason,
            'graph_response': err_body,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'delivery_mode': 'MICROSOFT_GRAPH_LIVE',
            'error': f'Microsoft Graph sendMail failed HTTP {he.code}: {he.reason}',
        }
    except Exception as e:
        log.error(f"Graph API sendMail failed: {e}. Returning truthful failure receipt.")
        return {
            'status': 'FAILED',
            'sender': SVC_SENDER_EMAIL,
            'to': to_recipients,
            'cc': cc_recipients or [],
            'subject': subject,
            'message_id': None,
            'web_link': None,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'delivery_mode': 'MICROSOFT_GRAPH_LIVE',
            'error': str(e),
        }


def draft_meeting_summary_email(
    topic: str,
    attendees: List[str],
    key_decisions: List[str],
    action_items: List[Dict[str, str]],
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Draft an executive meeting summary email with strict HTML escaping to prevent prompt/HTML injection."""
    escaped_topic = html.escape(topic)
    escaped_attendees = [html.escape(a) for a in attendees]
    recipients = ', '.join(escaped_attendees)
    
    decisions_html = ''.join((f'<li>{html.escape(str(d))}</li>' for d in key_decisions))
    
    actions_html = ''.join((
        f"<li><strong>{html.escape(str(item.get('task', '')))}</strong> — Owner: <em>{html.escape(str(item.get('owner', 'Unassigned')))}</em> (Due: {html.escape(str(item.get('due', 'TBD')))})</li>"
        for item in action_items
    ))
    
    now_str = datetime.now(timezone.utc).strftime('%B %d, %Y')
    subject = f'Executive Meeting Summary: {escaped_topic} - {now_str}'
    
    body_html = (
        f'\n    <h2>Meeting Summary: {escaped_topic}</h2>\n'
        f'    <p><strong>Date:</strong> {now_str}</p>\n'
        f'    <p><strong>Attendees:</strong> {recipients}</p>\n'
        f'    <hr/>\n'
        f'    <h3>Key Decisions</h3>\n'
        f'    <ul>{decisions_html}</ul>\n'
        f'    <h3>Action Items</h3>\n'
        f'    <ul>{actions_html}</ul>\n'
    )
    if notes:
        body_html += f'    <h3>Discussion Notes</h3><p>{html.escape(notes)}</p>'

    return {
        'status': 'ready_for_auto_send',
        'to': recipients,
        'subject': subject,
        'body_html': body_html.strip(),
        'auto_send_eligible': True,
    }


def configure_auto_send_policy(
    agent_name: str = 'Facilitator Copilot',
    require_confirmation: bool = True,
    default_recipients: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Configure auto-send and workflow policies for the Facilitator agent."""
    if not require_confirmation:
        # Strict enforcement: bypassing user review is disallowed in production (WP03, AIDEV-06)
        log.warning("Attempted to configure auto-send policy with require_confirmation=False; forced to True")
        require_confirmation = True

    return {
        'agent': agent_name,
        'policy': {
            'auto_send_enabled': False,  # Direct auto-send without human confirmation is prohibited
            'bypass_user_review': False,  # Review bypass is strictly disabled
            'require_confirmation': True,
            'default_recipients': default_recipients or ['leadership@velora.ae'],
            'trigger_event': 'End_of_Meeting',
            'audit_logging': True,
        },
        'message': 'Facilitator policy configured with mandatory human-in-the-loop confirmation.',
    }


def ingest_vendor_performance_record(
    vendor_id: str,
    vendor_name: str,
    entity_scope: str,
    contract_ref: str,
    period_start: str,
    period_end: str,
    event_type: str,
    severity: str,
    summary: str,
    source_doc_ref: str,
    original_event_date: str,
    details: Optional[str] = None,
    numeric_value: Optional[Decimal | float | str] = None,
    unit: str = "",
    currency: str = "",
    source_hash: Optional[str] = None,
    source_system: str = "S4HANA",
    recorded_by: Optional[str] = None,
    verification_status: str = "VERIFIED",
    access_scope: str = "CORP_PROCUREMENT",
    retention_policy: str = "7_YEARS_STANDARD",
    legal_hold: bool = False,
    tenant_id: str = "velora-tenant",
) -> Dict[str, Any]:
    """Synchronous/async wrapper for MCP tool execution to ingest approved vendor performance record."""
    import asyncio
    coro = ingest_institutional_record(
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        entity_scope=entity_scope,
        contract_ref=contract_ref,
        period_start=period_start,
        period_end=period_end,
        event_type=event_type,
        severity=severity,
        summary=summary,
        source_doc_ref=source_doc_ref,
        original_event_date=original_event_date,
        details=details,
        numeric_value=numeric_value,
        unit=unit,
        currency=currency,
        source_hash=source_hash,
        source_system=source_system,
        recorded_by=recorded_by,
        verification_status=verification_status,
        access_scope=access_scope,
        retention_policy=retention_policy,
        legal_hold=legal_hold,
        tenant_id=tenant_id,
    )
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


def get_vendor_performance_history(
    vendor_id: str,
    tenant_id: str = "velora-tenant",
    caller_entity_scopes: Optional[List[str]] = None,
    caller_roles: Optional[List[str]] = None,
    include_superseded: bool = False,
) -> Dict[str, Any]:
    """Retrieve bounded historical vendor performance profile."""
    return get_vendor_history(
        vendor_id=vendor_id,
        tenant_id=tenant_id,
        caller_entity_scopes=caller_entity_scopes,
        caller_roles=caller_roles,
        include_superseded=include_superseded,
    )


async def evaluate_vendor_options_tool(
    candidates: List[Dict[str, Any]],
    policy_id: str = "POLICY-VENDOR-PROC-V1",
    policy_version: Optional[str] = "1.0.0",
    use_case: str = "VENDOR_SELECTION",
    tenant_id: str = "velora-tenant",
    caller_entity_scopes: Optional[List[str]] = None,
    caller_roles: Optional[List[str]] = None,
    actor_object_id: str = "system-facilitator",
    db_path: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Execute governed, deterministic vendor options evaluation with Decimal scoring."""
    return await _evaluate_vendor_options(
        candidates=candidates,
        policy_id=policy_id,
        policy_version=policy_version,
        use_case=use_case,
        tenant_id=tenant_id,
        caller_entity_scopes=caller_entity_scopes,
        caller_roles=caller_roles,
        actor_object_id=actor_object_id,
        db_path=db_path,
        user_prompt_overrides=kwargs.get("user_prompt_overrides"),
    )


def get_vendor_decision_record(
    decision_id: str,
    tenant_id: str = "velora-tenant",
    version: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve persisted historical vendor decision record without fresh LLM evaluation."""
    return get_historical_decision(
        decision_id=decision_id,
        tenant_id=tenant_id,
        version=version,
        db_path=db_path,
    )


from .audit_export import (
    export_decision_trail as _export_decision_trail,
    verify_decision_manifest as _verify_decision_manifest,
)


def export_decision_trail(
    decision_id: str,
    tenant_id: str = "velora-tenant",
    version: Optional[str] = None,
    format: str = "JSON",
    caller_roles: Optional[List[str]] = None,
    actor_object_id: Optional[str] = None,
    ttl_seconds: int = 3600,
    redacted_fields: Optional[List[str]] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Export decision manifest with cryptographic signature and formula-safe CSV view."""
    roles = caller_roles or []
    if not any(r in ("AUDITOR", "Admin", "Velora_Admin", "GlobalAdmin") for r in roles):
        raise PermissionError("Exporting decision trail requires AUDITOR or Administrator role.")
    return _export_decision_trail(
        decision_id=decision_id,
        tenant_id=tenant_id,
        version=version,
        export_format=format,
        caller_roles=roles,
        actor_object_id=actor_object_id or "unspecified",
        ttl_seconds=ttl_seconds,
        redacted_fields=redacted_fields,
        db_path=db_path,
    )


def verify_decision_manifest(
    manifest: Dict[str, Any],
    signing_key: Optional[str] = None,
    declared_redactions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Verify cryptographic signature, Merkle root, and replay calculations from input snapshot."""
    is_valid, status, details = _verify_decision_manifest(
        manifest_data=manifest,
        signing_key=signing_key,
        declared_redactions=declared_redactions,
    )
    return {
        "isValid": is_valid,
        "statusCode": status,
        "details": details,
    }


TOOL_SPECS = [
    ('get_facilitator_guide', 'Retrieve the complete step-by-step guide for setting up Facilitator agent auto-send emails.', get_facilitator_guide),
    ('get_calendar_meetings', 'Fetch scheduled and concluded meetings directly from the executive Outlook / Teams calendar.', get_calendar_meetings),
    ('process_calendar_meeting_workflow', 'Automatically process calendar meetings: synthesize pre-meeting briefs or auto-dispatch post-meeting email summaries to calendar attendees.', process_calendar_meeting_workflow),
    ('query_user_history_from_dataverse', 'Query and filter Dataverse audit logs (cre2f_veloraagentauditlog) strictly for the specific user.', query_user_history_from_dataverse),
    ('sync_dataverse_logs_to_memory', "Sync the specific user's Dataverse audit history into the active Knowledge Graph / Memory Base for personalized context recall.", sync_dataverse_logs_to_memory),
    ('draft_meeting_summary_email', 'Generate a structured HTML executive meeting summary email ready for auto-dispatch.', draft_meeting_summary_email),
    ('send_executive_email_via_graph', 'Auto-send executive meeting summaries or briefs via Microsoft Graph API using the service account.', send_executive_email_via_graph),
    ('configure_auto_send_policy', 'Configure auto-send policies and review bypass settings for the Facilitator agent.', configure_auto_send_policy),
    ('ingest_chat_to_knowledge_graph', 'Ingest chat queries and responses into the Institutional Memory Knowledge Graph / Knowledge Base.', ingest_chat_to_knowledge_graph),
    ('generate_pre_meeting_briefing', 'Synthesize cross-system SAP data into executive pre-meeting briefing digests.', generate_pre_meeting_briefing),
    ('export_meeting_to_loop_notebook', 'Export meeting notes, decisions, and action items to Microsoft Loop components and OneNote Notebook.', export_meeting_to_loop_notebook),
    ('generate_finance_snapshot', 'Generate verified KPI snapshot from authoritative SAP S/4HANA financial records.', generate_finance_snapshot),
    ('evaluate_finance_snapshot', 'Generate and evaluate verified finance snapshot through Productivity recommendation engine.', evaluate_finance_snapshot),
    ('ingest_vendor_performance_record', 'Ingest approved vendor performance record with provenance, source hash, and subsidiary scoping.', ingest_vendor_performance_record),
    ('get_vendor_performance_history', 'Retrieve bounded vendor performance history with scope enforcement, gap analysis, and mandatory caveats.', get_vendor_performance_history),
    ('evaluate_vendor_options', 'Evaluate vendor proposals against approved policy, comparability criteria, and institutional history.', evaluate_vendor_options_tool),
    ('get_vendor_decision_record', 'Retrieve persisted historical vendor decision record without fresh LLM evaluation.', get_vendor_decision_record),
    ('export_decision_trail', 'Export decision audit manifest and formula-safe spreadsheet under ADAA retention policy.', export_decision_trail),
    ('verify_decision_manifest', 'Verify cryptographic signature, root hash, and mathematical trace of a decision manifest.', verify_decision_manifest),
]


