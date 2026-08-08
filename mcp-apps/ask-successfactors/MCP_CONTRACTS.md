# MCP contracts for the six SAP queries

## Common response envelope

Every successful tool returns this logical structure in `structuredContent`:

```json
{
  "status": "success",
  "data": {},
  "source": {
    "system": "SAP SuccessFactors or SAP S/4HANA",
    "object": "approved OData entity or CDS service",
    "asOf": "ISO-8601 timestamp"
  },
  "query": {
    "filters": {},
    "currency": null,
    "unit": null,
    "period": null
  },
  "quality": {
    "complete": true,
    "sampled": false,
    "confidence": "high",
    "warnings": []
  },
  "audit": {
    "correlationId": "request correlation ID",
    "authorizationModel": "delegated or approved-service-identity"
  },
  "cache": {
    "status": "disabled, miss, hit, or coalesced",
    "ageSeconds": 0,
    "ttlSeconds": 60,
    "storedAt": "ISO-8601 timestamp"
  }
}
```

Cache metadata is informational and must not replace the source envelope. On a cache hit, `source.asOf` remains the time at which the cached SAP result was stored. See `CACHE.md` for isolation, invalidation, and tuning rules.

Errors use `status: "error"`, a stable error code, a safe message, retryability, and the same correlation ID. They never include credentials, tokens, raw upstream error bodies, or personal records.

## SuccessFactors MCP

### `sf__get_headcount`

**Purpose:** Return headcount and position count, trimmed by SuccessFactors RBP.

**Inputs:** company, business unit, division, department, location, employee class, as-of date.

**Output:** active headcount, position count, FTE, breakdown, filters, as-of time, and source `EmpJob` or the approved tenant-specific equivalent.

**Rules:** Define active-worker logic centrally; do not count job-history rows as people; do not expose individual records unless the user explicitly requests an authorized drill-down.

### `sf__get_emiratisation_kpi`

**Purpose:** Return the aggregate Emiratisation KPI.

**Inputs:** company, organization filters, as-of date, target version.

**Output:** eligible headcount, Emirati-national count, ratio, target, variance, status, and rule version.

**Rules:** Aggregate only; suppress small groups; never reveal or infer an individual's nationality; configure the tenant-specific eligibility and nationality filters outside the model.

## S/4HANA MCP

The S/4HANA server must call allowlisted, released CDS/OData services selected by the finance owner. Exact service names differ by tenant and must be configured rather than guessed in code.

### `s4__get_receivables_aging`

**Purpose:** Return accounts-receivable exposure and aging.

**Inputs:** company code, key date, customer, currency, aging-bucket definition, materiality threshold.

**Output:** total receivables, overdue amount, aging buckets, top material exposures, owner where authorized, currency, and key date.

**Rules:** Normalize currencies explicitly; label disputed, blocked, or special-G/L items; avoid exposing bank or unnecessary customer personal data.

### `s4__get_payables_aging`

**Purpose:** Return open supplier liabilities and upcoming payment exposure.

**Inputs:** company code, key date, supplier, currency, aging buckets, due-date horizon.

**Output:** total open payables, overdue amount, due-soon amount, aging buckets, material suppliers, currency, and key date.

**Rules:** Respect payment blocks and sensitive supplier restrictions; no payment execution tool is included in phase one.

### `s4__get_profit_and_loss`

**Purpose:** Return a live P&L view.

**Inputs:** ledger, company code, fiscal year/period, comparison period, currency type, profit center, segment.

**Output:** revenue, cost, operating result, margin, comparison, variance, hierarchy version, currency, and period status.

**Rules:** Identify actual/plan/version and posting status; do not combine currencies or accounting bases silently.

### `s4__get_budget_variance`

**Purpose:** Compare budget or plan with actuals and identify supported variance drivers.

**Inputs:** plan version, ledger, company code, fiscal period, cost/profit center, account hierarchy, currency type, materiality threshold.

**Output:** budget, actual, absolute variance, percentage variance, favorable/unfavorable status, material drivers, currency, and rule version.

**Rules:** Driver statements must be supported by returned dimensions; narrative correlation is not causation; divide-by-zero and missing-plan cases must be explicit.

## Cross-server synthesis

For a cross-domain metric, the agent must retain both source envelopes and state the join logic. Example: revenue per employee must disclose the S/4HANA revenue period, SuccessFactors headcount as-of date, currency, average-versus-ending headcount choice, and any timing mismatch.
