"""Velora Asynchronous Background Logging & Durable Outbox Worker.

Ensures the user-facing response path never waits for Dataverse audit writes.
Implements bounded async queueing, durable file-backed spooling for container restart recovery,
retry with exponential backoff, and transcript reconciliation.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .dataverse_audit import (
    DataverseAuditRecord,
    RECORD_TYPE_LOGGING_ERROR,
    get_dataverse_client,
    AuditCommitStatus,
)
from shared_mcp.logger import get_logger

log = get_logger("background_logger")

MAX_QUEUE_SIZE = int(os.getenv("AUDIT_LOG_QUEUE_SIZE", "5000"))
MAX_RETRIES = int(os.getenv("AUDIT_LOG_MAX_RETRIES", "5"))
INITIAL_BACKOFF_SEC = float(os.getenv("AUDIT_LOG_INITIAL_BACKOFF", "0.5"))


class BackgroundLogger:
    """Non-blocking background queue and async worker for Dataverse audit logging with durable spooling."""

    def __init__(self, dataverse_client=None, spool_path: Optional[str] = None):
        self.client = dataverse_client or get_dataverse_client()
        self._queue: Optional[asyncio.Queue[DataverseAuditRecord]] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
        self._total_enqueued = 0
        self._total_persisted = 0
        self._total_failed = 0
        raw_spool = (
            spool_path
            or os.getenv("AZURE_STORAGE_MOUNT_PATH")
            or os.getenv("VELORA_STATE_DIR")
            or os.getenv("DATAVERSE_AUDIT_SPOOL_PATH")
            or str(Path.home() / ".velora" / "sf_audit_spool.jsonl")
        )
        p = Path(raw_spool)
        try:
            if p.is_dir() or (not p.suffix and not p.name.endswith(".jsonl")):
                p = p / "sf_audit_spool.jsonl"
        except OSError:
            if not p.suffix and not p.name.endswith(".jsonl"):
                p = p / "sf_audit_spool.jsonl"
        self.spool_path = p
        self._load_uncommitted_spool()

    def _get_queue(self) -> asyncio.Queue[DataverseAuditRecord]:
        """Ensure queue is bound to the currently running event loop."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        elif current_loop is not None:
            q_loop = getattr(self._queue, "_loop", None)
            if q_loop is not None and q_loop is not current_loop:
                # Rebind queue to new event loop while preserving pending items
                old_items = []
                while not self._queue.empty():
                    try:
                        old_items.append(self._queue.get_nowait())
                    except Exception:
                        break
                self._queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
                for item in old_items:
                    self._queue.put_nowait(item)
        return self._queue

    def _get_record_event_id(self, record: DataverseAuditRecord) -> str:
        if not getattr(record, "audit_id", None):
            record.audit_id = (
                record.invocation_id
                or f"EVT-{int(time.time() * 1000)}-{os.urandom(4).hex()}"
            )
        return record.audit_id

    def _load_uncommitted_spool(self) -> None:
        """Recover uncommitted audit records from disk on startup by replaying state machine."""
        try:
            if not self.spool_path.exists():
                return
        except OSError:
            return
        try:
            records_by_key: Dict[str, dict] = {}
            with open(self.spool_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        key = entry.get("event_id") or entry.get("turn_id")
                        if not key:
                            continue
                        if entry.get("persisted", False):
                            # Later commit marker indicates record was successfully persisted
                            if key in records_by_key:
                                records_by_key[key]["persisted"] = True
                            else:
                                records_by_key[key] = {"event_id": key, "turn_id": entry.get("turn_id"), "persisted": True}
                            if entry.get("turn_id") and entry.get("turn_id") in records_by_key:
                                records_by_key[entry["turn_id"]]["persisted"] = True
                        else:
                            # Pending record
                            if key not in records_by_key or not records_by_key[key].get("persisted", False):
                                records_by_key[key] = entry
                    except Exception:
                        continue

            for key, entry in records_by_key.items():
                if not entry.get("persisted", False):
                    payload = entry.get("payload", {})
                    if payload:
                        rec = DataverseAuditRecord.from_dataverse_payload(payload)
                        rec.audit_id = entry.get("event_id") or rec.audit_id
                        self._get_queue().put_nowait(rec)
                        self._total_enqueued += 1
        except Exception as ex:
            log.warning("spool_recovery_warning", error=str(ex))

    def _spool_record(self, record: DataverseAuditRecord) -> str:
        """Persist record to durable outbox before async dispatch."""
        event_id = self._get_record_event_id(record)
        try:
            self.spool_path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "event_id": event_id,
                "turn_id": record.turn_id,
                "record_type": record.record_type,
                "time": time.time(),
                "persisted": False,
                "payload": record.to_dataverse_payload(),
            }
            with open(self.spool_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as ex:
            log.error("durable_spool_write_failed", error=str(ex), spool_path=str(self.spool_path))
            raise IOError(f"Spool write failed to {self.spool_path}: {ex}") from ex
        return event_id

    def _mark_spool_persisted(self, event_id: str, turn_id: Optional[str] = None) -> None:
        """Mark record as safely committed to Dataverse."""
        try:
            if not self.spool_path.exists():
                return
            commit_entry = {
                "event_id": event_id,
                "turn_id": turn_id or event_id,
                "persisted": True,
                "time": time.time(),
            }
            with open(self.spool_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(commit_entry) + "\n")
        except Exception as ex:
            log.error("durable_spool_commit_marker_failed", error=str(ex), spool_path=str(self.spool_path))
            raise IOError(f"Commit marker write failed to {self.spool_path}: {ex}") from ex

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
        queue = self._get_queue()
        if self._worker_task and not self._worker_task.done():
            # Wait briefly to drain remaining items
            try:
                await asyncio.wait_for(queue.join(), timeout=3.0)
            except asyncio.TimeoutError:
                pass
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        log.info("background_logger_stopped", enqueued=self._total_enqueued, persisted=self._total_persisted)

    def enqueue(self, record: DataverseAuditRecord) -> bool:
        """Non-blocking enqueue of an audit event with durable spooling. Returns immediately to caller."""
        try:
            self._spool_record(record)
            queue = self._get_queue()
            queue.put_nowait(record)
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
        queue = self._get_queue()
        while self._running:
            try:
                record = await queue.get()
            except asyncio.CancelledError:
                break

            persisted = False
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    record.retry_count = attempt - 1
                    res = await self.client.create_audit_record(record)
                    commit_status = res.get("commit_status") or res.get("status")
                    if commit_status in (AuditCommitStatus.COMMITTED, AuditCommitStatus.ALREADY_COMMITTED):
                        self._total_persisted += 1
                        persisted = True
                        event_id = self._get_record_event_id(record)
                        self._mark_spool_persisted(event_id, turn_id=record.turn_id)
                        break
                    elif commit_status == AuditCommitStatus.BUFFERED:
                        # Acceptance requirement: A BUFFERED sink never produces a committed spool marker.
                        log.info("audit_sink_buffered_no_spool_release", event_id=self._get_record_event_id(record))
                        break
                    else:
                        raise RuntimeError(f"Audit write returned status {commit_status}: {res.get('message') or res.get('error')}")
                except Exception as exc:
                    log.warning("dataverse_audit_write_retry", attempt=attempt, error=str(exc))
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(INITIAL_BACKOFF_SEC * (2 ** (attempt - 1)))

            if not persisted:
                self._total_failed += 1
                log.error("dataverse_audit_write_exhausted", turn_id=record.turn_id)

            queue.task_done()

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
        queue = self._get_queue()
        return {
            "queue_size": queue.qsize(),
            "total_enqueued": self._total_enqueued,
            "total_persisted": self._total_persisted,
            "total_failed": self._total_failed,
            "running": self._running,
        }


_global_background_logger = BackgroundLogger()


def get_background_logger() -> BackgroundLogger:
    return _global_background_logger
