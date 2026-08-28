const pptxgen = require('pptxgenjs');
const pptx = new pptxgen();
pptx.layout = 'LAYOUT_WIDE';
pptx.author = 'Velora';
pptx.title = 'Velora — Remaining Steps to Cover Protiviti Deliverables';
pptx.subject = 'Single-slide management summary';
pptx.theme = { headFontFace: 'Aptos Display', bodyFontFace: 'Aptos', lang: 'en-US' };

const C = { navy:'103B55', teal:'13A6A6', blue:'2E6F95', orange:'F29C46', green:'2E8B68', ink:'20313C', muted:'667782', line:'D6DEE3', white:'FFFFFF', bg:'F4F7F9' };
const s = pptx.addSlide();
s.background = { color: C.bg };
s.addShape(pptx.ShapeType.rect,{x:0,y:0,w:13.333,h:0.12,fill:{color:C.teal},line:{color:C.teal}});
s.addText('VELORA  |  EXECUTIVE AI AGENT',{x:0.46,y:0.2,w:4,h:0.2,fontSize:8,bold:true,color:C.muted,margin:0});
s.addText('CONFIDENTIAL  •  26 AUGUST 2026',{x:10.2,y:0.2,w:2.65,h:0.2,fontSize:8,color:C.muted,align:'right',margin:0});
s.addText('REMAINING STEPS',{x:0.48,y:0.54,w:2.5,h:0.2,fontSize:8.5,bold:true,color:C.teal,charSpacing:1.1,margin:0});
s.addText('What Velora must complete to cover Protiviti’s deliverables',{x:0.48,y:0.79,w:12.1,h:0.48,fontSize:23.5,bold:true,color:C.navy,margin:0});
s.addText('Internal delivery is achievable; focus the remaining effort on four capability gaps, formal assurance and protected go-live capacity.',{x:0.5,y:1.28,w:12,h:0.28,fontSize:10.5,color:C.muted,margin:0});

function card(x,y,w,h,title,items,accent){
  s.addShape(pptx.ShapeType.roundRect,{x,y,w,h,rectRadius:0.05,fill:{color:C.white},line:{color:C.line,width:1},shadow:{type:'outer',color:'AAB6BE',blur:1,angle:45,distance:1,opacity:0.12}});
  s.addShape(pptx.ShapeType.rect,{x,y,w:0.08,h,fill:{color:accent},line:{color:accent}});
  s.addText(title,{x:x+0.2,y:y+0.15,w:w-0.32,h:0.28,fontSize:11.5,bold:true,color:C.navy,margin:0});
  const runs=[];
  items.forEach((item,i)=>{
    runs.push({text:item[0],options:{bullet:{indent:12},breakLine:true,bold:true,color:C.navy}});
    if(item[1]) runs.push({text:item[1],options:{breakLine:true,color:C.ink}});
  });
  s.addText(runs,{x:x+0.2,y:y+0.52,w:w-0.34,h:h-0.63,fontSize:8.6,breakLine:false,margin:0.01,fit:'shrink',paraSpaceAfterPt:2});
}

card(0.5,1.72,3.85,3.1,'1  Close and evidence the capability gaps',[
  ['C3 Evaluation — ','complete structured evaluation, criteria, sources and logged evidence.'],
  ['C5 Agent creation — ','confirm “without IT” governance; prove create/edit/pause/retire and lifecycle logging.'],
  ['C8 Benchmarking — ','demonstrate one approved peer source with citations and method.'],
  ['C9 Traceability — ','complete evidence schema and CSV export; use Dataverse if Purview is delayed.'],
  ['C1/C2/C4/C6/C7 — ','retest existing functions and capture signed acceptance evidence.']
],C.orange);

card(4.48,1.72,4.02,3.1,'2  Complete Protiviti-equivalent delivery controls',[
  ['Traceability — ','map every SOR requirement to component, owner, test and evidence.'],
  ['Assurance — ','formal system, integration, permission, security and negative-path testing.'],
  ['UAT — ','scripts, expected answers, CEO/proxy sessions and business sign-off.'],
  ['Evidence — ','capability-level ADAA pack plus recommendation/evaluation logs through 31 Oct.'],
  ['Operations — ','controlled release/rollback, runbooks, monitoring, incident escalation and full internal hypercare.']
],C.blue);

card(8.63,1.72,4.2,3.1,'3  Secure platform, access and delivery capacity',[
  ['Infrastructure — ','Non-Prod/Prod support, SAP endpoints/private connectivity and production approval.'],
  ['Access — ','Entra delegated identity, Graph scopes, Dataverse and Purview or approved fallback.'],
  ['SAP release — ','controlled transports and rollback for Phase 1; formal SAP DevOps is a next-phase improvement.'],
  ['Beyond September — ','SAP BDC + Azure AI Foundry/Azure Foundry roadmap; MeshX/Fabric only with a clear non-duplicative role.'],
  ['Fast-track capacity — ','add 1 agent developer, 1 QA/UAT/evidence specialist and 1 SAP BDC/Foundry integration engineer.']
],C.green);

s.addText('ACCOUNTABILITY',{x:0.5,y:5.02,w:2,h:0.2,fontSize:8.5,bold:true,color:C.teal,charSpacing:1,margin:0});
const header = t => ({text:t,options:{bold:true,color:C.white,fill:{color:C.navy}}});
s.addTable([
  [header('Bala'),header('Abdullah + Infrastructure'),header('SAP leads'),header('David • Shiva • Lakshmi'),header('Abdelaziz + Bala')],
  ['Architect + PM: traceability, architecture, RAID, documentation and coordination','Environments, access, connectivity and production readiness','Lakshmi • Abdelaziz • Kamalesh • Xavier • Rajesh • Kamal: formal testing','UAT scripts, CEO/proxy sessions and business sign-off','ADAA evidence, runbooks, monitoring and operational escalation']
],{x:0.5,y:5.28,w:12.33,h:0.86,colW:[2.18,2.42,2.55,2.5,2.68],rowH:[0.31,0.55],border:{type:'solid',color:C.line,pt:0.6},fill:C.white,fontFace:'Aptos',fontSize:7.5,color:C.ink,margin:0.05,valign:'mid'});

s.addShape(pptx.ShapeType.roundRect,{x:0.5,y:6.32,w:12.33,h:0.6,rectRadius:0.05,fill:{color:C.navy},line:{color:C.navy}});
s.addText('MANAGEMENT DECISION',{x:0.72,y:6.49,w:1.73,h:0.17,fontSize:8,bold:true,color:'78D4D0',charSpacing:0.8,margin:0});
s.addText('Protect the named internal owners through go-live and approve the three-person surge capacity. This enables Velora to cover the Protiviti deliverables internally without re-platforming Phase 1.',{x:2.4,y:6.42,w:10.0,h:0.32,fontSize:10.5,bold:true,color:C.white,margin:0.01,align:'center',valign:'mid'});
s.addShape(pptx.ShapeType.line,{x:0.5,y:7.12,w:12.32,h:0,line:{color:C.line,width:1}});
s.addText('Source: Velora SOR v1.0; internal weekly update 21 Aug 2026; Protiviti proposal; internal ownership confirmation',{x:0.5,y:7.18,w:10.8,h:0.16,fontSize:6.8,color:C.muted,margin:0});
s.addText('1',{x:12.42,y:7.17,w:0.35,h:0.16,fontSize:7,color:C.muted,align:'right',margin:0});

pptx.writeFile({fileName:'/Users/vikrambala/copilotstudio/Velora_Remaining_Steps_Protiviti_Parity_One_Slide.pptx'});
