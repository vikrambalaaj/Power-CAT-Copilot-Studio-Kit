"""SAP SuccessFactors OData v2 API client — authentication, HTTP requests, Delegated Identity & RBP trimming."""
from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

from .successfactors_settings import get_settings
from shared_mcp.logger import get_logger

log = get_logger("sf_hcm")


def _escape_odata_string(value: str) -> str:
    """Escape a string literal according to OData v2 quoting rules."""
    return value.replace("'", "''")


def _bounded_top(value: int, maximum: int = 1000) -> int:
    return max(1, min(int(value), maximum))


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
        queryParams = params or {}
        if "$format" not in queryParams:
            queryParams["$format"] = "json"

        log.debug("sf_request", method=method, url=url, executive_id=bool(executive_id))

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.request(
                    method,
                    url,
                    headers=headers,
                    params=queryParams,
                    json=json_data,
                )
                if resp.status_code >= 400:
                    log.error("sf_api_error", status=resp.status_code)
                    return {
                        "error": True,
                        "status": resp.status_code,
                        "message": f"SuccessFactors API Error {resp.status_code}: {resp.text[:500]}",
                    }
                if not resp.content:
                    return {"success": True}
                res_data = resp.json()
                if "d" in res_data:
                    return res_data["d"]
                return res_data
        except Exception as exc:
            log.error("sf_client_exception", error=str(exc))
            return {
                "error": True,
                "message": f"Connection error to SuccessFactors API: {str(exc)}",
            }

    # ── Headcount & Position Count (EmpJob) - Slide 4 Capability 01 ───────────

    async def list_emp_jobs(
        self,
        user_id: Optional[str] = None,
        company: Optional[str] = None,
        department: Optional[str] = None,
        business_unit: Optional[str] = None,
        job_title: Optional[str] = None,
        top: int = 20,
        executive_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query headcount & position count (EmpJob), trimmed by SuccessFactors Role-Based Permissions (RBP)."""
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
            "userId,startDate,seqNum,company,businessUnit,department,division,"
            "jobTitle,jobCode,employeeClass,employmentType,eventReason,fte,hireDate,"
            "endDate,location,payGrade,managerId"
        )
        params: Dict[str, Any] = {"$top": _bounded_top(top), "$select": select_fields, "$inlinecount": "allpages"}
        if filter_str:
            params["$filter"] = filter_str

        res = await self._request("GET", "EmpJob", params=params, executive_id=executive_id)
        if isinstance(res, dict) and res.get("error"):
            return res
        results = res.get("results", []) if isinstance(res, dict) else []
        count = res.get("__count", len(results)) if isinstance(res, dict) else len(results)
        return {
            "total": int(count),
            "results": results,
            "type": "EmpJob",
            "rbp_trimmed": True,
            "source": "SAP SuccessFactors · EmpJob",
            "access_context": "configured_service_account"
        }

    async def get_emp_job(self, user_id: str, seq_num: int = 1, executive_id: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve specific Job Info record by userId and seqNum."""
        params = {"$filter": f"userId eq '{_escape_odata_string(user_id)}' and seqNum eq {int(seq_num)}"}
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
            "access_context": "configured_service_account"
        }

    async def create_emp_job(self, emp_job_data: Dict[str, Any], executive_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a new Job Info record in EmpJob."""
        res = await self._request("POST", "EmpJob", json_data=emp_job_data, executive_id=executive_id)
        return res

    async def update_emp_job(self, user_id: str, start_date: str, seq_num: int, update_fields: Dict[str, Any], executive_id: Optional[str] = None) -> Dict[str, Any]:
        """Update an existing Job Info record."""
        endpoint = f"EmpJob(seqDate=datetime'{_escape_odata_string(start_date)}',seqNum={int(seq_num)}L,userId='{_escape_odata_string(user_id)}')"
        res = await self._request("MERGE", endpoint, json_data=update_fields, executive_id=executive_id)
        return res

    # ── Emiratisation Ratio KPI - Slide 4 Capability 02 (PDPL Enforced) ────────

    async def get_emiratisation_kpi(self, company: Optional[str] = None, executive_id: Optional[str] = None) -> Dict[str, Any]:
        """Query Emiratisation ratio served as aggregate KPI only (PDPL Privacy Rule Enforced)."""
        if not self.settings.sf_emirati_filter.strip():
            return {
                "error": True,
                "message": "SF_EMIRATI_FILTER must be configured with the tenant-specific nationality filter.",
            }

        company_filter = f"company eq '{_escape_odata_string(company)}'" if company else ""
        total_params: Dict[str, Any] = {"$top": 1, "$select": "userId", "$inlinecount": "allpages"}
        if company_filter:
            total_params["$filter"] = company_filter
        total_res = await self._request("GET", "EmpJob", params=total_params, executive_id=executive_id)
        if not isinstance(total_res, dict) or total_res.get("error"):
            return total_res

        emirati_filter = self.settings.sf_emirati_filter.strip()
        combined_filter = f"({company_filter}) and ({emirati_filter})" if company_filter else emirati_filter
        emirati_res = await self._request(
            "GET",
            "EmpJob",
            params={"$top": 1, "$select": "userId", "$inlinecount": "allpages", "$filter": combined_filter},
            executive_id=executive_id,
        )
        if not isinstance(emirati_res, dict) or emirati_res.get("error"):
            return emirati_res

        total_headcount = int(total_res.get("__count", len(total_res.get("results", []))))
        emirati_count = int(emirati_res.get("__count", len(emirati_res.get("results", []))))
        emiratisation_rate = round((emirati_count / total_headcount) * 100, 1) if total_headcount else 0.0
        target = float(self.settings.sf_emiratisation_target)

        return {
            "type": "EmiratisationKPI",
            "company": company or self.settings.sf_company_id,
            "total_headcount": total_headcount,
            "emirati_national_count": emirati_count,
            "emiratisation_ratio_percent": emiratisation_rate,
            "target_percent": target,
            "target_compliance": "ON_TRACK" if emiratisation_rate >= target else "BELOW_TARGET",
            "pdpl_enforced": True,
            "source": "SAP SuccessFactors · EmpJob",
            "access_context": "configured_service_account"
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
        filters = []
        if query:
            escaped_query = _escape_odata_string(query)
            filters.append(f"(substringof('{escaped_query}', firstName) or substringof('{escaped_query}', lastName) or substringof('{escaped_query}', email) or substringof('{escaped_query}', userId))")
        if department:
            filters.append(f"department eq '{_escape_odata_string(department)}'")
        if status and status.lower() != "all":
            filters.append(f"status eq '{_escape_odata_string(status)}'")

        filter_str = " and ".join(filters) if filters else None
        select_fields = (
            "userId,username,firstName,lastName,email,title,department,division,"
            "location,status,managerId,city,country,timeZone"
        )
        params: Dict[str, Any] = {"$top": _bounded_top(top), "$select": select_fields, "$inlinecount": "allpages"}
        if filter_str:
            params["$filter"] = filter_str

        res = await self._request("GET", "User", params=params, executive_id=executive_id)
        if isinstance(res, dict) and res.get("error"):
            return res
        results = res.get("results", []) if isinstance(res, dict) else []
        count = res.get("__count", len(results)) if isinstance(res, dict) else len(results)
        return {
            "total": int(count),
            "results": results,
            "type": "User",
            "rbp_trimmed": True,
            "source": "SAP SuccessFactors · User",
            "access_context": "configured_service_account"
        }

    async def get_user(self, user_id: str, executive_id: Optional[str] = None) -> Dict[str, Any]:
        """Get details for a specific user ID."""
        params = {"$filter": f"userId eq '{_escape_odata_string(user_id)}'"}
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
            "access_context": "configured_service_account"
        }

    async def update_user(self, user_id: str, update_data: Dict[str, Any], executive_id: Optional[str] = None) -> Dict[str, Any]:
        """Update user profile attributes."""
        endpoint = f"User('{_escape_odata_string(user_id)}')"
        res = await self._request("MERGE", endpoint, json_data=update_data, executive_id=executive_id)
        return res

    # ── Employment Info & Personal Info ───────────────────────────────────────

    async def get_employment_info(self, user_id: str, executive_id: Optional[str] = None) -> Dict[str, Any]:
        """Query employment details (EmpEmployment)."""
        params = {"$filter": f"userId eq '{_escape_odata_string(user_id)}'"}
        res = await self._request("GET", "EmpEmployment", params=params, executive_id=executive_id)
        return res

    async def get_personal_info(self, person_id_external: str, executive_id: Optional[str] = None) -> Dict[str, Any]:
        """Query personal information (PerPersonal)."""
        params = {"$filter": f"personIdExternal eq '{_escape_odata_string(person_id_external)}'"}
        res = await self._request("GET", "PerPersonal", params=params, executive_id=executive_id)
        return res

    # ── Master Org Data ───────────────────────────────────────────────────────

    async def list_org_units(self, entity_type: str = "FOCompany", top: int = 20, executive_id: Optional[str] = None) -> Dict[str, Any]:
        """List organization foundation objects (FOCompany, FOBusinessUnit, FODepartment, FODivision)."""
        valid_entities = {"FOCompany", "FOBusinessUnit", "FODepartment", "FODivision"}
        if entity_type not in valid_entities:
            return {"error": True, "message": f"Invalid org entity type. Must be one of {valid_entities}"}
        params = {"$top": _bounded_top(top), "$inlinecount": "allpages"}
        res = await self._request("GET", entity_type, params=params, executive_id=executive_id)
        if isinstance(res, dict) and res.get("error"):
            return res
        results = res.get("results", []) if isinstance(res, dict) else []
        count = res.get("__count", len(results)) if isinstance(res, dict) else len(results)
        return {
            "total": int(count),
            "results": results,
            "type": entity_type,
            "source": f"SAP SuccessFactors · {entity_type}",
            "access_context": "configured_service_account"
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
            "access_context": "configured_service_account"
        }
