import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
const out=path.dirname(new URL(import.meta.url).pathname);
const cards=fs.readFileSync(path.join(out,'cards-scratch.txt'),'utf8').trim();
const pipeline=fs.readFileSync(path.join(out,'pipeline-scratch.txt'),'utf8').trim();
const safeEnv={PATH:process.env.PATH,NODE_ENV:'test',IDEMPOTENCY_STORAGE_DIR:fs.mkdtempSync(path.join(os.tmpdir(),'cards-probe-')),TOKEN_SIGNING_SECRET:'synthetic-card-probe-secret'};
for(const k of Object.keys(process.env))delete process.env[k];Object.assign(process.env,safeEnv);
let build=spawnSync('npm',['run','build'],{cwd:cards,env:process.env,encoding:'utf8'});
fs.writeFileSync(path.join(out,'cards-build.log'),build.stdout+build.stderr);if(build.status)throw new Error('cards build failed');
process.chdir(cards);
const mod=await import(pathToFileURL(path.join(cards,'dist/index.js')));
const {IdempotencySigner}=await import(pathToFileURL(path.join(cards,'dist/security/idempotency-signer.js')));
const results={};
const r=await mod.fastify.inject({method:'POST',url:'/render-card',payload:{templateId:'approval-card',sessionId:'caller-chosen',data:{title:'Synthetic approval',description:'Offline probe',amount:1},ttlSeconds:'not-a-number'}});
const body=r.json();results.anonymous_render={status:r.statusCode,success:body.success,hasTicket:!!body.ticketToken};
const token=body.ticketToken;
if(token){
 const validation=await mod.fastify.inject({method:'POST',url:'/validate-submission',payload:{ticketToken:token,submittedData:{amount:999999,sessionId:'different-session'}}});
 results.unbound_submission={status:validation.statusCode,response:validation.json()};
}
process.env.NODE_ENV='production';delete process.env.TOKEN_SIGNING_SECRET;delete process.env.REQUIRE_EXPLICIT_SIGNING_SECRET;
try{new IdempotencySigner();results.production_accepts_missing_signing_secret=true;}catch{results.production_accepts_missing_signing_secret=false;}
process.env.NODE_ENV='test';
const signer=new IdempotencySigner('synthetic-shared-secret');const ticket=signer.generateTicket('s','t').ticketToken;
const child=`import {IdempotencySigner} from ${JSON.stringify(pathToFileURL(path.join(cards,'dist/security/idempotency-signer.js')).href)}; console.log(JSON.stringify(new IdempotencySigner('synthetic-shared-secret').verifyAndConsumeTicket(process.env.REVIEW_TICKET)));`;
results.two_replicas_local_storage=[];
for(let i=0;i<2;i++){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'card-replica-'));
 const p=spawnSync(process.execPath,['--input-type=module','-e',child],{env:{PATH:process.env.PATH,NODE_ENV:'test',VELORA_STATE_DIR:dir,REVIEW_TICKET:ticket},encoding:'utf8'});
 results.two_replicas_local_storage.push({exit:p.status,result:JSON.parse(p.stdout)});
}
const {runEvaluation}=await import(pathToFileURL(path.join(pipeline,'dist/evaluation/evaluationOrchestrator.js')));
let n=0;
globalThis.fetch=async()=>({ok:true,json:async()=>({responsev2:{predictionOutput:{text:JSON.stringify(n++===0?{Patterns:[{Status:true}]}:{compliancePercentage:0,issues:[{id:'unknown-criterion',title:'Synthetic serious issue',severity:'High',description:'Unrecognized criterion'}]})}}})});
const evaluation=await runEvaluation('offline.invalid','synthetic-token',{botName:'Synthetic',agentInstructions:'Review these instructions',topicComponents:[]});
results.pipeline_malformed_success={scores:evaluation.scores,errors:evaluation.errors};
await mod.fastify.close();
// Do not retain signed token material; only outcome metadata is needed.
for (const item of results.two_replicas_local_storage) delete item.result.payload;
fs.writeFileSync(path.join(out,'node-probes.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));
