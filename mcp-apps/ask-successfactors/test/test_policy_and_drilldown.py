"""Unit and integration tests for Dataverse Disclosure Policy & Workforce Drill-Down."""
import asyncio
import unittest
from datetime import date, datetime, timezone

from successfactors_mcp.policy_engine import (
    PolicyEngine,
    PolicyDecision,
    calculate_age_group,
    calculate_length_of_service,
    resolve_country_name,
    normalize_department,
    PERMANENTLY_PROHIBITED_FIELDS,
)
from successfactors_mcp.dataverse_audit import DataverseClient
from successfactors_mcp.successfactors_client import SuccessFactorsClient
from successfactors_mcp.policy_admin import PolicyAdminService


class FakeSFClient(SuccessFactorsClient):
    def __init__(self):
        super().__init__()
        self.mock_requests = {}

    async def _fetch_all(self, entity, select=None, filter_str=None, as_of_date=None, executive_id=None, page_size=1000):
        if entity == "FODepartment":
            return {
                "results": [
                    {"externalCode": "D101", "name": "Operations"},
                    {"externalCode": "D102", "name": "Engineering"},
                ]
            }
        elif entity == "EmpJob":
            # Return 15 unassigned employees and 5 operations employees
            results = []
            for i in range(1, 16):
                results.append({
                    "userId": f"UNASSIGNED_{i:03d}",
                    "department": None,
                    "businessUnit": "General",
                    "division": "Corporate",
                    "jobTitle": f"Coordinator {i}",
                    "location": "Abu Dhabi",
                    "employmentStatus": "Active",
                    "hireDate": "/Date(1614556800000)/",  # 2021-03-01
                    "customString1": "Talent Acquisition",
                })
            for i in range(1, 6):
                results.append({
                    "userId": f"OPS_{i:03d}",
                    "department": "D101",
                    "businessUnit": "Operations BU",
                    "division": "Operations Div",
                    "jobTitle": f"Engineer {i}",
                    "location": "Dubai",
                    "employmentStatus": "Active",
                    "hireDate": "/Date(1577836800000)/",  # 2020-01-01
                    "customString1": "Engineering Recruiter",
                })
            return {"results": results, "__count": str(len(results))}
        elif entity == "User":
            results = []
            for i in range(1, 16):
                uid = f"UNASSIGNED_{i:03d}"
                results.append({
                    "userId": uid,
                    "firstName": "Test",
                    "lastName": f"User_{uid}",
                    "displayName": f"Test User {uid}",
                    "title": "Specialist",
                    "city": "Abu Dhabi",
                    "email": f"{uid.lower()}@velora.ae",
                })
            for i in range(1, 6):
                uid = f"OPS_{i:03d}"
                results.append({
                    "userId": uid,
                    "firstName": "Test",
                    "lastName": f"User_{uid}",
                    "displayName": f"Test User {uid}",
                    "title": "Specialist",
                    "city": "Abu Dhabi",
                    "email": f"{uid.lower()}@velora.ae",
                })
            return {"results": results}
        elif entity == "PerPersonal":
            results = []
            for i in range(1, 16):
                uid = f"UNASSIGNED_{i:03d}"
                results.append({
                    "personIdExternal": uid,
                    "nationality": "ARE" if "001" in uid or "002" in uid else "IND",
                    "dateOfBirth": "/Date(771638400000)/",  # 1994-06-15 -> ~31 years old (25-34)
                })
            for i in range(1, 6):
                uid = f"OPS_{i:03d}"
                results.append({
                    "personIdExternal": uid,
                    "nationality": "ARE" if "001" in uid else "IND",
                    "dateOfBirth": "/Date(771638400000)/",
                })
            return {"results": results}
        return {"results": []}

    async def _request(self, method, endpoint, params=None, json_data=None, executive_id=None):
        if endpoint.startswith("User('"):
            uid = endpoint.split("'")[1]
            return {
                "userId": uid,
                "firstName": "Test",
                "lastName": f"User_{uid}",
                "displayName": f"Test User {uid}",
                "title": "Specialist",
                "city": "Abu Dhabi",
                "email": f"{uid.lower()}@velora.ae",
            }
        elif endpoint.startswith("PerPersonal('"):
            uid = endpoint.split("'")[1]
            return {
                "personIdExternal": uid,
                "nationality": "ARE" if "001" in uid or "002" in uid else "IND",
                "dateOfBirth": "/Date(771638400000)/",  # 1994-06-15 -> ~31 years old (25-34)
            }
        elif endpoint.startswith("EmpEmployment("):
            return {
                "startDate": "/Date(1614556800000)/",
                "origHireDate": "/Date(1614556800000)/",
            }
        return {"results": []}


class PolicyAndDrillDownTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dv_client = DataverseClient()
        self.engine = PolicyEngine(dataverse_client=self.dv_client)

    def test_age_group_calculation(self):
        self.assertEqual(calculate_age_group(None), "Not available")
        self.assertEqual(calculate_age_group("invalid-date"), "Not available")
        
        # Exact date conversions
        today = date.today()
        dob_under_25 = f"{today.year - 22}-01-01"
        dob_25_34 = f"{today.year - 30}-01-01"
        dob_35_44 = f"{today.year - 40}-01-01"
        dob_45_54 = f"{today.year - 50}-01-01"
        dob_55_plus = f"{today.year - 60}-01-01"

        self.assertEqual(calculate_age_group(dob_under_25), "Under 25")
        self.assertEqual(calculate_age_group(dob_25_34), "25–34")
        self.assertEqual(calculate_age_group(dob_35_44), "35–44")
        self.assertEqual(calculate_age_group(dob_45_54), "45–54")
        self.assertEqual(calculate_age_group(dob_55_plus), "55 and above")

    def test_length_of_service_calculation(self):
        self.assertEqual(calculate_length_of_service(None), "Not available")
        as_of = date(2026, 3, 1)
        # 3 years exactly
        hire_3y = date(2023, 3, 1)
        self.assertEqual(calculate_length_of_service(hire_3y, as_of=as_of), "3 yrs")
        
        # 2 years 5 months
        hire_2y5m = date(2023, 10, 1)
        self.assertEqual(calculate_length_of_service(hire_2y5m, as_of=as_of), "2 yrs 5 mos")

    def test_country_resolution_and_department_normalization(self):
        self.assertEqual(resolve_country_name("ARE"), "United Arab Emirates")
        self.assertEqual(resolve_country_name("IND"), "India")
        self.assertEqual(resolve_country_name(""), "Not available")
        self.assertEqual(resolve_country_name(None), "Not available")

        self.assertEqual(normalize_department(None), "Unassigned")
        self.assertEqual(normalize_department(""), "Unassigned")
        self.assertEqual(normalize_department("Operations"), "Operations")

    async def test_anonymous_context_is_rejected_for_drilldown(self):
        decision = await self.engine.evaluate_drilldown_policy(
            user_object_id=None,
            user_email=None,
        )
        self.assertFalse(decision.allowed)
        self.assertIn("requires verified user identity", decision.reason)

    async def test_authenticated_context_is_authorized_with_allowlist(self):
        decision = await self.engine.evaluate_drilldown_policy(
            user_object_id="entra-user-001",
            user_email="exec@velora.ae",
            user_roles=["Executive"],
        )
        self.assertTrue(decision.allowed)
        self.assertIn("userId", decision.allowed_fields)
        self.assertIn("name", decision.allowed_fields)
        self.assertIn("country", decision.allowed_fields)
        self.assertIn("age_group", decision.allowed_fields)
        # Prohibited fields must never be in allowed list
        for prohibited in PERMANENTLY_PROHIBITED_FIELDS:
            self.assertNotIn(prohibited, decision.allowed_fields)

    def test_field_redaction_strips_prohibited_fields(self):
        raw_employee = {
            "userId": "1001",
            "displayName": "Ahmed Al Zaabi",
            "nationality": "ARE",
            "dateOfBirth": "1990-05-10",
            "hireDate": "2020-01-15",
            "department": "Engineering",
            "jobTitle": "Lead Architect",
            "personalEmail": "ahmed.private@gmail.com",
            "homeAddress": "Corniche, Abu Dhabi",
            "iban": "AE070331234567890123456",
            "baseSalary": "45000",
        }

        decision = PolicyDecision(
            allowed=True,
            policy_id="POL-01",
            policy_version="1.0.0",
            allowed_fields=["userId", "name", "country", "age_group", "joined_date", "jobTitle"],
        )

        sanitized = self.engine.apply_field_redaction([raw_employee], decision)[0]

        # Allowed fields present
        self.assertEqual(sanitized["userId"], "1001")
        self.assertEqual(sanitized["name"], "Ahmed Al Zaabi")
        self.assertEqual(sanitized["country"], "United Arab Emirates")
        self.assertEqual(sanitized["jobTitle"], "Lead Architect")
        self.assertEqual(sanitized["age_group"], "35–44")

        # Prohibited fields completely absent
        self.assertNotIn("personalEmail", sanitized)
        self.assertNotIn("homeAddress", sanitized)
        self.assertNotIn("iban", sanitized)
        self.assertNotIn("baseSalary", sanitized)
        self.assertNotIn("dateOfBirth", sanitized)

    async def test_drilldown_15_unassigned_employees(self):
        client = FakeSFClient()
        result = await client.drilldown_employees(
            department="Unassigned",
            page=1,
            page_size=20,
            user_object_id="entra-user-123",
            user_email="auditor@velora.ae",
        )

        self.assertFalse(result.get("error"))
        self.assertEqual(result["type"], "WorkforceDrilldown")
        self.assertEqual(result["department"], "Unassigned")
        self.assertEqual(result["total_matched"], 15)
        self.assertEqual(len(result["employees"]), 15)
        
        first_emp = result["employees"][0]
        self.assertEqual(first_emp["userId"], "UNASSIGNED_001")
        self.assertEqual(first_emp["country"], "United Arab Emirates")
        self.assertIn(first_emp["age_group"], ["25–34", "Not available"])
        self.assertEqual(first_emp["recruited_by"], "Talent Acquisition")

        # Verify no prohibited fields in any employee record
        for emp in result["employees"]:
            for prohibited in PERMANENTLY_PROHIBITED_FIELDS:
                self.assertNotIn(prohibited, emp)


if __name__ == "__main__":
    unittest.main()
