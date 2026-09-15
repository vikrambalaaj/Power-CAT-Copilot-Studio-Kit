"""S/4HANA OData v4 resilient client supporting auth, paging, and strict contract verification."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from time import monotonic
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import httpx

from .cache import S4ReadCache
from .contracts import ReportStatus, create_coverage, create_source_record
from .settings import S4Settings, get_settings

log = logging.getLogger("s4hana_mcp.client")


def escape_odata(val: str) -> str:
    """Escape single quotes in OData string literals."""
    return str(val).replace("'", "''")


def bounded_top(value: Any, default: int = 100, min_val: int = 1, max_val: int = 1000) -> int:
    try:
        ival = int(value)
        return max(min_val, min(ival, max_val))
    except (ValueError, TypeError):
        return default


def validate_relative_entity(entity: str) -> str:
    """Ensure entity is a clean relative path segment, rejecting path traversal or absolute URLs."""
    e = str(entity).strip().lstrip("/")
    if ".." in e or e.startswith("http://") or e.startswith("https://") or "\\" in e:
        raise ValueError(f"Invalid or unsafe entity name: {entity}")
    return e


class S4Client:
    def __init__(self, settings: S4Settings | None = None):
        self.settings = settings or get_settings()
        self._oauth_token: str | None = None
        self._oauth_token_expires_at: float = 0.0
        self._read_cache = S4ReadCache(
            ttl_seconds=getattr(self.settings, "cache_ttl_seconds", 60),
            max_entries=getattr(self.settings, "cache_max_entries", 512),
            enabled=getattr(self.settings, "cache_enabled", True),
        )

    def validate(self) -> list[str]:
        """Validate client configuration and return any error messages."""
        errors: list[str] = []
        try:
            self._validated_base_url()
        except ValueError as ex:
            errors.append(str(ex))
        if not getattr(self.settings, "s4_ar_entity", ""):
            errors.append("s4_ar_entity is required")
        if not getattr(self.settings, "s4_ap_entity", ""):
            errors.append("s4_ap_entity is required")
        if not getattr(self.settings, "s4_budget_transfer_entity", ""):
            errors.append("s4_budget_transfer_entity is required")
        if not getattr(self.settings, "s4_budget_consumption_entity", ""):
            errors.append("s4_budget_consumption_entity is required")
        return errors


    def _validated_base_url(self, override_url: str | None = None) -> str:
        """Validate and return service base URL, strictly enforcing approved hosts and environment separation (F05)."""
        url = (override_url or self.settings.s4_api_url).rstrip("/")
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise ValueError(f"Insecure HTTP scheme rejected for S/4HANA endpoint: {url}")
        host = (parsed.hostname or "").lower()
        env = getattr(self.settings, "s4_environment_label", "Production").lower()

        # Enforce exact approved host and production/QAS separation
        if env in {"production", "prod"}:
            if host != "fiori.velora.ae":
                raise ValueError(f"Unapproved host (not allowlisted) for Production S/4HANA endpoint: '{host}'. Must be 'fiori.velora.ae'.")
        elif env in {"qas", "staging", "test"}:
            if host not in {"fioriqas.velora.ae", "fiori-qas.velora.ae", "fiori.velora.ae"}:
                raise ValueError(f"Unapproved host (not allowlisted) for QAS S/4HANA endpoint: '{host}'.")
        else:
            if host != "fiori.velora.ae":
                raise ValueError(f"Unapproved host (not allowlisted) for S/4HANA endpoint: '{host}'.")

        # Check path prefix: must be approved OData service path
        path = parsed.path.rstrip("/")
        approved_prefixes = (
            "/sap/opu/odata4/sap/zfi_sbn_ageingdata_srv/srvd_a2x/sap/zfi_sdf_ageingdata_srv/0001",
            "/sap/opu/odata/sap/zfi_sbn_ageingdata_srv",
            "/sap/opu/odata4/sap/zfi_budget_srv",
        )
        if not any(path == prefix or path.startswith(prefix + "/") for prefix in approved_prefixes):
            raise ValueError(f"Unapproved service path for S/4HANA endpoint: '{path}'.")

        return url

    def _get_composite_row_key(self, row: dict[str, Any]) -> str:
        """Construct metadata-confirmed composite entity key for accurate duplicate & line-item handling (F03)."""
        # AR / AP line item composite key: CompanyCode + FiscalYear + AccountingDocument + Item
        doc = row.get("AccountingDocument")
        if doc:
            comp = str(row.get("CompanyCode") or "").strip()
            fy = str(row.get("FiscalYear") or "").strip()
            item = str(row.get("AccountingDocumentItem") or row.get("LineItem") or "").strip()
            return f"ACC:{comp}:{fy}:{doc}:{item}"

        # Budget movement / entry document line item key (T07)
        b_change = row.get("BudgetChangeDocument")
        b_entry = row.get("BudgetEntryDocument")
        if b_change or b_entry:
            b_doc = str(b_change or b_entry).strip()
            fma = str(row.get("FinancialManagementArea") or "").strip()
            fy = str(row.get("FinMgmtAreaFiscalYear") or row.get("BudgetDocumentYear") or "").strip()
            item = str(
                row.get("BudgetChangeDocumentItem")
                or row.get("BudgetEntryDocumentItem")
                or row.get("BudgetDocumentItem")
                or row.get("LineItem")
                or ""
            ).strip()
            ci = str(row.get("CommitmentItem") or "").strip()
            fc = str(row.get("FundsCenter") or "").strip()
            return f"BDG:{fma}:{fy}:{b_doc}:{item}:{fc}:{ci}"

        # Budget consumption composite key (T08)
        if "BudgetAmountInFMACrcy" in row or "FundsCenter" in row:
            fma = str(row.get("FinancialManagementArea") or "").strip()
            fc = str(row.get("FundsCenter") or "").strip()
            ci = str(row.get("CommitmentItem") or "").strip()
            fy = str(row.get("FinMgmtAreaFiscalYear") or "").strip()
            bv = str(row.get("BudgetVersion") or "").strip()
            period = str(row.get("FinMgmtAreaPeriod") or row.get("FiscalPeriod") or row.get("PostingPeriod") or "").strip()
            doc_id = str(row.get("FinancialManagementAreaDoc") or row.get("BudgetDocumentItem") or "").strip()
            return f"CNS:{fma}:{fy}:{bv}:{fc}:{ci}:{period}:{doc_id}"

        return ""

    async def _authorization(self) -> str:
        mode = getattr(self.settings, "s4_auth_mode", "basic").lower()
        if mode == "basic":
            user = self.settings.s4_username or ""
            pwd = self.settings.s4_password or ""
            if not user or not pwd:
                raise RuntimeError("S/4HANA basic auth credentials not configured")
            token = base64.b64encode(f"{user}:{pwd}".encode()).decode("ascii")
            return f"Basic {token}"
        elif mode == "oauth":
            return await self._get_oauth_token()
        elif mode == "none":
            return ""
        raise ValueError(f"Unsupported auth mode: {mode}")

    async def _get_oauth_token(self) -> str:
        if self._oauth_token and monotonic() < self._oauth_token_expires_at:
            return f"Bearer {self._oauth_token}"

        token_url = self.settings.s4_token_url
        client_id = self.settings.s4_client_id
        client_secret = self.settings.s4_client_secret
        if not token_url or not client_id or not client_secret:
            raise RuntimeError("OAuth token URL or client credentials not configured")

        verify_opt = self.settings.s4_ca_bundle if self.settings.s4_ca_bundle else self.settings.s4_verify_tls
        async with httpx.AsyncClient(verify=verify_opt) as client:
            resp = await client.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                timeout=15.0,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"OAuth token request failed with HTTP {resp.status_code}")
            payload = resp.json()
            token = payload.get("access_token")
            if not token:
                raise RuntimeError("OAuth response did not contain an access token")
            expires_in = max(1, int(payload.get("expires_in", 300)))
            skew = max(0, int(getattr(self.settings, "oauth_token_cache_skew_seconds", 30)))
            self._oauth_token = token
            self._oauth_token_expires_at = monotonic() + max(1, expires_in - skew)
            return f"Bearer {token}"

    def _validate_safe_next_link(self, next_link: str, expected_base: str, expected_entity: str | None = None) -> str:
        """
        Ensure nextLink is within allowed origin, scheme, exact service path boundary, entity, and approved sap-client (R04).
        """
        resolved = urljoin(expected_base + "/", next_link)
        parsed_target = urlparse(resolved)
        parsed_base = urlparse(expected_base)
        
        # 1. Scheme and host
        if parsed_target.scheme != "https" or parsed_target.netloc.lower() != parsed_base.netloc.lower():
            raise ValueError(f"Cross-origin continuation link rejected: {next_link}")
            
        # 2. Path segment boundary: parsed_base.path must be exact prefix ending at '/' or exact match
        base_path = parsed_base.path.rstrip("/")
        target_path = parsed_target.path.rstrip("/")
        
        if not (target_path == base_path or target_path.startswith(base_path + "/")):
            raise ValueError(f"Continuation link path outside service root: {next_link}")
            
        # Entity path verification: must target the exact expected entity (F05)
        if expected_entity:
            relative_path = target_path[len(base_path):].strip("/")
            if relative_path != expected_entity:
                raise ValueError(f"Continuation link targets unapproved entity '{relative_path}', expected '{expected_entity}'")
            
        # 3. SAP Client parameter validation (R04)
        qs = parse_qs(parsed_target.query, keep_blank_values=True)
        approved_client = str(getattr(self.settings, "s4_sap_client", "100") or "100").strip()
        
        client_vals = qs.get("sap-client", [])
        if len(client_vals) > 1:
            raise ValueError("Duplicate sap-client parameter in continuation link")
        elif len(client_vals) == 1:
            if client_vals[0] != approved_client:
                raise ValueError(f"Continuation link attempts to change sap-client to '{client_vals[0]}', expected '{approved_client}'")
        else:
            # sap-client was omitted in nextLink query: inject approved sap-client so credentials aren't forwarded without client!
            qs["sap-client"] = [approved_client]
            new_query = urlencode(qs, doseq=True)
            resolved = urlunparse((
                parsed_target.scheme,
                parsed_target.netloc,
                parsed_target.path,
                parsed_target.params,
                new_query,
                parsed_target.fragment,
            ))
            
        return resolved

    async def _request(
        self,
        entity: str,
        params: dict[str, Any],
        base_url: str | None = None,
        max_rows: int | None = None,
        max_pages: int | None = None,
    ) -> dict[str, Any]:
        if entity == "$metadata":
            url = f"{self._validated_base_url(base_url)}/$metadata"
            params = {}
        elif entity:
            path = validate_relative_entity(entity)
            effective_base = self._validated_base_url(base_url)
            url = f"{effective_base}/{path}"
        else:
            effective_base = self._validated_base_url(base_url)
            url = effective_base
            params = {}

        effective_base = self._validated_base_url(base_url)
        safe_params = dict(params)
        approved_client = str(getattr(self.settings, "s4_sap_client", "100") or "100").strip()
        safe_params.setdefault("sap-client", approved_client)

        limit_rows = max_rows or getattr(self.settings, "s4_report_max_rows", 1000)
        limit_pages = max_pages or getattr(self.settings, "s4_report_max_pages", 50)
        timeout_seconds = getattr(self.settings, "s4_total_timeout_seconds", 60.0)
        deadline = monotonic() + timeout_seconds

        rows: list[dict[str, Any]] = []
        page_count = 0
        total_declared: int | None = None
        seen_next_urls: set[str] = set()
        seen_row_signatures: dict[str, str] = {}
        next_url: str | None = None
        is_complete = True
        incomplete_reason = ""

        try:
            authorization = await self._authorization()
            verify_opt = self.settings.s4_ca_bundle if self.settings.s4_ca_bundle else self.settings.s4_verify_tls

            async with httpx.AsyncClient(timeout=timeout_seconds, verify=verify_opt) as client:
                current_url = url
                current_params = safe_params

                while current_url and page_count < limit_pages:
                    remaining_time = deadline - monotonic()
                    if remaining_time <= 0:
                        is_complete = False
                        incomplete_reason = f"Exceeded total report query deadline ({timeout_seconds}s)"
                        break

                    headers = {
                        "Accept": "application/json",
                        "User-Agent": "Velora-S4HANA-Client/2.0",
                    }
                    if authorization:
                        headers["Authorization"] = authorization

                    req_timeout = max(0.1, min(remaining_time, getattr(self.settings, "s4_request_timeout_seconds", 15.0)))

                    page_count += 1
                    
                    # Transient retry loop (R05)
                    response = None
                    for attempt in range(2):
                        response = await client.get(current_url, params=current_params, headers=headers, timeout=req_timeout)
                        if response.status_code in {408, 429, 502, 503, 504} and attempt == 0:
                            rem = deadline - monotonic()
                            if rem <= 0:
                                is_complete = False
                                incomplete_reason = f"Exceeded total report query deadline ({timeout_seconds}s) during retry"
                                break
                            req_timeout = max(0.1, min(rem, getattr(self.settings, "s4_request_timeout_seconds", 15.0)))
                            continue
                        break

                    if not response or (response.status_code in {408, 429, 502, 503, 504} and not is_complete):
                        break

                    if response.status_code in {401, 403}:
                        return {
                            "status": "error",
                            "code": "ACCESS_DENIED" if response.status_code == 403 else "UNAUTHORIZED",
                            "message": f"S/4HANA authentication/authorization failed with HTTP {response.status_code}",
                            "retryable": False,
                        }
                    if response.status_code >= 400:
                        detail = ""
                        try:
                            err_body = response.json()
                            if isinstance(err_body, dict):
                                err_obj = err_body.get("error")
                                if isinstance(err_obj, dict):
                                    detail = err_obj.get("message") or str(err_obj)
                                elif err_obj:
                                    detail = str(err_obj)
                        except Exception:
                            detail = response.text[:300] if hasattr(response, "text") else ""
                        err_msg = f"S/4HANA request failed with HTTP {response.status_code}" + (f": {detail}" if detail else "")
                        log.error(f"S/4HANA upstream error: {err_msg} on {current_url}")
                        return {
                            "status": "error",
                            "code": "S4_UPSTREAM_ERROR",
                            "message": err_msg,
                            "retryable": response.status_code in {408, 429, 500, 502, 503, 504},
                        }

                    # Parse response safely with exact decimal preservation (T01)
                    try:
                        raw_bytes = response.content
                        payload = json.loads(raw_bytes.decode("utf-8"), parse_float=Decimal)
                    except Exception as e:
                        return {
                            "status": "error",
                            "code": "CONTRACT_MISMATCH",
                            "message": f"Failed to parse S/4 JSON response: {e}",
                            "retryable": False,
                        }

                    page_rows: list[dict[str, Any]] = []
                    page_next_link: str | None = None

                    # Strict shape validation (R08)
                    if isinstance(payload, dict):
                        if "value" in payload and isinstance(payload["value"], list):
                            page_rows = payload["value"]
                            if "@odata.count" in payload:
                                total_declared = int(payload["@odata.count"])
                            page_next_link = payload.get("@odata.nextLink")
                        elif "d" in payload:
                            data = payload["d"]
                            if isinstance(data, dict):
                                page_rows = data.get("results", [])
                                if "__count" in data:
                                    total_declared = int(data["__count"])
                                page_next_link = data.get("__next")
                            elif isinstance(data, list):
                                page_rows = data
                        elif "results" in payload and isinstance(payload["results"], list):
                            page_rows = payload.get("results", [])
                            if "__count" in payload:
                                total_declared = int(payload["__count"])
                        else:
                            # Not an expected OData collection shape (R08)
                            return {
                                "status": "error",
                                "code": "CONTRACT_MISMATCH",
                                "message": "OData response does not match expected collection contract",
                                "retryable": False,
                            }
                    elif isinstance(payload, list):
                        page_rows = payload
                    else:
                        return {
                            "status": "error",
                            "code": "CONTRACT_MISMATCH",
                            "message": "OData response payload is not an object or array",
                            "retryable": False,
                        }

                    # Append rows and verify conflict / snapshot consistency (R05, F03)
                    for row in page_rows:
                        if len(rows) >= limit_rows:
                            is_complete = False
                            incomplete_reason = f"Exceeded maximum row bound ({limit_rows})"
                            break

                        row_key = self._get_composite_row_key(row)
                        row_sig = hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()

                        if row_key:
                            if row_key in seen_row_signatures:
                                if seen_row_signatures[row_key] == row_sig:
                                    # Identical duplicate line: deduplicate, do not double count
                                    continue
                                else:
                                    # Conflicting snapshot version of the same composite entity key
                                    is_complete = False
                                    incomplete_reason = f"Snapshot inconsistency detected: conflicting versions of document line {row_key}"
                                    break
                            seen_row_signatures[row_key] = row_sig

                        rows.append(row)

                    if not is_complete:
                        break

                    # Check nextLink continuation with strict boundary validator (R04)
                    if page_next_link:
                        safe_link = self._validate_safe_next_link(page_next_link, effective_base, expected_entity=entity)
                        if safe_link in seen_next_urls:
                            is_complete = False
                            incomplete_reason = "Continuation loop detected in OData response"
                            break
                        seen_next_urls.add(safe_link)
                        current_url = safe_link
                        current_params = {}  # NextLink contains query parameters
                    else:
                        current_url = None

                if current_url and page_count >= limit_pages and not incomplete_reason:
                    is_complete = False
                    incomplete_reason = f"Exceeded maximum page bound ({limit_pages})"

            # Terminal completeness evaluation (R05)
            if total_declared is not None and len(rows) < total_declared:
                is_complete = False
                if not incomplete_reason:
                    incomplete_reason = f"Retrieved {len(rows)} rows, but server declared total of {total_declared} rows."

            return {
                "rows": rows,
                "count": total_declared if total_declared is not None else len(rows),
                "declared_count_present": total_declared is not None,
                "pages": page_count,
                "complete": is_complete,
                "incomplete_reason": incomplete_reason,
            }
        except (httpx.HTTPError, ValueError, RuntimeError, json.JSONDecodeError) as error:
            return {
                "status": "error",
                "code": "S4_CONNECTION_ERROR",
                "message": f"S/4HANA request failed: {error}",
                "retryable": isinstance(error, httpx.HTTPError),
            }

    async def query(
        self,
        entity: str,
        capability: str,
        filters: dict[str, str | None],
        period: str | None = None,
        currency: str | None = None,
        correlation_id: str | None = None,
        top: int = 100,
        override_base_url: str | None = None,
        max_rows: int | None = None,
    ) -> dict[str, Any]:
        # Construct $filter clauses
        clauses = []
        for key, value in filters.items():
            if value is not None:
                # Blank string filter support (R06)
                if value == "":
                    clauses.append(f"{key} eq ''")
                else:
                    clauses.append(f"{key} eq '{escape_odata(value)}'")

        # OData query parameters: full-input collection independent of detail size (F05)
        params: dict[str, Any] = {"$count": "true"}
        if clauses:
            params["$filter"] = " and ".join(clauses)

        effective_base = self._validated_base_url(override_base_url)
        key_payload = {
            "baseUrl": effective_base,
            "authMode": self.settings.s4_auth_mode,
            "entity": entity,
            "params": params,
        }
        cache_key = hashlib.sha256(
            json.dumps(key_payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()

        result, cache_info = await self._read_cache.get_or_load(
            cache_key,
            lambda: self._request(entity, params, base_url=effective_base, max_rows=max_rows),
            cacheable=lambda value: value.get("status") != "error",
        )

        if result.get("status") == "error":
            result["correlationId"] = correlation_id or ""
            result["audit"] = {
                "correlationId": correlation_id or "",
                "executingIdentity": self.settings.executing_identity,
                "authorizationModel": self.settings.authorization_model,
            }
            result["cache"] = cache_info.as_dict()
            return result

        rows = result.get("rows", [])
        total = result.get("count", len(rows))
        is_complete = result.get("complete", True) and (len(rows) >= total or total == 0)
        incomplete_reason = result.get("incomplete_reason", "")
        status = ReportStatus.COMPLETE.value if is_complete else ReportStatus.PARTIAL.value
        if len(rows) == 0:
            status = ReportStatus.EMPTY.value

        retrieved_at = cache_info.stored_at or datetime.now(timezone.utc).isoformat()
        comp_code = filters.get("CompanyCode") or filters.get("FinancialManagementArea") or "1000"

        coverage = create_coverage(
            rows_read=len(rows),
            rows_displayed=min(len(rows), bounded_top(top)),
            page_count=result.get("pages", 1),
            declared_total=total,
            completion_state="COMPLETE" if is_complete else "PARTIAL",
            incomplete_reason=incomplete_reason,
        )

        source_record = create_source_record(
            source_id=f"S4_{capability.upper()}",
            business_title=f"SAP S/4HANA {capability}",
            description=f"Authorized SAP financial service for {capability}",
            environment=getattr(self.settings, "s4_environment_label", "Production"),
            organization_scope=str(comp_code),
            report_period=str(period or "Current"),
            currency=str(currency or ""),
            retrieved_at=retrieved_at,
            completeness="COMPLETE" if is_complete else "PARTIAL",
            known_limitations=[incomplete_reason] if incomplete_reason else [],
        )

        declared_present = result.get("declared_count_present", False)
        if not declared_present:
            # Without server count verification, confidence is capped at Medium
            confidence = "Medium" if is_complete and status != ReportStatus.EMPTY.value else "Low"
            confidence_reason = "Retrieved pages without server-declared count verification" if is_complete else (incomplete_reason or "Incomplete extraction")
        elif is_complete and status != ReportStatus.EMPTY.value:
            confidence = "High"
            confidence_reason = "Complete unadjusted source extraction matching server count"
        else:
            confidence = "Low"
            confidence_reason = incomplete_reason or "Sampled or bounded results"

        return {
            "status": status,
            "data": {"records": rows, "total": total},
            "coverage": coverage,
            "sources": [source_record],
            "query": {"filters": {k: v for k, v in filters.items() if v is not None}, "period": period, "currency": currency},
            "quality": {
                "complete": is_complete,
                "sampled": not is_complete,
                "confidence": confidence,
                "confidenceReason": confidence_reason,
                "warnings": [incomplete_reason] if incomplete_reason else [],
            },
            "audit": {
                "correlationId": correlation_id or "",
                "executingIdentity": self.settings.executing_identity,
                "authorizationModel": self.settings.authorization_model,
            },
            "cache": cache_info.as_dict(),
            "type": capability,
        }

    async def query_profit_and_loss(self, **kwargs: Any) -> dict[str, Any]:
        """P&L is removed from the S/4HANA service scope. Return explicit unsupported response."""
        return {
            "status": ReportStatus.ERROR.value,
            "code": ReportStatus.UNSUPPORTED_OPERATION.value,
            "message": "P&L report is excluded from S/4HANA service scope.",
            "retryable": False,
            "type": "ProfitAndLoss",
        }
