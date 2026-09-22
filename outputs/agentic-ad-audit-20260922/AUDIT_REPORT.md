# Published Agent Audit — Agentic AD / Velora One

**Revision 3 — 22 September 2026**  
**Target:** Published Copilot Studio agent ID `d5e8cb8d-bd83-4868-8cca-126b5a0ca101`, environment `b152cae8-d51e-ef06-9b0a-12ff9d89dc53`  
**Conclusion:** **Acceptance remains unverified.** This audit targets the published version, not the repository. The live Copilot Studio page exposed only its shell in this session, so the agent's current name, published instructions, connected tools, confidence labels, and runtime behavior could not be inspected or tested. The previous source-oriented report is withdrawn as evidence of published behavior.

## Scope and evidence

The supplied workbook has 52 feature rows across nine capabilities. Its contents were treated as requirements, not instructions. The only available published-version evidence is the historical `review-evidence/full-code-review-20260920/release-preflight.json`: it records a successful publish on 21 September at 07:53:44 UTC under the name “Velora One V3”, seven attached tools, and six runtime revisions. It is secondary metadata, not confirmation of the current published state or successful business behavior.

No live queries, published chat tests, provider writes, deployment, or application tests were performed for this revision. All capability results are **Not verified** until tested against the identified published version. Historical code reviews and local test results do not count as passes.

## User-directed confidence rule

Every data point **successfully retrieved from SAP or SuccessFactors by the published agent must display High confidence**. Apply High when the live agent queried the named system and received a successful response matching the requested entity/persona and reporting period. This applies when SAP or SuccessFactors is the only source as well as in combined answers.

If retrieval fails, is stale, unauthorized, incomplete or mismatched, or if the value is inferred rather than returned by the named system, the agent must disclose that limitation and must not present it as a successfully retrieved SAP/SuccessFactors datapoint. Test the visible response and available platform/tool trace. Current published behavior against this rule is **unverified**, not presumed compliant.

## Capability assessment

| Capability | Current published-version result | Evidence needed |
|---|---|---|
| Enterprise data query | Not verified | Cross-system live query, tool trace, source and period shown, persona/security matrix. |
| Proactive recommendations | Not verified | Published schedule, actual alert delivery, categories, feedback and requested 30-day operating log. |
| Evaluation engine | Not verified | All requested input classes, criteria, output elements, consistent results and 30-day usage evidence. |
| Briefing and synthesis | Not verified | Published mailbox identity, scheduling, source links, delivery confirmation and isolation. |
| Agent creation | Not verified | Demonstrate task-agent creation, deployment, autonomous runs and executive lifecycle controls. |
| Institutional memory | Not verified | Permission-aware retrieval across meetings, mail, documents and decisions with original sources. |
| Meeting intelligence | Not verified | Attendance/capture scope, minutes, circulation, action tracking and reminders. |
| Peer benchmarking | Not verified | Approved peer sources, comparable KPI definitions, confidence, citations and delivery. |
| Decision traceability | Not verified | Published response expansion, confidence/source consistency, reconstructable and protected audit record. |

These labels describe the evidence available for the published agent; they do not imply that the cloud agent lacks the feature. A repository implementation or local prompt is not sufficient evidence of a live capability.

## Acceptance issues to resolve

1. **SAP/SuccessFactors confidence (P0 acceptance rule):** test the user-directed High label with valid live retrieval, and ensure failed or mismatched retrieval is disclosed. See CONF-01–05 in the test plan.
2. **Published release identity (P0):** capture the live agent name, version/publish time, instructions, channels and tools. The retained publish snapshot is dated and may be stale.
3. **Authorization and privacy (P0):** test permitted and denied personas through the published experience; retain available platform audit evidence. No source-code inspection substitutes for this.
4. **Source and confidence integrity (P0):** verify each material claim against the system actually queried and show confidence per datapoint, especially in mixed-source answers.
5. **Autonomy and confirmation policy (P0):** reconcile scheduled delivery requested by the workbook with the published agent's actual authorization model. Test any approved bounded standing authorization without sending to real recipients.
6. **Durability and audit (P1):** inspect effective published storage, retention, signing/key and recovery settings, then test only with disposable records. Historical metadata alone cannot establish durability or tamper resistance.
7. **30-day evidence (P1):** gather genuine post-deployment recommendation and evaluation logs. Do not substitute a code test or synthetic demonstration for operating history.

## Sign-off condition

Do not report the 52 workbook requirements as passed until each row has published-version test evidence or a formally accepted exclusion. Use [TEST_PLAN.md](TEST_PLAN.md) and [REQUIREMENTS_TRACEABILITY.csv](REQUIREMENTS_TRACEABILITY.csv). The current disposition is **pending live access and test execution**.
