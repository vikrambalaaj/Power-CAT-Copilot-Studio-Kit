"""Synthetic, offline reproductions for review findings."""
import asyncio
import json
import os
import socket
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
os.environ.clear()
os.environ.update(PYTHON_DOTENV_DISABLED="1", VELORA_STATE_DIR=tempfile.mkdtemp())
os.chdir(tempfile.mkdtemp())
def blocked(*args, **kwargs):
    raise RuntimeError("OFFLINE_REVIEW_NETWORK_BLOCKED")
socket.socket.connect = blocked
socket.create_connection = blocked
from pydantic_settings.sources import DotEnvSettingsSource
DotEnvSettingsSource._read_env_files = lambda self: {}
sys.path.insert(0, str(ROOT / "mcp-apps/ask-s4hana"))
from s4hana_mcp import server
from s4hana_mcp.report_calculations import calculate_budget_consumption
from starlette.testclient import TestClient
import httpx

results = {}
server.settings.allow_anonymous = False
server.settings.mcp_api_key = "synthetic-review-api-key"
response = httpx.Response(200, text='<Schema><EntityType Name="InternalEntity"/></Schema>')
with patch.object(server.S4Client, "_authorization", AsyncMock(return_value="Bearer synthetic-provider-token")), patch.object(server.S4Client, "_validated_base_url", return_value="https://example.invalid/odata"), patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=response)) as get:
    with TestClient(server.app) as client:
        secured = client.get("/mcp/tools")
        schema = client.get("/schema")
    results["unauthenticated_schema"] = {"tools_status": secured.status_code, "schema_status": schema.status_code, "provider_calls": get.call_count, "metadata_returned": "InternalEntity" in schema.text}

value = calculate_budget_consumption([{"BudgetAmountInFMACrcy": 0, "BudgetAmount": 999, "ActualAmountInFMACrcy": 0, "ActualAmount": 100, "FinancialManagementAreaCrcy": "AED"}])
results["zero_value_alias_selection"] = {"expected_budget": "0", "observed_budget": str(value["raw_budget"]), "expected_actual": "0", "observed_actual": str(value["raw_actuals"])}

from s4hana_mcp import tools
fake = type("FakeClient", (), {"settings": type("Settings", (), {"s4_budget_consumption_entity": "BudgetConsumSummary", "s4_budget_mapping_approved": False})(), "query": AsyncMock(return_value={"status": "error", "code": "SYNTHETIC_STOP"})})()
async def filter_probe():
    with patch.object(tools, "client", fake):
        await tools.s4__get_budget_consumption(company_code="2000", financial_management_area="2000", commitment_item="CI-1", budget_version="V2")
    results["summary_filter_loss"] = {"requested_filters": ["company_code", "financial_management_area", "commitment_item", "budget_version"], "provider_filters": fake.query.call_args.args[2]}
asyncio.run(filter_probe())
(OUT / "probes.json").write_text(json.dumps(results, indent=2))
print(json.dumps(results, indent=2))
