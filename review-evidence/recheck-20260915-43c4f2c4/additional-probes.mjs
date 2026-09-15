import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { runEvaluation } from '../../agent-review-pipeline/dist/evaluation/evaluationOrchestrator.js';

let requests = 0;
globalThis.fetch = async () => {
  requests++;
  if (requests === 1) throw new Error('SYNTHETIC_STAGE_B_OUTAGE');
  return new Response(JSON.stringify({responsev2:{predictionOutput:{text:JSON.stringify({issues:[],compliancePercentage:100})}}}),{status:200});
};
const evaluation = await runEvaluation('example.invalid','synthetic-token', {
  topicComponents: [], agentInstructions:'Synthetic test instructions',
  localPatterns:[{patternName:'Local check',status:true,category:'test',severity:'Low',recommendation:'none'}]
});

const temp = fs.mkdtempSync(path.join(os.tmpdir(),'velora-card-recheck-'));
const moduleUrl = new URL('../../mcp-apps/dynamic-adaptive-card-service/dist/security/idempotency-signer.js',import.meta.url).href;
const child = `import {IdempotencySigner} from ${JSON.stringify(moduleUrl)}; const s=new IdempotencySigner('synthetic-key'); const token=process.env.PROBE_TOKEN||s.generateTicket('session','approval-card').ticketToken; console.log(JSON.stringify({token,valid:s.verifyAndConsumeTicket(token).valid}));`;
const env = {PATH:process.env.PATH,IDEMPOTENCY_STORAGE_PATH:path.join(temp,'missing-parent','tokens.json')};
function call(extra={}) {
  const r=spawnSync(process.execPath,['--input-type=module','-e',child],{env:{...env,...extra},encoding:'utf8'});
  if(r.status!==0) throw new Error(r.stderr);
  return JSON.parse(r.stdout);
}
const first=call();
const second=call({PROBE_TOKEN:first.token});
const result={evaluationAfterStageBFailure:{errors:evaluation.errors,passed:evaluation.scores.passed,score:evaluation.scores.overallScore,providerCalls:requests},cardPersistenceFailure:{firstAccepted:first.valid,replayAfterRestartAccepted:second.valid,storeExists:fs.existsSync(env.IDEMPOTENCY_STORAGE_PATH)}};
fs.writeFileSync(new URL('./additional-node-probes.json',import.meta.url),JSON.stringify(result,null,2));
console.log(JSON.stringify(result,null,2));
