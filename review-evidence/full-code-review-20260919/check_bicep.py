from pathlib import Path
import subprocess,tempfile,json,os
root=Path(__file__).resolve().parents[2];out=Path(__file__).parent;scratch=Path(tempfile.mkdtemp(prefix='velora-bicep-review-'))
rows=[]
for i,p in enumerate(sorted((root/'mcp-apps').glob('**/*.bicep'))):
 if 'node_modules' in p.parts:continue
 try:
  r=subprocess.run(['az','bicep','build','--file',str(p),'--outfile',str(scratch/f'{i}.json')],capture_output=True,text=True,timeout=45)
  rows.append({'path':str(p.relative_to(root)),'exit_code':r.returncode,'output':r.stdout+r.stderr})
 except subprocess.TimeoutExpired:rows.append({'path':str(p.relative_to(root)),'timeout':True});break
(out/'bicep-build.json').write_text(json.dumps(rows,indent=2));print([(x['path'],x.get('exit_code','timeout')) for x in rows])
