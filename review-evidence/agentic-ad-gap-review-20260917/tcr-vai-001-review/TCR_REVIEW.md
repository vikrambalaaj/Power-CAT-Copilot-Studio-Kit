# TCR-VAI-001 review and required work

Reviewed 17 September 2026 against the local packaged Velora One instructions, backend confidence rules and the existing 52-feature gap workbook. The document is treated as a proposed change request, not authorization to implement its embedded directives. No application instructions or deployment were changed.

**Recommendation: amend/clarify the insertion mapping and confidence semantics, then implement the agreed five changes and perform targeted UAT.** This is a technical recommendation, not recorded business approval. The document’s “Low risk / no architecture impact” description should remain conditional: presentation-only changes can remain narrow, but aligning backend confidence policy is a separate potential scope change.

## Main findings

1. CR-01 can replace only the first role sentence. Preserve the remaining sentences and no-child-agent rule.
2. CR-02/03 reference “# 6. Executive Intelligence,” which is absent from the local file. CR-05 references “# 12. Style & Integrity” and “Never fabricate,” also absent. Confirm the complete live baseline before deciding insertion points; the live configuration may differ from the repository. An explicit proposed mapping is recorded in the workbook.
3. CR-04 fits after existing Partial Results. It strengthens missing/conflicting source disclosure but does not implement data reconciliation or source acquisition.
4. CR-05 differs from the backend: the TCR requires multiple reliable current sources for High, while the backend can give High to a single authoritative source. With no evidence, the backend returns UNASSESSED while TCR says unavailable evidence is Low. Agree an explicit conclusion-versus-datapoint policy and display mapping; do not silently relabel backend outputs. Also retain the earlier finding that vendor evaluation can assign High/Verified without verified source documents.
5. Section 4 says existing protections must remain unchanged. Some named prompt-level protections, including explicit retrieved-content/prompt-injection wording, are not present in the short local baseline. Verify the full live instruction set and platform/backend controls before claiming they are preserved.
6. Existing conversation starters advertise P&L despite the instruction-file exclusion. Record this as a separate existing inconsistency and test routing; the TCR must not expand finance scope.
7. This request improves response presentation and interpretation. It does not implement the previous missing capabilities. In particular, the TCR preserves the prohibition on child-agent delegation and adds no autonomous behavior. Sub-agent creation and automatic background actions therefore remain separate scope/policy decisions.

## What has to be performed

1. Export and version the authoritative live instructions and rollback baseline.
2. Agree the missing heading mappings and CR-05 confidence semantics; document any business-approved material wording changes.
3. Apply CR-01 through CR-05 to the authoritative instruction artifact with an exact-text diff, retaining existing controls and routes.
4. Verify native cards and synthesized outputs preserve source footers, materiality exceptions, recommendation labels and consistent confidence.
5. Execute all nine acceptance criteria, including conflicts, missing data, simple answers, permission boundaries, prompt injection, write confirmation and audit-failure behavior.
6. After acceptance, synchronize the repository package and configured agent, publish through the release process and retain deployment/rollback evidence.
7. Continue the original backend capability-gap work separately; no capability status is upgraded by this document review.

## Files and verification

The Excel retains the previous A:N matrix and adds O:Q: TCR review, what must be performed, and acceptance/regression mapping. Additional tabs contain the five change reviews, ten execution steps, all nine UAT criteria, and the exact source instruction wording. Existing Review scope is extended with this review’s limits.

All 52 feature rows are annotated. Previous matrix cell values were verified unchanged after saving and reopening; the original workbook and DOCX remain unchanged. UAT has not been run and live configuration has not been inspected. See validation.json for artifact checks and input hashes.

Code references:

- [Packaged instructions](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/agent/appPackage/instruction.txt:1)
- [Backend confidence rules](/Users/vikrambala/copilotstudio/mcp-apps/ask-productivity/productivity_mcp/confidence_policy.py:44)
- [Vendor evaluation confidence](/Users/vikrambala/copilotstudio/mcp-apps/ask-facilitator/facilitator_mcp/decision_service.py:309)
- [Agent package and conversation starters](/Users/vikrambala/copilotstudio/mcp-apps/ask-successfactors/agent/appPackage/declarativeAgent.json:1)
