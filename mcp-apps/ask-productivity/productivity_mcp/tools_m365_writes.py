"""Microsoft 365 Two-Step Transaction Write Tools (12 Tools) for Velora Productivity Agent.

Enforces:
- Stage A (Prepare): Input validation, recipient resolution, preview generation, short-lived HMAC approval token, TRANSACTION_PREVIEW audit, approvalRequired=True, zero external write side-effects.
- Stage B (Execute): Token signature verification, user identity binding, preview checksum check, expiry check, duplicate idempotency check, Fail-Closed TRANSACTION_START audit, external M365 execution, TRANSACTION_RESULT audit, returns platform-confirmed external ID.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

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


def _get_write_actions_enabled() -> bool:
    """Emergency write switch from environment variable (Section 2.3)."""
    return os.getenv("VeloraWriteActionsEnabled", "true").lower() in ("true", "1", "yes")


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
    corr_id = rootCorrelationId or f"corr-mail-{int(time.time() * 1000)}"
    idemp_key = f"idemp-email-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)

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
        "actingUser": userEmail or "balaadm@velora.ae",
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
) -> Dict[str, Any]:
    """Stage B: Validate approval token, fail-closed audit check, and execute approved email dispatch."""
    start_ts = datetime.now(timezone.utc).isoformat()
    corr_id = rootCorrelationId or previewDetails.get("correlationId") or f"corr-exec-{int(time.time() * 1000)}"

    # Emergency switch check
    if not _get_write_actions_enabled():
        return WriteResultEnvelope(
            status="POLICY_BLOCKED",
            resultSummary="Email dispatch is temporarily suspended by enterprise VeloraWriteActionsEnabled switch.",
            correlationId=corr_id,
            auditStatus="BLOCKED",
            warnings=["Write actions disabled in current environment."],
        ).model_dump()

    # 1. Cryptographic token & integrity validation
    token_mgr = get_token_manager()
    is_valid, error_reason, token_payload = token_mgr.verify_approval_token(
        token=confirmationToken,
        expected_operation="PREPARE_EMAIL",
        user_object_id=userObjectId,
        user_email=userEmail,
        current_preview_data=previewDetails,
    )
    if not is_valid:
        return WriteResultEnvelope(
            status="TOKEN_INVALID",
            resultSummary=f"Action blocked: {error_reason}",
            correlationId=corr_id,
            auditStatus="REJECTED",
            warnings=[error_reason],
        ).model_dump()

    idemp_key = token_payload.get("idk", f"idemp-email-{int(time.time() * 1000)}")
    summary = f"Sending approved email to {', '.join(previewDetails.get('to', []))}"

    # 2. Strict Fail-Closed TRANSACTION_START Dataverse audit
    audit_svc = get_productivity_audit_service()
    start_res = await audit_svc.start_stage_b_write_fail_closed(
        operation="SendApprovedEmail",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        idempotency_key=idemp_key,
        approval_token=confirmationToken,
        summary=summary,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    if not start_res.get("may_proceed"):
        return WriteResultEnvelope(
            status="FAIL_CLOSED_BLOCKED",
            resultSummary=f"Action aborted: {start_res.get('error')}",
            correlationId=corr_id,
            auditStatus="AUDIT_FAILED_WRITE_BLOCKED",
            warnings=["Fail-closed write policy: No external action was taken because the audit record could not be secured."],
        ).model_dump()

    audit_rec_id = start_res.get("audit_record_id", "")
    inv_id = start_res.get("invocation_id", f"inv-{idemp_key}")

    # 3. Call Microsoft 365 Connector
    client = Microsoft365Client(user_email=userEmail)
    try:
        res = client.execute_send_email(
            to=previewDetails.get("to", []),
            cc=previewDetails.get("cc", []),
            subject=previewDetails.get("subject", ""),
            body=previewDetails.get("body", ""),
            attachments=previewDetails.get("attachments", []),
        )
        msg_id = res["message_id"]
        evidence_link = res["web_link"]

        # 4. Complete Audit (TRANSACTION_RESULT)
        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="SUCCESS",
            external_object_id=msg_id,
            evidence_link=evidence_link,
            summary=f"Successfully sent email to {', '.join(previewDetails.get('to', []))}. Message ID: {msg_id}",
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=userEmail,
            operation="SendApprovedEmail",
            idempotency_key=idemp_key,
        )

        return WriteResultEnvelope(
            status="SUCCESS",
            resultSummary=f"Email successfully sent to {', '.join(previewDetails.get('to', []))}. Outlook Message ID: {msg_id}.",
            externalObjectId=msg_id,
            evidenceLink=evidence_link,
            correlationId=corr_id,
            auditStatus="PERSISTED",
        ).model_dump()

    except Exception as ex:
        # Audit failure
        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="ERROR",
            error_msg=str(ex),
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=userEmail,
            operation="SendApprovedEmail",
            idempotency_key=idemp_key,
        )
        return WriteResultEnvelope(
            status="EXECUTION_ERROR",
            resultSummary=f"Failed to dispatch email via Outlook: {str(ex)}",
            correlationId=corr_id,
            auditStatus="PERSISTED_ERROR",
            warnings=[str(ex)],
        ).model_dump()


async def prepare_email_reply(
    threadId: str,
    body: str,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Stage A: Prepare a reply to an existing email thread."""
    client = Microsoft365Client(user_email=userEmail)
    thread = client.get_mail_thread(thread_id=threadId)
    first_msg = thread[0] if thread else {"subject": "Re: Executive Thread", "from": "leadership@velora.ae"}

    return await prepare_email(
        to=[first_msg.get("from", "leadership@velora.ae")],
        subject=f"Re: {first_msg.get('subject', 'Follow-up')}",
        body=body,
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
    client = Microsoft365Client(user_email=userEmail)

    resolved_att, unres_att, ext_att = client.resolve_recipients(attendees)
    conflicts_info = client.check_availability(attendees=resolved_att, start_time=startTime, end_time=endTime)

    warnings = []
    if unres_att:
        warnings.append(f"Unresolved attendees: {', '.join(unres_att)}")
    if conflicts_info.get("has_conflict"):
        warnings.append(f"Scheduling conflict detected for {len(conflicts_info.get('conflicts', []))} participant(s).")

    preview_data = {
        "organizer": userEmail or "balaadm@velora.ae",
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
) -> Dict[str, Any]:
    """Stage B: Validate token, fail-closed audit check, and create approved meeting."""
    start_ts = datetime.now(timezone.utc).isoformat()
    corr_id = rootCorrelationId or previewDetails.get("correlationId") or f"corr-cal-{int(time.time() * 1000)}"

    if not _get_write_actions_enabled():
        return WriteResultEnvelope(
            status="POLICY_BLOCKED",
            resultSummary="Meeting creation is temporarily suspended by enterprise switch.",
            correlationId=corr_id,
            auditStatus="BLOCKED",
        ).model_dump()

    token_mgr = get_token_manager()
    is_valid, error_reason, token_payload = token_mgr.verify_approval_token(
        token=confirmationToken,
        expected_operation="PREPARE_MEETING_CREATION",
        user_object_id=userObjectId,
        user_email=userEmail,
        current_preview_data=previewDetails,
    )
    if not is_valid:
        return WriteResultEnvelope(
            status="TOKEN_INVALID",
            resultSummary=f"Action blocked: {error_reason}",
            correlationId=corr_id,
            auditStatus="REJECTED",
        ).model_dump()

    idemp_key = token_payload.get("idk", f"idemp-meet-{int(time.time() * 1000)}")
    summary = f"Creating approved meeting: '{previewDetails.get('subject')}'"

    audit_svc = get_productivity_audit_service()
    start_res = await audit_svc.start_stage_b_write_fail_closed(
        operation="CreateApprovedMeeting",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        idempotency_key=idemp_key,
        approval_token=confirmationToken,
        summary=summary,
        conversation_id=conversationId,
        turn_id=turnId,
    )
    if not start_res.get("may_proceed"):
        return WriteResultEnvelope(
            status="FAIL_CLOSED_BLOCKED",
            resultSummary=f"Action aborted: {start_res.get('error')}",
            correlationId=corr_id,
            auditStatus="AUDIT_FAILED_WRITE_BLOCKED",
        ).model_dump()

    audit_rec_id = start_res.get("audit_record_id", "")
    inv_id = start_res.get("invocation_id", f"inv-{idemp_key}")

    client = Microsoft365Client(user_email=userEmail)
    try:
        res = client.execute_create_meeting(
            subject=previewDetails.get("subject", ""),
            attendees=previewDetails.get("attendees", []),
            start_time=previewDetails.get("startTime", ""),
            end_time=previewDetails.get("endTime", ""),
            time_zone=previewDetails.get("timeZone", "Asia/Dubai"),
            location=previewDetails.get("location", "Teams Meeting"),
            body=previewDetails.get("body", ""),
        )
        evt_id = res["event_id"]
        evidence_link = res["web_link"]

        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="SUCCESS",
            external_object_id=evt_id,
            evidence_link=evidence_link,
            summary=f"Successfully created calendar meeting '{previewDetails.get('subject')}'. Event ID: {evt_id}",
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=userEmail,
            operation="CreateApprovedMeeting",
            idempotency_key=idemp_key,
        )

        return WriteResultEnvelope(
            status="SUCCESS",
            resultSummary=f"Meeting '{previewDetails.get('subject')}' scheduled successfully. Outlook Event ID: {evt_id}.",
            externalObjectId=evt_id,
            evidenceLink=evidence_link,
            correlationId=corr_id,
            auditStatus="PERSISTED",
        ).model_dump()
    except Exception as ex:
        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="ERROR",
            error_msg=str(ex),
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=userEmail,
            operation="CreateApprovedMeeting",
            idempotency_key=idemp_key,
        )
        return WriteResultEnvelope(
            status="EXECUTION_ERROR",
            resultSummary=f"Failed to create meeting: {str(ex)}",
            correlationId=corr_id,
            auditStatus="PERSISTED_ERROR",
        ).model_dump()


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
) -> Dict[str, Any]:
    """Stage B: Execute approved meeting updates."""
    start_ts = datetime.now(timezone.utc).isoformat()
    corr_id = rootCorrelationId or previewDetails.get("correlationId") or f"corr-cal-{int(time.time() * 1000)}"

    token_mgr = get_token_manager()
    is_valid, error_reason, token_payload = token_mgr.verify_approval_token(
        token=confirmationToken,
        expected_operation="PREPARE_MEETING_UPDATE",
        user_object_id=userObjectId,
        user_email=userEmail,
        current_preview_data=previewDetails,
    )
    if not is_valid:
        return WriteResultEnvelope(status="TOKEN_INVALID", resultSummary=error_reason, correlationId=corr_id).model_dump()

    idemp_key = token_payload.get("idk", f"idemp-calupd-{int(time.time() * 1000)}")
    event_id = previewDetails.get("existingEventId", "")

    audit_svc = get_productivity_audit_service()
    start_res = await audit_svc.start_stage_b_write_fail_closed(
        operation="UpdateApprovedMeeting",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        idempotency_key=idemp_key,
        approval_token=confirmationToken,
        summary=f"Updating meeting '{event_id}'",
        conversation_id=conversationId,
        turn_id=turnId,
    )
    if not start_res.get("may_proceed"):
        return WriteResultEnvelope(status="FAIL_CLOSED_BLOCKED", resultSummary=start_res.get("error", ""), correlationId=corr_id).model_dump()

    audit_rec_id = start_res.get("audit_record_id", "")
    inv_id = start_res.get("invocation_id", f"inv-{idemp_key}")

    client = Microsoft365Client(user_email=userEmail)
    try:
        res = client.execute_update_meeting(event_id=event_id, updates=previewDetails)
        evidence_link = res["web_link"]

        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="SUCCESS",
            external_object_id=event_id,
            evidence_link=evidence_link,
            summary=f"Successfully updated meeting '{event_id}'.",
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=userEmail,
            operation="UpdateApprovedMeeting",
            idempotency_key=idemp_key,
        )
        return WriteResultEnvelope(
            status="SUCCESS",
            resultSummary=f"Meeting '{event_id}' updated successfully.",
            externalObjectId=event_id,
            evidenceLink=evidence_link,
            correlationId=corr_id,
        ).model_dump()
    except Exception as ex:
        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="ERROR",
            error_msg=str(ex),
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=userEmail,
            operation="UpdateApprovedMeeting",
            idempotency_key=idemp_key,
        )
        return WriteResultEnvelope(status="EXECUTION_ERROR", resultSummary=str(ex), correlationId=corr_id).model_dump()


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
) -> Dict[str, Any]:
    """Stage B: Execute approved meeting cancellation."""
    start_ts = datetime.now(timezone.utc).isoformat()
    corr_id = rootCorrelationId or previewDetails.get("correlationId") or f"corr-cal-{int(time.time() * 1000)}"

    token_mgr = get_token_manager()
    is_valid, error_reason, token_payload = token_mgr.verify_approval_token(
        token=confirmationToken,
        expected_operation="PREPARE_MEETING_CANCELLATION",
        user_object_id=userObjectId,
        user_email=userEmail,
        current_preview_data=previewDetails,
    )
    if not is_valid:
        return WriteResultEnvelope(status="TOKEN_INVALID", resultSummary=error_reason, correlationId=corr_id).model_dump()

    idemp_key = token_payload.get("idk", f"idemp-calcanc-{int(time.time() * 1000)}")
    event_id = previewDetails.get("existingEventId", "")

    audit_svc = get_productivity_audit_service()
    start_res = await audit_svc.start_stage_b_write_fail_closed(
        operation="CancelApprovedMeeting",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        idempotency_key=idemp_key,
        approval_token=confirmationToken,
        summary=f"Cancelling meeting '{event_id}'",
        conversation_id=conversationId,
        turn_id=turnId,
    )
    if not start_res.get("may_proceed"):
        return WriteResultEnvelope(status="FAIL_CLOSED_BLOCKED", resultSummary=start_res.get("error", ""), correlationId=corr_id).model_dump()

    audit_rec_id = start_res.get("audit_record_id", "")
    inv_id = start_res.get("invocation_id", f"inv-{idemp_key}")

    client = Microsoft365Client(user_email=userEmail)
    try:
        client.execute_cancel_meeting(event_id=event_id)

        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="SUCCESS",
            external_object_id=event_id,
            evidence_link="",
            summary=f"Successfully cancelled meeting '{event_id}'.",
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=userEmail,
            operation="CancelApprovedMeeting",
            idempotency_key=idemp_key,
        )
        return WriteResultEnvelope(
            status="SUCCESS",
            resultSummary=f"Meeting '{event_id}' was cancelled.",
            externalObjectId=event_id,
            correlationId=corr_id,
        ).model_dump()
    except Exception as ex:
        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="ERROR",
            error_msg=str(ex),
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=userEmail,
            operation="CancelApprovedMeeting",
            idempotency_key=idemp_key,
        )
        return WriteResultEnvelope(status="EXECUTION_ERROR", resultSummary=str(ex), correlationId=corr_id).model_dump()


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
) -> Dict[str, Any]:
    """Stage B: Dispatch approved Teams direct chat message."""
    start_ts = datetime.now(timezone.utc).isoformat()
    corr_id = rootCorrelationId or previewDetails.get("correlationId") or f"corr-tm-{int(time.time() * 1000)}"

    token_mgr = get_token_manager()
    is_valid, error_reason, token_payload = token_mgr.verify_approval_token(
        token=confirmationToken,
        expected_operation="PREPARE_TEAMS_CHAT_MESSAGE",
        user_object_id=userObjectId,
        user_email=userEmail,
        current_preview_data=previewDetails,
    )
    if not is_valid:
        return WriteResultEnvelope(status="TOKEN_INVALID", resultSummary=error_reason, correlationId=corr_id).model_dump()

    idemp_key = token_payload.get("idk", f"idemp-tmchat-{int(time.time() * 1000)}")
    chat_id = previewDetails.get("chatId", "")
    content = previewDetails.get("messageContent", "")

    audit_svc = get_productivity_audit_service()
    start_res = await audit_svc.start_stage_b_write_fail_closed(
        operation="SendApprovedTeamsChatMessage",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        idempotency_key=idemp_key,
        approval_token=confirmationToken,
        summary=f"Posting Teams message to chat '{chat_id}'",
        conversation_id=conversationId,
        turn_id=turnId,
    )
    if not start_res.get("may_proceed"):
        return WriteResultEnvelope(status="FAIL_CLOSED_BLOCKED", resultSummary=start_res.get("error", ""), correlationId=corr_id).model_dump()

    audit_rec_id = start_res.get("audit_record_id", "")
    inv_id = start_res.get("invocation_id", f"inv-{idemp_key}")

    client = Microsoft365Client(user_email=userEmail)
    try:
        res = client.execute_post_teams_message(content=content, chat_id=chat_id)
        msg_id = res["message_id"]
        evidence_link = res["web_link"]

        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="SUCCESS",
            external_object_id=msg_id,
            evidence_link=evidence_link,
            summary=f"Successfully sent chat message to '{chat_id}'. Message ID: {msg_id}",
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=userEmail,
            operation="SendApprovedTeamsChatMessage",
            idempotency_key=idemp_key,
        )
        return WriteResultEnvelope(
            status="SUCCESS",
            resultSummary=f"Message posted to Teams chat '{chat_id}'. Message ID: {msg_id}.",
            externalObjectId=msg_id,
            evidenceLink=evidence_link,
            correlationId=corr_id,
        ).model_dump()
    except Exception as ex:
        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="ERROR",
            error_msg=str(ex),
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=userEmail,
            operation="SendApprovedTeamsChatMessage",
            idempotency_key=idemp_key,
        )
        return WriteResultEnvelope(status="EXECUTION_ERROR", resultSummary=str(ex), correlationId=corr_id).model_dump()


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
) -> Dict[str, Any]:
    """Stage B: Dispatch approved Teams channel post."""
    start_ts = datetime.now(timezone.utc).isoformat()
    corr_id = rootCorrelationId or previewDetails.get("correlationId") or f"corr-tm-{int(time.time() * 1000)}"

    token_mgr = get_token_manager()
    is_valid, error_reason, token_payload = token_mgr.verify_approval_token(
        token=confirmationToken,
        expected_operation="PREPARE_TEAMS_CHANNEL_POST",
        user_object_id=userObjectId,
        user_email=userEmail,
        current_preview_data=previewDetails,
    )
    if not is_valid:
        return WriteResultEnvelope(status="TOKEN_INVALID", resultSummary=error_reason, correlationId=corr_id).model_dump()

    idemp_key = token_payload.get("idk", f"idemp-tmchan-{int(time.time() * 1000)}")
    team = previewDetails.get("teamName", "")
    chan = previewDetails.get("channelName", "")
    content = previewDetails.get("messageContent", "")

    audit_svc = get_productivity_audit_service()
    start_res = await audit_svc.start_stage_b_write_fail_closed(
        operation="SendApprovedTeamsChannelPost",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        idempotency_key=idemp_key,
        approval_token=confirmationToken,
        summary=f"Posting to Teams channel '{team} > {chan}'",
        conversation_id=conversationId,
        turn_id=turnId,
    )
    if not start_res.get("may_proceed"):
        return WriteResultEnvelope(status="FAIL_CLOSED_BLOCKED", resultSummary=start_res.get("error", ""), correlationId=corr_id).model_dump()

    audit_rec_id = start_res.get("audit_record_id", "")
    inv_id = start_res.get("invocation_id", f"inv-{idemp_key}")

    client = Microsoft365Client(user_email=userEmail)
    try:
        res = client.execute_post_teams_message(content=content, team_name=team, channel_name=chan)
        msg_id = res["message_id"]
        evidence_link = res["web_link"]

        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="SUCCESS",
            external_object_id=msg_id,
            evidence_link=evidence_link,
            summary=f"Successfully posted to '{team} > {chan}'. Message ID: {msg_id}",
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=userEmail,
            operation="SendApprovedTeamsChannelPost",
            idempotency_key=idemp_key,
        )
        return WriteResultEnvelope(
            status="SUCCESS",
            resultSummary=f"Message posted to '{team} > {chan}'. Teams Message ID: {msg_id}.",
            externalObjectId=msg_id,
            evidenceLink=evidence_link,
            correlationId=corr_id,
        ).model_dump()
    except Exception as ex:
        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="ERROR",
            error_msg=str(ex),
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=userEmail,
            operation="SendApprovedTeamsChannelPost",
            idempotency_key=idemp_key,
        )
        return WriteResultEnvelope(status="EXECUTION_ERROR", resultSummary=str(ex), correlationId=corr_id).model_dump()


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
        "startDate": datetime.now(timezone.utc).isoformat(),
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
) -> Dict[str, Any]:
    """Stage B: Create approved Planner task."""
    start_ts = datetime.now(timezone.utc).isoformat()
    corr_id = rootCorrelationId or previewDetails.get("correlationId") or f"corr-pln-{int(time.time() * 1000)}"

    token_mgr = get_token_manager()
    is_valid, error_reason, token_payload = token_mgr.verify_approval_token(
        token=confirmationToken,
        expected_operation="PREPARE_PLANNER_TASK",
        user_object_id=userObjectId,
        user_email=userEmail,
        current_preview_data=previewDetails,
    )
    if not is_valid:
        return WriteResultEnvelope(status="TOKEN_INVALID", resultSummary=error_reason, correlationId=corr_id).model_dump()

    idemp_key = token_payload.get("idk", f"idemp-plntsk-{int(time.time() * 1000)}")
    plan = previewDetails.get("planName", "")
    bucket = previewDetails.get("bucketName", "")
    title = previewDetails.get("taskTitle", "")

    audit_svc = get_productivity_audit_service()
    start_res = await audit_svc.start_stage_b_write_fail_closed(
        operation="CreateApprovedPlannerTask",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        idempotency_key=idemp_key,
        approval_token=confirmationToken,
        summary=f"Creating Planner task '{title}'",
        conversation_id=conversationId,
        turn_id=turnId,
    )
    if not start_res.get("may_proceed"):
        return WriteResultEnvelope(status="FAIL_CLOSED_BLOCKED", resultSummary=start_res.get("error", ""), correlationId=corr_id).model_dump()

    audit_rec_id = start_res.get("audit_record_id", "")
    inv_id = start_res.get("invocation_id", f"inv-{idemp_key}")

    client = Microsoft365Client(user_email=userEmail)
    try:
        res = client.execute_create_planner_task(
            plan_name=plan,
            bucket_name=bucket,
            title=title,
            description=previewDetails.get("description", ""),
            assignees=previewDetails.get("assignees", []),
            due_date=previewDetails.get("dueDate"),
            priority=previewDetails.get("priority", "Medium"),
        )
        task_id = res["task_id"]
        evidence_link = res["web_link"]

        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="SUCCESS",
            external_object_id=task_id,
            evidence_link=evidence_link,
            summary=f"Successfully created Planner task '{title}'. Task ID: {task_id}",
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=userEmail,
            operation="CreateApprovedPlannerTask",
            idempotency_key=idemp_key,
        )
        return WriteResultEnvelope(
            status="SUCCESS",
            resultSummary=f"Planner task '{title}' created successfully in plan '{plan}'. Task ID: {task_id}.",
            externalObjectId=task_id,
            evidenceLink=evidence_link,
            correlationId=corr_id,
        ).model_dump()
    except Exception as ex:
        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="ERROR",
            error_msg=str(ex),
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=userEmail,
            operation="CreateApprovedPlannerTask",
            idempotency_key=idemp_key,
        )
        return WriteResultEnvelope(status="EXECUTION_ERROR", resultSummary=str(ex), correlationId=corr_id).model_dump()


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
) -> Dict[str, Any]:
    """Stage B: Execute approved Planner task update."""
    start_ts = datetime.now(timezone.utc).isoformat()
    corr_id = rootCorrelationId or previewDetails.get("correlationId") or f"corr-pln-{int(time.time() * 1000)}"

    token_mgr = get_token_manager()
    is_valid, error_reason, token_payload = token_mgr.verify_approval_token(
        token=confirmationToken,
        expected_operation="PREPARE_PLANNER_TASK_UPDATE",
        user_object_id=userObjectId,
        user_email=userEmail,
        current_preview_data=previewDetails,
    )
    if not is_valid:
        return WriteResultEnvelope(status="TOKEN_INVALID", resultSummary=error_reason, correlationId=corr_id).model_dump()

    idemp_key = token_payload.get("idk", f"idemp-plnupd-{int(time.time() * 1000)}")
    task_id = previewDetails.get("existingTaskId", "")

    audit_svc = get_productivity_audit_service()
    start_res = await audit_svc.start_stage_b_write_fail_closed(
        operation="UpdateApprovedPlannerTask",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        idempotency_key=idemp_key,
        approval_token=confirmationToken,
        summary=f"Updating task '{task_id}'",
        conversation_id=conversationId,
        turn_id=turnId,
    )
    if not start_res.get("may_proceed"):
        return WriteResultEnvelope(status="FAIL_CLOSED_BLOCKED", resultSummary=start_res.get("error", ""), correlationId=corr_id).model_dump()

    audit_rec_id = start_res.get("audit_record_id", "")
    inv_id = start_res.get("invocation_id", f"inv-{idemp_key}")

    client = Microsoft365Client(user_email=userEmail)
    try:
        res = client.execute_update_planner_task(task_id=task_id, updates=previewDetails)
        evidence_link = res["web_link"]

        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="SUCCESS",
            external_object_id=task_id,
            evidence_link=evidence_link,
            summary=f"Successfully updated Planner task '{task_id}'.",
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=userEmail,
            operation="UpdateApprovedPlannerTask",
            idempotency_key=idemp_key,
        )
        return WriteResultEnvelope(
            status="SUCCESS",
            resultSummary=f"Planner task '{task_id}' updated successfully.",
            externalObjectId=task_id,
            evidenceLink=evidence_link,
            correlationId=corr_id,
        ).model_dump()
    except Exception as ex:
        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="ERROR",
            error_msg=str(ex),
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=userEmail,
            operation="UpdateApprovedPlannerTask",
            idempotency_key=idemp_key,
        )
        return WriteResultEnvelope(status="EXECUTION_ERROR", resultSummary=str(ex), correlationId=corr_id).model_dump()


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
) -> Dict[str, Any]:
    """Stage B: Mark approved Planner task complete."""
    start_ts = datetime.now(timezone.utc).isoformat()
    corr_id = rootCorrelationId or previewDetails.get("correlationId") or f"corr-pln-{int(time.time() * 1000)}"

    token_mgr = get_token_manager()
    is_valid, error_reason, token_payload = token_mgr.verify_approval_token(
        token=confirmationToken,
        expected_operation="PREPARE_PLANNER_COMPLETION",
        user_object_id=userObjectId,
        user_email=userEmail,
        current_preview_data=previewDetails,
    )
    if not is_valid:
        return WriteResultEnvelope(status="TOKEN_INVALID", resultSummary=error_reason, correlationId=corr_id).model_dump()

    idemp_key = token_payload.get("idk", f"idemp-plncmp-{int(time.time() * 1000)}")
    task_id = previewDetails.get("existingTaskId", "")

    audit_svc = get_productivity_audit_service()
    start_res = await audit_svc.start_stage_b_write_fail_closed(
        operation="CompleteApprovedPlannerTask",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        idempotency_key=idemp_key,
        approval_token=confirmationToken,
        summary=f"Marking task '{task_id}' complete",
        conversation_id=conversationId,
        turn_id=turnId,
    )
    if not start_res.get("may_proceed"):
        return WriteResultEnvelope(status="FAIL_CLOSED_BLOCKED", resultSummary=start_res.get("error", ""), correlationId=corr_id).model_dump()

    audit_rec_id = start_res.get("audit_record_id", "")
    inv_id = start_res.get("invocation_id", f"inv-{idemp_key}")

    client = Microsoft365Client(user_email=userEmail)
    try:
        res = client.execute_complete_planner_task(task_id=task_id)
        evidence_link = res["web_link"]

        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="SUCCESS",
            external_object_id=task_id,
            evidence_link=evidence_link,
            summary=f"Successfully completed Planner task '{task_id}'.",
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=userEmail,
            operation="CompleteApprovedPlannerTask",
            idempotency_key=idemp_key,
        )
        return WriteResultEnvelope(
            status="SUCCESS",
            resultSummary=f"Planner task '{task_id}' marked as completed (100%).",
            externalObjectId=task_id,
            evidenceLink=evidence_link,
            correlationId=corr_id,
        ).model_dump()
    except Exception as ex:
        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="ERROR",
            error_msg=str(ex),
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=userEmail,
            operation="CompleteApprovedPlannerTask",
            idempotency_key=idemp_key,
        )
        return WriteResultEnvelope(status="EXECUTION_ERROR", resultSummary=str(ex), correlationId=corr_id).model_dump()


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
) -> Dict[str, Any]:
    """Stage B: Execute verified Daily Briefing email dispatch with fail-closed audit protection."""
    start_ts = datetime.now(timezone.utc).isoformat()
    token_mgr = get_token_manager()
    is_valid, error_reason, token_payload = token_mgr.verify_approval_token(
        token=confirmationToken,
        expected_operation="PREPARE_DAILY_BRIEFING_EMAIL",
        user_object_id=userObjectId,
        user_email=userEmail,
        current_preview_data=previewDetails,
    )
    if not is_valid:
        return WriteResultEnvelope(
            status="TOKEN_INVALID",
            resultSummary=f"Action blocked: {error_reason}",
            correlationId=rootCorrelationId,
            auditStatus="REJECTED",
            warnings=[error_reason],
        ).model_dump()

    preview = previewDetails or token_payload.get("preview", {})
    corr_id = preview.get("correlationId") or rootCorrelationId
    idemp_key = token_payload.get("idk", f"idemp-briefmail-{int(time.time() * 1000)}")

    audit_svc = get_productivity_audit_service()
    start_res = await audit_svc.start_stage_b_write_fail_closed(
        operation="SendApprovedDailyBriefingEmail",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        idempotency_key=idemp_key,
        approval_token=confirmationToken,
        summary=f"Dispatching Daily Briefing email to {preview.get('to')}",
        conversation_id=conversationId,
        turn_id=turnId,
    )
    if not start_res.get("may_proceed"):
        return WriteResultEnvelope(
            status="FAIL_CLOSED_BLOCKED",
            resultSummary=f"Action aborted: {start_res.get('error')}",
            correlationId=corr_id,
            auditStatus="AUDIT_FAILED_WRITE_BLOCKED",
            warnings=["Fail-closed write policy: No external action was taken because the audit record could not be secured."],
        ).model_dump()

    audit_rec_id = start_res.get("audit_record_id", "")
    inv_id = start_res.get("invocation_id", f"inv-{idemp_key}")

    client = Microsoft365Client(user_email=userEmail)
    try:
        res = client.execute_send_email(
            to=preview.get("to", [userEmail or "balaadm@velora.ae"]),
            cc=preview.get("cc", []),
            subject=preview.get("subject", "Executive Daily Briefing"),
            body=preview.get("body", ""),
            attachments=[],
        )
        msg_id = res["message_id"]
        evidence_link = res["web_link"]

        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="SUCCESS",
            external_object_id=msg_id,
            evidence_link=evidence_link,
            summary=f"Successfully dispatched Daily Briefing email to {', '.join(preview.get('to', []))}.",
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=userEmail,
            operation="SendApprovedDailyBriefingEmail",
            idempotency_key=idemp_key,
        )
        return WriteResultEnvelope(
            status="SUCCESS",
            resultSummary=f"Daily Briefing email successfully delivered to {', '.join(preview.get('to', []))}.",
            externalObjectId=msg_id,
            evidenceLink=evidence_link,
            correlationId=corr_id,
            auditStatus="PERSISTED",
        ).model_dump()
    except Exception as ex:
        await audit_svc.complete_stage_b_write(
            audit_record_id=audit_rec_id,
            invocation_id=inv_id,
            outcome="ERROR",
            error_msg=str(ex),
            start_time=start_ts,
            root_correlation_id=corr_id,
            user_email=userEmail,
            operation="SendApprovedDailyBriefingEmail",
            idempotency_key=idemp_key,
        )
        return WriteResultEnvelope(
            status="EXECUTION_ERROR",
            resultSummary=str(ex),
            correlationId=corr_id,
            auditStatus="PERSISTED_ERROR",
        ).model_dump()


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


