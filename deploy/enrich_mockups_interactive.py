import os
import glob
import re

OUT_DIR = "deploy/limad_ui_mockups"

NAV_ITEMS = [
    ("gap1_source_attribution", "1. Attribution"),
    ("gap2_automated_pre_meeting_briefs", "2. Pre-Meeting"),
    ("gap3_end_of_day_digests", "3. EOD Digest"),
    ("gap4_inbox_triage", "4. Inbox Triage"),
    ("gap5_recommendation_feedback", "5. Feedback"),
    ("gap6_confidence_scoring", "6. Confidence"),
    ("gap7_reasoning_chain_explainability", "7. Reasoning"),
    ("gap8_audit_ready_traceability", "8. Audit Trace"),
    ("gap9_institutional_memory", "9. Memory"),
    ("gap10_in_person_meeting_intelligence", "10. In-Person"),
    ("gap11_peer_benchmarking", "11. Benchmark"),
    ("gap12_proactive_recommendations", "12. Proactive"),
]

INTERACTIVE_CSS = """
  /* Modern UI/UX Polish, Micro-interactions & Accessibility */
  .btn {
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    cursor: pointer;
    user-select: none;
  }
  .btn:hover {
    filter: brightness(1.15);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  }
  .btn:active {
    transform: translateY(0) scale(0.98);
  }
  .btn.active-btn {
    background: #13A6A6 !important;
    color: #FFFFFF !important;
    border-color: #13A6A6 !important;
    box-shadow: 0 0 0 2px rgba(19, 166, 166, 0.4);
  }
  .expandable-panel {
    display: none;
    animation: slideDownFade 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards;
  }
  .expandable-panel.visible {
    display: block;
  }
  @keyframes slideDownFade {
    from { opacity: 0; transform: translateY(-8px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .toast-notification {
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: #112536;
    color: #FFFFFF;
    border: 1px solid #13A6A6;
    border-left: 5px solid #13A6A6;
    padding: 12px 20px;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 600;
    box-shadow: 0 16px 36px rgba(0,0,0,0.5);
    display: flex;
    align-items: center;
    gap: 10px;
    z-index: 9999;
    opacity: 0;
    transform: translateY(20px);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    pointer-events: none;
  }
  .toast-notification.show {
    opacity: 1;
    transform: translateY(0);
    pointer-events: auto;
  }
  .gap-nav {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    background: #09131B;
    border-bottom: 1px solid #1C3042;
    overflow-x: auto;
    white-space: nowrap;
    scrollbar-width: thin;
  }
  .gap-nav-label {
    font-size: 11px;
    font-weight: 800;
    color: #64748B;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-right: 6px;
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .gap-nav a {
    color: #8EA0B0;
    text-decoration: none;
    font-size: 11px;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 4px;
    border: 1px solid transparent;
    transition: all 0.15s ease;
  }
  .gap-nav a:hover {
    color: #FFFFFF;
    background: #162B3D;
    border-color: #23425E;
  }
  .gap-nav a.active {
    color: #13A6A6;
    background: rgba(19, 166, 166, 0.15);
    border-color: #13A6A6;
    font-weight: 700;
  }
"""

INTERACTIVE_JS = """
<script>
function showToast(msg, isSuccess = true) {
  let toast = document.getElementById('exec-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'exec-toast';
    toast.className = 'toast-notification';
    document.body.appendChild(toast);
  }
  toast.innerHTML = (isSuccess ? '✅ ' : 'ℹ️ ') + msg;
  toast.classList.add('show');
  clearTimeout(window.__toastTimeout);
  window.__toastTimeout = setTimeout(() => { toast.classList.remove('show'); }, 3400);
}

function togglePanel(panelId, btn) {
  const panel = document.getElementById(panelId);
  if (!panel) return;
  const isVisible = panel.classList.toggle('visible');
  if (btn) {
    btn.classList.toggle('active-btn', isVisible);
  }
  showToast(isVisible ? 'Panel expanded' : 'Panel collapsed');
}

function submitFeedback(rating, alertId, btn) {
  const container = btn.closest('div');
  if (container) {
    container.querySelectorAll('.feedback-btn').forEach(b => b.classList.remove('active-btn'));
  }
  btn.classList.add('active-btn');
  showToast('Rating recorded: ' + rating + ' for ' + alertId + ' (Saved in feedback_service)');
}

function confirmStageAction(actionTitle, stageDetails) {
  showToast('Stage A Preview generated: ' + actionTitle + ' (' + stageDetails + ')');
}
</script>
"""

def generate_navbar(current_id):
    links = []
    for fid, label in NAV_ITEMS:
        active_class = " class='active'" if fid == current_id else ""
        links.append(f"<a href='{fid}.html'{active_class}>{label}</a>")
    return f"""<div class="gap-nav">
  <span class="gap-nav-label">VELORA CAPABILITIES:</span>
  {' '.join(links)}
</div>"""

def enrich_file(filepath):
    current_id = os.path.basename(filepath).replace(".html", "")
    content = open(filepath, "r", encoding="utf-8").read()

    # Inject CSS
    if ".gap-nav" not in content:
        content = content.replace("</style>", f"{INTERACTIVE_CSS}\n</style>")

    # Inject Navbar after <div class="window">
    nav_html = generate_navbar(current_id)
    if "class=\"gap-nav\"" not in content:
        content = content.replace("<div class=\"window\">", f"<div class=\"window\">\n{nav_html}")

    # Inject JS before </body>
    if "showToast" not in content:
        content = content.replace("</body>", f"{INTERACTIVE_JS}\n</body>")

    # Wire buttons based on file ID
    if current_id == "gap1_source_attribution":
        content = re.sub(
            r'<button class="btn btn-primary"[^>]*>.*?</button>',
            '<button class="btn btn-primary" onclick="togglePanel(\'dept-drilldown\', this)">Drilldown Department Table</button>',
            content
        )
        content = re.sub(
            r'<button class="btn btn-outline"[^>]*>Export Provenance Receipt.*?</button>',
            '<button class="btn btn-outline" onclick="showToast(\'Provenance receipt exported (SHA-256 verified: corr-vel-e2e-001)\')">Export Provenance Receipt (JSON)</button>',
            content
        )
        # Add expandable dept table if not present
        if "id=\"dept-drilldown\"" not in content:
            drilldown_html = """
      <div id="dept-drilldown" class="expandable-panel" style="background:#0B141C; border:1px solid #1E3345; border-radius:8px; padding:12px; margin-top:8px;">
        <span style="font-size:11.5px; font-weight:700; color:#38BDF8;">DEPARTMENT HEADCOUNT & EMIRATISATION DRILLDOWN (TOP 5)</span>
        <table class="table-custom" style="margin-top:6px;">
          <tr><th>Department</th><th>Active Headcount</th><th>UAE Nationals</th><th>Emiratisation %</th><th>Target</th></tr>
          <tr><td>Check-in & Boarding</td><td>1,109</td><td>48</td><td>4.3%</td><td>52.0%</td></tr>
          <tr><td>Cabin Crew Operations</td><td>842</td><td>24</td><td>2.9%</td><td>52.0%</td></tr>
          <tr><td>Aircraft Engineering & MRO</td><td>614</td><td>31</td><td>5.0%</td><td>52.0%</td></tr>
          <tr><td>Flight Operations & Cockpit</td><td>485</td><td>12</td><td>2.5%</td><td>52.0%</td></tr>
          <tr><td>Ground Cargo Logistics</td><td>320</td><td>11</td><td>3.4%</td><td>52.0%</td></tr>
        </table>
      </div>
            """
            content = content.replace("</div>\n      <div style=\"display:flex; gap:10px; align-items:center;\">", f"{drilldown_html}\n      </div>\n      <div style=\"display:flex; gap:10px; align-items:center;\">")

    elif current_id == "gap2_automated_pre_meeting_briefs":
        content = re.sub(
            r'<button class="btn btn-primary"[^>]*>.*?</button>',
            '<button class="btn btn-primary" onclick="showToast(\'Pre-meeting briefing dispatched to executive Outlook mailbox\')">Dispatch Brief to Outlook</button>',
            content
        )
        content = re.sub(
            r'<button class="btn btn-outline"[^>]*>.*?</button>',
            '<button class="btn btn-outline" onclick="togglePanel(\'attendee-dossiers\', this)">Toggle Stakeholder Dossiers</button>',
            content
        )

    elif current_id == "gap3_end_of_day_digests":
        content = re.sub(
            r'<button class="btn btn-primary"[^>]*>.*?</button>',
            '<button class="btn btn-primary" onclick="showToast(\'End-of-day wrap-up summary email dispatched to outbox\')">Dispatch Wrap-up Email</button>',
            content
        )
        content = re.sub(
            r'<button class="btn btn-outline"[^>]*>.*?</button>',
            '<button class="btn btn-outline" onclick="togglePanel(\'tomorrow-agenda\', this)">Review Tomorrow\'s Preparation</button>',
            content
        )

    elif current_id == "gap4_inbox_triage":
        content = re.sub(
            r'<button class="btn btn-primary"[^>]*>.*?</button>',
            '<button class="btn btn-primary" onclick="showToast(\'High-priority triage queue approved: 3 items scheduled for action\')">Execute Top Priorities (3)</button>',
            content
        )
        content = re.sub(
            r'<button class="btn btn-outline"[^>]*>.*?</button>',
            '<button class="btn btn-outline" onclick="showToast(\'Triage queue acknowledged and archived\')">Archive Triage Feed</button>',
            content
        )

    elif current_id == "gap5_recommendation_feedback":
        content = re.sub(
            r'<button class="btn btn-success"[^>]*>.*?</button>',
            '<button class="btn btn-success feedback-btn" onclick="submitFeedback(\'Helpful\', \'REC-AR-8821\', this)">👍 Helpful</button>',
            content
        )
        content = re.sub(
            r'<button class="btn btn-danger"[^>]*>.*?</button>',
            '<button class="btn btn-danger feedback-btn" onclick="submitFeedback(\'Not Helpful\', \'REC-AR-8821\', this)">👎 Not Helpful</button>',
            content
        )
        content = re.sub(
            r'<button class="btn btn-outline"[^>]*>.*?</button>',
            '<button class="btn btn-outline" onclick="togglePanel(\'comment-panel\', this)">Add Executive Comment</button>',
            content
        )
        if "id=\"comment-panel\"" not in content:
            comment_html = """
      <div id="comment-panel" class="expandable-panel" style="background:#0B141C; border:1px solid #1E3345; border-radius:8px; padding:12px; margin-top:8px;">
        <span style="font-size:11.5px; font-weight:700; color:#38BDF8;">EXECUTIVE REASONING FEEDBACK (Saved to feedback_service)</span>
        <textarea style="width:100%; height:60px; background:#142433; border:1px solid #23394D; border-radius:6px; color:#FFFFFF; padding:8px; font-size:12px; margin-top:6px;" placeholder="Add contextual guidance for recommendation model tuning..."></textarea>
        <button class="btn btn-primary" style="margin-top:6px;" onclick="showToast('Executive contextual comment saved to Dataverse')">Submit Comment</button>
      </div>
            """
            content = content.replace("</div>\n      <div style=\"display:flex; gap:10px; align-items:center;\">", f"{comment_html}\n      </div>\n      <div style=\"display:flex; gap:10px; align-items:center;\">")

    elif current_id == "gap6_confidence_scoring":
        content = re.sub(
            r'<button class="btn btn-primary"[^>]*>.*?</button>',
            '<button class="btn btn-primary" onclick="togglePanel(\'confidence-factors\', this)">Inspect Confidence Factors</button>',
            content
        )
        content = re.sub(
            r'<button class="btn btn-outline"[^>]*>.*?</button>',
            '<button class="btn btn-outline" onclick="showToast(\'Live CDS re-read complete: 94% High Confidence confirmed\')">Re-verify Source Freshness</button>',
            content
        )

    elif current_id == "gap7_reasoning_chain_explainability":
        content = re.sub(
            r'<button class="btn btn-primary"[^>]*>.*?</button>',
            '<button class="btn btn-primary" onclick="confirmStageAction(\'Debtor Credit Freeze\', \'Stage A preview generated; 0 tasks committed\')">Proceed with Escalation</button>',
            content
        )
        content = re.sub(
            r'<button class="btn btn-outline"[^>]*>.*?</button>',
            '<button class="btn btn-outline" onclick="togglePanel(\'ledger-drilldown\', this)">Review S/4HANA Ledger Lines</button>',
            content
        )
        if "id=\"ledger-drilldown\"" not in content:
            ledger_html = """
      <div id="ledger-drilldown" class="expandable-panel" style="background:#0B141C; border:1px solid #1E3345; border-radius:8px; padding:12px; margin-top:8px;">
        <span style="font-size:11.5px; font-weight:700; color:#38BDF8;">S/4HANA BSID LIVE OPEN LINE ITEMS (Plant 1AD1)</span>
        <table class="table-custom" style="margin-top:6px;">
          <tr><th>Doc #</th><th>Customer Account</th><th>Net Due Date</th><th>Overdue Days</th><th>Outstanding (AED)</th></tr>
          <tr><td>1800004921</td><td>Gulf Aviation Charter Services</td><td>2026-03-01</td><td>192 days</td><td>AED 1,420,000.00</td></tr>
          <tr><td>1800005118</td><td>Al Futtaim Logistics Cargo</td><td>2026-03-12</td><td>181 days</td><td>AED 980,000.00</td></tr>
        </table>
      </div>
            """
            content = content.replace("</div>\n      <div style=\"display:flex; gap:10px; align-items:center;\">", f"{ledger_html}\n      </div>\n      <div style=\"display:flex; gap:10px; align-items:center;\">")

    elif current_id == "gap8_audit_ready_traceability":
        content = re.sub(
            r'<button class="btn btn-primary"[^>]*>Export ADAA Audit Bundle.*?</button>',
            '<button class="btn btn-primary" onclick="showToast(\'ADAA Audit Bundle exported as CSV with formula injection defense [CWE-1236]\')">Export ADAA Audit Bundle (CSV)</button>',
            content
        )
        content = re.sub(
            r'<button class="btn btn-outline"[^>]*>Export Cryptographic Trace.*?</button>',
            '<button class="btn btn-outline" onclick="showToast(\'Cryptographic manifest verified: Merkle Root signed with KMS key custody\')">Export Cryptographic Trace (JSON)</button>',
            content
        )

    elif current_id == "gap9_institutional_memory":
        content = re.sub(
            r'<button class="btn btn-primary"[^>]*>.*?</button>',
            '<button class="btn btn-primary" onclick="togglePanel(\'minutes-view\', this)">Open Historical Minutes</button>',
            content
        )
        content = re.sub(
            r'<button class="btn btn-outline"[^>]*>.*?</button>',
            '<button class="btn btn-outline" onclick="showToast(\'Retention compliance verified: UAE PDPL Decree Law No. 45/2021 active\')">Verify Retention SLA</button>',
            content
        )

    elif current_id == "gap10_in_person_meeting_intelligence":
        content = re.sub(
            r'<button class="btn btn-primary"[^>]*>.*?</button>',
            '<button class="btn btn-primary" onclick="confirmStageAction(\'Create Approved Actions\', \'Stage A preview generated: 2 tasks mapped; Stage B confirmation required\')">Create Tasks in Planner</button>',
            content
        )
        content = re.sub(
            r'<button class="btn btn-outline"[^>]*>.*?</button>',
            '<button class="btn btn-outline" onclick="showToast(\'Dispatching nudges: Suppressed for already-completed tasks\')">Dispatch Follow-up Nudges</button>',
            content
        )

    elif current_id == "gap11_peer_benchmarking":
        content = re.sub(
            r'<button class="btn btn-primary"[^>]*>.*?</button>',
            '<button class="btn btn-primary" onclick="togglePanel(\'methodology-view\', this)">Toggle Methodology & Sources</button>',
            content
        )
        content = re.sub(
            r'<button class="btn btn-outline"[^>]*>.*?</button>',
            '<button class="btn btn-outline" onclick="showToast(\'Licensed IATA/SEC peer dataset exported (Normalized to AED: 3.6725 USD/AED)\')">Download Comparative Dataset</button>',
            content
        )

    elif current_id == "gap12_proactive_recommendations":
        content = re.sub(
            r'<button class="btn btn-danger"[^>]*>.*?</button>',
            '<button class="btn btn-danger" onclick="confirmStageAction(\'Delivery Hold on Delinquent Debtors\', \'Stage A preview: requires CFO confirmation\')">Execute Delivery Hold (CoCode 1000)</button>',
            content
        )
        content = re.sub(
            r'<button class="btn btn-success"[^>]*>.*?</button>',
            '<button class="btn btn-success" onclick="confirmStageAction(\'1-Click Priority Release\', \'AED 8.10M payment batch: 2.5% prompt discount locked [AED 202,500 savings]\')">1-Click Release Priority Batch (AED 8.10M)</button>',
            content
        )

    open(filepath, "w", encoding="utf-8").write(content)
    print(f"✓ Enriched: {filepath}")

for f in sorted(glob.glob(f"{OUT_DIR}/*.html")):
    enrich_file(f)

print("All 12 mockups enriched with interactive UI/UX features!")
