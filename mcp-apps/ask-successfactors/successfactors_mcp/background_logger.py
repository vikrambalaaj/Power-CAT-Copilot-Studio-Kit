"""Velora Asynchronous Background Logging & Reconciliation Worker.

Ensures the user-facing response path never waits for Dataverse audit writes.
Implements bounded async queueing, retry with exponential backoff, and transcript reconciliation.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, List, Optional

from .dataverse_audit import (
    DataverseAuditRecord,
    RECORD_TYPE_LOGGING_ERROR,
    get_dataverse_client,
)
from shared_mcp.logger import get_logger

log = get_logger("background_logger")

MAX_QUEUE_SIZE = int(os.getenv("DATAVERSE_LOG_QUEUE_MAX", "10000"))
MAX_RETRIES = int(os.getenv("DATAVERSE_LOG_MAX_RETRIES", "3"))
INITIAL_BACKOFF_SEC = float(os.getenv("DATAVERSE_LOG_BACKOFF_SEC", "0.5"))


class BackgroundLogger:
    """Non-blocking background queue and async worker for Dataverse audit logging."""

    def __init__(self, dataverse_client=None):
        self.client = dataverse_client or get_dataverse_client()
        self._queue: asyncio.Queue[DataverseAuditRecord] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
        self._total_enqueued = 0
        self._total_persisted = 0
        self._total_failed = 0

    def start(self) -> None:
        """Start the background consumer worker task."""
        if self._worker_task is None or self._worker_task.done():
            self._running = True
            try:
                loop = asyncio.get_running_loop()
                self._worker_task = loop.create_task(self._worker_loop())
                log.info("background_logger_started")
            except RuntimeError:
                # Loop not running yet, will be started with server lifespan
                pass

    async def stop(self) -> None:
        """Gracefully drain the queue and stop the background worker."""
        self._running = False
        if self._worker_task and not self._worker_task.done():
            # Wait briefly to drain remaining items
            try:
                await asyncio.wait_for(self._queue.join(), timeout=3.0)
            except asyncio.TimeoutError:
                pass
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        log.info("background_logger_stopped", enqueued=self._total_enqueued, persisted=self._total_persisted)

    def enqueue(self, record: DataverseAuditRecord) -> bool:
        """Non-blocking enqueue of an audit event. Returns immediately to caller."""
        try:
            self._queue.put_nowait(record)
            self._total_enqueued += 1
            self.start()  # Ensure worker task is running if loop is active
            return True
        except asyncio.QueueFull:
            self._total_failed += 1
            log.error("background_log_queue_full", turn_id=record.turn_id)
            return False
        except Exception as exc:
            self._total_failed += 1
            log.error("enqueue_failed", error=str(exc))
            return False

    async def _worker_loop(self) -> None:
        """Continuous background loop consuming audit events."""
        while self._running:
            try:
                record = await self._queue.get()
            except asyncio.CancelledError:
                break

            persisted = False
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    record.retry_count = attempt - 1
                    await self.client.create_audit_record(record)
                    self._total_persisted += 1
                    persisted = True
                    break
                except Exception as exc:
                    log.warning("dataverse_audit_write_retry", attempt=attempt, error=str(exc))
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(INITIAL_BACKOFF_SEC * (2 ** (attempt - 1)))

            if not persisted:
                self._total_failed += 1
                log.error("dataverse_audit_write_exhausted", turn_id=record.turn_id)

            self._queue.task_done()

    async def reconcile_transcripts(self, transcript_turns: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Reconcile external platform transcript turns against Dataverse audit logs."""
        backfilled_count = 0
        existing_logs = await self.client.query_user_30_day_memory(
            user_object_id="", user_email="", days=30, limit=1000
        )
        existing_hashes = {
            log_entry.get("cre2f_contenthash")
            for log_entry in existing_logs
            if log_entry.get("cre2f_contenthash")
        }

        for turn in transcript_turns:
            user_msg = turn.get("user_message", "")
            asst_msg = turn.get("assistant_message", "")
            content_hash = turn.get("content_hash") or turn.get("cre2f_contenthash")
            if not content_hash and (user_msg or asst_msg):
                from .dataverse_audit import compute_content_hash
                content_hash = compute_content_hash(user_msg + asst_msg)

            if content_hash and content_hash not in existing_hashes:
                # Missing turn in Dataverse, backfill it
                rec = DataverseAuditRecord(
                    record_type=turn.get("record_type", "USER_TURN"),
                    user_object_id=turn.get("user_object_id", ""),
                    user_email=turn.get("user_email", ""),
                    conversation_id=turn.get("conversation_id", ""),
                    turn_id=turn.get("turn_id", f"recon-{int(time.time() * 1000)}"),
                    user_message=user_msg,
                    assistant_message=asst_msg,
                    message_summary=turn.get("message_summary", "Reconciled from transcript"),
                )
                rec.content_hash = content_hash
                rec.reconciled = True
                await self.client.create_audit_record(rec)
                existing_hashes.add(content_hash)
                backfilled_count += 1

        return {
            "status": "RECONCILIATION_COMPLETE",
            "evaluated_turns": len(transcript_turns),
            "backfilled_turns": backfilled_count,
            "completeness_ratio": 1.0 if len(transcript_turns) == 0 else round(1.0 - (backfilled_count / len(transcript_turns)), 4),
        }

    def get_stats(self) -> Dict[str, Any]:
        return {
            "queue_size": self._queue.qsize(),
            "total_enqueued": self._total_enqueued,
            "total_persisted": self._total_persisted,
            "total_failed": self._total_failed,
            "running": self._running,
        }


_global_background_logger = BackgroundLogger()


def get_background_logger() -> BackgroundLogger:
    return _global_background_logger
