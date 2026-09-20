import base64, hashlib, hmac, json, time
import pytest
from shared_mcp.identity import verify_bearer_token, AuthenticationError
from productivity_mcp.token_manager import get_hmac_secret


def token(payload):
    enc=lambda x:base64.urlsafe_b64encode(json.dumps(x).encode()).decode().rstrip('=')
    body=enc({'alg':'HS256'})+'.'+enc(payload)
    return body+'.'+base64.urlsafe_b64encode(hmac.new(b'synthetic-test-key',body.encode(),hashlib.sha256).digest()).decode().rstrip('=')


@pytest.mark.parametrize('bad', [{'exp':float('nan')},{'exp':float('inf')},{'nbf':'tomorrow'}, {'roles':[{}]}, {'oid':123}])
def test_malformed_claims_fail_closed(monkeypatch,bad):
    monkeypatch.delenv('VELORA_ENV',raising=False)
    payload={'tid':'tenant','aud':'aud','oid':'alice','iss':'https://login.microsoftonline.com/tenant/v2.0','exp':time.time()+60,**bad}
    with pytest.raises(AuthenticationError):
        verify_bearer_token(token(payload),expected_tenant_id='tenant',expected_audience='aud',test_secret='synthetic-test-key')


@pytest.mark.parametrize('env', ['VELORA_ENV','ENVIRONMENT','NODE_ENV'])
def test_production_cannot_use_offline_approval_key(monkeypatch,env):
    monkeypatch.setenv(env,'prod')
    monkeypatch.setenv('ALLOW_OFFLINE_TEST_TOKENS','true')
    monkeypatch.delenv('VELORA_APPROVAL_HMAC_SECRET',raising=False)
    with pytest.raises(ValueError):get_hmac_secret()
