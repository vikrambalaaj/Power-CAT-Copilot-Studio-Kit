"""Dataverse Audit & Disclosure Policy Data Access Layer.

Extends the single existing table `cre2f_veloraagentauditlog` with the `cre2f_recordtype`
discriminator, full telemetry, identity, and memory fields.
Manages `cre2f_veloradatadisclosurepolicy` for dynamic enterprise governance.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from shared_mcp.logger import get_logger

log = get_logger("dataverse_audit")

# Record Type Discriminator Constants
RECORD_TYPE_CONVERSATION_START = "CONVERSATION_START"
RECORD_TYPE_USER_TURN = "USER_TURN"
RECORD_TYPE_ASSISTANT_TURN = "ASSISTANT_TURN"
RECORD_TYPE_TOOL_EXECUTION = "TOOL_EXECUTION"
RECORD_TYPE_POLICY_DECISION = "POLICY_DECISION"
RECORD_TYPE_CONSENT = "CONSENT"
RECORD_TYPE_MEMORY_SUMMARY = "MEMORY_SUMMARY"
RECORD_TYPE_CONVERSATION_END = "CONVERSATION_END"
RECORD_TYPE_LOGGING_ERROR = "LOGGING_ERROR"

VALID_RECORD_TYPES = {
    RECORD_TYPE_CONVERSATION_START,
    RECORD_TYPE_USER_TURN,
    RECORD_TYPE_ASSISTANT_TURN,
    RECORD_TYPE_TOOL_EXECUTION,
    RECORD_TYPE_POLICY_DECISION,
    RECORD_TYPE_CONSENT,
    RECORD_TYPE_MEMORY_SUMMARY,
    RECORD_TYPE_CONVERSATION_END,
    RECORD_TYPE_LOGGING_ERROR,
}


def sanitize_email(email: Optional[str]) -> str:
    """Normalize email for consistent identity indexing and partitioning."""
    return (email or "").strip().lower()


def compute_content_hash(text: str) -> str:
    """Compute deterministic SHA-256 hash for transcript reconciliation and deduplication."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


class DataverseAuditRecord:
    """Strongly-typed wrapper for the extended `cre2f_veloraagentauditlog` schema."""

    def __init__(
        self,
        record_type: str,
        user_object_id: str,
        user_email: str,
        conversation_id: str = "",
        session_id: str = "",
        turn_id: str = "",
        parent_turn_id: str = "",
        turn_sequence: int = 0,
        correlation_id: str = "",
        user_display_name: str = "",
        user_groups: Optional[List[str]] = None,
        channel: str = "copilot_studio",
        message_role: str = "",
        user_message: str = "",
        assistant_message: str = "",
        message_summary: str = "",
        content_classification: str = "CONFIDENTIAL",
        policy_id: str = "",
        policy_version: str = "",
        policy_decision: str = "",
        released_fields: Optional[List[str]] = None,
        consent_version: str = "",
        consent_status: str = "",
        tool_name: str = "",
        tool_start_time: str = "",
        tool_end_time: str = "",
        latency_ms: Optional[int] = None,
        error_category: str = "",
        error_message_safe: str = "",
        source_system: str = "SuccessFactors",
        source_as_of: str = "",
        cache_hit: Optional[bool] = None,
        cache_age: Optional[float] = None,
        request_filter_safe: str = "",
        result_count: int = 0,
        memory_eligible: bool = False,
        memory_summary: str = "",
        memory_topics: Optional[List[str]] = None,
        memory_valid_from: str = "",
        memory_expires_on: str = "",
        memory_superseded: bool = False,
        memory_last_used: str = "",
        memory_importance: int = 1,
        agent_name: str = "Velora HCM Agent",
        agent_version: str = "1.0.0",
        environment: str = "Velora-AgenticAD-Dev",
        event_time: Optional[str] = None,
    ):
        if record_type not in VALID_RECORD_TYPES:
            raise ValueError(f"Invalid record_type: {record_type}. Must be one of {VALID_RECORD_TYPES}")

        self.record_type = record_type
        self.user_object_id = user_object_id or ""
        self.user_email = sanitize_email(user_email)
        self.conversation_id = conversation_id
        self.session_id = session_id
        self.turn_id = turn_id or f"turn-{int(time.time() * 1000)}"
        self.parent_turn_id = parent_turn_id
        self.turn_sequence = turn_sequence
        self.correlation_id = correlation_id
        self.user_display_name = user_display_name
        self.user_groups = user_groups or []
        self.channel = channel
        self.message_role = message_role
        self.user_message = user_message
        self.assistant_message = assistant_message
        self.message_summary = message_summary
        self.content_classification = content_classification
        self.content_hash = compute_content_hash(user_message + assistant_message)
        self.policy_id = policy_id
        self.policy_version = policy_version
        self.policy_decision = policy_decision
        self.released_fields = released_fields or []
        self.consent_version = consent_version
        self.consent_status = consent_status
        self.tool_name = tool_name
        self.tool_start_time = tool_start_time
        self.tool_end_time = tool_end_time
        self.latency_ms = latency_ms
        self.error_category = error_category
        self.error_message_safe = error_message_safe
        self.source_system = source_system
        self.source_as_of = source_as_of
        self.cache_hit = cache_hit
        self.cache_age = cache_age
        self.request_filter_safe = request_filter_safe
        self.result_count = result_count
        self.memory_eligible = memory_eligible
        self.memory_summary = memory_summary
        self.memory_topics = memory_topics or []
        self.memory_valid_from = memory_valid_from
        self.memory_expires_on = memory_expires_on
        self.memory_superseded = memory_superseded
        self.memory_last_used = memory_last_used
        self.memory_importance = memory_importance
        self.agent_name = agent_name
        self.agent_version = agent_version
        self.environment = environment
        self.event_time = event_time or datetime.now(timezone.utc).isoformat()
        self.logging_status = "PENDING"
        self.retry_count = 0
        self.reconciled = False

    def to_dataverse_payload(self) -> Dict[str, Any]:
        """Convert record into exact Dataverse payload matching logical column names."""
        audit_detail = self.message_summary or self.error_message_safe or f"{self.record_type}: {self.tool_name or self.message_role}"
        return {
            # Legacy columns preserved for full backward compatibility
            "cre2f_agentname": self.agent_name,
            "cre2f_auditdetail": audit_detail[:4000],
            "cre2f_dataclassification": self.content_classification,
            "cre2f_demodata": False,
            "cre2f_environment": self.environment,
            "cre2f_eventtime": self.event_time,
            "cre2f_newcolumn": self.user_email,  # Retained backward-compatible email slot
            "cre2f_operation": self.record_type,
            "cre2f_outcome": "ERROR" if self.error_category else "SUCCESS",
            "cre2f_resultcount": self.result_count,
            "cre2f_sourcesystem": self.source_system,
            "cre2f_toolname": self.tool_name,

            # Record-type discriminator
            "cre2f_recordtype": self.record_type,

            # Conversation identity
            "cre2f_conversationid": self.conversation_id,
            "cre2f_sessionid": self.session_id,
            "cre2f_turnid": self.turn_id,
            "cre2f_parentturnid": self.parent_turn_id,
            "cre2f_turnsequence": self.turn_sequence,
            "cre2f_correlationid": self.correlation_id,

            # User identity
            "cre2f_userobjectid": self.user_object_id,
            "cre2f_useremail": self.user_email,
            "cre2f_userdisplayname": self.user_display_name,
            "cre2f_usergroups": json.dumps(self.user_groups),
            "cre2f_channel": self.channel,

            # Content & message payload (safely bounded)
            "cre2f_messagerole": self.message_role,
            "cre2f_usermessage": (self.user_message or "")[:4000],
            "cre2f_assistantmessage": (self.assistant_message or "")[:4000],
            "cre2f_messagesummary": (self.message_summary or "")[:2000],
            "cre2f_contentclassification": self.content_classification,
            "cre2f_contenthash": self.content_hash,

            # Policy & Consent
            "cre2f_policyid": self.policy_id,
            "cre2f_policyversion": self.policy_version,
            "cre2f_policydecision": self.policy_decision,
            "cre2f_releasedfields": json.dumps(self.released_fields),
            "cre2f_consentversion": self.consent_version,
            "cre2f_consentstatus": self.consent_status,

            # Tool Execution & Telemetry
            "cre2f_toolstarttime": self.tool_start_time,
            "cre2f_toolendtime": self.tool_end_time,
            "cre2f_latencymilliseconds": self.latency_ms,
            "cre2f_errorcategory": self.error_category,
            "cre2f_errormessagesafe": (self.error_message_safe or "")[:2000],
            "cre2f_sourceasof": self.source_as_of,
            "cre2f_cachehit": self.cache_hit,
            "cre2f_cacheage": self.cache_age,
            "cre2f_requestfiltersafe": (self.request_filter_safe or "")[:2000],

            # Memory Fields
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
            "cre2f_agentversion": self.agent_version,
        }


class DataverseClient:
    """Production Dataverse client with in-memory resilient storage for local/hybrid operation."""

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
        
        # Local mock/in-memory store for high-performance and test environments
        self._audit_store: List[Dict[str, Any]] = []
        self._policy_store: List[Dict[str, Any]] = []
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
                "userId", "name", "country", "age_group", "joined_date",
                "length_of_service", "department", "businessUnit", "division",
                "jobTitle", "location", "employmentStatus", "recruited_by"
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

    async def create_audit_record(self, record: DataverseAuditRecord) -> Dict[str, Any]:
        """Persist a single audit record into `cre2f_veloraagentauditlog`."""
        payload = record.to_dataverse_payload()
        payload["cre2f_veloraagentauditlogid"] = f"AUD-{int(time.time() * 1000)}-{len(self._audit_store) + 1}"
        payload["cre2f_loggingstatus"] = "PERSISTED"
        self._audit_store.append(payload)
        log.debug("audit_record_created", type=record.record_type, turn_id=record.turn_id)
        return {"status": "SUCCESS", "id": payload["cre2f_veloraagentauditlogid"]}

    async def query_user_consent(self, user_object_id: str, user_email: str, notice_version: str) -> Optional[Dict[str, Any]]:
        """Query for valid active consent in `cre2f_veloraagentauditlog`."""
        sanitized = sanitize_email(user_email)
        for record in reversed(self._audit_store):
            if record.get("cre2f_recordtype") == RECORD_TYPE_CONSENT:
                uid = record.get("cre2f_userobjectid", "")
                email = sanitize_email(record.get("cre2f_useremail", record.get("cre2f_newcolumn", "")))
                ver = record.get("cre2f_consentversion", "")
                status = record.get("cre2f_consentstatus", "")
                
                matches_user = (user_object_id and uid == user_object_id) or (email == sanitized)
                if matches_user and ver == notice_version and status == "ACCEPTED":
                    return record
        return None

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

        # Sort descending by event time
        results.sort(key=lambda r: r.get("cre2f_eventtime", ""), reverse=True)
        return results[:limit]

    async def get_active_policy(
        self,
        domain: str = "Employee",
        agent_id: str = "velora-hcm-agent",
        environment: str = "Production",
    ) -> Optional[Dict[str, Any]]:
        """Retrieve the currently active Dataverse disclosure policy."""
        for policy in self._policy_store:
            if (
                policy.get("cre2f_isactive") is True
                and policy.get("cre2f_datadomain", "").lower() == domain.lower()
            ):
                return policy
        return None

    async def list_policies(self) -> List[Dict[str, Any]]:
        """List all policy versions in the table."""
        return list(self._policy_store)

    async def save_policy(self, policy_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update a policy entry."""
        policy_id = policy_data.get("cre2f_veloradatadisclosurepolicyid")
        now_iso = datetime.now(timezone.utc).isoformat()
        
        if policy_data.get("cre2f_isactive"):
            # Deactivate previous active policies for same domain
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

        # Create new
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
        self._seed_default_policies()


# Global Singleton Client
_global_dataverse_client = DataverseClient()


def get_dataverse_client() -> DataverseClient:
    return _global_dataverse_client
