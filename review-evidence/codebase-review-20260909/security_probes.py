"""Offline review probes. Synthetic credentials; never call external services."""
import os,sys,tempfile,json,asyncio,time,hashlib,hmac,base64,socket
from pathlib import Path
from unittest.mock import patch,AsyncMock
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
os.environ.clear()
os.environ.update(PATH='/usr/bin:/bin',HOME=tempfile.mkdtemp(),PYTHON_DOTENV_DISABLED='1')
from pydantic_settings.sources import DotEnvSettingsSource
DotEnvSettingsSource._read_env_files=lambda self:{}
socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('NETWORK_BLOCKED'))
for service in ['ask-productivity','ask-successfactors','ask-facilitator']:
 sys.path.insert(0,str(ROOT/'mcp-apps'/service))
os.chdir(tempfile.mkdtemp())
import shared_mcp
shared_mcp.__path__.append(str(ROOT/'mcp-apps/ask-productivity/shared_mcp'))
from shared_mcp import identity
results=[]
def record(name, observation, expected): results.append(dict(probe=name,observed=observation,expected=expected))
secret='synthetic-review-signing-key'
os.environ.update(TEST_JWT_SECRET=secret,ENTRA_TENANT_ID='review-tenant',API_AUDIENCE='review-api',VELORA_ENV='production')
payload={'tid':'review-tenant','oid':'review-user','aud':'review-api','exp':time.time()+300,'scp':'user_impersonation','iss':'https://untrusted.test.invalid'}
enc=lambda o:base64.urlsafe_b64encode(json.dumps(o).encode()).decode().rstrip('=')
raw=enc({'alg':'HS256'})+'.'+enc(payload)
token=raw+'.'+base64.urlsafe_b64encode(hmac.new(secret.encode(),raw.encode(),hashlib.sha256).digest()).decode().rstrip('=')
try:
 identity.verify_bearer_token(token)
 record('production_test_key_and_wrong_issuer','ACCEPTED','REJECT')
except Exception as e:record('production_test_key_and_wrong_issuer',type(e).__name__,'REJECT')
os.environ['GATEWAY_AUTH_SECRET']=secret
stamp=str(time.time()); nonce='review-legacy-nonce'
headers={'x-gateway-timestamp':stamp,'x-gateway-nonce':nonce,'x-gateway-tenant-id':'review-tenant','x-gateway-user-id':'review-user'}
canonical=f'{stamp}:{nonce}::review-tenant:review-user:'
headers['x-gateway-signature']=hmac.new(secret.encode(),canonical.encode(),hashlib.sha256).hexdigest()
try:
 identity.verify_gateway_assertion(headers,method='POST',path='/changed-path',body=b'changed body')
 record('legacy_signature_with_changed_request','ACCEPTED','REJECT')
except Exception as e:record('legacy_signature_with_changed_request',type(e).__name__,'REJECT')
from productivity_mcp.operation_store import SqliteOperationStore,PostgresOperationStore
required=['get_operation','approve_operation','claim_execution','mark_succeeded','mark_failed']
record('postgres_store_interface',{'sqlite_methods':[n for n in dir(SqliteOperationStore) if not n.startswith('_')], 'postgres_methods':[n for n in dir(PostgresOperationStore) if not n.startswith('_')]},'Equivalent complete approval lifecycle')
from productivity_mcp.m365_client import Microsoft365Client
client=Microsoft365Client('review@example.invalid'); client.graph_access_token='synthetic-not-real';client.force_mock=False
record('live_name_resolution_without_provider',client.resolve_recipients(['Ahmed Al Nuaimi']),'Provider resolution or unavailable; no hardcoded person')
from productivity_mcp.dataverse_audit import DataverseClient as PClient
from successfactors_mcp.dataverse_audit import DataverseClient as SClient,DataverseAuditRecord
async def run():
 import httpx
 response=httpx.Response(200,json={'access_token':'synthetic-result','expires_in':3600},request=httpx.Request('POST','https://example.invalid'))
 for klass in [PClient,SClient]:
  client=klass(base_url='https://example.invalid',tenant_id='review-tenant',client_id='review-client',client_secret='synthetic-old-secret',auth_type='FederatedCredential',federated_token_file='/missing/review-token')
  with patch('httpx.AsyncClient.post',new_callable=AsyncMock,return_value=response) as post:
   try:
    await client._get_access_token()
    record(klass.__module__+'.missing_assertion',{'used_client_secret': 'client_secret' in post.call_args.kwargs['data']},'Raise before token request; no secret fallback')
   except Exception as e:record(klass.__module__+'.missing_assertion',type(e).__name__,'Raise before token request; no secret fallback')
 c=SClient();r=DataverseAuditRecord(record_type='TOOL_EXECUTION_END',user_email='review@example.invalid',invocation_id='review-buffered-only')
 a=await c.create_audit_record(r);b=await c.create_audit_record(r)
 record('buffered_duplicate_commit_status',{'first':a.get('commit_status'),'retry':b.get('commit_status')},'Both BUFFERED until durable provider commit')
 from facilitator_mcp.server import _wrap_tool_handler
 async def safe_handler():return 'HANDLER_REACHED'
 record('facilitator_mcp_wrapper_without_identity',await _wrap_tool_handler('read_example',safe_handler)(),'Reject missing identity before handler')
 from facilitator_mcp.tools import send_executive_email_via_graph
 with patch('urllib.request.urlopen',side_effect=RuntimeError('TOKEN_REQUEST_REACHED')):
  try:
   receipt=send_executive_email_via_graph(['review@velora.ae'],'Review probe','Synthetic content',confirmation_token='not-a-valid-approval')
   observation={'status':receipt.get('status'),'delivery_mode':receipt.get('delivery_mode'),'invented_message_id':bool(receipt.get('message_id')),'invented_link':bool(receipt.get('web_link'))}
  except RuntimeError as e:observation=str(e)
 record('facilitator_nonempty_approval',observation,'Reject invalid approval before provider token request')
 c2=SClient();r2=DataverseAuditRecord(record_type='TRANSACTION_START',user_email='review@example.invalid',invocation_id='review-write-retry',operation='SEND_EMAIL')
 first=await c2.start_write_transaction_fail_closed(r2);second=await c2.start_write_transaction_fail_closed(r2)
 record('buffered_write_retry_permission',{'first':first['may_proceed'],'retry':second['may_proceed']},'Both false without durable commit')
asyncio.run(run())
(OUT/'security-probe-results.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
