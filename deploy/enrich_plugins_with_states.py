"""Enrich all Copilot plugin definitions with real-time processing states (live animated status updates in Teams/Copilot)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_PKG = ROOT / "mcp-apps" / "ask-successfactors" / "agent" / "appPackage"

STATE_DESCRIPTIONS = {
    # SuccessFactors HCM
    "sf__get_headcount": {
        "reasoning": "Analyzing workforce headcount query and department filters...",
        "executing": "[SAP SuccessFactors MCP] Connecting to HCM & calculating live department headcount...",
        "responding": "Synthesizing workforce analytics and rendering Executive Headcount Card..."
    },
    "sf__get_emiratisation_kpi": {
        "reasoning": "Identifying nationalization metrics and compliance targets...",
        "executing": "[SAP SuccessFactors MCP] Connecting to HCM & evaluating UAE Emiratisation ratios...",
        "responding": "Synthesizing Emiratisation KPI and rendering compliance card..."
    },
    "sf__get_workforce_drilldown": {
        "reasoning": "Verifying user authorization and Dataverse disclosure policy...",
        "executing": "[SAP SuccessFactors MCP + Dataverse] Filtering employee roster with strict PII & banking privacy masking...",
        "responding": "Rendering governed employee roster drilldown..."
    },
    "sf__get_attrition": {
        "reasoning": "Evaluating workforce departure parameters and calculation window...",
        "executing": "[SAP SuccessFactors MCP] Calculating annualized attrition and turnover rates...",
        "responding": "Synthesizing attrition intelligence and trend data..."
    },
    "sf__get_joiners": {
        "reasoning": "Identifying reporting period and new-hire filters...",
        "executing": "[SAP SuccessFactors MCP] Querying onboarding and new-hire records...",
        "responding": "Formatting verified joiners summary..."
    },
    "sf__get_leavers": {
        "reasoning": "Resolving exit reason classifications and departure periods...",
        "executing": "[SAP SuccessFactors MCP] Retrieving voluntary and involuntary exit records...",
        "responding": "Formatting verified leavers analytics..."
    },
    "sf__get_joiners_leavers_trend": {
        "reasoning": "Compiling multi-period workforce movement timeline...",
        "executing": "[SAP SuccessFactors MCP] Calculating net headcount growth and turnover trends...",
        "responding": "Rendering workforce movement trend visualization..."
    },
    "sf__get_analytics_dashboard": {
        "reasoning": "Aggregating multi-KPI workforce health indicators...",
        "executing": "[SAP SuccessFactors MCP] Querying executive headcount, Emiratisation, and retention...",
        "responding": "Rendering Executive Workforce Health Dashboard..."
    },
    "sf__get_session_greeting": {
        "reasoning": "Validating user session and confidentiality consent...",
        "executing": "[Dataverse MCP] Checking governance audit & consent records...",
        "responding": "Delivering personalized executive greeting..."
    },
    "sf__check_and_record_consent": {
        "reasoning": "Evaluating confidentiality notice version compliance...",
        "executing": "[Dataverse MCP] Persisting consent audit log in Microsoft Dataverse...",
        "responding": "Confirming data access authorization..."
    },
    "sf__recall_user_memory": {
        "reasoning": "Retrieving 30-day institutional memory snapshot...",
        "executing": "[Dataverse MCP] Loading contextual session history from Microsoft Dataverse...",
        "responding": "Applying historical context to conversation..."
    },
    "sf__get_emp_jobs": {
        "reasoning": "Resolving employee position and job classification filters...",
        "executing": "[SAP SuccessFactors MCP] Querying EmpJob position records...",
        "responding": "Formatting job assignment details..."
    },
    "sf__get_emp_job_detail": {
        "reasoning": "Retrieving detailed position attributes and organizational unit...",
        "executing": "[SAP SuccessFactors MCP] Querying single-record EmpJob entity...",
        "responding": "Formatting verified job detail record..."
    },
    "sf__get_users": {
        "reasoning": "Querying user profile directory in SAP SuccessFactors...",
        "executing": "[SAP SuccessFactors MCP] Retrieving active user profile metadata...",
        "responding": "Formatting user profile results..."
    },
    "sf__get_user_detail": {
        "reasoning": "Resolving specific user profile attributes...",
        "executing": "[SAP SuccessFactors MCP] Querying User entity in SAP SuccessFactors...",
        "responding": "Formatting verified user profile..."
    },
    "sf__get_employment_info": {
        "reasoning": "Checking employment dates, service length, and status...",
        "executing": "[SAP SuccessFactors MCP] Querying EmpEmployment in SAP SuccessFactors...",
        "responding": "Formatting employment service record..."
    },
    "sf__get_org_units": {
        "reasoning": "Mapping corporate organizational hierarchy...",
        "executing": "[SAP SuccessFactors MCP] Querying FODepartment and FOCompany organizational entities...",
        "responding": "Formatting organizational structure view..."
    },

    # S/4HANA Finance
    "s4__get_receivables_aging": {
        "reasoning": "Analyzing receivables aging parameters, key date, and currency...",
        "executing": "[SAP S/4HANA Finance MCP] Querying general ledger to calculate overdue aging buckets...",
        "responding": "Synthesizing aging exposures and rendering Accounts Receivable Card..."
    },
    "s4__get_payables_aging": {
        "reasoning": "Analyzing accounts payable parameters and vendor liability filters...",
        "executing": "[SAP S/4HANA Finance MCP] Querying Accounts Payable general ledger...",
        "responding": "Synthesizing supplier liabilities and rendering Accounts Payable Card..."
    },
    "s4__get_profit_and_loss": {
        "reasoning": "Resolving fiscal year, accounting period, and general ledger...",
        "executing": "[SAP S/4HANA Finance MCP] Querying General Ledger for revenues, COGS, and operating profit...",
        "responding": "Synthesizing P&L statement and rendering Financial Summary Card..."
    },
    "s4__get_budget_variance": {
        "reasoning": "Comparing budget plan version against actual ledger postings...",
        "executing": "[SAP S/4HANA Finance MCP] Calculating budget utilization and variance percentages...",
        "responding": "Rendering Budget vs. Actual Variance Analysis Card..."
    },

    # SAP Analytics Cloud (SAC)
    "get_sac_kpis": {
        "reasoning": "Identifying strategic domain performance indicators...",
        "executing": "[SAP Analytics Cloud MCP] Retrieving corporate EBITDA and operating margins...",
        "responding": "Synthesizing corporate metrics and rendering Executive Performance Card..."
    },
    "get_sac_story_analytics": {
        "reasoning": "Loading SAC Story BI dimensions and variance drivers...",
        "executing": "[SAP Analytics Cloud MCP] Retrieving verified SAC Story analytics and commentary...",
        "responding": "Rendering Strategic Story Analytics Card..."
    },
    "get_sac_model_data": {
        "reasoning": "Resolving SAC analytical model ID and requested measures...",
        "executing": "[SAP Analytics Cloud MCP] Querying raw measure datasets from model...",
        "responding": "Formatting analytical model data table..."
    },

    # Productivity Agent
    "productivity__get_executive_briefing": {
        "reasoning": "Scanning today's executive schedule and communications...",
        "executing": "[Productivity MCP] Querying Outlook Calendar, priority emails, Teams mentions & Planner...",
        "responding": "Synthesizing Executive Daily Briefing and action items..."
    },
    "productivity__prepare_email": {
        "reasoning": "Drafting governed executive email and resolving recipients...",
        "executing": "[Productivity MCP] Generating two-step transaction preview and cryptographic approval token...",
        "responding": "Rendering Governance Confirmation Card with Send button..."
    },
    "productivity__send_approved_email": {
        "reasoning": "Validating cryptographic confirmation token and executive approval...",
        "executing": "[Productivity MCP] Dispatching email via Microsoft Graph & writing Dataverse audit trail...",
        "responding": "Delivering confirmed delivery receipt with Message ID..."
    },

    # Facilitator
    "get_calendar_meetings": {
        "reasoning": "Scanning Outlook and Teams calendars for upcoming executive meetings...",
        "executing": "[Velora Facilitator MCP] Connecting to Microsoft Graph to retrieve scheduled meetings...",
        "responding": "Formatting scheduled meeting roster..."
    },
    "process_calendar_meeting_workflow": {
        "reasoning": "Analyzing meeting agenda, attendees, and historical context...",
        "executing": "[Velora Facilitator MCP] Synthesizing cross-system SAP intelligence and institutional notes...",
        "responding": "Delivering Executive Meeting Briefing packet..."
    },
    "generate_pre_meeting_briefing": {
        "reasoning": "Compiling executive briefing for scheduled attendees...",
        "executing": "[Velora Facilitator MCP] Querying SAP workforce, S/4HANA financials, and Dataverse history...",
        "responding": "Rendering Pre-Meeting Executive Briefing..."
    }
}


def enrich_plugin(plugin_path: Path):
    if not plugin_path.exists():
        return
    data = json.loads(plugin_path.read_text(encoding="utf-8"))
    functions = data.get("functions", [])
    for fn in functions:
        name = fn.get("name")
        states = STATE_DESCRIPTIONS.get(name, {
            "reasoning": f"Analyzing parameters for {name}...",
            "executing": f"Executing {name} across authorized enterprise systems...",
            "responding": f"Formatting response for {name}..."
        })
        fn["states"] = {
            "reasoning": {"description": states["reasoning"]},
            "executing": {"description": states["executing"]},
            "responding": {"description": states["responding"]}
        }
    plugin_path.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")
    print(f"Enriched {plugin_path.name} with live animated states for {len(functions)} functions.")


if __name__ == "__main__":
    for plugin_file in APP_PKG.glob("*-plugin.json"):
        enrich_plugin(plugin_file)
    # Also check ask-productivity appPackage
    prod_pkg = ROOT / "mcp-apps" / "ask-productivity" / "agent" / "appPackage"
    for plugin_file in prod_pkg.glob("*-plugin.json"):
        enrich_plugin(plugin_file)
