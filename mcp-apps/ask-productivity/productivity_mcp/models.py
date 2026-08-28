"""Strongly-typed Pydantic models, contracts, and envelopes for Velora Productivity Agent."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# --- Standard Output Envelopes (Section 5.4 & 13) ---

class ReadToolEnvelope(BaseModel):
    """Standardized output envelope for all Microsoft 365 and Work IQ read tools."""
    status: str = Field(description="Execution status: SUCCESS, EMPTY, PARTIAL, ERROR, etc.")
    resultSummary: str = Field(description="Safe executive natural language summary")
    structuredResult: Any = Field(description="Structured records, threads, meetings, or task list")
    sourceSystem: str = Field(default="Microsoft365", description="Authoritative source system: Outlook, Teams, Planner, WorkIQ")
    sourceAsOf: str = Field(description="ISO-8601 timestamp of data freshness")
    resultCount: int = Field(default=0, description="Total number of matching entities returned")
    warnings: List[str] = Field(default_factory=list, description="Policy, privacy, or freshness warnings")
    correlationId: str = Field(description="Preserved root correlation ID")
    auditStatus: str = Field(default="PERSISTED", description="Dataverse audit logging status")


class WritePreviewEnvelope(BaseModel):
    """Standardized output envelope for Stage A (Prepare) operations."""
    status: str = Field(default="PREVIEW_READY", description="Status code: PREVIEW_READY, VALIDATION_ERROR, POLICY_BLOCKED")
    approvalRequired: bool = Field(default=True, description="Strict requirement for explicit executive approval")
    resultSummary: str = Field(description="Executive preview summary")
    confirmationToken: str = Field(description="Short-lived HMAC approval token")
    correlationId: str = Field(description="Preserved root correlation ID")
    auditStatus: str = Field(default="PERSISTED", description="Dataverse preview audit status")
    warnings: List[str] = Field(default_factory=list, description="Warnings (e.g. external recipient, channel size)")
    previewDetails: Dict[str, Any] = Field(description="Full preview attributes (To, Cc, Subject, Body, Time, etc.)")
    expiresOn: str = Field(description="ISO-8601 timestamp when approval token expires")
    idempotencyKey: str = Field(description="Unique key to prevent duplicate execution")


class WriteResultEnvelope(BaseModel):
    """Standardized output envelope for Stage B (Execute Approved) operations."""
    status: str = Field(description="Execution status: SUCCESS, ERROR, REJECTED, DUPLICATE_BLOCKED, FAIL_CLOSED_BLOCKED")
    resultSummary: str = Field(description="Final executive confirmation message")
    externalObjectId: str = Field(default="", description="Platform confirmed Microsoft 365 ID (messageId, eventId, taskId)")
    evidenceLink: str = Field(default="", description="Deep link or web URL to confirmed item")
    correlationId: str = Field(description="Preserved root correlation ID")
    auditStatus: str = Field(default="PERSISTED", description="Dataverse audit completion status")
    warnings: List[str] = Field(default_factory=list, description="Any operational or audit warnings")


# --- Stage A Preview Detail Models (Sections 8.3, 9.2, 10.3, 11.3) ---

class EmailPreview(BaseModel):
    actingUser: str
    to: List[str]
    cc: List[str] = Field(default_factory=list)
    subject: str
    body: str
    attachments: List[str] = Field(default_factory=list)
    sensitivity: str = "CONFIDENTIAL"
    hasExternalRecipients: bool = False
    externalRecipients: List[str] = Field(default_factory=list)
    correlationId: str
    approvalExpiresOn: str


class MeetingPreview(BaseModel):
    organizer: str
    subject: str
    attendees: List[str]
    startTime: str
    endTime: str
    timeZone: str
    location: str
    isTeamsMeeting: bool = True
    recurrence: str = "None"
    body: str
    existingEventId: Optional[str] = None
    changesSummary: Optional[str] = None
    conflictsDetected: List[str] = Field(default_factory=list)
    correlationId: str
    approvalExpiresOn: str


class TeamsMessagePreview(BaseModel):
    sender: str
    destinationType: str  # "CHAT" or "CHANNEL"
    chatId: Optional[str] = None
    teamName: Optional[str] = None
    channelName: Optional[str] = None
    recipients: List[str] = Field(default_factory=list)
    messageContent: str
    containsSapData: bool = False
    isBroadChannel: bool = False
    correlationId: str
    approvalExpiresOn: str


class PlannerTaskPreview(BaseModel):
    groupName: str
    planName: str
    bucketName: str
    taskTitle: str
    description: str
    assignees: List[str] = Field(default_factory=list)
    startDate: Optional[str] = None
    dueDate: Optional[str] = None
    priority: str = "Medium"
    existingTaskId: Optional[str] = None
    changesSummary: Optional[str] = None
    correlationId: str
    approvalExpiresOn: str


# --- Operation Parameter Models for Handoff Contract (Section 15) ---

class GetMailThreadParameters(BaseModel):
    threadId: str
    maxMessages: int = 10


class GetPriorityMailParameters(BaseModel):
    top: int = 10
    unreadOnly: bool = False
    hoursLookback: int = 48


class GetMailFollowUpsParameters(BaseModel):
    daysLookback: int = 7
    top: int = 10


class PrepareEmailReplyParameters(BaseModel):
    messageId: str
    replyBody: str
    replyAll: bool = False


class GetCalendarEventsParameters(BaseModel):
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    top: int = 10


class GetMeetingContextParameters(BaseModel):
    eventId: str


class PrepareMeetingUpdateParameters(BaseModel):
    eventId: str
    subject: Optional[str] = None
    startTime: Optional[str] = None
    endTime: Optional[str] = None
    body: Optional[str] = None


class PrepareMeetingCancellationParameters(BaseModel):
    eventId: str
    cancellationComment: Optional[str] = None


class GetTeamsChannelContextParameters(BaseModel):
    teamId: str
    channelId: str
    top: int = 15


class GetTeamsChatContextParameters(BaseModel):
    chatId: str
    top: int = 15


class GetTeamsFollowUpsParameters(BaseModel):
    daysLookback: int = 7
    top: int = 10


class PrepareTeamsChatSendParameters(BaseModel):
    chatId: Optional[str] = None
    recipientEmail: Optional[str] = None
    messageContent: str = ""


class PrepareTeamsChannelPostParameters(BaseModel):
    teamId: str
    channelId: str
    subject: Optional[str] = None
    messageContent: str = ""


class GetPlannerUserTasksParameters(BaseModel):
    statusFilter: str = "INCOMPLETE"
    top: int = 20


class GetPlannerPlanTasksParameters(BaseModel):
    planId: str
    bucketId: Optional[str] = None
    top: int = 50


class PreparePlannerTaskCreateParameters(BaseModel):
    planId: str
    bucketId: str
    title: str
    description: Optional[str] = None
    dueDate: Optional[str] = None
    assignees: List[str] = Field(default_factory=list)


class PreparePlannerTaskUpdateParameters(BaseModel):
    taskId: str
    percentComplete: Optional[int] = None
    dueDate: Optional[str] = None
    title: Optional[str] = None


# --- Handoff Contracts (Section 13) ---

class HandoffRequest(BaseModel):
    """Parent Velora Agent to Connected Productivity Agent request contract."""
    task: str = Field(description="High-level requested task description")
    operation: str = Field(description="Standardized operation name e.g. PREPARE_EMAIL, SEARCH_MAIL")
    rootCorrelationId: str = Field(description="Root correlation ID generated by parent")
    conversationId: str = Field(description="Parent Copilot conversation ID")
    turnId: str = Field(description="Parent turn ID")
    userObjectId: str = Field(description="Signed-in Entra Object ID")
    userEmail: str = Field(description="Signed-in user email")
    userTimezone: str = Field(default="Asia/Dubai", description="User preferred IANA time zone")
    channel: str = Field(default="Microsoft365Copilot", description="Client channel")
    dataClassification: str = Field(default="CONFIDENTIAL", description="Data sensitivity classification")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Operation specific parameters")


class HandoffResponse(BaseModel):
    """Connected Productivity Agent to Parent Velora Agent response contract."""
    status: str = Field(description="Status code: PREVIEW_READY, SUCCESS, ERROR, POLICY_BLOCKED")
    approvalRequired: bool = Field(default=False, description="Whether explicit parent confirmation is required")
    resultSummary: str = Field(description="Safe executive summary")
    confirmationToken: Optional[str] = Field(default=None, description="Approval token for Stage B execution")
    correlationId: str = Field(description="Echoed root correlation ID")
    auditStatus: str = Field(default="PERSISTED", description="Dataverse audit persistence status")
    warnings: List[str] = Field(default_factory=list, description="Any warnings")
    previewDetails: Optional[Dict[str, Any]] = Field(default=None, description="Preview payload if approvalRequired is true")
    structuredResult: Optional[Any] = Field(default=None, description="Result payload if read operation")
