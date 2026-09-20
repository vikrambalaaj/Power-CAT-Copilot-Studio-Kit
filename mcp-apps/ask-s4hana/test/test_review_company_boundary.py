import pytest
from unittest.mock import AsyncMock
from starlette.testclient import TestClient
from s4hana_mcp import server


def test_foreign_company_rejected_without_caller_scope_header(monkeypatch):
    monkeypatch.setattr(server.settings, 'allow_anonymous', False)
    monkeypatch.setattr(server.settings, 'mcp_api_key', 'synthetic-review-key')
    with TestClient(server.app) as client:
        rest = client.post('/tools/s4__get_receivables_aging', headers={'x-api-key':'synthetic-review-key'}, json={'company_code':'9999'})
        assert rest.status_code == 403
        rpc = client.post('/mcp', headers={'x-api-key':'synthetic-review-key'}, json={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'s4__get_budget_transfers','arguments':{'financial_management_area':'9999'}}})
        assert 'error' in rpc.json()
        assert 'entitlement' in rpc.json()['error']['message']


@pytest.mark.asyncio
async def test_native_tool_blocks_company_before_provider():
    async def handler(company_code='1000'): return 'ok'
    wrapped = server._company_scoped_handler(handler)
    with pytest.raises(PermissionError):
        await wrapped(company_code='9999')
    assert await wrapped() == 'ok'
