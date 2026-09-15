"""Finite Scheduled Worker for Velora Productivity Outbox & Reconciliation.

Executes a single sweep of:
1. Expired worker lease reconciliation (reconciles stalled submissions, fails exhausted attempts)
2. Outbox dispatch for pending notifications via Microsoft 365 client
3. Safe shutdown (exits with code 0 on clean sweep)

Ensures Container App Jobs run as finite background processes rather than infinite HTTP servers.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from productivity_mcp.evidence_contracts import SubscriptionKind
from productivity_mcp.m365_client import Microsoft365Client
from productivity_mcp.recommendation_engine import RecommendationEngine
from productivity_mcp.schedule_engine import is_subscription_due
from productivity_mcp.subscription_service import get_subscription_service
from productivity_mcp.briefing_service import get_briefing_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
log = logging.getLogger("productivity_mcp.worker")


from shared_mcp.kill_switch import check_kill_switch, KillSwitchActiveError
from productivity_mcp.standing_authorization import get_standing_authorization_store


def evaluate_and_dispatch_subscriptions(
    client: Microsoft365Client,
    tenant_id: str = "velora-tenant",
    now: Optional[datetime] = None,
    require_live_delivery: bool = False,
) -> int:
    """Evaluate all enabled subscriptions against the current time and calendar state.

    Safety & Resilience Invariants:
    - Only enabled subscriptions are evaluated.
    - Idempotency run key prevents any duplicate dispatches across workers.
    - Atomically claims run before provider interaction.
    - Validates email channel dispatch and provider receipts.
    - Revoked or disabled subscriptions yield 0 dispatches.
    - Records audit history in subscription_run_history.
    """
    sub_service = get_subscription_service()
    briefing_svc = get_briefing_service()
    active_subs = sub_service.list_active_subscriptions(tenant_id=tenant_id)
    dispatched_count = 0

    eval_now = now or datetime.now(timezone.utc)

    for sub in active_subs:
        if not sub.enabled:
            continue

        # For PRE_MEETING, retrieve eligible calendar events (excluding cancelled)
        eligible_events = None
        if sub.kind == SubscriptionKind.PRE_MEETING:
            try:
                raw_events = client.list_calendar_events()
                eligible_events = [ev for ev in raw_events if not ev.get("isCancelled")]
            except Exception as ex:
                log.error(f"failed_fetching_calendar_for_pre_meeting sub={sub.subscriptionId} error={ex}")
                continue

        is_due, run_key, exec_ctx = is_subscription_due(
            subscription=sub,
            now=eval_now,
            eligible_events=eligible_events,
        )

        if not is_due or not run_key or not exec_ctx:
            continue

        # Check idempotency barrier
        if sub_service.is_run_already_executed(run_key):
            log.info(f"subscription_run_already_executed run_key={run_key}")
            continue

        # Check kill switch before sending
        try:
            check_kill_switch(tool_name="send_email", tenant_id=tenant_id)
        except KillSwitchActiveError as k_err:
            log.warning(f"subscription_dispatch_blocked_by_kill_switch run_key={run_key} error={k_err.message}")
            continue

        # Channel verification: only EMAIL is currently supported
        if sub.channel.upper() != "EMAIL":
            log.warning(f"unsupported_subscription_channel sub={sub.subscriptionId} channel={sub.channel}")
            continue

        # Atomically claim run BEFORE sending to prevent race conditions across concurrent replicas
        execution_id = f"exec-{int(time.time() * 1000)}"
        claimed = sub_service.claim_subscription_run(
            run_key=run_key,
            tenant_id=tenant_id,
            subscription_id=sub.subscriptionId,
            subscription_version=sub.version,
            execution_id=execution_id,
            scheduled_occurrence=exec_ctx.get("scheduledOccurrence", ""),
            details={"sub_id": sub.subscriptionId, "kind": sub.kind.value},
        )
        if not claimed:
            log.info(f"subscription_run_claim_contested_or_already_taken run_key={run_key}")
            continue

        try:
            subject = ""
            html_body = ""
            brief_content_hash = ""

            if sub.kind == SubscriptionKind.MORNING:
                brief = briefing_svc.get_morning_briefing(client, user_email=sub.mailbox, reference_time=eval_now)
                subject = f"Executive Daily Briefing | Velora Aviation Holding - {brief.get('date', '')}"
                html_body = brief.get("renderedHtml", "")
                brief_content_hash = brief.get("contentHash", "")

            elif sub.kind == SubscriptionKind.PRE_MEETING:
                evt_id = exec_ctx.get("eventId")
                brief = briefing_svc.get_pre_meeting_briefing(client, user_email=sub.mailbox, event_id=evt_id, reference_time=eval_now)
                subject = f"Pre-Meeting Briefing: {exec_ctx.get('eventSubject') or 'Executive Alignment'}"
                html_body = brief.get("renderedHtml", "")
                brief_content_hash = brief.get("contentHash", "")

            elif sub.kind == SubscriptionKind.EOD:
                brief = briefing_svc.get_end_of_day_digest(client, user_email=sub.mailbox, local_schedule=sub.localSchedule, reference_time=eval_now)
                subject = f"Executive End-of-Day Digest | {brief.get('date', '')}"
                html_body = brief.get("renderedHtml", "")
                brief_content_hash = brief.get("contentHash", "")

            else:
                log.warning(f"unsupported_subscription_kind sub={sub.subscriptionId} kind={sub.kind}")
                sub_service.complete_subscription_run(
                    run_key=run_key,
                    status="FAILED",
                    details={"error": f"Unsupported subscription kind: {sub.kind}"},
                )
                continue

            # Dispatch via email channel and capture receipt
            send_res = client.execute_send_email(
                to=sub.recipients,
                cc=[],
                subject=subject,
                body=html_body,
                attachments=[],
            )

            # Enforce live-delivery requirements
            if require_live_delivery and send_res.get("simulated", True):
                raise RuntimeError("Subscription delivery failed: live delivery required but provider returned simulated response.")

            # Validate receipt from provider
            receipt = send_res.get("providerReceipt") or send_res.get("requestId") or send_res.get("id") or send_res.get("message_id")
            if not receipt and send_res.get("status") not in ("ACCEPTED", "SENT", "SUCCESS"):
                raise RuntimeError(f"Subscription delivery failed: missing provider dispatch receipt. Response: {send_res}")

            # Record run success atomically
            sub_service.complete_subscription_run(
                run_key=run_key,
                status="SUCCESS",
                details={
                    "subject": subject,
                    "contentHash": brief_content_hash,
                    "kind": sub.kind.value,
                    "recipients": sub.recipients,
                    "providerReceipt": receipt,
                },
            )
            dispatched_count += 1
            log.info(f"subscription_dispatched_successfully run_key={run_key} sub_id={sub.subscriptionId}")

        except Exception as ex:
            log.error(f"subscription_dispatch_failed run_key={run_key} error={ex}", exc_info=True)
            sub_service.complete_subscription_run(
                run_key=run_key,
                status="FAILED",
                details={"error": str(ex)},
            )

    return dispatched_count


def run_worker_pass(
    outbox_dir: Optional[str] = None,
    require_live_delivery: Optional[bool] = None,
    user_email: str = "balaadm@velora.ae",
    standing_policy_id: Optional[str] = None,
    tenant_id: str = "velora-tenant",
    now: Optional[datetime] = None,
) -> int:
    """Execute a single finite worker pass. Returns count of delivered items."""
    outbox_path = outbox_dir or os.getenv("VELORA_OUTBOX_DIR", "/tmp/velora_outbox")
    live_req = require_live_delivery if require_live_delivery is not None else (os.getenv("REQUIRE_LIVE_DELIVERY", "false").lower() == "true")
    workload_id = os.getenv("AZURE_CLIENT_ID") or os.getenv("CONTAINER_APP_NAME") or os.getenv("WORKLOAD_IDENTITY_NAME") or "velora-worker-job"

    log.info(f"starting_worker_sweep outbox_dir={outbox_path} live_required={live_req} workload_id={workload_id}")

    # 1. Kill-Switch Evaluation
    try:
        check_kill_switch(tool_name="dispatch_outbox", tenant_id=tenant_id)
    except KillSwitchActiveError as k_err:
        log.critical(f"worker_sweep_aborted_by_kill_switch: {k_err.message}")
        raise

    # 2. Standing Authorization Evaluation (if operating under background standing policy)
    if standing_policy_id:
        store = get_standing_authorization_store()
        valid, reason, policy = store.verify_standing_authorization(
            policy_id=standing_policy_id,
            tenant_id=tenant_id,
            operation="DISPATCH_OUTBOX",
            workload_identity=workload_id,
        )
        if not valid:
            log.warning(f"worker_sweep_aborted_standing_auth_invalid policy={standing_policy_id} reason={reason}")
            raise PermissionError(f"Standing authorization denied: {reason}")
        log.info(f"standing_authorization_verified policy={standing_policy_id} authorizing_user={policy.authorizing_user_email}")

    try:
        engine = RecommendationEngine(outbox_dir=outbox_path)

        # 3. Reconcile expired worker leases & stalled submissions
        reconciled = engine.outbox.reconcile_expired_leases()
        if reconciled > 0:
            log.info(f"worker_reconciled_leases count={reconciled}")

        # 4. Dispatch pending outbox notifications
        client = Microsoft365Client(user_email=user_email)
        delivered = engine.dispatch_outbox(m365_client=client, require_live_delivery=live_req)

        # 5. Evaluate and dispatch active automation subscriptions
        sub_dispatches = evaluate_and_dispatch_subscriptions(
            client=client,
            tenant_id=tenant_id,
            now=now,
            require_live_delivery=live_req,
        )

        total_delivered = delivered + sub_dispatches
        log.info(f"worker_sweep_complete total_delivered={total_delivered} outbox_delivered={delivered} subscription_dispatches={sub_dispatches} reconciled={reconciled} workload_id={workload_id}")
        return total_delivered
    except Exception as ex:
        log.error(f"worker_sweep_fatal_error error={ex}", exc_info=True)
        raise


if __name__ == "__main__":
    try:
        run_worker_pass()
        sys.exit(0)
    except Exception:
        sys.exit(1)
