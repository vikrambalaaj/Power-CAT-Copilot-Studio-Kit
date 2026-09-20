from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from productivity_mcp import worker
from productivity_mcp.evidence_contracts import SubscriptionKind
from productivity_mcp.subscription_service import SubscriptionService


def subscription(kind=SubscriptionKind.MORNING):
    return SimpleNamespace(enabled=True, mailbox='alice@example.test', recipients=['alice@example.test'],
        subscriptionId='sub-a', version='1', channel='EMAIL', kind=kind, localSchedule='07:00')


def setup(monkeypatch, kind=SubscriptionKind.MORNING):
    sub=subscription(kind)
    service=Mock()
    service.list_active_subscriptions.return_value=[sub]
    service.is_run_already_executed.return_value=False
    service.claim_subscription_run.return_value=True
    service.transition_subscription_run.return_value=True
    client=Mock(user_email='alice@example.test')
    client.execute_send_email.return_value={'status':'SENT','providerReceipt':'synthetic-receipt','simulated':False}
    briefing=Mock()
    briefing.get_morning_briefing.return_value={'date':'2026-09-20','renderedHtml':'<p>Brief</p>','contentHash':'hash'}
    monkeypatch.setattr(worker,'get_subscription_service',lambda:service)
    monkeypatch.setattr(worker,'get_briefing_service',lambda:briefing)
    monkeypatch.setattr(worker,'is_subscription_due',lambda **kw:(True,'run-key',{'scheduledOccurrence':'today'}))
    monkeypatch.setattr(worker,'check_kill_switch',lambda **kw:None)
    return service,client,sub


def test_lost_lease_prevents_send(monkeypatch):
    service,client,_=setup(monkeypatch)
    service.transition_subscription_run.return_value=False
    assert worker.evaluate_and_dispatch_subscriptions(client)==0
    client.execute_send_email.assert_not_called()


def test_provider_timeout_requires_reconciliation(monkeypatch):
    service,client,_=setup(monkeypatch)
    client.execute_send_email.side_effect=TimeoutError('Response lost after send')
    assert worker.evaluate_and_dispatch_subscriptions(client)==0
    assert service.complete_subscription_run.call_args.kwargs['status']=='RECONCILIATION_REQUIRED'


def test_reminder_status_matches_evaluator_and_never_sends_other_owners(monkeypatch):
    service,client,sub=setup(monkeypatch,SubscriptionKind.ACTION_REMINDER)
    now=datetime(2026,9,20,tzinfo=timezone.utc)
    from productivity_mcp import meeting_actions
    reminder={'taskId':'task-a','status':'REMINDER_DUE','recipient':sub.mailbox,'subject':'Due','body':'Task <example>', 'dedupRunKey':'task-a:deadline:due','dueDateTime':'2026-09-20T00:00:00Z'}
    monkeypatch.setattr(meeting_actions,'evaluate_meeting_action_reminders',lambda **kw:[reminder,{**reminder,'recipient':'bob@example.test','taskId':'task-b'}])
    client.get_planner_task.return_value={'percentComplete':0,'dueDateTime':reminder['dueDateTime']}
    assert worker.evaluate_and_dispatch_subscriptions(client,now=now)==1
    assert client.execute_send_email.call_count==1
    assert client.execute_send_email.call_args.kwargs['to']==[sub.mailbox]
    assert '&lt;example&gt;' in client.execute_send_email.call_args.kwargs['body']


def test_completed_task_suppressed_after_evaluation(monkeypatch):
    service,client,sub=setup(monkeypatch,SubscriptionKind.ACTION_REMINDER)
    from productivity_mcp import meeting_actions
    monkeypatch.setattr(meeting_actions,'evaluate_meeting_action_reminders',lambda **kw:[{'taskId':'t','status':'REMINDER_DUE','recipient':sub.mailbox,'dedupRunKey':'t:due'}])
    client.get_planner_task.return_value={'percentComplete':100}
    assert worker.evaluate_and_dispatch_subscriptions(client)==0
    client.execute_send_email.assert_not_called()


def test_second_due_meeting_not_starved_by_first(monkeypatch):
    service,client,_=setup(monkeypatch,SubscriptionKind.PRE_MEETING)
    client.list_calendar_events.return_value=[{'id':'done'},{'id':'new'}]
    monkeypatch.setattr(worker,'is_subscription_due',lambda **kw:(True,kw['eligible_events'][0]['id'],{'eventId':kw['eligible_events'][0]['id']}))
    service.is_run_already_executed.side_effect=lambda key:key=='done'
    briefing=Mock()
    briefing.get_pre_meeting_briefing.return_value={'renderedHtml':'Brief','contentHash':'h'}
    monkeypatch.setattr(worker,'get_briefing_service',lambda:briefing)
    assert worker.evaluate_and_dispatch_subscriptions(client)==1
    assert briefing.get_pre_meeting_briefing.call_args.kwargs['event_id']=='new'


def test_skipped_runs_are_terminal(tmp_path):
    service=SubscriptionService(str(tmp_path/'subscriptions.db'))
    args=dict(run_key='k',tenant_id='t',subscription_id='s',subscription_version='1',execution_id='e',scheduled_occurrence='today')
    assert service.claim_subscription_run(**args)
    assert service.complete_subscription_run('k','SKIPPED',execution_id='e')
    assert service.is_run_already_executed('k')
    assert not service.claim_subscription_run(**args)
