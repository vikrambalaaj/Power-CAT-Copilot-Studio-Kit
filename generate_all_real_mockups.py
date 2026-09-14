import os

OUT_DIR = "deploy/limad_ui_mockups"
os.makedirs(OUT_DIR, exist_ok=True)

COMMON_CSS = """
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  body { background: #0B1924; color: #E1E7EC; padding: 20px; display: flex; justify-content: center; align-items: center; min-height: 750px; }
  .window { width: 1160px; background: #142433; border-radius: 12px; border: 1px solid #23394D; box-shadow: 0 20px 40px rgba(0,0,0,0.6); overflow: hidden; display: flex; flex-direction: column; }
  .titlebar { background: #0E1A24; padding: 12px 20px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #203547; }
  .window-dots { display: flex; gap: 8px; }
  .dot { width: 11px; height: 11px; border-radius: 50%; }
  .dot-red { background: #FF5F56; }
  .dot-yellow { background: #FFBD2E; }
  .dot-green { background: #27C93F; }
  .app-title { font-size: 13px; font-weight: 600; color: #8EA0B0; letter-spacing: 0.5px; display: flex; align-items: center; gap: 8px; }
  .app-badge { background: #13A6A6; color: #FFFFFF; font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 4px; text-transform: uppercase; }
  .content { padding: 20px 24px; display: flex; flex-direction: column; gap: 14px; }
  
  .chat-bubble-user { align-self: flex-end; background: #1D394E; color: #FFFFFF; padding: 12px 18px; border-radius: 14px 14px 2px 14px; max-width: 82%; font-size: 13.5px; border: 1px solid #2B5473; box-shadow: 0 4px 12px rgba(0,0,0,0.25); }
  .chat-bubble-agent { align-self: flex-start; background: #182B3A; color: #E8ECEF; padding: 18px 20px; border-radius: 14px 14px 14px 2px; width: 100%; border: 1px solid #294459; box-shadow: 0 8px 24px rgba(0,0,0,0.3); display: flex; flex-direction: column; gap: 12px; }
  
  .agent-header { display: flex; align-items: center; justify-content: space-between; padding-bottom: 8px; border-bottom: 1px solid #23394D; }
  .agent-id { display: flex; align-items: center; gap: 10px; font-size: 13.5px; font-weight: 700; color: #FFFFFF; }
  .agent-avatar { width: 28px; height: 28px; border-radius: 50%; background: linear-gradient(135deg, #13A6A6, #2E6F95); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: bold; color: white; }
  
  .badge { display: inline-flex; align-items: center; gap: 5px; font-size: 10.5px; font-weight: 700; padding: 3px 8px; border-radius: 16px; }
  .badge-green { background: rgba(46,139,104,0.2); color: #4ADE80; border: 1px solid #2E8B68; }
  .badge-blue { background: rgba(46,111,149,0.25); color: #60A5FA; border: 1px solid #2E6F95; }
  .badge-amber { background: rgba(214,138,30,0.2); color: #FBBF24; border: 1px solid #D68A1E; }
  .badge-red { background: rgba(184,74,74,0.25); color: #F87171; border: 1px solid #B84A4A; }
  .badge-purple { background: rgba(139,92,246,0.25); color: #C084FC; border: 1px solid #8B5CF6; }
  
  .card-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
  .stat-card { background: #101E2B; padding: 12px 14px; border-radius: 8px; border: 1px solid #203547; }
  .stat-label { font-size: 10.5px; font-weight: 600; color: #8699A8; text-transform: uppercase; letter-spacing: 0.5px; }
  .stat-val { font-size: 19px; font-weight: 800; color: #FFFFFF; margin-top: 3px; }
  .stat-sub { font-size: 10.5px; color: #8699A8; margin-top: 2px; }
  
  .table-custom { width: 100%; border-collapse: collapse; margin-top: 4px; font-size: 11.5px; }
  .table-custom th { background: #0E1A24; color: #94A3B8; text-align: left; padding: 7px 10px; font-weight: 600; border-bottom: 1px solid #23394D; }
  .table-custom td { padding: 8px 10px; border-bottom: 1px solid #1C3042; color: #CFDCE6; }
  .table-custom tr:hover { background: #162938; }
  
  .btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 6px 12px; border-radius: 6px; font-size: 11.5px; font-weight: 600; cursor: pointer; border: none; }
  .btn-primary { background: #13A6A6; color: #FFFFFF; }
  .btn-outline { background: transparent; color: #94A3B8; border: 1px solid #334D63; }
  .btn-success { background: #2E8B68; color: #FFFFFF; }
  .btn-danger { background: #B84A4A; color: #FFFFFF; }
  
  .banner-scheduled { background: #102534; border: 1px solid #1B4561; border-radius: 6px; padding: 8px 14px; font-size: 11.5px; color: #60A5FA; display: flex; align-items: center; justify-content: space-between; }
  .code-box { background: #0B141C; border-radius: 6px; padding: 10px 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; color: #7DD3FC; border: 1px solid #1E3345; overflow-x: auto; }
"""

# -------------------------------------------------------------
# 1. GAP 1: SOURCE ATTRIBUTION
# -------------------------------------------------------------
html1 = f"""<!DOCTYPE html><html><head><style>{COMMON_CSS}</style></head><body>
<div class="window">
  <div class="titlebar">
    <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
    <div class="app-title"><span class="app-badge">COPILOT STUDIO</span> Velora One — Live Attribution & Grounding</div>
    <div class="badge badge-green">✓ GROUNDING ACTIVE</div>
  </div>
  <div class="content">
    <div class="chat-bubble-user">
      What is our active workforce headcount by department and current Emiratisation KPI? Cite all underlying ERP sources.
    </div>
    <div class="chat-bubble-agent">
      <div class="agent-header">
        <div class="agent-id"><div class="agent-avatar">V1</div> Velora One Executive Agent • SAP SuccessFactors Live</div>
        <div class="badge badge-blue">SAP SF OData v2 LIVE</div>
      </div>
      <div>
        <p style="font-size: 13.5px; line-height: 1.5; color: #E2E8F0;">
          Live workforce status from <strong>SAP SuccessFactors (api22.sapsf.com)</strong> as of <strong>09 Sep 2026, 13:59 GST</strong>: Total headcount is <strong>4,112</strong> across <strong>98 departments</strong>, with <strong>3,704 active eligible employees</strong>. Emiratisation stands at <strong>3.4%</strong> (126 UAE nationals) against statutory target of <strong>52.0%</strong> (Below Target, gap: -48.6%). PDPL privacy controls applied.
        </p>
      </div>
      <div class="card-grid">
        <div class="stat-card">
          <div class="stat-label">Active Headcount</div>
          <div class="stat-val">3,704</div>
          <div class="stat-sub">Total Headcount: 4,112 (98 Depts)</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Emiratisation Ratio</div>
          <div class="stat-val" style="color:#F87171;">3.4%</div>
          <div class="stat-sub">126 UAE Nationals vs 52.0% Target</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Top Department Load</div>
          <div class="stat-val">1,109</div>
          <div class="stat-sub">Check-in & Boarding (27.0%)</div>
        </div>
      </div>
      <div style="background: #0E1A24; border: 1px solid #1E3447; border-radius: 8px; padding: 12px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
          <span style="font-size:11.5px; font-weight:700; color:#13A6A6; text-transform:uppercase; letter-spacing:0.5px;">
            📌 Verified Underlying ERP Sources & Provenance [3 Direct References]
          </span>
          <span class="badge badge-green">100% AUDIT COMMITTED</span>
        </div>
        <table class="table-custom">
          <tr><th>#</th><th>Data System / Entity</th><th>Live OData Service / Endpoint</th><th>Query Timestamp</th><th>Audit Correlation ID</th><th>Classification</th></tr>
          <tr><td>[1]</td><td><strong>SAP SuccessFactors</strong></td><td><code>https://api22.sapsf.com/odata/v2/EmpJob</code></td><td>2026-09-09 13:59:43 GST</td><td>corr-vel-e2e-001</td><td><span class="badge badge-amber">CONFIDENTIAL</span></td></tr>
          <tr><td>[2]</td><td><strong>SAP SuccessFactors</strong></td><td><code>https://api22.sapsf.com/odata/v2/PerPersonal</code></td><td>2026-09-09 13:59:48 GST</td><td>corr-vel-e2e-001</td><td><span class="badge badge-amber">CONFIDENTIAL</span></td></tr>
          <tr><td>[3]</td><td><strong>Dataverse Audit Ledger</strong></td><td><code>cre2f_veloraagentauditlog</code> (Table)</td><td>2026-09-09 13:59:52 GST</td><td>inv-001-e</td><td><span class="badge badge-blue">INTERNAL</span></td></tr>
        </table>
      </div>
      <div style="display:flex; gap:10px; align-items:center;">
        <button class="btn btn-primary">Drilldown Department Table</button>
        <button class="btn btn-outline">Export Provenance Receipt (JSON)</button>
        <span style="font-size:11px; color:#8599A8; margin-left:auto;">Executive: <code>balaadm@velora.ae</code> | Tenant: <code>7d167021-f5e9-4331-9b75-d44d55a1ce9b</code></span>
      </div>
    </div>
  </div>
</div>
</body></html>"""
open(f"{OUT_DIR}/gap1_source_attribution.html", "w").write(html1)

# -------------------------------------------------------------
# 2. GAP 2: AUTOMATED PRE-MEETING BRIEFS
# -------------------------------------------------------------
html2 = f"""<!DOCTYPE html><html><head><style>{COMMON_CSS}</style></head><body>
<div class="window">
  <div class="titlebar">
    <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
    <div class="app-title"><span class="app-badge">SCHEDULED DAEMON</span> Velora One — Automated Pre-Meeting Intelligence</div>
    <div class="badge badge-blue">T-15 MIN AUTONOMOUS TRIGGER</div>
  </div>
  <div class="content">
    <div class="banner-scheduled">
      <span>⏰ <strong>Automated Schedule Trigger:</strong> Pushed 15 minutes before calendar event <em>'Executive Operations & Workforce Alignment'</em></span>
      <span class="badge badge-green">DELIVERED AT 08:15 GST</span>
    </div>
    <div class="chat-bubble-agent">
      <div class="agent-header">
        <div class="agent-id"><div class="agent-avatar">V1</div> Velora One • Pre-Meeting Executive Briefing (VEL-E2E-008)</div>
        <div class="badge badge-purple">4-DOMAIN REAL-TIME SYNTHESIS</div>
      </div>
      <div>
        <h4 style="font-size:14px; color:#FFFFFF; margin-bottom:4px;">Executive Operations & Workforce Alignment (08:30 – 09:30 GST)</h4>
        <p style="font-size:12px; color:#94A3B8;">Attendees: Vikram Bala (CEO Office, <code>balaadm@velora.ae</code>), Ahmed Nuaimi (CFO Office, <code>ahmed.nuaimi@velora.ae</code>)</p>
      </div>
      <div class="card-grid">
        <div class="stat-card">
          <div class="stat-label">Live SF Headcount</div>
          <div class="stat-val">3,704</div>
          <div class="stat-sub">Ground Handling Ops: 2,020 staff</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">S/4HANA AR Exposure</div>
          <div class="stat-val" style="color:#F87171;">AED 2.40M</div>
          <div class="stat-sub">Overdue > 180d in CoCode 1000</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">SAC EBITDA Margin</div>
          <div class="stat-val">18.4%</div>
          <div class="stat-sub">Regional Peer Median: 19.2%</div>
        </div>
      </div>
      <div style="background:#0E1A24; padding:12px; border-radius:8px; border:1px solid #1E3447; font-size:12px; line-height:1.5;">
        <strong style="color:#13A6A6;">Dossier Insights for Today's Alignment Session:</strong><br>
        • <strong>Ground Handling Staffing:</strong> Check-in (1,109 staff) is operating at 94% roster capacity. Ramp Operations (911 staff) has completed shift reorganization.<br>
        • <strong>Receivables Exposure:</strong> Customer overdue balances exceeding 180 days (AED 2.40M in CoCode 1000) contribute +8.4 days to DSO. Recommend dunning notice execution.<br>
        • <strong>Payables Timing:</strong> S/4HANA AP shows AED 8.10M due this month; priority batch payment captures prompt settlement discount.
      </div>
      <div style="display:flex; gap:8px;">
        <button class="btn btn-primary">Join Teams Call</button>
        <button class="btn btn-outline">Add Agenda Topic</button>
        <button class="btn btn-outline">Share Dossier with Ahmed</button>
      </div>
    </div>
  </div>
</div>
</body></html>"""
open(f"{OUT_DIR}/gap2_automated_pre_meeting_briefs.html", "w").write(html2)

# -------------------------------------------------------------
# 3. GAP 3: END-OF-DAY DIGESTS
# -------------------------------------------------------------
html3 = f"""<!DOCTYPE html><html><head><style>{COMMON_CSS}</style></head><body>
<div class="window">
  <div class="titlebar">
    <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
    <div class="app-title"><span class="app-badge">SCHEDULED DAEMON</span> Velora One — Executive End-of-Day Digest</div>
    <div class="badge badge-amber">DAILY 17:30 GST RUN (VEL-E2E-004)</div>
  </div>
  <div class="content">
    <div class="banner-scheduled">
      <span>⏰ <strong>Daily Scheduled Run:</strong> <code>velora.scheduled-prompt [end-of-day]</code> dispatched to <code>balaadm@velora.ae</code></span>
      <span class="badge badge-green">SAFETY: DRAFT CONTAINMENT ONLY</span>
    </div>
    <div class="chat-bubble-agent">
      <div class="agent-header">
        <div class="agent-id"><div class="agent-avatar">V1</div> Velora One • Daily Executive Wrap-Up</div>
        <div class="badge badge-blue">PLANNER + M365 + S/4HANA</div>
      </div>
      <div class="card-grid">
        <div class="stat-card">
          <div class="stat-label">Tasks Completed</div>
          <div class="stat-val" style="color:#4ADE80;">2 Done</div>
          <div class="stat-sub">S/4 Dunning & Staffing Reallocation</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Pending / Overdue</div>
          <div class="stat-val" style="color:#F87171;">1 Overdue</div>
          <div class="stat-sub">Q3 Headcount Review (Ahmed Nuaimi)</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Tomorrow 08:00 Prep</div>
          <div class="stat-val">1 Session</div>
          <div class="stat-sub">Executive Operations Review</div>
        </div>
      </div>
      <div style="background:#0E1A24; border:1px solid #1E3447; border-radius:8px; padding:12px;">
        <span style="font-size:11.5px; font-weight:700; color:#13A6A6; text-transform:uppercase;">
          📋 Daily Closed-Loop Summary & Tomorrow's Action Tracker
        </span>
        <table class="table-custom">
          <tr><th>Item / Stream</th><th>Source</th><th>Status</th><th>Executive Note</th></tr>
          <tr><td>S/4HANA Dunning Run Review</td><td>S/4HANA Finance</td><td><span class="badge badge-green">COMPLETED</span></td><td>AED 2.4M overdue accounts flagged for delivery hold</td></tr>
          <tr><td>Staffing Reallocation (45 staff)</td><td>SuccessFactors</td><td><span class="badge badge-green">COMPLETED</span></td><td>Reassigned from Baggage (413) to Check-in (1,109)</td></tr>
          <tr><td>Q3 Headcount & Emiratisation Review</td><td>Microsoft Planner</td><td><span class="badge badge-red">OVERDUE</span></td><td>Owner: Ahmed Nuaimi • Due today 16:00 GST</td></tr>
        </table>
      </div>
      <div style="background:#162432; border:1px solid #28445C; border-radius:8px; padding:12px; font-size:12px;">
        <strong style="color:#60A5FA;">Draft Follow-up Prepared:</strong> <em>"Subject: Follow-up on Overdue Q3 Headcount Review"</em> to <code>ahmed.nuaimi@velora.ae</code>.<br>
        <span style="color:#94A3B8;">Safety Gate Enforced: Draft generated in Outlook drafts folder. Zero automatic dispatch without explicit executive approval.</span>
      </div>
      <div style="display:flex; gap:8px;">
        <button class="btn btn-primary">Review & Send Draft Email</button>
        <button class="btn btn-outline">Postpone Planner Task</button>
        <button class="btn btn-outline">Close Digest</button>
      </div>
    </div>
  </div>
</div>
</body></html>"""
open(f"{OUT_DIR}/gap3_end_of_day_digests.html", "w").write(html3)

# -------------------------------------------------------------
# 4. GAP 4: INBOX TRIAGE AND PRIORITISATION
# -------------------------------------------------------------
html4 = f"""<!DOCTYPE html><html><head><style>{COMMON_CSS}</style></head><body>
<div class="window">
  <div class="titlebar">
    <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
    <div class="app-title"><span class="app-badge">GRAPH MAIL REST</span> Velora One — Executive Inbox Triage & Prioritisation</div>
    <div class="badge badge-red">2 VIP ITEMS REQUIRING ATTENTION</div>
  </div>
  <div class="content">
    <div class="banner-scheduled">
      <span>📥 <strong>Mailbox:</strong> <code>balaadm@velora.ae</code> • 4-Tier Semantic Priority Model • 14 Non-Essential Emails Filtered</span>
      <span class="badge badge-green">SLA COMPLIANT</span>
    </div>
    <div class="chat-bubble-agent">
      <div class="agent-header">
        <div class="agent-id"><div class="agent-avatar">V1</div> Velora One • Inbox Triage Engine (PROD-004 & PROD-009)</div>
        <div class="badge badge-blue">SEMANTIC EXPOSURE SCORING</div>
      </div>
      <div style="display:flex; flex-direction:column; gap:10px;">
        <div style="background:#1B2735; border:1px solid #B84A4A; border-radius:8px; padding:12px;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span class="badge badge-red">P1 URGENT VIP</span>
              <strong style="font-size:13px; color:#FFFFFF;">Ahmed Nuaimi (CFO Office) — "URGENT: Q3 Budget & Workforce Variance Review"</strong>
            </div>
            <span style="font-size:11px; color:#F87171; font-weight:700;">Score: 98/100 • 14:12 GST</span>
          </div>
          <p style="font-size:12px; color:#CBD5E1; margin-top:6px; line-height:1.4;">
            Variance detected in Ground Handling staffing (-45 headcount) and AED 2.4M overdue customer receivables in CoCode 1000. Executive approval required prior to board pack publication.
          </p>
          <div style="display:flex; gap:8px; margin-top:8px;">
            <button class="btn btn-primary">Draft Executive Reply</button>
            <button class="btn btn-outline">Schedule 15m Sync</button>
          </div>
        </div>

        <div style="background:#1B2735; border:1px solid #D68A1E; border-radius:8px; padding:12px;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span class="badge badge-amber">P2 FINANCIAL ALERT</span>
              <strong style="font-size:13px; color:#FFFFFF;">SAP S/4HANA Alert — "Automated Dunning Run: Customer AR Overdue > 180 Days"</strong>
            </div>
            <span style="font-size:11px; color:#FBBF24; font-weight:700;">Score: 88/100 • 13:45 GST</span>
          </div>
          <p style="font-size:12px; color:#CBD5E1; margin-top:6px; line-height:1.4;">
            Open items exceeding 180 days reached AED 2,400,000.00 across delinquent commercial accounts. Automated recommendation suggests delivery freeze on Plant 1AD1.
          </p>
          <div style="display:flex; gap:8px; margin-top:8px;">
            <button class="btn btn-primary">Open AR Aging View</button>
            <button class="btn btn-outline">Review Delinquent Customers</button>
          </div>
        </div>

        <div style="background:#13212E; border:1px solid #203547; border-radius:8px; padding:10px;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span class="badge badge-blue">P3 OPERATIONAL</span>
              <span style="font-size:12.5px; color:#94A3B8;">Microsoft Planner — Task Completed: Ramp Operations Shift Schedule Update (911 staff)</span>
            </div>
            <span style="font-size:11px; color:#60A5FA;">Score: 62/100</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
</body></html>"""
open(f"{OUT_DIR}/gap4_inbox_triage.html", "w").write(html4)

# -------------------------------------------------------------
# 5. GAP 5: RECOMMENDATION FEEDBACK
# -------------------------------------------------------------
html5 = f"""<!DOCTYPE html><html><head><style>{COMMON_CSS}</style></head><body>
<div class="window">
  <div class="titlebar">
    <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
    <div class="app-title"><span class="app-badge">ACTIVE FEEDBACK LOOP</span> Velora One — Recommendation Feedback & Tuning</div>
    <div class="badge badge-green">TELEMETRY: DATAVERSE COMMIT</div>
  </div>
  <div class="content">
    <div class="chat-bubble-agent">
      <div class="agent-header">
        <div class="agent-id"><div class="agent-avatar">V1</div> Velora One • Active Recommendation Card</div>
        <div class="badge badge-amber">AWAITING EXECUTIVE DECISION</div>
      </div>
      <div style="background:#162634; border:1px solid #B84A4A; border-radius:8px; padding:14px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <strong style="color:#FFFFFF; font-size:13.5px;">Recommended Action: Issue Dunning Escalation & Delivery Freeze (CoCode 1000)</strong>
          <span class="badge badge-red">EXPOSURE: AED 2,400,000.00</span>
        </div>
        <p style="font-size:12px; color:#CBD5E1; margin-top:8px; line-height:1.4;">
          S/4HANA customer accounts overdue > 180 days have exceeded credit tolerance. Recommends administrative delivery hold on Plant 1AD1 and formal dunning escalation to recover AED 2.40M.
        </p>
        <div style="display:flex; gap:10px; margin-top:12px; align-items:center;">
          <button class="btn btn-success">👍 Accept & Execute (Approve)</button>
          <button class="btn btn-danger">👎 Reject / Cancel Action</button>
          <button class="btn btn-outline">✏️ Adjust Threshold Parameters</button>
        </div>
      </div>

      <!-- Parameter Adjustment Drawer -->
      <div style="background:#0F1C27; border:1px solid #203547; border-radius:8px; padding:12px;">
        <div style="font-size:11.5px; font-weight:700; color:#13A6A6; text-transform:uppercase; margin-bottom:8px;">
          ⚙️ Executive Qualitative Tuning & Feedback Parameters
        </div>
        <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:10px; font-size:11.5px;">
          <div style="background:#13222F; padding:8px; border-radius:6px;">
            <span style="color:#8699A8;">Overdue Threshold:</span><br>
            <strong style="color:#FFFFFF;">180 Days</strong> (Current Rule)
          </div>
          <div style="background:#13222F; padding:8px; border-radius:6px;">
            <span style="color:#8699A8;">Repayment Terms:</span><br>
            <strong style="color:#FFFFFF;">30% Down / 90d Wire</strong>
          </div>
          <div style="background:#13222F; padding:8px; border-radius:6px;">
            <span style="color:#8699A8;">HMAC Token:</span><br>
            <code style="color:#7DD3FC;">velora_appr_7c4f19a</code>
          </div>
        </div>
        <div class="code-box" style="margin-top:10px;">
          Dataverse Audit Write: table="cre2f_veloraagentauditlog" | record_type="USER_APPROVAL" | user="balaadm@velora.ae" | outcome="APPROVED" | latency=38ms
        </div>
      </div>
    </div>
  </div>
</div>
</body></html>"""
open(f"{OUT_DIR}/gap5_recommendation_feedback.html", "w").write(html5)

# -------------------------------------------------------------
# 6. GAP 6: CONFIDENCE SCORING
# -------------------------------------------------------------
html6 = f"""<!DOCTYPE html><html><head><style>{COMMON_CSS}</style></head><body>
<div class="window">
  <div class="titlebar">
    <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
    <div class="app-title"><span class="app-badge">EVALUATION METRIC</span> Velora One — Multi-Vector Confidence Scoring</div>
    <div class="badge badge-green">SCORE: 0.96 (HIGH CONFIDENCE)</div>
  </div>
  <div class="content">
    <div class="chat-bubble-agent">
      <div class="agent-header">
        <div class="agent-id"><div class="agent-avatar">V1</div> Velora One • Grounding & Confidence Telemetry</div>
        <div class="badge badge-blue">50/50 TEST PACK PASS RATE</div>
      </div>
      <div>
        <p style="font-size:13.5px; color:#E2E8F0; line-height:1.5;">
          Executive recommendations are validated against the <strong>Velora 50-Case Comprehensive Evaluation Test Pack</strong>. Current synthesis achieves a composite confidence rating of <strong>96%</strong> with zero synthetic or hallucinated fallback values.
        </p>
      </div>
      <div class="card-grid">
        <div class="stat-card">
          <div class="stat-label">ERP Grounding Vector</div>
          <div class="stat-val" style="color:#4ADE80;">98%</div>
          <div class="stat-sub">Live OData v2/v4 CDS line item match</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Data Freshness Vector</div>
          <div class="stat-val" style="color:#4ADE80;">99%</div>
          <div class="stat-sub">Snapshot latency 840ms (13:59 GST)</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Policy Compliance</div>
          <div class="stat-val" style="color:#4ADE80;">100%</div>
          <div class="stat-sub">PDPL & Zero-Synthetic rule enforced</div>
        </div>
      </div>
      <div style="background:#0E1A24; border:1px solid #1E3447; border-radius:8px; padding:12px;">
        <span style="font-size:11.5px; font-weight:700; color:#13A6A6; text-transform:uppercase;">
          🛡️ Enterprise Governance Thresholds & Action Gates
        </span>
        <table class="table-custom">
          <tr><th>Confidence Range</th><th>Badge Status</th><th>Permitted Action Mode</th><th>Safeguard Protocol</th></tr>
          <tr><td><strong>90% – 100%</strong></td><td><span class="badge badge-green">HIGH CONFIDENCE</span></td><td>1-Click Executive Execution Permitted</td><td>Full automated audit logging to Dataverse</td></tr>
          <tr><td><strong>70% – 89%</strong></td><td><span class="badge badge-amber">MEDIUM CONFIDENCE</span></td><td>Execution with Secondary Confirmation</td><td>Requires explicit checkbox acknowledgment</td></tr>
          <tr><td><strong>&lt; 70%</strong></td><td><span class="badge badge-red">LOW CONFIDENCE</span></td><td>Transaction Disabled (Read-Only)</td><td>Mandatory human-in-the-loop manual review</td></tr>
        </table>
      </div>
      <div class="code-box">
        Evaluation Suite: 25/25 SuccessFactors PASS • 5/5 S/4HANA Finance PASS • 15/15 M365 PASS • Zero Mock Fallback
      </div>
    </div>
  </div>
</div>
</body></html>"""
open(f"{OUT_DIR}/gap6_confidence_scoring.html", "w").write(html6)

# -------------------------------------------------------------
# 7. GAP 7: REASONING CHAIN / EXPLAINABILITY
# -------------------------------------------------------------
html7 = f"""<!DOCTYPE html><html><head><style>{COMMON_CSS}</style></head><body>
<div class="window">
  <div class="titlebar">
    <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
    <div class="app-title"><span class="app-badge">EXPLAINABLE AI</span> Velora One — Non-Technical Reasoning Chain</div>
    <div class="badge badge-green">4-STEP EXECUTIVE RATIONALE</div>
  </div>
  <div class="content">
    <div class="chat-bubble-user">
      Why is Velora recommending an immediate credit freeze and dunning escalation for Customer Receivables in Company Code 1000?
    </div>
    <div class="chat-bubble-agent">
      <div class="agent-header">
        <div class="agent-id"><div class="agent-avatar">V1</div> Velora One • Decision Explanation Engine (VEL-E2E-024)</div>
        <div class="badge badge-blue">PLAIN EXECUTIVE LANGUAGE</div>
      </div>
      <div style="display:flex; flex-direction:column; gap:8px;">
        <div style="background:#111F2C; border-left:4px solid #13A6A6; padding:10px 14px; border-radius:0 6px 6px 0;">
          <strong style="color:#13A6A6; font-size:12px;">STEP 1: ERP DATA TRIGGER DETECTED</strong>
          <p style="font-size:12px; color:#CBD5E1; margin-top:2px;">
            S/4HANA CDS entity <code>ARageingData</code> identified overdue customer balances of <strong>AED 2,400,000.00</strong> in the <strong>&gt; 180 days overdue</strong> bucket for Company Code 1000, Plant 1AD1.
          </p>
        </div>
        <div style="background:#111F2C; border-left:4px solid #D68A1E; padding:10px 14px; border-radius:0 6px 6px 0;">
          <strong style="color:#FBBF24; font-size:12px;">STEP 2: CORPORATE POLICY RULE EVALUATED</strong>
          <p style="font-size:12px; color:#CBD5E1; margin-top:2px;">
            Corporate Credit Policy Rule §4.2 mandates that any commercial account exceeding 180 days overdue with cumulative exposure &gt; AED 1,000,000 triggers mandatory credit facility suspension.
          </p>
        </div>
        <div style="background:#111F2C; border-left:4px solid #B84A4A; padding:10px 14px; border-radius:0 6px 6px 0;">
          <strong style="color:#F87171; font-size:12px;">STEP 3: FINANCIAL & WORKING CAPITAL IMPACT QUANTIFIED</strong>
          <p style="font-size:12px; color:#CBD5E1; margin-top:2px;">
            Outstanding balance inflates corporate Days Sales Outstanding (DSO) by <strong>+8.4 days</strong> and mandates IFRS 9 bad-debt provisioning of AED 720,000 at next quarterly financial close.
          </p>
        </div>
        <div style="background:#111F2C; border-left:4px solid #2E8B68; padding:10px 14px; border-radius:0 6px 6px 0;">
          <strong style="color:#4ADE80; font-size:12px;">STEP 4: PRESCRIBED EXECUTIVE INTERVENTION</strong>
          <p style="font-size:12px; color:#CBD5E1; margin-top:2px;">
            Suspend open sales order dispatch at Plant 1AD1, issue formal dunning notice to debtor, and propose structured 90-day settlement conditioned on 30% immediate wire payment.
          </p>
        </div>
      </div>
      <div style="display:flex; gap:10px; align-items:center;">
        <button class="btn btn-primary">Proceed with Escalation</button>
        <button class="btn btn-outline">Review S/4HANA Ledger Lines</button>
        <span style="font-size:11px; color:#8699A8; margin-left:auto;">Strict business terminology • Zero LLM prompt/token jargon</span>
      </div>
    </div>
  </div>
</div>
</body></html>"""
open(f"{OUT_DIR}/gap7_reasoning_chain_explainability.html", "w").write(html7)

# -------------------------------------------------------------
# 8. GAP 8: AUDIT-READY TRACEABILITY
# -------------------------------------------------------------
html8 = f"""<!DOCTYPE html><html><head><style>{COMMON_CSS}</style></head><body>
<div class="window">
  <div class="titlebar">
    <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
    <div class="app-title"><span class="app-badge">DATAVERSE AUDIT</span> Velora One — Enterprise Audit-Ready Traceability</div>
    <div class="badge badge-green">TABLE: cre2f_veloraagentauditlog</div>
  </div>
  <div class="content">
    <div class="banner-scheduled">
      <span>🔒 <strong>Dataverse Fail-Closed Audit Trail:</strong> Root Correlation ID <code>corr-vel-e2e-024-trace</code> committed</span>
      <span class="badge badge-green">ADAA & PURVIEW COMPLIANT</span>
    </div>
    <div class="chat-bubble-agent">
      <div class="agent-header">
        <div class="agent-id"><div class="agent-avatar">V1</div> Velora One • Cryptographic Audit Inspector</div>
        <div class="badge badge-purple">SHA-256 TAMPER-EVIDENT</div>
      </div>
      <div style="background:#0E1A24; border:1px solid #1E3447; border-radius:8px; padding:12px;">
        <span style="font-size:11.5px; font-weight:700; color:#13A6A6; text-transform:uppercase;">
          📑 Dataverse Schema Record: cre2f_veloraagentauditlog
        </span>
        <table class="table-custom">
          <tr><th>Column Field</th><th>Logged Transaction Value</th><th>Governance Description</th></tr>
          <tr><td><code>cre2f_rootcorrelationid</code></td><td><code>corr-vel-e2e-024-trace</code></td><td>Cross-system end-to-end transaction link</td></tr>
          <tr><td><code>cre2f_callingagent</code></td><td><code>Velora Executive Agent (v2.1.0-exec)</code></td><td>Parent Copilot Studio orchestrator</td></tr>
          <tr><td><code>cre2f_executingagent</code></td><td><code>Velora S/4HANA Finance MCP</code></td><td>SAP BTP Cloud Foundry execution node</td></tr>
          <tr><td><code>cre2f_useremail</code></td><td><code>balaadm@velora.ae</code></td><td>Delegated Entra ID executive user</td></tr>
          <tr><td><code>cre2f_recordtype</code></td><td><code>TRANSACTION_RESULT</code></td><td>Approval & execution commit phase</td></tr>
          <tr><td><code>cre2f_capability</code></td><td><code>s4__get_receivables_aging</code></td><td>Executed S/4HANA OData tool</td></tr>
          <tr><td><code>cre2f_outcome</code></td><td><span class="badge badge-green">SUCCESS</span></td><td>Zero-error deterministic outcome</td></tr>
          <tr><td><code>cre2f_dataclassification</code></td><td><span class="badge badge-amber">CONFIDENTIAL</span></td><td>PDPL restricted commercial record</td></tr>
        </table>
      </div>
      <div class="code-box">
        SHA-256 Checksum: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 (Verified)
      </div>
      <div style="display:flex; gap:8px;">
        <button class="btn btn-primary">Export ADAA Audit Bundle (CSV)</button>
        <button class="btn btn-outline">Export Cryptographic Trace (JSON)</button>
        <button class="btn btn-outline">Inspect Fail-Closed Rule</button>
      </div>
    </div>
  </div>
</div>
</body></html>"""
open(f"{OUT_DIR}/gap8_audit_ready_traceability.html", "w").write(html8)

# -------------------------------------------------------------
# 9. GAP 9: INSTITUTIONAL MEMORY
# -------------------------------------------------------------
html9 = f"""<!DOCTYPE html><html><head><style>{COMMON_CSS}</style></head><body>
<div class="window">
  <div class="titlebar">
    <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
    <div class="app-title"><span class="app-badge">SOVEREIGN AI</span> Velora One — Institutional Memory & AIATC Compliance</div>
    <div class="badge badge-green">AZURE UAE NORTH ENCLAVE</div>
  </div>
  <div class="content">
    <div class="chat-bubble-user">
      What did we agree during the last working capital review regarding supplier payment terms, and what are my current preferences?
    </div>
    <div class="chat-bubble-agent">
      <div class="agent-header">
        <div class="agent-id"><div class="agent-avatar">V1</div> Velora One • Institutional Memory Service (MEM-001 & MEM-002)</div>
        <div class="badge badge-blue">DATAVERSE SNAPSHOT RECALL</div>
      </div>
      <div class="card-grid">
        <div class="stat-card">
          <div class="stat-label">Session Recall</div>
          <div class="stat-val">30-Day Window</div>
          <div class="stat-sub">Review on 26 Aug 2026 recalled</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Multi-User Isolation</div>
          <div class="stat-val" style="color:#4ADE80;">100% RBAC</div>
          <div class="stat-sub">Zero leakage to exec2@velora.ae</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">AIATC Compliance</div>
          <div class="stat-val" style="color:#4ADE80;">Certified</div>
          <div class="stat-sub">Zero public model retention</div>
        </div>
      </div>
      <div style="background:#0E1A24; border:1px solid #1E3447; border-radius:8px; padding:12px; font-size:12px; line-height:1.5;">
        <strong style="color:#13A6A6;">Recalled Historical Context & Active Executive Preferences:</strong><br>
        • <strong>Historical Agreement (26 Aug 2026):</strong> Agreed that vendor payables &gt; 60 days must be evaluated for prompt payment discount capture before disbursement.<br>
        • <strong>Stored Executive Preferences:</strong> User <code>balaadm@velora.ae</code> requires all financials in <strong>AED</strong>, default plant <strong>1AD1</strong> (GRC1/GRC2), mandatory inclusion of active headcount (3,704), and bulleted executive tables.<br>
        • <strong>Sovereignty & Isolation:</strong> Memory snapshot encrypted in Azure Key Vault HSM in UAE North; strictly inaccessible to unauthorized users.
      </div>
      <div style="display:flex; gap:8px;">
        <button class="btn btn-primary">Update Executive Preferences</button>
        <button class="btn btn-outline">View Memory Snapshot (JSON)</button>
      </div>
    </div>
  </div>
</div>
</body></html>"""
open(f"{OUT_DIR}/gap9_institutional_memory.html", "w").write(html9)

# -------------------------------------------------------------
# 10. GAP 10: IN-PERSON MEETING INTELLIGENCE
# -------------------------------------------------------------
html10 = f"""<!DOCTYPE html><html><head><style>{COMMON_CSS}</style></head><body>
<div class="window">
  <div class="titlebar">
    <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
    <div class="app-title"><span class="app-badge">FACILITATOR MCP</span> Velora One — In-Person Meeting Intelligence</div>
    <div class="badge badge-purple">SPEAKER DIARIZATION ACTIVE</div>
  </div>
  <div class="content">
    <div class="banner-scheduled">
      <span>🎙️ <strong>Boardroom Session:</strong> <em>Executive Boardroom Operations Review — Ground Handling & Logistics Alignment</em></span>
      <span class="badge badge-green">CLOSED-LOOP ACTION SYNC</span>
    </div>
    <div class="chat-bubble-agent">
      <div class="agent-header">
        <div class="agent-id"><div class="agent-avatar">V1</div> Velora One Facilitator • Post-Meeting Synthesis (VEL-E2E-014)</div>
        <div class="badge badge-blue">SPEAKER DIARIZED (3 VOICES)</div>
      </div>
      <div class="card-grid">
        <div class="stat-card">
          <div class="stat-label">Audio Duration</div>
          <div class="stat-val">42 Mins</div>
          <div class="stat-sub">Boardroom Session A-101</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Decisions Logged</div>
          <div class="stat-val" style="color:#4ADE80;">3 Agreed</div>
          <div class="stat-sub">Committed to Dataverse</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Planner Actions</div>
          <div class="stat-val">2 Tasks Synced</div>
          <div class="stat-sub">Assigned with deadlines</div>
        </div>
      </div>
      <div style="background:#0E1A24; border:1px solid #1E3447; border-radius:8px; padding:12px;">
        <span style="font-size:11.5px; font-weight:700; color:#13A6A6; text-transform:uppercase;">
          📋 Synthesized Decisions & Microsoft Planner Synchronization
        </span>
        <table class="table-custom">
          <tr><th>#</th><th>Decision Logged</th><th>Owner</th><th>Destination System</th><th>Status</th></tr>
          <tr><td>[1]</td><td>Freeze credit deliveries on accounts overdue &gt; 180d (AED 2.4M)</td><td>Ahmed Nuaimi</td><td>SAP S/4HANA</td><td><span class="badge badge-green">COMMITTED</span></td></tr>
          <tr><td>[2]</td><td>Reallocate 45 staff from Baggage to Check-in & Boarding (1,109 staff)</td><td>Ramp Ops Lead</td><td>SuccessFactors</td><td><span class="badge badge-green">COMMITTED</span></td></tr>
          <tr><td>[3]</td><td>Release priority vendor payment batch of AED 8.10M (&gt;60 days)</td><td>Ahmed Nuaimi</td><td>Planner: Velora Agent UAT</td><td><span class="badge badge-blue">TASK CREATED</span></td></tr>
        </table>
      </div>
      <div style="background:#162432; border:1px solid #28445C; border-radius:8px; padding:10px; font-size:12px;">
        <strong style="color:#60A5FA;">Safety Gate Verified:</strong> Draft follow-up email prepared for session attendees. Automatic dispatch suppressed awaiting executive review.
      </div>
      <div style="display:flex; gap:8px;">
        <button class="btn btn-primary">Review & Send Email Summary</button>
        <button class="btn btn-outline">View Diarized Transcript</button>
      </div>
    </div>
  </div>
</div>
</body></html>"""
open(f"{OUT_DIR}/gap10_in_person_meeting_intelligence.html", "w").write(html10)

# -------------------------------------------------------------
# 11. GAP 11: PEER BENCHMARKING
# -------------------------------------------------------------
html11 = f"""<!DOCTYPE html><html><head><style>{COMMON_CSS}</style></head><body>
<div class="window">
  <div class="titlebar">
    <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
    <div class="app-title"><span class="app-badge">SAC + SF ANALYTICS</span> Velora One — Grounded Peer Benchmarking</div>
    <div class="badge badge-blue">5 REGIONAL AVIATION PEERS</div>
  </div>
  <div class="content">
    <div class="chat-bubble-agent">
      <div class="agent-header">
        <div class="agent-id"><div class="agent-avatar">V1</div> Velora One • Strategic Peer Benchmarking Console</div>
        <div class="badge badge-green">LIVE SUCCESSFACTORS + SAC</div>
      </div>
      <div style="background:#0E1A24; border:1px solid #1E3447; border-radius:8px; padding:12px;">
        <span style="font-size:11.5px; font-weight:700; color:#13A6A6; text-transform:uppercase;">
          📊 Grounded KPI Benchmark Matrix: Velora vs Regional Aviation Cohort
        </span>
        <table class="table-custom">
          <tr><th>Strategic KPI Metric</th><th>Velora Current</th><th>Peer Median Cohort</th><th>Statutory / Best Practice Target</th><th>Variance & Executive Status</th></tr>
          <tr>
            <td><strong>Emiratisation Ratio</strong></td>
            <td><strong style="color:#F87171;">3.4%</strong> (126 of 3,704)</td>
            <td>14.2%</td>
            <td>52.0% (MoHRE / Nafis)</td>
            <td><span class="badge badge-red">BELOW TARGET (-48.6%)</span></td>
          </tr>
          <tr>
            <td><strong>Days Sales Outstanding (DSO)</strong></td>
            <td><strong style="color:#F87171;">74 Days</strong></td>
            <td>62 Days</td>
            <td>&lt; 60 Days</td>
            <td><span class="badge badge-red">+12 Days Drag (AED 2.4M overdue)</span></td>
          </tr>
          <tr>
            <td><strong>EBITDA Operating Margin</strong></td>
            <td><strong style="color:#4ADE80;">18.4%</strong></td>
            <td>19.2%</td>
            <td>18.0% – 20.0%</td>
            <td><span class="badge badge-green">HEALTHY (-0.8% variance)</span></td>
          </tr>
          <tr>
            <td><strong>Days Payable Outstanding (DPO)</strong></td>
            <td><strong>48 Days</strong></td>
            <td>55 Days</td>
            <td>45 – 60 Days</td>
            <td><span class="badge badge-blue">EARLY DISCOUNT CAPTURE</span></td>
          </tr>
          <tr>
            <td><strong>Ground Handling Productivity</strong></td>
            <td><strong>2,020 Staff</strong> (Check-in/Ramp)</td>
            <td>1,850 Staff</td>
            <td>High Volume Wave Ready</td>
            <td><span class="badge badge-green">ROBUST CAPACITY</span></td>
          </tr>
        </table>
      </div>
      <div style="background:#13222F; border:1px solid #203547; border-radius:8px; padding:10px; font-size:12px; line-height:1.4;">
        <strong style="color:#60A5FA;">Strategic Benchmark Takeaway:</strong> Velora exhibits strong operational margins (18.4%) and ground staff capacity, but working capital is weighed down by receivables overdue &gt; 180 days (AED 2.40M) and Emiratisation requires acceleration toward statutory targets.
      </div>
      <div style="display:flex; gap:8px;">
        <button class="btn btn-primary">Launch Emiratisation Action Plan</button>
        <button class="btn btn-outline">Export SAC Peer Report</button>
      </div>
    </div>
  </div>
</div>
</body></html>"""
open(f"{OUT_DIR}/gap11_peer_benchmarking.html", "w").write(html11)

# -------------------------------------------------------------
# 12. GAP 12: PROACTIVE RECOMMENDATIONS (CORE USER MANDATE)
# -------------------------------------------------------------
html12 = f"""<!DOCTYPE html><html><head><style>{COMMON_CSS}</style></head><body>
<div class="window">
  <div class="titlebar">
    <div class="window-dots"><div class="dot dot-red"></div><div class="dot dot-yellow"></div><div class="dot dot-green"></div></div>
    <div class="app-title"><span class="app-badge">PROACTIVE ENGINE</span> Velora One — Proactive Working Capital Optimization</div>
    <div class="badge badge-red">🚨 2 THRESHOLD VIOLATIONS DETECTED</div>
  </div>
  <div class="content">
    <div class="chat-bubble-agent">
      <div class="agent-header">
        <div class="agent-id"><div class="agent-avatar">V1</div> Velora One Autonomous Daemon • S/4HANA Continuous Stream</div>
        <div class="badge badge-amber">DAILY AUDIT 08:00 GST</div>
      </div>

      <!-- User Explicit Rule 1: Receivables > 180 Days -->
      <div style="background:#1A2533; border: 1px solid #B84A4A; border-radius:8px; padding:12px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div style="display:flex; align-items:center; gap:8px;">
            <span class="badge badge-red">THRESHOLD BREACH: CUSTOMER AR &gt; 180 DAYS</span>
            <strong style="font-size:13px; color:#FFFFFF;">Overdue Exposure: AED 2,400,000.00 (CoCode 1000)</strong>
          </div>
          <span style="font-size:11px; color:#F87171; font-weight:700;">DSO Drag: +8.4 Days</span>
        </div>
        <div style="margin-top:8px; font-size:12px; color:#CBD5E1; line-height:1.4;">
          <strong>Underlying Material Inventory &gt; 180d (GRC1/GRC2):</strong> <code>AED 9,668,903.27</code> across Plant 1AD1 (TREPEL sensor AED 117.8k, TLD cooling fan AED 80.3k, TLD tire AED 47.5k).<br>
          <div style="margin-top:6px; background:#24161C; padding:8px 12px; border-radius:6px; border:1px solid #5C2229; color:#FCA5A5;">
            <strong>🤖 Automated Recommendation:</strong> Freeze pending delivery schedules on Plant 1AD1 for delinquent commercial debtors. Issue formal dunning escalation notice and offer 90-day structured repayment plan with 30% upfront wire (AED 720k) to prevent bad-debt write-off.
          </div>
        </div>
        <div style="display:flex; gap:8px; margin-top:10px;">
          <button class="btn btn-danger">Execute Delivery Hold (CoCode 1000)</button>
          <button class="btn btn-outline">Send Formal Escalation Notice</button>
          <button class="btn btn-outline">Inspect S/4HANA Ledger</button>
        </div>
      </div>

      <!-- User Explicit Rule 2: Payables > 60 Days -->
      <div style="background:#1A2533; border: 1px solid #D68A1E; border-radius:8px; padding:12px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div style="display:flex; align-items:center; gap:8px;">
            <span class="badge badge-amber">KPI OPPORTUNITY: VENDOR PAYABLES &gt; 60 DAYS</span>
            <strong style="font-size:13px; color:#FFFFFF;">Total Pending: AED 8,100,000.00 (CoCode 1000)</strong>
          </div>
          <span style="font-size:11px; color:#FBBF24; font-weight:700;">Discount at Risk: AED 202,500</span>
        </div>
        <div style="margin-top:8px; font-size:12px; color:#CBD5E1; line-height:1.4;">
          <strong>Critical Suppliers at Risk:</strong> Aircraft ground support equipment and maintenance spare parts suppliers in Plant 1AD1 approaching credit stop.<br>
          <div style="margin-top:6px; background:#262016; padding:8px 12px; border-radius:6px; border:1px solid #63431D; color:#FDE68A;">
            <strong>🤖 Automated Recommendation:</strong> Authorize priority payment release batch of AED 8.10M via S/4HANA Fiori payment run to capture 2.5% prompt settlement discount (AED 202,500 immediate net cash savings) and guarantee uninterrupted ground handling operations.
          </div>
        </div>
        <div style="display:flex; gap:8px; margin-top:10px;">
          <button class="btn btn-success">1-Click Release Priority Batch (AED 8.10M)</button>
          <button class="btn btn-outline">Negotiate Payment Extension</button>
          <button class="btn btn-outline">View Supplier Terms</button>
        </div>
      </div>

    </div>
  </div>
</div>
</body></html>"""
open(f"{OUT_DIR}/gap12_proactive_recommendations.html", "w").write(html12)

print("All 12 genuine HTML mockups written successfully!")
