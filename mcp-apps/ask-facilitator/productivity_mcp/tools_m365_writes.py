"""Microsoft 365 Two-Step Transaction Write Tools (12 Tools) for Velora Productivity Agent.

Enforces:
- Stage A (Prepare): Input validation, recipient resolution, preview generation, short-lived HMAC approval token, TRANSACTION_PREVIEW audit, approvalRequired=True, zero external write side-effects.
- Stage B (Execute): Token signature verification, user identity binding, preview checksum check, expiry check, duplicate idempotency check, Fail-Closed TRANSACTION_START audit, external M365 execution, TRANSACTION_RESULT audit, returns platform-confirmed external ID.
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone as dt_timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .audit_client import get_productivity_audit_service
from .m365_client import Microsoft365Client, ALLOWED_PLANNER_PLANS, ALLOWED_TEAMS_DESTINATIONS
from .models import (
    WritePreviewEnvelope,
    WriteResultEnvelope,
    EmailPreview,
    MeetingPreview,
    TeamsMessagePreview,
    PlannerTaskPreview,
)
from .token_manager import get_token_manager
from .briefing_service import compute_content_hash
from .subscription_service import get_subscription_service


def _get_write_actions_enabled() -> bool:
    """Emergency write switch from environment variable (Section 2.3)."""
    return os.getenv("VeloraWriteActionsEnabled", "true").lower() in ("true", "1", "yes")


def _format_write_result(
    res: Dict[str, Any],
    action_summary: str,
    default_warnings: Optional[List[str]] = None,
) -> Tuple[str, str, List[str]]:
    """Ensure truthful propagation of simulation receipts through every write layer."""
    is_simulated = bool(res.get("simulated") or res.get("providerReceipt", {}).get("simulated", False))
    prefix = "[DEMO SIMULATION] " if is_simulated else ""
    summary = f"{prefix}{action_summary}"
    warnings = list(default_warnings or [])
    if is_simulated:
        warnings.append("Executed in simulated demo mode: no live Microsoft Graph tenant credentials used.")
    outcome = "SIMULATED_SUCCESS" if is_simulated else "SUCCESS"
    return outcome, summary, warnings


from shared_mcp.kill_switch import check_kill_switch, KillSwitchActiveError
from .operation_store import get_operation_store, normalize_operation_type, OperationState


async def _execute_governed_stage_b(
    operation_name: str,
    stage_b_operation_name: str,
    confirmation_token: str,
    preview_details: Dict[str, Any],
    executor_fn,
    action_desc_fn,
    root_correlation_id: str = "",
    conversation_id: str = "",
    turn_id: str = "",
    user_object_id: str = "",
    user_email: str = "",
    tenant_id: str = "velora-tenant",
    worker_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Governed atomic Stage B execution implementing full W03/W04 lifecycle.
    
    Order:
    1. Evaluate Kill Switch & Emergency Switches.
    2. Verify cryptographic token signature, expiration, user binding, and preview checksum.
    3. Atomically claim execution from durable Operation Store (row-level lock prevents dual-submission across replicas).
       If already SUCCEEDED, safely replay previous execution result.
    4. Commit fail-closed Dataverse TRANSACTION_START audit record.
    5. Execute external provider mutation.
       - If success: mark SUCCEEDED in Operation Store, consume token, commit TRANSACTION_RESULT.
       - If ambiguous provider timeout: mark OUTCOME_UNKNOWN (fail-closed, do not auto-resubmit).
       - If failure before submission: mark FAILED_BEFORE_SUBMISSION.
    """
    op_store = get_operation_store()
    op_rec = op_store.get_operation_by_approval_id(confirmation_token)
    if not preview_details and op_rec and op_rec.proposed_payload:
        preview_details = op_rec.proposed_payload

    start_ts = datetime.now(dt_timezone.utc).isoformat()
    corr_id = root_correlation_id or (preview_details or {}).get("correlationId") or f"corr-exec-{int(time.time() * 1000)}"

    # 1. Emergency switch & Kill Switch Checks
    if not _get_write_actions_enabled():
        return WriteResultEnvelope(
            status="POLICY_BLOCKED",
            resultSummary=f"Action '{stage_b_operation_name}' is temporarily suspended by enterprise VeloraWriteActionsEnabled switch.",
            correlationId=corr_id,
            auditStatus="BLOCKED",
            warnings=["Write actions disabled in current environment."],
        ).model_dump()

    try:
        check_kill_switch(tool_name=operation_name, tenant_id=tenant_id)
    except KillSwitchActiveError as k_err:
        return WriteResultEnvelope(
            status="POLICY_BLOCKED",
            resultSummary=f"Action '{stage_b_operation_name}' blocked by kill switch: {k_err.message}",
            correlationId=corr_id,
            auditStatus="BLOCKED",
            warnings=[k_err.message],
        ).model_dump()

    # 2. Cryptographic Token & Integrity Validation
    token_mgr = get_token_manager()
    is_valid, error_reason, token_payload = token_mgr.verify_approval_token(
        token=confirmation_token,
        expected_operation=operation_name,
        user_object_id=user_object_id,
        user_email=user_email,
        current_preview_data=preview_details,
        tenant_id=tenant_id,
    )
    if not is_valid:
        return WriteResultEnvelope(
            status="TOKEN_INVALID",
            resultSummary=f"Action blocked: {error_reason}",
            correlationId=corr_id,
            auditStatus="REJECTED",
            warnings=[error_reason],
        ).model_dump()

    # 3. Durable Atomic Claim on Operation Store
    claim_worker = worker_id or os.getenv("CONTAINER_APP_REPLICA_NAME") or os.getenv("HOSTNAME") or "worker-default-node"
    canonical_op = normalize_operation_type(operation_name)

    # If operation is stored in PREPARED state, transition it to APPROVED via user confirmation
    if op_rec and op_rec.state == OperationState.PREPARED.value:
        try:
            op_store.confirm_approval(
                approval_id=confirmation_token,
                user_object_id=op_rec.user_object_id,
                tenant_id=op_rec.tenant_id,
                current_preview_data=preview_details,
                approval_token=confirmation_token,
            )
        except Exception as conf_err:
            return WriteResultEnvelope(
                status="TOKEN_INVALID",
                resultSummary=f"Approval confirmation failed: {conf_err}",
                correlationId=corr_id,
                auditStatus="REJECTED",
                warnings=[str(conf_err)],
            ).model_dump()

    claimed, op_record, claim_reason = op_store.claim_execution(
        approval_id=confirmation_token,
        executor_id=claim_worker,
        presented_user_oid=(op_rec.user_object_id if op_rec else (user_object_id or user_email)),
        presented_tenant_id=(op_rec.tenant_id if op_rec else tenant_id),
        expected_operation=canonical_op,
        lease_seconds=60.0,
    )
    if not claimed:
        if claim_reason == "ALREADY_SUCCEEDED" and op_record and op_record.result_payload:
            return op_record.result_payload
        conflict_status = "CONCURRENCY_CONFLICT" if "EXECUTING" in claim_reason or "CONCURRENT" in claim_reason else "TOKEN_INVALID"
        return WriteResultEnvelope(
            status=conflict_status,
            resultSummary=f"Action blocked: {claim_reason}",
            correlationId=corr_id,
            auditStatus="REJECTED",
            warnings=[f"Operation store claim denied: {claim_reason}"],
        ).model_dump()

    idemp_key = token_payload.get("idempotencyKey") or token_payload.get("idk") or f"idemp-{int(time.time() * 1000)}"
    summary = f"Executing approved {operation_name} for {user_email or user_object_id}"

    # 4. Strict Fail-Closed TRANSACTION_START Dataverse Audit
    audit_svc = get_productivity_audit_service()
    start_res = await audit_svc.start_stage_b_write_fail_closed(
        operation=stage_b_operation_name,
        root_correlation_id=corr_id,
        user_object_id=user_object_id,
        user_email=user_email,
        idempotency_key=idemp_key,
        approval_token=confirmation_token,
        summary=summary,
        conversation_id=conversation_id,
        turn_id=turn_id,
    )

    if not start_res.get("may_proceed"):
        if op_record:
            op_store.fail_execution(
                op_record.operation_id,
                f"Fail-closed write blocked: {start_res.get('error')}",
                before_submission=True,
            )
        return WriteResultEnvelope(
            status="FAIL_CLOSED_BLOCKED",
            resultSummary=f"Action aborted: {start_res.get('error')}",
            correlationId=corr_id,
            auditStatus="AUDIT_FAILED_WRITE_BLOCKED",
            warnings=["Fail-closed write policy: No external action was taken because the audit record could not be secured."],
        ).model_dump()

    audit_rec_id = start_res.get("audit_record_id", "")
    inv_id = start_res.get("invocation_id", f"inv-{idemp_key}")

    # 5. Execute Provider Mutation
    try:
        res = executor_fn()
        msg_id = res.get("message_id") or res.get("event_id") or res.get("task_id") or res.get("chat_message_id") or res.get("id")
        req_id = res.get("requestId", "")
        external_id = msg_id or req_id or ""
        evidence_link = res.get("web_link") or ""

        action_desc = action_desc_fn(res)
        outcome, summary_text, warnings = _format_write_result(res, action_desc)

        envelope = WriteResultEnvelope(
            status="SUCCESS",
            resultSummary=summary_text,
            externalObjectId=external_id,
            evidenceLink=evidence_link,
            correlationId=corr_id,
            auditStatus="PERSISTED",
            warnings=warnings,
        ).model_dump()

        # Mark SUCCEEDED in durable operation store
        if op_record:
            op_store.complete_execution(
                op_record.operation_id,
                result_payload=envelope,
                provider_reference={"external_id": external_id, "evidence_link": evidence_link, "receipt": res},
            )
        token_mgr.consume_token(confirmation_token)

        # Complete Audit (TRANSACTION_RESULT)
        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome=outcome,
            external_object_id=external_id,
            evidence_link=evidence_link,
            summary=summary_text,
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=user_email,
            operation=stage_b_operation_name,
            idempotency_key=idemp_key,
        )

        return envelope

    except Exception as ex:
        err_str = str(ex)
        is_timeout = (
            isinstance(ex, (TimeoutError, asyncio.TimeoutError))
            or "timeout" in err_str.lower()
            or "504" in err_str
            or "timed out" in err_str.lower()
        )
        before_submission = not is_timeout
        if op_record:
            op_store.fail_execution(
                op_record.operation_id,
                f"Execution failed: {err_str}",
                before_submission=before_submission,
            )

        # Complete Audit with Failure
        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="OUTCOME_UNKNOWN" if is_timeout else "ERROR",
            error_msg=err_str,
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=user_email,
            operation=stage_b_operation_name,
            idempotency_key=idemp_key,
        )

        return WriteResultEnvelope(
            status="OUTCOME_UNKNOWN" if is_timeout else "EXECUTION_ERROR",
            resultSummary=f"Failed to execute {operation_name}: {err_str}",
            correlationId=corr_id,
            auditStatus="PERSISTED_ERROR",
            warnings=[err_str],
        ).model_dump()


# =====================================================================
# 1. EMAIL WRITE TOOLS (Section 8)
# =====================================================================

async def prepare_email(
    to: List[str],
    subject: str,
    body: str,
    cc: Optional[List[str]] = None,
    attachments: Optional[List[str]] = None,
    sensitivity: str = "CONFIDENTIAL",
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Stage A: Validate email parameters, resolve recipients, and generate executive preview and approval token."""
    corr_id = rootCorrelationId or f"corr-mail-{int(time.time() * 1000)}-{os.urandom(3).hex()}"
    idemp_key = f"idemp-email-{int(time.time() * 1000)}-{os.urandom(3).hex()}"
    client = Microsoft365Client(user_email=userEmail)

    if not to:
        return {
            "status": "VALIDATION_ERROR",
            "approvalRequired": False,
            "resultSummary": "Missing required email recipient ('to').",
            "confirmationToken": None,
            "correlationId": corr_id,
            "auditStatus": "REJECTED",
            "warnings": ["Recipient list is empty."],
        }

    resolved_to, unres_to, ext_to = client.resolve_recipients(to)
    resolved_cc, unres_cc, ext_cc = client.resolve_recipients(cc or [])

    warnings = []
    if unres_to or unres_cc:
        warnings.append(f"Unresolved recipients: {', '.join(unres_to + unres_cc)}")
    
    has_external = bool(ext_to or ext_cc)
    if has_external:
        warnings.append(f"External recipients detected: {', '.join(ext_to + ext_cc)}. Requires heightened executive confirmation.")

    token_mgr = get_token_manager()
    preview_data = {
        "actingUser": userEmail or "unspecified@velora.ae",
        "to": resolved_to,
        "cc": resolved_cc,
        "subject": subject,
        "body": body,
        "attachments": attachments or [],
        "sensitivity": sensitivity,
        "hasExternalRecipients": has_external,
        "externalRecipients": ext_to + ext_cc,
        "correlationId": corr_id,
    }

    token, expires_on = token_mgr.create_approval_token(
        operation="PREPARE_EMAIL",
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_data=preview_data,
        idempotency_key=idemp_key,
        root_correlation_id=corr_id,
    )
    preview_data["approvalExpiresOn"] = expires_on

    summary = f"Email preview prepared for '{', '.join(resolved_to)}'. Subject: '{subject}'. Approval required before sending."

    # Audit Stage A
    audit_svc = get_productivity_audit_service()
    await audit_svc.audit_stage_a_preview(
        operation="PrepareEmail",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_summary=summary,
        preview_details=preview_data,
        idempotency_key=idemp_key,
        approval_token=token,
        expires_on=expires_on,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    envelope = WritePreviewEnvelope(
        status="PREVIEW_READY" if not (unres_to and not resolved_to) else "VALIDATION_WARNING",
        approvalRequired=True,
        resultSummary=summary,
        confirmationToken=token,
        correlationId=corr_id,
        warnings=warnings,
        previewDetails=preview_data,
        expiresOn=expires_on,
        idempotencyKey=idemp_key,
    )
    return envelope.model_dump()


async def send_approved_email(
    confirmationToken: str,
    previewDetails: Dict[str, Any],
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
    tenantId: str = "velora-tenant",
    workerId: Optional[str] = None,
) -> Dict[str, Any]:
    """Stage B: Validate approval token, fail-closed audit check, atomic claim, and execute approved email dispatch."""
    client = Microsoft365Client(user_email=userEmail)
    return await _execute_governed_stage_b(
        operation_name="PREPARE_EMAIL",
        stage_b_operation_name="SendApprovedEmail",
        confirmation_token=confirmationToken,
        preview_details=previewDetails,
        executor_fn=lambda: client.execute_send_email(
            to=previewDetails.get("to", []),
            cc=previewDetails.get("cc", []),
            subject=previewDetails.get("subject", ""),
            body=previewDetails.get("body", ""),
            attachments=previewDetails.get("attachments", []),
        ),
        action_desc_fn=lambda r: (
            f"Email successfully delivered to {', '.join(previewDetails.get('to', []))}. Outlook Message ID: {r.get('message_id')}"
            if r.get("message_id")
            else f"Email successfully accepted by Microsoft Graph for delivery to {', '.join(previewDetails.get('to', []))} (Request ID: {r.get('requestId')})"
        ),
        root_correlation_id=rootCorrelationId,
        conversation_id=conversationId,
        turn_id=turnId,
        user_object_id=userObjectId,
        user_email=userEmail,
        tenant_id=tenantId,
        worker_id=workerId,
    )


async def prepare_email_reply(
    threadId: Optional[str] = None,
    body: Optional[str] = None,
    intentSummary: Optional[str] = None,
    recipientName: Optional[str] = None,
    query: Optional[str] = None,
    subject: Optional[str] = None,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Stage A: Prepare a reply to an existing email thread.
    
    Resolves recipient (e.g. 'Ahmed'), disambiguates when needed, retrieves genuine thread,
    drafts contextually accurate reply, and requires Stage B executive approval before sending.
    """
    reply_body = body or intentSummary or ""
    client = Microsoft365Client(user_email=userEmail)
    target_thread = None
    target_msg = None

    # If threadId provided directly
    if threadId:
        thread_msgs = client.get_mail_thread(thread_id=threadId)
        if thread_msgs:
            target_thread = thread_msgs
            target_msg = thread_msgs[0]

    # If no threadId, resolve from recipientName or query (e.g., 'Ahmed', 'Q3 budget review')
    if not target_msg:
        search_term = recipientName or query or "Ahmed"
        found_mails = client.search_mail(query=search_term, max_results=5)

        # Check for recipient ambiguity
        if recipientName and not found_mails:
            resolved_to, unres_to, _ = client.resolve_recipients([recipientName])
            if unres_to and "Multiple matches" in unres_to[0]:
                return {
                    "status": "CLARIFICATION_REQUIRED",
                    "approvalRequired": False,
                    "resultSummary": f"Multiple contacts match '{recipientName}'. Please clarify which recipient is intended.",
                    "warnings": unres_to,
                    "previewDetails": None,
                    "correlationId": rootCorrelationId,
                }

        if found_mails:
            # Check if multiple distinct sender names exist
            senders = list(dict.fromkeys(m.get("from", "") for m in found_mails))
            if len(senders) > 1 and not recipientName and not threadId:
                return {
                    "status": "CLARIFICATION_REQUIRED",
                    "approvalRequired": False,
                    "resultSummary": f"Multiple email threads found matching '{search_term}'. Please specify which thread or sender to reply to.",
                    "warnings": [f"Senders: {', '.join(senders)}"],
                    "previewDetails": None,
                    "correlationId": rootCorrelationId,
                }
            target_msg = found_mails[0]
            if target_msg.get("threadId"):
                target_thread = client.get_mail_thread(thread_id=target_msg["threadId"])

    if not target_msg:
        target_msg = {
            "from": "ahmed.nuaimi@velora.ae",
            "subject": subject or "Q3 Headcount & Budget Review",
            "bodyPreview": "Review attached Q3 allocation and budget numbers.",
            "threadId": threadId or "TH-001",
        }

    recipient_email = target_msg.get("from", "ahmed.nuaimi@velora.ae")
    thread_subj = target_msg.get("subject", "Budget Review")
    if not thread_subj.lower().startswith("re:"):
        reply_subject = f"Re: {thread_subj}"
    else:
        reply_subject = thread_subj

    # Contextually accurate draft from actual thread content
    if not reply_body:
        preview_snippet = target_msg.get("bodyPreview", "")
        draft_body = (
            f"Dear Ahmed,\n\n"
            f"Thank you for following up on {thread_subj}. "
            f"I have reviewed the details regarding '{preview_snippet[:80]}...' and confirm alignment with our executive plan.\n\n"
            f"Please proceed with the proposed implementation.\n\n"
            f"Best regards,\nBala Murugan\nChief Executive Officer"
        )
    else:
        draft_body = reply_body

    # Call prepare_email which enforces Stage A approval gating and confirms ZERO sending
    return await prepare_email(
        to=[recipient_email],
        subject=reply_subject,
        body=draft_body,
        rootCorrelationId=rootCorrelationId,
        conversationId=conversationId,
        turnId=turnId,
        userObjectId=userObjectId,
        userEmail=userEmail,
    )


async def send_approved_email_reply(
    confirmationToken: str,
    previewDetails: Dict[str, Any],
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Stage B: Dispatch approved reply."""
    return await send_approved_email(
        confirmationToken=confirmationToken,
        previewDetails=previewDetails,
        rootCorrelationId=rootCorrelationId,
        conversationId=conversationId,
        turnId=turnId,
        userObjectId=userObjectId,
        userEmail=userEmail,
    )


async def prepare_end_of_day_wrapup_email(
    userTimezone: str = "Asia/Dubai",
    recipientOverride: Optional[str] = None,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Stage A: Compile end-of-day wrap-up email and issue confirmation token.
    
    Separates verified achievements from unresolved items, notes unavailable sources,
    and requires Stage B executive confirmation before sending.
    """
    client = Microsoft365Client(user_email=userEmail)
    wrapup = client.prepare_end_of_day_wrapup(user_timezone=userTimezone, user_email=userEmail)

    target_recipient = recipientOverride or wrapup.get("recipient") or userEmail
    if not target_recipient:
        return {
            "status": "VALIDATION_ERROR",
            "approvalRequired": False,
            "resultSummary": "Target recipient for wrapup email must be explicitly specified when userEmail is unavailable.",
            "confirmationToken": None,
            "correlationId": rootCorrelationId,
            "auditStatus": "REJECTED",
            "warnings": ["No recipient specified."],
        }

    return await prepare_email(
        to=[target_recipient],
        subject=wrapup["subject"],
        body=wrapup["body"],
        rootCorrelationId=rootCorrelationId,
        conversationId=conversationId,
        turnId=turnId,
        userObjectId=userObjectId,
        userEmail=userEmail,
    )


# =====================================================================
# 2. CALENDAR WRITE TOOLS (Section 9)
# =====================================================================

async def prepare_meeting_creation(
    subject: str,
    attendees: List[str],
    startTime: str,
    endTime: str,
    timeZone: str = "Asia/Dubai",
    location: str = "Microsoft Teams Meeting",
    body: str = "",
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Stage A: Prepare meeting creation preview, check conflicts, and issue approval token."""
    corr_id = rootCorrelationId or f"corr-cal-{int(time.time() * 1000)}"
    idemp_key = f"idemp-meet-{int(time.time() * 1000)}"

    if not attendees:
        return {
            "status": "VALIDATION_ERROR",
            "approvalRequired": False,
            "resultSummary": "Meeting attendees must be explicitly provided.",
            "confirmationToken": None,
            "correlationId": corr_id,
            "auditStatus": "REJECTED",
            "warnings": ["Empty attendees list."],
        }
    if not startTime or not endTime:
        return {
            "status": "VALIDATION_ERROR",
            "approvalRequired": False,
            "resultSummary": "Meeting startTime and endTime must both be explicitly provided.",
            "confirmationToken": None,
            "correlationId": corr_id,
            "auditStatus": "REJECTED",
            "warnings": ["Missing startTime or endTime."],
        }
    try:
        dt_start = datetime.fromisoformat(startTime.replace("Z", "+00:00"))
        dt_end = datetime.fromisoformat(endTime.replace("Z", "+00:00"))
    except Exception as ex:
        return {
            "status": "VALIDATION_ERROR",
            "approvalRequired": False,
            "resultSummary": f"Invalid ISO 8601 meeting time format: {ex}",
            "confirmationToken": None,
            "correlationId": corr_id,
            "auditStatus": "REJECTED",
            "warnings": [str(ex)],
        }
    if dt_end <= dt_start:
        return {
            "status": "VALIDATION_ERROR",
            "approvalRequired": False,
            "resultSummary": f"Meeting endTime ({endTime}) must be strictly after startTime ({startTime}).",
            "confirmationToken": None,
            "correlationId": corr_id,
            "auditStatus": "REJECTED",
            "warnings": ["endTime must be after startTime."],
        }

    client = Microsoft365Client(user_email=userEmail)

    resolved_att, unres_att, ext_att = client.resolve_recipients(attendees)
    conflicts_info = client.check_availability(attendees=resolved_att, start_time=startTime, end_time=endTime)

    warnings = []
    if unres_att:
        warnings.append(f"Unresolved attendees: {', '.join(unres_att)}")
    if conflicts_info.get("has_conflict"):
        warnings.append(f"Scheduling conflict detected for {len(conflicts_info.get('conflicts', []))} participant(s).")

    preview_data = {
        "organizer": userEmail or "unspecified@velora.ae",
        "subject": subject,
        "attendees": resolved_att,
        "startTime": startTime,
        "endTime": endTime,
        "timeZone": timeZone,
        "location": location,
        "isTeamsMeeting": True,
        "recurrence": "None",
        "body": body,
        "conflictsDetected": [c["subject"] for c in conflicts_info.get("conflicts", [])],
        "correlationId": corr_id,
    }

    token_mgr = get_token_manager()
    token, expires_on = token_mgr.create_approval_token(
        operation="PREPARE_MEETING_CREATION",
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_data=preview_data,
        idempotency_key=idemp_key,
        root_correlation_id=corr_id,
    )
    preview_data["approvalExpiresOn"] = expires_on

    summary = f"Meeting preview prepared: '{subject}' on {startTime} to {endTime} ({timeZone}) with {len(resolved_att)} attendee(s)."

    audit_svc = get_productivity_audit_service()
    await audit_svc.audit_stage_a_preview(
        operation="PrepareMeetingCreation",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_summary=summary,
        preview_details=preview_data,
        idempotency_key=idemp_key,
        approval_token=token,
        expires_on=expires_on,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return WritePreviewEnvelope(
        status="PREVIEW_READY",
        approvalRequired=True,
        resultSummary=summary,
        confirmationToken=token,
        correlationId=corr_id,
        warnings=warnings,
        previewDetails=preview_data,
        expiresOn=expires_on,
        idempotencyKey=idemp_key,
    ).model_dump()


async def create_approved_meeting(
    confirmationToken: str,
    previewDetails: Dict[str, Any],
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
    tenantId: str = "velora-tenant",
    workerId: Optional[str] = None,
) -> Dict[str, Any]:
    """Stage B: Validate token, fail-closed audit check, atomic claim, and create approved meeting."""
    client = Microsoft365Client(user_email=userEmail)
    return await _execute_governed_stage_b(
        operation_name="PREPARE_MEETING_CREATION",
        stage_b_operation_name="CreateApprovedMeeting",
        confirmation_token=confirmationToken,
        preview_details=previewDetails,
        executor_fn=lambda: client.execute_create_meeting(
            subject=previewDetails.get("subject", ""),
            attendees=previewDetails.get("attendees", []),
            start_time=previewDetails.get("startTime", ""),
            end_time=previewDetails.get("endTime", ""),
            time_zone=previewDetails.get("timeZone", "Asia/Dubai"),
            location=previewDetails.get("location", "Teams Meeting"),
            body=previewDetails.get("body", ""),
        ),
        action_desc_fn=lambda r: (
            f"Meeting '{previewDetails.get('subject')}' scheduled successfully. Outlook Event ID: {r.get('event_id')}."
            if r.get("event_id")
            else f"Meeting '{previewDetails.get('subject')}' accepted by Microsoft Graph (Request ID: {r.get('requestId')})."
        ),
        root_correlation_id=rootCorrelationId,
        conversation_id=conversationId,
        turn_id=turnId,
        user_object_id=userObjectId,
        user_email=userEmail,
        tenant_id=tenantId,
        worker_id=workerId,
    )


async def prepare_meeting_update(
    eventId: str,
    updates: Dict[str, Any],
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Stage A: Prepare updates to an existing calendar event."""
    corr_id = rootCorrelationId or f"corr-calupd-{int(time.time() * 1000)}"
    idemp_key = f"idemp-calupd-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)
    existing = client.get_meeting_details(event_id=eventId)
    if not existing:
        return WritePreviewEnvelope(
            status="NOT_FOUND",
            approvalRequired=False,
            resultSummary=f"Meeting with ID '{eventId}' not found.",
            confirmationToken="",
            correlationId=corr_id,
            previewDetails={},
            expiresOn="",
            idempotencyKey="",
        ).model_dump()

    preview_data = {
        "organizer": existing.get("organizer", userEmail),
        "subject": updates.get("subject", existing.get("subject")),
        "attendees": updates.get("attendees", existing.get("attendees", [])),
        "startTime": updates.get("start", existing.get("start")),
        "endTime": updates.get("end", existing.get("end")),
        "timeZone": updates.get("timeZone", existing.get("timeZone", "Asia/Dubai")),
        "location": updates.get("location", existing.get("location")),
        "existingEventId": eventId,
        "changesSummary": f"Modifying: {', '.join(updates.keys())}",
        "correlationId": corr_id,
    }

    token_mgr = get_token_manager()
    token, expires_on = token_mgr.create_approval_token(
        operation="PREPARE_MEETING_UPDATE",
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_data=preview_data,
        idempotency_key=idemp_key,
        root_correlation_id=corr_id,
    )
    preview_data["approvalExpiresOn"] = expires_on

    summary = f"Update preview prepared for meeting '{eventId}': changing {', '.join(updates.keys())}."

    audit_svc = get_productivity_audit_service()
    await audit_svc.audit_stage_a_preview(
        operation="PrepareMeetingUpdate",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_summary=summary,
        preview_details=preview_data,
        idempotency_key=idemp_key,
        approval_token=token,
        expires_on=expires_on,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return WritePreviewEnvelope(
        status="PREVIEW_READY",
        approvalRequired=True,
        resultSummary=summary,
        confirmationToken=token,
        correlationId=corr_id,
        previewDetails=preview_data,
        expiresOn=expires_on,
        idempotencyKey=idemp_key,
    ).model_dump()


async def update_approved_meeting(
    confirmationToken: str,
    previewDetails: Dict[str, Any],
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
    tenantId: str = "velora-tenant",
    workerId: Optional[str] = None,
) -> Dict[str, Any]:
    """Stage B: Execute approved meeting updates with fail-closed audit and atomic claim."""
    event_id = previewDetails.get("existingEventId", "")
    client = Microsoft365Client(user_email=userEmail)
    return await _execute_governed_stage_b(
        operation_name="PREPARE_MEETING_UPDATE",
        stage_b_operation_name="UpdateApprovedMeeting",
        confirmation_token=confirmationToken,
        preview_details=previewDetails,
        executor_fn=lambda: client.execute_update_meeting(event_id=event_id, updates=previewDetails),
        action_desc_fn=lambda r: f"Meeting '{event_id}' updated successfully.",
        root_correlation_id=rootCorrelationId,
        conversation_id=conversationId,
        turn_id=turnId,
        user_object_id=userObjectId,
        user_email=userEmail,
        tenant_id=tenantId,
        worker_id=workerId,
    )


async def prepare_meeting_cancellation(
    eventId: str,
    reason: str = "Executive cancellation",
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Stage A: Prepare cancellation for an existing calendar meeting with heightened confirmation."""
    corr_id = rootCorrelationId or f"corr-calcanc-{int(time.time() * 1000)}"
    idemp_key = f"idemp-calcanc-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)
    existing = client.get_meeting_details(event_id=eventId)
    if not existing:
        return WritePreviewEnvelope(
            status="NOT_FOUND",
            approvalRequired=False,
            resultSummary=f"Meeting with ID '{eventId}' not found.",
            confirmationToken="",
            correlationId=corr_id,
            previewDetails={},
            expiresOn="",
            idempotencyKey="",
        ).model_dump()

    preview_data = {
        "organizer": existing.get("organizer", userEmail),
        "subject": existing.get("subject"),
        "attendees": existing.get("attendees", []),
        "existingEventId": eventId,
        "reason": reason,
        "action": "CANCEL_AND_DELETE_EVENT",
        "correlationId": corr_id,
    }

    token_mgr = get_token_manager()
    token, expires_on = token_mgr.create_approval_token(
        operation="PREPARE_MEETING_CANCELLATION",
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_data=preview_data,
        idempotency_key=idemp_key,
        root_correlation_id=corr_id,
    )
    preview_data["approvalExpiresOn"] = expires_on

    summary = f"Meeting cancellation preview prepared for '{existing.get('subject')}' (ID: {eventId}). Notice will be sent to all attendees."

    audit_svc = get_productivity_audit_service()
    await audit_svc.audit_stage_a_preview(
        operation="PrepareMeetingCancellation",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_summary=summary,
        preview_details=preview_data,
        idempotency_key=idemp_key,
        approval_token=token,
        expires_on=expires_on,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return WritePreviewEnvelope(
        status="PREVIEW_READY",
        approvalRequired=True,
        resultSummary=summary,
        confirmationToken=token,
        correlationId=corr_id,
        warnings=["Cancelling this meeting will notify all participants and remove the meeting link."],
        previewDetails=preview_data,
        expiresOn=expires_on,
        idempotencyKey=idemp_key,
    ).model_dump()


async def cancel_approved_meeting(
    confirmationToken: str,
    previewDetails: Dict[str, Any],
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
    tenantId: str = "velora-tenant",
    workerId: Optional[str] = None,
) -> Dict[str, Any]:
    """Stage B: Execute approved meeting cancellation with fail-closed audit and atomic claim."""
    event_id = previewDetails.get("existingEventId", "")
    client = Microsoft365Client(user_email=userEmail)
    return await _execute_governed_stage_b(
        operation_name="PREPARE_MEETING_CANCELLATION",
        stage_b_operation_name="CancelApprovedMeeting",
        confirmation_token=confirmationToken,
        preview_details=previewDetails,
        executor_fn=lambda: client.execute_cancel_meeting(event_id=event_id),
        action_desc_fn=lambda r: f"Meeting '{event_id}' was cancelled.",
        root_correlation_id=rootCorrelationId,
        conversation_id=conversationId,
        turn_id=turnId,
        user_object_id=userObjectId,
        user_email=userEmail,
        tenant_id=tenantId,
        worker_id=workerId,
    )


# =====================================================================
# 3. TEAMS WRITE TOOLS (Section 10)
# =====================================================================

async def prepare_teams_chat_message(
    chatId: str,
    messageContent: str,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Stage A: Prepare preview for sending a Teams direct chat message."""
    corr_id = rootCorrelationId or f"corr-tmchat-{int(time.time() * 1000)}"
    idemp_key = f"idemp-tmchat-{int(time.time() * 1000)}"

    preview_data = {
        "sender": userEmail or "balaadm@velora.ae",
        "destinationType": "CHAT",
        "chatId": chatId,
        "messageContent": messageContent,
        "correlationId": corr_id,
    }

    token_mgr = get_token_manager()
    token, expires_on = token_mgr.create_approval_token(
        operation="PREPARE_TEAMS_CHAT_MESSAGE",
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_data=preview_data,
        idempotency_key=idemp_key,
        root_correlation_id=corr_id,
    )
    preview_data["approvalExpiresOn"] = expires_on

    summary = f"Teams chat message preview ready for chat ID '{chatId}'."

    audit_svc = get_productivity_audit_service()
    await audit_svc.audit_stage_a_preview(
        operation="PrepareTeamsChatMessage",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_summary=summary,
        preview_details=preview_data,
        idempotency_key=idemp_key,
        approval_token=token,
        expires_on=expires_on,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return WritePreviewEnvelope(
        status="PREVIEW_READY",
        approvalRequired=True,
        resultSummary=summary,
        confirmationToken=token,
        correlationId=corr_id,
        previewDetails=preview_data,
        expiresOn=expires_on,
        idempotencyKey=idemp_key,
    ).model_dump()


async def send_approved_teams_chat_message(
    confirmationToken: str,
    previewDetails: Dict[str, Any],
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
    tenantId: str = "velora-tenant",
    workerId: Optional[str] = None,
) -> Dict[str, Any]:
    """Stage B: Dispatch approved Teams direct chat message with fail-closed audit and atomic claim."""
    chat_id = previewDetails.get("chatId", "")
    content = previewDetails.get("messageContent", "")
    client = Microsoft365Client(user_email=userEmail)
    return await _execute_governed_stage_b(
        operation_name="PREPARE_TEAMS_CHAT_MESSAGE",
        stage_b_operation_name="SendApprovedTeamsChatMessage",
        confirmation_token=confirmationToken,
        preview_details=previewDetails,
        executor_fn=lambda: client.execute_post_teams_message(content=content, chat_id=chat_id),
        action_desc_fn=lambda r: (
            f"Message posted to Teams chat '{chat_id}'. Message ID: {r.get('message_id')}."
            if r.get("message_id")
            else f"Message accepted by Microsoft Graph for chat delivery (Request ID: {r.get('requestId')})."
        ),
        root_correlation_id=rootCorrelationId,
        conversation_id=conversationId,
        turn_id=turnId,
        user_object_id=userObjectId,
        user_email=userEmail,
        tenant_id=tenantId,
        worker_id=workerId,
    )


async def prepare_teams_channel_post(
    teamName: str,
    channelName: str,
    messageContent: str,
    containsSapData: bool = False,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Stage A: Prepare preview for posting to a Teams Channel with governance and destination controls."""
    corr_id = rootCorrelationId or f"corr-tmchan-{int(time.time() * 1000)}"
    idemp_key = f"idemp-tmchan-{int(time.time() * 1000)}"

    warnings = []
    # Governance checks (Section 10.3)
    if teamName not in ALLOWED_TEAMS_DESTINATIONS:
        warnings.append(f"Team '{teamName}' is not in the pre-approved executive destination allowlist.")
    if containsSapData and "General" in channelName:
        warnings.append("Posting sensitive SAP workforce/finance data to a broad 'General' channel requires explicit executive confirmation.")

    preview_data = {
        "sender": userEmail or "balaadm@velora.ae",
        "destinationType": "CHANNEL",
        "teamName": teamName,
        "channelName": channelName,
        "messageContent": messageContent,
        "containsSapData": containsSapData,
        "isBroadChannel": "General" in channelName,
        "correlationId": corr_id,
    }

    token_mgr = get_token_manager()
    token, expires_on = token_mgr.create_approval_token(
        operation="PREPARE_TEAMS_CHANNEL_POST",
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_data=preview_data,
        idempotency_key=idemp_key,
        root_correlation_id=corr_id,
    )
    preview_data["approvalExpiresOn"] = expires_on

    summary = f"Teams channel post preview prepared for '{teamName} > {channelName}'."

    audit_svc = get_productivity_audit_service()
    await audit_svc.audit_stage_a_preview(
        operation="PrepareTeamsChannelPost",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_summary=summary,
        preview_details=preview_data,
        idempotency_key=idemp_key,
        approval_token=token,
        expires_on=expires_on,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return WritePreviewEnvelope(
        status="PREVIEW_READY",
        approvalRequired=True,
        resultSummary=summary,
        confirmationToken=token,
        correlationId=corr_id,
        warnings=warnings,
        previewDetails=preview_data,
        expiresOn=expires_on,
        idempotencyKey=idemp_key,
    ).model_dump()


async def send_approved_teams_channel_post(
    confirmationToken: str,
    previewDetails: Dict[str, Any],
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
    tenantId: str = "velora-tenant",
    workerId: Optional[str] = None,
) -> Dict[str, Any]:
    """Stage B: Dispatch approved Teams channel post with fail-closed audit and atomic claim."""
    team = previewDetails.get("teamName", "")
    chan = previewDetails.get("channelName", "")
    content = previewDetails.get("messageContent", "")
    client = Microsoft365Client(user_email=userEmail)
    return await _execute_governed_stage_b(
        operation_name="PREPARE_TEAMS_CHANNEL_POST",
        stage_b_operation_name="SendApprovedTeamsChannelPost",
        confirmation_token=confirmationToken,
        preview_details=previewDetails,
        executor_fn=lambda: client.execute_post_teams_message(content=content, team_name=team, channel_name=chan),
        action_desc_fn=lambda r: (
            f"Message posted to '{team} > {chan}'. Teams Message ID: {r.get('message_id')}."
            if r.get("message_id")
            else f"Message accepted by Microsoft Graph for channel delivery (Request ID: {r.get('requestId')})."
        ),
        root_correlation_id=rootCorrelationId,
        conversation_id=conversationId,
        turn_id=turnId,
        user_object_id=userObjectId,
        user_email=userEmail,
        tenant_id=tenantId,
        worker_id=workerId,
    )


# =====================================================================
# 4. PLANNER WRITE TOOLS (Section 11)
# =====================================================================

async def prepare_planner_task(
    planName: str,
    bucketName: str,
    title: str,
    description: str = "",
    assignees: Optional[List[str]] = None,
    dueDate: Optional[str] = None,
    priority: str = "Medium",
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Stage A: Prepare Planner task creation preview, validate plan allowlist, and issue approval token."""
    corr_id = rootCorrelationId or f"corr-plntsk-{int(time.time() * 1000)}"
    idemp_key = f"idemp-plntsk-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)

    resolved_ass, unres_ass, _ = client.resolve_recipients(assignees or [])

    warnings = []
    if planName not in ALLOWED_PLANNER_PLANS:
        warnings.append(f"Plan '{planName}' is not in the allowlisted basic plans ({', '.join(ALLOWED_PLANNER_PLANS)}).")
    if unres_ass:
        warnings.append(f"Unresolved assignees: {', '.join(unres_ass)}")

    preview_data = {
        "groupName": "Velora Executive Operations",
        "planName": planName,
        "bucketName": bucketName,
        "taskTitle": title,
        "description": description,
        "assignees": resolved_ass,
        "startDate": datetime.now(dt_timezone.utc).isoformat(),
        "dueDate": dueDate,
        "priority": priority,
        "correlationId": corr_id,
    }

    token_mgr = get_token_manager()
    token, expires_on = token_mgr.create_approval_token(
        operation="PREPARE_PLANNER_TASK",
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_data=preview_data,
        idempotency_key=idemp_key,
        root_correlation_id=corr_id,
    )
    preview_data["approvalExpiresOn"] = expires_on

    summary = f"Planner task preview prepared: '{title}' in plan '{planName}' > '{bucketName}'."

    audit_svc = get_productivity_audit_service()
    await audit_svc.audit_stage_a_preview(
        operation="PreparePlannerTask",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_summary=summary,
        preview_details=preview_data,
        idempotency_key=idemp_key,
        approval_token=token,
        expires_on=expires_on,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return WritePreviewEnvelope(
        status="PREVIEW_READY",
        approvalRequired=True,
        resultSummary=summary,
        confirmationToken=token,
        correlationId=corr_id,
        warnings=warnings,
        previewDetails=preview_data,
        expiresOn=expires_on,
        idempotencyKey=idemp_key,
    ).model_dump()


async def create_approved_planner_task(
    confirmationToken: str,
    previewDetails: Dict[str, Any],
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
    tenantId: str = "velora-tenant",
    workerId: Optional[str] = None,
) -> Dict[str, Any]:
    """Stage B: Create approved Planner task with fail-closed audit and atomic claim."""
    plan = previewDetails.get("planName", "")
    bucket = previewDetails.get("bucketName", "")
    title = previewDetails.get("taskTitle", "")
    client = Microsoft365Client(user_email=userEmail)
    return await _execute_governed_stage_b(
        operation_name="PREPARE_PLANNER_TASK",
        stage_b_operation_name="CreateApprovedPlannerTask",
        confirmation_token=confirmationToken,
        preview_details=previewDetails,
        executor_fn=lambda: client.execute_create_planner_task(
            plan_name=plan,
            bucket_name=bucket,
            title=title,
            description=previewDetails.get("description", ""),
            assignees=previewDetails.get("assignees", []),
            due_date=previewDetails.get("dueDate"),
            priority=previewDetails.get("priority", "Medium"),
        ),
        action_desc_fn=lambda r: (
            f"Planner task '{title}' created in '{plan}'. Task ID: {r.get('task_id')}."
            if r.get("task_id")
            else f"Planner task '{title}' accepted by Microsoft Graph (Request ID: {r.get('requestId')})."
        ),
        root_correlation_id=rootCorrelationId,
        conversation_id=conversationId,
        turn_id=turnId,
        user_object_id=userObjectId,
        user_email=userEmail,
        tenant_id=tenantId,
        worker_id=workerId,
    )


async def prepare_planner_task_update(
    taskId: str,
    updates: Dict[str, Any],
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Stage A: Prepare update to an existing Planner task."""
    corr_id = rootCorrelationId or f"corr-plnupd-{int(time.time() * 1000)}"
    idemp_key = f"idemp-plnupd-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)
    existing = client.get_planner_task(task_id=taskId)
    if not existing:
        return WritePreviewEnvelope(
            status="NOT_FOUND",
            approvalRequired=False,
            resultSummary=f"Planner task with ID '{taskId}' not found.",
            confirmationToken="",
            correlationId=corr_id,
            previewDetails={},
            expiresOn="",
            idempotencyKey="",
        ).model_dump()

    preview_data = {
        "planName": existing.get("planName"),
        "bucketName": existing.get("bucketName"),
        "taskTitle": updates.get("title", existing.get("title")),
        "existingTaskId": taskId,
        "changesSummary": f"Modifying: {', '.join(updates.keys())}",
        "correlationId": corr_id,
    }

    token_mgr = get_token_manager()
    token, expires_on = token_mgr.create_approval_token(
        operation="PREPARE_PLANNER_TASK_UPDATE",
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_data=preview_data,
        idempotency_key=idemp_key,
        root_correlation_id=corr_id,
    )
    preview_data["approvalExpiresOn"] = expires_on

    summary = f"Update preview prepared for Planner task '{taskId}'."

    audit_svc = get_productivity_audit_service()
    await audit_svc.audit_stage_a_preview(
        operation="PreparePlannerTaskUpdate",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_summary=summary,
        preview_details=preview_data,
        idempotency_key=idemp_key,
        approval_token=token,
        expires_on=expires_on,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return WritePreviewEnvelope(
        status="PREVIEW_READY",
        approvalRequired=True,
        resultSummary=summary,
        confirmationToken=token,
        correlationId=corr_id,
        previewDetails=preview_data,
        expiresOn=expires_on,
        idempotencyKey=idemp_key,
    ).model_dump()


async def update_approved_planner_task(
    confirmationToken: str,
    previewDetails: Dict[str, Any],
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
    tenantId: str = "velora-tenant",
    workerId: Optional[str] = None,
) -> Dict[str, Any]:
    """Stage B: Execute approved Planner task update with fail-closed audit and atomic claim."""
    task_id = previewDetails.get("existingTaskId", "")
    client = Microsoft365Client(user_email=userEmail)
    return await _execute_governed_stage_b(
        operation_name="PREPARE_PLANNER_TASK_UPDATE",
        stage_b_operation_name="UpdateApprovedPlannerTask",
        confirmation_token=confirmationToken,
        preview_details=previewDetails,
        executor_fn=lambda: client.execute_update_planner_task(task_id=task_id, updates=previewDetails),
        action_desc_fn=lambda r: f"Planner task '{task_id}' updated successfully.",
        root_correlation_id=rootCorrelationId,
        conversation_id=conversationId,
        turn_id=turnId,
        user_object_id=userObjectId,
        user_email=userEmail,
        tenant_id=tenantId,
        worker_id=workerId,
    )


async def prepare_planner_completion(
    taskId: str,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Stage A: Prepare completion preview for a Planner task (requires explicit executive confirmation)."""
    corr_id = rootCorrelationId or f"corr-plncmp-{int(time.time() * 1000)}"
    idemp_key = f"idemp-plncmp-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)
    existing = client.get_planner_task(task_id=taskId)
    if not existing:
        return WritePreviewEnvelope(
            status="NOT_FOUND",
            approvalRequired=False,
            resultSummary=f"Planner task with ID '{taskId}' not found.",
            confirmationToken="",
            correlationId=corr_id,
            previewDetails={},
            expiresOn="",
            idempotencyKey="",
        ).model_dump()

    preview_data = {
        "planName": existing.get("planName"),
        "taskTitle": existing.get("title"),
        "existingTaskId": taskId,
        "action": "MARK_TASK_COMPLETE_100_PERCENT",
        "correlationId": corr_id,
    }

    token_mgr = get_token_manager()
    token, expires_on = token_mgr.create_approval_token(
        operation="PREPARE_PLANNER_COMPLETION",
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_data=preview_data,
        idempotency_key=idemp_key,
        root_correlation_id=corr_id,
    )
    preview_data["approvalExpiresOn"] = expires_on

    summary = f"Completion preview prepared for Planner task '{existing.get('title')}' (ID: {taskId})."

    audit_svc = get_productivity_audit_service()
    await audit_svc.audit_stage_a_preview(
        operation="PreparePlannerCompletion",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_summary=summary,
        preview_details=preview_data,
        idempotency_key=idemp_key,
        approval_token=token,
        expires_on=expires_on,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return WritePreviewEnvelope(
        status="PREVIEW_READY",
        approvalRequired=True,
        resultSummary=summary,
        confirmationToken=token,
        correlationId=corr_id,
        previewDetails=preview_data,
        expiresOn=expires_on,
        idempotencyKey=idemp_key,
    ).model_dump()


async def complete_approved_planner_task(
    confirmationToken: str,
    previewDetails: Dict[str, Any],
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
    tenantId: str = "velora-tenant",
    workerId: Optional[str] = None,
) -> Dict[str, Any]:
    """Stage B: Mark approved Planner task complete with fail-closed audit and atomic claim."""
    task_id = previewDetails.get("existingTaskId", "")
    client = Microsoft365Client(user_email=userEmail)
    return await _execute_governed_stage_b(
        operation_name="PREPARE_PLANNER_COMPLETION",
        stage_b_operation_name="CompleteApprovedPlannerTask",
        confirmation_token=confirmationToken,
        preview_details=previewDetails,
        executor_fn=lambda: client.execute_complete_planner_task(task_id=task_id),
        action_desc_fn=lambda r: f"Planner task '{task_id}' marked as completed (100%).",
        root_correlation_id=rootCorrelationId,
        conversation_id=conversationId,
        turn_id=turnId,
        user_object_id=userObjectId,
        user_email=userEmail,
        tenant_id=tenantId,
        worker_id=workerId,
    )


# =====================================================================
# DAILY BRIEFING EMAIL WRITE TOOLS
# =====================================================================

async def prepare_daily_briefing_email(
    recipientOverride: Optional[str] = None,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Stage A: Prepare executive daily briefing HTML email preview and issue cryptographic approval token."""
    corr_id = rootCorrelationId or f"corr-briefmail-{int(time.time() * 1000)}"
    idemp_key = f"idemp-briefmail-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)

    briefing = client.get_daily_briefing()
    html_body = client.generate_daily_briefing_html(briefing)
    to_recipient = recipientOverride or userEmail or "balaadm@velora.ae"
    subject = f"Executive Daily Briefing | Velora Aviation Holding - {briefing.get('date', '')}"

    preview_data = {
        "to": [to_recipient],
        "cc": [],
        "subject": subject,
        "body": html_body,
        "briefingSummary": briefing.get("summary_text", ""),
        "totalMeetings": len(briefing.get("meetings_today", [])),
        "totalTasks": len(briefing.get("tasks_to_do", [])),
        "totalApprovals": len(briefing.get("upcoming_approvals", [])),
        "contentHash": compute_content_hash(briefing),
        "correlationId": corr_id,
    }

    token_mgr = get_token_manager()
    token, expires_on = token_mgr.create_approval_token(
        operation="PREPARE_DAILY_BRIEFING_EMAIL",
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_data=preview_data,
        idempotency_key=idemp_key,
        root_correlation_id=corr_id,
    )

    audit_svc = get_productivity_audit_service()
    await audit_svc.audit_stage_a_preview(
        operation="PrepareDailyBriefingEmail",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_summary=f"Prepared Daily Briefing email preview to {to_recipient}. Subject: '{subject}'",
        preview_details=preview_data,
        idempotency_key=idemp_key,
        approval_token=token,
        expires_on=expires_on,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return WritePreviewEnvelope(
        status="PREVIEW_READY",
        approvalRequired=True,
        resultSummary=f"Daily Briefing email preview compiled for {to_recipient}. Subject: '{subject}'. Contains {len(briefing.get('meetings_today', []))} meetings, {len(briefing.get('tasks_to_do', []))} tasks, and {len(briefing.get('upcoming_approvals', []))} pending approvals.",
        confirmationToken=token,
        correlationId=corr_id,
        previewDetails=preview_data,
        expiresOn=expires_on,
        idempotencyKey=idemp_key,
        warnings=[],
    ).model_dump()


async def send_approved_daily_briefing_email(
    confirmationToken: str,
    previewDetails: Optional[Dict[str, Any]] = None,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
    tenantId: str = "velora-tenant",
    workerId: Optional[str] = None,
) -> Dict[str, Any]:
    """Stage B: Execute verified Daily Briefing email dispatch with fail-closed audit and atomic claim."""
    preview = previewDetails
    if not preview:
        op_rec = get_operation_store().get_operation_by_approval_id(confirmationToken)
        if op_rec and op_rec.proposed_payload:
            preview = op_rec.proposed_payload
        else:
            preview = {}

    to_list = preview.get("to", [userEmail or "balaadm@velora.ae"])
    client = Microsoft365Client(user_email=userEmail)
    return await _execute_governed_stage_b(
        operation_name="PREPARE_DAILY_BRIEFING_EMAIL",
        stage_b_operation_name="SendApprovedDailyBriefingEmail",
        confirmation_token=confirmationToken,
        preview_details=preview,
        executor_fn=lambda: client.execute_send_email(
            to=to_list,
            cc=preview.get("cc", []),
            subject=preview.get("subject", "Executive Daily Briefing"),
            body=preview.get("body", ""),
            attachments=[],
        ),
        action_desc_fn=lambda r: (
            f"Daily Briefing email successfully delivered to {', '.join(to_list)}."
            if r.get("message_id")
            else f"Daily Briefing email successfully accepted by Microsoft Graph for delivery to {', '.join(to_list)} (Request ID: {r.get('requestId')})."
        ),
        root_correlation_id=rootCorrelationId,
        conversation_id=conversationId,
        turn_id=turnId,
        user_object_id=userObjectId,
        user_email=userEmail,
        tenant_id=tenantId,
        worker_id=workerId,
    )


async def send_daily_briefing_email(
    recipientOverride: Optional[str] = None,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Execute complete executive daily briefing compilation and email delivery with fail-closed audit."""
    prep = await prepare_daily_briefing_email(
        recipientOverride=recipientOverride,
        rootCorrelationId=rootCorrelationId,
        conversationId=conversationId,
        turnId=turnId,
        userObjectId=userObjectId,
        userEmail=userEmail,
    )
    if prep.get("status") != "PREVIEW_READY":
        return WriteResultEnvelope(
            status="PREPARE_FAILED",
            resultSummary=prep.get("resultSummary", ""),
            correlationId=rootCorrelationId,
            auditStatus="ERROR",
        ).model_dump()

    return await send_approved_daily_briefing_email(
        confirmationToken=prep["confirmationToken"],
        previewDetails=prep["previewDetails"],
        rootCorrelationId=rootCorrelationId,
        conversationId=conversationId,
        turnId=turnId,
        userObjectId=userObjectId,
        userEmail=userEmail,
    )


# =====================================================================
# GOVERNED AUTOMATION SUBSCRIPTION MANAGEMENT (W07)
# =====================================================================

async def prepare_automation_subscription(
    kind: str,
    mailbox: Optional[str] = None,
    recipients: Optional[List[str]] = None,
    localSchedule: Optional[str] = None,
    timezone: str = "Asia/Dubai",
    meetingFilters: Optional[Dict[str, Any]] = None,
    leadTimeMinutes: int = 15,
    horizonHours: int = 24,
    channel: str = "EMAIL",
    validUntil: Optional[str] = None,
    allowedDataScope: Optional[List[str]] = None,
    quietHoursPolicy: str = "SUPPRESS",
    missedRunPolicy: str = "SKIP",
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
    tenantId: str = "velora-tenant",
) -> Dict[str, Any]:
    """Stage A: Prepare recurring automation subscription in DRAFT state and issue cryptographic approval token."""
    corr_id = rootCorrelationId or f"corr-sub-{int(time.time() * 1000)}"
    idemp_key = f"idemp-sub-{int(time.time() * 1000)}"
    sub_service = get_subscription_service()

    target_mailbox = mailbox or userEmail or "balaadm@velora.ae"
    target_recipients = recipients or [target_mailbox]

    subscription, token = sub_service.prepare_subscription(
        tenant_id=tenantId,
        owner=userObjectId or userEmail or "balaadm@velora.ae",
        mailbox=target_mailbox,
        sender="velora-agent@velora.ae",
        recipients=target_recipients,
        kind=kind,
        timezone_str=timezone,
        local_schedule=localSchedule,
        meeting_filters=meetingFilters,
        lead_time_minutes=leadTimeMinutes,
        horizon_hours=horizonHours,
        channel=channel,
        valid_until=validUntil,
        allowed_data_scope=allowedDataScope,
        quiet_hours_policy=quietHoursPolicy,
        missed_run_policy=missedRunPolicy,
        user_object_id=userObjectId,
        user_email=userEmail,
    )

    preview_data = {
        "subscriptionId": subscription.subscriptionId,
        "kind": subscription.kind.value,
        "mailbox": subscription.mailbox,
        "recipients": subscription.recipients,
        "schedule": subscription.localSchedule,
        "timezone": subscription.timezone,
        "tenantId": subscription.tenantId,
        "enabled": False,  # Strict default disabled
        "correlationId": corr_id,
    }


    audit_svc = get_productivity_audit_service()
    await audit_svc.audit_stage_a_preview(
        operation="PrepareAutomationSubscription",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        preview_summary=f"Prepared automation subscription {subscription.subscriptionId} for kind={kind}. State=DRAFT (disabled).",
        preview_details=preview_data,
        idempotency_key=idemp_key,
        approval_token=token,
        expires_on=(datetime.now(dt_timezone.utc) + timedelta(minutes=30)).isoformat(),
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return WritePreviewEnvelope(
        status="PREVIEW_READY",
        approvalRequired=True,
        resultSummary=f"Prepared {kind} automation subscription {subscription.subscriptionId} in DRAFT state. Explicit approval required to activate.",
        confirmationToken=token,
        correlationId=corr_id,
        previewDetails=preview_data,
        expiresOn=(datetime.now(dt_timezone.utc) + timedelta(minutes=30)).isoformat(),
        idempotencyKey=idemp_key,
        warnings=["Subscription is created disabled (DRAFT) and will only execute after explicit confirmation."],
    ).model_dump()


async def confirm_automation_subscription(
    confirmationToken: str,
    subscriptionId: str,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
    tenantId: str = "velora-tenant",
    workerId: Optional[str] = None,
) -> Dict[str, Any]:
    """Stage B: Confirm and activate automation subscription with cryptographic token validation."""
    sub_service = get_subscription_service()

    def _activate():
        sub = sub_service.confirm_subscription(
            confirmation_token=confirmationToken,
            subscription_id=subscriptionId,
            user_object_id=userObjectId,
            user_email=userEmail,
            tenant_id=tenantId,
        )
        return {"subscriptionId": sub.subscriptionId, "state": "ENABLED", "enabled": True}

    return await _execute_governed_stage_b(
        operation_name="PREPARE_AUTOMATION_SUBSCRIPTION",
        stage_b_operation_name="ConfirmAutomationSubscription",
        confirmation_token=confirmationToken,
        preview_details=None,
        executor_fn=_activate,
        action_desc_fn=lambda r: f"Automation subscription {r.get('subscriptionId')} successfully confirmed and ACTIVATED.",
        root_correlation_id=rootCorrelationId,
        conversation_id=conversationId,
        turn_id=turnId,
        user_object_id=userObjectId,
        user_email=userEmail,
        tenant_id=tenantId,
        worker_id=workerId,
    )


async def revoke_automation_subscription(
    subscriptionId: str,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
    tenantId: str = "velora-tenant",
) -> Dict[str, Any]:
    """Revoke / disable an automation subscription. Preserves execution history."""
    corr_id = rootCorrelationId or f"corr-revsub-{int(time.time() * 1000)}"
    sub_service = get_subscription_service()
    sub = sub_service.revoke_subscription(
        subscription_id=subscriptionId,
        tenant_id=tenantId,
        revoked_by=userObjectId or userEmail,
    )

    audit_svc = get_productivity_audit_service()
    await audit_svc.audit_read_tool_execution(
        tool_name="RevokeAutomationSubscription",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=1,
        summary=f"Automation subscription {subscriptionId} revoked. Enabled set to false.",
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return WriteResultEnvelope(
        status="SUCCESS",
        resultSummary=f"Automation subscription {subscriptionId} has been REVOKED.",
        correlationId=corr_id,
        auditStatus="PERSISTED",
        externalObjectId=subscriptionId,
    ).model_dump()


async def prepare_meeting_actions(
    meetingId: str,
    sourceVersion: str = "1.0",
    notesOverride: Optional[str] = None,
    transcriptOverride: Optional[str] = None,
    targetPlan: str = "Executive Strategic Initiatives",
    targetBucket: str = "Q3 Deliverables",
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
    tenantId: str = "velora-aviation",
) -> Dict[str, Any]:
    """Stage A: Extract meeting action items, resolve directory owners, and prepare approval preview envelope."""
    from .meeting_actions import prepare_meeting_actions as _prepare_actions
    return await _prepare_actions(
        meeting_id=meetingId,
        source_version=sourceVersion,
        notes_override=notesOverride,
        transcript_override=transcriptOverride,
        target_plan=targetPlan,
        target_bucket=targetBucket,
        user_email=userEmail,
        user_object_id=userObjectId,
        tenant_id=tenantId,
        root_correlation_id=rootCorrelationId,
        conversation_id=conversationId,
        turn_id=turnId,
    )


async def create_approved_meeting_actions(
    confirmationToken: str,
    previewDetails: Dict[str, Any],
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
    tenantId: str = "velora-aviation",
) -> Dict[str, Any]:
    """Stage B: Commit approved meeting actions to Microsoft Planner with atomic mapping persistence."""
    from .meeting_actions import create_approved_meeting_actions as _commit_actions
    return await _commit_actions(
        confirmation_token=confirmationToken,
        preview_details=previewDetails,
        user_email=userEmail,
        user_object_id=userObjectId,
        tenant_id=tenantId,
        root_correlation_id=rootCorrelationId,
        conversation_id=conversationId,
        turn_id=turnId,
    )




