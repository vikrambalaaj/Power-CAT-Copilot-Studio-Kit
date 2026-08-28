const pptxgen = require('pptxgenjs');
const pptx = new pptxgen();
pptx.layout = 'LAYOUT_WIDE';
pptx.author = 'Velora';
pptx.title = 'Velora Nine-Capability Coverage — Ownership and Clarifications';
pptx.subject = 'Management capability comparison';
pptx.theme = { headFontFace: 'Aptos Display', bodyFontFace: 'Aptos', lang: 'en-US' };

const C = {
  navy:'103B55', teal:'13A6A6', blue:'2E6F95', green:'2E8B68',
  amber:'D68A1E', orange:'F29C46', ink:'20313C', muted:'667782',
  line:'CFD9DF', white:'FFFFFF', bg:'F4F7F9', paleGreen:'E8F4EF',
  paleBlue:'EAF2F7', paleAmber:'FFF4DC', paleOrange:'FFF0E2', paleTeal:'E7F5F5'
};

const slide = pptx.addSlide();
slide.background = { color: C.bg };
slide.addShape(pptx.ShapeType.rect,{x:0,y:0,w:13.333,h:0.11,fill:{color:C.teal},line:{color:C.teal}});
slide.addText('VELORA  |  EXECUTIVE AI AGENT',{x:0.45,y:0.18,w:4.2,h:0.2,fontSize:7.8,bold:true,color:C.muted,margin:0});
slide.addText('CONFIDENTIAL  •  27 AUGUST 2026',{x:10.15,y:0.18,w:2.7,h:0.2,fontSize:7.8,color:C.muted,align:'right',margin:0});
slide.addText('Nine-capability coverage: ownership, dependencies and vendors',{x:0.46,y:0.5,w:12.3,h:0.42,fontSize:22.5,bold:true,color:C.navy,margin:0});
slide.addText('Management view for 30 September and year-end delivery',{x:0.48,y:0.98,w:7.0,h:0.22,fontSize:9.7,color:C.muted,margin:0});

function h(text, fill) {
  return { text, options: { bold:true, color:C.white, fill:{color:fill}, align:'left', valign:'mid' } };
}
function cell(text, fill) {
  return { text, options: { fill:{color:fill}, color:C.ink, valign:'mid' } };
}

const rows = [
  [
    h('Capability',C.navy),
    h('Velora covered\nby 30 Sep',C.green),
    h('Velora covered\nby year-end',C.blue),
    h('Velora — other\ndepartment to cover',C.amber),
    h('Needs more clarity\nto cover',C.orange),
    h('Protiviti',C.navy),
    h('MeshX',C.teal)
  ],
  [
    cell('C1  Enterprise\ndata query',C.white),
    cell('FULL — 6 SAP\nqueries live',C.paleGreen),
    cell('Expand via SAP BDC/\nBTP + Foundry',C.paleBlue),
    cell('Infra + SAP data owners:\naccess/endpoints',C.paleAmber),
    cell('Confirm priority year-end\ndata products',C.paleOrange),
    cell('Full — SAP + SharePoint/\nOneLake',C.white),
    cell('Foundation MCP;\n3–5 questions',C.paleTeal)
  ],
  [
    cell('C2  Proactive\nrecommendations',C.white),
    cell('FULL — daily KPI\nscan',C.paleGreen),
    cell('Broader signals and\nreusable skills',C.paleBlue),
    cell('Business owners:\napprove KPIs/thresholds',C.paleAmber),
    cell('Confirm future signals\nand trigger thresholds',C.paleOrange),
    cell('Full — Foundry\nscheduled skill',C.white),
    cell('Not covered',C.paleTeal)
  ],
  [
    cell('C3  Evaluation\nengine',C.white),
    cell('FULL — covered\ninternally',C.paleGreen),
    cell('Deeper criteria and\ndata models',C.paleBlue),
    cell('Business owners:\napprove evaluation criteria',C.paleAmber),
    cell('Confirm additional\nevaluation use cases',C.paleOrange),
    cell('Full — Foundry\nevaluation skill',C.white),
    cell('Not covered',C.paleTeal)
  ],
  [
    cell('C4  Briefing &\nsynthesis',C.white),
    cell('FULL — inbox\nbriefs/digests',C.paleGreen),
    cell('More sources and\nautomation',C.paleBlue),
    cell('Business/M365 owners:\nsource access',C.paleAmber),
    cell('Confirm new sources,\nformats and cadence',C.paleOrange),
    cell('Full — cited Outlook/\nTeams briefs',C.white),
    cell('Not covered',C.paleTeal)
  ],
  [
    cell('C5  Agent\ncreation',C.white),
    cell('Covered — governed\ncreation; controls manageable',C.paleGreen),
    cell('Full self-service +\nedit/pause/retire',C.paleBlue),
    cell('David/PMO: confirm\nscope interpretation',C.paleAmber),
    cell('Clarify “without IT” and\nrequired lifecycle controls',C.paleOrange),
    cell('Full — create/edit/\npause/retire',C.white),
    cell('Not covered',C.paleTeal)
  ],
  [
    cell('C6  Institutional\nmemory',C.white),
    cell('FULL — documents/\ntranscripts searchable',C.paleGreen),
    cell('Broader corpus and\nretention controls',C.paleBlue),
    cell('Data/records owners:\ncontent + retention approval',C.paleAmber),
    cell('Confirm additional corpus\nand retention policy',C.paleOrange),
    cell('Full — AI Search/RAG',C.white),
    cell('Not covered',C.paleTeal)
  ],
  [
    cell('C7  Meeting\nintelligence',C.white),
    cell('FULL — Graph +\naction flows',C.paleGreen),
    cell('Broader channels and\nautomation',C.paleBlue),
    cell('M365/Privacy owners:\naccess + retention',C.paleAmber),
    cell('Confirm non-Teams scope\nand privacy requirements',C.paleOrange),
    cell('Full — Graph/manual\nupload',C.white),
    cell('Not covered',C.paleTeal)
  ],
  [
    cell('C8  Peer\nbenchmarking',C.white),
    cell('PENDING — ADAA\ndata/source required',C.paleGreen),
    cell('Build once ADAA details\nand data are received',C.paleBlue),
    cell('DAVID — obtain peer set,\nmetrics and data from ADAA',C.paleAmber),
    cell('ADAA-approved peers,\nsource, metrics and format',C.paleOrange),
    cell('Full — one approved\nsource minimum',C.white),
    cell('Not covered',C.paleTeal)
  ],
  [
    cell('C9  Decision\ntraceability',C.white),
    cell('Captured internally in\nVelora’s current format',C.paleGreen),
    cell('Align final schema, CSV\nexport and Purview',C.paleBlue),
    cell('DAVID — provide ADAA\nevidence/export template',C.paleAmber),
    cell('Official ADAA schema,\nfields and export format',C.paleOrange),
    cell('Full — Dataverse +\nCSV evidence',C.white),
    cell('Data lineage/audit\nportion only',C.paleTeal)
  ]
];

slide.addTable(rows,{
  x:0.46,y:1.32,w:12.42,h:5.2,
  colW:[1.38,1.66,1.77,1.92,1.87,1.79,2.03],
  rowH:[0.48,0.52,0.52,0.52,0.52,0.52,0.52,0.52,0.52,0.52],
  border:{type:'solid',color:C.line,pt:0.55},
  fontFace:'Aptos',fontSize:7.1,color:C.ink,margin:0.045,valign:'mid',
  autoFit:false,breakLine:false
});

slide.addShape(pptx.ShapeType.roundRect,{x:0.47,y:6.66,w:12.4,h:0.37,rectRadius:0.05,fill:{color:C.navy},line:{color:C.navy}});
slide.addText('MANAGEMENT VIEW',{x:0.65,y:6.77,w:1.35,h:0.14,fontSize:7.2,bold:true,color:'78D4D0',charSpacing:0.7,margin:0});
slide.addText('Velora covers C1–C7 internally. C8 depends on ADAA peer/data inputs; C9 is already logged internally but awaits David’s official ADAA evidence/export template.',{x:1.95,y:6.73,w:10.55,h:0.2,fontSize:8.5,bold:true,color:C.white,align:'center',margin:0});
slide.addShape(pptx.ShapeType.line,{x:0.47,y:7.13,w:12.4,h:0,line:{color:C.line,width:1}});
slide.addText('Source: Velora SOR v1.0; internal weekly update 21 Aug 2026; Protiviti proposal; MeshX SOW; management clarifications',{x:0.48,y:7.19,w:11.2,h:0.14,fontSize:6.3,color:C.muted,margin:0});
slide.addText('1',{x:12.48,y:7.18,w:0.3,h:0.14,fontSize:6.5,color:C.muted,align:'right',margin:0});

pptx.writeFile({fileName:'/Users/vikrambala/copilotstudio/Velora_9_Capability_Coverage_7_Column_Management_View.pptx'});
