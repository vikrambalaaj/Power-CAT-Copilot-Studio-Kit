"""Microsoft 365 and Work IQ Read Tools (16 Logical Tools) for Velora Productivity Agent."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .audit_client import get_productivity_audit_service
from .m365_client import Microsoft365Client
from .models import ReadToolEnvelope


def _create_read_envelope(
    status: str,
    summary: str,
    structured_data: Any,
    source_system: str,
    result_count: int,
    correlation_id: str,
    warnings: Optional[List[str]] = None,
    audit_status: str = "PERSISTED",
) -> Dict[str, Any]:
    """Helper to construct standardized output envelope (Section 5.4)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    envelope = ReadToolEnvelope(
        status=status,
        resultSummary=summary,
        structuredResult=structured_data,
        sourceSystem=source_system,
        sourceAsOf=now_iso,
        resultCount=result_count,
        warnings=warnings or [],
        correlationId=correlation_id,
        auditStatus=audit_status,
    )
    return envelope.model_dump()


# =====================================================================
# MAIL READ TOOLS (Section 5.2)
# =====================================================================

async def search_mail(
    query: str = "",
    dateFrom: Optional[str] = None,
    dateTo: Optional[str] = None,
    timeZone: str = "Asia/Dubai",
    safeFilters: str = "",
    maximumResults: int = 10,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Search the user's authorized Microsoft 365 mailbox for emails matching query criteria."""
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-mail-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)
    
    results = client.search_mail(query=query, date_from=dateFrom, max_results=maximumResults)
    latency = int((time.time() - start_ts) * 1000)
    summary = f"Found {len(results)} email(s) matching query '{query or 'all'}' in Outlook mailbox."

    audit_svc = get_productivity_audit_service()
    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="SearchMail",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(results),
        summary=summary,
        safe_filters=safeFilters or query,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status="SUCCESS" if results else "EMPTY",
        summary=summary,
        structured_data=results,
        source_system="Microsoft Outlook Mail",
        result_count=len(results),
        correlation_id=corr_id,
        audit_status=audit_status,
    )


async def get_mail_thread(
    threadId: str,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Retrieve full conversation thread details for a specific email thread."""
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-thread-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)

    results = client.get_mail_thread(thread_id=threadId)
    latency = int((time.time() - start_ts) * 1000)
    summary = f"Retrieved {len(results)} message(s) for email thread '{threadId}'."

    audit_svc = get_productivity_audit_service()
    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="GetMailThread",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(results),
        summary=summary,
        safe_filters=f"threadId={threadId}",
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status="SUCCESS" if results else "EMPTY",
        summary=summary,
        structured_data=results,
        source_system="Microsoft Outlook Mail",
        result_count=len(results),
        correlation_id=corr_id,
        audit_status=audit_status,
    )


async def summarize_priority_mail(
    maximumResults: int = 5,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Retrieve and summarize high-priority or executive inbox messages."""
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-pmail-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)

    results = client.summarize_priority_mail(max_results=maximumResults)
    latency = int((time.time() - start_ts) * 1000)
    summary = f"Identified {len(results)} priority email(s) requiring executive attention."

    audit_svc = get_productivity_audit_service()
    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="SummarizePriorityMail",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(results),
        summary=summary,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status="SUCCESS" if results else "EMPTY",
        summary=summary,
        structured_data=results,
        source_system="Microsoft Outlook Mail",
        result_count=len(results),
        correlation_id=corr_id,
        audit_status=audit_status,
    )


async def find_mail_follow_ups(
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Find emails flagged for follow-up or requiring pending responses."""
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-follow-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)

    results = client.find_mail_follow_ups()
    latency = int((time.time() - start_ts) * 1000)
    summary = f"Found {len(results)} email item(s) flagged for follow-up."

    audit_svc = get_productivity_audit_service()
    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="FindMailFollowUps",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(results),
        summary=summary,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status="SUCCESS" if results else "EMPTY",
        summary=summary,
        structured_data=results,
        source_system="Microsoft Outlook Mail",
        result_count=len(results),
        correlation_id=corr_id,
        audit_status=audit_status,
    )


# =====================================================================
# CALENDAR READ TOOLS (Section 5.2)
# =====================================================================

async def list_calendar_events(
    dateFrom: Optional[str] = None,
    dateTo: Optional[str] = None,
    timeZone: str = "Asia/Dubai",
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """List calendar events for the user within the specified date range."""
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-cal-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)

    results = client.list_calendar_events(date_from=dateFrom, date_to=dateTo)
    latency = int((time.time() - start_ts) * 1000)
    summary = f"Retrieved {len(results)} calendar event(s) in timezone '{timeZone}'."

    audit_svc = get_productivity_audit_service()
    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="ListCalendarEvents",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(results),
        summary=summary,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status="SUCCESS" if results else "EMPTY",
        summary=summary,
        structured_data=results,
        source_system="Microsoft Outlook Calendar",
        result_count=len(results),
        correlation_id=corr_id,
        audit_status=audit_status,
    )


async def get_meeting_details(
    eventId: str,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Retrieve detailed meeting information including organizer, attendees, and Teams link."""
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-mtg-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)

    event = client.get_meeting_details(event_id=eventId)
    latency = int((time.time() - start_ts) * 1000)
    summary = f"Meeting details retrieved for event '{eventId}': {event.get('subject', 'Unknown') if event else 'Not found'}."

    audit_svc = get_productivity_audit_service()
    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="GetMeetingDetails",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=1 if event else 0,
        summary=summary,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status="SUCCESS" if event else "NOT_FOUND",
        summary=summary,
        structured_data=event or {},
        source_system="Microsoft Outlook Calendar",
        result_count=1 if event else 0,
        correlation_id=corr_id,
        audit_status=audit_status,
    )


async def check_availability(
    attendees: List[str],
    startTime: str,
    endTime: str,
    timeZone: str = "Asia/Dubai",
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Check availability and detect conflicts across proposed meeting participants."""
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-avail-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)

    res = client.check_availability(attendees=attendees, start_time=startTime, end_time=endTime)
    latency = int((time.time() - start_ts) * 1000)
    has_conflict = res.get("has_conflict", False)
    summary = f"Availability check completed: {'Conflicts detected' if has_conflict else 'All participants available'} for {startTime} to {endTime}."

    audit_svc = get_productivity_audit_service()
    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="CheckAvailability",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(res.get("conflicts", [])),
        summary=summary,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status="CONFLICT_DETECTED" if has_conflict else "AVAILABLE",
        summary=summary,
        structured_data=res,
        source_system="Microsoft Outlook Calendar",
        result_count=len(res.get("conflicts", [])),
        correlation_id=corr_id,
        warnings=["One or more attendees have conflicting calendar commitments."] if has_conflict else [],
        audit_status=audit_status,
    )


async def get_meeting_context(
    subjectOrId: str,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Retrieve pre-meeting or post-meeting contextual packet."""
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-mctx-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)

    events = client.list_calendar_events()
    matched = next((e for e in events if subjectOrId.lower() in e["id"].lower() or subjectOrId.lower() in e["subject"].lower()), None)
    latency = int((time.time() - start_ts) * 1000)
    
    summary = f"Contextual packet synthesized for meeting: '{matched.get('subject', 'Unknown') if matched else subjectOrId}'."

    audit_svc = get_productivity_audit_service()
    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="GetMeetingContext",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=1 if matched else 0,
        summary=summary,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status="SUCCESS" if matched else "NOT_FOUND",
        summary=summary,
        structured_data=matched or {},
        source_system="Microsoft 365 Work IQ",
        result_count=1 if matched else 0,
        correlation_id=corr_id,
        audit_status=audit_status,
    )


# =====================================================================
# TEAMS READ TOOLS (Section 5.2)
# =====================================================================

async def search_teams_messages(
    query: str = "",
    maximumResults: int = 10,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Search Microsoft Teams channels and chats for messages matching query."""
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-teams-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)

    results = client.search_teams_messages(query=query, max_results=maximumResults)
    latency = int((time.time() - start_ts) * 1000)
    summary = f"Found {len(results)} message(s) in Microsoft Teams matching '{query or 'all'}'."

    audit_svc = get_productivity_audit_service()
    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="SearchTeamsMessages",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(results),
        summary=summary,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status="SUCCESS" if results else "EMPTY",
        summary=summary,
        structured_data=results,
        source_system="Microsoft Teams",
        result_count=len(results),
        correlation_id=corr_id,
        audit_status=audit_status,
    )


async def get_channel_context(
    teamName: str,
    channelName: str,
    maximumResults: int = 5,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Retrieve recent conversation context from a specific Teams channel."""
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-chan-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)

    results = client.get_channel_context(team_name=teamName, channel_name=channelName, max_results=maximumResults)
    latency = int((time.time() - start_ts) * 1000)
    summary = f"Retrieved {len(results)} channel post(s) from '{teamName} > {channelName}'."

    audit_svc = get_productivity_audit_service()
    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="GetChannelContext",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(results),
        summary=summary,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status="SUCCESS" if results else "EMPTY",
        summary=summary,
        structured_data=results,
        source_system="Microsoft Teams",
        result_count=len(results),
        correlation_id=corr_id,
        audit_status=audit_status,
    )


async def get_chat_context(
    chatId: str,
    maximumResults: int = 5,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Retrieve recent direct chat message context."""
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-chat-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)

    results = client.get_chat_context(chat_id=chatId, max_results=maximumResults)
    latency = int((time.time() - start_ts) * 1000)
    summary = f"Retrieved {len(results)} chat message(s) from chat ID '{chatId}'."

    audit_svc = get_productivity_audit_service()
    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="GetChatContext",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(results),
        summary=summary,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status="SUCCESS" if results else "EMPTY",
        summary=summary,
        structured_data=results,
        source_system="Microsoft Teams",
        result_count=len(results),
        correlation_id=corr_id,
        audit_status=audit_status,
    )


async def find_teams_follow_ups(
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Identify action items, mentions, or follow-ups directed to the user in Teams."""
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-tflw-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)

    results = client.search_teams_messages(query="", max_results=5)
    latency = int((time.time() - start_ts) * 1000)
    summary = f"Identified {len(results)} relevant message(s) and mention(s) across Teams."

    audit_svc = get_productivity_audit_service()
    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="FindTeamsFollowUps",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(results),
        summary=summary,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status="SUCCESS" if results else "EMPTY",
        summary=summary,
        structured_data=results,
        source_system="Microsoft Teams",
        result_count=len(results),
        correlation_id=corr_id,
        audit_status=audit_status,
    )


# =====================================================================
# PLANNER READ TOOLS (Section 5.2)
# =====================================================================

async def list_my_planner_tasks(
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """List all Planner tasks assigned to the current authenticated executive."""
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-mytask-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)

    results = client.list_planner_tasks(my_tasks_only=True)
    latency = int((time.time() - start_ts) * 1000)
    summary = f"Retrieved {len(results)} Planner task(s) assigned to '{userEmail or 'current user'}'."

    audit_svc = get_productivity_audit_service()
    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="ListMyPlannerTasks",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(results),
        summary=summary,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status="SUCCESS" if results else "EMPTY",
        summary=summary,
        structured_data=results,
        source_system="Microsoft Planner",
        result_count=len(results),
        correlation_id=corr_id,
        audit_status=audit_status,
    )


async def list_plan_tasks(
    planName: str,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """List tasks in a specific Planner basic plan."""
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-plantask-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)

    results = client.list_planner_tasks(plan_name=planName)
    latency = int((time.time() - start_ts) * 1000)
    summary = f"Retrieved {len(results)} task(s) in plan '{planName}'."

    audit_svc = get_productivity_audit_service()
    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="ListPlanTasks",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(results),
        summary=summary,
        safe_filters=f"planName={planName}",
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status="SUCCESS" if results else "EMPTY",
        summary=summary,
        structured_data=results,
        source_system="Microsoft Planner",
        result_count=len(results),
        correlation_id=corr_id,
        audit_status=audit_status,
    )


async def get_planner_task(
    taskId: str,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Get details for a single Planner task."""
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-task-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)

    task = client.get_planner_task(task_id=taskId)
    latency = int((time.time() - start_ts) * 1000)
    summary = f"Details for task '{taskId}': {task.get('title', 'Unknown') if task else 'Not found'}."

    audit_svc = get_productivity_audit_service()
    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="GetPlannerTask",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=1 if task else 0,
        summary=summary,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status="SUCCESS" if task else "NOT_FOUND",
        summary=summary,
        structured_data=task or {},
        source_system="Microsoft Planner",
        result_count=1 if task else 0,
        correlation_id=corr_id,
        audit_status=audit_status,
    )


async def find_overdue_tasks(
    planName: Optional[str] = None,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Find overdue Planner tasks across authorized plans."""
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-overdue-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)

    results = client.list_planner_tasks(plan_name=planName, overdue_only=True)
    latency = int((time.time() - start_ts) * 1000)
    summary = f"Identified {len(results)} overdue task(s) requiring remediation."

    audit_svc = get_productivity_audit_service()
    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="FindOverdueTasks",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(results),
        summary=summary,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status="OVERDUE_ITEMS_FOUND" if results else "CLEAN",
        summary=summary,
        structured_data=results,
        source_system="Microsoft Planner",
        result_count=len(results),
        correlation_id=corr_id,
        warnings=[f"{len(results)} task(s) past their scheduled due date."] if results else [],
        audit_status=audit_status,
    )


# =====================================================================
# EXECUTIVE DAILY BRIEFING TOOL
# =====================================================================

async def get_daily_executive_briefing(
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Synthesize complete executive daily briefing covering calendar meetings, tasks to do, Teams chats, upcoming approvals, and urgent priorities."""
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-brief-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)

    briefing = client.get_daily_briefing()
    latency = int((time.time() - start_ts) * 1000)
    summary = briefing.get("summary_text", "Executive daily briefing synthesized.")

    audit_svc = get_productivity_audit_service()
    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="GetDailyExecutiveBriefing",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(briefing.get("meetings_today", [])) + len(briefing.get("tasks_to_do", [])) + len(briefing.get("upcoming_approvals", [])),
        summary=summary,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status="SUCCESS",
        summary=summary,
        structured_data=briefing,
        source_system="Microsoft365 & Work IQ",
        result_count=len(briefing.get("meetings_today", [])),
        correlation_id=corr_id,
        warnings=["3 pending executive approvals requiring action today.", "1 overdue governance task flagged in Planner."],
        audit_status=audit_status,
    )

