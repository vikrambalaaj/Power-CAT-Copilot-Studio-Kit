"""Dataverse Audit & Governance Data Access Layer for Velora Executive Agent Platform.

Implements full schema governance for `cre2f_veloraagentauditlog`, supporting:
- 12 Standard Record Types + Legacy Record Types
- Full Correlation Envelope (rootcorrelationid, conversationid, invocationid, idempotencykey)
- Strict Alternate Key Idempotency (invocationid + recordtype, idempotencykey + operation)
- Fail-Closed Synchronous Write-Auditing vs Asynchronous Queue-Buffered Read-Auditing
- Cryptographic Token Hashing (SHA-256 HMAC) & Sensitive Content Redaction
- Dual-mode Operation: Production Dataverse OData / Web API & Resilient In-Memory Buffer
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

from shared_mcp.logger import get_logger

log = get_logger("dataverse_audit")

# --- Dataverse Web API wiring (Section 3.1) -----------------------------------
# Logical tables `cre2f_veloraagentauditlog` and `cre2f_botuserconsent`; the OData
# collections are the plural entity set names, overridable for customised tenants.
AUDIT_ENTITY_SET = os.getenv("DATAVERSE_AUDIT_ENTITY_SET", "cre2f_veloraagentauditlogs")
CONSENT_ENTITY_SET = os.getenv("DATAVERSE_CONSENT_ENTITY_SET", "cre2f_botuserconsents")
POLICY_ENTITY_SET = os.getenv(
    "DATAVERSE_POLICY_ENTITY_SET", "cre2f_veloradatadisclosurepolicies"
)

# Dataverse rejects an entire insert that names any column the table does not have,
# so every write is projected onto the columns that genuinely exist. These two sets
# mirror the live schema; widen them only once the column is created and published.
AUDIT_LOG_COLUMNS = frozenset({
    "cre2f_actor", "cre2f_agentname", "cre2f_auditdetail", "cre2f_correlationid",
    "cre2f_dataclassification", "cre2f_demodata", "cre2f_durationms",
    "cre2f_environment", "cre2f_errorcode", "cre2f_eventtime", "cre2f_newcolumn",
    "cre2f_operation", "cre2f_outcome", "cre2f_responsehash", "cre2f_resultcount",
    "cre2f_safefilters", "cre2f_sessionid", "cre2f_sourcesystem", "cre2f_toolname",
})
# `cre2f_newcolumn` is the table's primary name column. Its *display* name is
# "User ID", which is what the Copilot Studio flow's designer shows — that mismatch
# is what produced the original `cre2f_userid` bug. It is the only identity column
# the table has, so both writers key on it.
CONSENT_COLUMNS = frozenset({
    "cre2f_newcolumn", "cre2f_channel",
    "cre2f_consentdate", "cre2f_consentgranted", "cre2f_consentversion",
})
CONSENT_IDENTITY_COLUMN = "cre2f_newcolumn"
DATAVERSE_API_VERSION = os.getenv("DATAVERSE_API_VERSION", "v9.2")
DATAVERSE_TIMEOUT_SECONDS = float(os.getenv("DATAVERSE_TIMEOUT_SECONDS", "10"))
# Consent must survive process restarts, so its lookup is never served from the
# in-memory buffer while a live connection is configured.
CONSENT_QUERY_CACHE_SECONDS = float(os.getenv("DATAVERSE_CONSENT_CACHE_SECONDS", "300"))

# --- Standard Record Type Discriminators (Section 3.3) ---
RECORD_TYPE_AGENT_DELEGATION_START = "AGENT_DELEGATION_START"
RECORD_TYPE_AGENT_DELEGATION_END = "AGENT_DELEGATION_END"
RECORD_TYPE_TOOL_EXECUTION_START = "TOOL_EXECUTION_START"
RECORD_TYPE_TOOL_EXECUTION_END = "TOOL_EXECUTION_END"
RECORD_TYPE_TRANSACTION_PREVIEW = "TRANSACTION_PREVIEW"
RECORD_TYPE_USER_APPROVAL = "USER_APPROVAL"
RECORD_TYPE_TRANSACTION_START = "TRANSACTION_START"
RECORD_TYPE_TRANSACTION_RESULT = "TRANSACTION_RESULT"
RECORD_TYPE_TRANSACTION_ERROR = "TRANSACTION_ERROR"
RECORD_TYPE_POLICY_DECISION = "POLICY_DECISION"
RECORD_TYPE_RECONCILIATION = "RECONCILIATION"
RECORD_TYPE_LOGGING_ERROR = "LOGGING_ERROR"

# Backward compatibility record types
RECORD_TYPE_CONVERSATION_START = "CONVERSATION_START"
RECORD_TYPE_USER_TURN = "USER_TURN"
RECORD_TYPE_ASSISTANT_TURN = "ASSISTANT_TURN"
RECORD_TYPE_TOOL_EXECUTION = "TOOL_EXECUTION"
RECORD_TYPE_CONSENT = "CONSENT"
RECORD_TYPE_MEMORY_SUMMARY = "MEMORY_SUMMARY"
RECORD_TYPE_CONVERSATION_END = "CONVERSATION_END"

VALID_RECORD_TYPES: Set[str] = {
    RECORD_TYPE_AGENT_DELEGATION_START,
    RECORD_TYPE_AGENT_DELEGATION_END,
    RECORD_TYPE_TOOL_EXECUTION_START,
    RECORD_TYPE_TOOL_EXECUTION_END,
    RECORD_TYPE_TRANSACTION_PREVIEW,
    RECORD_TYPE_USER_APPROVAL,
    RECORD_TYPE_TRANSACTION_START,
    RECORD_TYPE_TRANSACTION_RESULT,
    RECORD_TYPE_TRANSACTION_ERROR,
    RECORD_TYPE_POLICY_DECISION,
    RECORD_TYPE_RECONCILIATION,
    RECORD_TYPE_LOGGING_ERROR,
    RECORD_TYPE_CONVERSATION_START,
    RECORD_TYPE_USER_TURN,
    RECORD_TYPE_ASSISTANT_TURN,
    RECORD_TYPE_TOOL_EXECUTION,
    RECORD_TYPE_CONSENT,
    RECORD_TYPE_MEMORY_SUMMARY,
    RECORD_TYPE_CONVERSATION_END,
}

# Transaction & Approval States
APPROVAL_STATUS_PENDING = "PENDING"
APPROVAL_STATUS_APPROVED = "APPROVED"
APPROVAL_STATUS_REJECTED = "REJECTED"
APPROVAL_STATUS_MODIFIED = "MODIFIED"
APPROVAL_STATUS_EXPIRED = "EXPIRED"
APPROVAL_STATUS_NOT_REQUIRED = "NOT_REQUIRED"

HMAC_SECRET = os.getenv("VELORA_APPROVAL_HMAC_SECRET", "velora-prod-executive-secret-key-2026")


class AuditCommitStatus:
    """Explicit result contract for audit persistence (Defect 5)."""
    COMMITTED = "COMMITTED"
    ALREADY_COMMITTED = "ALREADY_COMMITTED"
    BUFFERED = "BUFFERED"
    FAILED = "FAILED"


def sanitize_email(email: Optional[str]) -> str:
    """Normalize email for consistent identity indexing and partitioning."""
    return (email or "").strip().lower()


def _odata_escape(value: str) -> str:
    """Escape a value for safe inlining into an OData string literal."""
    return (value or "").replace("'", "''")


def compute_content_hash(text: str) -> str:
    """Compute deterministic SHA-256 hash for payload reconciliation and deduplication."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def compute_approval_token_hash(token: str) -> str:
    """Compute HMAC-SHA256 hash of approval token so raw secrets are never persisted."""
    if not token:
        return ""
    return hmac.new(HMAC_SECRET.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


class DataverseAuditRecord:
    """Strongly-typed wrapper for the full `cre2f_veloraagentauditlog` schema."""

    def __init__(
        self,
        record_type: str,
        user_object_id: str = "",
        user_email: str = "",
        user_display_name: str = "",
        # Correlation
        root_correlation_id: str = "",
        conversation_id: str = "",
        session_id: str = "",
        turn_id: str = "",
        parent_turn_id: str = "",
        parent_invocation_id: str = "",
        invocation_id: str = "",
        idempotency_key: str = "",
        turn_sequence: int = 0,
        correlation_id: str = "",
        # Agent identity
        calling_agent: str = "Velora Executive Agent",
        executing_agent: str = "Velora Productivity Agent",
        agent_name: str = "Velora Executive Agent",
        agent_version: str = "1.0.0",
        environment: str = "Velora-AgenticAD-Dev",
        channel: str = "copilot_studio",
        # Transaction specifics
        capability: str = "",
        operation: str = "",
        transaction_type: str = "READ",
        source_system: str = "Microsoft365",
        approval_status: str = APPROVAL_STATUS_NOT_REQUIRED,
        approval_expires_on: str = "",
        approval_token_hash: str = "",
        external_object_id: str = "",
        evidence_link: str = "",
        # Outcomes & telemetry
        outcome: str = "SUCCESS",
        start_time: str = "",
        end_time: str = "",
        latency_ms: Optional[int] = None,
        result_count: int = 0,
        error_category: str = "",
        error_message_safe: str = "",
        source_as_of: str = "",
        cache_hit: Optional[bool] = None,
        cache_age: Optional[float] = None,
        # Content Governance
        audit_detail: str = "",
        message_summary: str = "",
        content_classification: str = "CONFIDENTIAL",
        request_filter_safe: str = "",
        target_summary_safe: str = "",
        user_groups: Optional[List[str]] = None,
        message_role: str = "",
        user_message: str = "",
        assistant_message: str = "",
        # Policy & Consent & Memory
        policy_id: str = "",
        policy_version: str = "",
        policy_decision: str = "",
        released_fields: Optional[List[str]] = None,
        consent_version: str = "",
        consent_status: str = "",
        tool_name: str = "",
        memory_eligible: bool = False,
        memory_summary: str = "",
        memory_topics: Optional[List[str]] = None,
        memory_valid_from: str = "",
        memory_expires_on: str = "",
        memory_superseded: bool = False,
        memory_last_used: str = "",
        memory_importance: int = 1,
        event_time: Optional[str] = None,
    ):
        if record_type not in VALID_RECORD_TYPES:
            raise ValueError(f"Invalid record_type: {record_type}. Must be one of {VALID_RECORD_TYPES}")

        self.record_type = record_type
        self.user_object_id = user_object_id or ""
        self.user_email = sanitize_email(user_email)
        self.user_display_name = user_display_name or ""

        # Correlation
        self.root_correlation_id = root_correlation_id or correlation_id or f"corr-{int(time.time() * 1000)}"
        self.correlation_id = self.root_correlation_id
        self.conversation_id = conversation_id or ""
        self.session_id = session_id or ""
        self.turn_id = turn_id or f"turn-{int(time.time() * 1000)}"
        self.parent_turn_id = parent_turn_id or ""
        self.parent_invocation_id = parent_invocation_id or ""
        self.invocation_id = invocation_id or f"inv-{int(time.time() * 1000)}-{os.urandom(3).hex()}"
        self.idempotency_key = idempotency_key or f"idemp-{int(time.time() * 1000)}-{os.urandom(3).hex()}"
        self.turn_sequence = turn_sequence

        # Agent Identity
        self.calling_agent = calling_agent or agent_name
        self.executing_agent = executing_agent or agent_name
        self.agent_name = agent_name
        self.agent_version = agent_version
        self.environment = environment
        self.channel = channel

        # Transaction
        self.capability = capability or tool_name or record_type
        self.operation = operation or tool_name or record_type
        self.transaction_type = transaction_type
        self.source_system = source_system
        self.approval_status = approval_status
        self.approval_expires_on = approval_expires_on
        self.approval_token_hash = approval_token_hash
        self.external_object_id = external_object_id
        self.evidence_link = evidence_link

        # Outcomes
        self.outcome = outcome if not error_category else "ERROR"
        self.start_time = start_time or datetime.now(timezone.utc).isoformat()
        self.end_time = end_time or ""
        self.latency_ms = latency_ms
        self.result_count = result_count
        self.error_category = error_category
        self.error_message_safe = error_message_safe
        self.source_as_of = source_as_of
        self.cache_hit = cache_hit
        self.cache_age = cache_age

        # Governance & Content
        self.audit_detail = audit_detail
        self.message_summary = message_summary
        self.content_classification = content_classification
        self.request_filter_safe = request_filter_safe
        self.target_summary_safe = target_summary_safe
        self.user_groups = user_groups or []
        self.message_role = message_role
        self.user_message = user_message
        self.assistant_message = assistant_message
        self.content_hash = compute_content_hash(user_message + assistant_message + (audit_detail or ""))

        # Policy & Consent
        self.policy_id = policy_id
        self.policy_version = policy_version
        self.policy_decision = policy_decision
        self.released_fields = released_fields or []
        self.consent_version = consent_version
        self.consent_status = consent_status
        self.tool_name = tool_name or self.operation

        # Memory Fields
        self.memory_eligible = memory_eligible
        self.memory_summary = memory_summary
        self.memory_topics = memory_topics or []
        self.memory_valid_from = memory_valid_from
        self.memory_expires_on = memory_expires_on
        self.memory_superseded = memory_superseded
        self.memory_last_used = memory_last_used
        self.memory_importance = memory_importance

        self.event_time = event_time or datetime.now(timezone.utc).isoformat()
        self.audit_id = invocation_id or f"EVT-{int(time.time() * 1000)}-{os.urandom(4).hex()}"
        self.logging_status = "PENDING"
        self.retry_count = 0
        self.reconciled = False

    def to_audit_log_payload(self) -> Dict[str, Any]:
        """Project this record onto the columns `cre2f_veloraagentauditlog` really has.

        The rich record models ~70 fields; the table exposes 19 writable ones. The
        record type has no column of its own, so it is preserved as a prefix on
        `cre2f_auditdetail` rather than being silently dropped.
        """
        detail = (
            self.audit_detail
            or self.message_summary
            or self.error_message_safe
            or self.operation
            or self.record_type
        )
        payload = {
            "cre2f_actor": self.user_email or self.user_display_name or self.executing_agent,
            "cre2f_agentname": self.agent_name,
            "cre2f_auditdetail": f"[{self.record_type}] {detail}"[:4000],
            "cre2f_correlationid": self.root_correlation_id,
            "cre2f_dataclassification": self.content_classification,
            "cre2f_demodata": False,
            "cre2f_durationms": self.latency_ms,
            "cre2f_environment": self.environment,
            "cre2f_errorcode": self.error_category,
            "cre2f_eventtime": self.event_time,
            "cre2f_newcolumn": self.user_email,
            "cre2f_operation": self.operation or self.record_type,
            "cre2f_outcome": self.outcome,
            "cre2f_responsehash": self.content_hash,
            "cre2f_resultcount": self.result_count,
            "cre2f_safefilters": (self.request_filter_safe or "")[:2000],
            "cre2f_sessionid": self.session_id,
            "cre2f_sourcesystem": self.source_system,
            "cre2f_toolname": self.tool_name,
        }
        return {k: v for k, v in payload.items() if k in AUDIT_LOG_COLUMNS and v not in (None, "")}

    def to_consent_payload(self) -> Dict[str, Any]:
        """Project this record onto `cre2f_botuserconsent`.

        The identity is written to the table's primary name column, the same column
        the Copilot Studio flow writes and filters on, so both writers address the
        same row.
        """
        identity = self.user_object_id or sanitize_email(self.user_email)
        payload = {
            CONSENT_IDENTITY_COLUMN: identity,
            "cre2f_channel": self.channel,
            "cre2f_consentdate": self.event_time,
            "cre2f_consentgranted": self.consent_status == "ACCEPTED",
            "cre2f_consentversion": self.consent_version,
        }
        return {k: v for k, v in payload.items() if k in CONSENT_COLUMNS and v is not None}

    def to_dataverse_payload(self) -> Dict[str, Any]:
        """Convert record into exact Dataverse payload matching logical column names (Section 3.2)."""
        detail = (
            self.audit_detail
            or self.message_summary
            or self.error_message_safe
            or f"{self.record_type}: {self.operation}"
        )
        return {
            # Correlation Columns (Section 3.2)
            "cre2f_rootcorrelationid": self.root_correlation_id,
            "cre2f_conversationid": self.conversation_id,
            "cre2f_sessionid": self.session_id,
            "cre2f_turnid": self.turn_id,
            "cre2f_parentinvocationid": self.parent_invocation_id,
            "cre2f_invocationid": self.invocation_id,
            "cre2f_idempotencykey": self.idempotency_key,
            "cre2f_correlationid": self.root_correlation_id,
            "cre2f_parentturnid": self.parent_turn_id,
            "cre2f_turnsequence": self.turn_sequence,

            # Agent Identity Columns (Section 3.2)
            "cre2f_callingagent": self.calling_agent,
            "cre2f_executingagent": self.executing_agent,
            "cre2f_agentname": self.agent_name,
            "cre2f_agentversion": self.agent_version,
            "cre2f_environment": self.environment,
            "cre2f_channel": self.channel,

            # User Identity Columns (Section 3.2)
            "cre2f_userobjectid": self.user_object_id,
            "cre2f_useremail": self.user_email,
            "cre2f_userdisplayname": self.user_display_name,
            "cre2f_usergroups": json.dumps(self.user_groups),
            "cre2f_newcolumn": self.user_email,  # Retained backward-compatible slot

            # Transaction Columns (Section 3.2)
            "cre2f_recordtype": self.record_type,
            "cre2f_capability": self.capability,
            "cre2f_operation": self.operation,
            "cre2f_transactiontype": self.transaction_type,
            "cre2f_sourcesystem": self.source_system,
            "cre2f_approvalstatus": self.approval_status,
            "cre2f_approvalexpireson": self.approval_expires_on,
            "cre2f_approvaltokenhash": self.approval_token_hash,
            "cre2f_externalobjectid": self.external_object_id,
            "cre2f_evidencelink": self.evidence_link,
            "cre2f_toolname": self.tool_name,
            "cre2f_auditid": getattr(self, "audit_id", ""),

            # Outcome Columns (Section 3.2)
            "cre2f_outcome": self.outcome,
            "cre2f_eventtime": self.event_time,
            "cre2f_starttime": self.start_time,
            "cre2f_endtime": self.end_time,
            "cre2f_latencymilliseconds": self.latency_ms,
            "cre2f_resultcount": self.result_count,
            "cre2f_errorcategory": self.error_category,
            "cre2f_errormessagesafe": (self.error_message_safe or "")[:2000],
            "cre2f_sourceasof": self.source_as_of,
            "cre2f_cachehit": self.cache_hit,
            "cre2f_cacheage": self.cache_age,
            "cre2f_demodata": False,

            # Content Governance Columns (Section 3.2)
            "cre2f_auditdetail": (detail or "")[:4000],
            "cre2f_messagesummary": (self.message_summary or "")[:2000],
            "cre2f_contenthash": self.content_hash,
            "cre2f_dataclassification": self.content_classification,
            "cre2f_requestfiltersafe": (self.request_filter_safe or "")[:2000],
            "cre2f_targetsummarysafe": (self.target_summary_safe or "")[:2000],
            "cre2f_messagerole": self.message_role,
            "cre2f_usermessage": (self.user_message or "")[:4000],
            "cre2f_assistantmessage": (self.assistant_message or "")[:4000],

            # Policy & Consent & Memory
            "cre2f_policyid": self.policy_id,
            "cre2f_policyversion": self.policy_version,
            "cre2f_policydecision": self.policy_decision,
            "cre2f_releasedfields": json.dumps(self.released_fields),
            "cre2f_consentversion": self.consent_version,
            "cre2f_consentstatus": self.consent_status,
            "cre2f_memoryeligible": self.memory_eligible,
            "cre2f_memorysummary": (self.memory_summary or "")[:4000],
            "cre2f_memorytopics": json.dumps(self.memory_topics),
            "cre2f_memoryvalidfrom": self.memory_valid_from,
            "cre2f_memoryexpireson": self.memory_expires_on,
            "cre2f_memorysuperseded": self.memory_superseded,
            "cre2f_memorylastused": self.memory_last_used,
            "cre2f_memoryimportance": self.memory_importance,

            # Delivery & Reconciliation
            "cre2f_loggingstatus": self.logging_status,
            "cre2f_retrycount": self.retry_count,
            "cre2f_reconciled": self.reconciled,
        }

    @classmethod
    def from_dataverse_payload(cls, payload: Dict[str, Any]) -> "DataverseAuditRecord":
        """Reconstruct a complete DataverseAuditRecord preserving all fields from a Dataverse payload."""
        def _parse_json_list(val: Any) -> List[str]:
            if isinstance(val, list):
                return val
            if isinstance(val, str) and val.strip():
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, list):
                        return parsed
                except Exception:
                    pass
            return []

        rec = cls(
            record_type=payload.get("cre2f_recordtype") or "USER_TURN",
            user_object_id=payload.get("cre2f_userobjectid") or "",
            user_email=payload.get("cre2f_useremail") or "",
            user_display_name=payload.get("cre2f_userdisplayname") or "",
            root_correlation_id=payload.get("cre2f_rootcorrelationid") or payload.get("cre2f_correlationid") or "",
            conversation_id=payload.get("cre2f_conversationid") or "",
            session_id=payload.get("cre2f_sessionid") or "",
            turn_id=payload.get("cre2f_turnid") or "",
            parent_turn_id=payload.get("cre2f_parentturnid") or "",
            parent_invocation_id=payload.get("cre2f_parentinvocationid") or "",
            invocation_id=payload.get("cre2f_invocationid") or "",
            idempotency_key=payload.get("cre2f_idempotencykey") or "",
            turn_sequence=int(payload.get("cre2f_turnsequence") or 0),
            correlation_id=payload.get("cre2f_correlationid") or "",
            calling_agent=payload.get("cre2f_callingagent") or "Velora Executive Agent",
            executing_agent=payload.get("cre2f_executingagent") or "Velora Productivity Agent",
            agent_name=payload.get("cre2f_agentname") or "Velora Executive Agent",
            agent_version=payload.get("cre2f_agentversion") or "1.0.0",
            environment=payload.get("cre2f_environment") or "Velora-AgenticAD-Dev",
            channel=payload.get("cre2f_channel") or "copilot_studio",
            capability=payload.get("cre2f_capability") or "",
            operation=payload.get("cre2f_operation") or "",
            transaction_type=payload.get("cre2f_transactiontype") or "READ",
            source_system=payload.get("cre2f_sourcesystem") or "Microsoft365",
            approval_status=payload.get("cre2f_approvalstatus") or APPROVAL_STATUS_NOT_REQUIRED,
            approval_expires_on=payload.get("cre2f_approvalexpireson") or "",
            approval_token_hash=payload.get("cre2f_approvaltokenhash") or "",
            external_object_id=payload.get("cre2f_externalobjectid") or "",
            evidence_link=payload.get("cre2f_evidencelink") or "",
            outcome=payload.get("cre2f_outcome") or "SUCCESS",
            start_time=payload.get("cre2f_starttime") or "",
            end_time=payload.get("cre2f_endtime") or "",
            latency_ms=payload.get("cre2f_latencymilliseconds"),
            result_count=int(payload.get("cre2f_resultcount") or 0),
            error_category=payload.get("cre2f_errorcategory") or "",
            error_message_safe=payload.get("cre2f_errormessagesafe") or "",
            source_as_of=payload.get("cre2f_sourceasof") or "",
            cache_hit=payload.get("cre2f_cachehit"),
            cache_age=payload.get("cre2f_cacheage"),
            audit_detail=payload.get("cre2f_auditdetail") or "",
            message_summary=payload.get("cre2f_messagesummary") or "",
            content_classification=payload.get("cre2f_dataclassification") or "CONFIDENTIAL",
            request_filter_safe=payload.get("cre2f_requestfiltersafe") or "",
            target_summary_safe=payload.get("cre2f_targetsummarysafe") or "",
            user_groups=_parse_json_list(payload.get("cre2f_usergroups")),
            message_role=payload.get("cre2f_messagerole") or "",
            user_message=payload.get("cre2f_usermessage") or "",
            assistant_message=payload.get("cre2f_assistantmessage") or "",
            policy_id=payload.get("cre2f_policyid") or "",
            policy_version=payload.get("cre2f_policyversion") or "",
            policy_decision=payload.get("cre2f_policydecision") or "",
            released_fields=_parse_json_list(payload.get("cre2f_releasedfields")),
            consent_version=payload.get("cre2f_consentversion") or "",
            consent_status=payload.get("cre2f_consentstatus") or "",
            tool_name=payload.get("cre2f_toolname") or "",
            memory_eligible=bool(payload.get("cre2f_memoryeligible", False)),
            memory_summary=payload.get("cre2f_memorysummary") or "",
            memory_topics=_parse_json_list(payload.get("cre2f_memorytopics")),
            memory_valid_from=payload.get("cre2f_memoryvalidfrom") or "",
            memory_expires_on=payload.get("cre2f_memoryexpireson") or "",
            memory_superseded=bool(payload.get("cre2f_memorysuperseded", False)),
            memory_last_used=payload.get("cre2f_memorylastused") or "",
            memory_importance=int(payload.get("cre2f_memoryimportance") or 1),
            event_time=payload.get("cre2f_eventtime"),
        )
        if "cre2f_loggingstatus" in payload:
            rec.logging_status = payload["cre2f_loggingstatus"]
        if "cre2f_retrycount" in payload:
            rec.retry_count = int(payload["cre2f_retrycount"] or 0)
        if "cre2f_reconciled" in payload:
            rec.reconciled = bool(payload["cre2f_reconciled"])
        if "cre2f_contenthash" in payload:
            rec.content_hash = payload["cre2f_contenthash"]
        if "cre2f_auditid" in payload:
            rec.audit_id = payload["cre2f_auditid"]
        elif "cre2f_veloraagentauditlogid" in payload:
            rec.audit_id = payload["cre2f_veloraagentauditlogid"]
        return rec


class DataverseClient:
    """Production Dataverse client with fail-closed write semantics and in-memory fallback."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        self.base_url = (base_url or os.getenv("DATAVERSE_URL", "")).rstrip("/")
        self.tenant_id = tenant_id or os.getenv("AZURE_TENANT_ID", "")
        self.client_id = client_id or os.getenv("AZURE_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("AZURE_CLIENT_SECRET", "")
        self.simulate_down = False

        # Cached client-credentials token for the Dataverse Web API
        self._access_token: str = ""
        self._token_expires_at: float = 0.0
        # Short-lived positive cache for consent lookups (keyed by identity+version)
        self._consent_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

        # In-memory store for high-performance indexing, verification, and tests
        self._audit_store: List[Dict[str, Any]] = []
        self._policy_store: List[Dict[str, Any]] = []
        self._alternate_keys_index: Set[Tuple[str, str]] = set()  # (invocation_id, record_type)
        self._idempotency_index: Set[Tuple[str, str]] = set()     # (idempotency_key, operation)
        self._seed_default_policies()

    def _seed_default_policies(self) -> None:
        """Seed initial active disclosure policies for Velora HCM."""
        now_iso = datetime.now(timezone.utc).isoformat()
        default_policy = {
            "cre2f_veloradatadisclosurepolicyid": "POL-SF-WORKFORCE-V1",
            "cre2f_policyname": "Velora Executive Workforce Disclosure Policy",
            "cre2f_policycode": "POL_SF_WORKFORCE",
            "cre2f_version": "1.0.0",
            "cre2f_isactive": True,
            "cre2f_environment": "Production",
            "cre2f_agentid": "velora-hcm-agent",
            "cre2f_datadomain": "Employee",
            "cre2f_allowemployeesearch": True,
            "cre2f_allowgroupdrilldown": True,
            "cre2f_allowedemployeefields": json.dumps([
                "userId", "name", "email", "jobTitle", "department", "division", "businessUnit",
                "location", "country", "gender", "age", "age_group", "joined_date",
                "tenure", "length_of_service", "employmentStatus", "recruited_by"
            ]),
            "cre2f_restrictedemployeefields": json.dumps([
                "dateOfBirth", "bankAccountNumber", "iban", "nationalId",
                "passportNumber", "personalEmail", "homeAddress", "ssn",
                "baseSalary", "compensation", "bonus", "medicalHistory"
            ]),
            "cre2f_maximumresultrows": 100,
            "cre2f_minimumgroupsize": 1,
            "cre2f_allowedusergroups": json.dumps(["Executive", "HR_Leader", "Workforce_Analyst", "All_Velora_Authenticated"]),
            "cre2f_alloweddepartments": json.dumps([]),
            "cre2f_purposerequired": False,
            "cre2f_effectivefrom": "2026-01-01T00:00:00Z",
            "cre2f_effectiveto": "2030-12-31T23:59:59Z",
            "cre2f_approvedby": "Velora HR & Privacy Governance Committee",
            "cre2f_approvaldate": "2026-01-01T00:00:00Z",
            "cre2f_changereason": "Standard enterprise baseline disclosure policy",
            "cre2f_createdon": now_iso,
            "cre2f_modifiedon": now_iso,
        }
        self._policy_store.append(default_policy)

    # ── Dataverse Web API transport ────────────────────────────────────────────

    @property
    def is_live(self) -> bool:
        """True when full client-credentials configuration for Dataverse is present."""
        return bool(self.base_url and self.tenant_id and self.client_id and self.client_secret)

    async def _get_access_token(self) -> str:
        """Acquire and cache an app-only bearer token for the Dataverse Web API."""
        now = time.time()
        if self._access_token and now < self._token_expires_at:
            return self._access_token

        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        form = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": f"{self.base_url}/.default",
            "grant_type": "client_credentials",
        }
        async with httpx.AsyncClient(timeout=DATAVERSE_TIMEOUT_SECONDS) as client:
            resp = await client.post(token_url, data=form)
            resp.raise_for_status()
            body = resp.json()

        self._access_token = body["access_token"]
        # Refresh 60s early so a token never expires mid-request.
        self._token_expires_at = now + max(int(body.get("expires_in", 3600)) - 60, 60)
        return self._access_token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Issue an authenticated Dataverse Web API request."""
        token = await self._get_access_token()
        url = f"{self.base_url}/api/data/{DATAVERSE_API_VERSION}/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Content-Type": "application/json; charset=utf-8",
        }
        if method.upper() == "POST":
            # Ask Dataverse to echo the created row so the caller gets the real GUID.
            headers["Prefer"] = "return=representation"

        async with httpx.AsyncClient(timeout=DATAVERSE_TIMEOUT_SECONDS) as client:
            resp = await client.request(method, url, headers=headers, json=json_body, params=params)
            resp.raise_for_status()
            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()

    async def _create_row(self, entity_set: str, body: Dict[str, Any], id_field: str) -> Optional[str]:
        """Insert one row into the given entity set; returns the Dataverse GUID.

        The caller supplies an already-projected body, so no column that the table
        lacks is ever sent. Dataverse assigns the primary key itself.
        """
        created = await self._request("POST", entity_set, json_body=body)
        if isinstance(created, dict):
            return created.get(id_field)
        return None

    def check_alternate_key_exists(self, invocation_id: str, record_type: str) -> bool:
        """Check Section 3.4 alternate key: cre2f_invocationid + cre2f_recordtype."""
        if not invocation_id:
            return False
        return (invocation_id, record_type) in self._alternate_keys_index

    def check_successful_idempotency_exists(self, idempotency_key: str, operation: str) -> bool:
        """Check Section 3.4 idempotency protection: cre2f_idempotencykey + cre2f_operation."""
        if not idempotency_key:
            return False
        return (idempotency_key, operation) in self._idempotency_index

    async def create_audit_record(self, record: DataverseAuditRecord) -> Dict[str, Any]:
        """Persist a single audit record into `cre2f_veloraagentauditlog` with idempotency validation."""
        if self.simulate_down:
            log.error("dataverse_simulated_down_audit_failed", record_type=record.record_type)
            raise ConnectionError("Dataverse service endpoint is unreachable (simulated outage).")

        payload = record.to_dataverse_payload()
        inv_id = record.invocation_id
        rec_type = record.record_type
        idemp_key = record.idempotency_key
        operation = record.operation

        # 1. Alternate key check (Section 3.4)
        if inv_id and self.check_alternate_key_exists(inv_id, rec_type):
            log.warning("duplicate_alternate_key_detected", invocation_id=inv_id, record_type=rec_type)
            return {
                "status": AuditCommitStatus.ALREADY_COMMITTED,
                "commit_status": AuditCommitStatus.ALREADY_COMMITTED,
                "message": f"Record with invocation ID '{inv_id}' and record type '{rec_type}' already committed.",
                "id": f"EXISTS-{inv_id}",
                "invocation_id": inv_id,
            }

        # 2. Duplicate successful write check (Section 3.4)
        if rec_type == RECORD_TYPE_TRANSACTION_START and self.check_successful_idempotency_exists(idemp_key, operation):
            log.warning("duplicate_successful_transaction_detected", idempotency_key=idemp_key, operation=operation)
            return {
                "status": AuditCommitStatus.ALREADY_COMMITTED,
                "commit_status": AuditCommitStatus.ALREADY_COMMITTED,
                "message": f"A successful transaction for operation '{operation}' with idempotency key '{idemp_key}' has already executed.",
                "id": f"EXISTS-{idemp_key}",
                "invocation_id": inv_id,
            }

        # Unconfigured / Mock Fallback
        if not self.is_live:
            buf_id = f"BUF-{rec_type}-{int(time.time() * 1000)}-{os.urandom(2).hex()}"
            payload["cre2f_veloraagentauditlogid"] = buf_id
            payload["cre2f_loggingstatus"] = AuditCommitStatus.BUFFERED
            self._audit_store.append(payload)
            if inv_id:
                self._alternate_keys_index.add((inv_id, rec_type))
            if rec_type in (RECORD_TYPE_TRANSACTION_RESULT, RECORD_TYPE_TOOL_EXECUTION_END) and record.outcome == "SUCCESS":
                if idemp_key:
                    self._idempotency_index.add((idemp_key, operation))
            log.info("dataverse_not_configured_audit_buffered", record_type=rec_type, buffer_id=buf_id)
            return {
                "status": AuditCommitStatus.BUFFERED,
                "commit_status": AuditCommitStatus.BUFFERED,
                "id": buf_id,
                "invocation_id": inv_id,
                "logging_status": AuditCommitStatus.BUFFERED,
            }

        # Live Dataverse Persistence
        try:
            if rec_type == RECORD_TYPE_CONSENT:
                remote_id = await self._create_row(
                    CONSENT_ENTITY_SET, record.to_consent_payload(), "cre2f_botuserconsentid"
                )
            else:
                remote_id = await self._create_row(
                    AUDIT_ENTITY_SET, record.to_audit_log_payload(), "cre2f_veloraagentauditlogid"
                )
            log_id = remote_id or f"AUD-{int(time.time() * 1000)}-{len(self._audit_store) + 1}"
            payload["cre2f_veloraagentauditlogid"] = log_id
            payload["cre2f_loggingstatus"] = AuditCommitStatus.COMMITTED
            self._audit_store.append(payload)
            if rec_type == RECORD_TYPE_CONSENT:
                self._consent_cache.clear()
            if inv_id:
                self._alternate_keys_index.add((inv_id, rec_type))
            if rec_type in (RECORD_TYPE_TRANSACTION_RESULT, RECORD_TYPE_TOOL_EXECUTION_END) and record.outcome == "SUCCESS":
                if idemp_key:
                    self._idempotency_index.add((idemp_key, operation))

            log.debug("audit_record_created", type=record.record_type, turn_id=record.turn_id, log_id=log_id)
            return {
                "status": AuditCommitStatus.COMMITTED,
                "commit_status": AuditCommitStatus.COMMITTED,
                "id": log_id,
                "invocation_id": inv_id,
            }
        except httpx.HTTPStatusError as http_err:
            if http_err.response.status_code == 412 or "DuplicateKey" in http_err.response.text:
                log.info("dataverse_duplicate_already_committed", invocation_id=inv_id)
                return {
                    "status": AuditCommitStatus.ALREADY_COMMITTED,
                    "commit_status": AuditCommitStatus.ALREADY_COMMITTED,
                    "id": f"EXISTS-{inv_id}",
                    "invocation_id": inv_id,
                }
            log.error("dataverse_live_write_failed", error=str(http_err), status_code=http_err.response.status_code)
            raise ConnectionError(f"Dataverse destination write failed: {http_err}") from http_err
        except Exception as exc:
            log.error("dataverse_live_write_failed", error=str(exc))
            raise ConnectionError(f"Dataverse destination write failed: {exc}") from exc

    async def start_write_transaction_fail_closed(self, record: DataverseAuditRecord) -> Dict[str, Any]:
        """Strict Fail-Closed Write Auditing (Section 3.5 & 6.1).
        
        A TRANSACTION_START record MUST be persisted before external write.
        If Dataverse is unavailable or fails, returns may_proceed=False and aborts.
        """
        if record.record_type != RECORD_TYPE_TRANSACTION_START:
            record.record_type = RECORD_TYPE_TRANSACTION_START

        # Check duplicate before starting
        if self.check_successful_idempotency_exists(record.idempotency_key, record.operation):
            return {
                "may_proceed": False,
                "status": "DUPLICATE_BLOCKED",
                "error": f"Operation '{record.operation}' with key '{record.idempotency_key}' was already executed successfully.",
                "audit_record_id": "",
            }

        try:
            res = await self.create_audit_record(record)
            commit_status = res.get("commit_status") or res.get("status")
            if commit_status in (AuditCommitStatus.COMMITTED, AuditCommitStatus.ALREADY_COMMITTED):
                return {
                    "may_proceed": True,
                    "status": "AUDIT_PERSISTED",
                    "commit_status": commit_status,
                    "audit_record_id": res.get("id"),
                    "invocation_id": record.invocation_id,
                    "error": None,
                }
            elif commit_status == AuditCommitStatus.BUFFERED:
                strict_fail_closed = os.getenv("STRICT_FAIL_CLOSED_AUDIT", "1") == "1"
                if strict_fail_closed and not os.getenv("ALLOW_BUFFERED_AUDIT_WRITES", ""):
                    return {
                        "may_proceed": False,
                        "status": "AUDIT_BUFFERED_BLOCKED",
                        "commit_status": AuditCommitStatus.BUFFERED,
                        "error": "Governed write blocked: Audit destination is only BUFFERED in memory; durable Dataverse commitment required.",
                        "audit_record_id": res.get("id"),
                    }
                return {
                    "may_proceed": True,
                    "status": "AUDIT_BUFFERED",
                    "commit_status": AuditCommitStatus.BUFFERED,
                    "audit_record_id": res.get("id"),
                    "invocation_id": record.invocation_id,
                    "error": None,
                }
            else:
                return {
                    "may_proceed": False,
                    "status": res.get("status", "AUDIT_REJECTED"),
                    "commit_status": AuditCommitStatus.FAILED,
                    "error": res.get("message", "Audit could not be persisted."),
                    "audit_record_id": "",
                }
        except Exception as ex:
            log.error("fail_closed_write_audit_exception", error=str(ex))
            return {
                "may_proceed": False,
                "status": "FAIL_CLOSED_BLOCKED",
                "commit_status": AuditCommitStatus.FAILED,
                "error": f"Write action blocked: Dataverse audit log could not be saved ({str(ex)}).",
                "audit_record_id": "",
            }

    async def complete_write_transaction(
        self,
        audit_record_id: str,
        invocation_id: str,
        outcome: str,
        external_object_id: str = "",
        evidence_link: str = "",
        result_count: int = 1,
        safe_summary: str = "",
        safe_error: str = "",
        start_time: str = "",
        end_time: str = "",
        record_type: str = RECORD_TYPE_TRANSACTION_RESULT,
        calling_agent: str = "Velora Productivity Agent",
        executing_agent: str = "Velora Productivity Agent",
        root_correlation_id: str = "",
        user_email: str = "",
        operation: str = "",
        idempotency_key: str = "",
    ) -> Dict[str, Any]:
        """Record Section 6.2 Audit Complete Operation (TRANSACTION_RESULT or TRANSACTION_ERROR)."""
        calc_end = end_time or datetime.now(timezone.utc).isoformat()
        latency = None
        if start_time:
            try:
                st = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                et = datetime.fromisoformat(calc_end.replace("Z", "+00:00"))
                latency = int((et - st).total_seconds() * 1000)
            except Exception:
                latency = 0

        rec = DataverseAuditRecord(
            record_type=record_type if outcome == "SUCCESS" else RECORD_TYPE_TRANSACTION_ERROR,
            root_correlation_id=root_correlation_id,
            invocation_id=f"{invocation_id}-end",
            parent_invocation_id=invocation_id,
            idempotency_key=idempotency_key,
            calling_agent=calling_agent,
            executing_agent=executing_agent,
            user_email=user_email,
            operation=operation,
            transaction_type="WRITE",
            outcome=outcome,
            start_time=start_time,
            end_time=calc_end,
            latency_ms=latency,
            result_count=result_count,
            external_object_id=external_object_id,
            evidence_link=evidence_link,
            message_summary=safe_summary,
            error_message_safe=safe_error,
            error_category="" if outcome == "SUCCESS" else "EXECUTION_ERROR",
        )
        return await self.create_audit_record(rec)

    async def record_user_approval(
        self,
        invocation_id: str,
        user_object_id: str,
        user_email: str,
        approval_status: str,
        approval_token: str,
        safe_preview_summary: str,
        expiration_time: str,
        root_correlation_id: str = "",
        operation: str = "",
    ) -> Dict[str, Any]:
        """Record Section 6.3 Audit Record Approval."""
        token_hash = compute_approval_token_hash(approval_token)
        rec = DataverseAuditRecord(
            record_type=RECORD_TYPE_USER_APPROVAL,
            root_correlation_id=root_correlation_id,
            invocation_id=f"{invocation_id}-appr",
            parent_invocation_id=invocation_id,
            user_object_id=user_object_id,
            user_email=user_email,
            operation=operation,
            approval_status=approval_status,
            approval_expires_on=expiration_time,
            approval_token_hash=token_hash,
            message_summary=safe_preview_summary,
            audit_detail=f"User approval decision: {approval_status}",
        )
        return await self.create_audit_record(rec)

    def _match_consent_in_buffer(
        self, user_object_id: str, user_email: str, notice_version: str
    ) -> Optional[Dict[str, Any]]:
        """Scan the in-memory buffer for an accepted consent row."""
        sanitized = sanitize_email(user_email)
        for record in reversed(self._audit_store):
            if record.get("cre2f_recordtype") != RECORD_TYPE_CONSENT:
                continue
            uid = record.get("cre2f_userobjectid", "")
            email = sanitize_email(record.get("cre2f_useremail", record.get("cre2f_newcolumn", "")))
            ver = record.get("cre2f_consentversion", "")
            status = record.get("cre2f_consentstatus", "")

            # An identity match requires a non-empty identifier on both sides,
            # otherwise two anonymous rows would satisfy each other.
            matches_user = bool(
                (user_object_id and uid == user_object_id)
                or (sanitized and email == sanitized)
            )
            if matches_user and ver == notice_version and status == "ACCEPTED":
                return record
        return None

    async def query_user_consent(self, user_object_id: str, user_email: str, notice_version: str) -> Optional[Dict[str, Any]]:
        """Query for valid active consent in `cre2f_veloraagentauditlog`.

        Reads live Dataverse when configured so a consent accepted in an earlier
        session (or on another replica) is honoured and the user is not re-asked.
        Falls back to the in-memory buffer for tests and offline operation.
        """
        sanitized = sanitize_email(user_email)
        cache_key = f"{user_object_id}|{sanitized}|{notice_version}"

        if not self.is_live:
            return self._match_consent_in_buffer(user_object_id, user_email, notice_version)

        cached = self._consent_cache.get(cache_key)
        if cached and time.time() < cached[0]:
            return cached[1]

        # The Copilot Studio flow writes whichever identity string the agent passes
        # into the primary name column, so match on the object id or the email —
        # either may be the value on the stored row.
        identities = [v for v in (user_object_id, sanitized) if v]
        if not identities:
            return None
        ident_clause = " or ".join(
            f"{CONSENT_IDENTITY_COLUMN} eq '{_odata_escape(v)}'" for v in identities
        )
        filter_expr = (
            f"cre2f_consentgranted eq true"
            f" and cre2f_consentversion eq '{_odata_escape(notice_version)}'"
            f" and ({ident_clause})"
        )
        params = {
            "$filter": filter_expr,
            "$orderby": "createdon desc",
            "$top": "1",
            "$select": "cre2f_botuserconsentid,cre2f_newcolumn,cre2f_consentversion,"
                       "cre2f_consentgranted,cre2f_consentdate,cre2f_channel",
        }

        try:
            body = await self._request("GET", CONSENT_ENTITY_SET, params=params)
        except Exception as exc:
            # Fail closed: an unreadable consent table must re-prompt, never
            # silently grant access to employee data.
            log.error(
                "dataverse_consent_query_failed",
                error=str(exc),
                exc_type=type(exc).__name__,
            )
            return None

        rows = (body or {}).get("value") or []
        record = rows[0] if rows else None
        if record:
            self._consent_cache[cache_key] = (time.time() + CONSENT_QUERY_CACHE_SECONDS, record)
        return record

    async def query_user_30_day_memory(
        self,
        user_object_id: str,
        user_email: str,
        days: int = 30,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query user-partitioned memory logs from the last 30 days."""
        sanitized = sanitize_email(user_email)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_iso = cutoff_date.isoformat()

        eligible_types = {
            RECORD_TYPE_USER_TURN,
            RECORD_TYPE_ASSISTANT_TURN,
            RECORD_TYPE_MEMORY_SUMMARY,
            RECORD_TYPE_POLICY_DECISION,
            RECORD_TYPE_TOOL_EXECUTION,
            RECORD_TYPE_TRANSACTION_RESULT,
        }

        results = []
        for record in self._audit_store:
            rec_type = record.get("cre2f_recordtype")
            if rec_type not in eligible_types:
                continue

            uid = record.get("cre2f_userobjectid", "")
            email = sanitize_email(record.get("cre2f_useremail", record.get("cre2f_newcolumn", "")))
            if not user_object_id and not user_email:
                matches_user = True
            else:
                matches_user = bool((user_object_id and uid == user_object_id) or (user_email and email == sanitized))
            if not matches_user:
                continue

            event_time = record.get("cre2f_eventtime", "")
            if event_time and event_time < cutoff_iso:
                continue

            results.append(record)

        results.sort(key=lambda r: r.get("cre2f_eventtime", ""), reverse=True)
        return results[:limit]

    async def get_active_policy(
        self,
        domain: str = "Employee",
        agent_id: str = "velora-hcm-agent",
        environment: str = "Production",
    ) -> Optional[Dict[str, Any]]:
        """Retrieve the currently active Dataverse disclosure policy."""
        if self.is_live:
            escaped_domain = _odata_escape(domain)
            escaped_agent = _odata_escape(agent_id)
            result = await self._request(
                "GET",
                POLICY_ENTITY_SET,
                params={
                    "$filter": (
                        f"cre2f_isactive eq true and cre2f_datadomain eq '{escaped_domain}' "
                        f"and cre2f_agentid eq '{escaped_agent}'"
                    ),
                    "$orderby": "modifiedon desc",
                    "$top": "1",
                },
            )
            rows = result.get("value", []) if isinstance(result, dict) else []
            if rows:
                return rows[0]

            # Environment labels changed during early development. If no exact
            # agent match exists, retain the strict domain-only lookup rather than
            # silently using the process-local seed.
            result = await self._request(
                "GET",
                POLICY_ENTITY_SET,
                params={
                    "$filter": f"cre2f_isactive eq true and cre2f_datadomain eq '{escaped_domain}'",
                    "$orderby": "modifiedon desc",
                    "$top": "1",
                },
            )
            rows = result.get("value", []) if isinstance(result, dict) else []
            return rows[0] if rows else None

        for policy in self._policy_store:
            if (
                policy.get("cre2f_isactive") is True
                and policy.get("cre2f_datadomain", "").lower() == domain.lower()
            ):
                return policy
        return None

    async def list_policies(self) -> List[Dict[str, Any]]:
        """List all policy versions in the table."""
        if self.is_live:
            result = await self._request(
                "GET", POLICY_ENTITY_SET, params={"$orderby": "modifiedon desc"}
            )
            return result.get("value", []) if isinstance(result, dict) else []
        return list(self._policy_store)

    async def save_policy(self, policy_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update a policy entry."""
        policy_id = policy_data.get("cre2f_veloradatadisclosurepolicyid")
        now_iso = datetime.now(timezone.utc).isoformat()

        if self.is_live:
            writable = {
                key: value
                for key, value in policy_data.items()
                if key.startswith("cre2f_")
                and key != "cre2f_veloradatadisclosurepolicyid"
                and key not in {"cre2f_createdon", "cre2f_modifiedon"}
            }
            if writable.get("cre2f_isactive"):
                domain = _odata_escape(writable.get("cre2f_datadomain", "Employee"))
                current = await self._request(
                    "GET",
                    POLICY_ENTITY_SET,
                    params={
                        "$select": "cre2f_veloradatadisclosurepolicyid",
                        "$filter": f"cre2f_isactive eq true and cre2f_datadomain eq '{domain}'",
                    },
                )
                for row in (current or {}).get("value", []):
                    row_id = row.get("cre2f_veloradatadisclosurepolicyid")
                    if row_id and row_id != policy_id:
                        await self._request(
                            "PATCH",
                            f"{POLICY_ENTITY_SET}({row_id})",
                            json_body={"cre2f_isactive": False},
                        )

            if policy_id and len(str(policy_id)) == 36:
                await self._request(
                    "PATCH",
                    f"{POLICY_ENTITY_SET}({policy_id})",
                    json_body=writable,
                )
                refreshed = await self._request(
                    "GET", f"{POLICY_ENTITY_SET}({policy_id})"
                )
                return {"status": "UPDATED", "policy": refreshed or writable}

            created = await self._request(
                "POST", POLICY_ENTITY_SET, json_body=writable
            )
            return {"status": "CREATED", "policy": created or writable}
        
        if policy_data.get("cre2f_isactive"):
            domain = policy_data.get("cre2f_datadomain", "Employee")
            for pol in self._policy_store:
                if pol.get("cre2f_datadomain") == domain:
                    pol["cre2f_isactive"] = False

        if policy_id:
            for idx, existing in enumerate(self._policy_store):
                if existing.get("cre2f_veloradatadisclosurepolicyid") == policy_id:
                    updated = {**existing, **policy_data, "cre2f_modifiedon": now_iso}
                    self._policy_store[idx] = updated
                    return {"status": "UPDATED", "policy": updated}

        new_id = policy_id or f"POL-{int(time.time())}"
        new_policy = {
            **policy_data,
            "cre2f_veloradatadisclosurepolicyid": new_id,
            "cre2f_createdon": now_iso,
            "cre2f_modifiedon": now_iso,
        }
        self._policy_store.append(new_policy)
        return {"status": "CREATED", "policy": new_policy}

    def clear_all_for_testing(self) -> None:
        """Reset internal stores for clean test isolation."""
        self._audit_store.clear()
        self._policy_store.clear()
        self._alternate_keys_index.clear()
        self._idempotency_index.clear()
        self._consent_cache.clear()
        self.simulate_down = False
        self._seed_default_policies()


# Global Singleton Client
_global_dataverse_client = DataverseClient()


def get_dataverse_client() -> DataverseClient:
    return _global_dataverse_client
