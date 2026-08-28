const pptxgen = require('pptxgenjs');

const pptx = new pptxgen();
pptx.layout = 'LAYOUT_WIDE';
pptx.author = 'Velora';
pptx.subject = 'Executive AI Agent capability coverage follow-up';
pptx.title = 'Velora Executive AI Agent — Capability and Internal Delivery Follow-up';
pptx.company = 'Velora';
pptx.lang = 'en-US';
pptx.theme = {
  headFontFace: 'Aptos Display',
  bodyFontFace: 'Aptos',
  lang: 'en-US'
};
pptx.defineSlideMaster({
  title: 'VELORA',
  background: { color: 'F4F7F9' },
  objects: [
    { rect: { x: 0, y: 0, w: 13.333, h: 0.12, fill: { color: '13A6A6' }, line: { color: '13A6A6' } } },
    { text: { text: 'VELORA  |  EXECUTIVE AI AGENT', options: { x: 0.45, y: 0.18, w: 4.2, h: 0.25, fontFace: 'Aptos', fontSize: 8, bold: true, color: '5A6974', margin: 0 } } },
    { text: { text: 'CONFIDENTIAL  •  26 AUGUST 2026', options: { x: 10.1, y: 0.18, w: 2.78, h: 0.25, fontFace: 'Aptos', fontSize: 8, color: '71808A', align: 'right', margin: 0 } } },
    { line: { x: 0.45, y: 7.12, w: 12.43, h: 0, line: { color: 'D6DEE3', width: 1 } } },
    { text: { text: 'Source: Velora SOR v1.0; internal weekly update 21 Aug 2026; Protiviti proposal; MeshX SOW', options: { x: 0.48, y: 7.18, w: 9.9, h: 0.16, fontFace: 'Aptos', fontSize: 6.8, color: '6B7A84', margin: 0 } } }
  ],
  slideNumber: { x: 12.45, y: 7.16, w: 0.4, h: 0.18, fontFace: 'Aptos', fontSize: 7, color: '6B7A84', align: 'right', margin: 0 }
});

const C = {
  navy: '103B55', teal: '13A6A6', blue: '2E6F95', orange: 'F29C46',
  green: '2E8B68', amber: 'D68A1E', red: 'B84A4A', ink: '20313C',
  muted: '667782', line: 'D6DEE3', pale: 'EAF2F5', white: 'FFFFFF', bg: 'F4F7F9'
};

function title(slide, kicker, heading, sub) {
  slide.addText(kicker.toUpperCase(), { x: 0.48, y: 0.53, w: 4.2, h: 0.22, fontFace: 'Aptos', fontSize: 8.5, bold: true, color: C.teal, charSpacing: 1.1, margin: 0 });
  slide.addText(heading, { x: 0.48, y: 0.76, w: 12.2, h: 0.48, fontFace: 'Aptos Display', fontSize: 24, bold: true, color: C.navy, margin: 0, breakLine: false });
  if (sub) slide.addText(sub, { x: 0.5, y: 1.27, w: 12.0, h: 0.32, fontFace: 'Aptos', fontSize: 10.5, color: C.muted, margin: 0 });
}

function pill(slide, text, x, y, w, color) {
  slide.addShape(pptx.ShapeType.roundRect, { x, y, w, h: 0.25, rectRadius: 0.06, fill: { color }, line: { color }, radius: 0.06 });
  slide.addText(text, { x: x + 0.03, y: y + 0.025, w: w - 0.06, h: 0.18, fontSize: 7.5, bold: true, color: C.white, align: 'center', margin: 0 });
}

function addCard(slide, x, y, w, h, heading, body, accent = C.teal) {
  slide.addShape(pptx.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.05, fill: { color: C.white }, line: { color: C.line, width: 1 }, shadow: { type: 'outer', color: 'AAB6BE', blur: 1, angle: 45, distance: 1, opacity: 0.12 } });
  slide.addShape(pptx.ShapeType.rect, { x, y, w: 0.07, h, fill: { color: accent }, line: { color: accent } });
  slide.addText(heading, { x: x + 0.18, y: y + 0.13, w: w - 0.28, h: 0.25, fontSize: 11, bold: true, color: C.navy, margin: 0 });
  slide.addText(body, { x: x + 0.18, y: y + 0.44, w: w - 0.28, h: h - 0.52, fontSize: 8.5, color: C.ink, margin: 0.02, breakLine: false, valign: 'top', fit: 'shrink' });
}

function headerCell(text) {
  return { text, options: { bold: true, color: C.white, fill: { color: C.navy }, align: 'left' } };
}

// Slide 1 — comparison matrix
{
  const s = pptx.addSlide('VELORA');
  title(s, 'Follow-up 1 of 3', 'Nine-capability coverage: current, future and vendors', 'Management view as of the 30 September 2026 milestone (date to confirm)');

  const rows = [
    [headerCell('Capability'), headerCell('Velora by 30 Sep'), headerCell('Velora beyond Sep'), headerCell('Protiviti claim'), headerCell('MeshX scope')],
    ['C1  Enterprise data query', 'Covered — 6 SAP queries live', 'Expand via SAP BDC/BTP + Foundry', 'Full — SAP + SharePoint/OneLake', 'Foundation MCP; 3–5 questions'],
    ['C2  Recommendations', 'Covered — daily KPI scan', 'Broader signals and skills', 'Full — Foundry scheduled skill', 'Not covered'],
    ['C3  Evaluation engine', 'In progress — close and evidence', 'Deeper criteria/data models', 'Full — Foundry evaluation skill', 'Not covered'],
    ['C4  Briefing & synthesis', 'Covered — inbox briefs/digests', 'More sources and automation', 'Full — cited Outlook/Teams briefs', 'Not covered'],
    ['C5  Agent creation', 'Gated — governance + lifecycle', 'Full governed self-service', 'Full — create/edit/pause/retire', 'Not covered'],
    ['C6  Institutional memory', 'Covered — documents/transcripts', 'Broader corpus and retention', 'Full — AI Search/RAG', 'Not covered'],
    ['C7  Meeting intelligence', 'Covered — Graph + action flows', 'Broader channels/automation', 'Full — Graph/manual upload', 'Not covered'],
    ['C8  Peer benchmarking', 'Planned — one approved source', 'Multi-source benchmarking', 'Full — one-source minimum', 'Not covered'],
    ['C9  Decision traceability', 'Partial — Dataverse live; export/Purview', 'Dual audit + full governance', 'Full — Dataverse + CSV evidence', 'Data lineage/audit portion only']
  ];
  s.addTable(rows, {
    x: 0.48, y: 1.69, w: 12.36, h: 4.78,
    colW: [2.16, 2.42, 2.58, 2.72, 2.48],
    rowH: [0.42, 0.47, 0.47, 0.47, 0.47, 0.47, 0.47, 0.47, 0.47, 0.47],
    border: { type: 'solid', color: C.line, pt: 0.65 },
    fill: C.white, color: C.ink, fontFace: 'Aptos', fontSize: 8.4,
    margin: 0.06, valign: 'mid', breakLine: false,
    autoFit: false,
    bold: false,
    fillHeader: C.navy,
    bandRow: true,
    bandColor: 'F1F6F8'
  });
  pill(s, 'VELORA: 5 COMPLETE • 2 ACTIVE/PARTIAL • 2 GATED/PLANNED', 0.5, 6.59, 4.25, C.blue);
  pill(s, 'PROTIVITI: 9 CLAIMED — NOT YET DELIVERED', 4.9, 6.59, 3.48, C.orange);
  pill(s, 'MESHX: C1 + DATA-LAYER C9 ONLY', 8.53, 6.59, 3.15, C.teal);
  s.addText('Key point: Protiviti is broader; MeshX is deeper only in governed data/lineage. Velora can reach capability parity without rebuilding the current SAP path.', { x: 0.5, y: 6.88, w: 12.05, h: 0.2, fontSize: 8.2, bold: true, color: C.navy, margin: 0 });
}

// Slide 2 — internal completion and ownership
{
  const s = pptx.addSlide('VELORA');
  title(s, 'Follow-up 2 of 3', 'What Velora must complete to cover Protiviti’s claims', 'Internal ownership is available; the remaining need is protected capacity, evidence and management decisions');

  addCard(s, 0.5, 1.67, 3.92, 2.03, 'Close the four remaining capability items',
    'C3 — complete structured evaluation and evidence.\nC5 — confirm “without IT” governance; prove create/edit/pause/retire.\nC8 — demonstrate benchmarking against one approved source.\nC9 — complete evidence schema and CSV export; use Dataverse if Purview is delayed.', C.orange);
  addCard(s, 4.57, 1.67, 3.92, 2.03, 'Retest the five capabilities already covered',
    'C1 — six permission-trimmed SAP queries.\nC2 — scheduled KPI recommendations.\nC4 — executive briefing and synthesis.\nC6 — searchable documents/transcripts.\nC7 — meeting intelligence and action flows.\nOutput: signed tests, screenshots, logs and business acceptance.', C.green);
  addCard(s, 8.64, 1.67, 4.18, 2.03, 'Add Protiviti-equivalent delivery controls',
    'Requirements traceability matrix • formal SIT/integration/security/negative-path tests • UAT scripts and CEO/proxy booking • capability-level ADAA evidence • controlled release/rollback • runbooks, monitoring and full internal hypercare.', C.blue);

  s.addText('ACCOUNTABILITY', { x: 0.5, y: 3.93, w: 2.3, h: 0.23, fontSize: 9, bold: true, color: C.teal, charSpacing: 1, margin: 0 });
  const owners = [
    ['Bala', 'Developer Architect + Project Manager', 'Architecture, traceability, delivery plan, RAID/defects, documentation and coordination'],
    ['Abdullah + Infrastructure team', 'Infrastructure and access', 'Non-Prod/Prod support, connectivity, environments, production readiness and access'],
    ['SAP leads', 'Lakshmi • Abdelaziz • Kamalesh • Xavier • Rajesh • Kamal', 'System, integration, permission, security and negative-path testing'],
    ['David • Shiva • Lakshmi', 'Business/UAT', 'UAT scripts, CEO/proxy sessions, expected results and business sign-off'],
    ['Abdelaziz + Bala', 'Evidence and operations', 'ADAA evidence pack, runbooks, monitoring, incident ownership and escalation']
  ];
  s.addTable([
    [headerCell('Owner'), headerCell('Role'), headerCell('Accountability')],
    ...owners
  ], {
    x: 0.5, y: 4.22, w: 12.3, h: 2.04, colW: [2.15, 3.22, 6.93], rowH: [0.32, 0.34, 0.34, 0.34, 0.34, 0.34],
    border: { type: 'solid', color: C.line, pt: 0.6 }, fill: C.white, fillHeader: C.navy, bandRow: true, bandColor: 'F1F6F8',
    fontFace: 'Aptos', fontSize: 8.4, color: C.ink, margin: 0.06, valign: 'mid'
  });
  s.addShape(pptx.ShapeType.roundRect, { x: 0.5, y: 6.48, w: 12.3, h: 0.47, rectRadius: 0.05, fill: { color: 'E4F3EF' }, line: { color: 'A9D5C7', width: 1 } });
  s.addText('Management position: Phase 1 can be covered internally. Additional resources do not replace the owners above—they create the capacity to fast-track C3/C5/C8/C9 and complete testing/evidence without weakening go-live support.', { x: 0.7, y: 6.58, w: 11.9, h: 0.25, fontSize: 9.2, bold: true, color: '175D48', margin: 0, align: 'center' });
}

// Slide 3 — timeline, software/access and resource ask
{
  const s = pptx.addSlide('VELORA');
  title(s, 'Follow-up 3 of 3', 'Delivery path: September completion and beyond-timeline scale', 'Keep Phase 1 stable; introduce SAP BDC, Azure AI Foundry/Azure Foundry and SAP DevOps as a governed next phase');

  // Timeline
  s.addText('DELIVERY TIMELINE', { x: 0.5, y: 1.58, w: 2.6, h: 0.22, fontSize: 9, bold: true, color: C.teal, charSpacing: 1, margin: 0 });
  s.addShape(pptx.ShapeType.line, { x: 0.85, y: 2.25, w: 11.45, h: 0, line: { color: 'AFC2CD', width: 3 } });
  const points = [
    [1.05, 'NOW–28 AUG', 'Close C3/C5/C8/C9\nFreeze Phase 1 scope'],
    [4.0, 'SEP', 'SIT • security • UAT\nrelease and evidence'],
    [7.05, '30 SEP', 'Executive issuance /\nproduction go-live'],
    [9.86, '31 OCT', '30-day recommendation +\nevaluation logs complete']
  ];
  for (const [x, date, body] of points) {
    s.addShape(pptx.ShapeType.ellipse, { x, y: 2.08, w: 0.34, h: 0.34, fill: { color: date === '30 SEP' ? C.orange : C.teal }, line: { color: C.white, width: 1 } });
    s.addText(date, { x: x - 0.28, y: 1.82, w: 1.25, h: 0.2, fontSize: 8.3, bold: true, color: C.navy, align: 'center', margin: 0 });
    s.addText(body, { x: x - 0.45, y: 2.5, w: 1.75, h: 0.48, fontSize: 8.1, color: C.ink, align: 'center', margin: 0.01, fit: 'shrink' });
  }

  addCard(s, 0.5, 3.13, 3.85, 2.55, 'Phase 1 software and access',
    'M365 Copilot + Teams\nCopilot Studio\nSAP BTP and SAP-direct MCP\nS/4HANA • SuccessFactors • SAC endpoints\nEntra delegated identity\nDataverse audit/evidence store\nGraph transcript permissions\nNon-Prod/Prod access and Infrastructure support\nPurview access or approved Dataverse fallback', C.green);
  addCard(s, 4.48, 3.13, 4.15, 2.55, 'Beyond September architecture',
    'SAP BDC — governed SAP data products, semantics, KPIs and lineage.\nAzure AI Foundry / Azure Foundry — advanced recommendations, evaluations, benchmarking and reusable skills.\nSAP BTP + standard MCP — controlled integration layer.\nDataverse + Purview — traceability and governance.\nMeshX Foundation or Fabric/OneLake only where management approves a clear, non-duplicative role.', C.blue);
  addCard(s, 8.76, 3.13, 4.06, 2.55, 'SAP DevOps and fast-track resources',
    'Phase 1: controlled SAP transports, named approvals, version records and rollback—formal SAP DevOps pipeline does not yet exist.\nNext phase: source control, automated testing, release gates, repeatable promotion and monitoring.\nFast-track ask: +1 Copilot/agent developer, +1 QA/UAT/evidence specialist and +1 SAP BDC/Foundry integration engineer.', C.orange);

  s.addShape(pptx.ShapeType.roundRect, { x: 0.5, y: 5.93, w: 12.3, h: 0.95, rectRadius: 0.05, fill: { color: C.navy }, line: { color: C.navy } });
  s.addText('DECISION REQUIRED', { x: 0.72, y: 6.08, w: 1.75, h: 0.2, fontSize: 8.3, bold: true, color: '78D4D0', charSpacing: 0.9, margin: 0 });
  s.addText('Protect the existing internal owners through go-live and approve a small surge team to fast-track the remaining capabilities. Treat SAP BDC + Azure AI Foundry/Azure Foundry + SAP DevOps as a separately governed next-phase roadmap—not a September re-platforming exercise.', { x: 2.35, y: 6.02, w: 10.05, h: 0.55, fontSize: 11, bold: true, color: C.white, margin: 0.02, valign: 'mid' });
}

pptx.writeFile({ fileName: '/Users/vikrambala/copilotstudio/Velora_Executive_AI_Follow_Up_3_Slides.pptx' });
