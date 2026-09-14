# Migration Rollback Instructions — MoM 2026-09-10

## 1. Safety Principles & Invariants
1. **Never Drop Audit History**: Under no circumstance should `cre2f_veloraagentauditlog`, `cre2f_botuserconsent`, or any audit history tables be dropped or truncated during rollback.
2. **Expand/Migrate Tolerant Architecture**: The application code is built to tolerate the expand/migrate transition. Rolling back application containers to prior versions will continue to operate safely against the expanded database schema without needing schema rollback.
3. **Preserve Idempotency & Outbox State**: Do not delete pending outbox rows or operations during rollback; preserve their durable states to allow clean drain or controlled replay.

---

## 2. Fast Rollback (Application Rollback Only)
Because migrations `001_create_operations_and_outbox.sql` and `002_create_business_entities.sql` are **strictly additive** (new tables, indexes, and nullable/default columns only), rolling back simply involves:

1. **Revert Application Deployment**:
   ```bash
   # Revert Azure Container Apps revision to previous known good revision:
   az containerapp revision set-active \
     --name velora-productivity-mcp \
     --resource-group rg-velora-prod \
     --revision <PREVIOUS_REVISION_NAME>
   ```
2. **Verify Service Health**:
   Check health endpoints on the rolled back containers:
   ```bash
   curl -s -f https://<service-url>/health || echo "Health check failed"
   ```

---

## 3. Schema Rollback (If Explicitly Mandated by Change Advisory Board)
If emergency database rollback is required to decommission new entities:

### Step 3.1: Verify Zero Active Transactions
```sql
SELECT pid, query, state, age(clock_timestamp(), query_start) 
FROM pg_stat_activity 
WHERE query LIKE '%operations%' OR query LIKE '%notification_deliveries%';
```

### Step 3.2: Revert Compatibility Views First
```sql
DROP VIEW IF EXISTS cre2f_recommendation;
```

### Step 3.3: Drain or Archive Pending Outbox Rows Before Dropping
```sql
-- Archive any undelivered notification outbox entries to an archive table:
CREATE TABLE IF NOT EXISTS notification_deliveries_archive AS 
SELECT * FROM notification_deliveries WHERE status IN ('PENDING', 'FAILED_RETRYABLE');
```

### Step 3.4: Remove Non-Audit Business Entities (DO NOT DROP AUDIT TABLES)
```sql
-- Safe removal of W03 newly created business tables
DROP TABLE IF EXISTS peer_benchmark CASCADE;
DROP TABLE IF EXISTS proposal_evaluation CASCADE;
DROP TABLE IF EXISTS institutional_record CASCADE;
DROP TABLE IF EXISTS decision_evidence CASCADE;
DROP TABLE IF EXISTS recommendation_feedback CASCADE;
DROP TABLE IF EXISTS kpi_snapshot CASCADE;
DROP TABLE IF EXISTS kpi_recommendation_rule CASCADE;
DROP TABLE IF EXISTS kpi_definition CASCADE;
DROP TABLE IF EXISTS source_catalog CASCADE;

-- Safe removal of outbox / operation tables
DROP TABLE IF EXISTS notification_deliveries CASCADE;
DROP TABLE IF EXISTS breach_episodes CASCADE;
DROP TABLE IF EXISTS cooldowns CASCADE;
DROP TABLE IF EXISTS recommendations CASCADE;
DROP TABLE IF EXISTS operations CASCADE;
DROP TABLE IF EXISTS audit_reconciliation_queue CASCADE;
```

---

## 4. Post-Rollback Validation Checklist
- [ ] Ensure `cre2f_veloraagentauditlog` records are 100% intact.
- [ ] Confirm previous container revision is serving traffic.
- [ ] Inspect error logs for any missing table exceptions.
- [ ] File incident post-mortem with CAB documenting the rollback root cause.
