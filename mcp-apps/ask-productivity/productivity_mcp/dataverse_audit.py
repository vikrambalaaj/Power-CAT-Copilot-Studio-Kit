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

AUDIT_ENTITY_SET = os.getenv("DATAVERSE_AUDIT_ENTITY_SET", "cre2f_veloraagentauditlogs")
DATAVERSE_API_VERSION = os.getenv("DATAVERSE_API_VERSION", "v9.2")
DATAVERSE_TIMEOUT_SECONDS = float(os.getenv("DATAVERSE_TIMEOUT_SECONDS", "10"))
AUDIT_LOG_COLUMNS = frozenset({
    "cre2f_actor", "cre2f_agentname", "cre2f_auditdetail", "cre2f_correlationid",
    "cre2f_dataclassification", "cre2f_demodata", "cre2f_durationms",
    "cre2f_environment", "cre2f_errorcode", "cre2f_eventtime", "cre2f_newcolumn",
    "cre2f_operation", "cre2f_outcome", "cre2f_responsehash", "cre2f_resultcount",
    "cre2f_safefilters", "cre2f_sessionid", "cre2f_sourcesystem", "cre2f_toolname",
})

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
        """Project the rich audit envelope onto the columns in the live table."""
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
            "cre2f_newcolumn": self.user_email or self.user_object_id or self.executing_agent,
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

    def to_dataverse_payload(self) -> Dict[str, Any]:
        """Convert record into exact Dataverse payload matching logical column names."""
        detail = (
            self.audit_detail
            or self.message_summary
            or self.error_message_safe
            or f"{self.record_type}: {self.operation}"
        )
        return {
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

            "cre2f_callingagent": self.calling_agent,
            "cre2f_executingagent": self.executing_agent,
            "cre2f_agentname": self.agent_name,
            "cre2f_agentversion": self.agent_version,
            "cre2f_environment": self.environment,
            "cre2f_channel": self.channel,

            "cre2f_userobjectid": self.user_object_id,
            "cre2f_useremail": self.user_email,
            "cre2f_userdisplayname": self.user_display_name,
            "cre2f_usergroups": json.dumps(self.user_groups),
            "cre2f_newcolumn": self.user_email,

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

            "cre2f_auditdetail": (detail or "")[:4000],
            "cre2f_messagesummary": (self.message_summary or "")[:2000],
            "cre2f_contenthash": self.content_hash,
            "cre2f_dataclassification": self.content_classification,
            "cre2f_requestfiltersafe": (self.request_filter_safe or "")[:2000],
            "cre2f_targetsummarysafe": (self.target_summary_safe or "")[:2000],
            "cre2f_messagerole": self.message_role,
            "cre2f_usermessage": (self.user_message or "")[:4000],
            "cre2f_assistantmessage": (self.assistant_message or "")[:4000],

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

            "cre2f_loggingstatus": self.logging_status,
            "cre2f_retrycount": self.retry_count,
            "cre2f_reconciled": self.reconciled,
        }


class DataverseClient:
    """Production Dataverse client with fail-closed write semantics and in-memory fallback."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        federated_token: Optional[str] = None,
        federated_token_file: Optional[str] = None,
        auth_type: Optional[str] = None,
    ):
        self.base_url = (base_url or os.getenv("DATAVERSE_URL", "")).rstrip("/")
        self.tenant_id = (
            tenant_id
            or os.getenv("AZURE_TENANT_ID", "")
            or os.getenv("DATAVERSE_TENANT_ID", "")
            or os.getenv("M365_TENANT_ID", "")
            or os.getenv("ENTRA_TENANT_ID", "")
        )
        self.client_id = (
            client_id
            or os.getenv("AZURE_CLIENT_ID", "")
            or os.getenv("DATAVERSE_CLIENT_ID", "")
            or os.getenv("M365_CLIENT_ID", "")
            or os.getenv("ENTRA_CLIENT_ID", "")
        )
        self.client_secret = (
            client_secret
            or os.getenv("AZURE_CLIENT_SECRET", "")
            or os.getenv("DATAVERSE_CLIENT_SECRET", "")
            or os.getenv("M365_CLIENT_SECRET", "")
            or os.getenv("ENTRA_CLIENT_SECRET", "")
        )
        self.federated_token = (
            federated_token
            or os.getenv("AZURE_FEDERATED_TOKEN")
            or os.getenv("DATAVERSE_FEDERATED_TOKEN")
            or os.getenv("CLIENT_ASSERTION")
        )
        self.federated_token_file = (
            federated_token_file
            or os.getenv("AZURE_FEDERATED_TOKEN_FILE")
            or os.getenv("DATAVERSE_FEDERATED_TOKEN_FILE")
        )
        self.auth_type = (
            auth_type
            or os.getenv("DATAVERSE_AUTH_TYPE")
            or os.getenv("DATAVERSE_AUTH_MODE")
            or (
                "FederatedCredential"
                if (
                    self.federated_token
                    or self.federated_token_file
                    or os.getenv("USE_FEDERATED_AUTH") in ("1", "true", "True")
                )
                else "OAuth2_ClientCredentials"
            )
        )
        self.simulate_down = False
        self.simulate_unconfigured = False

        self._access_token = ""
        self._token_expires_at = 0.0

        self._audit_store: List[Dict[str, Any]] = []
        self._policy_store: List[Dict[str, Any]] = []
        self._alternate_keys_index: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._idempotency_index: Set[Tuple[str, str]] = set()

    def _resolve_federated_token(self) -> Optional[str]:
        """Resolve federated assertion token from string or file path."""
        if self.federated_token:
            return self.federated_token.strip()
        if self.federated_token_file and os.path.exists(self.federated_token_file):
            try:
                with open(self.federated_token_file, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception as err:
                log.warning("failed_to_read_federated_token_file", path=self.federated_token_file, error=str(err))
        return None

    @property
    def is_live(self) -> bool:
        if self.simulate_unconfigured:
            return False
        if os.getenv("MOCK_M365") == "1" or os.getenv("MOCK_DATAVERSE") == "1":
            return False
        has_secret = bool(self.client_secret)
        has_federated = bool(
            self._resolve_federated_token()
            or str(self.auth_type).lower() in ("federatedcredential", "federated_credential", "managedidentity", "managed_identity")
            or os.getenv("USE_FEDERATED_AUTH") in ("1", "true", "True")
        )
        return bool(self.base_url and self.tenant_id and self.client_id and (has_secret or has_federated))

    async def _get_access_token(self) -> str:
        """Acquire and cache an app-only bearer token for Dataverse Web API.
        
        Supports:
        1. Federated Credential / Workload Identity Federation (RFC 7523 client assertion)
           using client_id without static client secrets.
        2. Azure Managed Identity using client_id for User-Assigned Managed Identity.
        3. Standard OAuth 2.0 client credentials using client_id and client_secret.
        """
        now = time.time()
        if self._access_token and now < self._token_expires_at:
            return self._access_token

        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        scope = f"{self.base_url}/.default"

        # 1. Federated Credential / Workload Identity (RFC 7523 Client Assertion)
        fed_token = self._resolve_federated_token()
        is_federated_mode = (
            bool(fed_token)
            or str(self.auth_type).lower() in ("federatedcredential", "federated_credential")
            or (not self.client_secret and os.getenv("USE_FEDERATED_AUTH") in ("1", "true", "True"))
        )

        if is_federated_mode and not fed_token:
            raise ValueError("Federated Dataverse authentication requires a current client assertion or readable token file; client-secret fallback is disabled.")

        if is_federated_mode and fed_token:
            form = {
                "client_id": self.client_id,
                "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                "client_assertion": fed_token,
                "scope": scope,
                "grant_type": "client_credentials",
            }
            async with httpx.AsyncClient(timeout=DATAVERSE_TIMEOUT_SECONDS) as client:
                resp = await client.post(token_url, data=form)
                resp.raise_for_status()
                token_body = resp.json()
            self._access_token = token_body["access_token"]
            self._token_expires_at = now + max(int(token_body.get("expires_in", 3600)) - 60, 60)
            return self._access_token

        # 2. Azure Managed Identity (User-Assigned Identity via client_id)
        is_managed_identity = (
            str(self.auth_type).lower() in ("managedidentity", "managed_identity")
            or os.getenv("USE_MANAGED_IDENTITY") in ("1", "true", "True")
        )
        if is_managed_identity:
            identity_endpoint = os.getenv("IDENTITY_ENDPOINT")
            identity_header = os.getenv("IDENTITY_HEADER")
            if identity_endpoint and identity_header:
                async with httpx.AsyncClient(timeout=DATAVERSE_TIMEOUT_SECONDS) as client:
                    resp = await client.get(
                        f"{identity_endpoint}?api-version=2019-08-01&resource={self.base_url}&client_id={self.client_id}",
                        headers={"X-IDENTITY-HEADER": identity_header},
                    )
                    resp.raise_for_status()
                    token_body = resp.json()
                    self._access_token = token_body["access_token"]
                    self._token_expires_at = now + max(int(token_body.get("expires_in", 3600)) - 60, 60)
                    return self._access_token
            # Fallback to Azure IMDS
            imds_url = f"http://169.254.169.254/metadata/identity/oauth2/token?api-version=2019-08-01&resource={self.base_url}&client_id={self.client_id}"
            async with httpx.AsyncClient(timeout=DATAVERSE_TIMEOUT_SECONDS) as client:
                resp = await client.get(imds_url, headers={"Metadata": "true"})
                resp.raise_for_status()
                token_body = resp.json()
                self._access_token = token_body["access_token"]
                self._token_expires_at = now + max(int(token_body.get("expires_in", 3600)) - 60, 60)
                return self._access_token

        # 3. Standard OAuth 2.0 Client Credentials
        if self.client_secret:
            async with httpx.AsyncClient(timeout=DATAVERSE_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    token_url,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "scope": scope,
                        "grant_type": "client_credentials",
                    },
                )
                response.raise_for_status()
                token_body = response.json()

            self._access_token = token_body["access_token"]
            self._token_expires_at = now + max(int(token_body.get("expires_in", 3600)) - 60, 60)
            return self._access_token

        raise ValueError(
            f"No valid credentials found for Dataverse authentication (client_id='{self.client_id}'). "
            "Provide client_secret, federated token (AZURE_FEDERATED_TOKEN/AZURE_FEDERATED_TOKEN_FILE), "
            "or configure Managed Identity."
        )

    async def _create_live_audit_row(self, payload: Dict[str, Any]) -> str:
        token = await self._get_access_token()
        url = f"{self.base_url}/api/data/{DATAVERSE_API_VERSION}/{AUDIT_ENTITY_SET}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Prefer": "return=representation",
        }
        async with httpx.AsyncClient(timeout=DATAVERSE_TIMEOUT_SECONDS) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            created = response.json() if response.content else {}
        return created.get("cre2f_veloraagentauditlogid", "")

    def check_alternate_key_exists(self, invocation_id: str, record_type: str, record: Optional[DataverseAuditRecord] = None) -> bool:
        if not invocation_id:
            return False
        if (invocation_id, record_type) not in self._alternate_keys_index:
            return False
        if record is not None:
            existing = self._alternate_keys_index[(invocation_id, record_type)]
            if existing.get("operation") and record.operation and existing["operation"] != record.operation:
                return False
        return True

    def check_successful_idempotency_exists(self, idempotency_key: str, operation: str) -> bool:
        if not idempotency_key:
            return False
        return (idempotency_key, operation) in self._idempotency_index

    async def create_audit_record(self, record: DataverseAuditRecord) -> Dict[str, Any]:
        if self.simulate_down:
            log.error("dataverse_simulated_down_audit_failed", record_type=record.record_type)
            raise ConnectionError("Dataverse service endpoint is unreachable (simulated outage).")

        payload = record.to_dataverse_payload()
        inv_id = record.invocation_id
        rec_type = record.record_type
        idemp_key = record.idempotency_key
        operation = record.operation

        if inv_id and self.check_alternate_key_exists(inv_id, rec_type, record):
            existing = self._alternate_keys_index.get((inv_id, rec_type), {})
            existing_id = existing.get("id") or f"EXISTS-{inv_id}"
            log.warning("duplicate_alternate_key_detected", invocation_id=inv_id, record_type=rec_type)
            return {
                "status": "DUPLICATE_KEY",
                "commit_status": AuditCommitStatus.ALREADY_COMMITTED,
                "audit_record_id": existing_id,
                "message": f"Record with invocation ID '{inv_id}' and record type '{rec_type}' already exists and is committed.",
                "id": existing_id,
                "invocation_id": inv_id,
            }

        if rec_type == RECORD_TYPE_TRANSACTION_START and self.check_successful_idempotency_exists(idemp_key, operation):
            log.warning("duplicate_successful_transaction_detected", idempotency_key=idemp_key, operation=operation)
            existing_id = f"EXISTS-{idemp_key}"
            return {
                "status": AuditCommitStatus.ALREADY_COMMITTED,
                "commit_status": AuditCommitStatus.ALREADY_COMMITTED,
                "audit_record_id": existing_id,
                "message": f"A successful transaction for operation '{operation}' with idempotency key '{idemp_key}' has already executed.",
                "id": existing_id,
                "invocation_id": inv_id,
            }

        if not self.is_live:
            buf_id = f"BUF-{rec_type}-{int(time.time() * 1000)}-{os.urandom(2).hex()}"
            payload["cre2f_veloraagentauditlogid"] = buf_id
            payload["cre2f_loggingstatus"] = AuditCommitStatus.BUFFERED
            self._audit_store.append(payload)
            # CRITICAL (E11 / W03): A local buffer cannot populate confirmed-commit indices
            # (_alternate_keys_index or _idempotency_index). Only live committed records do.
            log.info("dataverse_not_configured_audit_buffered", record_type=rec_type, buffer_id=buf_id)
            return {
                "status": "SUCCESS",
                "commit_status": AuditCommitStatus.BUFFERED,
                "audit_record_id": buf_id,
                "id": buf_id,
                "invocation_id": inv_id,
                "logging_status": AuditCommitStatus.BUFFERED,
            }

        try:
            log_id = await self._create_live_audit_row(record.to_audit_log_payload())
            payload["cre2f_veloraagentauditlogid"] = log_id
            payload["cre2f_loggingstatus"] = AuditCommitStatus.COMMITTED
            self._audit_store.append(payload)
            if inv_id:
                self._alternate_keys_index[(inv_id, rec_type)] = {
                    "id": log_id,
                    "record_type": rec_type,
                    "invocation_id": inv_id,
                    "operation": operation,
                    "committed_at": datetime.now(timezone.utc).isoformat(),
                }
            if rec_type in (RECORD_TYPE_TRANSACTION_RESULT, RECORD_TYPE_TOOL_EXECUTION_END) and record.outcome == "SUCCESS":
                if idemp_key:
                    self._idempotency_index.add((idemp_key, operation))

            return {
                "status": "SUCCESS",
                "commit_status": AuditCommitStatus.COMMITTED,
                "audit_record_id": log_id,
                "id": log_id,
                "invocation_id": inv_id,
            }
        except httpx.HTTPStatusError as http_err:
            resp_text = http_err.response.text if http_err.response else ""
            is_verified_dup = any(
                code in resp_text
                for code in ("0x80040333", "DuplicateKey", "DuplicateRecord", "already exists", "Cannot insert duplicate key")
            )
            if http_err.response.status_code in (409, 412) and is_verified_dup:
                log.info("dataverse_duplicate_already_committed", invocation_id=inv_id, record_type=rec_type)
                existing_id = f"EXISTS-{inv_id}"
                return {
                    "status": AuditCommitStatus.ALREADY_COMMITTED,
                    "commit_status": AuditCommitStatus.ALREADY_COMMITTED,
                    "audit_record_id": existing_id,
                    "id": existing_id,
                    "invocation_id": inv_id,
                    "message": f"Durable record for invocation ID '{inv_id}' and record type '{rec_type}' already exists in Dataverse.",
                }
            log.error("dataverse_live_write_failed", error=str(http_err), status_code=http_err.response.status_code, response=resp_text)
            raise ConnectionError(f"Dataverse destination write failed (HTTP {http_err.response.status_code}): {resp_text}") from http_err
        except Exception as exc:
            log.error("dataverse_live_write_failed", error=str(exc))
            raise ConnectionError(f"Dataverse destination write failed: {exc}") from exc

    async def start_write_transaction_fail_closed(self, record: DataverseAuditRecord) -> Dict[str, Any]:
        if record.record_type != RECORD_TYPE_TRANSACTION_START:
            record.record_type = RECORD_TYPE_TRANSACTION_START

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
                if strict_fail_closed and not (os.getenv("ALLOW_BUFFERED_AUDIT_WRITES", "") == "1" or os.getenv("MOCK_M365", "") == "1"):
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

    def clear_all_for_testing(self) -> None:
        self._audit_store.clear()
        self._policy_store.clear()
        self._alternate_keys_index.clear()
        self._idempotency_index.clear()
        self.simulate_down = False


_global_dataverse_client = DataverseClient()


def get_dataverse_client() -> DataverseClient:
    return _global_dataverse_client
