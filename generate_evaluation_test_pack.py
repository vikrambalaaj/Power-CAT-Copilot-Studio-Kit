"""Generate Copilot Studio Evaluation Test Set with exact distribution:
- SAP SuccessFactors (SF): 50%
- Microsoft 365 / Productivity: 30%
- SAP S/4HANA Finance MCP: 10%
- Memory & Performance / Audit: 10%
"""
import csv
import json
from pathlib import Path

test_cases = [
    # =========================================================================
    # 1. SAP SUCCESSFACTORS (SF) - 50% (25 Test Cases)
    # =========================================================================
    {
        "ID": "SF-001",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "What is the total active employee headcount at Velora?",
        "Expected response": "Total active workforce count categorized by company code, division, and permanent vs. contractor status with source transparency from SAP SuccessFactors.",
        "Target Tool": "sf__get_headcount",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-002",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "Show me the current Emiratisation KPI percentage across departments.",
        "Expected response": "Emiratisation percentage, total UAE national employees versus total workforce, department-level breakdown, and quota compliance status.",
        "Target Tool": "sf__get_emiratisation_kpi",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-003",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "How many new joiners were onboarded this month?",
        "Expected response": "New joiner count for the current month, grouped by business unit and hiring date from SuccessFactors EmpEmployment.",
        "Target Tool": "sf__get_joiners",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-004",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "Show me the list of leavers and offboardings last quarter.",
        "Expected response": "Quarterly leavers summary, termination event reasons, and department breakdown.",
        "Target Tool": "sf__get_leavers",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-005",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "What is our annualized voluntary attrition rate?",
        "Expected response": "Annualized voluntary vs. involuntary attrition rate percentages and annualized talent turnover metrics.",
        "Target Tool": "sf__get_attrition",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-006",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "What is the net hiring trend over the last 6 months?",
        "Expected response": "Net headcount movement chart/table comparing joiners vs. leavers over a 6-month historical period.",
        "Target Tool": "sf__get_joiners_leavers_trend",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-007",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "Give me an executive analytics dashboard of our workforce.",
        "Expected response": "Consolidated workforce dashboard covering total headcount, gender diversity, span of control, and key HR health indicators.",
        "Target Tool": "sf__get_analytics_dashboard",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-008",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "Drill down into headcount by Engineering division and job grade.",
        "Expected response": "Engineering division staffing breakdown classified by seniority grade, location, and position title.",
        "Target Tool": "sf__get_workforce_drilldown",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-009",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "Who is the direct manager and position details for employee 10482?",
        "Expected response": "Job profile, title, department, cost center, and direct manager hierarchy from EmpJob.",
        "Target Tool": "sf__get_emp_job_detail",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-010",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "Which department hired the highest number of people last quarter?",
        "Expected response": "Top hiring department identified with specific headcount additions and percentage of total hires.",
        "Target Tool": "sf__get_joiners",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-011",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "Compare workforce joiners between this month and last month.",
        "Expected response": "Month-over-month joiner variance analysis with absolute numbers and percentage growth.",
        "Target Tool": "sf__get_joiners_leavers_trend",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-012",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "Show me the legal entities and org units defined in SuccessFactors.",
        "Expected response": "Catalog of FOCompany and FOBusinessUnit organizational entities active in SuccessFactors.",
        "Target Tool": "sf__get_org_units",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-013",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "What is the average span of control for managers in Operations?",
        "Expected response": "Span of control ratio (direct reports per manager) across Operations departments.",
        "Target Tool": "sf__get_analytics_dashboard",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-014",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "Provide a workforce breakdown by UAE location and facility.",
        "Expected response": "Headcount distribution across Abu Dhabi, Dubai, and regional operating bases.",
        "Target Tool": "sf__get_workforce_drilldown",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-015",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "Display the verified workforce metric card for Executive Committee review.",
        "Expected response": "Adaptive Card presentation with verified fact set, timestamp, and SAP SuccessFactors verification badge.",
        "Target Tool": "sf__get_analytics_dashboard",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-016",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "How many contractors vs full-time employees are currently active?",
        "Expected response": "Contingent worker vs. regular permanent headcount comparison with percentage split.",
        "Target Tool": "sf__get_headcount",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-017",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "What are the primary exit reasons cited in Q2 offboarding records?",
        "Expected response": "Categorized termination reasons from SuccessFactors offboarding records.",
        "Target Tool": "sf__get_leavers",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-018",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "Show gender diversity ratio across leadership grades.",
        "Expected response": "Gender representation metrics across executive and senior management job grades.",
        "Target Tool": "sf__get_analytics_dashboard",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-019",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "List open employee requisitions and pending start dates for Aviation Maintenance.",
        "Expected response": "Pending joiners and onboarding pipeline for Aviation Maintenance division.",
        "Target Tool": "sf__get_joiners",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-020",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "What is the historical headcount growth rate year-over-year?",
        "Expected response": "YoY workforce expansion rate with baseline and current period comparison.",
        "Target Tool": "sf__get_analytics_dashboard",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-021",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "Retrieve position classification and standard hours for Job Code AV-ENG-04.",
        "Expected response": "Standard weekly hours, pay grade band, and classification details from EmpJob.",
        "Target Tool": "sf__get_emp_jobs",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-022",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "Summarize workforce KPIs for company code 1000 in SAP SuccessFactors.",
        "Expected response": "Aggregated summary for entity 1000 covering headcount, joiners, attrition, and Emiratisation.",
        "Target Tool": "sf__get_analytics_dashboard",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-023",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "Check if national recruitment targets for Q3 have been reached.",
        "Expected response": "Q3 Emiratisation target benchmark compared against actual national hires.",
        "Target Tool": "sf__get_emiratisation_kpi",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-024",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "How many employees joined the Flight Operations team in the last 30 days?",
        "Expected response": "Filtered joiner count for Flight Operations with start dates and role names.",
        "Target Tool": "sf__get_joiners",
        "Weight": "2.0%"
    },
    {
        "ID": "SF-025",
        "Category": "SAP SuccessFactors (50%)",
        "User utterance": "Provide a high-level HCM summary table suitable for executive board pack.",
        "Expected response": "Formatted executive table with Total Headcount, National Ratio, Quarterly Growth, and Attrition.",
        "Target Tool": "sf__get_analytics_dashboard",
        "Weight": "2.0%"
    },

    # =========================================================================
    # 2. MICROSOFT 365 / PRODUCTIVITY AGENT - 30% (15 Test Cases)
    # =========================================================================
    {
        "ID": "PROD-001",
        "Category": "M365 Productivity (30%)",
        "User utterance": "Plan my day",
        "Expected response": "Complete 8-part Daily Morning Brief: 1. Executive snapshot (<30s), 2. Today's schedule with meeting prep, 3. Priority inbox (Respond today, Action required, Waiting for me), 4. Teams updates, 5. Tasks/commitments, 6. Watchlist, 7. Recommended plan, 8. Quick-action checklist.",
        "Target Tool": "Velora Productivity Agent (Daily Morning Brief)",
        "Weight": "2.0%"
    },
    {
        "ID": "PROD-002",
        "Category": "M365 Productivity (30%)",
        "User utterance": "Generate my daily morning brief",
        "Expected response": "Chronological schedule, conflicting/back-to-back meetings, priority email drafts, Teams mentions, and top 7 verb-led actions.",
        "Target Tool": "Velora Productivity Agent (Daily Morning Brief)",
        "Weight": "2.0%"
    },
    {
        "ID": "PROD-003",
        "Category": "M365 Productivity (30%)",
        "User utterance": "Share today's work and schedule",
        "Expected response": "Consolidated overview of today's calendar meetings, focus time availability, and key deliverables.",
        "Target Tool": "Velora Productivity Agent (Calendar & Schedule)",
        "Weight": "2.0%"
    },
    {
        "ID": "PROD-004",
        "Category": "M365 Productivity (30%)",
        "User utterance": "What are the urgent unread emails in my Outlook inbox today?",
        "Expected response": "High-priority emails requiring response or action with sender name, subject, deadline, and draft replies.",
        "Target Tool": "Velora Productivity Agent (Priority Inbox)",
        "Weight": "2.0%"
    },
    {
        "ID": "PROD-005",
        "Category": "M365 Productivity (30%)",
        "User utterance": "Summarize my meetings today and what I need to prepare for each.",
        "Expected response": "Meeting-by-meeting breakdown with organizer, agenda, relevant recent emails/docs, and 1-2 suggested questions.",
        "Target Tool": "Velora Productivity Agent (Meeting Prep)",
        "Weight": "2.0%"
    },
    {
        "ID": "PROD-006",
        "Category": "M365 Productivity (30%)",
        "User utterance": "Do I have any overlapping or back-to-back meetings today?",
        "Expected response": "Identified calendar conflicts, back-to-back meetings without buffer time, and recommendations for review.",
        "Target Tool": "Velora Productivity Agent (Calendar Availability)",
        "Weight": "2.0%"
    },
    {
        "ID": "PROD-007",
        "Category": "M365 Productivity (30%)",
        "User utterance": "Show my pending tasks in Microsoft Planner and To Do due this week.",
        "Expected response": "Consolidated task list classified into Overdue, Due Today, and Due in Next 3 Days with deep links.",
        "Target Tool": "Velora Productivity Agent (Planner & To Do)",
        "Weight": "2.0%"
    },
    {
        "ID": "PROD-008",
        "Category": "M365 Productivity (30%)",
        "User utterance": "Summarize important Teams chat mentions from leadership since yesterday.",
        "Expected response": "Direct mentions, executive requests, blockers, and commitments extracted from Microsoft Teams channels.",
        "Target Tool": "Velora Productivity Agent (Teams Mentions)",
        "Weight": "2.0%"
    },
    {
        "ID": "PROD-009",
        "Category": "M365 Productivity (30%)",
        "User utterance": "Draft a reply to Ahmed regarding the Q3 budget review meeting.",
        "Expected response": "Prepares email draft with confirmation token and explicitly prompts for executive approval before sending (Two-step transaction).",
        "Target Tool": "Velora Productivity Agent (Prepare Email Write)",
        "Weight": "2.0%"
    },
    {
        "ID": "PROD-0010",
        "Category": "M365 Productivity (30%)",
        "User utterance": "Search Work IQ for recent policy documents on executive travel.",
        "Expected response": "Search results and excerpts from SharePoint/OneDrive documents accessible under caller permissions.",
        "Target Tool": "Work IQ Enterprise Search",
        "Weight": "2.0%"
    },
    {
        "ID": "PROD-011",
        "Category": "M365 Productivity (30%)",
        "User utterance": "Schedule a 30-minute sync with Sarah tomorrow afternoon.",
        "Expected response": "Checks both participants' calendar availability, prepares meeting invite preview, and requests confirmation token.",
        "Target Tool": "Velora Productivity Agent (Prepare Calendar Write)",
        "Weight": "2.0%"
    },
    {
        "ID": "PROD-012",
        "Category": "M365 Productivity (30%)",
        "User utterance": "What items are waiting for my approval or decision to unblock others?",
        "Expected response": "List of emails, PRs, and chats where progress is blocked pending executive sign-off.",
        "Target Tool": "Velora Productivity Agent (Waiting for Me)",
        "Weight": "2.0%"
    },
    {
        "ID": "PROD-013",
        "Category": "M365 Productivity (30%)",
        "User utterance": "Create a quick-action checklist for the rest of today.",
        "Expected response": "Prioritized checklist of max 7 verb-led actions with estimated time durations.",
        "Target Tool": "Velora Productivity Agent (Quick-Action Checklist)",
        "Weight": "2.0%"
    },
    {
        "ID": "PROD-014",
        "Category": "M365 Productivity (30%)",
        "User utterance": "Find the slide deck shared in the Executive Committee Teams channel last week.",
        "Expected response": "Direct link and summary of the presentation file shared in Teams.",
        "Target Tool": "Work IQ / Teams Files",
        "Weight": "2.0%"
    },
    {
        "ID": "PROD-015",
        "Category": "M365 Productivity (30%)",
        "User utterance": "Review my available focus time for deep work this Thursday.",
        "Expected response": "Focus blocks identified between scheduled calendar events.",
        "Target Tool": "Velora Productivity Agent (Focus Time)",
        "Weight": "2.0%"
    },

    # =========================================================================
    # 3. SAP S/4HANA FINANCE MCP - 10% (5 Test Cases)
    # =========================================================================
    {
        "ID": "S4-001",
        "Category": "SAP S/4HANA Finance (10%)",
        "User utterance": "What is the accounts payable aging from SAP S/4HANA for company code 1000?",
        "Expected response": "Executive summary with total open records, sampled open balance in AED, aging buckets (0-30, 31-90, 91-180, Over 180 days), and top suppliers by balance.",
        "Target Tool": "s4__get_payables_aging",
        "Weight": "2.0%"
    },
    {
        "ID": "S4-002",
        "Category": "SAP S/4HANA Finance (10%)",
        "User utterance": "Show me the top overdue suppliers in SAP S/4HANA.",
        "Expected response": "Top suppliers list ranked by overdue balance (e.g. Daman Insurance, Goldhofer, Etihad Airways) with amounts in AED.",
        "Target Tool": "s4__get_payables_aging",
        "Weight": "2.0%"
    },
    {
        "ID": "S4-003",
        "Category": "SAP S/4HANA Finance (10%)",
        "User utterance": "What is the total accounts receivable balance and customer aging?",
        "Expected response": "Receivables aging buckets, total open customer exposure, and top accounts with outstanding invoices in AED.",
        "Target Tool": "s4__get_receivables_aging",
        "Weight": "2.0%"
    },
    {
        "ID": "S4-004",
        "Category": "SAP S/4HANA Finance (10%)",
        "User utterance": "How much payable balance is overdue beyond 90 days in Company 1000?",
        "Expected response": "Sum of balances in 91-180 days and Over 180 days aging buckets with verified SAP S/4HANA source citation.",
        "Target Tool": "s4__get_payables_aging",
        "Weight": "2.0%"
    },
    {
        "ID": "S4-005",
        "Category": "SAP S/4HANA Finance (10%)",
        "User utterance": "Retrieve invoice aging metrics and verify the live connection to SAP S/4HANA.",
        "Expected response": "Real-time OData query response with ERP timestamp, company code 1000, and verified financial aging fact set.",
        "Target Tool": "s4__get_payables_aging",
        "Weight": "2.0%"
    },

    # =========================================================================
    # 4. MEMORY, PERFORMANCE & AUDIT GOVERNANCE - 10% (5 Test Cases)
    # =========================================================================
    {
        "ID": "MEM-001",
        "Category": "Memory & Performance (10%)",
        "User utterance": "What headcount numbers and finance metrics did we review earlier in this session?",
        "Expected response": "Recalls previous session figures from user-partitioned MemoryService without re-executing unnecessary full backend calls.",
        "Target Tool": "MemoryService (30-Day Context Recall)",
        "Weight": "2.0%"
    },
    {
        "ID": "MEM-002",
        "Category": "Memory & Performance (10%)",
        "User utterance": "Can User B access my morning briefing drafts or private mailbox memory?",
        "Expected response": "Zero cross-user access; strictly enforces Entra ID user partition and logs ACCESS_DENIED audit record in Dataverse.",
        "Target Tool": "Security Partition & Audit Engine",
        "Weight": "2.0%"
    },
    {
        "ID": "MEM-003",
        "Category": "Memory & Performance (10%)",
        "User utterance": "Verify that all delegated operations are recorded in the Dataverse audit log.",
        "Expected response": "Confirms audit record creation in cre2f_veloraagentauditlog with correlation ID, executing agent, and transaction status.",
        "Target Tool": "Dataverse Audit Logger",
        "Weight": "2.0%"
    },
    {
        "ID": "MEM-004",
        "Category": "Memory & Performance (10%)",
        "User utterance": "Test response latency on executive analytics aggregation.",
        "Expected response": "Returns complete aggregated metric response within performance SLA (<3.0s) utilizing local memory cache and connection pooling.",
        "Target Tool": "Memory Cache & Connection Manager",
        "Weight": "2.0%"
    },
    {
        "ID": "MEM-005",
        "Category": "Memory & Performance (10%)",
        "User utterance": "Attempt an unauthorized external write without confirmation token.",
        "Expected response": "Enforces fail-closed transaction policy, rejects direct unconfirmed write, and requires two-step approval token.",
        "Target Tool": "Fail-Closed Governance Engine",
        "Weight": "2.0%"
    }
]

out_csv = Path("/Users/vikrambala/copilotstudio/velora_evaluation_test_set.csv")
with open(out_csv, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["ID", "Category", "User utterance", "Expected response", "Target Tool", "Weight"])
    writer.writeheader()
    writer.writerows(test_cases)

print(f"Generated evaluation test pack: {out_csv} ({len(test_cases)} test cases)")
