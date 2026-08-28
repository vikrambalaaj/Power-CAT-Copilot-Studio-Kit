"""FastMCP and FastAPI Service for Velora Productivity Agent."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .models import HandoffRequest, HandoffResponse
from .tools_m365_reads import (
    search_mail,
    get_mail_thread,
    summarize_priority_mail,
    find_mail_follow_ups,
    list_calendar_events,
    get_meeting_details,
    check_availability,
    get_meeting_context,
    search_teams_messages,
    get_channel_context,
    get_chat_context,
    find_teams_follow_ups,
    list_my_planner_tasks,
    list_plan_tasks,
    get_planner_task,
    find_overdue_tasks,
    get_daily_executive_briefing,
)
from .tools_m365_writes import (
    prepare_email,
    send_approved_email,
    prepare_email_reply,
    send_approved_email_reply,
    prepare_meeting_creation,
    create_approved_meeting,
    prepare_meeting_update,
    update_approved_meeting,
    prepare_meeting_cancellation,
    cancel_approved_meeting,
    prepare_teams_chat_message,
    send_approved_teams_chat_message,
    prepare_teams_channel_post,
    send_approved_teams_channel_post,
    prepare_planner_task,
    create_approved_planner_task,
    prepare_planner_task_update,
    update_approved_planner_task,
    prepare_planner_completion,
    complete_approved_planner_task,
    prepare_daily_briefing_email,
    send_approved_daily_briefing_email,
    send_daily_briefing_email,
)

# Optional FastAPI instantiation
try:
    from fastapi import FastAPI
    app = FastAPI(
        title="Velora Productivity Agent MCP",
        description="Authorized Microsoft 365, Work IQ, Outlook, Calendar, Teams, and Planner Connected Agent.",
        version="1.0.0",
    )
except ImportError:
    class MockFastAPI:
        def __init__(self, *args, **kwargs): pass
        def get(self, *args, **kwargs): return lambda f: f
        def post(self, *args, **kwargs): return lambda f: f
    app = MockFastAPI()


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    return {
        "status": "HEALTHY",
        "service": "Velora Productivity Agent",
        "version": "1.0.0",
        "capabilities": ["Mail", "Calendar", "Teams", "Planner", "WorkIQ", "DataverseAudit"],
        "audit_table": "cre2f_veloraagentauditlog",
    }


# --- Hand-off Router Endpoint (Section 12 & 13) ---

@app.post("/handoff")
async def handle_parent_handoff(request: HandoffRequest) -> HandoffResponse:
    """Entry point for Copilot Studio Parent to Connected Productivity Agent calls."""
    op = request.operation.upper()
    params = request.parameters
    corr_id = request.rootCorrelationId
    conv_id = request.conversationId
    turn_id = request.turnId
    uid = request.userObjectId
    email = request.userEmail

    try:
        if op in ("SEARCH_MAIL", "SEARCHMAIL"):
            res = await search_mail(
                query=params.get("query", ""),
                maximumResults=params.get("maximumResults", 10),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res["structuredResult"],
            )

        elif op in ("PREPARE_EMAIL", "PREPAREEMAIL"):
            res = await prepare_email(
                to=params.get("recipientNames") or params.get("to") or ["financeleadership@velora.ae"],
                subject=params.get("subject", "Executive Follow-up"),
                body=params.get("body", params.get("bodySource", "")),
                cc=params.get("cc"),
                attachments=params.get("attachments"),
                sensitivity=request.dataClassification or "CONFIDENTIAL",
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("SEND_APPROVED_EMAIL", "SENDAPPROVEDEMAIL"):
            res = await send_approved_email(
                confirmationToken=params.get("confirmationToken", ""),
                previewDetails=params.get("previewDetails", {}),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("PREPARE_MEETING_CREATION", "PREPAREMEETING"):
            res = await prepare_meeting_creation(
                subject=params.get("subject", "Executive Strategy Alignment"),
                attendees=params.get("attendees", ["leadership@velora.ae"]),
                startTime=params.get("startTime", "2026-08-27T10:00:00Z"),
                endTime=params.get("endTime", "2026-08-27T11:00:00Z"),
                timeZone=request.userTimezone or "Asia/Dubai",
                location=params.get("location", "Microsoft Teams Meeting"),
                body=params.get("body", ""),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("CREATE_APPROVED_MEETING", "CREATEAPPROVEDMEETING"):
            res = await create_approved_meeting(
                confirmationToken=params.get("confirmationToken", ""),
                previewDetails=params.get("previewDetails", {}),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("GET_DAILY_EXECUTIVE_BRIEFING", "GETDAILYBRIEFING", "DAILY_BRIEFING", "BRIEFING"):
            res = await get_daily_executive_briefing(
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult=res["structuredResult"],
            )

        elif op in ("PREPARE_DAILY_BRIEFING_EMAIL", "PREPAREDAILYBRIEFINGEMAIL"):
            res = await prepare_daily_briefing_email(
                recipientOverride=params.get("recipientOverride") or params.get("to"),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("SEND_APPROVED_DAILY_BRIEFING_EMAIL", "SENDAPPROVEDDAILYBRIEFINGEMAIL"):
            res = await send_approved_daily_briefing_email(
                confirmationToken=params.get("confirmationToken", ""),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("SEND_DAILY_BRIEFING_EMAIL", "SENDDAILYBRIEFINGEMAIL"):
            res = await send_daily_briefing_email(
                recipientOverride=params.get("recipientOverride") or params.get("to"),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("GET_MAIL_THREAD", "GETMAILTHREAD"):
            res = await get_mail_thread(
                conversationId_filter=params.get("conversationId", ""),
                maximumResults=params.get("maximumResults", 10),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("SUMMARIZE_PRIORITY_MAIL", "SUMMARIZEPRIORITYMAIL"):
            res = await summarize_priority_mail(
                timeWindowHours=params.get("timeWindowHours", 24),
                maximumResults=params.get("maximumResults", 5),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("FIND_MAIL_FOLLOW_UPS", "FINDMAILFOLLOWUPS"):
            res = await find_mail_follow_ups(
                timeWindowHours=params.get("timeWindowHours", 72),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("PREPARE_EMAIL_REPLY", "PREPAREEMAILREPLY"):
            res = await prepare_email_reply(
                messageId=params.get("messageId", ""),
                replyBody=params.get("replyBody", params.get("body", "")),
                replyAll=params.get("replyAll", False),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("SEND_APPROVED_EMAIL_REPLY", "SENDAPPROVEDEMAILREPLY"):
            res = await send_approved_email_reply(
                confirmationToken=params.get("confirmationToken", ""),
                previewDetails=params.get("previewDetails", {}),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("LIST_CALENDAR_EVENTS", "LISTCALENDAREVENTS", "LIST_EVENTS", "CALENDAR"):
            res = await list_calendar_events(
                startTime=params.get("startTime"),
                endTime=params.get("endTime"),
                timeZone=request.userTimezone or "Asia/Dubai",
                maximumResults=params.get("maximumResults", 10),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("GET_MEETING_DETAILS", "GETMEETINGDETAILS"):
            res = await get_meeting_details(
                eventId=params.get("eventId", ""),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("CHECK_AVAILABILITY", "CHECKAVAILABILITY"):
            res = await check_availability(
                attendees=params.get("attendees", []),
                startTime=params.get("startTime", "2026-08-27T10:00:00Z"),
                endTime=params.get("endTime", "2026-08-27T11:00:00Z"),
                timeZone=request.userTimezone or "Asia/Dubai",
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("GET_MEETING_CONTEXT", "GETMEETINGCONTEXT"):
            res = await get_meeting_context(
                subjectOrEventId=params.get("subjectOrEventId", params.get("subject", "")),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("PREPARE_MEETING_UPDATE", "PREPAREMEETINGUPDATE"):
            res = await prepare_meeting_update(
                eventId=params.get("eventId", ""),
                subject=params.get("subject"),
                attendees=params.get("attendees"),
                startTime=params.get("startTime"),
                endTime=params.get("endTime"),
                body=params.get("body"),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("UPDATE_APPROVED_MEETING", "UPDATEAPPROVEDMEETING"):
            res = await update_approved_meeting(
                confirmationToken=params.get("confirmationToken", ""),
                previewDetails=params.get("previewDetails", {}),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("PREPARE_MEETING_CANCELLATION", "PREPAREMEETINGCANCELLATION"):
            res = await prepare_meeting_cancellation(
                eventId=params.get("eventId", ""),
                cancellationReason=params.get("cancellationReason", "Cancelled by executive"),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("CANCEL_APPROVED_MEETING", "CANCELAPPROVEDMEETING"):
            res = await cancel_approved_meeting(
                confirmationToken=params.get("confirmationToken", ""),
                previewDetails=params.get("previewDetails", {}),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("SEARCH_TEAMS_MESSAGES", "SEARCHTEAMS", "SEARCH_TEAMS"):
            res = await search_teams_messages(
                query=params.get("query", ""),
                maximumResults=params.get("maximumResults", 10),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("GET_CHANNEL_CONTEXT", "GETCHANNELCONTEXT"):
            res = await get_channel_context(
                teamName=params.get("teamName", ""),
                channelName=params.get("channelName", ""),
                maximumMessages=params.get("maximumMessages", 10),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("GET_CHAT_CONTEXT", "GETCHATCONTEXT"):
            res = await get_chat_context(
                participantEmail=params.get("participantEmail", ""),
                maximumMessages=params.get("maximumMessages", 10),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("FIND_TEAMS_FOLLOW_UPS", "FINDTEAMSFOLLOWUPS"):
            res = await find_teams_follow_ups(
                timeWindowHours=params.get("timeWindowHours", 48),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("PREPARE_TEAMS_CHAT_MESSAGE", "PREPARETEAMSCHAT"):
            res = await prepare_teams_chat_message(
                recipientEmail=params.get("recipientEmail", "leadership@velora.ae"),
                messageText=params.get("messageText", params.get("message", "")),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("SEND_APPROVED_TEAMS_CHAT_MESSAGE", "SENDAPPROVEDTEAMSCHAT"):
            res = await send_approved_teams_chat_message(
                confirmationToken=params.get("confirmationToken", ""),
                previewDetails=params.get("previewDetails", {}),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("PREPARE_TEAMS_CHANNEL_POST", "PREPARETEAMSCHANNELPOST"):
            res = await prepare_teams_channel_post(
                teamName=params.get("teamName", "Executive Leadership Team"),
                channelName=params.get("channelName", "General"),
                subject=params.get("subject", "Executive Update"),
                postBody=params.get("postBody", params.get("body", "")),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("SEND_APPROVED_TEAMS_CHANNEL_POST", "SENDAPPROVEDTEAMSCHANNELPOST"):
            res = await send_approved_teams_channel_post(
                confirmationToken=params.get("confirmationToken", ""),
                previewDetails=params.get("previewDetails", {}),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("LIST_MY_PLANNER_TASKS", "LISTMYPLANNER", "PLANNER_TASKS", "TASKS"):
            res = await list_my_planner_tasks(
                includeCompleted=params.get("includeCompleted", False),
                maximumResults=params.get("maximumResults", 20),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("LIST_PLAN_TASKS", "LISTPLANTASKS"):
            res = await list_plan_tasks(
                planTitle=params.get("planTitle", "Executive Strategic Initiatives"),
                includeCompleted=params.get("includeCompleted", False),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("GET_PLANNER_TASK", "GETPLANNER"):
            res = await get_planner_task(
                taskId=params.get("taskId", ""),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("FIND_OVERDUE_TASKS", "FINDOVERDUETASKS", "OVERDUE_TASKS"):
            res = await find_overdue_tasks(
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                structuredResult=res.get("structuredResult"),
            )

        elif op in ("PREPARE_PLANNER_TASK", "PREPAREPLANNER"):
            res = await prepare_planner_task(
                planTitle=params.get("planTitle", "Executive Strategic Initiatives"),
                title=params.get("title", "Strategic Initiative Action Item"),
                assignedToEmail=params.get("assignedToEmail", email or "leadership@velora.ae"),
                dueDate=params.get("dueDate", "2026-08-30"),
                priority=params.get("priority", "HIGH"),
                notes=params.get("notes", ""),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("CREATE_APPROVED_PLANNER_TASK", "CREATEAPPROVEDPLANNER"):
            res = await create_approved_planner_task(
                confirmationToken=params.get("confirmationToken", ""),
                previewDetails=params.get("previewDetails", {}),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("PREPARE_PLANNER_TASK_UPDATE", "PREPAREPLANNERUPDATE"):
            res = await prepare_planner_task_update(
                taskId=params.get("taskId", ""),
                title=params.get("title"),
                percentComplete=params.get("percentComplete"),
                dueDate=params.get("dueDate"),
                priority=params.get("priority"),
                notes=params.get("notes"),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("UPDATE_APPROVED_PLANNER_TASK", "UPDATEAPPROVEDPLANNER"):
            res = await update_approved_planner_task(
                confirmationToken=params.get("confirmationToken", ""),
                previewDetails=params.get("previewDetails", {}),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        elif op in ("PREPARE_PLANNER_COMPLETION", "PREPAREPLANNERCOMPLETION"):
            res = await prepare_planner_completion(
                taskId=params.get("taskId", ""),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=res["approvalRequired"],
                resultSummary=res["resultSummary"],
                confirmationToken=res["confirmationToken"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                previewDetails=res.get("previewDetails"),
            )

        elif op in ("COMPLETE_APPROVED_PLANNER_TASK", "COMPLETEAPPROVEDPLANNER"):
            res = await complete_approved_planner_task(
                confirmationToken=params.get("confirmationToken", ""),
                previewDetails=params.get("previewDetails", {}),
                rootCorrelationId=corr_id,
                conversationId=conv_id,
                turnId=turn_id,
                userObjectId=uid,
                userEmail=email,
            )
            return HandoffResponse(
                status=res["status"],
                approvalRequired=False,
                resultSummary=res["resultSummary"],
                correlationId=corr_id,
                auditStatus=res["auditStatus"],
                warnings=res.get("warnings", []),
                structuredResult={"externalObjectId": res.get("externalObjectId"), "evidenceLink": res.get("evidenceLink")},
            )

        else:
            return HandoffResponse(
                status="UNSUPPORTED_OPERATION",
                approvalRequired=False,
                resultSummary=f"Operation '{request.operation}' is not supported by Velora Productivity Agent.",
                correlationId=corr_id,
                auditStatus="ERROR",
                warnings=[f"Unknown operation {request.operation}"],
            )

    except Exception as ex:
        return HandoffResponse(
            status="ERROR",
            approvalRequired=False,
            resultSummary=f"Productivity Agent execution error: {str(ex)}",
            correlationId=corr_id,
            auditStatus="ERROR",
            warnings=[str(ex)],
        )
