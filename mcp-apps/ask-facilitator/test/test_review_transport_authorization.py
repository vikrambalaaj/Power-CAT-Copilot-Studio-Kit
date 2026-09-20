"""Both external transports must enforce the same verified caller boundary."""
import hashlib
import hmac
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from starlette.testclient import TestClient
from facilitator_mcp import server
from shared_mcp.identity import VerifiedIdentity, AuthorizationError


def identity(roles=(), scopes=()):
    return VerifiedIdentity('tenant-a', 'alice', 'user', 'client', roles=set(roles), scopes=set(scopes))


@pytest.mark.asyncio
async def test_native_mcp_rejects_forged_tenant_and_roles(monkeypatch):
    async def handler(tenant_id='default', caller_roles=None):
        return {'tenant': tenant_id, 'roles': caller_roles}
    ctx = SimpleNamespace(request_context=SimpleNamespace(request=SimpleNamespace(state=SimpleNamespace(identity=identity()))))
    monkeypatch.setattr(server.mcp, 'get_context', lambda: ctx)
    wrapped = server._wrap_tool_handler('get_vendor_performance_history', handler)
    with pytest.raises(AuthorizationError):
        await wrapped(tenant_id='tenant-b')
    with pytest.raises(AuthorizationError):
        await wrapped(caller_roles=['AUDITOR'])
    assert await wrapped() == {'tenant': 'tenant-a', 'roles': []}


def test_entity_scope_must_be_subset_not_single_overlap():
    def handler(caller_entity_scopes=None): pass
    with pytest.raises(AuthorizationError):
        server._authorize_arguments('read', handler, {'caller_entity_scopes': ['allowed', 'foreign']}, identity(scopes=['allowed']))


def test_gateway_assertion_binds_actual_request_and_is_consumed_once(monkeypatch):
    monkeypatch.setenv('ALLOW_ANONYMOUS', 'false')
    monkeypatch.setenv('GATEWAY_AUTH_SECRET', 'synthetic-review-key')
    monkeypatch.delenv('TEST_JWT_SECRET', raising=False)
    def headers(path, nonce):
        ts = str(time.time())
        canonical = f"GET:{path}:{hashlib.sha256(b'').hexdigest()}:{ts}:{nonce}::tenant-a:alice:alice@example.test:"
        return {'x-gateway-timestamp': ts, 'x-gateway-nonce': nonce, 'x-gateway-tenant-id': 'tenant-a',
                'x-gateway-user-id':'alice','x-gateway-user-email':'alice@example.test',
                'x-gateway-signature':hmac.new(b'synthetic-review-key',canonical.encode(),hashlib.sha256).hexdigest()}
    with TestClient(server.app) as client:
        assert client.get('/guide', headers=headers('/different', 'tampered')).status_code == 401
        valid = headers('/guide', 'valid-'+str(time.time()))
        assert client.get('/guide', headers=valid).status_code == 200
        assert client.get('/guide', headers=valid).status_code == 401
