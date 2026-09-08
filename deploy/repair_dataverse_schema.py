"""Idempotently repair the Velora Dataverse governance schema.

The script uses the signed-in Azure CLI identity, creates the missing disclosure
policy table in the Velora Executive Agent solution, adds the two existing
governance tables to that solution, and seeds the baseline workforce policy.
"""
from __future__ import annotations

import json
import base64
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DATAVERSE_URL = "https://org4b098979.crm15.dynamics.com"
API_URL = f"{DATAVERSE_URL}/api/data/v9.2"
SOLUTION_UNIQUE_NAME = "VeloraExecutiveAgent"
GOVERNANCE_SOLUTION_UNIQUE_NAME = "cre2f_VeloraExecutiveAgentPlatform"
PUBLISHER_ID = "00000001-0000-0000-0000-00000000005a"

AUDIT_TABLE = "cre2f_veloraagentauditlog"
CONSENT_TABLE = "cre2f_botuserconsent"
POLICY_TABLE = "cre2f_veloradatadisclosurepolicy"


def azure_access_token() -> str:
    return subprocess.check_output(
        [
            "az",
            "account",
            "get-access-token",
            "--resource",
            DATAVERSE_URL,
            "--query",
            "accessToken",
            "-o",
            "tsv",
        ],
        text=True,
    ).strip()


TOKEN = azure_access_token()


def request(
    method: str,
    path: str,
    body: dict | None = None,
    *,
    solution_header: bool = False,
) -> tuple[int, dict, dict]:
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
    }
    if solution_header:
        headers["MSCRM.SolutionUniqueName"] = SOLUTION_UNIQUE_NAME
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{API_URL}/{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read()
            parsed = json.loads(raw) if raw else {}
            return response.status, parsed, dict(response.headers)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Dataverse {method} {path} failed ({exc.code}): {detail}") from exc


def label(text: str) -> dict:
    return {
        "@odata.type": "Microsoft.Dynamics.CRM.Label",
        "LocalizedLabels": [
            {
                "@odata.type": "Microsoft.Dynamics.CRM.LocalizedLabel",
                "Label": text,
                "LanguageCode": 1033,
            }
        ],
    }


def required_level(value: str = "None") -> dict:
    return {
        "Value": value,
        "CanBeChanged": True,
        "ManagedPropertyLogicalName": "canmodifyrequirementlevelsettings",
    }


def string_attribute(schema_name: str, display_name: str, max_length: int = 200) -> dict:
    return {
        "@odata.type": "Microsoft.Dynamics.CRM.StringAttributeMetadata",
        "AttributeType": "String",
        "AttributeTypeName": {"Value": "StringType"},
        "SchemaName": schema_name,
        "DisplayName": label(display_name),
        "RequiredLevel": required_level(),
        "FormatName": {"Value": "Text"},
        "MaxLength": max_length,
    }


def memo_attribute(schema_name: str, display_name: str, max_length: int = 10000) -> dict:
    return {
        "@odata.type": "Microsoft.Dynamics.CRM.MemoAttributeMetadata",
        "AttributeType": "Memo",
        "AttributeTypeName": {"Value": "MemoType"},
        "SchemaName": schema_name,
        "DisplayName": label(display_name),
        "RequiredLevel": required_level(),
        "Format": "TextArea",
        "MaxLength": max_length,
    }


def boolean_attribute(schema_name: str, display_name: str, default: bool = False) -> dict:
    return {
        "@odata.type": "Microsoft.Dynamics.CRM.BooleanAttributeMetadata",
        "AttributeType": "Boolean",
        "AttributeTypeName": {"Value": "BooleanType"},
        "SchemaName": schema_name,
        "DisplayName": label(display_name),
        "RequiredLevel": required_level(),
        "DefaultValue": default,
        "OptionSet": {
            "@odata.type": "Microsoft.Dynamics.CRM.BooleanOptionSetMetadata",
            "TrueOption": {"Value": 1, "Label": label("Yes")},
            "FalseOption": {"Value": 0, "Label": label("No")},
        },
    }


def integer_attribute(schema_name: str, display_name: str, minimum: int = 0, maximum: int = 100000) -> dict:
    return {
        "@odata.type": "Microsoft.Dynamics.CRM.IntegerAttributeMetadata",
        "AttributeType": "Integer",
        "AttributeTypeName": {"Value": "IntegerType"},
        "SchemaName": schema_name,
        "DisplayName": label(display_name),
        "RequiredLevel": required_level(),
        "Format": "None",
        "MinValue": minimum,
        "MaxValue": maximum,
    }


def datetime_attribute(schema_name: str, display_name: str) -> dict:
    return {
        "@odata.type": "Microsoft.Dynamics.CRM.DateTimeAttributeMetadata",
        "AttributeType": "DateTime",
        "AttributeTypeName": {"Value": "DateTimeType"},
        "SchemaName": schema_name,
        "DisplayName": label(display_name),
        "RequiredLevel": required_level(),
        "Format": "DateAndTime",
        "DateTimeBehavior": {"Value": "UserLocal"},
    }


POLICY_ATTRIBUTES = [
    string_attribute("cre2f_PolicyCode", "Policy Code", 100),
    string_attribute("cre2f_Version", "Version", 50),
    boolean_attribute("cre2f_IsActive", "Is Active", True),
    string_attribute("cre2f_Environment", "Environment", 100),
    string_attribute("cre2f_AgentId", "Agent ID", 200),
    string_attribute("cre2f_DataDomain", "Data Domain", 100),
    boolean_attribute("cre2f_AllowEmployeeSearch", "Allow Employee Search", True),
    boolean_attribute("cre2f_AllowGroupDrilldown", "Allow Group Drill-down", True),
    memo_attribute("cre2f_AllowedEmployeeFields", "Allowed Employee Fields"),
    memo_attribute("cre2f_RestrictedEmployeeFields", "Restricted Employee Fields"),
    integer_attribute("cre2f_MaximumResultRows", "Maximum Result Rows", 1, 10000),
    integer_attribute("cre2f_MinimumGroupSize", "Minimum Group Size", 1, 10000),
    memo_attribute("cre2f_AllowedUserGroups", "Allowed User Groups"),
    memo_attribute("cre2f_AllowedDepartments", "Allowed Departments"),
    boolean_attribute("cre2f_PurposeRequired", "Purpose Required", False),
    datetime_attribute("cre2f_EffectiveFrom", "Effective From"),
    datetime_attribute("cre2f_EffectiveTo", "Effective To"),
    string_attribute("cre2f_ApprovedBy", "Approved By", 300),
    datetime_attribute("cre2f_ApprovalDate", "Approval Date"),
    memo_attribute("cre2f_ChangeReason", "Change Reason", 4000),
]


def get_table(logical_name: str) -> dict | None:
    query = urllib.parse.urlencode(
        {
            "$select": "LogicalName,SchemaName,EntitySetName,MetadataId",
            "$filter": f"LogicalName eq '{logical_name}'",
        }
    )
    _, result, _ = request("GET", f"EntityDefinitions?{query}")
    return result.get("value", [None])[0] if result.get("value") else None


def ensure_policy_table() -> dict:
    existing = get_table(POLICY_TABLE)
    if existing:
        print(f"Policy table already exists: {existing['MetadataId']}")
        return existing

    primary_name = string_attribute("cre2f_PolicyName", "Policy Name", 300)
    primary_name["IsPrimaryName"] = True
    primary_name["RequiredLevel"] = required_level("ApplicationRequired")
    table = {
        "@odata.type": "Microsoft.Dynamics.CRM.EntityMetadata",
        "SchemaName": "cre2f_VeloraDataDisclosurePolicy",
        "DisplayName": label("Velora Data Disclosure Policy"),
        "DisplayCollectionName": label("Velora Data Disclosure Policies"),
        "Description": label("Governed workforce data disclosure rules used by the Velora Executive Agent."),
        "OwnershipType": "OrganizationOwned",
        "IsActivity": False,
        "HasActivities": False,
        "HasNotes": False,
        "Attributes": [primary_name, *POLICY_ATTRIBUTES],
    }
    request("POST", "EntityDefinitions", table, solution_header=True)
    created = get_table(POLICY_TABLE)
    if not created:
        raise RuntimeError("Policy table creation returned successfully but metadata was not found")
    print(f"Created policy table: {created['MetadataId']}")
    return created


def ensure_governance_solution() -> None:
    query = urllib.parse.urlencode(
        {
            "$select": "solutionid",
            "$filter": f"uniquename eq '{GOVERNANCE_SOLUTION_UNIQUE_NAME}'",
        }
    )
    _, result, _ = request("GET", f"solutions?{query}")
    if result.get("value"):
        print("Governance solution already exists")
        return
    request(
        "POST",
        "solutions",
        {
            "friendlyname": "Velora Executive Agent Platform",
            "uniquename": GOVERNANCE_SOLUTION_UNIQUE_NAME,
            "version": "1.0.1.0",
            "description": "Velora Dataverse audit, consent, and disclosure governance schema.",
            "publisherid@odata.bind": f"/publishers({PUBLISHER_ID})",
        },
    )
    print("Created Velora Executive Agent Platform solution")


def add_table_to_solution(
    metadata_id: str,
    logical_name: str,
    solution_unique_name: str = SOLUTION_UNIQUE_NAME,
) -> None:
    payload = {
        "ComponentId": metadata_id,
        "ComponentType": 1,
        "SolutionUniqueName": solution_unique_name,
        "AddRequiredComponents": False,
        "DoNotIncludeSubcomponents": True,
        "IncludedComponentSettingsValues": [],
    }
    try:
        request("POST", "AddSolutionComponent", payload)
        print(f"Added {logical_name} to {solution_unique_name}")
    except RuntimeError as exc:
        if "already exists" in str(exc).lower() or "0x8004f016" in str(exc).lower():
            print(f"{logical_name} is already in {solution_unique_name}")
        else:
            raise

    # Dataverse requires explicit component properties when a table is added with
    # all subcomponents through the action. Add each custom column separately so
    # the solution remains exportable and faithfully recreates the schema.
    _, attributes, _ = request(
        "GET",
        f"EntityDefinitions({metadata_id})/Attributes?$select=MetadataId,LogicalName",
    )
    for attribute in attributes.get("value", []):
        attribute_name = attribute.get("LogicalName", "")
        if not attribute_name.startswith("cre2f_"):
            continue
        attribute_payload = {
            "ComponentId": attribute["MetadataId"],
            "ComponentType": 2,
            "SolutionUniqueName": solution_unique_name,
            "AddRequiredComponents": False,
            "DoNotIncludeSubcomponents": True,
            "IncludedComponentSettingsValues": [],
        }
        try:
            request("POST", "AddSolutionComponent", attribute_payload)
        except RuntimeError as exc:
            if "already exists" not in str(exc).lower() and "0x8004f016" not in str(exc).lower():
                raise
    print(f"Added custom columns for {logical_name}")


def export_governance_solution() -> None:
    _, result, _ = request(
        "POST",
        "ExportSolution",
        {"SolutionName": GOVERNANCE_SOLUTION_UNIQUE_NAME, "Managed": False},
    )
    encoded = result.get("ExportSolutionFile")
    if not encoded:
        raise RuntimeError("Dataverse did not return an exported solution archive")
    output = Path(__file__).resolve().parent / "cre2f_VeloraExecutiveAgentPlatform.zip"
    output.write_bytes(base64.b64decode(encoded))
    print(f"Exported repaired governance solution: {output}")


def seed_policy(entity_set: str) -> None:
    query = urllib.parse.urlencode(
        {
            "$select": "cre2f_veloradatadisclosurepolicyid,cre2f_policyname",
            "$filter": "cre2f_policycode eq 'POL_SF_WORKFORCE' and cre2f_isactive eq true",
        }
    )
    _, existing, _ = request("GET", f"{entity_set}?{query}")
    if existing.get("value"):
        print("Baseline workforce disclosure policy already exists")
        return

    policy = {
        "cre2f_policyname": "Velora Executive Workforce Disclosure Policy",
        "cre2f_policycode": "POL_SF_WORKFORCE",
        "cre2f_version": "1.0.0",
        "cre2f_isactive": True,
        "cre2f_environment": "Velora-AgenticAD-Dev",
        "cre2f_agentid": "velora-hcm-agent",
        "cre2f_datadomain": "Employee",
        "cre2f_allowemployeesearch": True,
        "cre2f_allowgroupdrilldown": True,
        "cre2f_allowedemployeefields": json.dumps([
            "userId", "name", "email", "jobTitle", "department", "division", "businessUnit",
            "location", "country", "gender", "age", "age_group", "joined_date",
            "tenure", "length_of_service", "employmentStatus", "recruited_by",
        ]),
        "cre2f_restrictedemployeefields": json.dumps([
            "dateOfBirth", "bankAccountNumber", "iban", "nationalId", "passportNumber",
            "personalEmail", "homeAddress", "ssn", "baseSalary", "compensation",
            "bonus", "medicalHistory",
        ]),
        "cre2f_maximumresultrows": 100,
        "cre2f_minimumgroupsize": 1,
        "cre2f_allowedusergroups": json.dumps([
            "Executive", "HR_Leader", "Workforce_Analyst", "All_Velora_Authenticated",
        ]),
        "cre2f_alloweddepartments": "[]",
        "cre2f_purposerequired": False,
        "cre2f_effectivefrom": "2026-01-01T00:00:00Z",
        "cre2f_effectiveto": "2030-12-31T23:59:59Z",
        "cre2f_approvedby": "Velora HR & Privacy Governance Committee",
        "cre2f_approvaldate": "2026-01-01T00:00:00Z",
        "cre2f_changereason": "Standard enterprise baseline disclosure policy",
    }
    request("POST", entity_set, policy)
    print("Seeded baseline workforce disclosure policy")


def main() -> None:
    audit = get_table(AUDIT_TABLE)
    consent = get_table(CONSENT_TABLE)
    if not audit or not consent:
        raise RuntimeError("Existing audit or consent table is missing")

    policy = ensure_policy_table()
    ensure_governance_solution()
    for logical_name, table in (
        (AUDIT_TABLE, audit),
        (CONSENT_TABLE, consent),
        (POLICY_TABLE, policy),
    ):
        add_table_to_solution(table["MetadataId"], logical_name)
        add_table_to_solution(
            table["MetadataId"], logical_name, GOVERNANCE_SOLUTION_UNIQUE_NAME
        )

    seed_policy(policy["EntitySetName"])
    export_governance_solution()
    print("Velora Dataverse schema repair complete")


if __name__ == "__main__":
    main()
