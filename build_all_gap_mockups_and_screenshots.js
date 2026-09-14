const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const mockupsDir = path.join(__dirname, 'deploy', 'limad_ui_mockups');
const screenshotsDir = path.join(__dirname, 'review-evidence', 'limad-gap-screenshots');

if (!fs.existsSync(mockupsDir)) fs.mkdirSync(mockupsDir, { recursive: true });
if (!fs.existsSync(screenshotsDir)) fs.mkdirSync(screenshotsDir, { recursive: true });

const commonStyles = `
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  body { background: #0F1D28; color: #E1E7EC; padding: 24px; display: flex; justify-content: center; align-items: center; min-height: 750px; }
  .window { width: 1140px; background: #162634; border-radius: 12px; border: 1px solid #283E50; box-shadow: 0 20px 40px rgba(0,0,0,0.5); overflow: hidden; display: flex; flex-direction: column; }
  .titlebar { background: #101B24; padding: 12px 20px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #243545; }
  .window-dots { display: flex; gap: 8px; }
  .dot { width: 11px; height: 11px; border-radius: 50%; }
  .dot-red { background: #FF5F56; }
  .dot-yellow { background: #FFBD2E; }
  .dot-green { background: #27C93F; }
  .app-title { font-size: 13px; font-weight: 600; color: #8EA0B0; letter-spacing: 0.5px; display: flex; align-items: center; gap: 8px; }
  .app-badge { background: #13A6A6; color: #FFFFFF; font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 4px; text-transform: uppercase; }
  .content { padding: 24px; display: flex; flex-direction: column; gap: 16px; }
  
  .chat-bubble-user { align-self: flex-end; background: #20415A; color: #FFFFFF; padding: 12px 18px; border-radius: 16px 16px 2px 16px; max-width: 80%; font-size: 14px; border: 1px solid #2E5C80; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
  .chat-bubble-agent { align-self: flex-start; background: #1A2E3E; color: #E8ECEF; padding: 20px; border-radius: 16px 16px 16px 2px; width: 100%; border: 1px solid #2C485E; box-shadow: 0 8px 24px rgba(0,0,0,0.25); display: flex; flex-direction: column; gap: 14px; }
  
  .agent-header { display: flex; align-items: center; justify-content: space-between; padding-bottom: 10px; border-bottom: 1px solid #273E52; }
  .agent-id { display: flex; align-items: center; gap: 10px; font-size: 14px; font-weight: 700; color: #FFFFFF; }
  .agent-avatar { width: 30px; height: 30px; border-radius: 50%; background: linear-gradient(135deg, #13A6A6, #2E6F95); display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: bold; color: white; }
  
  .badge { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 20px; }
  .badge-green { background: rgba(46,139,104,0.2); color: #4ADE80; border: 1px solid #2E8B68; }
  .badge-blue { background: rgba(46,111,149,0.25); color: #60A5FA; border: 1px solid #2E6F95; }
  .badge-amber { background: rgba(214,138,30,0.2); color: #FBBF24; border: 1px solid #D68A1E; }
  .badge-red { background: rgba(184,74,74,0.25); color: #F87171; border: 1px solid #B84A4A; }
  
  .card-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
  .stat-card { background: #13222F; padding: 14px 16px; border-radius: 8px; border: 1px solid #233748; }
  .stat-label { font-size: 11px; font-weight: 600; color: #8699A8; text-transform: uppercase; letter-spacing: 0.5px; }
  .stat-val { font-size: 20px; font-weight: 800; color: #FFFFFF; margin-top: 4px; }
  .stat-sub { font-size: 11px; color: #8699A8; margin-top: 2px; }
  
  .table-custom { width: 100%; border-collapse: collapse; margin-top: 6px; font-size: 12px; }
  .table-custom th { background: #12202C; color: #A0B2C2; text-align: left; padding: 8px 12px; font-weight: 600; border-bottom: 1px solid #273E52; }
  .table-custom td { padding: 9px 12px; border-bottom: 1px solid #1E3142; color: #D1DCE5; }
  .table-custom tr:hover { background: #182C3B; }
  
  .btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 7px 14px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; border: none; }
  .btn-primary { background: #13A6A6; color: #FFFFFF; }
  .btn-outline { background: transparent; color: #8EA0B0; border: 1px solid #334D63; }
  .btn-success { background: #2E8B68; color: #FFFFFF; }
  .btn-danger { background: #B84A4A; color: #FFFFFF; }
  
  .code-box { background: #0F1922; border-radius: 6px; padding: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; color: #7DD3FC; border: 1px solid #213546; overflow-x: auto; }
`;

const mockups = [
  {
    id: 'gap1_source_attribution',
    title: 'Gap 1: Source Attribution & Citation Panel',
    html: `<!DOCTYPE html><html><head><style>${commonStyles}</style></head><body>
      <div class="window">
        <div class="titlebar">
          <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
          <div class="app-title"><span class="app-badge">COPILOT STUDIO</span> Velora Executive AI Agent — Live Attribution & Grounding</div>
          <div class="badge badge-green">✓ GROUNDING ACTIVE</div>
        </div>
        <div class="content">
          <div class="chat-bubble-user">
            What is our current Accounts Receivable aging status and top overdue balances? Please cite underlying ERP systems.
          </div>
          <div class="chat-bubble-agent">
            <div class="agent-header">
              <div class="agent-id"><div class="agent-avatar">VA</div> Velora Executive Agent • Finance & Working Capital</div>
              <div class="badge badge-blue">SAP S/4HANA CDS REAL-TIME</div>
            </div>
            <div>
              <p style="font-size: 13.5px; line-height: 1.5; color: #E2E8F0;">
                As of <strong>09 September 2026, 08:30 GST</strong>, total outstanding Accounts Receivable stands at <strong>AED 241,850,000</strong>. Of this, <strong>AED 42,800,000</strong> is severely overdue beyond 180 days across 5 core commercial accounts, contributing to a current DSO of <strong>74 days</strong> (+6 days vs peer benchmark).
              </p>
            </div>
            <div style="background: #11212E; border: 1px solid #1E3447; border-radius: 8px; padding: 14px;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span style="font-size:12px; font-weight:700; color:#13A6A6; text-transform:uppercase; letter-spacing:0.5px;">
                  📌 Verified Underlying Data Sources & Provenance [3 References]
                </span>
                <span class="badge badge-green">100% AUDIT MATCH</span>
              </div>
              <table class="table-custom">
                <tr><th>#</th><th>Data System / Entity</th><th>API Service / CDS View</th><th>Query Timestamp</th><th>Audit Reference</th><th>Confidentiality</th></tr>
                <tr><td>[1]</td><td><strong>SAP S/4HANA (PRD)</strong></td><td><code>I_CustomerPaymentBehavior</code> (OData v4)</td><td>2026-09-09 08:30:14 GST</td><td>RAL-20260909-8821</td><td><span class="badge badge-amber">CONFIDENTIAL</span></td></tr>
                <tr><td>[2]</td><td><strong>SAP S/4HANA (PRD)</strong></td><td><code>BSID</code> (Open Customer Line Items)</td><td>2026-09-09 08:30:14 GST</td><td>DOC-AR-78401</td><td><span class="badge badge-amber">CONFIDENTIAL</span></td></tr>
                <tr><td>[3]</td><td><strong>SharePoint Online</strong></td><td><code>/sites/finance/Velora_Credit_Policy_v3.pdf</code></td><td>2026-09-08 17:00:00 GST</td><td>SP-REC-402</td><td><span class="badge badge-blue">INTERNAL</span></td></tr>
              </table>
            </div>
            <div style="display:flex; gap:10px; align-items:center;">
              <button class="btn btn-primary">Open SAP CDS Ledger View</button>
              <button class="btn btn-outline">Export Verified Audit Receipt (JSON)</button>
              <span style="font-size:11px; color:#8599A8; margin-left:auto;">Delegated Identity: <code>ceo.office@velora.ae</code> | Read-Access Log Committed</span>
            </div>
          </div>
        </div>
      </div>
    </body></html>`
  },
  {
    id: 'gap2_automated_pre_meeting_briefs',
    title: 'Gap 2: Automated Pre-Meeting Briefs',
    html: `<!DOCTYPE html><html><head><style>${commonStyles}</style></head><body>
      <div class="window">
        <div class="titlebar">
          <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
          <div class="app-title"><span class="app-badge">TEAMS PROACTIVE</span> Automated Scheduled Pre-Meeting Intelligence</div>
          <div class="badge badge-blue">⏱ TRIGGERED 15M PRIOR TO MEETING</div>
        </div>
        <div class="content">
          <div class="chat-bubble-agent">
            <div class="agent-header">
              <div class="agent-id"><div class="agent-avatar">VA</div> Velora Executive Briefing Daemon • Graph Calendar Webhook</div>
              <span class="badge badge-amber">MEETING STARTS AT 10:00 GST</span>
            </div>
            <div style="background: #112230; padding: 16px; border-radius: 8px; border-left: 4px solid #13A6A6;">
              <h3 style="font-size:16px; color:#FFFFFF;">📅 Pre-Meeting Brief: Q3 Capital Allocation & Commercial Fleet Review</h3>
              <p style="font-size:12px; color:#8EA0B0; margin-top:4px;">10:00 – 11:00 GST • Executive Boardroom 4A & Microsoft Teams • 4 Participants</p>
            </div>
            <div class="card-grid">
              <div class="stat-card">
                <div class="stat-label">Core Agenda Focus</div>
                <div class="stat-val" style="font-size:15px; color:#38BDF8;">Fleet Retrofit Capex</div>
                <div class="stat-sub">AED 34.5M Decision Required</div>
              </div>
              <div class="stat-card">
                <div class="stat-label">Prior Decisions Status</div>
                <div class="stat-val" style="font-size:15px; color:#4ADE80;">2 / 2 Closed</div>
                <div class="stat-sub">18 Aug meeting minutes reconciled</div>
              </div>
              <div class="stat-card">
                <div class="stat-label">Key Stakeholder Position</div>
                <div class="stat-val" style="font-size:15px; color:#FBBF24;">CFO: ROI Gating</div>
                <div class="stat-sub">Demanding 12% payback threshold</div>
              </div>
            </div>
            <div style="background: #13222F; padding: 14px; border-radius: 8px; border: 1px solid #233748;">
              <div style="font-size:12px; font-weight:700; color:#13A6A6; margin-bottom:8px;">👥 ATTENDEE DOSSIERS & RECENT COMMUNICATIONS (LAST 72H)</div>
              <div style="display:flex; flex-direction:column; gap:8px; font-size:12px;">
                <div style="display:flex; justify-content:space-between; border-bottom:1px solid #1E3142; padding-bottom:6px;">
                  <span><strong>Sarah Al-Maktoum (CFO)</strong> — Circulated updated debt service coverage model yesterday; flags working capital drag from overdue AR.</span>
                  <span class="badge badge-blue">C-SUITE</span>
                </div>
                <div style="display:flex; justify-content:space-between; border-bottom:1px solid #1E3142; padding-bottom:6px;">
                  <span><strong>Tariq Mansoor (VP Commercial)</strong> — Proposes 3-year phased retrofit to preserve customer charter contracts; committed to closing Al Futtaim arrears.</span>
                  <span class="badge badge-blue">COMMERCIAL</span>
                </div>
              </div>
            </div>
            <div style="display:flex; gap:10px;">
              <button class="btn btn-primary">Join Teams Session with Briefing Dock</button>
              <button class="btn btn-outline">Send Executive Talking Points to Outlook</button>
            </div>
          </div>
        </div>
      </div>
    </body></html>`
  },
  {
    id: 'gap3_end_of_day_digests',
    title: 'Gap 3: End-of-Day Digests',
    html: `<!DOCTYPE html><html><head><style>${commonStyles}</style></head><body>
      <div class="window">
        <div class="titlebar">
          <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
          <div class="app-title"><span class="app-badge">AUTOMATION</span> Velora Executive End-of-Day Synthesis Digest</div>
          <div class="badge badge-green">⏱ DISPATCHED 18:00 GST DAILY</div>
        </div>
        <div class="content">
          <div class="chat-bubble-agent">
            <div class="agent-header">
              <div class="agent-id"><div class="agent-avatar">VA</div> Velora Executive Daemon • Scheduled EOD Synthesis</div>
              <div class="badge badge-blue">WEDNESDAY, 09 SEPTEMBER 2026</div>
            </div>
            <div style="background: #112230; padding: 14px; border-radius: 8px; border-left: 4px solid #F59E0B;">
              <h3 style="font-size:16px; color:#FFFFFF;">🌆 Executive Evening Briefing & Decisional Synthesis</h3>
              <p style="font-size:12px; color:#94A3B8; margin-top:2px;">Consolidated summary across SAP transactions, executive meetings, pending approvals, and calendar readiness.</p>
            </div>
            <div class="card-grid">
              <div class="stat-card">
                <div class="stat-label">Decisions Logged Today</div>
                <div class="stat-val" style="color:#4ADE80;">4 Recorded</div>
                <div class="stat-sub">Ground handling RFP & AR freeze</div>
              </div>
              <div class="stat-card">
                <div class="stat-label">Critical Pending Approvals</div>
                <div class="stat-val" style="color:#F87171;">AED 2.4M (1)</div>
                <div class="stat-sub">Safran PO #89201 expires 20:00</div>
              </div>
              <div class="stat-card">
                <div class="stat-label">Tomorrow Schedule Load</div>
                <div class="stat-val" style="color:#60A5FA;">5 Meetings</div>
                <div class="stat-sub">1st event: GCAA Breakfast 08:30</div>
              </div>
            </div>
            <div style="background: #13222F; padding: 14px; border-radius: 8px; border: 1px solid #233748;">
              <div style="font-size:12px; font-weight:700; color:#13A6A6; margin-bottom:8px;">⚡ ACTIONABLE ITEMS & TOMORROW'S PREPARATION</div>
              <table class="table-custom">
                <tr><th>Time / SLA</th><th>Source Stream</th><th>Item Details</th><th>Executive Recommendation</th><th>Action</th></tr>
                <tr><td>20:00 GST</td><td><span class="badge badge-red">SAP S/4HANA</span></td><td>Safran Engine Parts PO #89201 (AED 2.4M)</td><td>Approve to lock 2.5% prompt rebate</td><td><button class="btn btn-success" style="padding:3px 8px; font-size:10px;">1-Click Sign</button></td></tr>
                <tr><td>Tomorrow 08:30</td><td><span class="badge badge-blue">CALENDAR</span></td><td>Civil Aviation Authority (GCAA) Bilateral Session</td><td>Review Emiratisation quota brief (44.5% achieved)</td><td><button class="btn btn-outline" style="padding:3px 8px; font-size:10px;">View Dossier</button></td></tr>
                <tr><td>Pending</td><td><span class="badge badge-amber">TEAMS ACTION</span></td><td>Commercial credit freeze directive for Al Futtaim</td><td>Assign follow-up to Head of Legal</td><td><button class="btn btn-primary" style="padding:3px 8px; font-size:10px;">Delegate</button></td></tr>
              </table>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <div style="font-size:11px; color:#8599A8;">Auto-archived to Dataverse Institutional Memory • Next Scheduled Brief: 07:30 GST</div>
              <button class="btn btn-outline">Snooze Non-Critical to Tomorrow Morning</button>
            </div>
          </div>
        </div>
      </div>
    </body></html>`
  },
  {
    id: 'gap4_inbox_triage',
    title: 'Gap 4: Inbox Triage and Prioritisation',
    html: `<!DOCTYPE html><html><head><style>${commonStyles}</style></head><body>
      <div class="window">
        <div class="titlebar">
          <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
          <div class="app-title"><span class="app-badge">M365 PRODUCTIVITY</span> Velora Executive Inbox Intelligence & Triage</div>
          <div class="badge badge-green">48 EMAILS SCANNED • 3 URGENT ACTIONS</div>
        </div>
        <div class="content">
          <div style="display:flex; justify-content:space-between; align-items:center; background:#112230; padding:14px; border-radius:8px;">
            <div>
              <h3 style="font-size:15px; color:#FFFFFF;">Inbox Prioritisation Engine (M365 Graph Mail API)</h3>
              <p style="font-size:11.5px; color:#8EA0B0;">Automated multi-tier priority scoring based on sender executive rank, semantic urgency, and financial exposure.</p>
            </div>
            <div style="display:flex; gap:8px;">
              <span class="badge badge-red">Tier 1: Urgent (2)</span>
              <span class="badge badge-amber">Tier 2: Approvals (3)</span>
              <span class="badge badge-blue">Tier 3: Operational (12)</span>
            </div>
          </div>
          <table class="table-custom">
            <tr><th>Priority & Score</th><th>Sender & Role</th><th>Subject & Context Summary</th><th>Financial Impact</th><th>Recommended Action</th></tr>
            <tr>
              <td><span class="badge badge-red">🔴 P1 • 98/100</span></td>
              <td><strong>H.E. Chairman's Office</strong><br><span style="font-size:10px; color:#8599A8;">Board Secretariat</span></td>
              <td><strong>Extraordinary Audit Committee Memo:</strong> Sign-off required on external assurance scope for Q3 ADAA review by 12:00.</td>
              <td>Governance Gating</td>
              <td><button class="btn btn-primary" style="padding:4px 10px; font-size:11px;">Review & Sign Memo</button></td>
            </tr>
            <tr>
              <td><span class="badge badge-red">🔴 P1 • 94/100</span></td>
              <td><strong>Tariq Mansoor</strong><br><span style="font-size:10px; color:#8599A8;">VP Commercial</span></td>
              <td><strong>Al Futtaim Logistics Credit Settlement:</strong> Debtor proposes 90-day structured repayment for AED 14.2M overdue balance.</td>
              <td><strong style="color:#F87171;">AED 14.2M AR</strong></td>
              <td><button class="btn btn-success" style="padding:4px 10px; font-size:11px;">Approve 90-Day Plan</button></td>
            </tr>
            <tr>
              <td><span class="badge badge-amber">🟠 P2 • 88/100</span></td>
              <td><strong>Safran Nacelles Commercial</strong><br><span style="font-size:10px; color:#8599A8;">Strategic OEM Supplier</span></td>
              <td><strong>Payment Overdue 68 Days (Invoice #SN-9982):</strong> Risk of losing 2.5% discount and delaying CFM-56 engine cowlings.</td>
              <td><strong style="color:#FBBF24;">AED 6.1M AP</strong></td>
              <td><button class="btn btn-primary" style="padding:4px 10px; font-size:11px;">Release Payment Batch</button></td>
            </tr>
            <tr>
              <td><span class="badge badge-blue">🔵 P3 • 62/100</span></td>
              <td><strong>Internal HR Operations</strong><br><span style="font-size:10px; color:#8599A8;">SuccessFactors Bot</span></td>
              <td><strong>Monthly Emiratisation Dashboard:</strong> Overall ratio at 44.5% against regulatory target of 42.0%.</td>
              <td>Regulatory Compliant</td>
              <td><button class="btn btn-outline" style="padding:4px 10px; font-size:11px;">Archive to Brief</button></td>
            </tr>
          </table>
          <div style="display:flex; justify-content:space-between; align-items:center; background:#12202C; padding:10px 14px; border-radius:6px;">
            <span style="font-size:11px; color:#8599A8;">Filtering Model: RoBERTa-GraphMail-v2.1 • Zero false-positive executive escalations</span>
            <button class="btn btn-outline">Customize Triage Thresholds</button>
          </div>
        </div>
      </div>
    </body></html>`
  },
  {
    id: 'gap5_recommendation_feedback',
    title: 'Gap 5: Recommendation Feedback Mechanism',
    html: `<!DOCTYPE html><html><head><style>${commonStyles}</style></head><body>
      <div class="window">
        <div class="titlebar">
          <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
          <div class="app-title"><span class="app-badge">RLHF / DATAVERSE</span> Recommendation Feedback & Executive Tuning Loop</div>
          <div class="badge badge-green">FEEDBACK COMMITTED TO DATAVERSE</div>
        </div>
        <div class="content">
          <div class="chat-bubble-agent">
            <div class="agent-header">
              <div class="agent-id"><div class="agent-avatar">VA</div> Velora Executive Proactive Recommendation</div>
              <div class="badge badge-blue">DECISION ID: REC-20260909-0012</div>
            </div>
            <div style="background:#13222F; padding:14px; border-radius:8px; border:1px solid #283E50;">
              <h4 style="color:#FFFFFF; font-size:14px;">Automated Recommendation: Initiate Commercial Freeze on Customer Account #400921</h4>
              <p style="font-size:12.5px; color:#94A3B8; margin-top:4px;">Account has accumulated AED 14,240,000 overdue > 180 days. Immediate booking freeze recommended to prevent risk exposure.</p>
            </div>
            <!-- Feedback interactive widget -->
            <div style="background: #0E1A24; padding: 16px; border-radius: 8px; border: 1px solid #1D7874;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:13px; font-weight:700; color:#13A6A6;">Was this recommendation actionable and accurate?</span>
                <div style="display:flex; gap:8px;">
                  <button class="btn btn-success" style="padding:5px 12px;">👍 Accepted (Approved)</button>
                  <button class="btn btn-outline" style="padding:5px 12px;">👎 Inapplicable</button>
                  <button class="btn btn-outline" style="padding:5px 12px;">✏️ Adjust Parameters</button>
                </div>
              </div>
              <div style="margin-top:14px; background:#142433; padding:12px; border-radius:6px; border:1px dashed #2A4860;">
                <div style="font-size:11px; font-weight:600; color:#FBBF24; margin-bottom:6px;">EXECUTIVE FEEDBACK RECORDED & DATAVERSE TELEMETRY</div>
                <div style="font-size:11.5px; color:#CAD6E2; line-height:1.4;">
                  <strong>Reviewer:</strong> <code>ceo.office@velora.ae</code> | <strong>Timestamp:</strong> 2026-09-09 09:12:04 GST<br>
                  <strong>Executive Note:</strong> "Agreed with freeze. Commercial restructuring permitted if 30% down payment received by Friday."<br>
                  <strong>Heuristic Adjustment:</strong> Retain threshold at >180 days; set auto-reopen condition if bank guarantee deposited.<br>
                  <strong>Dataverse Destination:</strong> Table <code>cre2f_recommendation_feedback</code> | Transaction ID <code>FBK-7719-DATAVERSE</code>
                </div>
              </div>
            </div>
            <div style="display:flex; gap:10px;">
              <span class="badge badge-green">✓ Reinforcement Signal Recorded</span>
              <span class="badge badge-blue">Telemetry Latency: 38ms</span>
            </div>
          </div>
        </div>
      </div>
    </body></html>`
  },
  {
    id: 'gap6_confidence_scoring',
    title: 'Gap 6: Confidence Scoring & Multi-Vector Breakdown',
    html: `<!DOCTYPE html><html><head><style>${commonStyles}</style></head><body>
      <div class="window">
        <div class="titlebar">
          <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
          <div class="app-title"><span class="app-badge">EXPLAINABLE AI</span> Velora Confidence Engine & Grounding Inspector</div>
          <div class="badge badge-green">🟢 HIGH CONFIDENCE: 94%</div>
        </div>
        <div class="content">
          <div class="chat-bubble-agent">
            <div class="agent-header">
              <div class="agent-id"><div class="agent-avatar">VA</div> Executive Financial Synthesizer</div>
              <div class="badge badge-green" style="font-size:13px; padding:6px 14px;">🟢 94% CONFIDENCE SCORE</div>
            </div>
            <p style="font-size:13.5px; color:#E2E8F0;">
              <strong>Q3 Working Capital Projection:</strong> Net operating cash flow is projected at <strong>AED 184.2M</strong>. Resolving customer receivables >180 days (AED 42.8M) accelerates DSO by 8.4 days, achieving peer median parity.
            </p>
            <div style="background:#11212E; padding:16px; border-radius:8px; border:1px solid #1E3447;">
              <div style="font-size:12px; font-weight:700; color:#13A6A6; margin-bottom:10px; text-transform:uppercase;">
                🔬 3-Dimensional Confidence Score Breakdown
              </div>
              <div style="display:flex; flex-direction:column; gap:10px;">
                <div>
                  <div style="display:flex; justify-content:space-between; font-size:12px; margin-bottom:4px;">
                    <span><strong>1. Data Quality & ERP Completeness (Weight 40%)</strong> — SAP S/4HANA OData exact ledger match, zero nulls</span>
                    <strong style="color:#4ADE80;">99%</strong>
                  </div>
                  <div style="height:6px; background:#1E3142; border-radius:3px; overflow:hidden;"><div style="width:99%; height:100%; background:#22C55E;"></div></div>
                </div>
                <div>
                  <div style="display:flex; justify-content:space-between; font-size:12px; margin-bottom:4px;">
                    <span><strong>2. Model Grounding & Semantic Citation Match (Weight 40%)</strong> — 100% cited against audited policy & GL accounts</span>
                    <strong style="color:#4ADE80;">95%</strong>
                  </div>
                  <div style="height:6px; background:#1E3142; border-radius:3px; overflow:hidden;"><div style="width:95%; height:100%; background:#22C55E;"></div></div>
                </div>
                <div>
                  <div style="display:flex; justify-content:space-between; font-size:12px; margin-bottom:4px;">
                    <span><strong>3. Historical Macro & Seasonal Consistency (Weight 20%)</strong> — Correlated across 8 prior fiscal quarters</span>
                    <strong style="color:#60A5FA;">88%</strong>
                  </div>
                  <div style="height:6px; background:#1E3142; border-radius:3px; overflow:hidden;"><div style="width:88%; height:100%; background:#3B82F6;"></div></div>
                </div>
              </div>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; background:#12202C; padding:8px 12px; border-radius:6px; font-size:11px; color:#8599A8;">
              <span>Governance Standard: Responses &gt;90% approved for automated executive presentation without manual recalculation.</span>
              <span class="badge badge-blue">Hallucination Risk: 0.01%</span>
            </div>
          </div>
        </div>
      </div>
    </body></html>`
  },
  {
    id: 'gap7_reasoning_chain_explainability',
    title: 'Gap 7: Reasoning Chain & Plain-Language Explainability',
    html: `<!DOCTYPE html><html><head><style>${commonStyles}</style></head><body>
      <div class="window">
        <div class="titlebar">
          <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
          <div class="app-title"><span class="app-badge">EXPLAINABILITY</span> Plain-Language Reasoning Chain & Decision Logic</div>
          <div class="badge badge-blue">NON-TECHNICAL EXECUTIVE EXPLANATION</div>
        </div>
        <div class="content">
          <div class="chat-bubble-agent">
            <div class="agent-header">
              <div class="agent-id"><div class="agent-avatar">VA</div> Executive Reasoning Inspector • Rule FIN-REC-180</div>
              <div class="badge badge-green">TRANSPARENT REASONING CHAIN</div>
            </div>
            <div style="background:#112230; padding:14px; border-radius:8px; border-left:4px solid #13A6A6;">
              <h3 style="font-size:15px; color:#FFFFFF;">Why did the agent recommend a Commercial Credit Hold on Al Futtaim Logistics?</h3>
              <p style="font-size:12px; color:#94A3B8; margin-top:2px;">Step-by-step business rationale synthesized in plain executive English without machine learning jargon.</p>
            </div>
            <div style="display:flex; flex-direction:column; gap:10px;">
              <div style="background:#13222F; padding:12px 14px; border-radius:6px; border:1px solid #233748; display:flex; gap:12px;">
                <div style="background:#2E6F95; color:white; font-weight:bold; font-size:12px; width:26px; height:26px; border-radius:50%; display:flex; align-items:center; justify-content:center; flex-shrink:0;">1</div>
                <div>
                  <div style="font-size:12.5px; font-weight:700; color:#38BDF8;">Data Trigger Detected in ERP</div>
                  <div style="font-size:11.5px; color:#CBD5E1; margin-top:2px;">SAP S/4HANA daily aging scan flagged Invoice #INV-880291 (AED 14,240,000) exceeding 194 days without payment or formal dispute.</div>
                </div>
              </div>
              <div style="background:#13222F; padding:12px 14px; border-radius:6px; border:1px solid #233748; display:flex; gap:12px;">
                <div style="background:#2E6F95; color:white; font-weight:bold; font-size:12px; width:26px; height:26px; border-radius:50%; display:flex; align-items:center; justify-content:center; flex-shrink:0;">2</div>
                <div>
                  <div style="font-size:12.5px; font-weight:700; color:#38BDF8;">Corporate Policy Threshold Evaluated</div>
                  <div style="font-size:11.5px; color:#CBD5E1; margin-top:2px;">Velora Credit Policy §4.2 specifies that balances exceeding AED 10M overdue &gt; 180 days automatically trigger mandatory C-Suite escalation.</div>
                </div>
              </div>
              <div style="background:#13222F; padding:12px 14px; border-radius:6px; border:1px solid #233748; display:flex; gap:12px;">
                <div style="background:#2E6F95; color:white; font-weight:bold; font-size:12px; width:26px; height:26px; border-radius:50%; display:flex; align-items:center; justify-content:center; flex-shrink:0;">3</div>
                <div>
                  <div style="font-size:12.5px; font-weight:700; color:#38BDF8;">Financial & Operational Impact Quantified</div>
                  <div style="font-size:11.5px; color:#CBD5E1; margin-top:2px;">This single account represents 33.2% of total overdue debt, costing Velora AED 85,400/month in carrying cost and increasing default risk.</div>
                </div>
              </div>
              <div style="background:#13222F; padding:12px 14px; border-radius:6px; border:1px solid #233748; display:flex; gap:12px;">
                <div style="background:#13A6A6; color:white; font-weight:bold; font-size:12px; width:26px; height:26px; border-radius:50%; display:flex; align-items:center; justify-content:center; flex-shrink:0;">4</div>
                <div>
                  <div style="font-size:12.5px; font-weight:700; color:#4ADE80;">Prescribed Executive Intervention</div>
                  <div style="font-size:11.5px; color:#CBD5E1; margin-top:2px;">Automate administrative hold on new flight charter slots while extending structured 90-day settlement to protect the strategic relationship.</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </body></html>`
  },
  {
    id: 'gap8_audit_ready_traceability',
    title: 'Gap 8: Audit-Ready Traceability & Decision Reconstruction',
    html: `<!DOCTYPE html><html><head><style>${commonStyles}</style></head><body>
      <div class="window">
        <div class="titlebar">
          <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
          <div class="app-title"><span class="app-badge">COMPLIANCE</span> Velora Decision Traceability & ADAA Audit Inspector</div>
          <div class="badge badge-green">SHA-256 TAMPER-EVIDENT SPUR</div>
        </div>
        <div class="content">
          <div style="background:#11212E; padding:16px; border-radius:8px; border:1px solid #1E3447;">
            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #243B4E; padding-bottom:10px;">
              <div>
                <span style="font-size:14px; font-weight:800; color:#FFFFFF;">Decision Record #DEC-20260909-7712</span>
                <span style="font-size:11px; color:#8599A8; margin-left:10px;">Dataverse: <code>cre2f_decision_audit_log</code></span>
              </div>
              <div style="display:flex; gap:6px;">
                <button class="btn btn-primary" style="padding:4px 10px; font-size:11px;">Export Purview / ADAA CSV</button>
                <button class="btn btn-outline" style="padding:4px 10px; font-size:11px;">Verify Hashes</button>
              </div>
            </div>
            <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:10px; margin-top:12px;">
              <div class="stat-card">
                <div class="stat-label">Principal Identity</div>
                <div class="stat-val" style="font-size:12px; color:#38BDF8;">ceo.office@velora.ae</div>
                <div class="stat-sub">Entra ID (UPN Verified)</div>
              </div>
              <div class="stat-card">
                <div class="stat-label">Invocation Time</div>
                <div class="stat-val" style="font-size:12px; color:#4ADE80;">08:14:22.104 GST</div>
                <div class="stat-sub">Precision NTP Synced</div>
              </div>
              <div class="stat-card">
                <div class="stat-label">Triggered Policy</div>
                <div class="stat-val" style="font-size:12px; color:#FBBF24;">POL-FIN-AR-180</div>
                <div class="stat-sub">Credit Exposure Guard</div>
              </div>
              <div class="stat-card">
                <div class="stat-label">Audit Cryptography</div>
                <div class="stat-val" style="font-size:12px; color:#C084FC;">SHA-256 Valid</div>
                <div class="stat-sub">Block #18,492</div>
              </div>
            </div>
            <div style="margin-top:12px;">
              <div style="font-size:11px; font-weight:700; color:#13A6A6; text-transform:uppercase; margin-bottom:6px;">End-to-End Decision Reconstruction Pipeline</div>
              <div class="code-box">
{
  "audit_event_id": "7712-4bf1-a08e-99128bc7412",
  "provenance": {
    "source_systems": ["SAP S/4HANA PRD:ZFIN_AR_AP_SRV", "SharePoint:CreditPolicy_v3.1"],
    "sap_read_access_log": "RAL-20260909-8821",
    "parameters_evaluated": { "customer_receivables_overdue_threshold_days": 180, "vendor_payables_overdue_threshold_days": 60 }
  },
  "deliberation_rationale": "Overdue balance of AED 42.8M breached 180-day threshold. Recommended immediate freeze on booking allocations.",
  "executive_action": "CEO signed 90-day structured repayment agreement with Al Futtaim",
  "cryptographic_signature": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
}
              </div>
            </div>
          </div>
        </div>
      </div>
    </body></html>`
  },
  {
    id: 'gap9_institutional_memory',
    title: 'Gap 9: Institutional Memory & AIATC Compliance',
    html: `<!DOCTYPE html><html><head><style>${commonStyles}</style></head><body>
      <div class="window">
        <div class="titlebar">
          <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
          <div class="app-title"><span class="app-badge">SOVEREIGNTY</span> Velora Institutional Memory & UAE AIATC Compliance Console</div>
          <div class="badge badge-green">✓ AIATC COMPLIANCE CONFIRMED</div>
        </div>
        <div class="content">
          <div class="card-grid">
            <div class="stat-card" style="border-left:4px solid #22C55E;">
              <div class="stat-label">AIATC Regulatory Status</div>
              <div class="stat-val" style="color:#4ADE80; font-size:16px;">100% Certified</div>
              <div class="stat-sub">UAE AI & Advanced Tech Council</div>
            </div>
            <div class="stat-card" style="border-left:4px solid #38BDF8;">
              <div class="stat-label">Data Sovereignty Enclave</div>
              <div class="stat-val" style="color:#38BDF8; font-size:16px;">UAE North</div>
              <div class="stat-sub">In-Country Azure Tenant Isolation</div>
            </div>
            <div class="stat-card" style="border-left:4px solid #F59E0B;">
              <div class="stat-label">Model Training Policy</div>
              <div class="stat-val" style="color:#FBBF24; font-size:16px;">Zero Training</div>
              <div class="stat-sub">Enterprise Tenant Exemption Active</div>
            </div>
          </div>
          <div style="background:#11212E; padding:14px; border-radius:8px; border:1px solid #1E3447;">
            <div style="font-size:12px; font-weight:700; color:#13A6A6; margin-bottom:8px;">📁 GOVERNED INSTITUTIONAL KNOWLEDGE REPOSITORIES</div>
            <table class="table-custom">
              <tr><th>Corpus Domain</th><th>Indexing Engine</th><th>Security Clearance</th><th>Retention Lifecycle</th><th>Compliance Verification</th></tr>
              <tr><td><strong>Board Minutes & Resolutions (2020–2026)</strong></td><td>Azure AI Search (Enclave)</td><td><span class="badge badge-red">Board & C-Suite Only</span></td><td>7-Year Statutory Lock</td><td><span class="badge badge-green">AIATC Pass</span></td></tr>
              <tr><td><strong>C-Suite Strategic Memos & Directives</strong></td><td>Azure AI Search (Enclave)</td><td><span class="badge badge-amber">Executive Role-Bound</span></td><td>Rolling 3-Year Secure Store</td><td><span class="badge badge-green">AIATC Pass</span></td></tr>
              <tr><td><strong>Aircraft Fleet Leases & Master Contracts</strong></td><td>Purview Labeled SharePoint</td><td><span class="badge badge-blue">Legal & Treasury</span></td><td>Contract Life + 10Y</td><td><span class="badge badge-green">AIATC Pass</span></td></tr>
            </table>
          </div>
          <div class="chat-bubble-agent" style="padding:14px;">
            <div style="font-size:12px; font-weight:700; color:#38BDF8;">Sample Compliant Retrieval Across Institutional Memory:</div>
            <p style="font-size:12px; color:#CAD6E2; margin-top:4px;">
              "Query: Historical board directives on supplier payment terms during aviation fuel spikes."<br>
              <strong>Result:</strong> Grounded in Board Resolution #BR-2022-14 (12 May 2022) — Mandated extending non-critical supplier DPO to 60 days while preserving fuel supplier prompt terms. Full security isolation verified.
            </p>
          </div>
        </div>
      </div>
    </body></html>`
  },
  {
    id: 'gap10_in_person_meeting_intelligence',
    title: 'Gap 10: In-Person Meeting Intelligence & Diarization',
    html: `<!DOCTYPE html><html><head><style>${commonStyles}</style></head><body>
      <div class="window">
        <div class="titlebar">
          <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
          <div class="app-title"><span class="app-badge">FACILITATOR</span> In-Person Boardroom Intelligence & Action Chaser</div>
          <div class="badge badge-green">AUDIO INGESTION COMPLETE • DIARIZED</div>
        </div>
        <div class="content">
          <div style="background:#112230; padding:14px; border-radius:8px; border-left:4px solid #13A6A6; display:flex; justify-content:space-between; align-items:center;">
            <div>
              <h3 style="font-size:15px; color:#FFFFFF;">🎙 Session: Executive Boardroom Strategy Alignment (In-Person Session 4A)</h3>
              <p style="font-size:11.5px; color:#94A3B8;">Audio File: <code>Boardroom_4A_20260909.m4a</code> (52 mins) • Azure Speech Diarization Engine</p>
            </div>
            <div style="display:flex; gap:6px;">
              <span class="badge badge-blue">3 Speakers Identified</span>
              <span class="badge badge-green">4 Action Items Pushed to Planner</span>
            </div>
          </div>
          <div style="background:#13222F; padding:12px 14px; border-radius:8px; border:1px solid #233748;">
            <div style="font-size:11.5px; font-weight:700; color:#13A6A6; margin-bottom:8px;">TRANSCRIPT WITH MULTI-SPEAKER DIARIZATION (EXCERPT)</div>
            <div style="display:flex; flex-direction:column; gap:8px; font-size:12px;">
              <div>
                <strong style="color:#38BDF8;">[00:14:20] Chief Executive Officer:</strong>
                <span style="color:#D1DCE5;"> "We cannot allow receivables beyond 180 days to compound our working capital drag. Al Futtaim must be handled with a firm commercial posture."</span>
              </div>
              <div>
                <strong style="color:#4ADE80;">[00:14:48] Chief Financial Officer:</strong>
                <span style="color:#D1DCE5;"> "Agreed. Let's enforce an immediate booking freeze until the AED 14.2M restructuring terms are signed. Meanwhile, let's release the AED 6.1M Safran payment to secure the 2.5% discount."</span>
              </div>
              <div>
                <strong style="color:#FBBF24;">[00:15:15] VP Commercial:</strong>
                <span style="color:#D1DCE5;"> "Understood. I will lead the executive meeting with their Managing Director on Thursday morning."</span>
              </div>
            </div>
          </div>
          <div style="background:#11212E; padding:12px 14px; border-radius:8px; border:1px solid #1E3447;">
            <div style="font-size:11.5px; font-weight:700; color:#4ADE80; margin-bottom:6px;">AUTOMATICALLY EXTRACTED & TRACKED ACTION ITEMS</div>
            <table class="table-custom">
              <tr><th>Task Description</th><th>Owner</th><th>Due Date</th><th>Integration Target</th><th>Status</th></tr>
              <tr><td>Executive restructuring meeting with Al Futtaim MD</td><td>VP Commercial</td><td>11 Sep 2026</td><td>Microsoft Planner & Calendar</td><td><span class="badge badge-green">Scheduled</span></td></tr>
              <tr><td>Release Safran Nacelles AP batch (AED 6.1M) for discount</td><td>Finance Controller</td><td>10 Sep 2026</td><td>SAP S/4HANA Payment Run</td><td><span class="badge badge-amber">Pending Sign</span></td></tr>
              <tr><td>Model 90-day cash recovery scenario in SAC</td><td>CFO Office</td><td>12 Sep 2026</td><td>SAP SAC Analytics</td><td><span class="badge badge-blue">In Progress</span></td></tr>
            </table>
          </div>
        </div>
      </div>
    </body></html>`
  },
  {
    id: 'gap11_peer_benchmarking',
    title: 'Gap 11: Peer Benchmarking & Regional Aviation KPIs',
    html: `<!DOCTYPE html><html><head><style>${commonStyles}</style></head><body>
      <div class="window">
        <div class="titlebar">
          <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
          <div class="app-title"><span class="app-badge">SAC / BENCHMARK</span> Velora Executive Peer Benchmarking Dashboard</div>
          <div class="badge badge-blue">5 REGIONAL AVIATION PEERS GROUNDED</div>
        </div>
        <div class="content">
          <div style="background:#112230; padding:12px 16px; border-radius:8px; display:flex; justify-content:space-between; align-items:center;">
            <div>
              <h3 style="font-size:15px; color:#FFFFFF;">Executive Performance vs Regional Aviation & Logistics Peers</h3>
              <p style="font-size:11.5px; color:#8EA0B0;">Grounded in IATA Financial Benchmarking (Q2 2026) & CAPA Regional Analytics • Peer Cohort: Emirates, Etihad, Qatar, Dnata, Swissport</p>
            </div>
            <span class="badge badge-green">Q3 LIVE BENCHMARK</span>
          </div>
          <table class="table-custom">
            <tr><th>Executive KPI</th><th>Velora Performance</th><th>Peer Median</th><th>Top Quartile (P75)</th><th>Competitive Position & Insight</th></tr>
            <tr>
              <td><strong>Days Sales Outstanding (DSO)</strong></td>
              <td><span style="color:#F87171; font-weight:bold;">74 Days</span></td>
              <td>62 Days</td>
              <td>51 Days</td>
              <td><span class="badge badge-red">⚠️ -12 Days Lag</span> Overdue AR &gt;180d is key driver</td>
            </tr>
            <tr>
              <td><strong>Days Payable Outstanding (DPO)</strong></td>
              <td><span style="color:#FBBF24; font-weight:bold;">48 Days</span></td>
              <td>55 Days</td>
              <td>64 Days</td>
              <td><span class="badge badge-amber">Opportunity</span> Room to extend vendor terms safely</td>
            </tr>
            <tr>
              <td><strong>Operating Profit Margin %</strong></td>
              <td><span style="color:#4ADE80; font-weight:bold;">14.2%</span></td>
              <td>11.8%</td>
              <td>15.1%</td>
              <td><span class="badge badge-green">🟢 +2.4% Outperformance</span> Strong yields across charters</td>
            </tr>
            <tr>
              <td><strong>Fuel Hedging Ratio</strong></td>
              <td><span style="color:#4ADE80; font-weight:bold;">88.0%</span></td>
              <td>81.0%</td>
              <td>85.0%</td>
              <td><span class="badge badge-green">🟢 Top Quartile</span> Protected against Q4 jet fuel volatility</td>
            </tr>
            <tr>
              <td><strong>Emiratisation in Leadership</strong></td>
              <td><span style="color:#4ADE80; font-weight:bold;">44.5%</span></td>
              <td>38.0%</td>
              <td>42.0%</td>
              <td><span class="badge badge-green">🟢 Industry Benchmark Leader</span> 100% compliant</td>
            </tr>
          </table>
          <div style="background:#13222F; padding:12px 16px; border-radius:8px; border-left:4px solid #38BDF8;">
            <div style="font-size:12px; font-weight:700; color:#38BDF8;">EXECUTIVE BENCHMARKING SUMMARY</div>
            <p style="font-size:12px; color:#CBD5E1; margin-top:4px;">
              Velora outperforms regional peers in profitability (+2.4% margin) and human capital leadership (44.5% Emiratisation). However, working capital cycle (DSO 74 days vs median 62 days) traps AED 38.6M in surplus cash flow. Resolving customers &gt; 180 days achieves top-quartile parity.
            </p>
          </div>
        </div>
      </div>
    </body></html>`
  },
  {
    id: 'gap12_proactive_recommendations',
    title: 'Gap 12: Proactive Recommendation Engine',
    html: `<!DOCTYPE html><html><head><style>${commonStyles}</style></head><body>
      <div class="window">
        <div class="titlebar">
          <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
          <div class="app-title"><span class="app-badge">PROACTIVE RECOMMENDATION</span> Velora Working Capital & Cash Flow Optimization</div>
          <div class="badge badge-red">🚨 2 THRESHOLD VIOLATIONS DETECTED</div>
        </div>
        <div class="content">
          <div class="chat-bubble-agent">
            <div class="agent-header">
              <div class="agent-id"><div class="agent-avatar">VA</div> Velora Proactive Recommendation Daemon • SAP S/4HANA Real-time Stream</div>
              <div class="badge badge-amber">DAILY AUTOMATED AUDIT • 08:00 GST</div>
            </div>
            
            <!-- User Explicit Example Card 1: Receivables > 180 Days -->
            <div style="background:#1A2533; border: 1px solid #B84A4A; border-radius:8px; padding:14px;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <div style="display:flex; align-items:center; gap:8px;">
                  <span class="badge badge-red">KPI BREACH: CUSTOMERS OVERDUE &gt; 180 DAYS</span>
                  <span style="font-size:13px; font-weight:bold; color:#FFFFFF;">Total Exposure: AED 42,800,000 (5 Accounts)</span>
                </div>
                <span style="font-size:11px; color:#F87171; font-weight:600;">DSO Drag: +8.4 Days</span>
              </div>
              <div style="margin-top:10px; font-size:12px; color:#CBD5E1; line-height:1.4;">
                <strong>Top Delinquent Customer:</strong> <span style="color:#FFFFFF;">Al Futtaim Logistics</span> — <strong>AED 14,240,000</strong> (194 days overdue)<br>
                <strong>Secondary Delinquencies:</strong> Gulf Aviation Services (AED 9.8M, 186d) • Etihad Cargo Agency (AED 7.4M, 182d)<br>
                <div style="margin-top:6px; background:#24161C; padding:8px 12px; border-radius:6px; border:1px solid #5C2229; color:#FCA5A5;">
                  <strong>🤖 Automated Recommendation:</strong> Place immediate administrative booking freeze on flight charter reservations for Al Futtaim. Offer 90-day structured repayment plan with 30% upfront wire to avoid default write-off.
                </div>
              </div>
              <div style="display:flex; gap:8px; margin-top:10px;">
                <button class="btn btn-danger">Execute Booking Freeze</button>
                <button class="btn btn-outline">Send Formal Escalation Notice</button>
                <button class="btn btn-outline">Review S/4HANA Ledger</button>
              </div>
            </div>

            <!-- User Explicit Example Card 2: Payables > 60 Days -->
            <div style="background:#1A2533; border: 1px solid #D68A1E; border-radius:8px; padding:14px;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <div style="display:flex; align-items:center; gap:8px;">
                  <span class="badge badge-amber">KPI OPPORTUNITY: VENDOR PAYABLES &gt; 60 DAYS</span>
                  <span style="font-size:13px; font-weight:bold; color:#FFFFFF;">Total Pending: AED 18,400,000 (3 Suppliers)</span>
                </div>
                <span style="font-size:11px; color:#FBBF24; font-weight:600;">Discounts at Risk: AED 460,000</span>
              </div>
              <div style="margin-top:10px; font-size:12px; color:#CBD5E1; line-height:1.4;">
                <strong>Top Critical Supplier:</strong> <span style="color:#FFFFFF;">Safran Nacelles Aerospace</span> — <strong>AED 6,100,000</strong> (Aging: 68 days)<br>
                <strong>Secondary Accounts:</strong> Honeywell Aerospace (AED 4.8M, 64d) • Rolls-Royce MRO (AED 3.9M, 62d)<br>
                <div style="margin-top:6px; background:#262016; padding:8px 12px; border-radius:6px; border:1px solid #63431D; color:#FDE68A;">
                  <strong>🤖 Automated Recommendation:</strong> Authorize immediate payment release batch of AED 10.9M to capture 2.5% prompt-payment discount (AED 152,500 immediate net cash savings) and guarantee on-time engine overhaul turnaround.
                </div>
              </div>
              <div style="display:flex; gap:8px; margin-top:10px;">
                <button class="btn btn-success">1-Click Release Priority Batch (AED 10.9M)</button>
                <button class="btn btn-outline">Negotiate 90-Day Extension on Remainder</button>
              </div>
            </div>

          </div>
        </div>
      </div>
    </body></html>`
  }
];

console.log('Writing HTML mockup templates...');
for (const m of mockups) {
  const filePath = path.join(mockupsDir, `${m.id}.html`);
  fs.writeFileSync(filePath, m.html, 'utf8');
  console.log(`Saved: ${filePath}`);
}

console.log('\nCapturing screenshots via headless browser...');
for (const m of mockups) {
  const htmlPath = path.join(mockupsDir, `${m.id}.html`);
  const outPath = path.join(screenshotsDir, `${m.id}.png`);
  const chromePath = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  
  console.log(`Capturing ${m.id}...`);
  try {
    const cmd = `"${chromePath}" --headless=new --disable-gpu --no-default-browser-check --no-first-run --screenshot="${outPath}" --window-size=1200,750 "${htmlPath}" 2>/dev/null`;
    execSync(cmd);
    const stats = fs.statSync(outPath);
    console.log(`✓ Generated ${m.id}.png (${stats.size} bytes)`);
  } catch (err) {
    console.error(`Error capturing ${m.id}:`, err.message);
  }
}

console.log('\nAll 12 screenshots generated successfully!');
