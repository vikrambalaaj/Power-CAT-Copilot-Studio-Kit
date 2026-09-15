"""Velora Dataverse Disclosure Policy Engine.

Enforces field-level and row-level disclosure rules, source field transformations
(age buckets, length of service, nationality mapping), role checks, and permanent
prohibitions before data leaves the SuccessFactors layer.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from .dataverse_audit import get_dataverse_client
from shared_mcp.logger import get_logger

log = get_logger("policy_engine")

# Permanently prohibited fields across all profiles and states
PERMANENTLY_PROHIBITED_FIELDS: Set[str] = {
    "dateofbirth",
    "dob",
    "bankaccountnumber",
    "bank_account",
    "iban",
    "nationalid",
    "national_id",
    "passportnumber",
    "passport_number",
    "personalemail",
    "personal_email",
    "homeaddress",
    "home_address",
    "ssn",
    "socialsecuritynumber",
    "basesalary",
    "salary",
    "compensation",
    "bonus",
    "medicalhistory",
    "medical_info",
    "password",
    "passwordhash",
}

# Standard Country / Nationality Mappings
COUNTRY_CODE_MAP: Dict[str, str] = {
    "ARE": "United Arab Emirates",
    "UAE": "United Arab Emirates",
    "SAU": "Saudi Arabia",
    "KSA": "Saudi Arabia",
    "OMN": "Oman",
    "KWT": "Kuwait",
    "BHR": "Bahrain",
    "QAT": "Qatar",
    "EGY": "Egypt",
    "JOR": "Jordan",
    "LBN": "Lebanon",
    "IND": "India",
    "PAK": "Pakistan",
    "PHL": "Philippines",
    "GBR": "United Kingdom",
    "UK": "United Kingdom",
    "USA": "United States",
    "US": "United States",
    "CAN": "Canada",
    "AUS": "Australia",
    "DEU": "Germany",
    "FRA": "France",
    "SGP": "Singapore",
}

PROFILE_BASIC: List[str] = ["userId", "name", "country"]
PROFILE_WORKFORCE_DRILLDOWN: List[str] = [
    "userId", "name", "email", "jobTitle", "department", "division", "businessUnit",
    "location", "country", "gender", "age", "age_group", "joined_date",
    "tenure", "length_of_service", "employmentStatus", "recruited_by"
]


def _parse_date_input(val: Optional[Any]) -> Optional[date]:
    """Safely parse various date formats (date, datetime, OData /Date(...)/, ISO string)."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        val_str = val.strip()
        if not val_str or val_str.lower() in ("null", "none", "—", ""):
            return None
        match_ms = re.search(r"/Date\((\d+)\)/", val_str)
        if match_ms:
            try:
                return datetime.fromtimestamp(int(match_ms.group(1)) / 1000, tz=timezone.utc).date()
            except Exception:
                pass
        try:
            return datetime.strptime(val_str[:10], "%Y-%m-%d").date()
        except Exception:
            pass
    return None


def calculate_age(dob: Optional[Any], as_of: Optional[date] = None) -> Optional[int]:
    """Calculate integer age in years from date of birth without exposing DOB.
    
    Returns None if DOB is invalid or out of realistic range (0-120).
    """
    birth_date = _parse_date_input(dob)
    if not birth_date:
        return None

    target_date = as_of or date.today()
    if birth_date > target_date:
        return None

    age = target_date.year - birth_date.year - ((target_date.month, target_date.day) < (birth_date.month, birth_date.day))
    if age < 0 or age > 120:
        return None
    return age


def calculate_age_group(dob: Optional[Any], as_of: Optional[date] = None) -> str:
    """Calculate age bucket on the server. Never return raw date of birth."""
    age = calculate_age(dob, as_of=as_of)
    if age is None:
        return "Not available"
    
    if age < 25:
        return "Under 25"
    elif 25 <= age <= 34:
        return "25–34"
    elif 35 <= age <= 44:
        return "35–44"
    elif 45 <= age <= 54:
        return "45–54"
    else:
        return "55 and above"


def calculate_tenure(hire_date: Optional[Any], as_of: Optional[date] = None) -> str:
    """Calculate tenure in years and months from original hire/start date."""
    start = _parse_date_input(hire_date)
    if not start:
        return "Not available"

    target_date = as_of or date.today()
    if start > target_date:
        return "Future Hire"

    total_months = (target_date.year - start.year) * 12 + (target_date.month - start.month)
    if target_date.day < start.day:
        total_months -= 1
    
    total_months = max(0, total_months)
    years = total_months // 12
    months = total_months % 12

    if years == 0 and months == 0:
        return "Less than 1 mo"
    elif years == 0:
        return f"{months} mo{'s' if months != 1 else ''}"
    elif months == 0:
        return f"{years} yr{'s' if years != 1 else ''}"
    else:
        return f"{years} yr{'s' if years != 1 else ''} {months} mo{'s' if months != 1 else ''}"


def calculate_length_of_service(hire_date: Optional[Any], as_of: Optional[date] = None) -> str:
    """Calculate length of service (alias for tenure)."""
    return calculate_tenure(hire_date, as_of=as_of)


def calculate_tenure_years(hire_date: Optional[Any], as_of: Optional[date] = None) -> Optional[float]:
    """Calculate tenure as fractional years rounded to 1 decimal place."""
    start = _parse_date_input(hire_date)
    if not start:
        return None

    target_date = as_of or date.today()
    if start > target_date:
        return 0.0

    days = (target_date - start).days
    if days < 0:
        return 0.0
    return round(days / 365.25, 1)


def calculate_tenure_group(hire_date: Optional[Any], as_of: Optional[date] = None) -> str:
    """Calculate tenure bracket for aggregate demographic reporting using exact dates."""
    start = _parse_date_input(hire_date)
    if not start:
        return "Not available"

    target_date = as_of or date.today()
    if start > target_date:
        return "Future Hire"

    # Calculate exact elapsed years based on calendar anniversary
    exact_years = target_date.year - start.year
    if (target_date.month, target_date.day) < (start.month, start.day):
        exact_years -= 1

    if exact_years < 1:
        return "< 1 year"
    elif 1 <= exact_years < 3:
        return "1–3 years"
    elif 3 <= exact_years < 5:
        return "3–5 years"
    elif 5 <= exact_years < 10:
        return "5–10 years"
    else:
        return "10+ years"


def resolve_country_name(raw_val: Optional[str]) -> str:
    """Resolve ISO country code or nationality text into standardized country name."""
    if not raw_val or str(raw_val).strip() in ("", "—", "null", "None"):
        return "Not available"
    code = str(raw_val).strip().upper()
    return COUNTRY_CODE_MAP.get(code, str(raw_val).strip())


def normalize_department(dept_val: Optional[str]) -> str:
    """Normalize department names, mapping missing/unknown to Unassigned."""
    if not dept_val or str(dept_val).strip().lower() in ("", "—", "null", "none", "unknown", "0"):
        return "Unassigned"
    return str(dept_val).strip()


class PolicyDecision:
    """Represents the outcome of a disclosure policy evaluation."""

    def __init__(
        self,
        allowed: bool,
        policy_id: str,
        policy_version: str,
        allowed_fields: List[str],
        reason: str = "",
        max_rows: int = 100,
        page_size: int = 20,
    ):
        self.allowed = allowed
        self.policy_id = policy_id
        self.policy_version = policy_version
        self.allowed_fields = allowed_fields
        self.reason = reason
        self.max_rows = max_rows
        self.page_size = page_size

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "allowed_fields": self.allowed_fields,
            "reason": self.reason,
            "max_rows": self.max_rows,
            "page_size": self.page_size,
        }


class PolicyEngine:
    """Evaluates active Dataverse policies and sanitizes outgoing data."""

    def __init__(self, dataverse_client=None):
        self.client = dataverse_client or get_dataverse_client()

    async def evaluate_drilldown_policy(
        self,
        user_object_id: Optional[str],
        user_email: Optional[str],
        user_roles: Optional[List[str]] = None,
        group_size: int = 1,
        field_profile: str = "workforce_drilldown",
    ) -> PolicyDecision:
        """Evaluate whether group drill-down and specific fields are permitted."""
        # 1. Anonymous MCP constraint: Require verified user context for employee drill-down
        if not user_object_id and not user_email:
            return PolicyDecision(
                allowed=False,
                policy_id="NONE",
                policy_version="0.0.0",
                allowed_fields=[],
                reason="Employee-level drill-down requires verified user identity context (Entra Object ID).",
            )

        policy = await self.client.get_active_policy(domain="Employee")
        if not policy:
            # Fallback default strict decision
            return PolicyDecision(
                allowed=False,
                policy_id="NO_ACTIVE_POLICY",
                policy_version="0.0.0",
                allowed_fields=[],
                reason="No active Dataverse employee disclosure policy found.",
            )

        policy_id = policy.get("cre2f_veloradatadisclosurepolicyid", "")
        policy_ver = policy.get("cre2f_version", "1.0.0")

        # 2. Check if drill-down is enabled
        if not policy.get("cre2f_allowgroupdrilldown", True):
            return PolicyDecision(
                allowed=False,
                policy_id=policy_id,
                policy_version=policy_ver,
                allowed_fields=[],
                reason="Employee group drill-down is currently disabled in the active policy.",
            )

        # 3. Check minimum group size
        min_size = int(policy.get("cre2f_minimumgroupsize", 1))
        if group_size < min_size:
            return PolicyDecision(
                allowed=False,
                policy_id=policy_id,
                policy_version=policy_ver,
                allowed_fields=[],
                reason=f"Group size ({group_size}) is smaller than policy minimum threshold ({min_size}).",
            )

        # 4. Check user roles/groups
        allowed_groups_raw = policy.get("cre2f_allowedusergroups", "[]")
        allowed_groups = json.loads(allowed_groups_raw) if isinstance(allowed_groups_raw, str) else allowed_groups_raw
        if allowed_groups and "All_Velora_Authenticated" not in allowed_groups:
            user_groups_set = set(user_roles or [])
            if not user_groups_set.intersection(set(allowed_groups)):
                return PolicyDecision(
                    allowed=False,
                    policy_id=policy_id,
                    policy_version=policy_ver,
                    allowed_fields=[],
                    reason="User role does not have authorization for employee-level drill-down under active policy.",
                )

        # 5. Determine allowed field allowlist
        configured_fields_raw = policy.get("cre2f_allowedemployeefields", "[]")
        configured_fields = json.loads(configured_fields_raw) if isinstance(configured_fields_raw, str) else configured_fields_raw
        
        target_profile_fields = PROFILE_BASIC if field_profile == "basic" else PROFILE_WORKFORCE_DRILLDOWN
        
        # Intersect with configured fields and remove permanently prohibited
        effective_allowed: List[str] = []
        for f in target_profile_fields:
            if f.lower() in PERMANENTLY_PROHIBITED_FIELDS:
                continue
            if not configured_fields or f in configured_fields or f.lower() in [cf.lower() for cf in configured_fields]:
                effective_allowed.append(f)

        max_rows = int(policy.get("cre2f_maximumresultrows", 100))
        return PolicyDecision(
            allowed=True,
            policy_id=policy_id,
            policy_version=policy_ver,
            allowed_fields=effective_allowed,
            reason="Authorized by active Dataverse disclosure policy.",
            max_rows=max_rows,
            page_size=20,
        )

    def apply_field_redaction(
        self,
        raw_records: List[Dict[str, Any]],
        decision: PolicyDecision,
    ) -> List[Dict[str, Any]]:
        """Apply strict field allowlist, compute derived fields, and strip prohibited properties."""
        if not decision.allowed:
            return []

        allowed_fields_lower = {f.lower(): f for f in decision.allowed_fields}
        sanitized_records: List[Dict[str, Any]] = []

        for record in raw_records:
            sanitized: Dict[str, Any] = {}
            
            # Map canonical user fields
            emp_id = record.get("userId") or record.get("personIdExternal") or record.get("employeeId") or ""
            name = record.get("name") or record.get("displayName") or f"{record.get('firstName', '')} {record.get('lastName', '')}".strip()
            
            # Derived fields
            raw_country = record.get("nationality") or record.get("country") or record.get("locationCountry")
            country = resolve_country_name(raw_country)
            
            raw_dob = record.get("dateOfBirth") or record.get("dob")
            age = calculate_age(raw_dob)
            age_group = calculate_age_group(raw_dob)
            
            raw_hire_date = record.get("hireDate") or record.get("startDate") or record.get("origHireDate") or record.get("originalStartDate")
            parsed_hire = _parse_date_input(raw_hire_date)
            joined_date_str = parsed_hire.isoformat() if parsed_hire else "Not available"
            tenure = calculate_tenure(raw_hire_date)
            length_of_service = tenure
            tenure_years = calculate_tenure_years(raw_hire_date)
            tenure_group = calculate_tenure_group(raw_hire_date)
            
            dept = normalize_department(record.get("department"))
            business_unit = record.get("businessUnit", "—")
            division = record.get("division", "—")
            job_title = record.get("jobTitle") or record.get("title") or "—"
            location = record.get("location") or record.get("city") or "—"
            emp_status = record.get("employmentStatus") or record.get("status") or "Active"
            recruiter = record.get("recruiter") or record.get("recruited_by") or record.get("recruitedBy") or "Not available"

            field_pool: Dict[str, Any] = {
                "userid": emp_id,
                "name": name or f"Employee {emp_id}",
                "email": record.get("email") or record.get("work_email") or f"{emp_id.lower()}@velora.ae",
                "work_email": record.get("email") or record.get("work_email") or f"{emp_id.lower()}@velora.ae",
                "country": country,
                "nationality": country,
                "gender": record.get("gender") or "Not disclosed",
                "age": age if age is not None else "Not available",
                "age_group": age_group,
                "joined_date": joined_date_str,
                "hire_date": joined_date_str,
                "tenure": tenure,
                "length_of_service": length_of_service,
                "tenure_years": tenure_years if tenure_years is not None else "Not available",
                "tenure_group": tenure_group,
                "department": dept,
                "businessunit": business_unit,
                "division": division,
                "jobtitle": job_title,
                "location": location,
                "employmentstatus": emp_status,
                "recruited_by": recruiter,
            }

            for lower_key, original_key in allowed_fields_lower.items():
                # Enforce absolute blacklist
                if lower_key in PERMANENTLY_PROHIBITED_FIELDS:
                    continue
                if lower_key in field_pool:
                    sanitized[original_key] = field_pool[lower_key]
                elif original_key in record and original_key.lower() not in PERMANENTLY_PROHIBITED_FIELDS:
                    sanitized[original_key] = record[original_key]

            sanitized_records.append(sanitized)

        return sanitized_records


_global_policy_engine = PolicyEngine()


def get_policy_engine() -> PolicyEngine:
    return _global_policy_engine
