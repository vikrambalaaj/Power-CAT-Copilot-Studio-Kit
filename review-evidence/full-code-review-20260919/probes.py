"""Offline boundary probes. Synthetic inputs only; outbound connections blocked."""
import os,sys,socket,tempfile,json,time,asyncio,warnings
from pathlib import Path
from unittest.mock import patch
root=Path(__file__).resolve().parents[2]; out=Path(__file__).parent
keep={k:v for k,v in os.environ.items() if k in {'PATH','LANG','LC_ALL','TMPDIR'}}
os.environ.clear(); os.environ.update(keep)
scratch=Path(tempfile.mkdtemp(prefix='velora-boundary-probes-'))
os.environ.update(PYTHON_DOTENV_DISABLED='1',VELORA_STATE_DIR=str(scratch),VELORA_OUTBOX_DIR=str(scratch/'outbox'),FACILITATOR_STORAGE_DIR=str(scratch/'facilitator'),AZURE_STORAGE_MOUNT_PATH=str(scratch),ALLOW_ANONYMOUS='false',ALLOWED_HOSTS='localhost,localhost:*',TEST_JWT_SECRET='synthetic-review-key-not-a-production-secret',ENTRA_TENANT_ID='review-tenant',ENTRA_INBOUND_AUDIENCE='review-api')
def blocked(*a,**kw): raise RuntimeError('OFFLINE_REVIEW_NETWORK_BLOCKED')
socket.create_connection=blocked; socket.socket.connect=blocked; socket.socket.connect_ex=blocked
from pydantic_settings.sources import DotEnvSettingsSource
DotEnvSettingsSource._read_env_files=lambda self: {}
sys.path.insert(0,str(root/'mcp-apps/ask-facilitator'))
from facilitator_mcp import server,tools,decision_service,decision_audit
from starlette.testclient import TestClient
import jwt
results={}
token=jwt.encode({'tid':'review-tenant','oid':'ordinary-user','aud':'review-api','iss':'https://login.microsoftonline.com/review-tenant/v2.0','scp':'user.read','preferred_username':'ordinary@velora.ae','exp':time.time()+600},os.environ['TEST_JWT_SECRET'],algorithm='HS256')
headers={'Authorization':'Bearer '+token}
async def intercepted(**kwargs): return kwargs
with TestClient(server.app,base_url='http://localhost') as c:
 r=c.post('/get_vendor_performance_history',json={'vendor_id':'v1'})
 results['facilitator_rest_anonymous_status']=r.status_code
 with patch.object(server,'TOOL_SPECS',[('get_vendor_performance_history','probe',intercepted)]):
  r=c.post('/get_vendor_performance_history',headers=headers,json={'vendor_id':'v1','tenant_id':'other-tenant','caller_roles':['AUDITOR'],'caller_entity_scopes':['9999']})
  results['facilitator_rest_identity_forwarding']={'status':r.status_code,'handler_received':r.json()}
 with patch.object(tools,'_export_decision_trail',lambda **kw:kw):
  r=c.post('/export_decision_trail',headers=headers,json={'decision_id':'review-decision'})
  results['facilitator_export_default_role']={'status':r.status_code,'handler_received':r.json()}
 args={k:'x' for k in ['vendor_id','vendor_name','entity_scope','contract_ref','period_start','period_end','event_type','severity','summary','source_doc_ref','original_event_date']}
 with warnings.catch_warnings():
  warnings.simplefilter('ignore',RuntimeWarning)
  r=c.post('/ingest_vendor_performance_record',headers=headers,json=args)
  results['facilitator_sync_async_ingestion']={'status':r.status_code,'response':r.json()}
 h={'Accept':'application/json, text/event-stream','Content-Type':'application/json'}
 r=c.post('/mcp',headers=h,json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'offline-review','version':'1'}}})
 results['facilitator_unauthenticated_mcp_initialize']={'status':r.status_code,'has_initialize_result':'protocolVersion' in r.text}
 sid=r.headers.get('mcp-session-id')
 if sid: h['Mcp-Session-Id']=sid
 c.post('/mcp',headers=h,json={'jsonrpc':'2.0','method':'notifications/initialized'})
 r=c.post('/mcp',headers=h,json={'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'get_facilitator_guide','arguments':{'args':[],'kwargs':{}}}})
 results['facilitator_unauthenticated_mcp_tool']={'status':r.status_code,'body':r.text[:1000]}
results['facilitator_native_tool_schema']=asyncio.run(server.mcp.list_tools())[0].inputSchema
os.environ['VELORA_ENV']='production'; os.environ.pop('VELORA_AUDIT_SIGNING_KEY',None)
results['audit_production_uses_default_key']=decision_audit.get_audit_signing_key()==decision_audit.DEFAULT_SIGNING_KEY
os.environ.pop('VELORA_ENV',None)
async def fake_history(*a,**kw): return {}
with patch.object(decision_service,'get_vendor_history',return_value={'records':[],'totalRecords':0}):
 r=asyncio.run(decision_service.evaluate_vendor_options(candidates=[{'vendor_id':'v1','vendor_name':'Synthetic Vendor','technical_score':90,'commercial_price':100}],tenant_id='review-tenant',db_path=str(scratch/'decision.db')))
 results['vendor_unverified_input_result']=r
# Use the actual standalone Productivity package for worker probes (not its copy).
for name in list(sys.modules):
 if name=='productivity_mcp' or name.startswith('productivity_mcp.'): del sys.modules[name]
sys.path.insert(0,str(root/'mcp-apps/ask-productivity'))
from productivity_mcp import worker
from productivity_mcp.evidence_contracts import SubscriptionKind
from types import SimpleNamespace
subs=[SimpleNamespace(enabled=True,kind=SubscriptionKind.MORNING,subscriptionId='sub-'+who,version='1',mailbox=who+'@velora.ae',recipients=[who+'@velora.ae'],channel='EMAIL') for who in ['alice','bob']]
seen=[]
class Provider:
 user_email='alice@velora.ae'
 def execute_send_email(self,**kw):
  seen.append({'to':kw['to'],'body':kw['body']}); return {'simulated':False,'id':'synthetic-receipt'}
class SubSvc:
 def list_active_subscriptions(self,**kw):return subs
 def is_run_already_executed(self,*a):return False
 def claim_subscription_run(self,**kw):return True
 def complete_subscription_run(self,**kw):pass
class BriefSvc:
 def get_morning_briefing(self,client,user_email,**kw):return {'renderedHtml':'PRIVATE DATA OF '+client.user_email,'contentHash':'synthetic'}
with patch.object(worker,'get_subscription_service',return_value=SubSvc()),patch.object(worker,'get_briefing_service',return_value=BriefSvc()),patch.object(worker,'is_subscription_due',side_effect=lambda **kw:(True,kw['subscription'].subscriptionId,{'scheduledOccurrence':'2026-09-19T08:00:00Z'})):
 results['worker_cross_mailbox']={'dispatched':worker.evaluate_and_dispatch_subscriptions(Provider(),tenant_id='review-tenant',require_live_delivery=True),'deliveries':seen}
from productivity_mcp.subscription_service import SubscriptionService
import sqlite3,datetime
svc=SubscriptionService(db_path=str(scratch/'subs.db'))
claim=dict(run_key='run1',tenant_id='review-tenant',subscription_id='sub1',subscription_version='1',execution_id='worker1',scheduled_occurrence='2026-09-19')
first=svc.claim_subscription_run(**claim)
with sqlite3.connect(svc.db_path) as con: con.execute("UPDATE subscription_run_history SET executed_at=? WHERE run_key='run1'",((datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(minutes=11)).isoformat(),))
claim['execution_id']='worker2'; retry=svc.claim_subscription_run(**claim)
results['subscription_after_send_before_receipt_crash']={'first_claim':first,'reclaimed_without_provider_reconciliation':retry,'explanation':'Row is exactly the persisted state if process dies after provider accepts but before complete_subscription_run.'}
(out/'python-probes.json').write_text(json.dumps(results,indent=2,default=str))
print(json.dumps({k:v for k,v in results.items() if k!='vendor_unverified_input_result'},indent=2,default=str))
