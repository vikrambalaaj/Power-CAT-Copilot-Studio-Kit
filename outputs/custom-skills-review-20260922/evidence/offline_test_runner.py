import os, sys, tempfile, pathlib, socket
repo=pathlib.Path(__file__).resolve().parents[3]
service=sys.argv[1]
work=pathlib.Path(tempfile.mkdtemp(prefix='velora-skill-review-'+service+'-'))
os.chdir(work)
for k in list(os.environ):
 if k not in ('PATH','LANG','TMPDIR','SYSTEMROOT'): os.environ.pop(k,None)
os.environ.update({'PYTHON_DOTENV_DISABLED':'1','VELORA_ENV':'test','NODE_ENV':'test','ALLOW_OFFLINE_TEST_TOKENS':'1','VELORA_STATE_DIR':str(work),'VELORA_OUTBOX_DIR':str(work/'outbox'),'FACILITATOR_STORAGE_DIR':str(work/'facilitator'),'VELORA_BUSINESS_REPO_DB':str(work/'business.db'),'VELORA_STORAGE_DIR':str(work),'VELORA_APPROVAL_HMAC_SECRET':'isolated-review-tests-only-secret','MCP_API_KEY':'review-tests-only','SF_API_URL':'https://review.invalid','SF_COMPANY_ID':'review','SF_USERNAME':'review','SF_PASSWORD':'review'})
sys.path.insert(0,str(repo/'mcp-apps'/service))
if service=='ask-productivity':
 sys.path.extend([str(repo/'mcp-apps/ask-facilitator'),str(repo/'mcp-apps/ask-s4hana')])
import dotenv
dotenv.load_dotenv=lambda *a,**k:False
dotenv.dotenv_values=lambda *a,**k:{}
original_connect=socket.socket.connect
original_connect_ex=socket.socket.connect_ex
def block_connect(sock,address):
 if sock.family in (socket.AF_INET,socket.AF_INET6): raise OSError('Network disabled for offline source review')
 return original_connect(sock,address)
def block_connect_ex(sock,address):
 if sock.family in (socket.AF_INET,socket.AF_INET6): raise OSError('Network disabled for offline source review')
 return original_connect_ex(sock,address)
socket.socket.connect=block_connect
socket.socket.connect_ex=block_connect_ex
if len(sys.argv)>2 and sys.argv[2] in ('test_graph_read_contracts.py','test_handoff_contract.py'):
 os.environ['MOCK_M365']='1'
 from productivity_mcp.m365_client import seed_test_m365_data
 seed_test_m365_data()
import pytest
raise SystemExit(pytest.main([str(repo/'mcp-apps'/service/'test'/sys.argv[2]) if len(sys.argv)>2 else str(repo/'mcp-apps'/service/'test'),'-q','--tb=short','-p','no:cacheprovider','-c','/dev/null','--import-mode=importlib','-o','asyncio_mode=auto']))
