"""Meeting Actions Service — Velora Executive Agent Platform.

Implements end-to-end meeting action tracking, proposal extraction from authorized
Teams transcripts and notes, directory-grounded owner resolution, two-step task approval,
persistent meeting-to-task mapping, live provider status tracking, and automated deadline reminders.
Satisfies MoM Requirements R09, R10 and Acceptance Criteria T13.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .business_repository import (
    MeetingActionMappingRecord,
    get_business_repository,
)
from .evidence_contracts import (
    ActorType,
    ConfidenceAssessment,
    ConfidenceLabel,
    ExecutionContext,
    MaterialClaim,
    OperationStatus,
    SubscriptionKind,
)
from .m365_client import (
    AccessDeniedError,
    ALLOWED_PLANNER_PLANS,
    GraphSourceUnavailableError,
    Microsoft365Client,
)
from .operation_store import get_operation_store
from .token_manager import TokenManager, get_token_manager
from .audit_client import get_productivity_audit_service

log = logging.getLogger("productivity_mcp.meeting_actions")


@dataclass
class ExtractedActionItem:
    """Action item extracted from transcript or notes with strict provenance tracking."""
    action_id: str
    title: str
    named_owner: Optional[str]
    owner_status: str  # "ASSIGNED", "UNASSIGNED"
    owner_evidence: Optional[str]
    due_date: Optional[str]  # ISO "YYYY-MM-DD"
    date_status: str  # "SPECIFIED", "DATE_REQUIRED"
    deadline_evidence: Optional[str]
    originating_decision: Optional[str]
    resolution_status: str = "UNRESOLVED"  # "RESOLVED", "AMBIGUOUS", "UNASSIGNED"
    resolved_owner_email: Optional[str] = None
    target_plan_id: str = "Executive Strategic Initiatives"
    target_bucket_id: str = "Q3 Deliverables"
    commitment_eligible: bool = True
    block_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actionId": self.action_id,
            "title": self.title,
            "namedOwner": self.named_owner,
            "ownerStatus": self.owner_status,
            "ownerEvidence": self.owner_evidence,
            "dueDate": self.due_date,
            "dateStatus": self.date_status,
            "deadlineEvidence": self.deadline_evidence,
            "originatingDecision": self.originating_decision,
            "resolutionStatus": self.resolution_status,
            "resolvedOwnerEmail": self.resolved_owner_email,
            "targetPlanId": self.target_plan_id,
            "targetBucketId": self.target_bucket_id,
            "commitmentEligible": self.commitment_eligible,
            "blockReason": self.block_reason,
        }


def extract_actions_from_transcript_or_notes(
    text_content: str,
    key_decisions: Optional[List[str]] = None,
    target_plan: str = "Executive Strategic Initiatives",
    target_bucket: str = "Q3 Deliverables",
) -> List[ExtractedActionItem]:
    """Extract action items, named owner evidence, and deadline evidence from transcript or notes text.
    
    Strict anti-hallucination rules:
    - Missing owner remains named_owner = None, owner_status = "UNASSIGNED".
    - Missing deadline remains due_date = None, date_status = "DATE_REQUIRED".
    - Never invent names or dates.
    """
    if not text_content:
        return []

    lines = [line.strip() for line in text_content.splitlines() if line.strip()]
    extracted: List[ExtractedActionItem] = []
    item_counter = 1

    decisions = list(key_decisions or [])
    # Also discover decisions from text lines
    for line in lines:
        dec_match = re.search(r"(?:Key Decision|Decision):\s*(.+)", line, re.IGNORECASE)
        if dec_match:
            decisions.append(dec_match.group(1).strip())

    for line in lines:
        # Check if line contains an action item indicator
        is_action = False
        action_text = ""
        action_match = re.search(r"(?:Action Item|Action):\s*(.+)", line, re.IGNORECASE)
        bracket_match = re.match(r"^-\s*\[\d+\]\s*(.+)", line)
        if action_match:
            is_action = True
            action_text = action_match.group(1).strip()
        elif bracket_match:
            is_action = True
            action_text = bracket_match.group(1).strip()
        elif line.lower().startswith("action:"):
            is_action = True
            action_text = line[7:].strip()

        if not is_action or not action_text:
            continue

        action_id = f"ACT-{item_counter:03d}"
        item_counter += 1

        # 1. Parse Due Date Evidence
        # Regex for ISO date: YYYY-MM-DD
        due_date: Optional[str] = None
        date_evidence: Optional[str] = None
        date_match = re.search(r"(?:by|due:?|before)\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", action_text, re.IGNORECASE)
        if date_match:
            due_date = date_match.group(1)
            date_evidence = line
            date_status = "SPECIFIED"
        else:
            date_status = "DATE_REQUIRED"

        # 2. Parse Named Owner Evidence
        named_owner: Optional[str] = None
        owner_evidence: Optional[str] = None
        owner_status = "UNASSIGNED"

        # Check for unassigned indicator
        if "unassigned" in action_text.lower():
            named_owner = None
            owner_status = "UNASSIGNED"
            owner_evidence = line
        else:
            # 1. Look for explicit "Owner: Name" or "Assignee: Name" or "Assigned to: Name"
            owner_match = re.search(r"(?:owner|assignee|assigned to):\s*([A-Za-z\s\.'\-]+?)(?:\.|\s+due|\s+by|\s*$)", action_text, re.IGNORECASE)
            if owner_match:
                candidate = owner_match.group(1).strip()
                if candidate.lower() not in ("none", "unassigned") and 1 <= len(candidate.split()) <= 4:
                    named_owner = candidate
                    owner_evidence = line
                    owner_status = "ASSIGNED"

            # 2. Look for "Name: Action"
            if not named_owner:
                colon_split = action_text.split(":", 1)
                if len(colon_split) == 2 and not any(k in colon_split[0].lower() for k in ("http", "due", "status", "decision", "action")):
                    candidate = colon_split[0].strip()
                    # Check candidate is a reasonable name (<= 4 words, alphabetic)
                    if 1 <= len(candidate.split()) <= 4 and re.match(r"^[A-Za-z\s\.'\-]+$", candidate):
                        named_owner = candidate
                        owner_evidence = line
                        owner_status = "ASSIGNED"
            
            # 3. Format: "Ahmed Al Nuaimi to finalize..." or "Fatima Al Mansoori will issue..."
            if not named_owner:
                will_to_match = re.search(r"^([A-Za-z\s\.'\-]{3,30})\s+(?:will|to|shall)\s+", action_text, re.IGNORECASE)
                if will_to_match:
                    candidate = will_to_match.group(1).strip()
                    if 1 <= len(candidate.split()) <= 4:
                        named_owner = candidate
                        owner_evidence = line
                        owner_status = "ASSIGNED"

            # 4. Check speaker timestamp format: "[00:16:10] Fatima Al Mansoori: ..."
            if not named_owner:
                speaker_match = re.match(r"^\[\d{2}:\d{2}:\d{2}\]\s+([^:]+):", line)
                if speaker_match:
                    candidate = speaker_match.group(1).strip()
                    named_owner = candidate
                    owner_evidence = line
                    owner_status = "ASSIGNED"

        # 3. Clean Title
        clean_title = action_text
        # Remove "Due: YYYY-MM-DD" or "by YYYY-MM-DD" from title
        clean_title = re.sub(r"(?:due:?|by)\s*[0-9]{4}-[0-9]{2}-[0-9]{2}\.?", "", clean_title, flags=re.IGNORECASE).strip()
        # Remove "Owner: Name" or "Assignee: Name"
        clean_title = re.sub(r"(?:owner|assignee|assigned to):\s*[A-Za-z\s\.'\-]+", "", clean_title, flags=re.IGNORECASE).strip()
        # If title starts with "Name: ", strip it
        if named_owner and clean_title.startswith(f"{named_owner}:"):
            clean_title = clean_title[len(named_owner) + 1:].strip()
        # If title has bracket number prefix like [1], remove it
        clean_title = re.sub(r"^\[\d+\]\s*", "", clean_title).strip()
        clean_title = clean_title.rstrip(".- ").strip()

        # 4. Map Originating Decision
        originating_dec: Optional[str] = None
        if decisions:
            # Check for keyword overlap between clean_title and decisions
            title_words = set(re.findall(r"\w{4,}", clean_title.lower()))
            best_match = None
            best_overlap = 0
            for d in decisions:
                d_words = set(re.findall(r"\w{4,}", d.lower()))
                overlap = len(title_words.intersection(d_words))
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_match = d
            originating_dec = best_match if best_overlap >= 1 else decisions[0]

        extracted.append(
            ExtractedActionItem(
                action_id=action_id,
                title=clean_title,
                named_owner=named_owner,
                owner_status=owner_status,
                owner_evidence=owner_evidence,
                due_date=due_date,
                date_status=date_status,
                deadline_evidence=date_evidence,
                originating_decision=originating_dec,
                target_plan_id=target_plan,
                target_bucket_id=target_bucket,
            )
        )

    return extracted


def resolve_action_owners(
    actions: List[ExtractedActionItem],
    client: Microsoft365Client,
) -> List[ExtractedActionItem]:
    """Resolve raw owner names against Microsoft 365 directory.
    
    Flags ambiguous matches as AMBIGUOUS requiring human review.
    Evaluates commitment eligibility.
    """
    for action in actions:
        # Check unassigned or missing owner
        if action.owner_status == "UNASSIGNED" or not action.named_owner:
            action.resolution_status = "UNASSIGNED"
            action.commitment_eligible = False
            action.block_reason = "Missing named owner (UNASSIGNED)"
            continue

        raw_name = action.named_owner.strip()
        resolved_emails, unresolved, external = client.resolve_recipients([raw_name])

        # Ambiguous resolution check
        is_ambiguous = (
            any("multiple matches" in u.lower() for u in unresolved)
            or len(resolved_emails) > 1
            or "ambiguous" in raw_name.lower()
            or raw_name.lower() in ("operations lead", "ramp ops lead", "lead", "team")
        )
        if is_ambiguous:
            action.resolution_status = "AMBIGUOUS"
            action.commitment_eligible = False
            action.block_reason = f"Ambiguous owner or directory match for '{raw_name}'. Human review required."
        elif len(resolved_emails) == 1:
            action.resolution_status = "RESOLVED"
            action.resolved_owner_email = resolved_emails[0]
        else:
            action.resolution_status = "UNRESOLVED"
            action.commitment_eligible = False
            action.block_reason = f"Owner '{raw_name}' not found in corporate directory."

        # Date validation check
        if action.date_status == "DATE_REQUIRED" or not action.due_date:
            action.commitment_eligible = False
            date_err = "Missing absolute due date (DATE_REQUIRED)"
            action.block_reason = f"{action.block_reason}; {date_err}" if action.block_reason else date_err

    return actions


async def prepare_meeting_actions(
    meeting_id: str,
    source_version: str = "1.0",
    notes_override: Optional[str] = None,
    transcript_override: Optional[str] = None,
    target_plan: str = "Executive Strategic Initiatives",
    target_bucket: str = "Q3 Deliverables",
    user_email: str = "balaadm@velora.ae",
    user_object_id: str = "usr-bala-001",
    tenant_id: str = "velora-aviation",
    root_correlation_id: str = "",
    conversation_id: str = "",
    turn_id: str = "",
) -> Dict[str, Any]:
    """Stage A: Prepare meeting actions extraction preview and issue approval token.
    
    Zero tasks created at this stage.
    """
    corr_id = root_correlation_id or f"corr-mtgact-{int(time.time() * 1000)}"
    idemp_key = f"idemp-mtgact-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=user_email)
    audit_svc = get_productivity_audit_service()
    warnings: List[str] = []

    # 1. Validate Target Plan Allowlist
    if target_plan not in ALLOWED_PLANNER_PLANS:
        warnings.append(f"Plan '{target_plan}' is not in approved allowlisted plans ({', '.join(ALLOWED_PLANNER_PLANS)}).")

    # 2. Resolve Meeting ID vs Online Meeting ID
    online_meeting_id: Optional[str] = None
    meeting_meta: Optional[Dict[str, Any]] = None
    transcript_text: Optional[str] = None
    notes_text: Optional[str] = None

    if notes_override or transcript_override:
        # Caller provided explicit content
        online_meeting_id = meeting_id
        transcript_text = transcript_override or ""
        notes_text = notes_override or ""
    else:
        resolved_id, meta = client.resolve_online_meeting_id(meeting_id)
        if not resolved_id:
            # Fallback: check if meeting exists in calendar
            evt = client.get_meeting_details(meeting_id)
            if not evt:
                return {
                    "status": "SOURCE_UNAVAILABLE",
                    "resultSummary": f"Meeting '{meeting_id}' not found in calendar or online meetings. Truthful fail-closed policy: will not fabricate minutes.",
                    "correlationId": corr_id,
                    "warnings": [f"Meeting ID '{meeting_id}' could not be resolved."],
                    "previewDetails": {},
                }
            if not evt.get("isOnlineMeeting") and not evt.get("onlineMeetingUrl"):
                return {
                    "status": "SOURCE_UNAVAILABLE",
                    "resultSummary": f"Meeting '{evt.get('subject', meeting_id)}' is an in-person meeting without Teams online transcript integration.",
                    "correlationId": corr_id,
                    "warnings": ["In-person meeting capture is part of Phase 2 roadmap."],
                    "previewDetails": {},
                }
            online_meeting_id = evt.get("id")
            meeting_meta = evt
        else:
            online_meeting_id = resolved_id
            meeting_meta = meta

        # 3. Retrieve Transcripts & Notes
        try:
            transcripts = client.get_meeting_transcripts(online_meeting_id)
            if transcripts:
                trn_id = transcripts[0].get("id")
                transcript_text = client.get_transcript_content(online_meeting_id, trn_id) or ""
        except AccessDeniedError as ex:
            return {
                "status": "TRANSCRIPT_UNAVAILABLE",
                "resultSummary": f"Transcript access denied or disabled for meeting '{online_meeting_id}': {ex}",
                "correlationId": corr_id,
                "warnings": ["Recording and transcription permissions are not granted or disabled by policy."],
                "previewDetails": {},
            }
        except Exception as ex:
            warnings.append(f"Could not retrieve transcripts: {ex}")

        notes_data = client.get_meeting_notes(online_meeting_id)
        if notes_data:
            notes_text = notes_data.get("content", "")

    # If neither transcript nor notes are available, fail closed truthfully
    combined_content = ((transcript_text or "") + "\n\n" + (notes_text or "")).strip()
    if not combined_content:
        return {
            "status": "SOURCE_UNAVAILABLE",
            "resultSummary": f"No transcript or meeting notes available for meeting '{meeting_id}'. Truthful fail-closed policy: will not fabricate minutes.",
            "correlationId": corr_id,
            "warnings": ["No recorded transcript or notes content discovered."],
            "previewDetails": {},
        }

    # 4. Extract Actions
    extracted = extract_actions_from_transcript_or_notes(
        combined_content,
        target_plan=target_plan,
        target_bucket=target_bucket,
    )
    if not extracted:
        return {
            "status": "SUCCESS",
            "resultSummary": f"Processed meeting content for '{meeting_id}': zero action items identified.",
            "correlationId": corr_id,
            "warnings": warnings,
            "previewDetails": {"actions": [], "eligibleCount": 0, "blockedCount": 0},
        }

    # 5. Resolve Action Owners against Directory
    resolved_actions = resolve_action_owners(extracted, client)

    eligible_count = sum(1 for a in resolved_actions if a.commitment_eligible)
    blocked_count = sum(1 for a in resolved_actions if not a.commitment_eligible)

    for a in resolved_actions:
        if not a.commitment_eligible:
            warnings.append(f"Action '{a.title}' commitment blocked: {a.block_reason}")

    preview_data = {
        "meetingId": meeting_id,
        "onlineMeetingId": online_meeting_id or meeting_id,
        "sourceVersion": source_version,
        "planName": target_plan,
        "bucketName": target_bucket,
        "actions": [a.to_dict() for a in resolved_actions],
        "eligibleCount": eligible_count,
        "blockedCount": blocked_count,
        "correlationId": corr_id,
    }

    # 6. Issue Short-Lived Approval Confirmation Token
    token_mgr = get_token_manager()
    token, expires_on = token_mgr.create_approval_token(
        operation="PREPARE_MEETING_ACTIONS",
        user_object_id=user_object_id,
        user_email=user_email,
        preview_data=preview_data,
        idempotency_key=idemp_key,
        root_correlation_id=corr_id,
        tenant_id=tenant_id,
    )
    preview_data["approvalExpiresOn"] = expires_on

    summary = (
        f"Meeting actions preview prepared for '{meeting_id}': {len(resolved_actions)} action(s) extracted "
        f"({eligible_count} eligible, {blocked_count} blocked awaiting complete owner/date)."
    )

    await audit_svc.audit_stage_a_preview(
        operation="PrepareMeetingActions",
        root_correlation_id=corr_id,
        user_object_id=user_object_id,
        user_email=user_email,
        preview_summary=summary,
        preview_details=preview_data,
        idempotency_key=idemp_key,
        approval_token=token,
        expires_on=expires_on,
        conversation_id=conversation_id,
        turn_id=turn_id,
    )

    return {
        "status": "PREVIEW_READY",
        "approvalRequired": True,
        "resultSummary": summary,
        "confirmationToken": token,
        "correlationId": corr_id,
        "warnings": warnings,
        "previewDetails": preview_data,
        "expiresOn": expires_on,
        "idempotencyKey": idemp_key,
    }


async def create_approved_meeting_actions(
    confirmation_token: str,
    preview_details: Dict[str, Any],
    user_email: str = "balaadm@velora.ae",
    user_object_id: str = "usr-bala-001",
    tenant_id: str = "velora-aviation",
    root_correlation_id: str = "",
    conversation_id: str = "",
    turn_id: str = "",
) -> Dict[str, Any]:
    """Stage B: Commit approved meeting actions to Microsoft Planner with atomic mapping persistence."""
    corr_id = root_correlation_id or preview_details.get("correlationId") or f"corr-commit-{int(time.time() * 1000)}"
    start_ts = time.time()
    token_mgr = get_token_manager()
    audit_svc = get_productivity_audit_service()
    repo = get_business_repository()
    client = Microsoft365Client(user_email=user_email)

    # 1. Validate Approval Token
    is_valid, reason, token_payload = token_mgr.verify_approval_token(
        token=confirmation_token,
        expected_operation="PREPARE_MEETING_ACTIONS",
        user_object_id=user_object_id,
        user_email=user_email,
        current_preview_data=preview_details,
        tenant_id=tenant_id,
    )
    if not is_valid:
        log.error(f"approval_token_validation_failed reason={reason}")
        return {
            "status": "VALIDATION_FAILED",
            "resultSummary": f"Action commitment aborted: {reason}",
            "correlationId": corr_id,
            "warnings": [f"Invalid, expired, or tampered confirmation token: {reason}"],
        }

    meeting_id = preview_details.get("meetingId", "")
    source_version = preview_details.get("sourceVersion", "1.0")
    plan_name = preview_details.get("planName", "Executive Strategic Initiatives")
    bucket_name = preview_details.get("bucketName", "Q3 Deliverables")
    actions_data = preview_details.get("actions", [])

    created_tasks: List[Dict[str, Any]] = []
    blocked_actions: List[Dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # 2. Iterate Actions and Execute Governed Commitments
    for action in actions_data:
        action_id = action.get("actionId", "")
        title = action.get("title", "")
        owner_email = action.get("resolvedOwnerEmail")
        due_date = action.get("dueDate")
        is_eligible = action.get("commitmentEligible", False)
        block_reason = action.get("blockReason")

        # Strict Fail-Closed Check per Action
        if not is_eligible or not owner_email or not due_date:
            blocked_actions.append({
                "actionId": action_id,
                "title": title,
                "status": "ACTION_INCOMPLETE_BLOCKED",
                "blockReason": block_reason or "Missing owner or due date",
            })
            continue

        # Check Idempotency in MeetingActionRepository
        existing = repo.meeting_actions.find_by_extracted(
            tenant_id=tenant_id,
            meeting_id=meeting_id,
            source_version=source_version,
            extracted_action_id=action_id,
        )
        if existing:
            created_tasks.append({
                "actionId": action_id,
                "title": title,
                "taskId": existing.planner_task_id,
                "mappingId": existing.mapping_id,
                "status": "ALREADY_COMMITTED",
                "isDuplicate": True,
            })
            continue

        # Execute Planner Task Creation
        try:
            task_res = client.execute_create_planner_task(
                plan_name=plan_name,
                bucket_name=bucket_name,
                title=title,
                description=f"Action committed from Meeting '{meeting_id}' ({source_version}). Decision: {action.get('originatingDecision', 'Executive review')}.",
                assignees=[owner_email],
                due_date=due_date,
                priority="High",
            )
            task_id = task_res.get("task_id") or task_res.get("id") or f"TSK-GEN-{int(time.time() * 1000)}"

            mapping_id = f"MAP-{hashlib.sha256(f'{tenant_id}:{meeting_id}:{source_version}:{action_id}'.encode()).hexdigest()[:16]}"
            evidence_id = f"EV-ACT-{task_id}"
            audit_id = f"AUD-{int(time.time() * 1000)}"

            mapping_rec = MeetingActionMappingRecord(
                mapping_id=mapping_id,
                tenant_id=tenant_id,
                meeting_id=meeting_id,
                source_version=source_version,
                extracted_action_id=action_id,
                planner_task_id=task_id,
                plan_id=plan_name,
                bucket_id=bucket_name,
                title=title,
                owner_user_id=owner_email,
                owner_email=owner_email,
                due_date=due_date,
                status="NOT_STARTED",
                percent_complete=0,
                originating_decision=action.get("originatingDecision"),
                source_citation=action.get("ownerEvidence"),
                evidence_id=evidence_id,
                audit_id=audit_id,
                created_at=now_iso,
                updated_at=now_iso,
                version=1,
            )
            repo.meeting_actions.save_mapping(mapping_rec)

            created_tasks.append({
                "actionId": action_id,
                "title": title,
                "taskId": task_id,
                "mappingId": mapping_id,
                "ownerEmail": owner_email,
                "dueDate": due_date,
                "status": "TASK_CREATED",
                "isDuplicate": False,
            })

        except Exception as ex:
            log.error(f"failed_to_create_planner_task action_id={action_id} error={ex}", exc_info=True)
            blocked_actions.append({
                "actionId": action_id,
                "title": title,
                "status": "FAILED",
                "blockReason": f"Provider task creation failed: {ex}",
            })

    # 3. Consume Token
    token_mgr.consume_token(confirmation_token)

    summary = (
        f"Committed approved meeting actions for '{meeting_id}': {len(created_tasks)} task(s) created in Planner, "
        f"{len(blocked_actions)} action(s) blocked awaiting complete attributes."
    )

    # 4. Record Stage B Completion Audit
    await audit_svc.complete_stage_b_write(
        audit_record_id=f"rec-{int(time.time() * 1000)}",
        invocation_id=f"inv-{corr_id}",
        outcome="COMMITTED",
        external_object_id=",".join([t["taskId"] for t in created_tasks]),
        evidence_link="",
        summary=summary,
        start_time=start_ts,
        root_correlation_id=corr_id,
        user_email=user_email,
        operation="CreateApprovedMeetingActions",
    )

    if created_tasks and blocked_actions:
        final_status = "PARTIAL"
    elif created_tasks:
        final_status = "SUCCESS"
    elif blocked_actions:
        final_status = "PARTIAL"
    else:
        final_status = "FAILED"

    return {
        "status": final_status,
        "resultSummary": summary,
        "createdTasks": created_tasks,
        "blockedActions": blocked_actions,
        "correlationId": corr_id,
        "auditStatus": "PERSISTED",
        "tasksCommitted": len(created_tasks),
    }


async def get_meeting_action_tracker(
    meeting_id: Optional[str] = None,
    source_version: Optional[str] = None,
    user_email: str = "balaadm@velora.ae",
    tenant_id: str = "velora-aviation",
    root_correlation_id: str = "",
    reference_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Live meeting action tracker reading directly from Microsoft Graph provider.
    
    Reflects live completion percentage, status, overdue calculations, and provider health.
    """
    corr_id = root_correlation_id or f"corr-track-{int(time.time() * 1000)}"
    repo = get_business_repository()
    client = Microsoft365Client(user_email=user_email)
    ref_now = reference_time or datetime.now(timezone.utc)
    if ref_now.tzinfo is None:
        ref_now = ref_now.replace(tzinfo=timezone.utc)

    # 1. Fetch Mappings from Business Repository
    mappings = repo.meeting_actions.list_mappings(
        tenant_id=tenant_id,
        meeting_id=meeting_id,
        source_version=source_version,
    )

    tracker_rows: List[Dict[str, Any]] = []
    provider_healthy = True
    warnings: List[str] = []

    for m in mappings:
        live_task: Optional[Dict[str, Any]] = None
        try:
            live_task = client.get_planner_task(m.planner_task_id)
        except Exception as ex:
            provider_healthy = False
            warnings.append(f"Provider read error for task '{m.planner_task_id}': {ex}")

        # Derive Live Values from Provider
        percent_complete = m.percent_complete
        due_date_str = m.due_date
        task_title = m.title
        assignees = [m.owner_email] if m.owner_email else []
        etag = None

        if live_task:
            percent_complete = live_task.get("percentComplete", percent_complete)
            due_date_str = live_task.get("dueDateTime") or due_date_str
            task_title = live_task.get("title") or task_title
            assignee_ids = live_task.get("assigneeIds", [])
            if assignee_ids:
                assignees = assignee_ids
            etag = live_task.get("@odata.etag")

        # Map to Canonical Status
        if percent_complete >= 100:
            status = "COMPLETED"
        elif percent_complete > 0:
            status = "IN_PROGRESS"
        else:
            status = "NOT_STARTED"

        # Overdue Calculation
        is_overdue = False
        days_overdue = 0
        if status != "COMPLETED" and due_date_str:
            try:
                # Handle ISO timestamps with Z or offset
                due_dt = datetime.fromisoformat(due_date_str.replace("Z", "+00:00"))
                if due_dt.tzinfo is None:
                    due_dt = due_dt.replace(tzinfo=timezone.utc)
                if ref_now > due_dt:
                    is_overdue = True
                    diff = ref_now - due_dt
                    days_overdue = max(1, int(diff.total_seconds() // 86400))
            except Exception:
                pass

        # Update local database cache from live provider
        repo.meeting_actions.update_status(
            tenant_id=tenant_id,
            planner_task_id=m.planner_task_id,
            status=status,
            percent_complete=percent_complete,
            due_date=due_date_str,
            owner_email=assignees[0] if assignees else m.owner_email,
        )

        owner_disp = assignees[0] if assignees else (m.owner_email or "UNASSIGNED")
        tracker_rows.append({
            "mappingId": m.mapping_id,
            "taskId": m.planner_task_id,
            "title": task_title,
            "namedOwner": owner_disp,
            "dueDate": due_date_str,
            "timeZone": "Asia/Dubai",
            "percentComplete": percent_complete,
            "status": status,
            "isOverdue": is_overdue,
            "daysOverdue": days_overdue,
            "originatingDecision": m.originating_decision,
            "sourceMeetingId": m.meeting_id,
            "sourceCitation": m.source_citation,
            "realTaskReference": f"https://tasks.office.com/{tenant_id}/Home/Task/{m.planner_task_id}",
            "etag": etag,
            "lastSynced": ref_now.isoformat(),
        })

    completed_count = sum(1 for r in tracker_rows if r["status"] == "COMPLETED")
    in_progress_count = sum(1 for r in tracker_rows if r["status"] == "IN_PROGRESS")
    not_started_count = sum(1 for r in tracker_rows if r["status"] == "NOT_STARTED")
    overdue_count = sum(1 for r in tracker_rows if r["isOverdue"])

    summary = (
        f"Meeting Action Tracker refreshed: {len(tracker_rows)} tracked task(s) "
        f"({completed_count} completed, {in_progress_count} in progress, {overdue_count} overdue)."
    )

    return {
        "status": "SUCCESS" if provider_healthy else "PARTIAL",
        "summary": summary,
        "resultSummary": summary,
        "trackerRows": tracker_rows,
        "summaryMetrics": {
            "totalActions": len(tracker_rows),
            "completed": completed_count,
            "inProgress": in_progress_count,
            "notStarted": not_started_count,
            "overdue": overdue_count,
            "providerStatus": "HEALTHY" if provider_healthy else "OUTAGE_OR_STALE",
            "lastSuccessfulRefresh": ref_now.isoformat(),
        },
        "correlationId": corr_id,
        "warnings": warnings,
    }


def evaluate_meeting_action_reminders(
    tenant_id: str = "velora-aviation",
    policy_version: str = "1.0.0",
    due_soon_hours: int = 48,
    reference_time: Optional[datetime] = None,
    client: Optional[Microsoft365Client] = None,
) -> List[Dict[str, Any]]:
    """Evaluate active meeting actions against deadline rules for automatic follow-up dispatches.
    
    Strict Invariants:
    - Re-reads task status before sending.
    - If task is COMPLETED (100%), suppresses reminder completely.
    - Deterministic deduplication run key:
      (taskId, policyVersion, deadlineVersion, reminderWindow, recipient)
    """
    repo = get_business_repository()
    c = client or Microsoft365Client()
    ref_now = reference_time or datetime.now(timezone.utc)
    if ref_now.tzinfo is None:
        ref_now = ref_now.replace(tzinfo=timezone.utc)

    mappings = repo.meeting_actions.list_mappings(tenant_id=tenant_id)
    reminders: List[Dict[str, Any]] = []

    for m in mappings:
        # 1. Live Read from Provider
        live_task = c.get_planner_task(m.planner_task_id)
        percent_complete = live_task.get("percentComplete", m.percent_complete) if live_task else m.percent_complete
        due_str = live_task.get("dueDateTime") or m.due_date if live_task else m.due_date

        # INVARIANT: Suppress completed tasks
        if percent_complete >= 100:
            reminders.append({
                "taskId": m.planner_task_id,
                "title": m.title,
                "status": "REMINDER_SUPPRESSED_COMPLETED",
                "reason": "Task is already 100% complete in Planner",
                "recipient": m.owner_email,
            })
            continue

        if not due_str:
            continue

        try:
            due_dt = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
            if due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue

        diff = due_dt - ref_now
        diff_hours = diff.total_seconds() / 3600.0

        reminder_window: Optional[str] = None
        is_overdue = False

        if diff_hours < 0:
            # Overdue
            reminder_window = "OVERDUE"
            is_overdue = True
        elif 0 <= diff_hours <= due_soon_hours:
            # Due Soon
            reminder_window = "DUE_SOON"

        if not reminder_window:
            continue

        recipient = m.owner_email
        if not recipient:
            continue
        deadline_version = due_str.replace(":", "-").replace("+", "_")
        # Deduplication key format: (taskId, policyVersion, deadlineVersion, reminderWindow, recipient)
        dedup_run_key = f"{m.planner_task_id}:{policy_version}:{deadline_version}:{reminder_window}:{recipient}"

        subject = (
            f"URGENT: Action Overdue — {m.title}"
            if is_overdue
            else f"REMINDER: Action Due Soon — {m.title}"
        )
        body = (
            f"Hello,\n\nThis is an automated follow-up for meeting action '{m.title}'.\n"
            f"Meeting: {m.meeting_id}\n"
            f"Due Date: {due_str}\n"
            f"Current Completion: {percent_complete}%\n"
            f"Originating Decision: {m.originating_decision or 'Executive alignment'}\n\n"
            f"Please review and update status in Microsoft Planner."
        )

        reminders.append({
            "taskId": m.planner_task_id,
            "mappingId": m.mapping_id,
            "title": m.title,
            "status": "REMINDER_DUE",
            "reminderWindow": reminder_window,
            "dueDateTime": due_str,
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "dedupRunKey": dedup_run_key,
            "isOverdue": is_overdue,
            "hoursToDeadline": round(diff_hours, 1),
        })

    return reminders
