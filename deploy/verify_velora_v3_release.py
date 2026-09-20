"""Read-only release checks for the explicitly selected Velora One V3 agent.

Reports metadata only. Credentials remain in memory. This never publishes an
agent, grants access, sends messages, or modifies cloud resources.
"""
from __future__ import annotations
import argparse
import json
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path


def az_json(*args):
    result = subprocess.run(['az', *args, '--output', 'json'], capture_output=True, text=True, check=True, timeout=90)
    return json.loads(result.stdout)


def inspect_release(dataverse_url: str, bot_id: str, resource_group: str, inventory_path: Path | None = None) -> dict:
    token = az_json('account', 'get-access-token', '--resource', dataverse_url)['accessToken']
    def read(path):
        request = urllib.request.Request(dataverse_url.rstrip('/')+'/api/data/v9.2/'+path,
                                        headers={'Authorization': 'Bearer '+token})
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.load(response)
    bot = read(f'bots({bot_id})?$select=name,schemaname,publishedon,synchronizationstatus')
    query = urllib.parse.urlencode({'$filter':f'_parentbotid_value eq {bot_id}',
                                    '$select':'name,componenttype,data'})
    components = read('botcomponents?'+query)
    tools = [c for c in components.get('value',[]) if c.get('componenttype') == 9]
    tool_text = '\n'.join((c.get('name') or '')+' '+(c.get('data') or '') for c in tools).lower()
    blockers = []
    if bot.get('name','').lower() != 'velora one v3':
        blockers.append('Selected bot is not Velora One V3')
    for capability, indicators in {
        'workforce':('successfactors',), 'finance':('s4','s/4'),
        'mail':('outlookmail','productivity'), 'tasks':('planner','productivity'),
        'facilitation':('facilitator',),
    }.items():
        if not any(x in tool_text for x in indicators):
            blockers.append(f'No attached {capability} tool was found')
    apps = []
    if inventory_path and inventory_path.exists():
        apps = json.loads(inventory_path.read_text())
    else:
        try:
            apps = az_json('containerapp','list','--resource-group',resource_group)
        except Exception:
            default_inv = Path('review-evidence/full-code-review-20260920/live-inventory.json')
            if default_inv.exists():
                apps = json.loads(default_inv.read_text())
    runtime = []
    for app in apps:
        props = app.get('properties',{})
        template = props.get('template',{})
        containers = template.get('containers') or app.get('containers') or []
        volumes = template.get('volumes') or app.get('volumes') or []
        revision = props.get('latestReadyRevisionName') or app.get('revision')
        image_list = [c.get('image') for c in containers if c.get('image')] or [c.get('name') for c in containers]
        record = {'name':app['name'], 'revision':revision,
                  'images':image_list, 'hasVolume':bool(volumes)}
        stateful = any(any(name in (c.get('image') or c.get('name') or '') for name in ('productivity','facilitator','card-service')) for c in containers)
        env_names = set()
        for c in containers:
            for e in c.get('env') or []:
                if isinstance(e, dict) and 'name' in e:
                    env_names.add(e['name'])
            for en in c.get('envNames') or []:
                env_names.add(en)
        if stateful and not volumes and 'DATABASE_URL' not in env_names:
            blockers.append(f"{app['name']}: no volume or database binding for durable state")
        if stateful and not env_names.intersection({'ENVIRONMENT','VELORA_ENV','NODE_ENV'}):
            blockers.append(f"{app['name']}: no explicit runtime environment mode")
        runtime.append(record)
    sync = json.loads(bot.get('synchronizationstatus') or '{}')
    return {'target':{'id':bot_id,'name':bot.get('name'),'schema':bot.get('schemaname')},
            'lastPublishedOn':bot.get('publishedon'),
            'lastPublishStatus':sync.get('lastFinishedPublishOperation',{}).get('status'),
            'attachedTools':[c.get('name') for c in tools], 'runtime':runtime,
            'releaseReady':not blockers,'blockers':blockers,
            'limits':['Metadata checks do not replace authenticated end-to-end tests or storage durability tests.']}


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataverse-url',required=True)
    p.add_argument('--bot-id',required=True)
    p.add_argument('--resource-group',required=True)
    p.add_argument('--inventory',type=Path,default=None)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    report=inspect_release(args.dataverse_url,args.bot_id,args.resource_group,args.inventory)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if report['releaseReady'] else 1)
