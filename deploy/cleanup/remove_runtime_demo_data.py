#!/usr/bin/env python3
"""Reviewed source cleanup. Default: preview. No Azure/Dataverse deletion or deployment.

--apply requires the exact --plan produced by a prior preview. Stops on source drift.
Only allowlisted source files are rewritten; no keyword-based record/file deletion.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

TARGETS = {
    'mcp-apps/ask-productivity/productivity_mcp/m365_client.py': 'm365',
    'mcp-apps/ask-sac/sac_mcp/client.py': 'sac',
    'mcp-apps/ask-sac/sac_mcp/settings.py': 'sac_settings',
    'mcp-apps/ask-facilitator/facilitator_mcp/tools.py': 'facilitator',
    'mcp-apps/ask-successfactors/successfactors_mcp/policy_admin.py': 'policy',
}
M365_COLLECTION_METHODS = {
    'get_mail_thread', 'summarize_priority_mail', 'find_mail_follow_ups',
    'get_meeting_details', 'check_availability', 'get_channel_context',
    'get_chat_context', 'get_planner_task', 'list_pending_approvals',
}
FACILITATOR_UNAVAILABLE = {
    'generate_pre_meeting_briefing', 'query_user_history_from_dataverse',
    'get_calendar_meetings', 'process_calendar_meeting_workflow',
    'sync_dataverse_logs_to_memory', 'export_meeting_to_loop_notebook',
}

def statements(code):
    return ast.parse(code).body

def unavailable(name):
    return statements(f"raise RuntimeError('SOURCE_UNAVAILABLE: {name} requires a configured live provider; no substitute data is returned.')")

class Cleanup(ast.NodeTransformer):
    def __init__(self, kind):
        self.kind = kind
        self.changes = []

    def visit_Assign(self, node):
        if self.kind == 'm365' and any(isinstance(t, ast.Attribute) and t.attr == 'force_mock' for t in node.targets):
            self.changes.append('Remove runtime mock-mode switch')
            return None
        return self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if self.kind == 'sac_settings' and isinstance(node.target, ast.Name) and node.target.id == 'demo_mode':
            self.changes.append('Remove demo-mode configuration field')
            return None
        if self.kind == 'm365' and isinstance(node.target, ast.Name) and node.target.id.startswith('_M365_'):
            self.changes.append('Remove fixture collection ' + node.target.id)
            return None
        if self.kind == 'facilitator' and isinstance(node.target, ast.Name) and node.target.id in {'_CALENDAR_STORE', '_DATAVERSE_AUDIT_LOGS'}:
            self.changes.append('Remove fixture collection ' + node.target.id)
            return None
        return self.generic_visit(node)

    def visit_FunctionDef(self, node):
        if node.name in {'seed_test_m365_data', 'seed_test_facilitator_data'}:
            self.changes.append('Delete embedded fixture seed ' + node.name)
            return None
        if self.kind == 'm365':
            if node.name == 'is_live':
                node.body = statements('return bool(self.graph_access_token or (self.tenant_id and self.client_id and self.client_secret))')
                self.changes.append('Require configured live Graph credentials')
                return node
            if node.name in M365_COLLECTION_METHODS:
                node.body = unavailable(node.name)
                self.changes.append('Remove fixed/local result: ' + node.name)
                return node
            if node.name == 'resolve_recipients':
                node.body = statements('''
resolved, unresolved, external = [], [], []
for item in names_or_emails:
    item = item.strip()
    if '@' not in item:
        unresolved.append(item + ' (Live directory resolution unavailable; provide a verified email address)')
        continue
    email = item.lower()
    resolved.append(email)
    if email.rsplit('@', 1)[-1] not in ALLOWED_DOMAINS:
        external.append(email)
return resolved, unresolved, external
''')
                self.changes.append('Remove sample directory lookup; keep supplied email handling')
                return node
            if node.name == '_create_receipt':
                node.body = statements('''
if simulated:
    raise RuntimeError('Simulated receipts are prohibited')
receipt = {'provider': 'MICROSOFT_GRAPH', 'operation': operation, 'executionMode': 'LIVE_GRAPH', 'simulated': False, 'receiptStatus': 'DISPATCHED', 'timestamp': datetime.now(timezone.utc).isoformat()}
if live_id:
    receipt['externalId'] = live_id
if extra:
    receipt.update(extra)
return receipt
''')
                self.changes.append('Remove simulated-success receipt generation')
                return node
            # Keep the existing live branch, discard its entire offline fallback.
            for index, stmt in enumerate(node.body):
                if isinstance(stmt, ast.If) and ast.unparse(stmt.test) == 'self.is_live':
                    if stmt.orelse:
                        raise ValueError('Unexpected live branch shape: ' + node.name)
                    before = node.body[:index]
                    if before and isinstance(before[0], ast.Expr) and isinstance(before[0].value, ast.Constant) and isinstance(before[0].value.value, str):
                        before = before[1:]
                    node.body = before + [stmt] + unavailable(node.name)
                    self.changes.append('Delete offline fallback: ' + node.name)
                    return self.generic_visit(node)
        if self.kind == 'facilitator' and node.name in FACILITATOR_UNAVAILABLE:
            node.body = statements("return {'status': 'SOURCE_UNAVAILABLE', 'message': 'This operation requires a verified live integration. No generated business facts or destination links are returned.', 'source': None}")
            self.changes.append('Remove fabricated/local provider result: ' + node.name)
            return node
        if self.kind == 'policy' and node.name == 'preview_policy_output':
            node.body = statements("return {'status': 'SOURCE_UNAVAILABLE', 'message': 'Policy preview requires explicitly supplied, authorized input. Embedded employee examples have been removed.'}")
            self.changes.append('Delete embedded employee policy-preview record')
            return node
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        if self.kind == 'sac' and node.name in {'get_executive_kpis', 'get_story_analytics', 'get_model_data'}:
            for stmt in node.body:
                if isinstance(stmt, ast.If) and ast.unparse(stmt.test) == 'not token':
                    stmt.body = unavailable(node.name)
                    stmt.orelse = []
                    self.changes.append('Delete embedded SAC response: ' + node.name)
                if isinstance(stmt, ast.If) and ast.unparse(stmt.test) == 'cached':
                    stmt.body = statements("if cached.get('isDemoData') or cached.get('simulated'):\n    raise RuntimeError('Cached non-live data rejected; restart on the cleaned image')\nreturn cached")
            return node
        return self.generic_visit(node)

def transform(text, kind):
    tree = ast.parse(text)
    visitor = Cleanup(kind)
    tree = visitor.visit(tree)
    ast.fix_missing_locations(tree)
    result = ast.unparse(tree) + '\n'
    compile(result, '<cleaned-source>', 'exec')
    return result, visitor.changes

def digest(data):
    return hashlib.sha256(data).hexdigest()

def plan(root):
    entries = []
    replacements = {}
    for rel, kind in TARGETS.items():
        path = root / rel
        if path.is_symlink() or not path.is_file():
            raise ValueError('Missing or symlink target: ' + rel)
        if root not in path.resolve().parents:
            raise ValueError('Target escapes root')
        old = path.read_bytes()
        new, changes = transform(old.decode('utf-8'), kind)
        new = new.encode('utf-8')
        entries.append({'path': rel, 'before_sha256': digest(old), 'after_sha256': digest(new), 'changes': changes})
        replacements[rel] = new
    return entries, replacements

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--plan', type=Path, required=True, help='Preview manifest to create, or exact manifest to apply')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    entries, replacements = plan(root)
    if args.apply:
        expected = json.loads(args.plan.read_text())
        if expected.get('root') != str(root) or expected.get('files') != entries:
            raise SystemExit('REFUSED: root/source/cleanup plan changed. Generate and review a new preview.')
        # Validate every file before any write. Recheck each hash immediately before replacement.
        for entry in entries:
            path = root / entry['path']
            if digest(path.read_bytes()) != entry['before_sha256']:
                raise SystemExit('REFUSED: source changed during apply')
            temporary = path.with_name(path.name + '.cleanup-new')
            with temporary.open('xb') as f:
                f.write(replacements[entry['path']])
            temporary.chmod(path.stat().st_mode & 0o777)
            temporary.replace(path)
        log = {**expected, 'applied_at_utc': datetime.now(timezone.utc).isoformat()}
        args.plan.with_suffix('.applied.json').write_text(json.dumps(log, indent=2) + '\n')
        print('Applied reviewed source cleanup to five files. No cloud records or deployed images changed. Run regression tests and rebuild images before release.')
    else:
        output = {'root': str(root), 'created_at_utc': datetime.now(timezone.utc).isoformat(), 'files': entries, 'scope': 'Source-only; tests, historical artifacts, Azure images and Dataverse records are not deleted.'}
        args.plan.parent.mkdir(parents=True, exist_ok=True)
        args.plan.write_text(json.dumps(output, indent=2) + '\n')
        print(json.dumps({'mode':'PREVIEW','files':len(entries),'changes':sum(len(e['changes']) for e in entries),'manifest':str(args.plan)}, indent=2))

if __name__ == '__main__':
    main()
