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
from typing import Optional

from productivity_mcp.m365_client import Microsoft365Client
from productivity_mcp.recommendation_engine import RecommendationEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
log = logging.getLogger("productivity_mcp.worker")


def run_worker_pass(
    outbox_dir: Optional[str] = None,
    require_live_delivery: Optional[bool] = None,
    user_email: str = "balaadm@velora.ae",
) -> int:
    """Execute a single finite worker pass. Returns count of delivered items."""
    outbox_path = outbox_dir or os.getenv("VELORA_OUTBOX_DIR", "/tmp/velora_outbox")
    live_req = require_live_delivery if require_live_delivery is not None else (os.getenv("REQUIRE_LIVE_DELIVERY", "false").lower() == "true")

    log.info(f"starting_worker_sweep outbox_dir={outbox_path} live_required={live_req}")
    try:
        engine = RecommendationEngine(outbox_dir=outbox_path)

        # 1. Reconcile expired worker leases & stalled submissions
        reconciled = engine.outbox.reconcile_expired_leases()
        if reconciled > 0:
            log.info(f"worker_reconciled_leases count={reconciled}")

        # 2. Dispatch pending outbox notifications
        client = Microsoft365Client(user_email=user_email)
        delivered = engine.dispatch_outbox(m365_client=client, require_live_delivery=live_req)
        log.info(f"worker_sweep_complete delivered={delivered} reconciled={reconciled}")
        return delivered
    except Exception as ex:
        log.error(f"worker_sweep_fatal_error error={ex}", exc_info=True)
        raise


if __name__ == "__main__":
    try:
        run_worker_pass()
        sys.exit(0)
    except Exception:
        sys.exit(1)
