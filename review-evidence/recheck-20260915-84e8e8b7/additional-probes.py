"""Offline synthetic verification of production configuration and recovery."""
import os,sys,tempfile,json,time,hmac,hashlib,base64,socket,sqlite3
from pathlib import Path
root=Path(__file__).resolve().parents[2]
out=Path(__file__).resolve().parent
scratch=tempfile.mkdtemp(prefix='velora-recheck-extra-')
os.environ.clear()
os.environ.update(PYTHON_DOTENV_DISABLED='1',VELORA_STATE_DIR=scratch,VELORA_OUTBOX_DIR=scratch,AZURE_STORAGE_MOUNT_PATH=scratch,VELORA_SUBSCRIPTION_DB=scratch+'/subs.db')
socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('OFFLINE_NETWORK_BLOCKED'))
from pydantic_settings.sources import DotEnvSettingsSource
DotEnvSettingsSource._read_env_files=lambda self:{}
sys.path.insert(0,str(root/'mcp-apps/ask-productivity'))
from shared_mcp.identity import verify_bearer_token
enc=lambda x:base64.urlsafe_b64encode(json.dumps(x).encode()).decode().rstrip('=')
key='synthetic-test-key'
payload={'tid':'synthetic-tenant','oid':'synthetic-user','aud':'https://api.velora.ae','iss':'https://test.example.invalid','exp':time.time()+300,'scp':'user_impersonation'}
raw=enc({'alg':'HS256'})+'.'+enc(payload)
token=raw+'.'+base64.urlsafe_b64encode(hmac.new(key.encode(),raw.encode(),hashlib.sha256).digest()).decode().rstrip('=')
os.environ.update(VELORA_ENV='production',TEST_JWT_SECRET=key,ENTRA_TENANT_ID='synthetic-tenant')
results={}
try:
 verify_bearer_token(token)
 results['velora_env_production_test_key']='ACCEPTED'
except Exception as e: results['velora_env_production_test_key']=type(e).__name__
os.environ.pop('VELORA_ENV')
try:
 verify_bearer_token(token,expected_audience='required-specific-api')
 results['explicit_audience_override']='ACCEPTED_OTHER_AUDIENCE'
except Exception as e:results['explicit_audience_override']=type(e).__name__
os.environ.pop('TEST_JWT_SECRET')
from productivity_mcp.subscription_service import SubscriptionService
s=SubscriptionService(scratch+'/subscriptions.db')
args=dict(run_key='synthetic-run',tenant_id='tenant',subscription_id='sub',subscription_version='1',execution_id='exec',scheduled_occurrence='synthetic')
first=s.claim_subscription_run(**args)
with sqlite3.connect(s.db_path) as c:
 c.execute("UPDATE subscription_run_history SET executed_at='2000-01-01T00:00:00+00:00'")
already=s.is_run_already_executed('synthetic-run')
retry=s.claim_subscription_run(**args)
results['expired_subscription_claim']={'firstClaimed':first,'alreadyExecutedAfterExpiry':already,'retryClaimed':retry}
(out/'additional-python-probes.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
