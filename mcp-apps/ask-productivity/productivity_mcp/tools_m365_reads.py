"""Microsoft 365 and Work IQ Read Tools (16 Logical Tools) for Velora Productivity Agent."""
from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from .audit_client import get_productivity_audit_service
from .briefing_service import get_briefing_service, compute_content_hash
from .evidence_contracts import MaterialClaim, EvidenceSource, ClaimKind, ConfidenceAssessment, ConfidenceLabel
from .m365_client import (
    Microsoft365Client,
    AccessDeniedError,
    GraphRateLimitError,
    GraphTimeoutError,
    GraphSourceUnavailableError,
)
from .models import ReadToolEnvelope
from .triage_engine import (
    TriageRubricPolicy,
    TEST_EQUAL_WEIGHTS_RUBRIC,
    score_candidates_pipeline,
)


def _create_read_envelope(
    status: str,
    summary: str,
    structured_data: Any,
    source_system: str,
    result_count: int,
    correlation_id: str,
    warnings: Optional[List[str]] = None,
    audit_status: str = "PERSISTED",
    truncated: bool = False,
    next_link: Optional[str] = None,
    page_count: int = 1,
    claims: Optional[List[MaterialClaim]] = None,
    sources: Optional[List[EvidenceSource]] = None,
    confidence: Optional[ConfidenceAssessment] = None,
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
        claims=claims or [],
        sources=sources or [],
        confidence=confidence,
        truncated=truncated,
        nextLink=next_link,
        pageCount=page_count,
    )
    return envelope.model_dump()


def _handle_read_error(ex: Exception, op_name: str) -> tuple[str, str, List[str]]:
    """Map Graph client exceptions to (status, summary, warnings)."""
    if isinstance(ex, AccessDeniedError):
        return ("ACCESS_DENIED", f"Access denied executing {op_name}: {ex}", [str(ex)])
    elif isinstance(ex, GraphRateLimitError):
        return ("THROTTLED", f"Graph rate limit exceeded executing {op_name} (retry after {ex.retry_after}s)", [str(ex), f"Retry-After: {ex.retry_after}s"])
    elif isinstance(ex, GraphTimeoutError):
        return ("TIMEOUT", f"Graph timeout executing {op_name}: {ex}", [str(ex)])
    elif isinstance(ex, GraphSourceUnavailableError):
        return ("SOURCE_UNAVAILABLE", f"Graph source unavailable executing {op_name}: {ex}", [str(ex)])
    return ("ERROR", f"Error executing {op_name}: {ex}", [str(ex)])


# =====================================================================
# MAIL READ TOOLS (Section 5.2)
# =====================================================================

async def search_mail(
    query: str = "",
    dateFrom: Optional[str] = None,
    dateTo: Optional[str] = None,
    unreadOnly: bool = False,
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
    audit_svc = get_productivity_audit_service()

    truncated = False
    next_link = None
    page_count = 1
    warnings: List[str] = []
    try:
        results = client.search_mail(
            query=query,
            date_from=dateFrom,
            date_to=dateTo,
            unread_only=unreadOnly,
            max_results=maximumResults,
        )
        pag = client.get_last_pagination()
        truncated = pag.get("truncated", False)
        next_link = pag.get("nextLink")
        page_count = pag.get("pageCount", 1)
        latency = int((time.time() - start_ts) * 1000)
        summary = f"Found {len(results)} email(s) matching query '{query or 'all'}' in Outlook mailbox."
        status = "SUCCESS" if results else "EMPTY"
    except (AccessDeniedError, GraphRateLimitError, GraphTimeoutError, GraphSourceUnavailableError, Exception) as ex:
        results = []
        latency = int((time.time() - start_ts) * 1000)
        status, summary, warnings = _handle_read_error(ex, "SearchMail")

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
        status=status,
        summary=summary,
        structured_data=results,
        source_system="Microsoft Outlook Mail",
        result_count=len(results),
        correlation_id=corr_id,
        warnings=warnings,
        audit_status=audit_status,
        truncated=truncated,
        next_link=next_link,
        page_count=page_count,
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
    audit_svc = get_productivity_audit_service()

    warnings: List[str] = []
    try:
        results = client.get_mail_thread(thread_id=threadId)
        latency = int((time.time() - start_ts) * 1000)
        summary = f"Retrieved {len(results)} message(s) for email thread '{threadId}'."
        status = "SUCCESS" if results else "EMPTY"
    except (AccessDeniedError, GraphRateLimitError, GraphTimeoutError, GraphSourceUnavailableError, Exception) as ex:
        results = []
        latency = int((time.time() - start_ts) * 1000)
        status, summary, warnings = _handle_read_error(ex, "GetMailThread")

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
        status=status,
        summary=summary,
        structured_data=results,
        source_system="Microsoft Outlook Mail",
        result_count=len(results),
        correlation_id=corr_id,
        warnings=warnings,
        audit_status=audit_status,
    )


async def summarize_priority_mail(
    maximumResults: int = 5,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
    rubricPolicy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Retrieve and summarize high-priority or executive inbox messages.
    
    Acts as a compatibility view backed by Contextual Attention Scoring Engine (CASE).
    Considers candidate mail messages, ranks them deterministically, and preserves
    legacy priority mail fields alongside priority scores.
    """
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-pmail-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)
    audit_svc = get_productivity_audit_service()

    warnings: List[str] = []
    claims: List[MaterialClaim] = []
    sources: List[EvidenceSource] = []
    results: List[Dict[str, Any]] = []

    try:
        # Retrieve candidate mail messages
        raw_candidates = []
        try:
            raw_candidates = client.search_mail(max_results=max(maximumResults * 2, 10))
        except Exception:
            pass

        if not raw_candidates:
            # Fallback to direct client summarize_priority_mail
            raw_candidates = client.summarize_priority_mail(max_results=maximumResults)

        # Resolve rubric
        rubric = TriageRubricPolicy(**rubricPolicy) if rubricPolicy else TEST_EQUAL_WEIGHTS_RUBRIC

        # Score via CASE pipeline
        scored_items = score_candidates_pipeline(
            mail_candidates=raw_candidates,
            calendar_candidates=[],
            task_candidates=[],
            rubric=rubric,
            maximum_results=maximumResults,
        )

        for item in scored_items:
            # Build compatibility dict combining original mail fields with attention scoring
            orig = next((m for m in raw_candidates if m.get("id") in item.sourceRecordReferences), {})
            source_id = orig.get("id") or (item.sourceRecordReferences[0] if item.sourceRecordReferences else item.itemId)
            compat = {
                "id": source_id,
                "threadId": orig.get("threadId") or orig.get("conversationId"),
                "subject": item.title,
                "from": orig.get("from") or "",
                "bodyPreview": orig.get("bodyPreview") or "",
                "isPriority": item.totalScore >= 50 or orig.get("isPriority", False),
                "receivedDateTime": orig.get("receivedDateTime") or "",
                "priorityScore": item.totalScore,
                "rank": item.rank,
                "requiredAttention": item.requiredAttention,
                "deadline": item.deadline,
                "deadlineEvidence": item.deadlineEvidence,
                "factorScores": item.factorScores,
            }
            results.append(compat)

            # Build MaterialClaim and EvidenceSource
            claims.append(
                MaterialClaim(
                    claimId=f"CLM-{item.itemId}",
                    kind=ClaimKind.EVALUATION,
                    text=f"Priority #{item.rank}: {item.title} (Priority Score: {item.totalScore}/100) — {item.requiredAttention}",
                    sourceIds=item.sourceRecordReferences,
                    calculationVersion=item.scoringVersion,
                    confidenceAssessment=item.claimConfidence,
                )
            )
            sources.append(
                EvidenceSource(
                    sourceId=source_id,
                    system="Microsoft Outlook Mail",
                    businessTitle=f"Mail: {item.title[:40]}",
                    providerRecordId=source_id,
                    retrievedAt=datetime.now(timezone.utc).isoformat(),
                    sourceUpdatedAt=compat.get("receivedDateTime") or None,
                )
            )

        latency = int((time.time() - start_ts) * 1000)
        summary = f"Identified {len(results)} priority email(s) requiring executive attention."
        status = "SUCCESS" if results else "EMPTY"
    except (AccessDeniedError, GraphRateLimitError, GraphTimeoutError, GraphSourceUnavailableError, Exception) as ex:
        results = []
        latency = int((time.time() - start_ts) * 1000)
        status, summary, warnings = _handle_read_error(ex, "SummarizePriorityMail")

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
        status=status,
        summary=summary,
        structured_data=results,
        source_system="Microsoft Outlook Mail",
        result_count=len(results),
        correlation_id=corr_id,
        warnings=warnings,
        audit_status=audit_status,
        claims=claims,
        sources=sources,
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
    audit_svc = get_productivity_audit_service()

    warnings: List[str] = []
    try:
        results = client.find_mail_follow_ups()
        latency = int((time.time() - start_ts) * 1000)
        summary = f"Found {len(results)} email item(s) flagged for follow-up."
        status = "SUCCESS" if results else "EMPTY"
    except (AccessDeniedError, GraphRateLimitError, GraphTimeoutError, GraphSourceUnavailableError, Exception) as ex:
        results = []
        latency = int((time.time() - start_ts) * 1000)
        status, summary, warnings = _handle_read_error(ex, "FindMailFollowUps")

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
        status=status,
        summary=summary,
        structured_data=results,
        source_system="Microsoft Outlook Mail",
        result_count=len(results),
        correlation_id=corr_id,
        warnings=warnings,
        audit_status=audit_status,
    )


# =====================================================================
# CALENDAR READ TOOLS (Section 5.2)
# =====================================================================

async def list_calendar_events(
    dateFrom: Optional[str] = None,
    dateTo: Optional[str] = None,
    timeZone: str = "Asia/Dubai",
    includeCancelled: bool = False,
    maximumResults: int = 50,
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
    audit_svc = get_productivity_audit_service()

    truncated = False
    next_link = None
    page_count = 1
    warnings: List[str] = []
    try:
        results = client.list_calendar_events(
            date_from=dateFrom,
            date_to=dateTo,
            time_zone=timeZone,
            include_cancelled=includeCancelled,
            max_results=maximumResults,
        )
        pag = client.get_last_pagination()
        truncated = pag.get("truncated", False)
        next_link = pag.get("nextLink")
        page_count = pag.get("pageCount", 1)
        latency = int((time.time() - start_ts) * 1000)
        summary = f"Retrieved {len(results)} calendar event(s) in timezone '{timeZone}'."
        status = "SUCCESS" if results else "EMPTY"
    except (AccessDeniedError, GraphRateLimitError, GraphTimeoutError, GraphSourceUnavailableError, Exception) as ex:
        results = []
        latency = int((time.time() - start_ts) * 1000)
        status, summary, warnings = _handle_read_error(ex, "ListCalendarEvents")

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
        status=status,
        summary=summary,
        structured_data=results,
        source_system="Microsoft Outlook Calendar",
        result_count=len(results),
        correlation_id=corr_id,
        warnings=warnings,
        audit_status=audit_status,
        truncated=truncated,
        next_link=next_link,
        page_count=page_count,
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
    audit_svc = get_productivity_audit_service()

    warnings: List[str] = []
    try:
        event = client.get_meeting_details(event_id=eventId)
        latency = int((time.time() - start_ts) * 1000)
        summary = f"Meeting details retrieved for event '{eventId}': {event.get('subject', 'Unknown') if event else 'Not found'}."
        status = "SUCCESS" if event else "NOT_FOUND"
    except (AccessDeniedError, GraphRateLimitError, GraphTimeoutError, GraphSourceUnavailableError, Exception) as ex:
        event = None
        latency = int((time.time() - start_ts) * 1000)
        status, summary, warnings = _handle_read_error(ex, "GetMeetingDetails")

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
        status=status,
        summary=summary,
        structured_data=event or {},
        source_system="Microsoft Outlook Calendar",
        result_count=1 if event else 0,
        correlation_id=corr_id,
        warnings=warnings,
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
    audit_svc = get_productivity_audit_service()

    warnings: List[str] = []
    try:
        res = client.check_availability(attendees=attendees, start_time=startTime, end_time=endTime)
        latency = int((time.time() - start_ts) * 1000)
        has_conflict = res.get("has_conflict") if "has_conflict" in res else (bool(res.get("conflicts")) or not res.get("available", True))
        summary = f"Availability check completed: {'Conflicts detected' if has_conflict else 'All participants available'} for {startTime} to {endTime}."
        status = "CONFLICT_DETECTED" if has_conflict else "AVAILABLE"
        if has_conflict:
            warnings.append("One or more attendees have conflicting calendar commitments.")
    except (AccessDeniedError, GraphRateLimitError, GraphTimeoutError, GraphSourceUnavailableError, Exception) as ex:
        res = {}
        latency = int((time.time() - start_ts) * 1000)
        status, summary, warnings = _handle_read_error(ex, "CheckAvailability")

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
        status=status,
        summary=summary,
        structured_data=res,
        source_system="Microsoft Outlook Calendar",
        result_count=len(res.get("conflicts", [])),
        correlation_id=corr_id,
        warnings=warnings,
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
    audit_svc = get_productivity_audit_service()

    warnings: List[str] = []
    try:
        events = client.list_calendar_events()
        # 1. Exact match check
        exact_match = next(
            (e for e in events if e.get("id") == subjectOrId or (e.get("subject") and e.get("subject").strip().lower() == subjectOrId.strip().lower())),
            None,
        )
        if exact_match:
            matched = exact_match
            verified_match = True
            candidate_relationship = "EXACT_MATCH"
        else:
            # 2. Substring match check
            substr_match = next(
                (e for e in events if subjectOrId.lower() in (e.get("id") or "").lower() or subjectOrId.lower() in (e.get("subject") or "").lower()),
                None,
            )
            if substr_match:
                matched = substr_match
                verified_match = False
                candidate_relationship = "UNCERTAIN_CANDIDATE"
                warnings.append(
                    f"Candidate meeting match '{matched.get('subject')}' is an UNCERTAIN_CANDIDATE based on substring matching. Verification required."
                )
            else:
                matched = None
                verified_match = False
                candidate_relationship = "NONE"

        if not matched:
            latency = int((time.time() - start_ts) * 1000)
            summary = f"No calendar meeting found matching '{subjectOrId}'."
            status = "NOT_FOUND"
            structured_data = {}
            result_count = 0
        else:
            related_mails = []
            meeting_subject = matched.get("subject", "")
            if meeting_subject:
                try:
                    related_mails = client.search_mail(query=meeting_subject, max_results=5)
                except Exception:
                    related_mails = []

            structured_data = dict(matched)
            structured_data.update({
                "meeting": matched,
                "verifiedMatch": verified_match,
                "candidateRelationship": candidate_relationship,
                "relatedMails": related_mails,
            })
            status = "SUCCESS"
            match_label = "verified exact match" if verified_match else "uncertain candidate match"
            summary = f"Contextual packet synthesized for meeting '{matched.get('subject', subjectOrId)}': {match_label} with {len(related_mails)} related email(s)."
            result_count = 1
            latency = int((time.time() - start_ts) * 1000)

    except (AccessDeniedError, GraphRateLimitError, GraphTimeoutError, GraphSourceUnavailableError, Exception) as ex:
        structured_data = {}
        result_count = 0
        latency = int((time.time() - start_ts) * 1000)
        status, summary, warnings = _handle_read_error(ex, "GetMeetingContext")

    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="GetMeetingContext",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=result_count,
        summary=summary,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status=status,
        summary=summary,
        structured_data=structured_data,
        source_system="Microsoft Outlook Calendar & Graph",
        result_count=result_count,
        correlation_id=corr_id,
        warnings=warnings,
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
    audit_svc = get_productivity_audit_service()

    warnings: List[str] = []
    try:
        results = client.search_teams_messages(query=query, max_results=maximumResults)
        latency = int((time.time() - start_ts) * 1000)
        summary = f"Found {len(results)} message(s) in Microsoft Teams matching '{query or 'all'}'."
        status = "SUCCESS" if results else "EMPTY"
    except (AccessDeniedError, GraphRateLimitError, GraphTimeoutError, GraphSourceUnavailableError, Exception) as ex:
        results = []
        latency = int((time.time() - start_ts) * 1000)
        status, summary, warnings = _handle_read_error(ex, "SearchTeamsMessages")

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
        status=status,
        summary=summary,
        structured_data=results,
        source_system="Microsoft Teams",
        result_count=len(results),
        correlation_id=corr_id,
        warnings=warnings,
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
    audit_svc = get_productivity_audit_service()

    warnings: List[str] = []
    try:
        results = client.get_channel_context(team_name=teamName, channel_name=channelName, max_results=maximumResults)
        latency = int((time.time() - start_ts) * 1000)
        summary = f"Retrieved {len(results)} channel post(s) from '{teamName} > {channelName}'."
        status = "SUCCESS" if results else "EMPTY"
    except (AccessDeniedError, GraphRateLimitError, GraphTimeoutError, GraphSourceUnavailableError, Exception) as ex:
        results = []
        latency = int((time.time() - start_ts) * 1000)
        status, summary, warnings = _handle_read_error(ex, "GetChannelContext")

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
        status=status,
        summary=summary,
        structured_data=results,
        source_system="Microsoft Teams",
        result_count=len(results),
        correlation_id=corr_id,
        warnings=warnings,
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
    audit_svc = get_productivity_audit_service()

    warnings: List[str] = []
    try:
        results = client.get_chat_context(chat_id=chatId, max_results=maximumResults)
        latency = int((time.time() - start_ts) * 1000)
        summary = f"Retrieved {len(results)} chat message(s) from chat ID '{chatId}'."
        status = "SUCCESS" if results else "EMPTY"
    except (AccessDeniedError, GraphRateLimitError, GraphTimeoutError, GraphSourceUnavailableError, Exception) as ex:
        results = []
        latency = int((time.time() - start_ts) * 1000)
        status, summary, warnings = _handle_read_error(ex, "GetChatContext")

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
        status=status,
        summary=summary,
        structured_data=results,
        source_system="Microsoft Teams",
        result_count=len(results),
        correlation_id=corr_id,
        warnings=warnings,
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
    audit_svc = get_productivity_audit_service()

    warnings: List[str] = []
    try:
        results = client.search_teams_messages(query="", max_results=5)
        latency = int((time.time() - start_ts) * 1000)
        summary = f"Identified {len(results)} relevant message(s) and mention(s) across Teams."
        status = "SUCCESS" if results else "EMPTY"
    except (AccessDeniedError, GraphRateLimitError, GraphTimeoutError, GraphSourceUnavailableError, Exception) as ex:
        results = []
        latency = int((time.time() - start_ts) * 1000)
        status, summary, warnings = _handle_read_error(ex, "FindTeamsFollowUps")

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
        status=status,
        summary=summary,
        structured_data=results,
        source_system="Microsoft Teams",
        result_count=len(results),
        correlation_id=corr_id,
        warnings=warnings,
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
    audit_svc = get_productivity_audit_service()

    warnings: List[str] = []
    try:
        results = client.list_planner_tasks(my_tasks_only=True)
        latency = int((time.time() - start_ts) * 1000)
        summary = f"Retrieved {len(results)} Planner task(s) assigned to '{userEmail or 'current user'}'."
        status = "SUCCESS" if results else "EMPTY"
    except (AccessDeniedError, GraphRateLimitError, GraphTimeoutError, GraphSourceUnavailableError, Exception) as ex:
        results = []
        latency = int((time.time() - start_ts) * 1000)
        status, summary, warnings = _handle_read_error(ex, "ListMyPlannerTasks")

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
        status=status,
        summary=summary,
        structured_data=results,
        source_system="Microsoft Planner",
        result_count=len(results),
        correlation_id=corr_id,
        warnings=warnings,
        audit_status=audit_status,
    )


async def list_plan_tasks(
    planName: str = "Executive Strategic Initiatives",
    planId: Optional[str] = None,
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
    audit_svc = get_productivity_audit_service()

    target_plan = planName or planId or "Executive Strategic Initiatives"
    warnings: List[str] = []
    try:
        results = client.list_planner_tasks(plan_name=target_plan)
        latency = int((time.time() - start_ts) * 1000)
        summary = f"Retrieved {len(results)} task(s) in plan '{target_plan}'."
        status = "SUCCESS" if results else "EMPTY"
    except (AccessDeniedError, GraphRateLimitError, GraphTimeoutError, GraphSourceUnavailableError, Exception) as ex:
        results = []
        latency = int((time.time() - start_ts) * 1000)
        status, summary, warnings = _handle_read_error(ex, "ListPlanTasks")

    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="ListPlanTasks",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(results),
        summary=summary,
        safe_filters=f"planName={target_plan}",
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status=status,
        summary=summary,
        structured_data=results,
        source_system="Microsoft Planner",
        result_count=len(results),
        correlation_id=corr_id,
        warnings=warnings,
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
    audit_svc = get_productivity_audit_service()

    warnings: List[str] = []
    try:
        task = client.get_planner_task(task_id=taskId)
        latency = int((time.time() - start_ts) * 1000)
        summary = f"Details for task '{taskId}': {task.get('title', 'Unknown') if task else 'Not found'}."
        status = "SUCCESS" if task else "NOT_FOUND"
    except (AccessDeniedError, GraphRateLimitError, GraphTimeoutError, GraphSourceUnavailableError, Exception) as ex:
        task = None
        latency = int((time.time() - start_ts) * 1000)
        status, summary, warnings = _handle_read_error(ex, "GetPlannerTask")

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
        status=status,
        summary=summary,
        structured_data=task or {},
        source_system="Microsoft Planner",
        result_count=1 if task else 0,
        correlation_id=corr_id,
        warnings=warnings,
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
    audit_svc = get_productivity_audit_service()

    warnings: List[str] = []
    try:
        results = client.list_planner_tasks(plan_name=planName, overdue_only=True)
        latency = int((time.time() - start_ts) * 1000)
        summary = f"Identified {len(results)} overdue task(s) requiring remediation."
        status = "OVERDUE_ITEMS_FOUND" if results else "CLEAN"
        if results:
            warnings.append(f"{len(results)} task(s) past their scheduled due date.")
    except (AccessDeniedError, GraphRateLimitError, GraphTimeoutError, GraphSourceUnavailableError, Exception) as ex:
        results = []
        latency = int((time.time() - start_ts) * 1000)
        status, summary, warnings = _handle_read_error(ex, "FindOverdueTasks")

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
        status=status,
        summary=summary,
        structured_data=results,
        source_system="Microsoft Planner",
        result_count=len(results),
        correlation_id=corr_id,
        warnings=warnings,
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
    audit_svc = get_productivity_audit_service()

    warnings: List[str] = []
    degraded_sections: List[str] = []

    # Section 1: Meetings
    meetings: List[Dict[str, Any]] = []
    try:
        meetings = client.list_calendar_events()
    except Exception as ex:
        degraded_sections.append(f"Calendar: {ex}")

    # Section 2: Tasks & Overdue
    tasks: List[Dict[str, Any]] = []
    overdue: List[Dict[str, Any]] = []
    try:
        tasks = client.list_planner_tasks()
        now_iso = datetime.now(timezone.utc).isoformat()
        overdue = [
            t for t in tasks
            if t.get("dueDateTime") and t.get("dueDateTime") < now_iso and t.get("percentComplete", 0) < 100
        ]
    except Exception as ex:
        degraded_sections.append(f"Planner: {ex}")

    # Section 3: Teams messages
    teams_msgs: List[Dict[str, Any]] = []
    try:
        teams_msgs = client.search_teams_messages(query="*")
    except Exception as ex:
        degraded_sections.append(f"Teams: {ex}")

    # Section 4: Priority emails
    priority_mails: List[Dict[str, Any]] = []
    try:
        priority_mails = client.search_mail(query="priority") or client.summarize_priority_mail()
    except Exception as ex:
        degraded_sections.append(f"Mail: {ex}")

    # Section 5: Approvals (Mark as SOURCE_UNAVAILABLE unless configured)
    approvals: List[Dict[str, Any]] = []
    try:
        approvals = client.list_pending_approvals()
    except Exception as ex:
        degraded_sections.append(f"Approvals: SOURCE_UNAVAILABLE ({ex})")

    # Determine top-level status
    if degraded_sections:
        status = "PARTIAL"
        for deg in degraded_sections:
            warnings.append(f"Degraded section: {deg}")
    else:
        status = "SUCCESS"

    if overdue:
        warnings.append(f"{len(overdue)} overdue task(s) flagged in Planner requiring immediate attention.")
    if approvals:
        warnings.append(f"{len(approvals)} pending executive approval(s) requiring sign-off.")

    now_str = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")
    exec_name = "Executive"
    if userEmail and "@" in userEmail:
        exec_name = userEmail.split("@")[0].replace(".", " ").title()

    summary_text = (
        f"Executive Daily Briefing for {now_str}:\n"
        f"• 📅 Meetings Today: {len(meetings)} scheduled executive sessions\n"
        f"• 📋 Tasks to Perform: {len(tasks)} active items ({len(overdue)} overdue items requiring attention)\n"
        f"• 💬 Teams Activity: {len(teams_msgs)} message threads\n"
        f"• ⏳ Pending Approvals: {len(approvals)} pending sign-offs\n"
        f"• ✉️ Priority Mails: {len(priority_mails)} priority updates."
    )
    if degraded_sections:
        summary_text += f"\n[Degraded sources: {', '.join(degraded_sections)}]"

    focus_areas = []
    if overdue:
        focus_areas.append(f"Remediate {len(overdue)} overdue Planner task(s) past scheduled deadline.")
    if approvals:
        focus_areas.append(f"Review and act upon {len(approvals)} pending approval request(s).")
    if priority_mails:
        focus_areas.append(f"Triage {len(priority_mails)} priority incoming email(s).")
    if meetings:
        focus_areas.append(f"Prepare for {len(meetings)} executive meeting(s) scheduled today.")
    if not focus_areas:
        focus_areas.append("No critical urgent operational items detected for today.")

    briefing = {
        "date": now_str,
        "executive_name": exec_name,
        "executive_email": userEmail or "connected-user@velora.ae",
        "summary_text": summary_text,
        "meetings_today": meetings,
        "tasks_to_do": tasks,
        "overdue_tasks": overdue,
        "teams_activity": teams_msgs,
        "priority_mails": priority_mails,
        "upcoming_approvals": approvals,
        "key_focus_areas": focus_areas,
        "degraded_sections": degraded_sections,
    }
    briefing["contentHash"] = compute_content_hash(briefing)

    latency = int((time.time() - start_ts) * 1000)
    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="GetDailyExecutiveBriefing",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(meetings) + len(tasks) + len(approvals),
        summary=summary_text,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status=status,
        summary=summary_text,
        structured_data=briefing,
        source_system="Microsoft 365 Graph",
        result_count=len(meetings),
        correlation_id=corr_id,
        warnings=warnings,
        audit_status=audit_status,
    )


# =====================================================================
# SPECIALIZED READ TOOLS (The 4 Failed Cases)
# =====================================================================

async def plan_my_day(
    userTimezone: str = "Asia/Dubai",
    timezone: Optional[str] = None,
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Combine live calendar events, overdue/due tasks, and urgent emails into an ordered chronological plan.
    
    Resolves user's timezone, detects conflicts, identifies available focus blocks,
    and isolates any failed source section with clear status attribution.
    """
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-plan-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)
    audit_svc = get_productivity_audit_service()

    resolved_tz = timezone or userTimezone or "Asia/Dubai"
    warnings: List[str] = []
    try:
        plan_result = client.plan_my_day(user_timezone=resolved_tz, user_email=userEmail)
        missing = plan_result.get("missingSections", [])
        if missing:
            warnings.extend([f"Missing live source: {m}" for m in missing])
        summary = (
            f"Prioritized daily plan constructed for {plan_result.get('targetDate')} ({plan_result.get('userTimezone')}): "
            f"{plan_result.get('scheduledMeetingsCount')} meetings, {plan_result.get('overdueTasksCount')} overdue/urgent tasks, "
            f"{len(plan_result.get('focusBlocks', []))} focus blocks identified."
        )
        if missing:
            summary += f" [Note: {len(missing)} source(s) unavailable: {', '.join(missing)}]"
        status = "SUCCESS"
        result_items = plan_result.get("chronologicalPlan", [])
    except (AccessDeniedError, GraphRateLimitError, GraphTimeoutError, GraphSourceUnavailableError, Exception) as ex:
        plan_result = {}
        result_items = []
        status, summary, warnings = _handle_read_error(ex, "PlanMyDay")

    latency = int((time.time() - start_ts) * 1000)
    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="PlanMyDay",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(result_items),
        summary=summary,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status=status,
        summary=summary,
        structured_data=plan_result,
        source_system="Microsoft 365 (Calendar, Planner, Mail)",
        result_count=len(result_items),
        correlation_id=corr_id,
        warnings=warnings,
        audit_status=audit_status,
    )


async def get_quick_action_checklist(
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Fetch live tasks, follow-ups, and upcoming meetings into a prioritized checklist with links.
    
    Every item traces directly to a real task, email, or meeting.
    Empty sources return an honest empty result, never hallucinated work.
    """
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-chk-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)
    audit_svc = get_productivity_audit_service()

    warnings: List[str] = []
    try:
        checklist_res = client.get_quick_action_checklist(user_email=userEmail)
        summary = checklist_res.get("statusSummary", "Quick-action checklist synthesized.")
        status = "SUCCESS" if not checklist_res.get("isEmpty") else "EMPTY"
        total_count = checklist_res.get("totalCount", 0)
    except (AccessDeniedError, GraphRateLimitError, GraphTimeoutError, GraphSourceUnavailableError, Exception) as ex:
        checklist_res = {}
        total_count = 0
        status, summary, warnings = _handle_read_error(ex, "GetQuickActionChecklist")

    latency = int((time.time() - start_ts) * 1000)
    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="GetQuickActionChecklist",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=total_count,
        summary=summary,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status=status,
        summary=summary,
        structured_data=checklist_res,
        source_system="Microsoft 365 (Planner, Mail, Calendar)",
        result_count=total_count,
        correlation_id=corr_id,
        warnings=warnings,
        audit_status=audit_status,
    )


async def get_executive_attention(
    lookbackHours: int = 48,
    maximumResults: int = 10,
    policyId: Optional[str] = None,
    rubricPolicy: Optional[Dict[str, Any]] = None,
    includeCalendar: bool = True,
    includeTasks: bool = True,
    timeZone: str = "Asia/Dubai",
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Ranked attention items across inbox, calendar and meetings with contextual priority scores (Operation: GET_EXECUTIVE_ATTENTION).
    
    Normalizes candidate messages, calendar events, and planner tasks into AttentionItem contracts.
    Calculates priorityScore = round_half_up(100 * sum(weight_i * factor_i / 5)) using exact Decimals.
    Ranks items deterministically: totalScore desc -> earlier known deadline -> stable itemId.
    Triage is strictly read-only: does not send emails or mutate calendar.
    """
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-attn-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)
    audit_svc = get_productivity_audit_service()
    ref_now = now or datetime.now(timezone.utc)

    warnings: List[str] = []
    claims: List[MaterialClaim] = []
    sources: List[EvidenceSource] = []
    items: List[Dict[str, Any]] = []

    try:
        # Validate mailbox boundary
        client._validate_user_mailbox(userEmail)

        # 1. Fetch Candidate Mails (including normal importance)
        date_from_dt = ref_now - timedelta(hours=lookbackHours)
        date_from_str = date_from_dt.isoformat()
        mail_candidates = []
        try:
            mail_candidates = client.search_mail(
                date_from=date_from_str,
                max_results=max(maximumResults * 2, 20),
            )
        except Exception as mail_err:
            warnings.append(f"Mail candidate retrieval degraded: {mail_err}")

        # 2. Fetch Candidate Calendar Events
        calendar_candidates = []
        if includeCalendar:
            try:
                date_to_str = (ref_now + timedelta(hours=lookbackHours)).isoformat()
                calendar_candidates = client.list_calendar_events(
                    date_from=ref_now.isoformat(),
                    date_to=date_to_str,
                    time_zone=timeZone,
                    max_results=maximumResults,
                )
            except Exception as cal_err:
                warnings.append(f"Calendar candidate retrieval degraded: {cal_err}")

        # 3. Fetch Candidate Tasks / Meeting Actions
        task_candidates = []
        if includeTasks:
            try:
                overdue = client.find_overdue_tasks()
                all_tasks = client.list_planner_tasks(my_tasks_only=True)
                seen_task_ids = set()
                for t in overdue + all_tasks:
                    tid = t.get("id")
                    if tid and tid not in seen_task_ids:
                        seen_task_ids.add(tid)
                        task_candidates.append(t)
            except Exception as tsk_err:
                warnings.append(f"Task candidate retrieval degraded: {tsk_err}")

        # 4. Resolve Rubric Policy
        if rubricPolicy:
            rubric = TriageRubricPolicy(**rubricPolicy)
        elif policyId:
            rubric = TriageRubricPolicy(policyId=policyId, isTestPolicy=True)
        else:
            rubric = TEST_EQUAL_WEIGHTS_RUBRIC

        # 5. Score Candidates Pipeline
        scored_attention_items = score_candidates_pipeline(
            mail_candidates=mail_candidates,
            calendar_candidates=calendar_candidates,
            task_candidates=task_candidates,
            rubric=rubric,
            now=ref_now,
            maximum_results=maximumResults,
            default_tz_offset="+04:00",
        )

        for item in scored_attention_items:
            item_dict = item.model_dump()
            items.append(item_dict)

            # Synthesize MaterialClaim
            claims.append(
                MaterialClaim(
                    claimId=f"CLM-{item.itemId}",
                    kind=ClaimKind.EVALUATION,
                    text=f"Rank #{item.rank}: {item.title} (Score: {item.totalScore}/100) — {item.requiredAttention}",
                    sourceIds=item.sourceRecordReferences,
                    calculationVersion=item.scoringVersion,
                    confidenceAssessment=item.claimConfidence,
                    limitations=item.missingFactors,
                )
            )

            # Synthesize EvidenceSource
            for s_id in item.sourceRecordReferences:
                sources.append(
                    EvidenceSource(
                        sourceId=s_id,
                        system="Microsoft 365",
                        businessTitle=f"{item.itemType}: {item.title[:40]}",
                        providerRecordId=s_id,
                        retrievedAt=ref_now.isoformat(),
                        sourceUpdatedAt=None,
                        limitations=[f"Missing factors: {', '.join(item.missingFactors)}"] if item.missingFactors else [],
                    )
                )

        latency = int((time.time() - start_ts) * 1000)
        if items:
            status = "SUCCESS" if not warnings else "PARTIAL"
            summary = f"Identified {len(items)} prioritized attention item(s) across inbox, calendar, and tasks."
        else:
            status = "EMPTY"
            summary = "No attention items found requiring executive intervention in the specified window."

    except (AccessDeniedError, GraphRateLimitError, GraphTimeoutError, GraphSourceUnavailableError, Exception) as ex:
        items = []
        latency = int((time.time() - start_ts) * 1000)
        status, summary, err_warnings = _handle_read_error(ex, "GetExecutiveAttention")
        warnings.extend(err_warnings)

    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="GetExecutiveAttention",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(items),
        summary=summary,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    return _create_read_envelope(
        status=status,
        summary=summary,
        structured_data=items,
        source_system="Microsoft 365 (Outlook, Calendar, Planner)",
        result_count=len(items),
        correlation_id=corr_id,
        warnings=warnings,
        audit_status=audit_status,
        claims=claims,
        sources=sources,
    )


async def get_pre_meeting_brief(
    eventId: Optional[str] = None,
    leadTimeMinutes: int = 15,
    userTimezone: str = "Asia/Dubai",
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Retrieve synthesized Pre-Meeting Dossier Briefing for upcoming non-canceled meeting."""
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-premeet-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)
    audit_svc = get_productivity_audit_service()
    service = get_briefing_service()

    briefing = service.get_pre_meeting_briefing(
        client=client,
        user_email=userEmail or "balaadm@velora.ae",
        event_id=eventId,
        lead_time_minutes=leadTimeMinutes,
    )
    latency = int((time.time() - start_ts) * 1000)

    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="GetPreMeetingBrief",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=1 if briefing.get("targetEvent") else 0,
        summary=briefing.get("summary_text", "Pre-meeting briefing compiled"),
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    claims = [MaterialClaim(**c) for c in briefing.get("claims", [])] if briefing.get("claims") else []
    sources = [EvidenceSource(**s) for s in briefing.get("sources", [])] if briefing.get("sources") else []
    conf = ConfidenceAssessment(**briefing["confidence"]) if briefing.get("confidence") else None

    return _create_read_envelope(
        status=briefing.get("status", "SUCCESS"),
        summary=briefing.get("summary_text", "Pre-meeting briefing compiled"),
        structured_data=briefing,
        source_system="Microsoft 365 Graph (Calendar, Mail, Planner)",
        result_count=1 if briefing.get("targetEvent") else 0,
        correlation_id=corr_id,
        warnings=[],
        audit_status=audit_status,
        claims=claims,
        sources=sources,
        confidence=conf,
    )


async def get_end_of_day_digest(
    localSchedule: Optional[str] = None,
    userTimezone: str = "Asia/Dubai",
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
    userObjectId: str = "",
    userEmail: str = "",
) -> Dict[str, Any]:
    """Retrieve synthesized End-of-Day Digest with ground truth task/meeting completions."""
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-eod-{int(time.time() * 1000)}"
    client = Microsoft365Client(user_email=userEmail)
    audit_svc = get_productivity_audit_service()
    service = get_briefing_service()

    digest = service.get_end_of_day_digest(
        client=client,
        user_email=userEmail or "balaadm@velora.ae",
        local_schedule=localSchedule,
    )
    latency = int((time.time() - start_ts) * 1000)

    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="GetEndOfDayDigest",
        root_correlation_id=corr_id,
        user_object_id=userObjectId,
        user_email=userEmail,
        result_count=len(digest.get("completed_tasks", [])) + len(digest.get("held_meetings", [])),
        summary=digest.get("summary_text", "End-of-day digest compiled"),
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    claims = [MaterialClaim(**c) for c in digest.get("claims", [])] if digest.get("claims") else []
    sources = [EvidenceSource(**s) for s in digest.get("sources", [])] if digest.get("sources") else []
    conf = ConfidenceAssessment(**digest["confidence"]) if digest.get("confidence") else None

    return _create_read_envelope(
        status=digest.get("status", "SUCCESS"),
        summary=digest.get("summary_text", "End-of-day digest compiled"),
        structured_data=digest,
        source_system="Microsoft 365 Graph (Planner, Calendar, Mail)",
        result_count=len(digest.get("completed_tasks", [])) + len(digest.get("held_meetings", [])),
        correlation_id=corr_id,
        warnings=digest.get("warnings", []),
        audit_status=audit_status,
        claims=claims,
        sources=sources,
        confidence=conf,
    )


async def get_meeting_action_tracker(
    meetingId: Optional[str] = None,
    sourceVersion: Optional[str] = None,
    userEmail: str = "balaadm@velora.ae",
    tenantId: str = "velora-aviation",
    rootCorrelationId: str = "",
    conversationId: str = "",
    turnId: str = "",
) -> Dict[str, Any]:
    """Retrieve live meeting action tracker with provider synchronization, percentComplete, and overdue status."""
    from .meeting_actions import get_meeting_action_tracker as _get_tracker
    start_ts = time.time()
    corr_id = rootCorrelationId or f"corr-track-{int(time.time() * 1000)}"
    audit_svc = get_productivity_audit_service()

    res = await _get_tracker(
        meeting_id=meetingId,
        source_version=sourceVersion,
        user_email=userEmail,
        tenant_id=tenantId,
        root_correlation_id=corr_id,
    )

    latency = int((time.time() - start_ts) * 1000)
    tracker_rows = res.get("trackerRows", [])
    summary = res.get("summary", "Meeting Action Tracker refreshed")

    audit_status = await audit_svc.audit_read_tool_execution(
        tool_name="GetMeetingActionTracker",
        root_correlation_id=corr_id,
        user_object_id="",
        user_email=userEmail,
        result_count=len(tracker_rows),
        summary=summary,
        latency_ms=latency,
        conversation_id=conversationId,
        turn_id=turnId,
    )

    conf = ConfidenceAssessment(
        label=ConfidenceLabel.HIGH if res.get("status") == "SUCCESS" else ConfidenceLabel.LOW,
        frameworkVersion="v1.0",
        sourceReliability="AUTHORITATIVE",
        corroboration="VERIFIED_GRAPH_PLANNER",
        timeliness="REAL_TIME_SYNC",
        completeness="COMPLETE" if res.get("status") == "SUCCESS" else "PARTIAL",
        comparability="CANONICAL",
        reason="Tracker synced live from Microsoft Graph Planner provider.",
    )

    source_ids = [r.get("taskId") for r in tracker_rows if r.get("taskId")]
    if not source_ids:
        source_ids = ["src-graph-planner-tasks"]

    sources = [
        EvidenceSource(
            sourceId=r.get("taskId", f"task-{idx}"),
            system="Microsoft Graph Planner & Dataverse",
            businessTitle=r.get("title", "Meeting Action Task"),
            providerRecordId=r.get("taskId", ""),
            url=r.get("realTaskReference"),
            retrievedAt=datetime.now(timezone.utc).isoformat(),
        )
        for idx, r in enumerate(tracker_rows)
    ]
    if not sources:
        sources = [
            EvidenceSource(
                sourceId="src-graph-planner-tasks",
                system="Microsoft Graph Planner & Dataverse",
                businessTitle="Planner Tasks Registry",
                providerRecordId=meetingId or "all-meetings",
                url="https://tasks.office.com",
                retrievedAt=datetime.now(timezone.utc).isoformat(),
            )
        ]

    claims = [
        MaterialClaim(
            claimId=f"claim-tracker-{int(time.time() * 1000)}",
            kind=ClaimKind.FACT,
            text=summary,
            sourceIds=source_ids,
            confidenceAssessment=conf,
        )
    ]

    return _create_read_envelope(
        status=res.get("status", "SUCCESS"),
        summary=summary,
        structured_data=res,
        source_system="Microsoft 365 Graph (Planner & Tasks)",
        result_count=len(tracker_rows),
        correlation_id=corr_id,
        warnings=res.get("warnings", []),
        audit_status=audit_status,
        claims=claims,
        sources=sources,
        confidence=conf,
    )




