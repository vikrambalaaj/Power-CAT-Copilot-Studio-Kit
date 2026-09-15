"""Offline reproduction of interruption after provider acceptance."""
import os,sys,tempfile,socket,json,sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
root=Path(__file__).resolve().parents[2];out=Path(__file__).resolve().parent
temp=tempfile.mkdtemp(prefix='velora-recovery-check-')
os.environ.clear();os.environ.update(PYTHON_DOTENV_DISABLED='1',VELORA_OUTBOX_DIR=temp,VELORA_STATE_DIR=temp,AZURE_STORAGE_MOUNT_PATH=temp)
socket.socket.connect=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('OFFLINE_NETWORK_BLOCKED'))
from pydantic_settings.sources import DotEnvSettingsSource
DotEnvSettingsSource._read_env_files=lambda self:{}
sys.path.insert(0,str(root/'mcp-apps/ask-productivity'))
from productivity_mcp import worker
from productivity_mcp.subscription_service import SubscriptionService
from productivity_mcp.evidence_contracts import SubscriptionKind
store=SubscriptionService(temp+'/subs.db')
sub=SimpleNamespace(enabled=True,kind=SubscriptionKind.MORNING,subscriptionId='synthetic-sub',channel='EMAIL',version='1',mailbox='review@example.invalid',recipients=['review@example.invalid'])
store.list_active_subscriptions=lambda **kw:[sub]
brief=SimpleNamespace(get_morning_briefing=lambda *a,**k:{'date':'synthetic','renderedHtml':'synthetic','contentHash':'synthetic'})
class Provider:
    accepted=0
    def execute_send_email(self,**kw):
        self.accepted+=1
        if self.accepted==1:
            raise SystemExit('Synthetic process termination after provider accepted the message')
        return {'status':'ACCEPTED','simulated':False,'providerReceipt':{'id':'synthetic-provider-reference'}}
provider=Provider()
with patch.object(worker,'get_subscription_service',return_value=store),patch.object(worker,'get_briefing_service',return_value=brief),patch.object(worker,'is_subscription_due',return_value=(True,'synthetic-run',{'scheduledOccurrence':'synthetic-time'})),patch.object(worker,'check_kill_switch',return_value=None):
    try:worker.evaluate_and_dispatch_subscriptions(provider,tenant_id='synthetic-tenant',require_live_delivery=True)
    except SystemExit:pass
    with sqlite3.connect(store.db_path) as c:
        before=c.execute("SELECT status,details_json FROM subscription_run_history WHERE run_key='synthetic-run'").fetchone()
        c.execute("UPDATE subscription_run_history SET executed_at='2000-01-01T00:00:00+00:00' WHERE run_key='synthetic-run'")
    dispatched=worker.evaluate_and_dispatch_subscriptions(provider,tenant_id='synthetic-tenant',require_live_delivery=True)
result={'provider_acceptances_for_same_run':provider.accepted,'state_after_interruption':before[0],'receipt_stored_after_interruption':'providerReceipt' in before[1],'retry_reported_dispatched':dispatched}
(out/'recovery-probe.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
