"""Offline regression checks for the proposed cleanup; no provider imports/calls."""
import ast
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('cleanup', HERE/'remove_runtime_demo_data.py')
cleanup=importlib.util.module_from_spec(spec);spec.loader.exec_module(cleanup)

def isolated_node(source, name):
    t=ast.parse(source)
    node=next(n for n in t.body if getattr(n,'name',None)==name)
    module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),node],type_ignores=[])
    ast.fix_missing_locations(module)
    ns={'os':os,'datetime':datetime,'timezone':timezone}
    exec(compile(module,'<offline-cleanup-test>','exec'),ns)
    return ns

class CleanupTests(unittest.TestCase):
    def test_preview_apply_and_drift_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for rel in cleanup.TARGETS:
                p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/rel).read_bytes())
            manifest=root/'plan.json'
            command=[sys.executable,str(HERE/'remove_runtime_demo_data.py'),'--root',str(root),'--plan',str(manifest)]
            before={rel:(root/rel).read_bytes() for rel in cleanup.TARGETS}
            subprocess.run(command,check=True,capture_output=True)
            self.assertEqual(before,{rel:(root/rel).read_bytes() for rel in cleanup.TARGETS})
            target=root/next(iter(cleanup.TARGETS));target.write_bytes(target.read_bytes()+b'\n# source drift\n')
            self.assertNotEqual(subprocess.run(command+['--apply'],capture_output=True).returncode,0)
            self.assertEqual(target.read_bytes(),before[next(iter(cleanup.TARGETS))]+b'\n# source drift\n')
            target.write_bytes(before[next(iter(cleanup.TARGETS))])
            subprocess.run(command+['--apply'],check=True,capture_output=True)
            self.assertTrue(manifest.with_suffix('.applied.json').exists())
            for rel,kind in cleanup.TARGETS.items():
                data=(root/rel).read_text();compile(data,rel,'exec')
                self.assertEqual(cleanup.transform(data,kind)[0],data)

    def test_m365_no_credentials_never_returns_simulated_success(self):
        source,_=cleanup.transform((ROOT/next(iter(cleanup.TARGETS))).read_text(),'m365')
        self.assertNotIn('seed_test_m365_data',source)
        self.assertNotIn('_M365_',source)
        self.assertNotIn('MOCK_M365',source)
        self.assertNotIn('APPR-2026-0826',source)
        ns=isolated_node(source,'Microsoft365Client')
        with patch.dict(os.environ,{},clear=True):client=ns['Microsoft365Client']('review@example.invalid')
        for name,args in [
            ('execute_send_email',([],[],'review','review',[])),
            ('execute_create_meeting',('review',[],'a','b','UTC','','')),
            ('execute_update_meeting',('x',{})),('execute_cancel_meeting',('x',)),
            ('execute_post_teams_message',('review',)),
            ('execute_create_planner_task',('p','b','t','d',[],None,'Medium')),
            ('execute_update_planner_task',('x',{})),
            ('search_mail',('x',)),('list_calendar_events',()),('search_teams_messages',()),('list_planner_tasks',()),
            ('list_pending_approvals',()),('get_mail_thread',('x',)),('check_availability',([],'a','b')),
        ]:
            with self.subTest(operation=name):
                with self.assertRaisesRegex(RuntimeError,'SOURCE_UNAVAILABLE'):getattr(client,name)(*args)
        with self.assertRaisesRegex(RuntimeError,'prohibited'):client._create_receipt('SendEmail',True)
        # Existing live branch survives, without sending anything.
        self.assertIn('client.post',source)

    def test_sac_removes_payloads_and_fails_without_token(self):
        rel='mcp-apps/ask-sac/sac_mcp/client.py'
        source,_=cleanup.transform((ROOT/rel).read_text(),'sac')
        self.assertNotIn('Synthetic demonstration data',source)
        self.assertNotIn('settings.demo_mode',source)
        ns=isolated_node(source,'SACClient')
        ns['cache']=type('Cache',(),{'get':lambda self,k:None})()
        client=ns['SACClient']()
        async def no_token():return None
        client.get_token=no_token
        for name,args in [('get_executive_kpis',()),('get_story_analytics',()),('get_model_data',('review',))]:
            with self.subTest(operation=name):
                with self.assertRaisesRegex(RuntimeError,'SOURCE_UNAVAILABLE'):asyncio.run(getattr(client,name)(*args))

    def test_facilitator_and_policy_remove_facts_and_fake_destinations(self):
        source,_=cleanup.transform((ROOT/'mcp-apps/ask-facilitator/facilitator_mcp/tools.py').read_text(),'facilitator')
        for marker in ['2,916','23.8%','2.4M','seed_test_facilitator_data','loop.microsoft.com/p/velora-exec','_CALENDAR_STORE','_DATAVERSE_AUDIT_LOGS']:
            self.assertNotIn(marker,source)
        for name,args in [('generate_pre_meeting_briefing',('review',[])),('export_meeting_to_loop_notebook',('review',[],'',[],[])),('get_calendar_meetings',())]:
            fn=isolated_node(source,name)[name]
            self.assertEqual(fn(*args)['status'],'SOURCE_UNAVAILABLE')
        policy,_=cleanup.transform((ROOT/'mcp-apps/ask-successfactors/successfactors_mcp/policy_admin.py').read_text(),'policy')
        self.assertNotIn('sample_raw_employee',policy)
        self.assertNotIn('sarah.personal@example.com',policy)

if __name__=='__main__':unittest.main(verbosity=2)
