# Operational Recovery & Disaster Playbook — MoM 2026-09-10

This document defines authoritative recovery procedures for Velora Agentic AD persistence, outbox delivery, and audit reconciliation.

---

## 1. Authoritative State and Recovery Order
When recovering from an outage, component failure, or database interruption, restore systems in this strict order:

```
[PostgreSQL / SQLite Operational State]
                   │
                   ▼ (1. Recover Operations & Outbox Locks)
[Notification Outbox Delivery Engine]
                   │
                   ▼ (2. Replay Deliveries / Drain Queues)
[Dataverse Audit & Governance Mirror]
                   │
                   ▼ (3. Drain audit_reconciliation_queue)
[Live Copilot Studio / M365 Tools]
```

**Rule**: The PostgreSQL (or SQLite local) operational store is authoritative for in-flight transaction lifecycle, locks, and recommendation outbox state. Dataverse is the governed audit destination and mirror.

---

## 2. Scenario 1: Container / Pod Crash or Abrupt Restart
When a container terminates unexpectedly during execution:

1. **State Preservation**:
   - `operations` in `PREPARED`, `APPROVED`, or `EXECUTING` retain their state, `token_hash`, and server-side `operation_id`.
   - `cooldowns` and `breach_episodes` are durably stored in SQL tables—no alert storm will be generated upon container boot.
2. **Expired Outbox Claim Clean-up**:
   - Deliveries locked by dead containers auto-expire when `locked_until < NOW()`.
   - The outbox worker queries:
     ```sql
     UPDATE notification_deliveries
     SET status = 'PENDING', locked_by = NULL, locked_until = NULL
     WHERE status = 'PROCESSING' AND locked_until < NOW();
     ```
3. **Operations Timeout Sweeper**:
   - Background job expires stale prepared operations:
     ```python
     store.expire_stale_operations()
     ```

---

## 3. Scenario 2: Dataverse Outage / Degradation Recovery
When Microsoft Dataverse endpoints become unreachable (`simulate_down=True` or 502/503/504 errors):

1. **Governed Writes Fail Closed**:
   - Stage B write executions require committed Dataverse audit records. If Dataverse is down, writes are blocked (`FAIL_CLOSED_BLOCKED`), preventing un-audited state mutation.
2. **Read Audits Buffer to Reconciliation Queue**:
   - Best-effort read audits are durably enqueued into `audit_reconciliation_queue`.
3. **Recovery & Mirror Replay**:
   - Once Dataverse health probes report healthy (HTTP 200 on `/.default` token and Web API `$metadata`), invoke the reconciliation worker:
     ```python
     from productivity_mcp.audit_client import get_productivity_audit_service
     audit_service = get_productivity_audit_service()
     report = await audit_service.reconcile_pending_audits(max_items=100)
     print(f"Reconciliation completed: {report}")
     ```
   - Monitor remaining count until `remaining == 0`.

---

## 4. Scenario 3: Database Concurrency Contention / Deadlocks
If two background workers or parent agents attempt to claim or complete the same operation:

- `PostgresOperationStore` uses row-level locking:
  `SELECT ... FOR UPDATE SKIP LOCKED`
- The winning worker acquires the lock, increments `version = version + 1`, and transitions the state.
- The losing worker receives an optimistic concurrency error (`CONCURRENCY_CONFLICT` or `OPERATION_ALREADY_CLAIMED`).
- Recovery Action: The losing worker simply reads the committed state and reports the authoritative result back to the caller without re-executing side effects.

---

## 5. Diagnostic Commands
Check health and pending backlog across operational tables:
```sql
-- 1. Check pending outbox deliveries
SELECT status, count(*) FROM notification_deliveries GROUP BY status;

-- 2. Check stuck locks
SELECT delivery_id, locked_by, locked_until 
FROM notification_deliveries 
WHERE status = 'PROCESSING' AND locked_until < NOW();

-- 3. Check pending audit reconciliation rows
SELECT status, count(*), max(retry_count) FROM audit_reconciliation_queue GROUP BY status;

-- 4. Check active operations by state
SELECT state, count(*) FROM operations GROUP BY state;
```
