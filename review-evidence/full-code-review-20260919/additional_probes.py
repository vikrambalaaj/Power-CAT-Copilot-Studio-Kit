"""Synthetic identity and provider-boundary probes; no external connections."""
import os,sys,socket,tempfile,time,json,hashlib,hmac,asyncio
from pathlib import Path
from unittest.mock import patch,AsyncMock
root=Path(__file__).resolve().parents[2];out=Path(__file__).parent
retain={k:v for k,v in os.environ.items() if k in {'PATH','LANG','LC_ALL','TMPDIR'}}
os.environ.clear();os.environ.update(retain)
scratch=tempfile.mkdtemp(prefix='velora-extra-probes-')
os.environ.update(PYTHON_DOTENV_DISABLED='1',VELORA_STATE_DIR=scratch,FACILITATOR_STORAGE_DIR=scratch,AZURE_STORAGE_MOUNT_PATH=scratch,MCP_API_KEY='synthetic-review-api-key',ALLOW_ANONYMOUS='false')
def blocked(*a,**kw):raise RuntimeError('OFFLINE_REVIEW_NETWORK_BLOCKED')
socket.create_connection=blocked;socket.socket.connect=blocked;socket.socket.connect_ex=blocked
from pydantic_settings.sources import DotEnvSettingsSource
DotEnvSettingsSource._read_env_files=lambda self:{}
from starlette.testclient import TestClient
mode=sys.argv[1];results={}
if mode=='gateway':
 sys.path.insert(0,str(root/'mcp-apps/ask-productivity'))
 from shared_mcp import identity
 os.environ['GATEWAY_AUTH_SECRET']='synthetic-gateway-secret'
 ts=str(time.time());nonce='review-nonce'
 headers={'x-gateway-timestamp':ts,'x-gateway-nonce':nonce,'x-gateway-tenant-id':'review-tenant','x-gateway-user-id':'alice-id','x-gateway-user-email':'alice@velora.ae','x-user-roles':'USER'}
 legacy=f'{ts}:{nonce}::review-tenant:alice-id:USER'
 headers['x-gateway-signature']=hmac.new(os.environ['GATEWAY_AUTH_SECRET'].encode(),legacy.encode(),hashlib.sha256).hexdigest()
 headers['x-gateway-user-email']='bob@velora.ae'
 ident=identity.verify_gateway_assertion(headers,method='POST',path='/different-operation',body=b'{"changed":true}')
 results['legacy_assertion_accepted_for_modified_request']={'object_id':ident.object_id,'email':ident.display_email,'changed_method_path_body_accepted':True,'unsigned_email_change_accepted':ident.display_email=='bob@velora.ae'}
elif mode=='s4':
 sys.path.insert(0,str(root/'mcp-apps/ask-s4hana'))
 from s4hana_mcp import server,tools
 query=AsyncMock(return_value={'status':'error','message':'synthetic stop after boundary'})
 with TestClient(server.app) as c,patch.object(tools.client,'query',query):
  r=c.post('/tools/s4__get_receivables_aging',headers={'x-api-key':'synthetic-review-api-key','x-organization-scope':'1000'},json={'company_code':'9999'})
  results={'http_status':r.status_code,'provider_calls':query.await_count,'provider_args':query.await_args.args if query.await_args else None,'response':r.json()}
elif mode=='productivity':
 sys.path.insert(0,str(root/'mcp-apps/ask-productivity'))
 os.environ.update(TEST_JWT_SECRET='synthetic-review-key',ENTRA_TENANT_ID='review-tenant',ENTRA_INBOUND_AUDIENCE='review-api')
 from productivity_mcp import server
 import jwt
 token=jwt.encode({'tid':'review-tenant','oid':'ordinary-user','aud':'review-api','iss':'https://login.microsoftonline.com/review-tenant/v2.0','scp':'user.read','preferred_username':'ordinary@velora.ae','exp':time.time()+600},os.environ['TEST_JWT_SECRET'],algorithm='HS256')
 probe=AsyncMock(return_value={'status':'SUCCESS','approvalRequired':False,'resultSummary':'synthetic','auditStatus':'PERSISTED'})
 with TestClient(server.app) as c,patch.object(server,'evaluate_verified_kpi_snapshot',probe):
  r=c.post('/handoff',headers={'Authorization':'Bearer '+token},json={'task':'Synthetic offline review','tenantId':'other-tenant','operation':'EVALUATE_VERIFIED_KPI_SNAPSHOT','userObjectId':'ordinary-user','userEmail':'ordinary@velora.ae','rootCorrelationId':'review','conversationId':'review','turnId':'review','parameters':{'tenantId':'other-tenant','callerRole':'WORKLOAD_AUTHORIZED','snapshot':{}}})
  results={'status':r.status_code,'handler_kwargs':probe.await_args.kwargs if probe.await_args else None,'response':r.json()}
elif mode=='zero':
 sys.path.insert(0,str(root/'mcp-apps/ask-productivity'))
 from productivity_mcp.tools_recommendations import evaluate_verified_kpi_snapshot
 results=asyncio.run(evaluate_verified_kpi_snapshot({'value':0,'kpi_code':'SYNTHETIC_ZERO'}))
elif mode=='sac':
 sys.path.insert(0,str(root/'mcp-apps/ask-sac'))
 from sac_mcp import server
 with TestClient(server.app) as c:
  r=c.post('/mcp',headers={'x-api-key':'synthetic-review-api-key','Accept':'application/json, text/event-stream'},json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'offline-review','version':'1'}}})
  results={'initialize_status':r.status_code,'response':r.json()}
elif mode=='sf':
 sys.path.insert(0,str(root/'mcp-apps/ask-successfactors'))
 from successfactors_mcp import successfactors_server as server
 from successfactors_mcp import memory_service,consent_service
 from types import SimpleNamespace
 recall=AsyncMock(return_value={'synthetic':True});record=AsyncMock(return_value={'synthetic':True})
 with TestClient(server.create_app()) as c,patch.object(memory_service,'get_memory_service',return_value=SimpleNamespace(recall_user_context=recall)),patch.object(consent_service,'get_consent_service',return_value=SimpleNamespace(record_user_consent=record)):
  r=c.get('/api/memory',headers={'x-api-key':'synthetic-review-api-key'},params={'user_object_id':'victim-id','user_email':'victim@velora.ae'})
  results['memory']={'status':r.status_code,'provider_calls':recall.await_count,'provider_args':recall.await_args.args if recall.await_args else None}
  r=c.post('/api/consent',headers={'x-api-key':'synthetic-review-api-key'},json={'user_object_id':'victim-id','user_email':'victim@velora.ae','accepted':'false'})
  results['consent']={'status':r.status_code,'provider_calls':record.await_count,'provider_kwargs':record.await_args.kwargs if record.await_args else None}
(out/(mode+'-probes.json')).write_text(json.dumps(results,indent=2,default=str));print(json.dumps(results,indent=2,default=str))
