"""SAP SuccessFactors OData v2 API client — authentication, HTTP requests, Delegated Identity & RBP trimming."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx
from dotenv import load_dotenv

from .successfactors_settings import get_settings
from .cache import AsyncTTLCache
from shared_mcp.logger import get_logger

log = get_logger("sf_hcm")


def _escape_odata_string(value: str) -> str:
    """Escape a string literal according to OData v2 quoting rules."""
    return value.replace("'", "''")


def _bounded_top(value: int, maximum: int = 1000) -> int:
    return max(1, min(int(value), maximum))


def _csv_codes(value: str) -> set[str]:
    return {item.strip() for item in (value or "").split(",") if item.strip()}


def _parse_sf_date(value: Any) -> Optional[date]:
    if isinstance(value, str):
        match = re.search(r"/Date\((\d+)", value)
        if match:
            return datetime.fromtimestamp(int(match.group(1)) / 1000, tz=timezone.utc).date()
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _load_env() -> None:
    explicit = os.environ.get("MCP_SERVERS_ENV_FILE")
    if explicit:
        load_dotenv(explicit, override=True)
        return
    project_env = Path.cwd() / "env" / ".env.dev"
    if project_env.exists():
        load_dotenv(project_env, override=True)
        return
    load_dotenv()


_load_env()
_settings = get_settings()


class SuccessFactorsClient:
    """Async OData v2 client for SAP SuccessFactors HCM API supporting Delegated Identity & RBP Trimming."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.base_url = self.settings.sf_api_url.rstrip("/")
        self._read_cache = AsyncTTLCache[Dict[str, Any]](
            enabled=getattr(self.settings, "cache_enabled", True),
            ttl_seconds=getattr(self.settings, "cache_ttl_seconds", 120),
            max_entries=getattr(self.settings, "cache_max_entries", 512),
        )
        self._aggregate_cache = AsyncTTLCache[Dict[str, Any]](
            enabled=getattr(self.settings, "cache_enabled", True),
            ttl_seconds=getattr(self.settings, "aggregate_cache_ttl_seconds", 900),
            max_entries=getattr(self.settings, "aggregate_cache_max_entries", 128),
        )

    def _get_auth_header(self) -> str:
        """Construct Basic Auth header in format username@companyId:password."""
        user_company = f"{self.settings.sf_username}@{self.settings.sf_company_id}"
        creds = f"{user_company}:{self.settings.sf_password}"
        encoded = base64.b64encode(creds.encode("utf-8")).decode("utf-8")
        return f"Basic {encoded}"

    def _get_headers(self, executive_id: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "Authorization": self._get_auth_header(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        return headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        executive_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = self._get_headers(executive_id=executive_id)
        query_params = dict(params or {})
        query_params.setdefault("$format", "json")

        log.debug("sf_request", method=method, url=url, executive_id=bool(executive_id))

        async def send_request() -> Dict[str, Any]:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.request(
                    method,
                    url,
                    headers=headers,
                    params=query_params,
                    json=json_data,
                )
                if resp.status_code >= 400:
                    log.error("sf_api_error", status=resp.status_code)
                    return {
                        "error": True,
                        "status": resp.status_code,
                        "error_category": "authorization" if resp.status_code in {401, 403} else "service",
                        "message": (
                            "I couldn't retrieve that information with the current access."
                            if resp.status_code in {401, 403}
                            else "I couldn't retrieve that information right now. Please try again shortly."
                        ),
                    }
                if not resp.content:
                    return {"success": True}
                res_data = resp.json()
                if "d" in res_data:
                    return res_data["d"]
                return res_data

        try:
            if method.upper() == "GET":
                key_payload = {
                    "baseUrl": self.base_url,
                    "executiveId": executive_id or "configured-service-account",
                    "endpoint": endpoint,
                    "params": query_params,
                }
                cache_key = hashlib.sha256(
                    json.dumps(key_payload, sort_keys=True, separators=(",", ":"), default=str).encode()
                ).hexdigest()
                result, cache_info = await self._read_cache.get_or_load(
                    cache_key,
                    send_request,
                    cacheable=lambda value: isinstance(value, dict) and not value.get("error"),
                )
                if isinstance(result, dict):
                    result["_cache"] = cache_info.as_dict()
                return result

            result = await send_request()
            if isinstance(result, dict) and not result.get("error"):
                await self._read_cache.clear()
                await self._aggregate_cache.clear()
            return result
        except Exception as exc:
            log.error("sf_client_exception", error=str(exc))
            return {
                "error": True,
                "error_category": "service",
                "message": "I couldn't retrieve that information right now. Please try again shortly.",
            }

    async def _fetch_all(
        self,
        entity: str,
        *,
        select: str,
        filter_str: Optional[str] = None,
        as_of_date: Optional[str] = None,
        executive_id: Optional[str] = None,
        page_size: int = 1000,
    ) -> Dict[str, Any]:
        """Read every RBP-visible OData page and report explicit coverage."""
        rows: List[Dict[str, Any]] = []
        page_caches: List[Dict[str, Any]] = []
        total_available: Optional[int] = None
        offset = 0
        seen_pages: set[str] = set()
        while True:
            params: Dict[str, Any] = {
                "$top": _bounded_top(page_size),
                "$skip": offset,
                "$select": select,
                "$inlinecount": "allpages",
            }
            if filter_str:
                params["$filter"] = filter_str
            if as_of_date:
                params["asOfDate"] = as_of_date
            page = await self._request("GET", entity, params=params, executive_id=executive_id)
            if not isinstance(page, dict) or page.get("error"):
                return page if isinstance(page, dict) else {
                    "error": True,
                    "message": f"Unexpected {entity} response.",
                }
            page_rows = page.get("results", [])
            if not isinstance(page_rows, list):
                return {
                    "error": True,
                    "error_category": "pagination",
                    "message": f"Unexpected {entity} page format.",
                }
            if page.get("__count") is not None:
                try:
                    total_available = int(page["__count"])
                except (TypeError, ValueError):
                    return {
                        "error": True,
                        "error_category": "pagination",
                        "message": f"Invalid {entity} total count.",
                    }
            if page_rows:
                page_fingerprint = hashlib.sha256(
                    json.dumps(page_rows, sort_keys=True, separators=(",", ":"), default=str).encode()
                ).hexdigest()
                if page_fingerprint in seen_pages:
                    return {
                        "error": True,
                        "error_category": "pagination",
                        "message": f"Repeated {entity} page prevented a complete result.",
                    }
                seen_pages.add(page_fingerprint)
            rows.extend(page_rows)
            page_caches.append(page.get("_cache", {}))
            offset += len(page_rows)
            if not page_rows:
                break
            if total_available is not None and len(rows) >= total_available:
                break
            if total_available is None and len(page_rows) < _bounded_top(page_size):
                break
        resolved_total = total_available if total_available is not None else len(rows)
        return {
            "results": rows,
            "total_available": resolved_total,
            "rows_returned": len(rows),
            "complete": len(rows) == resolved_total,
            "page_caches": page_caches,
        }

    async def _nationality_map(
        self,
        *,
        executive_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        entity = self.settings.sf_nationality_entity.strip()
        person_field = self.settings.sf_nationality_person_id_field.strip()
        nationality_field = self.settings.sf_nationality_field.strip()
        if not entity or not person_field or not nationality_field:
            return {
                "error": True,
                "message": "SuccessFactors nationality entity and field mapping is not configured.",
                "error_category": "configuration",
            }
        response = await self._fetch_all(
            entity,
            select=f"{person_field},{nationality_field}",
            executive_id=executive_id,
        )
        if response.get("error"):
            return response
        mapping = {
            str(row.get(person_field)): str(row.get(nationality_field) or "")
            for row in response.get("results", [])
            if row.get(person_field)
        }
        return {
            "mapping": mapping,
            "entity": entity,
            "person_id_field": person_field,
            "nationality_field": nationality_field,
            "coverage": {
                "rows_returned": response.get("rows_returned", 0),
                "total_available": response.get("total_available", 0),
                "complete": response.get("complete", False),
            },
            "cache": response.get("page_caches", []),
        }

    async def _active_user_ids(
        self,
        *,
        executive_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        active_codes = _csv_codes(self.settings.sf_active_user_statuses)
        if not active_codes:
            return {
                "error": True,
                "message": "SF_ACTIVE_USER_STATUSES is not configured.",
                "error_category": "configuration",
            }
        response = await self._fetch_all(
            "User", select="userId,status", executive_id=executive_id
        )
        if response.get("error"):
            return response
        ids = {
            str(row.get("userId"))
            for row in response.get("results", [])
            if row.get("userId") and str(row.get("status") or "") in active_codes
        }
        return {
            "ids": ids,
            "status_codes": sorted(active_codes),
            "coverage": {
                "rows_returned": response.get("rows_returned", 0),
                "total_available": response.get("total_available", 0),
                "complete": response.get("complete", False),
            },
            "cache": response.get("page_caches", []),
        }

    # ── Headcount & Position Count (EmpJob) - Slide 4 Capability 01 ───────────

    async def list_emp_jobs(
        self,
        user_id: Optional[str] = None,
        company: Optional[str] = None,
        department: Optional[str] = None,
        business_unit: Optional[str] = None,
        job_title: Optional[str] = None,
        as_of_date: Optional[str] = None,
        top: int = 20,
        executive_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query headcount & position count (EmpJob), trimmed by SuccessFactors Role-Based Permissions (RBP)."""
        if not any((user_id, company, department, business_unit, job_title)):
            return {
                "error": True,
                "error_category": "validation",
                "message": "Employee job retrieval requires an employee or organization filter. Use sf__get_headcount for aggregate workforce questions.",
            }
        filters = []
        if user_id:
            filters.append(f"userId eq '{_escape_odata_string(user_id)}'")
        if company:
            filters.append(f"company eq '{_escape_odata_string(company)}'")
        if department:
            filters.append(f"department eq '{_escape_odata_string(department)}'")
        if business_unit:
            filters.append(f"businessUnit eq '{_escape_odata_string(business_unit)}'")
        if job_title:
            filters.append(f"substringof('{_escape_odata_string(job_title)}', jobTitle)")

        filter_str = " and ".join(filters) if filters else None
        select_fields = (
            "userId,startDate,seqNumber,company,businessUnit,department,division,"
            "jobTitle,jobCode,employeeClass,employmentType,eventReason,fte,hireDate,"
            "endDate,location"
        )
        requested_top = _bounded_top(top, maximum=100)
        params: Dict[str, Any] = {"$top": requested_top, "$select": select_fields, "$inlinecount": "allpages"}
        if as_of_date:
            params["asOfDate"] = as_of_date
        if filter_str:
            params["$filter"] = filter_str

        res = await self._request("GET", "EmpJob", params=params, executive_id=executive_id)
        if isinstance(res, dict) and res.get("error"):
            return res
        results = res.get("results", []) if isinstance(res, dict) else []
        count = res.get("__count", len(results)) if isinstance(res, dict) else len(results)
        return {
            "total": int(count),
            "rows_returned": len(results),
            "complete": len(results) == int(count),
            "partial": len(results) < int(count),
            "results": results,
            "type": "EmpJob",
            "rbp_trimmed": True,
            "source": "SAP SuccessFactors · EmpJob",
            "access_context": "configured_service_account",
            "cache": res.get("_cache", {}),
        }

    async def drilldown_employees(
        self,
        department: Optional[str] = "Unassigned",
        company: Optional[str] = None,
        business_unit: Optional[str] = None,
        as_of_date: Optional[str] = None,
        field_profile: str = "workforce_drilldown",
        page: int = 1,
        page_size: int = 20,
        max_results: int = 100,
        user_object_id: Optional[str] = None,
        user_email: Optional[str] = None,
        user_roles: Optional[List[str]] = None,
        executive_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Drill down into employee-level details for a specific group/department governed by Dataverse disclosure policy."""
        from .policy_engine import get_policy_engine
        from .cache import get_multi_layer_cache
        from .background_logger import get_background_logger
        from .dataverse_audit import DataverseAuditRecord, RECORD_TYPE_POLICY_DECISION

        engine = get_policy_engine()
        cache_mgr = get_multi_layer_cache()
        bg_logger = get_background_logger()

        # 1. Evaluate active policy
        decision = await engine.evaluate_drilldown_policy(
            user_object_id=user_object_id,
            user_email=user_email,
            user_roles=user_roles,
            group_size=1,
            field_profile=field_profile,
        )

        # Log policy decision in background
        bg_logger.enqueue(DataverseAuditRecord(
            record_type=RECORD_TYPE_POLICY_DECISION,
            user_object_id=user_object_id or "",
            user_email=user_email or "",
            policy_id=decision.policy_id,
            policy_version=decision.policy_version,
            policy_decision="ALLOWED" if decision.allowed else "DENIED",
            released_fields=decision.allowed_fields,
            message_summary=f"Policy decision for {department or 'All'}: {'ALLOWED' if decision.allowed else 'DENIED'} - {decision.reason}",
            content_classification="INTERNAL_GOVERNANCE",
        ))

        if not decision.allowed:
            return {
                "error": True,
                "error_category": "authorization",
                "message": f"Employee-level drill-down is restricted: {decision.reason}",
                "policy_version": decision.policy_version,
                "policy_id": decision.policy_id,
            }

        # 2. Check Layer 4 Drill-Down Cache
        cache_key = cache_mgr.build_drilldown_cache_key(
            environment=getattr(self.settings, "environment", "Production"),
            user_object_id=user_object_id or "anon",
            policy_id=decision.policy_id,
            policy_version=decision.policy_version,
            field_profile=field_profile,
            department=department,
            top=page_size,
            page=page,
        )

        async def load_drilldown() -> Dict[str, Any]:
            # Read department mapping
            dept_res = await self._fetch_all("FODepartment", select="externalCode,name", executive_id=executive_id)
            dept_map = {}
            if isinstance(dept_res, dict) and not dept_res.get("error"):
                dept_map = {
                    str(r.get("externalCode")): str(r.get("name"))
                    for r in dept_res.get("results", [])
                    if r.get("externalCode") and r.get("name")
                }

            # Fetch EmpJob records
            emp_filters = []
            if company:
                emp_filters.append(f"company eq '{_escape_odata_string(company)}'")
            if business_unit:
                emp_filters.append(f"businessUnit eq '{_escape_odata_string(business_unit)}'")

            is_unassigned = (department or "").strip().lower() in ("unassigned", "unmapped department", "none", "null")
            if department and not is_unassigned:
                matching_codes = [code for code, name in dept_map.items() if name.lower() == department.strip().lower() or code.lower() == department.strip().lower()]
                if matching_codes:
                    emp_filters.append(f"department eq '{_escape_odata_string(matching_codes[0])}'")
                else:
                    emp_filters.append(f"department eq '{_escape_odata_string(department)}'")

            jobs_res = await self._fetch_all(
                "EmpJob",
                select="userId,startDate,department,businessUnit,division,jobTitle,location,employmentStatus,hireDate,customString1",
                filter_str=" and ".join(emp_filters) if emp_filters else None,
                as_of_date=as_of_date,
                executive_id=executive_id,
            )
            if isinstance(jobs_res, dict) and jobs_res.get("error"):
                return jobs_res

            raw_jobs = jobs_res.get("results", []) if isinstance(jobs_res, dict) else []
            
            matched_jobs: Dict[str, Dict[str, Any]] = {}
            for j in raw_jobs:
                uid = str(j.get("userId") or "")
                if not uid:
                    continue
                dept_code = str(j.get("department") or "")
                dept_name = dept_map.get(dept_code) or ("Unassigned" if not dept_code else "Unmapped department")
                
                if is_unassigned:
                    if dept_name == "Unassigned" or not dept_code or dept_code.lower() in ("none", "null", "0", ""):
                        matched_jobs.setdefault(uid, {**j, "resolved_department": "Unassigned"})
                else:
                    matched_jobs.setdefault(uid, {**j, "resolved_department": dept_name})

            total_matched = len(matched_jobs)
            effective_cap = min(max_results, decision.max_rows)
            sorted_uids = sorted(matched_jobs.keys())[:effective_cap]

            effective_page_size = min(page_size, 20)
            total_pages = max(1, (len(sorted_uids) + effective_page_size - 1) // effective_page_size)
            current_page = max(1, min(page, total_pages))
            start_idx = (current_page - 1) * effective_page_size
            end_idx = start_idx + effective_page_size
            paged_uids = sorted_uids[start_idx:end_idx]

            enriched_records = []
            for uid in paged_uids:
                job_data = matched_jobs[uid]
                
                user_res = await self._request("GET", f"User('{_escape_odata_string(uid)}')", params={"$select": "userId,firstName,lastName,displayName,title,department,city,email,custom01"}, executive_id=executive_id)
                user_obj = user_res if isinstance(user_res, dict) and not user_res.get("error") else {}
                
                pers_res = await self._request("GET", f"PerPersonal('{_escape_odata_string(uid)}')", params={"$select": "personIdExternal,nationality,dateOfBirth"}, executive_id=executive_id)
                pers_obj = pers_res if isinstance(pers_res, dict) and not pers_res.get("error") else {}

                emp_res = await self._request("GET", f"EmpEmployment(personIdExternal='{_escape_odata_string(uid)}',userId='{_escape_odata_string(uid)}')", params={"$select": "startDate,origHireDate"}, executive_id=executive_id)
                emp_obj = emp_res if isinstance(emp_res, dict) and not emp_res.get("error") else {}

                merged = {
                    "userId": uid,
                    "name": user_obj.get("displayName") or f"{user_obj.get('firstName', '')} {user_obj.get('lastName', '')}".strip() or f"Employee {uid}",
                    "nationality": pers_obj.get("nationality"),
                    "dateOfBirth": pers_obj.get("dateOfBirth"),
                    "hireDate": emp_obj.get("origHireDate") or emp_obj.get("startDate") or job_data.get("hireDate") or job_data.get("startDate"),
                    "department": job_data.get("resolved_department", "Unassigned"),
                    "businessUnit": job_data.get("businessUnit"),
                    "division": job_data.get("division"),
                    "jobTitle": user_obj.get("title") or job_data.get("jobTitle"),
                    "location": job_data.get("location") or user_obj.get("city"),
                    "employmentStatus": job_data.get("employmentStatus", "Active"),
                    "recruited_by": job_data.get("customString1") or user_obj.get("custom01") or "Talent Acquisition",
                }
                enriched_records.append(merged)

            sanitized_employees = engine.apply_field_redaction(enriched_records, decision)

            return {
                "type": "WorkforceDrilldown",
                "department": department or "All",
                "total_matched": total_matched,
                "capped_total": len(sorted_uids),
                "page": current_page,
                "page_size": len(sanitized_employees),
                "total_pages": total_pages,
                "has_next_page": current_page < total_pages,
                "next_page": current_page + 1 if current_page < total_pages else None,
                "policy_id": decision.policy_id,
                "policy_version": decision.policy_version,
                "released_fields": decision.allowed_fields,
                "employees": sanitized_employees,
                "source": "SAP SuccessFactors · EmpJob / User / PerPersonal",
            }

        result, info = await cache_mgr.drilldown_cache.get_or_load(
            cache_key,
            load_drilldown,
            cacheable=lambda val: isinstance(val, dict) and not val.get("error"),
        )
        if isinstance(result, dict):
            result["cache"] = info.as_dict()
        return result

    async def aggregate_headcount_by_department(
        self,
        company: Optional[str] = None,
        department: Optional[str] = None,
        business_unit: Optional[str] = None,
        as_of_date: Optional[str] = None,
        executive_id: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """Return a permission-scoped cached headcount aggregation."""
        key = hashlib.sha256(json.dumps({
            "operation": "headcount_by_department",
            "baseUrl": self.base_url,
            "executiveId": executive_id or "configured-service-account",
            "company": company,
            "department": department,
            "businessUnit": business_unit,
            "asOfDate": as_of_date,
        }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

        async def load() -> Dict[str, Any]:
            return await self._aggregate_headcount_by_department_uncached(
                company=company, department=department, business_unit=business_unit,
                as_of_date=as_of_date, executive_id=executive_id,
                progress_callback=progress_callback,
            )

        result, info = await self._aggregate_cache.get_or_load(
            key, load, cacheable=lambda value: isinstance(value, dict) and not value.get("error"),
        )
        if progress_callback and info.status == "hit":
            await progress_callback(0.90, "Using fresh cached SuccessFactors aggregation")
        if isinstance(result, dict):
            result["aggregate_cache"] = info.as_dict()
        return result

    async def _aggregate_headcount_by_department_uncached(
        self,
        company: Optional[str] = None,
        department: Optional[str] = None,
        business_unit: Optional[str] = None,
        as_of_date: Optional[str] = None,
        executive_id: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """Aggregate the complete RBP-visible EmpJob population by department name."""

        async def report(progress: float, message: str) -> None:
            if progress_callback:
                await progress_callback(progress, message)

        await report(0.10, "Reading SuccessFactors department descriptions")
        department_res = await self._fetch_all(
            "FODepartment",
            select="externalCode,name,status",
            executive_id=executive_id,
        )
        if department_res.get("error"):
            return department_res
        department_names = {
            str(row.get("externalCode")): str(row.get("name"))
            for row in department_res.get("results", [])
            if row.get("externalCode") and row.get("name")
        }

        filters = []
        if company:
            filters.append(f"company eq '{_escape_odata_string(company)}'")
        if department:
            filters.append(f"department eq '{_escape_odata_string(department)}'")
        if business_unit:
            filters.append(f"businessUnit eq '{_escape_odata_string(business_unit)}'")

        await report(0.25, "Reading all role-visible SuccessFactors workforce records")
        job_res = await self._fetch_all(
            "EmpJob",
            select="userId,department",
            filter_str=" and ".join(filters) if filters else None,
            as_of_date=as_of_date,
            executive_id=executive_id,
        )
        if job_res.get("error"):
            return job_res
        rows = job_res.get("results", [])
        distinct_jobs: Dict[str, Dict[str, Any]] = {}
        missing_user_id_rows = 0
        for row in rows:
            user_id = str(row.get("userId") or "")
            if not user_id:
                missing_user_id_rows += 1
                continue
            distinct_jobs.setdefault(user_id, row)

        active_res = await self._active_user_ids(executive_id=executive_id)
        active_ids = active_res.get("ids", set()) if not active_res.get("error") else set()
        warnings: List[str] = []
        if active_res.get("error"):
            warnings.append(str(active_res.get("message")))
        if missing_user_id_rows:
            warnings.append(f"Excluded {missing_user_id_rows} EmpJob rows without a userId.")

        counts: Dict[str, int] = {}
        active_counts: Dict[str, int] = {}
        for user_id, row in distinct_jobs.items():
            code = row.get("department")
            name = department_names.get(str(code)) if code else None
            label = name or ("Unassigned" if not code else "Unmapped department")
            counts[label] = counts.get(label, 0) + 1
            if user_id in active_ids:
                active_counts[label] = active_counts.get(label, 0) + 1

        total = len(distinct_jobs)
        active_total = len(set(distinct_jobs).intersection(active_ids)) if active_ids else None

        await report(0.82, "Aggregating department totals and percentages")
        breakdown = [
            {
                "department": name,
                "headcount": count,
                "percentage": round((count / total) * 100, 1) if total else 0.0,
            }
            for name, count in counts.items()
        ]
        breakdown.sort(key=lambda item: (-item["headcount"], item["department"]))
        active_breakdown = [
            {
                "department": name,
                "headcount": count,
                "percentage": round((count / active_total) * 100, 1) if active_total else 0.0,
            }
            for name, count in active_counts.items()
        ]
        active_breakdown.sort(key=lambda item: (-item["headcount"], item["department"]))
        chart_bars = breakdown[:10]

        await report(0.94, "Compiling the executive visualization and source details")
        return {
            "type": "Headcount",
            "total_headcount": total,
            "active_headcount": active_total,
            "rows_evaluated": len(rows),
            "distinct_employees_evaluated": total,
            "department_count": len(breakdown),
            "department_breakdown": breakdown,
            "active_department_breakdown": active_breakdown,
            "chart_bars": chart_bars,
            "aggregation_complete": bool(job_res.get("complete")) and not missing_user_id_rows,
            "reconciliation": {
                "department_total": sum(item["headcount"] for item in breakdown),
                "headline_total": total,
                "passed": sum(item["headcount"] for item in breakdown) == total,
            },
            "population_definition": "Distinct current-effective, RBP-visible EmpJob employees",
            "active_population_definition": (
                "Distinct current-effective EmpJob employees whose User.status is in the configured active-status set"
            ),
            "rule_version": self.settings.sf_metric_rule_version,
            "warnings": warnings,
            "filters": {
                "company": company,
                "department": department,
                "business_unit": business_unit,
                "as_of_date": as_of_date,
            },
            "visualization": {
                "type": "horizontal_bar_chart",
                "selection_reason": "Best for comparing ranked department headcounts with long department names.",
                "bars": chart_bars,
            },
            "source": "SAP SuccessFactors · EmpJob and FODepartment",
            "source_details": {
                "system": "SAP SuccessFactors",
                "environment": "UAE Preview test tenant",
                "entities": ["EmpJob", "FODepartment"],
                "scope": "Distinct current-effective, role-permission-visible population",
            },
            "access_context": "configured_service_account",
            "processing_stages": [
                "Connected to SAP SuccessFactors",
                "Read department descriptions",
                "Read all role-visible workforce records",
                "Aggregated department totals",
                "Compiled visualization and sources",
            ],
            "cache": {
                "departments": department_res.get("page_caches", []),
                "jobs": job_res.get("page_caches", []),
                "active_users": active_res.get("cache", []),
            },
        }

    async def aggregate_joiners(
        self,
        start_date: str,
        end_date: str,
        group_by: str = "month",
        company: Optional[str] = None,
        executive_id: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """Return a permission-scoped cached joiner aggregation."""
        key = hashlib.sha256(json.dumps({
            "operation": "joiners",
            "baseUrl": self.base_url,
            "executiveId": executive_id or "configured-service-account",
            "startDate": start_date,
            "endDate": end_date,
            "groupBy": group_by,
            "company": company,
        }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

        async def load() -> Dict[str, Any]:
            return await self._aggregate_joiners_uncached(
                start_date=start_date, end_date=end_date, group_by=group_by,
                company=company, executive_id=executive_id,
                progress_callback=progress_callback,
            )

        result, info = await self._aggregate_cache.get_or_load(
            key, load, cacheable=lambda value: isinstance(value, dict) and not value.get("error"),
        )
        if progress_callback and info.status == "hit":
            await progress_callback(0.90, "Using fresh cached SuccessFactors joiner analysis")
        if isinstance(result, dict):
            result["aggregate_cache"] = info.as_dict()
        return result

    async def _aggregate_joiners_uncached(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        group_by: str = "month",
        company: Optional[str] = None,
        executive_id: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """Return complete, distinct-employee hire counts for an inclusive ISO date range."""
        start_date = start_date or f"{date.today().year}-01-01"
        end_date = end_date or date.today().isoformat()
        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
        except ValueError:
            return {"error": True, "message": "start_date and end_date must use YYYY-MM-DD."}
        if end < start:
            return {"error": True, "message": "end_date must be on or after start_date."}
        if group_by not in {"day", "week", "month", "department"}:
            return {"error": True, "message": "group_by must be day, week, month, or department."}

        async def report(progress: float, message: str) -> None:
            if progress_callback:
                await progress_callback(progress, message)

        await report(0.10, "Reading SuccessFactors department descriptions")
        department_res = await self._fetch_all(
            "FODepartment",
            select="externalCode,name,status",
            executive_id=executive_id,
        )
        if not isinstance(department_res, dict) or department_res.get("error"):
            return department_res
        department_names = {
            str(row.get("externalCode")): str(row.get("name"))
            for row in department_res.get("results", [])
            if row.get("externalCode") and row.get("name")
        }

        filters = [
            f"hireDate ge datetime'{start_date}T00:00:00'",
            f"hireDate lt datetime'{(end.fromordinal(end.toordinal() + 1)).isoformat()}T00:00:00'",
        ]
        if company:
            filters.append(f"company eq '{_escape_odata_string(company)}'")

        hires: Dict[str, Dict[str, Any]] = {}
        await report(0.20, "Reading complete SuccessFactors hire records")
        hire_res = await self._fetch_all(
            "EmpJob",
            select="userId,hireDate,department",
            filter_str=" and ".join(filters),
            executive_id=executive_id,
        )
        if hire_res.get("error"):
            return hire_res
        for row in hire_res.get("results", []):
            user_id = str(row.get("userId") or "")
            if user_id and user_id not in hires:
                hires[user_id] = row
        rows_evaluated = int(hire_res.get("rows_returned", 0))
        total = int(hire_res.get("total_available", rows_evaluated))
        page_caches = list(hire_res.get("page_caches", []))

        counts: Dict[str, int] = {}
        for row in hires.values():
            hired = _parse_sf_date(row.get("hireDate"))
            if group_by == "department":
                code = row.get("department")
                bucket = department_names.get(str(code)) if code else None
                bucket = bucket or ("Unassigned" if not code else "Unmapped department")
            elif not hired:
                bucket = "Unknown date"
            elif group_by == "day":
                bucket = hired.isoformat()
            elif group_by == "week":
                year, week, _ = hired.isocalendar()
                bucket = f"{year}-W{week:02d}"
            else:
                bucket = hired.strftime("%Y-%m")
            counts[bucket] = counts.get(bucket, 0) + 1

        breakdown = [{"period" if group_by != "department" else "department": key, "joiners": value} for key, value in counts.items()]
        breakdown.sort(key=lambda item: (-item["joiners"], next(iter(item.values()))) if group_by == "department" else next(iter(item.values())))
        nationality_res = await self._nationality_map(executive_id=executive_id)
        uae_codes = _csv_codes(self.settings.sf_uae_nationality_codes)
        nationality_map = nationality_res.get("mapping", {}) if not nationality_res.get("error") else {}
        uae_joiners = sum(1 for user_id in hires if nationality_map.get(user_id) in uae_codes)
        missing_nationality = sum(1 for user_id in hires if not nationality_map.get(user_id))
        known_non_uae = len(hires) - uae_joiners - missing_nationality
        warnings = []
        if nationality_res.get("error"):
            warnings.append("Joiner nationality split is unavailable: " + str(nationality_res.get("message")))
        await report(0.90, "Compiling joiner trends and visualization")
        return {
            "type": "JoinerAnalytics",
            "total_joiners": len(hires),
            "rows_evaluated": rows_evaluated,
            "aggregation_complete": rows_evaluated == total,
            "start_date": start_date,
            "end_date": end_date,
            "group_by": group_by,
            "breakdown": breakdown,
            "uae_national_joiners": uae_joiners if not nationality_res.get("error") else None,
            "non_uae_national_joiners": known_non_uae if not nationality_res.get("error") else None,
            "missing_nationality_joiners": missing_nationality if not nationality_res.get("error") else None,
            "reconciliation": {
                "breakdown_total": sum(item["joiners"] for item in breakdown),
                "headline_total": len(hires),
                "passed": sum(item["joiners"] for item in breakdown) == len(hires),
            },
            "population_definition": "Distinct EmpJob employees with hireDate inside the inclusive reporting window",
            "hire_definition": "First distinct employee occurrence returned by the configured current-effective EmpJob view; rehire classification is not available",
            "rule_version": self.settings.sf_metric_rule_version,
            "warnings": warnings,
            "visualization": {"type": "horizontal_bar_chart" if group_by == "department" else "time_series", "data": breakdown},
            "source": "SAP SuccessFactors · EmpJob and FODepartment",
            "source_details": {"system": "SAP SuccessFactors", "environment": "UAE Preview test tenant", "entities": ["EmpJob", "FODepartment"]},
            "access_context": "configured_service_account",
            "cache": {
                "departments": department_res.get("_cache", {}),
                "pages": page_caches,
                "nationality": nationality_res.get("cache", []),
            },
        }

    # ── Leavers & Separations Analytics ─────────────────────────────────────────

    async def aggregate_leavers(
        self,
        start_date: str,
        end_date: str,
        group_by: str = "department",
        company: Optional[str] = None,
        reason_type: Optional[str] = "all",
        executive_id: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """Return a permission-scoped cached leaver aggregation."""
        key = hashlib.sha256(json.dumps({
            "operation": "leavers",
            "baseUrl": self.base_url,
            "executiveId": executive_id or "configured-service-account",
            "startDate": start_date,
            "endDate": end_date,
            "groupBy": group_by,
            "company": company,
            "reasonType": reason_type,
        }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

        async def load() -> Dict[str, Any]:
            return await self._aggregate_leavers_uncached(
                start_date=start_date, end_date=end_date, group_by=group_by,
                company=company, reason_type=reason_type, executive_id=executive_id,
                progress_callback=progress_callback,
            )

        result, info = await self._aggregate_cache.get_or_load(
            key, load, cacheable=lambda value: isinstance(value, dict) and not value.get("error"),
        )
        if progress_callback and info.status == "hit":
            await progress_callback(0.90, "Using fresh cached SuccessFactors leaver analysis")
        if isinstance(result, dict):
            result["aggregate_cache"] = info.as_dict()
        return result

    async def _aggregate_leavers_uncached(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        group_by: str = "department",
        company: Optional[str] = None,
        reason_type: Optional[str] = "all",
        executive_id: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """Aggregate leavers and terminations across the organization."""
        start_date = start_date or f"{date.today().year}-01-01"
        end_date = end_date or date.today().isoformat()
        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
        except ValueError:
            return {"error": True, "message": "start_date and end_date must use YYYY-MM-DD."}
        if end < start:
            return {"error": True, "message": "end_date must be on or after start_date."}
        if group_by not in {"day", "week", "month", "department", "reason", "business_unit"}:
            return {"error": True, "message": "group_by must be day, week, month, department, reason, or business_unit."}

        async def report(progress: float, message: str) -> None:
            if progress_callback:
                await progress_callback(progress, message)

        if company:
            return {
                "error": True,
                "error_category": "unsupported_filter",
                "message": "Company-scoped leaver analytics requires an approved employment-to-job effective-date join, which is not configured.",
            }
        if reason_type not in (None, "all"):
            return {
                "error": True,
                "error_category": "unavailable_classification",
                "message": "Voluntary/involuntary filtering is unavailable because eventReason is not viewable to the configured SuccessFactors account.",
            }

        await report(0.20, "Reading complete SuccessFactors separation records")
        filter_str = (
            f"endDate ge datetime'{start_date}T00:00:00' and "
            f"endDate lt datetime'{(end.fromordinal(end.toordinal() + 1)).isoformat()}T00:00:00'"
        )
        res = await self._fetch_all(
            "EmpEmployment",
            select="userId,personIdExternal,endDate,lastDateWorked",
            filter_str=filter_str,
            executive_id=executive_id,
        )
        if res.get("error"):
            return res
        distinct: Dict[str, Dict[str, Any]] = {}
        for row in res.get("results", []):
            user_id = str(row.get("userId") or row.get("personIdExternal") or "")
            if user_id:
                distinct.setdefault(user_id, row)
        total_leavers = len(distinct)

        time_counts: Dict[str, int] = {}
        if group_by in {"day", "week", "month"}:
            for row in distinct.values():
                ended = _parse_sf_date(row.get("endDate"))
                if not ended:
                    bucket = "Unknown date"
                elif group_by == "day":
                    bucket = ended.isoformat()
                elif group_by == "week":
                    year, week, _ = ended.isocalendar()
                    bucket = f"{year}-W{week:02d}"
                else:
                    bucket = ended.strftime("%Y-%m")
                time_counts[bucket] = time_counts.get(bucket, 0) + 1
        breakdown_key = "period" if group_by in {"day", "week", "month"} else group_by
        if time_counts:
            breakdown = [{breakdown_key: key, "leavers": value} for key, value in sorted(time_counts.items())]
        else:
            breakdown = [{breakdown_key: "Unclassified", "leavers": total_leavers}] if total_leavers else []

        warnings = []
        if total_leavers:
            warnings.append(
                "Separation reason and organizational breakdowns are unavailable because the configured account cannot view termination eventReason or an approved effective-dated organization join."
            )

        await report(0.92, "Compiling leaver intelligence and visualization")
        return {
            "type": "LeaverAnalytics",
            "total_leavers": total_leavers,
            "voluntary_leavers": None,
            "involuntary_leavers": None,
            "unclassified_leavers": total_leavers,
            "voluntary_rate_pct": None,
            "start_date": start_date,
            "end_date": end_date,
            "group_by": group_by,
            "breakdown": breakdown,
            "reason_breakdown": ([{"reason": "Unclassified", "count": total_leavers, "category": "Unclassified"}] if total_leavers else []),
            "bu_breakdown": [],
            "top_separation_reason": None,
            "highest_attrition_bu": None,
            "aggregation_complete": bool(res.get("complete")),
            "reconciliation": {
                "breakdown_total": sum(item["leavers"] for item in breakdown),
                "headline_total": total_leavers,
                "passed": sum(item["leavers"] for item in breakdown) == total_leavers,
            },
            "population_definition": "Distinct RBP-visible EmpEmployment records whose endDate falls inside the inclusive reporting window",
            "rule_version": self.settings.sf_metric_rule_version,
            "warnings": warnings,
            "visualization": {
                "type": "horizontal_bar_chart",
                "selection_reason": "Shows verified separation volume for the requested time grouping.",
                "data": breakdown,
            },
            "source": "SAP SuccessFactors · EmpEmployment",
            "source_details": {
                "system": "SAP SuccessFactors",
                "environment": "UAE Preview test tenant",
                "entities": ["EmpEmployment"],
            },
            "access_context": "configured_service_account",
            "cache": {"pages": res.get("page_caches", [])},
        }

    # ── Attrition Rate & Mobility Analysis ─────────────────────────────────────

    async def aggregate_attrition(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        company: Optional[str] = None,
        business_unit: Optional[str] = None,
        executive_id: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """Calculate organizational and national attrition rates with drivers."""
        start_date = start_date or f"{date.today().year}-01-01"
        end_date = end_date or date.today().isoformat()
        key = hashlib.sha256(json.dumps({
            "operation": "attrition",
            "baseUrl": self.base_url,
            "executiveId": executive_id or "configured-service-account",
            "startDate": start_date,
            "endDate": end_date,
            "company": company,
            "businessUnit": business_unit,
        }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

        async def load() -> Dict[str, Any]:
            return await self._aggregate_attrition_uncached(
                start_date=start_date, end_date=end_date, company=company,
                business_unit=business_unit, executive_id=executive_id,
                progress_callback=progress_callback,
            )

        result, info = await self._aggregate_cache.get_or_load(
            key, load, cacheable=lambda value: isinstance(value, dict) and not value.get("error"),
        )
        if isinstance(result, dict):
            result["aggregate_cache"] = info.as_dict()
        return result

    async def _aggregate_attrition_uncached(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        company: Optional[str] = None,
        business_unit: Optional[str] = None,
        executive_id: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """Compute transparent period attrition against a verified active denominator."""
        start_date = start_date or "2026-01-01"
        end_date = end_date or date.today().isoformat()
        try:
            start = date.fromisoformat(start_date)
            end_date_value = date.fromisoformat(end_date)
        except ValueError:
            return {"error": True, "error_category": "validation", "message": "start_date and end_date must use YYYY-MM-DD."}
        if end_date_value < start:
            return {"error": True, "error_category": "validation", "message": "end_date must be on or after start_date."}
        headcount_res = await self.aggregate_headcount_by_department(company=company, business_unit=business_unit, executive_id=executive_id)
        if not isinstance(headcount_res, dict) or headcount_res.get("error"):
            return headcount_res if isinstance(headcount_res, dict) else {
                "error": True, "message": "Headcount denominator query failed."
            }
        denominator = headcount_res.get("active_headcount")
        if denominator is None:
            return {
                "error": True,
                "error_category": "missing_denominator",
                "message": "Active workforce denominator is unavailable; attrition was not calculated.",
            }

        leavers_res = await self.aggregate_leavers(start_date=start_date, end_date=end_date, company=company, executive_id=executive_id)
        if not isinstance(leavers_res, dict) or leavers_res.get("error"):
            return leavers_res if isinstance(leavers_res, dict) else {
                "error": True, "message": "Leaver numerator query failed."
            }
        total_leavers = int(leavers_res.get("total_leavers", 0))
        overall_attrition_rate = round((total_leavers / denominator) * 100, 2) if denominator else 0.0

        end = end_date_value
        separation_res = await self._fetch_all(
            "EmpEmployment",
            select="userId,personIdExternal,endDate",
            filter_str=(
                f"endDate ge datetime'{start_date}T00:00:00' and "
                f"endDate lt datetime'{(end.fromordinal(end.toordinal() + 1)).isoformat()}T00:00:00'"
            ),
            executive_id=executive_id,
        )
        nationality_res = await self._nationality_map(executive_id=executive_id)
        uae_codes = _csv_codes(self.settings.sf_uae_nationality_codes)
        nationality_map = nationality_res.get("mapping", {}) if not nationality_res.get("error") else {}
        leaver_ids = {
            str(row.get("userId") or row.get("personIdExternal"))
            for row in separation_res.get("results", [])
            if row.get("userId") or row.get("personIdExternal")
        } if not separation_res.get("error") else set()
        uae_national_leavers = sum(1 for user_id in leaver_ids if nationality_map.get(user_id) in uae_codes)

        population_res = await self._fetch_all(
            "EmpJob",
            select="userId",
            filter_str=" and ".join(
                item for item in (
                    f"company eq '{_escape_odata_string(company)}'" if company else "",
                    f"businessUnit eq '{_escape_odata_string(business_unit)}'" if business_unit else "",
                ) if item
            ) or None,
            executive_id=executive_id,
        )
        active_res = await self._active_user_ids(executive_id=executive_id)
        population_ids = {
            str(row.get("userId")) for row in population_res.get("results", []) if row.get("userId")
        } if not population_res.get("error") else set()
        active_ids = active_res.get("ids", set()) if not active_res.get("error") else set()
        active_population_ids = population_ids.intersection(active_ids)
        uae_national_headcount = sum(
            1 for user_id in active_population_ids if nationality_map.get(user_id) in uae_codes
        )
        nationality_available = not any(
            result.get("error") for result in (separation_res, nationality_res, population_res, active_res)
        )
        uae_attrition_rate = (
            round((uae_national_leavers / uae_national_headcount) * 100, 2)
            if nationality_available and uae_national_headcount else 0.0 if nationality_available else None
        )
        warnings = list(leavers_res.get("warnings", []))
        if not nationality_available:
            warnings.append("UAE National attrition is unavailable because one or more nationality/population queries failed.")

        return {
            "type": "AttritionAnalytics",
            "overall_attrition_rate_pct": overall_attrition_rate,
            "uae_national_attrition_rate_pct": uae_attrition_rate,
            "total_headcount_evaluated": denominator,
            "total_leavers": total_leavers,
            "voluntary_leavers": leavers_res.get("voluntary_leavers"),
            "involuntary_leavers": leavers_res.get("involuntary_leavers"),
            "unclassified_leavers": leavers_res.get("unclassified_leavers", total_leavers),
            "uae_national_leavers": uae_national_leavers if nationality_available else None,
            "uae_national_headcount": uae_national_headcount if nationality_available else None,
            "top_attrition_reason": None,
            "highest_attrition_bu": None,
            "bu_attrition_comparison": [],
            "formula": "period leavers / current active headcount × 100",
            "denominator_method": "Current effective active headcount at query time; not annualized",
            "population_definition": headcount_res.get("active_population_definition"),
            "rule_version": self.settings.sf_metric_rule_version,
            "warnings": warnings,
            "start_date": start_date,
            "end_date": end_date,
            "source": "SAP SuccessFactors · EmpJob, EmpEmployment and PerPersonal",
            "source_details": {
                "system": "SAP SuccessFactors",
                "environment": "UAE Preview test tenant",
                "entities": ["EmpJob", "EmpEmployment", "PerPersonal"],
            },
            "access_context": "configured_service_account",
        }

    # ── Joiners vs Leavers Net Growth Trend ────────────────────────────────────

    async def aggregate_joiners_leavers_trend(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        granularity: str = "month",
        company: Optional[str] = None,
        executive_id: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """Compute talent velocity, monthly joiners vs leavers, and net headcount growth."""
        today = date.today()
        start_date = start_date or f"{today.year}-01-01"
        end_date = end_date or today.isoformat()
        if granularity not in {"day", "week", "month"}:
            return {
                "error": True,
                "message": "granularity must be day, week, or month.",
                "error_category": "validation",
            }
        joiners_res = await self.aggregate_joiners(start_date=start_date, end_date=end_date, group_by=granularity, company=company, executive_id=executive_id, progress_callback=progress_callback)
        if not isinstance(joiners_res, dict) or joiners_res.get("error"):
            return joiners_res if isinstance(joiners_res, dict) else {
                "error": True, "message": "Joiner trend query failed."
            }
        total_joiners = int(joiners_res.get("total_joiners", 0))

        leavers_res = await self.aggregate_leavers(start_date=start_date, end_date=end_date, group_by=granularity, company=company, executive_id=executive_id, progress_callback=progress_callback)
        if not isinstance(leavers_res, dict) or leavers_res.get("error"):
            return leavers_res if isinstance(leavers_res, dict) else {
                "error": True, "message": "Leaver trend query failed."
            }
        total_leavers = int(leavers_res.get("total_leavers", 0))

        net_talent_growth = total_joiners - total_leavers
        growth_ratio = round(total_joiners / total_leavers, 2) if total_leavers else None

        periods: Dict[str, Dict[str, Any]] = {}
        for row in joiners_res.get("breakdown", []):
            period = str(row.get("period"))
            periods.setdefault(period, {"period": period, "joiners": 0, "leavers": 0})["joiners"] = int(row.get("joiners", 0))
        for row in leavers_res.get("breakdown", []):
            period = str(row.get("period"))
            periods.setdefault(period, {"period": period, "joiners": 0, "leavers": 0})["leavers"] = int(row.get("leavers", 0))
        trend = []
        for period in sorted(periods):
            row = periods[period]
            row["net_growth"] = row["joiners"] - row["leavers"]
            trend.append(row)

        end = date.fromisoformat(end_date)
        separation_res = await self._fetch_all(
            "EmpEmployment",
            select="userId,personIdExternal,endDate",
            filter_str=(
                f"endDate ge datetime'{start_date}T00:00:00' and "
                f"endDate lt datetime'{(end.fromordinal(end.toordinal() + 1)).isoformat()}T00:00:00'"
            ),
            executive_id=executive_id,
        )
        nationality_res = await self._nationality_map(executive_id=executive_id)
        uae_codes = _csv_codes(self.settings.sf_uae_nationality_codes)
        nationality_map = nationality_res.get("mapping", {}) if not nationality_res.get("error") else {}
        leaver_ids = {
            str(row.get("userId") or row.get("personIdExternal"))
            for row in separation_res.get("results", [])
            if row.get("userId") or row.get("personIdExternal")
        } if not separation_res.get("error") else set()
        nationality_available = not separation_res.get("error") and not nationality_res.get("error")
        uae_leavers = sum(1 for user_id in leaver_ids if nationality_map.get(user_id) in uae_codes)
        uae_joiners = joiners_res.get("uae_national_joiners")
        uae_net = (int(uae_joiners) - uae_leavers) if nationality_available and uae_joiners is not None else None
        warnings = list(joiners_res.get("warnings", [])) + list(leavers_res.get("warnings", []))

        return {
            "type": "JoinerLeaverTrend",
            "total_joiners": total_joiners,
            "total_leavers": total_leavers,
            "net_talent_growth": net_talent_growth,
            "talent_replacement_ratio": growth_ratio,
            "uae_national_joiners": uae_joiners,
            "uae_national_leavers": uae_leavers if nationality_available else None,
            "uae_national_net_growth": uae_net,
            "monthly_trend": trend,
            "hiring_velocity_status": "EXPANDING" if net_talent_growth > 0 else "CONTRACTING" if net_talent_growth < 0 else "STABLE",
            "reconciliation": {
                "period_joiners": sum(row["joiners"] for row in trend),
                "headline_joiners": total_joiners,
                "period_leavers": sum(row["leavers"] for row in trend),
                "headline_leavers": total_leavers,
                "passed": (
                    sum(row["joiners"] for row in trend) == total_joiners
                    and sum(row["leavers"] for row in trend) == total_leavers
                ),
            },
            "population_definition": "Distinct joiner and leaver populations using the same inclusive reporting window",
            "rule_version": self.settings.sf_metric_rule_version,
            "warnings": warnings,
            "start_date": start_date,
            "end_date": end_date,
            "granularity": granularity,
            "source": "SAP SuccessFactors · EmpJob, EmpEmployment and PerPersonal",
            "source_details": {
                "system": "SAP SuccessFactors",
                "environment": "UAE Preview test tenant",
                "entities": ["EmpJob", "EmpEmployment", self.settings.sf_nationality_entity],
            },
            "access_context": "configured_service_account",
        }

    async def get_emp_job(self, user_id: str, seq_num: int = 1, executive_id: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve specific Job Info record by userId and seqNumber."""
        params = {
            "$filter": f"userId eq '{_escape_odata_string(user_id)}' and seqNumber eq {int(seq_num)}",
            "$select": "userId,startDate,seqNumber,company,businessUnit,department,division,jobTitle,jobCode,employeeClass,employmentType,eventReason,fte,endDate,location",
        }
        res = await self._request("GET", "EmpJob", params=params, executive_id=executive_id)
        if isinstance(res, dict) and res.get("error"):
            return res
        results = res.get("results", []) if isinstance(res, dict) else []
        if not results:
            return {"error": True, "message": f"EmpJob record for user {user_id} not found."}
        return {
            "record": results[0],
            "type": "EmpJob",
            "source": "SAP SuccessFactors · EmpJob",
            "access_context": "configured_service_account",
            "cache": res.get("_cache", {}),
        }

    async def create_emp_job(self, emp_job_data: Dict[str, Any], executive_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a new Job Info record in EmpJob."""
        res = await self._request("POST", "EmpJob", json_data=emp_job_data, executive_id=executive_id)
        return res

    async def update_emp_job(self, user_id: str, start_date: str, seq_num: int, update_fields: Dict[str, Any], executive_id: Optional[str] = None) -> Dict[str, Any]:
        """Update an existing Job Info record."""
        endpoint = f"EmpJob(startDate=datetime'{_escape_odata_string(start_date)}',seqNumber={int(seq_num)}L,userId='{_escape_odata_string(user_id)}')"
        res = await self._request("MERGE", endpoint, json_data=update_fields, executive_id=executive_id)
        return res

    # ── Emiratisation Ratio KPI - Slide 4 Capability 02 (PDPL Enforced) ────────

    async def get_emiratisation_kpi(
        self,
        company: Optional[str] = None,
        as_of_date: Optional[str] = None,
        executive_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query Emiratisation ratio served as aggregate KPI only (PDPL Privacy Rule Enforced)."""
        target = float(self.settings.sf_emiratisation_target)
        company_filter = f"company eq '{_escape_odata_string(company)}'" if company else None
        population_res = await self._fetch_all(
            "EmpJob",
            select="userId",
            filter_str=company_filter,
            as_of_date=as_of_date,
            executive_id=executive_id,
        )
        if population_res.get("error"):
            return population_res
        nationality_res = await self._nationality_map(executive_id=executive_id)
        if nationality_res.get("error"):
            return nationality_res
        active_res = await self._active_user_ids(executive_id=executive_id)
        if active_res.get("error"):
            return active_res

        population_ids = {
            str(row.get("userId"))
            for row in population_res.get("results", [])
            if row.get("userId")
        }
        active_ids = population_ids.intersection(active_res.get("ids", set()))
        nationality_map = nationality_res.get("mapping", {})
        uae_codes = _csv_codes(self.settings.sf_uae_nationality_codes)
        if not uae_codes:
            return {
                "error": True,
                "error_category": "configuration",
                "message": "SF_UAE_NATIONALITY_CODES is not configured.",
            }

        def classify(ids: set[str]) -> Dict[str, int]:
            uae = sum(1 for user_id in ids if nationality_map.get(user_id) in uae_codes)
            missing = sum(1 for user_id in ids if not nationality_map.get(user_id))
            non_uae = len(ids) - uae - missing
            return {"eligible": len(ids), "uae": uae, "non_uae": non_uae, "missing": missing}

        total = classify(population_ids)
        active = classify(active_ids)
        if active["eligible"] < int(self.settings.sf_small_group_threshold):
            return {
                "error": True,
                "error_category": "privacy_suppression",
                "message": "Emiratisation result suppressed because the eligible active population is below the configured privacy threshold.",
            }
        total_rate = round((total["uae"] / total["eligible"]) * 100, 2) if total["eligible"] else 0.0
        active_rate = round((active["uae"] / active["eligible"]) * 100, 2) if active["eligible"] else 0.0
        target_gap = round(target - active_rate, 2)
        total_reconciles = total["uae"] + total["non_uae"] + total["missing"] == total["eligible"]
        active_reconciles = active["uae"] + active["non_uae"] + active["missing"] == active["eligible"]
        warnings = []
        if as_of_date:
            warnings.append("The EmpJob population uses the requested as-of date; User active status reflects the current directory status.")
        if total["missing"] or active["missing"]:
            warnings.append("Employees with blank or unmapped nationality are reported separately and are not classified as non-UAE.")

        return {
            "type": "EmiratisationKPI",
            "company": company or self.settings.sf_company_id,
            "population_scope": "active",
            "total_headcount": total["eligible"],
            "active_headcount": active["eligible"],
            "emirati_national_count": active["uae"],
            "uae_national_count": active["uae"],
            "non_uae_national_count": active["non_uae"],
            "missing_unclassified_nationality_count": active["missing"],
            "total_uae_national_count": total["uae"],
            "total_non_uae_national_count": total["non_uae"],
            "total_missing_unclassified_nationality_count": total["missing"],
            "emiratisation_ratio_percent": active_rate,
            "active_emiratisation_ratio_percent": active_rate,
            "total_emiratisation_ratio_percent": total_rate,
            "target_percent": target,
            "target_gap_percentage_points": target_gap,
            "target_gap_percent": target_gap,
            "target_compliance": "ON_TRACK" if active_rate >= target else "BELOW_TARGET",
            "reconciliation": {
                "active": {**active, "passed": active_reconciles},
                "total": {**total, "passed": total_reconciles},
                "passed": active_reconciles and total_reconciles,
            },
            "population_definition": "Distinct current-effective EmpJob employees intersected with configured active User.status values",
            "nationality_rule": {
                "entity": nationality_res.get("entity"),
                "person_id_field": nationality_res.get("person_id_field"),
                "nationality_field": nationality_res.get("nationality_field"),
                "uae_codes": sorted(uae_codes),
                "active_user_statuses": active_res.get("status_codes", []),
            },
            "rule_version": self.settings.sf_metric_rule_version,
            "as_of_date": as_of_date,
            "warnings": warnings,
            "pdpl_enforced": True,
            "source": f"SAP SuccessFactors · EmpJob, User and {nationality_res.get('entity')}",
            "source_details": {
                "entities": ["EmpJob", "User", nationality_res.get("entity")],
                "scope": "Aggregate, role-permission-visible population",
            },
            "access_context": "configured_service_account",
            "cache": {
                "population": population_res.get("page_caches", []),
                "active_users": active_res.get("cache", []),
                "nationality": nationality_res.get("cache", []),
            },
        }

    # ── Employee Directory (User) ─────────────────────────────────────────────

    async def list_users(
        self,
        query: Optional[str] = None,
        department: Optional[str] = None,
        status: Optional[str] = "active",
        top: int = 20,
        executive_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query user profiles in SuccessFactors under executive RBP permissions."""
        if not query and not department:
            return {
                "error": True,
                "error_category": "validation",
                "message": "Employee directory lookup requires a name, email, employee ID, or department filter.",
            }
        filters = []
        if query:
            escaped_query = _escape_odata_string(query)
            filters.append(f"(substringof('{escaped_query}', firstName) or substringof('{escaped_query}', lastName) or substringof('{escaped_query}', email) or substringof('{escaped_query}', userId))")
        if department:
            filters.append(f"department eq '{_escape_odata_string(department)}'")
        if status and status.lower() != "all":
            if status.lower() == "active":
                active_codes = sorted(_csv_codes(self.settings.sf_active_user_statuses))
                if not active_codes:
                    return {"error": True, "error_category": "configuration", "message": "SF_ACTIVE_USER_STATUSES is not configured."}
                filters.append("(" + " or ".join(f"status eq '{_escape_odata_string(code)}'" for code in active_codes) + ")")
            else:
                filters.append(f"status eq '{_escape_odata_string(status)}'")

        filter_str = " and ".join(filters) if filters else None
        select_fields = (
            "userId,displayName,email,title,department,division,location,status"
        )
        params: Dict[str, Any] = {"$top": _bounded_top(top, maximum=20), "$select": select_fields, "$inlinecount": "allpages"}
        if filter_str:
            params["$filter"] = filter_str

        res = await self._request("GET", "User", params=params, executive_id=executive_id)
        if isinstance(res, dict) and res.get("error"):
            return res
        results = res.get("results", []) if isinstance(res, dict) else []
        count = res.get("__count", len(results)) if isinstance(res, dict) else len(results)
        return {
            "total": int(count),
            "rows_returned": len(results),
            "complete": len(results) == int(count),
            "partial": len(results) < int(count),
            "results": results,
            "type": "User",
            "rbp_trimmed": True,
            "source": "SAP SuccessFactors · User",
            "access_context": "configured_service_account",
            "cache": res.get("_cache", {}),
        }

    async def get_user(self, user_id: str, executive_id: Optional[str] = None) -> Dict[str, Any]:
        """Get details for a specific user ID."""
        params = {
            "$filter": f"userId eq '{_escape_odata_string(user_id)}'",
            "$select": "userId,displayName,email,title,department,division,location,status",
        }
        res = await self._request("GET", "User", params=params, executive_id=executive_id)
        if isinstance(res, dict) and res.get("error"):
            return res
        results = res.get("results", []) if isinstance(res, dict) else []
        if not results:
            return {"error": True, "message": f"User {user_id} not found."}
        return {
            "user": results[0],
            "type": "User",
            "source": "SAP SuccessFactors · User",
            "access_context": "configured_service_account",
            "cache": res.get("_cache", {}),
        }

    async def update_user(self, user_id: str, update_data: Dict[str, Any], executive_id: Optional[str] = None) -> Dict[str, Any]:
        """Update user profile attributes."""
        endpoint = f"User('{_escape_odata_string(user_id)}')"
        res = await self._request("MERGE", endpoint, json_data=update_data, executive_id=executive_id)
        return res

    # ── Employment Info & Personal Info ───────────────────────────────────────

    async def get_employment_info(self, user_id: str, executive_id: Optional[str] = None) -> Dict[str, Any]:
        """Query employment details (EmpEmployment)."""
        params = {
            "$filter": f"userId eq '{_escape_odata_string(user_id)}'",
            "$select": "userId,startDate,originalStartDate,endDate,lastDateWorked,plannedEndDate",
        }
        res = await self._request("GET", "EmpEmployment", params=params, executive_id=executive_id)
        return res

    async def get_personal_info(self, person_id_external: str, executive_id: Optional[str] = None) -> Dict[str, Any]:
        """Query a minimal allowlist of personal information when explicitly enabled."""
        if not self.settings.enable_personal_info_tool:
            return {
                "error": True,
                "error_category": "policy",
                "message": "Personal-information retrieval is disabled for the executive agent.",
            }
        params = {
            "$filter": f"personIdExternal eq '{_escape_odata_string(person_id_external)}'",
            "$select": "personIdExternal,displayName,preferredName,nativePreferredLang",
        }
        res = await self._request("GET", "PerPersonal", params=params, executive_id=executive_id)
        return res

    # ── Master Org Data ───────────────────────────────────────────────────────

    async def list_org_units(self, entity_type: str = "FOCompany", top: int = 20, executive_id: Optional[str] = None) -> Dict[str, Any]:
        """List organization foundation objects (FOCompany, FOBusinessUnit, FODepartment, FODivision)."""
        valid_entities = {"FOCompany", "FOBusinessUnit", "FODepartment", "FODivision"}
        if entity_type not in valid_entities:
            return {"error": True, "message": f"Invalid org entity type. Must be one of {valid_entities}"}
        limit = _bounded_top(top)
        res = await self._request("GET", entity_type, params={"$top": limit, "$inlinecount": "allpages"}, executive_id=executive_id)
        if isinstance(res, dict) and res.get("error"):
            return res
        results = res.get("results", []) if isinstance(res, dict) else []
        count = res.get("__count", len(results)) if isinstance(res, dict) else len(results)
        return {
            "total": int(count),
            "rows_returned": len(results),
            "complete": len(results) == int(count),
            "partial": len(results) < int(count),
            "results": results,
            "type": entity_type,
            "source": f"SAP SuccessFactors · {entity_type}",
            "access_context": "configured_service_account",
            "cache": res.get("_cache", {}),
        }

    # ── Universal OData Query ─────────────────────────────────────────────────

    async def execute_odata(
        self,
        entity: str,
        select: Optional[str] = None,
        filter_str: Optional[str] = None,
        top: int = 20,
        expand: Optional[str] = None,
        executive_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute arbitrary OData v2 query against any SuccessFactors entity."""
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", entity):
            return {"error": True, "message": "Invalid SuccessFactors entity name."}
        params: Dict[str, Any] = {"$top": _bounded_top(top), "$inlinecount": "allpages"}
        if select:
            params["$select"] = select
        if filter_str:
            params["$filter"] = filter_str
        if expand:
            params["$expand"] = expand

        res = await self._request("GET", entity, params=params, executive_id=executive_id)
        if isinstance(res, dict) and res.get("error"):
            return res
        results = res.get("results", []) if isinstance(res, dict) else []
        count = res.get("__count", len(results)) if isinstance(res, dict) else len(results)
        return {
            "total": int(count),
            "results": results,
            "type": entity,
            "source": f"SAP SuccessFactors · {entity}",
            "access_context": "configured_service_account",
            "cache": res.get("_cache", {}),
        }
