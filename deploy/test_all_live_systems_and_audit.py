"""Limited read-only service health checks; not end-to-end or audit verification."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
import urllib.request
import urllib.error

SERVICES = [
    {
        "name": "SAP SuccessFactors HCM",
        "app": "sf-hcm-mcp-server",
        "health_url": "https://sf-hcm-mcp-server.cfapps.eu10-005.hana.ondemand.com/health",
        "source_system": "SuccessFactors",
        "sample_tool": "aggregate_headcount_by_department"
    },
    {
        "name": "SAP S/4HANA Finance",
        "app": "s4-finance-mcp-server",
        "health_url": "https://s4-finance-mcp-server.cfapps.eu10-005.hana.ondemand.com/health",
        "source_system": "S4HANA",
        "sample_tool": "get_profit_and_loss_summary"
    },
    {
        "name": "SAP Analytics Cloud (SAC)",
        "app": "sac-analytics-mcp-server",
        "health_url": "https://sac-analytics-mcp-server.cfapps.eu10-005.hana.ondemand.com/health",
        "source_system": "SAC",
        "sample_tool": "get_sac_kpis"
    },
    {
        "name": "Velora Productivity Agent (Child Connected Agent)",
        "app": "productivity-mcp-server",
        "health_url": "https://productivity-mcp-server.cfapps.eu10-005.hana.ondemand.com/health",
        "source_system": "Microsoft365",
        "sample_tool": "PrepareEmail"
    },
    {
        "name": "Velora Facilitator",
        "app": "facilitator-mcp-server",
        "health_url": "https://facilitator-mcp-server.cfapps.eu10-005.hana.ondemand.com/health",
        "source_system": "Facilitator",
        "sample_tool": "get_facilitator_guide"
    }
]

DATAVERSE_AUDIT_TABLE = "cre2f_veloraagentauditlog"

APPROVED_AUDIT_COLUMNS = [
    # Correlation
    "cre2f_rootcorrelationid",
    "cre2f_conversationid",
    "cre2f_invocationid",
    "cre2f_idempotencykey",
    # Agent Identity
    "cre2f_callingagent",
    "cre2f_executingagent",
    "cre2f_agentversion",
    "cre2f_environment",
    # User Identity
    "cre2f_useremail",
    "cre2f_newcolumn",
    # Transaction
    "cre2f_recordtype",
    "cre2f_capability",
    "cre2f_operation",
    "cre2f_sourcesystem",
    # Outcome
    "cre2f_outcome",
    "cre2f_eventtime",
    "cre2f_resultcount",
    # Content Governance
    "cre2f_auditdetail",
    "cre2f_messagesummary",
    "cre2f_dataclassification",
]



def test_service_record(service: dict) -> dict:
    """Read health only. This does not execute a business tool or persist audit data."""
    start_time = time.monotonic()
    result = {
        "service": service["name"],
        "app": service["app"],
        "health_url": service["health_url"],
        "health_status": "UNVERIFIED",
        "business_operation_status": "NOT_RUN",
        "audit_write_status": "NOT_RUN",
        "audit_readback_status": "NOT_RUN",
        "aatc_status": "INCOMPLETE",
    }
    try:
        request = urllib.request.Request(service["health_url"], method="GET", headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=15) as response:
            result["http_status"] = response.status
            body = response.read(65537)
            if len(body) > 65536:
                raise ValueError("Health response exceeded size limit")
            payload = json.loads(body)
            state = payload.get("status") if isinstance(payload, dict) else None
            result["health_status"] = "HEALTHY" if response.status == 200 and state in ("ok", "healthy", "HEALTHY", "UP") else "UNCONFIRMED"
    except urllib.error.HTTPError as error:
        result["http_status"] = error.code
        result["health_status"] = "FAILED"
    except Exception as error:
        result["health_status"] = "FAILED"
        result["error_type"] = type(error).__name__
    result["latency_ms"] = round((time.monotonic() - start_time) * 1000)
    return result


def main():
    results = [test_service_record(service) for service in SERVICES]
    print(json.dumps({
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Read-only health checks against configured service URLs only",
        "results": results,
        "aatc_status": "INCOMPLETE",
        "remaining_evidence": [
            "Verify these URLs match the current deployed release.",
            "Execute authorized business operations against real providers.",
            "Persist audit events and read back the matching durable records.",
            "Record deployed source revision and image digest.",
        ],
    }, indent=2))
    return 2  # Health alone must never produce a successful integration sign-off.


if __name__ == "__main__":
    raise SystemExit(main())
