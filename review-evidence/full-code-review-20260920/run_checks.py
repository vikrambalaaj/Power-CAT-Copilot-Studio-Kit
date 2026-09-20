import concurrent.futures,json,os,pathlib,shutil,subprocess,tempfile,time
root=pathlib.Path(__file__).resolve().parents[2]; out=pathlib.Path(__file__).parent
py='/tmp/velora-review-20260919-venv/bin/python'
env={k:v for k,v in os.environ.items() if k in {'PATH','LANG','LC_ALL','TMPDIR'}}
env['PYTHONDONTWRITEBYTECODE']='1'
def run_one(spec):
 name,cmd,cwd=spec; started=time.time()
 with (out/(name+'.log')).open('w') as log:
  try:
   r=subprocess.run(cmd,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240)
   return {'name':name,'exit_code':r.returncode,'seconds':round(time.time()-started,2)}
  except subprocess.TimeoutExpired: return {'name':name,'timeout':True}
specs=[]
for service in ['ask-successfactors','ask-productivity','ask-s4hana','ask-facilitator','ask-sac']:
 args=[py,str(out/'offline_test_runner.py'),'mcp-apps/'+service,str(out/(service+'.xml')),'test']
 if service=='ask-productivity': args+=['--workspace-imports']
 specs.append((service,args,root))
specs += [('architecture',[py,str(out/'offline_test_runner.py'),'mcp-apps',str(out/'architecture.xml'),'test_target_credential_architecture.py'],root),('cleanup',[py,str(out/'offline_test_runner.py'),'deploy/cleanup',str(out/'cleanup.xml'),'test_remove_runtime_demo_data.py'],root)]
for name,sub in [('cards','mcp-apps/dynamic-adaptive-card-service'),('pipeline','agent-review-pipeline')]:
 scratch=pathlib.Path(tempfile.mkdtemp(prefix='velora-'+name+'-review-'))
 for item in ['src','test','package.json','package-lock.json','tsconfig.json']:
  p=root/sub/item
  if p.is_dir(): shutil.copytree(p,scratch/item)
  elif p.exists(): shutil.copy2(p,scratch/item)
 (scratch/'node_modules').symlink_to(root/sub/'node_modules',target_is_directory=True)
 (out/(name+'-scratch.txt')).write_text(str(scratch))
 specs.append((name,['npm','test'],scratch))
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 results=list(pool.map(run_one,specs))
(out/'check-exits.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
