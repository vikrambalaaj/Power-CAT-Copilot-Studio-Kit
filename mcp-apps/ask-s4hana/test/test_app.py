import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from mcp.types import CallToolResult

import s4hana_mcp.server as server
import s4hana_mcp.tools as tools
from s4hana_mcp.client import S4Client, bounded_top, escape_odata, validate_relative_entity
from s4hana_mcp.contracts import ReportStatus, format_decimal, safe_decimal
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
    s4_budget_consumption_entity = "BudgetConsumSummary"
    s4_customer_api_url = "https://fiori.velora.ae/sap/opu/odata4/sap/zmm_cds_sbn_customer_srv/srvd_a2x/sap/zmm_cds_sdf_customer_srv/0001"
    s4_customer_entity = "CustomerMaster"
    s4_costcenter_api_url = "https://fiori.velora.ae/sap/opu/odata4/sap/zfi_cds_sbn_costcenter_srv/srvd_a2x/sap/zfi_cds_sdf_costcenter_srv/0001"
    s4_costcenter_entity = "CostCenterMaster"
    s4_profitcenter_api_url = "https://fiori.velora.ae/sap/opu/odata4/sap/zfi_cds_sbn_profcenter_srv/srvd_a2x/sap/zfi_cds_sdf_profcenter_srv/0001"
    s4_profitcenter_entity = "ProfitCenterMaster"
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


class CapturingClient(S4Client):
    def __init__(self, return_rows=None, return_count=None, return_complete=True):
        super().__init__(FakeSettings())
        self.calls = []
        self.call_count = 0
        self.return_rows = return_rows if return_rows is not None else [{"OpenAmount": "100.00"}]
        self.return_count = return_count if return_count is not None else len(self.return_rows)
        self.return_complete = return_complete

    async def _request(self, entity, params, base_url=None, max_rows=None, max_pages=None):
        self.call_count += 1
        self.calls.append((entity, params, base_url))
        return {
            "rows": self.return_rows,
            "count": self.return_count,
            "pages": 1,
            "complete": self.return_complete,
            "incomplete_reason": "" if self.return_complete else "Bounded limit reached",
        }


class ClientAndContractTests(unittest.IsolatedAsyncioTestCase):
    def test_c01_validates_https_and_entities(self):
        settings = FakeSettings()
        client = S4Client(settings)
        self.assertEqual(client.validate(), [])
        self.assertEqual(validate_relative_entity("ARageingData"), "ARageingData")
        with self.assertRaises(ValueError):
            validate_relative_entity("../private")
        with self.assertRaises(ValueError):
            validate_relative_entity("https://attacker.example/collect")

    def test_c02_escaping_and_bounds(self):
        self.assertEqual(escape_odata("O'Reilly"), "O''Reilly")
        self.assertEqual(bounded_top(9999), 1000)
        self.assertEqual(bounded_top(0), 1)

    def test_c09_cross_origin_continuation_rejected(self):
        client = S4Client(FakeSettings())
        base = "https://fiori.velora.ae/sap/opu/odata4/sap/zfi_sbn_ageingdata_srv/srvd_a2x/sap/zfi_sdf_ageingdata_srv/0001"
        # Safe relative link is allowed
        safe = client._validate_safe_next_link("ARageingData?$skiptoken=123", base)
        self.assertTrue(safe.startswith(base))
        # Cross origin link is rejected
        with self.assertRaises(ValueError):
            client._validate_safe_next_link("https://evil.example.com/steal?token=123", base)
        # Outside service root is rejected
        with self.assertRaises(ValueError):
            client._validate_safe_next_link("https://fiori.velora.ae/other/service", base)

    def test_c10_decimal_handling(self):
        self.assertEqual(safe_decimal("123.45"), Decimal("123.45"))
        self.assertEqual(safe_decimal(None), Decimal("0.00"))
        self.assertEqual(format_decimal("123.456", 2), "123.46")


class CalculationTests(unittest.TestCase):
    def test_c11_age_boundaries_and_reconciliation(self):
        # Boundaries: -1, 0, 1, 30, 31, 60, 61, 90, 91, 180, 181
        test_records = [
            {"Customer": "C1", "CustomerName": "Cust 1", "OpenAmount": "100.00", "DaysOverdue": -1},
            {"Customer": "C2", "CustomerName": "Cust 2", "OpenAmount": "200.00", "DaysOverdue": 0},
            {"Customer": "C3", "CustomerName": "Cust 3", "OpenAmount": "300.00", "DaysOverdue": 1},
            {"Customer": "C4", "CustomerName": "Cust 4", "OpenAmount": "400.00", "DaysOverdue": 30},
            {"Customer": "C5", "CustomerName": "Cust 5", "OpenAmount": "500.00", "DaysOverdue": 31},
            {"Customer": "C6", "CustomerName": "Cust 6", "OpenAmount": "600.00", "DaysOverdue": 60},
            {"Customer": "C7", "CustomerName": "Cust 7", "OpenAmount": "700.00", "DaysOverdue": 61},
            {"Customer": "C8", "CustomerName": "Cust 8", "OpenAmount": "800.00", "DaysOverdue": 90},
            {"Customer": "C9", "CustomerName": "Cust 9", "OpenAmount": "900.00", "DaysOverdue": 91},
            {"Customer": "C10", "CustomerName": "Cust 10", "OpenAmount": "1000.00", "DaysOverdue": 180},
            {"Customer": "C11", "CustomerName": "Cust 11", "OpenAmount": "1100.00", "DaysOverdue": 181},
            {"Customer": "C12", "CustomerName": "Cust 12", "OpenAmount": "50.00", "DaysOverdue": None},
        ]
        res = calculate_aging_buckets(test_records, is_receivable=True)
        buckets = res["buckets"]
        self.assertEqual(buckets["not_yet_due"]["amount"], Decimal("100.00"))
        self.assertEqual(buckets["due_today"]["amount"], Decimal("200.00"))
        self.assertEqual(buckets["bucket_1_30"]["amount"], Decimal("700.00"))
        self.assertEqual(buckets["bucket_31_60"]["amount"], Decimal("1100.00"))
        self.assertEqual(buckets["bucket_61_90"]["amount"], Decimal("1500.00"))
        self.assertEqual(buckets["bucket_91_180"]["amount"], Decimal("1900.00"))
        self.assertEqual(buckets["bucket_over_180"]["amount"], Decimal("1100.00"))
        self.assertEqual(buckets["unaged"]["amount"], Decimal("50.00"))
        
        # Verify reconciliation
        expected_total = sum(Decimal(r["OpenAmount"]) for r in test_records)
        self.assertEqual(res["total_open_signed"], expected_total)
        self.assertEqual(res["bucket_sum"], expected_total)

    def test_c13_signed_credit_handling_no_universal_abs(self):
        records = [
            {"Customer": "C1", "CustomerName": "Cust 1", "OpenAmount": "1000.00", "DaysOverdue": 10},
            {"Customer": "C2", "CustomerName": "Cust 2", "OpenAmount": "-200.00", "DaysOverdue": 5},  # Credit note
        ]
        res = calculate_aging_buckets(records, is_receivable=True)
        self.assertEqual(res["total_open_signed"], Decimal("800.00"))
        self.assertEqual(res["gross_debit"], Decimal("1000.00"))
        self.assertEqual(res["gross_credit"], Decimal("-200.00"))
        self.assertEqual(res["overdue_exposure"], Decimal("1000.00"))

    def test_c15_c16_budget_transfer_classification(self):
        records = [
            {
                "BudgetChangeDocument": "1000001",
                "BudgetAmountInTransactionCrcy": "50000.00",
                "BudgetingProcess": "ENTR",
                "BudgetMovementType": "ENTR",
                "BudgetingProcessText": "Original Budget",
            },
            {
                "BudgetChangeDocument": "1000002",
                "BudgetAmountInTransactionCrcy": "15000.00",
                "BudgetingProcess": "TRAN",
                "BudgetMovementType": "TRAN",
            },
        ]
        res = calculate_budget_movements(records)
        cats = res["categories"]
        self.assertEqual(cats["ORIGINAL_BUDGET"]["amount"], Decimal("50000.00"))
        self.assertEqual(cats["ORIGINAL_BUDGET"]["count"], 1)
        self.assertEqual(cats["TRANSFER"]["amount"], Decimal("15000.00"))
        self.assertEqual(cats["TRANSFER"]["count"], 1)
        self.assertEqual(res["total_movement_amount"], Decimal("65000.00"))

    def test_c18_c21_budget_consumption_raw_measures_and_zero_budget(self):
        records = [
            {
                "FundsCenter": "FC01",
                "BudgetAmountInFMACrcy": "0.00",
                "ActualAmountInFMACrcy": "-5000.00",
                "CmtmtOpenItemAmountInFMACrcy": "1000.00",
                "CtrlgItemAmountInFMACrcy": "0.00",
            }
        ]
        # Unapproved mapping -> raw measures only, configuration required
        raw_res = calculate_budget_consumption(records, mapping_approved=False)
        self.assertEqual(raw_res["raw_budget"], Decimal("0.00"))
        self.assertEqual(raw_res["raw_actuals"], Decimal("-5000.00"))
        self.assertEqual(raw_res["raw_commitments"], Decimal("1000.00"))
        self.assertNotIn("utilization_pct", raw_res)

        # Approved mapping with 0 budget -> no division by zero
        appr_res = calculate_budget_consumption(records, mapping_approved=True)
        self.assertIsNone(appr_res["utilization_pct"])
        self.assertEqual(appr_res["variance"], Decimal("-5000.00"))


class ToolAndServerTests(unittest.IsolatedAsyncioTestCase):
    def test_c24_active_tools_in_registry(self):
        tool_names = [item[0] for item in tools.TOOL_SPECS]
        self.assertIn("s4__get_receivables_aging", tool_names)
        self.assertIn("s4__get_payables_aging", tool_names)
        self.assertIn("s4__get_budget_consumption", tool_names)
        self.assertIn("s4__get_budget_transfers", tool_names)
        # P&L is excluded from discovery
        self.assertNotIn("s4__get_profit_and_loss", tool_names)

    async def test_c25_old_profit_and_loss_returns_unsupported_without_sap_query(self):
        res = await tools.s4__get_profit_and_loss()
        self.assertIsInstance(res, CallToolResult)
        self.assertTrue(res.isError)
        self.assertEqual(res.structuredContent["code"], ReportStatus.UNSUPPORTED_OPERATION.value)
        self.assertIn("excluded", res.structuredContent["message"])

    async def test_budget_transfers_queries_sap_and_calculates_movements(self):
        original = tools.client
        fake = CapturingClient(return_rows=[
            {
                "BudgetChangeDocument": "DOC001",
                "FinancialManagementArea": "1000",
                "FundsCenter": "FC01",
                "TransactionCurrency": "AED",
                "BudgetAmountInTransactionCrcy": "50000.00",
                "BudgetingProcess": "TRAN",
                "BudgetMovementType": "TRAN",
            }
        ])
        tools.client = fake
        try:
            res = await tools.s4__get_budget_transfers(financial_management_area="1000", funds_center="FC01")
            self.assertIsInstance(res, CallToolResult)
            self.assertFalse(res.isError)
            self.assertEqual(res.structuredContent["status"], "COMPLETE")
            self.assertIn("calculations", res.structuredContent)
            self.assertEqual(res.structuredContent["calculations"]["currency"], "AED")
            self.assertEqual(fake.calls[0][0], "BudgetTransfer")
        finally:
            tools.client = original

    async def test_c04_currency_fields_mapped_correctly(self):
        original = tools.client
        fake = CapturingClient()
        tools.client = fake
        try:
            # AR uses CompanyCodeCurrency
            await tools.s4__get_receivables_aging(currency="AED")
            ar_filters = fake.calls[-1][1]["$filter"]
            self.assertIn("CompanyCodeCurrency eq 'AED'", ar_filters)

            # AP uses DisplayCurrency
            await tools.s4__get_payables_aging(currency="USD")
            ap_filters = fake.calls[-1][1]["$filter"]
            self.assertIn("DisplayCurrency eq 'USD'", ap_filters)

            # Budget Consumption uses FinancialManagementAreaCrcy
            await tools.s4__get_budget_consumption(currency="EUR")
            cons_filters = fake.calls[-1][1]["$filter"]
            self.assertIn("FinancialManagementAreaCrcy eq 'EUR'", cons_filters)
        finally:
            tools.client = original

    async def test_c14_historical_key_date_rejected(self):
        res = await tools.s4__get_receivables_aging(company_code="1000", key_date="2020-01-01")
        self.assertTrue(res.isError)
        self.assertEqual(res.structuredContent["code"], ReportStatus.HISTORICAL_DATA_UNAVAILABLE.value)

    async def test_c26_budget_variance_compatibility_adapter(self):
        original = tools.client
        fake = CapturingClient()
        tools.client = fake
        try:
            res = await tools.s4__get_budget_variance(
                company_code="1000",
                fiscal_year="2026",
                fiscal_period="008",
                plan_version="0",
            )
            self.assertEqual(res.structuredContent["type"], "BudgetConsumption")
            cons_filters = fake.calls[-1][1]["$filter"]
            self.assertIn("FinMgmtAreaFiscalYear eq '2026'", cons_filters)
            self.assertIn("FinMgmtAreaPeriod eq '008'", cons_filters)
        finally:
            tools.client = original

    async def test_c28_budget_consumption_summary_entity_and_alias(self):
        from s4hana_mcp.settings import Settings
        s = Settings()
        self.assertEqual(s.s4_budget_consumption_entity, "BudgetConsumSummary")

        handler = server.resolve_tool_handler("BudgetConsumSummary")
        self.assertIsNotNone(handler)
        self.assertEqual(handler[0], "s4__get_budget_consumption")

        handler2 = server.resolve_tool_handler("getBudgetConsumptionSummary")
        self.assertIsNotNone(handler2)
        self.assertEqual(handler2[0], "s4__get_budget_consumption")

        bt_handler = server.resolve_tool_handler("BudgetTransfer")
        self.assertIsNotNone(bt_handler)
        self.assertEqual(bt_handler[0], "s4__get_budget_transfers")

        ar_handler = server.resolve_tool_handler("ARageingData")
        self.assertIsNotNone(ar_handler)
        self.assertEqual(ar_handler[0], "s4__get_receivables_aging")

        ap_handler = server.resolve_tool_handler("APageingData")
        self.assertIsNotNone(ap_handler)
        self.assertEqual(ap_handler[0], "s4__get_payables_aging")

        original = tools.client
        fake = CapturingClient(return_rows=[
            {
                "FinancialManagementArea": "1000",
                "FundsCenter": "FC01",
                "FinancialManagementAreaCrcy": "AED",
                "BudgetAmountInFMACrcy": "1000000.00",
                "ActualAmountInFMACrcy": "450000.00",
                "CmtmtOpenItemAmountInFMACrcy": "150000.00",
            }
        ])
        fake.settings.s4_budget_consumption_entity = "BudgetConsumSummary"
        tools.client = fake
        try:
            res = await tools.s4__get_budget_consumption(financial_management_area="1000", currency="AED")
            self.assertEqual(fake.calls[-1][0], "BudgetConsumSummary")
            self.assertFalse(res.isError)
            calc = res.structuredContent["calculations"]
            self.assertEqual(calc["raw_budget"], Decimal("1000000.00"))
            self.assertEqual(calc["raw_actuals"], Decimal("450000.00"))
            self.assertEqual(calc["raw_commitments"], Decimal("150000.00"))
        finally:
            tools.client = original

    async def test_c27_structured_content_and_cards(self):
        original = tools.client
        fake = CapturingClient(return_rows=[
            {"Customer": "C1", "CustomerName": "Client 1", "OpenAmount": "500.00", "DaysOverdue": 15}
        ])
        tools.client = fake
        try:
            res = await tools.s4__get_receivables_aging(company_code="1000")
            struct = res.structuredContent
            self.assertEqual(struct["type"], "ReceivablesAging")
            self.assertIn("adaptiveCard", struct)
            self.assertEqual(struct["adaptiveCard"]["type"], "AdaptiveCard")
            self.assertEqual(struct["cardTitle"], "Receivables aging")
            # Plain language text summary includes source note
            text = res.content[0].text
            self.assertIn("Finance's customer open-invoice report in SAP", text)
        finally:
            tools.client = original


class MiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def _invoke(self, headers):
        called = False
        messages = []

        async def downstream(_scope, _receive, send):
            nonlocal called
            called = True
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = server.ApiKeyMiddleware(downstream)

        async def send(message):
            messages.append(message)

        await middleware({"type": "http", "path": "/mcp", "headers": headers}, lambda: None, send)
        return called, messages

    async def test_api_key_auth(self):
        original = server.settings
        server.settings = SimpleNamespace(allow_anonymous=False, mcp_api_key="test-secret")
        try:
            called, messages = await self._invoke([])
            self.assertFalse(called)
            self.assertEqual(messages[0]["status"], 401)
            called, _ = await self._invoke([(b"x-api-key", b"test-secret")])
            self.assertTrue(called)
        finally:
            server.settings = original


class AppRouteTests(unittest.TestCase):
    def test_routes_registered_correctly(self):
        app = server.create_app()
        route_paths = {getattr(route, "path", "") for route in app.routes}
        self.assertIn("/mcp/tools", route_paths)
        self.assertIn("/s4__get_receivables_aging", route_paths)
        self.assertIn("/s4__get_payables_aging", route_paths)
        self.assertIn("/s4__get_budget_transfers", route_paths)
        self.assertIn("/s4__get_budget_consumption", route_paths)
        self.assertIn("/s4__get_profit_and_loss", route_paths)  # legacy route preserved for clear error
        self.assertIn("/", route_paths)


if __name__ == "__main__":
    unittest.main()
