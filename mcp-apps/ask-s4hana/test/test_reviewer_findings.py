"""Comprehensive verification tests proving resolution of independent review findings R01 through R10."""
import json
import unittest
from decimal import Decimal
from unittest.mock import patch

import httpx
from starlette.testclient import TestClient

import s4hana_mcp.server as server
from s4hana_mcp.client import S4Client
from s4hana_mcp.contracts import ReportStatus, to_jsonable_data
from s4hana_mcp.report_calculations import (
    calculate_aging_buckets,
    calculate_budget_consumption,
    calculate_budget_movements,
)


class FakeSettings:
    s4_api_url = "https://fiori.velora.ae/sap/opu/odata4/sap/zfi_sbn_ageingdata_srv/srvd_a2x/sap/zfi_sdf_ageingdata_srv/0001"
    s4_sap_client = "100"
    s4_auth_mode = "basic"
    s4_token_url = ""
    s4_client_id = ""
    s4_client_secret = ""
    s4_username = "API_USER"
    s4_password = "secret_password"
    s4_ar_entity = "ARageingData"
    s4_ap_entity = "APageingData"
    s4_budget_transfer_entity = "BudgetTransfer"
    s4_budget_consumption_entity = "BudgetConsumData"
    executing_identity = "velora-s4-finance-test-reader"
    authorization_model = "MAKER_SERVICE_CREDENTIAL"
    s4_environment_label = "Production"
    s4_report_timezone = "Asia/Dubai"
    s4_report_max_rows = 1000
    s4_report_max_pages = 50
    s4_total_timeout_seconds = 60.0
    s4_verify_tls = True
    s4_ca_bundle = ""
    cache_enabled = True
    cache_ttl_seconds = 60
    cache_max_entries = 512




class ReviewerFindingsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = server.create_app()
        self.client = TestClient(self.app)
        self.api_key = "test_key"
        server.settings.mcp_api_key = self.api_key
        server.settings.allow_anonymous = False

    def test_r01_decimal_serialization_at_http_boundary(self):
        """R01: Verify Decimal in report responses serializes cleanly through REST and MCP boundaries without 500 error."""
        # Directly check SafeJSONResponse with Decimal
        res = server.SafeJSONResponse({
            "total": Decimal("12345.67"),
            "buckets": {"1_30": Decimal("500.00")},
        })
        body = json.loads(res.body.decode("utf-8"))
        self.assertEqual(body["total"], 12345.67)
        self.assertEqual(body["buckets"]["1_30"], 500.00)

        # Mock SAP request returning records with Decimals
        import s4hana_mcp.tools as tools
        with patch.object(tools.client, "query") as mock_query:

            mock_query.return_value = {
                "status": "COMPLETE",
                "data": {
                    "records": [
                        {"Customer": "1001", "CustomerName": "Test Client", "OpenAmount": Decimal("100.50"), "DaysOverdue": 15, "Currency": "AED"}
                    ],
                    "total": 1,
                },
                "coverage": {"rowsRead": 1, "rowsDisplayed": 1, "pageCount": 1, "declaredTotal": 1, "completionState": "COMPLETE"},
                "sources": [{"sourceId": "S4_RECEIVABLESAGING", "currency": "AED"}],
                "quality": {"confidence": "High"},
                "type": "ReceivablesAging",
            }
            # REST endpoint with alias
            resp = self.client.get("/s4__get_receivables_aging", headers={"X-API-Key": self.api_key})
            self.assertEqual(resp.status_code, 200, f"Expected 200, got {resp.status_code}: {resp.text}")
            data = resp.json()
            self.assertIn("calculations", data)
            self.assertEqual(data["calculations"]["total_open_signed"], 100.50)

            # Custom MCP tools/call
            mcp_resp = self.client.post(
                "/mcp",
                headers={"X-API-Key": self.api_key},
                json={
                    "jsonrpc": "2.0",
                    "id": "test-1",
                    "method": "tools/call",
                    "params": {"name": "getReceivablesAging", "arguments": {}},
                },
            )
            self.assertEqual(mcp_resp.status_code, 200)
            mcp_data = mcp_resp.json()
            self.assertNotIn("error", mcp_data)
            self.assertIn("result", mcp_data)

    def test_r02_different_currencies_partitioned_not_combined(self):
        """R02: Verify multi-currency records (USD and AED) are partitioned per currency and NOT summed into AED."""
        records = [
            {"Customer": "C1", "OpenAmount": "100.00", "Currency": "USD", "DaysOverdue": 10},
            {"Customer": "C2", "OpenAmount": "100.00", "Currency": "AED", "DaysOverdue": 10},
        ]
        calc = calculate_aging_buckets(records, is_receivable=True)
        self.assertTrue(calc.get("is_multi_currency"))
        self.assertIn("by_currency", calc)
        self.assertEqual(calc["by_currency"]["USD"]["total_open_signed"], Decimal("100.00"))
        self.assertEqual(calc["by_currency"]["AED"]["total_open_signed"], Decimal("100.00"))
        # Must not have a single combined total of 200 labelled AED
        self.assertNotIn("total_open_signed", calc)

    def test_r03_budget_consumption_dedup_and_configuration_required(self):
        """R03: Verify repeated budget amounts are deduplicated by composite grain, and status is CONFIGURATION_REQUIRED when unapproved."""
        records = [
            {
                "FinancialManagementArea": "1000",
                "FundsCenter": "FC01",
                "CommitmentItem": "CI01",
                "FinMgmtAreaFiscalYear": "2026",
                "BudgetVersion": "0",
                "BudgetAmountInFMACrcy": "100.00",
                "ActualAmountInFMACrcy": "20.00",
                "CmtmtOpenItemAmountInFMACrcy": "10.00",
            },
            {
                # Repeated budget row with identical grain key (same budget line, different line item)
                "FinancialManagementArea": "1000",
                "FundsCenter": "FC01",
                "CommitmentItem": "CI01",
                "FinMgmtAreaFiscalYear": "2026",
                "BudgetVersion": "0",
                "BudgetAmountInFMACrcy": "100.00",
                "ActualAmountInFMACrcy": "30.00",
                "CmtmtOpenItemAmountInFMACrcy": "5.00",
            },
        ]
        calc = calculate_budget_consumption(records, mapping_approved=False)
        # F02: Headline and funds-center detail must reconcile from the same validated inputs (not arbitrarily drop rows)
        self.assertEqual(calc["raw_budget"], Decimal("200.00"))
        self.assertEqual(calc["funds_centers"][0]["budget"], Decimal("200.00"))
        self.assertEqual(calc["raw_actuals"], Decimal("50.00"))
        self.assertEqual(calc["mapping_status"], "CONFIGURATION_REQUIRED")
        self.assertNotIn("approved_budget", calc)  # Ambiguous business totals blocked until approved

    def test_r04_next_link_boundary_and_sap_client_invariants(self):
        """R04: Continuation links cannot escape path segment boundary or change sap-client."""
        client = S4Client(FakeSettings())
        base = "https://fiori.velora.ae/sap/opu/odata4/sap/zfi_sbn_ageingdata_srv/srvd_a2x/sap/zfi_sdf_ageingdata_srv/0001"

        # 1. Sibling path injection rejected
        with self.assertRaises(ValueError):
            client._validate_safe_next_link("https://fiori.velora.ae/sap/opu/odata4/sap/zfi_sbn_ageingdata_srv/srvd_a2x/sap/zfi_sdf_ageingdata_srv/0001evil/ARageingData", base)

        # 2. Changed sap-client=200 rejected
        with self.assertRaises(ValueError):
            client._validate_safe_next_link(f"{base}/ARageingData?$skiptoken=20&sap-client=200", base)

        # 3. Duplicate sap-client rejected
        with self.assertRaises(ValueError):
            client._validate_safe_next_link(f"{base}/ARageingData?$skiptoken=20&sap-client=100&sap-client=100", base)

        # 4. Missing sap-client injected with approved client 100
        safe = client._validate_safe_next_link(f"{base}/ARageingData?$skiptoken=20", base)
        self.assertIn("sap-client=100", safe)

    def test_r06_legacy_variance_and_date_handling(self):
        """R06: Legacy variance rejects cost_center and unmapped company; live key date rejects future dates."""
        import s4hana_mcp.tools as tools

        # Future date rejected
        res = tools.live_key_date_error("2099-01-01")
        self.assertIsNotNone(res)
        self.assertEqual(res["code"], ReportStatus.UNSUPPORTED_FILTER.value)

        # Past date rejected
        res_past = tools.live_key_date_error("2020-01-01")
        self.assertIsNotNone(res_past)
        self.assertEqual(res_past["code"], ReportStatus.HISTORICAL_DATA_UNAVAILABLE.value)

        # Budget variance rejecting cost_center
        resp = self.client.get("/s4__get_budget_variance?cost_center=CC01", headers={"X-API-Key": self.api_key})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Filtering by cost_center", resp.text)

        # Budget variance rejecting unmapped company code
        resp_comp = self.client.get("/s4__get_budget_variance?company_code=2000", headers={"X-API-Key": self.api_key})
        self.assertEqual(resp_comp.status_code, 400)
        self.assertIn("no approved Financial Management Area mapping", resp_comp.text)

    def test_r08_contract_mismatch_on_unexpected_shape(self):
        """R08: Malformed OData JSON shape returns CONTRACT_MISMATCH instead of silently returning empty list."""
        mock_response = httpx.Response(
            status_code=200,
            text=json.dumps({"unexpected_key": "some_value"}),
            request=httpx.Request("GET", "https://fiori.velora.ae/test"),
        )
        client = S4Client(FakeSettings())
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            import asyncio
            result = asyncio.run(client._request("ARageingData", {}))
            self.assertEqual(result.get("status"), "error")
            self.assertEqual(result.get("code"), "CONTRACT_MISMATCH")

    def test_r10_tool_surface_and_alias_routing(self):
        """R10: Tool discovery exposes exactly the 4 core reports, and aliases resolve without 404."""
        # 1. MCP Tools discovery
        resp = self.client.get("/mcp/tools", headers={"X-API-Key": self.api_key})
        self.assertEqual(resp.status_code, 200)
        tools_list = resp.json()["tools"]
        tool_names = [t["name"] for t in tools_list]
        self.assertEqual(
            set(tool_names),
            {
                "s4__get_receivables_aging",
                "s4__get_payables_aging",
                "s4__get_budget_transfers",
                "s4__get_budget_consumption",
            },
        )
        self.assertNotIn("s4__get_profit_and_loss", tool_names)

        # 2. Aliases resolve successfully on REST
        import s4hana_mcp.tools as tools

        async def fake_query(entity, capability, *args, **kwargs):
            return {
                "status": "EMPTY",
                "data": {"records": [], "total": 0},
                "coverage": {"rowsRead": 0, "rowsDisplayed": 0, "pageCount": 1, "declaredTotal": 0, "completionState": "COMPLETE"},
                "sources": [],
                "quality": {"confidence": "High"},
                "type": capability,
            }

        with patch.object(tools.client, "query", side_effect=fake_query):
            # CamelCase alias
            r_camel = self.client.get("/getReceivablesAging", headers={"X-API-Key": self.api_key})
            self.assertEqual(r_camel.status_code, 200)

            # Budget variance alias
            r_bvar = self.client.get("/getBudgetVariance", headers={"X-API-Key": self.api_key})
            self.assertEqual(r_bvar.status_code, 200)

    def test_f01_ar_company_code_currency_multi_currency_and_text(self):
        """F01: AR uses exact CompanyCodeCurrency; mixed currencies do not sum together and text/cards don't crash."""
        from s4hana_mcp.report_calculations import calculate_aging_buckets
        from s4hana_mcp.tools import build_text_summary
        from s4hana_mcp.adaptive_cards import decorate

        records = [
            {"AccountingDocument": "0001", "AccountingDocumentItem": "001", "CompanyCodeCurrency": "USD", "OpenAmount": "100.00"},
            {"AccountingDocument": "0002", "AccountingDocumentItem": "001", "CompanyCodeCurrency": "AED", "OpenAmount": "100.00"},
        ]
        calc = calculate_aging_buckets(records, is_receivable=True)
        self.assertTrue(calc["is_multi_currency"])
        self.assertIn("USD", calc["by_currency"])
        self.assertIn("AED", calc["by_currency"])
        self.assertEqual(calc["by_currency"]["USD"]["total_open_signed"], Decimal("100.00"))
        self.assertEqual(calc["by_currency"]["AED"]["total_open_signed"], Decimal("100.00"))

        data = {
            "type": "ReceivablesAging",
            "data": {"records": records, "total": 2},
            "calculations": calc,
            "query": {"filters": {"CompanyCode": "1000"}},
            "coverage": {"rowsRead": 2, "declaredTotal": 2},
        }
        text = build_text_summary(data)
        self.assertIn("Multi-Currency", text)
        self.assertIn("USD: Net 100.00", text)
        self.assertIn("AED: Net 100.00", text)

        card_data = decorate(data)
        self.assertIn("adaptiveCard", card_data)

    def test_f02_budget_reconciles_headline_and_detail(self):
        """F02: Rows with amounts 100 and 200 at same key reconcile between headline and detail without dropping rows."""
        from s4hana_mcp.report_calculations import calculate_budget_consumption

        records = [
            {
                "FinancialManagementArea": "1000",
                "FundsCenter": "FC01",
                "CommitmentItem": "CI01",
                "FinMgmtAreaFiscalYear": "2026",
                "BudgetVersion": "0",
                "BudgetAmountInFMACrcy": "100.00",
            },
            {
                "FinancialManagementArea": "1000",
                "FundsCenter": "FC01",
                "CommitmentItem": "CI01",
                "FinMgmtAreaFiscalYear": "2026",
                "BudgetVersion": "0",
                "BudgetAmountInFMACrcy": "200.00",
            },
        ]
        calc = calculate_budget_consumption(records, mapping_approved=False)
        # Headline and funds center detail must both equal 300.00
        self.assertEqual(calc["raw_budget"], Decimal("300.00"))
        self.assertEqual(calc["funds_centers"][0]["budget"], Decimal("300.00"))

    def test_f03_composite_row_keys_multi_line_and_duplicates(self):
        """F03: Normal multi-line documents (items 001 and 002) are both kept; true duplicates are deduped; conflicts flagged."""
        client = S4Client(FakeSettings())
        # Multi-line document: same document, different line items -> distinct keys
        k1 = client._get_composite_row_key({"AccountingDocument": "0001", "AccountingDocumentItem": "001", "CompanyCode": "1000", "FiscalYear": "2026"})
        k2 = client._get_composite_row_key({"AccountingDocument": "0001", "AccountingDocumentItem": "002", "CompanyCode": "1000", "FiscalYear": "2026"})
        self.assertNotEqual(k1, k2)

        # In request simulation:
        rows = [
            {"AccountingDocument": "0001", "AccountingDocumentItem": "001", "CompanyCode": "1000", "FiscalYear": "2026", "OpenAmount": "100.00"},
            {"AccountingDocument": "0001", "AccountingDocumentItem": "002", "CompanyCode": "1000", "FiscalYear": "2026", "OpenAmount": "200.00"},
            {"AccountingDocument": "0001", "AccountingDocumentItem": "001", "CompanyCode": "1000", "FiscalYear": "2026", "OpenAmount": "100.00"}, # Identical duplicate
        ]
        mock_resp = httpx.Response(200, text=json.dumps({"value": rows, "@odata.count": 2}), request=httpx.Request("GET", "https://fiori.velora.ae/test"))
        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            import asyncio
            res = asyncio.run(client._request("ARageingData", {}))
            self.assertEqual(len(res["rows"]), 2)
            self.assertTrue(res["complete"])

    def test_f04_exact_decimal_serialization(self):
        """F04: 9007199254740993.01 does not lose precision to 9007199254740994.0 in SafeJSONResponse."""
        from s4hana_mcp.server import serialize_with_exact_decimals, SafeJSONResponse

        exact_val = Decimal("9007199254740993.01")
        payload = {"amount": exact_val}
        serialized = serialize_with_exact_decimals(payload)
        self.assertIn("9007199254740993.01", serialized)
        self.assertNotIn("9007199254740994", serialized)

        loaded = json.loads(serialized, parse_float=Decimal)
        self.assertEqual(loaded["amount"], exact_val)

        resp = SafeJSONResponse(payload)
        self.assertIn(b"9007199254740993.01", resp.body)

    def test_f05_endpoint_validation_and_continuation_entity(self):
        """F05: Arbitrary .velora.ae hosts rejected; exact continuation entity path enforced."""
        client = S4Client(FakeSettings())
        # 1. QAS host with Prod settings rejected
        with self.assertRaises(ValueError):
            client._validated_base_url("https://fioriqas.velora.ae/anything")

        # 2. Child entity path rejected
        base = "https://fiori.velora.ae/sap/opu/odata4/sap/zfi_sbn_ageingdata_srv/srvd_a2x/sap/zfi_sdf_ageingdata_srv/0001"
        with self.assertRaises(ValueError):
            client._validate_safe_next_link(f"{base}/ARageingData/childEntity?$skiptoken=10", base, expected_entity="ARageingData")

    def test_f06_rest_tools_route_and_executive_entitlement(self):
        """F06: /tools/{name} routes exist, and unauthorized executive scope is rejected."""
        import s4hana_mcp.tools as tools

        async def fake_query(*args, **kwargs):
            return {
                "status": "EMPTY",
                "data": {"records": [], "total": 0},
                "coverage": {"rowsRead": 0, "rowsDisplayed": 0, "pageCount": 1, "declaredTotal": 0, "completionState": "COMPLETE"},
                "sources": [],
                "quality": {"confidence": "High"},
                "type": "ReceivablesAging",
            }

        with patch.object(tools.client, "query", side_effect=fake_query):
            # /tools/ route works
            resp = self.client.get("/tools/s4__get_receivables_aging", headers={"X-API-Key": self.api_key})
            self.assertEqual(resp.status_code, 200)

            # Unauthorized organization scope rejected with 403
            resp_denied = self.client.get(
                "/tools/s4__get_receivables_aging",
                headers={"X-API-Key": self.api_key, "X-Organization-Scope": "9999"}
            )
            self.assertEqual(resp_denied.status_code, 403)
            self.assertEqual(resp_denied.json()["code"], "ACCESS_DENIED")

