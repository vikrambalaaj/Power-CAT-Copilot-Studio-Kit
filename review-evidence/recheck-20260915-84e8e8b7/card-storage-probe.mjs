import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'velora-storage-check-'));
const url=new URL('../../mcp-apps/dynamic-adaptive-card-service/dist/security/idempotency-signer.js',import.meta.url).href;
const code=`import {IdempotencySigner} from ${JSON.stringify(url)};const s=new IdempotencySigner('synthetic-key');const token=process.env.PROBE_TOKEN||s.generateTicket('s','approval-card').ticketToken;const result=s.verifyAndConsumeTicket(token);console.log(JSON.stringify({token,valid:result.valid,error:result.error}));`;
function call(store,token){const r=spawnSync(process.execPath,['--input-type=module','-e',code],{env:{PATH:process.env.PATH,IDEMPOTENCY_STORAGE_PATH:store,...token&&{PROBE_TOKEN:token}},encoding:'utf8'});if(r.status)throw Error(r.stderr);return JSON.parse(r.stdout);}
const shared=path.join(temp,'shared','tokens.json');const first=call(shared);const repeat=call(shared,first.token);
const other=call(path.join(temp,'other-instance','tokens.json'),first.token);
const blocker=path.join(temp,'file-not-directory');fs.writeFileSync(blocker,'synthetic');const denied=call(path.join(blocker,'tokens.json'));
const result={sharedDiskFirstAccepted:first.valid,sharedDiskRestartReplayAccepted:repeat.valid,separateInstanceReplayAccepted:other.valid,unusableStorageAccepted:denied.valid,unusableStorageError:denied.error};
fs.writeFileSync(new URL('./card-storage-probe.json',import.meta.url),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
