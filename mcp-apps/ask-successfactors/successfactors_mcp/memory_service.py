"""Velora Dataverse-Backed 30-Day Memory Service.

Maintains a secure, user-partitioned 30-day historical context layer.
Constructs layered memory snapshots (decisions, follow-ups, summaries) without prompt bloat.
Emits background MEMORY_SUMMARY records and handles historical context recall with live-data refresh prompts.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .dataverse_audit import (
    DataverseAuditRecord,
    RECORD_TYPE_MEMORY_SUMMARY,
    get_dataverse_client,
)
from .background_logger import get_background_logger
from shared_mcp.logger import get_logger

log = get_logger("memory_service")


class MemorySnapshot:
    """Bounded, layered snapshot of a user's 30-day interaction history."""

    def __init__(
        self,
        user_object_id: str,
        user_email: str,
        loaded_at: str,
        decisions: List[Dict[str, Any]],
        follow_ups: List[Dict[str, Any]],
        preferences: Dict[str, Any],
        conversation_summaries: List[Dict[str, Any]],
        raw_turns_count: int,
    ):
        self.user_object_id = user_object_id
        self.user_email = user_email
        self.loaded_at = loaded_at
        self.decisions = decisions
        self.follow_ups = follow_ups
        self.preferences = preferences
        self.conversation_summaries = conversation_summaries
        self.raw_turns_count = raw_turns_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_email": self.user_email,
            "loaded_at": self.loaded_at,
            "decisions_count": len(self.decisions),
            "decisions": self.decisions[:10],
            "follow_ups_count": len(self.follow_ups),
            "follow_ups": self.follow_ups[:10],
            "preferences": self.preferences,
            "summaries_count": len(self.conversation_summaries),
            "conversation_summaries": self.conversation_summaries[:20],
            "raw_turns_evaluated": self.raw_turns_count,
        }


class MemoryService:
    """Manages 30-day historical context indexing, snapshotting, and recall."""

    def __init__(self, dataverse_client=None, background_logger=None):
        self.client = dataverse_client or get_dataverse_client()
        self.bg_logger = background_logger or get_background_logger()
        self._snapshot_cache: Dict[str, Tuple[float, MemorySnapshot]] = {}
        self._lock = asyncio.Lock()

    def _cache_key(self, user_object_id: str, user_email: str) -> str:
        return f"{user_object_id or 'anon'}:{user_email.strip().lower()}"

    async def prewarm_user_memory_snapshot(
        self,
        user_object_id: str,
        user_email: str,
        force_refresh: bool = False,
    ) -> Optional[MemorySnapshot]:
        """Asynchronously load 30-day user memory and store in session snapshot cache."""
        key = self._cache_key(user_object_id, user_email)
        now = time.monotonic()

        async with self._lock:
            cached = self._snapshot_cache.get(key)
            if cached and not force_refresh and (now - cached[0] < 600):  # 10 min TTL
                return cached[1]

        try:
            raw_logs = await self.client.query_user_30_day_memory(
                user_object_id=user_object_id,
                user_email=user_email,
                days=30,
                limit=100,
            )
            snapshot = self._build_layered_snapshot(user_object_id, user_email, raw_logs)
            async with self._lock:
                self._snapshot_cache[key] = (time.monotonic(), snapshot)
            log.info("user_memory_prewarmed", user_email=user_email, turns=len(raw_logs))
            return snapshot
        except Exception as exc:
            log.warning("memory_prewarm_failed", user_email=user_email, error=str(exc))
            return None

    def _build_layered_snapshot(
        self,
        user_object_id: str,
        user_email: str,
        raw_logs: List[Dict[str, Any]],
    ) -> MemorySnapshot:
        """Process raw Dataverse turns into layered summaries and decision records."""
        decisions: List[Dict[str, Any]] = []
        follow_ups: List[Dict[str, Any]] = []
        preferences: Dict[str, Any] = {}
        summaries: List[Dict[str, Any]] = []

        for log_entry in raw_logs:
            rec_type = log_entry.get("cre2f_recordtype")
            event_time = log_entry.get("cre2f_eventtime", "")[:10]
            cid = log_entry.get("cre2f_conversationid", "")

            # Check for memory summary records
            if rec_type == RECORD_TYPE_MEMORY_SUMMARY:
                summary_text = log_entry.get("cre2f_memorysummary") or log_entry.get("cre2f_messagesummary", "")
                topics_raw = log_entry.get("cre2f_memorytopics", "[]")
                topics = json.loads(topics_raw) if isinstance(topics_raw, str) else topics_raw
                summaries.append({
                    "date": event_time,
                    "conversation_id": cid,
                    "summary": summary_text,
                    "topics": topics,
                    "importance": log_entry.get("cre2f_memoryimportance", 1),
                })
            else:
                user_msg = log_entry.get("cre2f_usermessage", "")
                asst_msg = log_entry.get("cre2f_assistantmessage", "")
                tool_name = log_entry.get("cre2f_toolname", "")

                if user_msg:
                    # Synthesize topic summary
                    summaries.append({
                        "date": event_time,
                        "conversation_id": cid,
                        "summary": f"User asked: '{user_msg[:120]}…'" if len(user_msg) > 120 else f"User asked: '{user_msg}'",
                        "tool_used": tool_name,
                        "importance": 1,
                    })

                # Check for decision/follow-up markers
                if "decide" in asst_msg.lower() or "agreed" in asst_msg.lower():
                    decisions.append({
                        "date": event_time,
                        "conversation_id": cid,
                        "detail": asst_msg[:200],
                    })

        return MemorySnapshot(
            user_object_id=user_object_id,
            user_email=user_email,
            loaded_at=datetime.now(timezone.utc).isoformat(),
            decisions=decisions[:20],
            follow_ups=follow_ups[:20],
            preferences=preferences,
            conversation_summaries=summaries[:50],
            raw_turns_count=len(raw_logs),
        )

    async def recall_user_context(
        self,
        user_object_id: str,
        user_email: str,
        topic_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Recall relevant prior topics/turns and attach disclaimer for historical figures."""
        snapshot = await self.prewarm_user_memory_snapshot(user_object_id, user_email)
        if not snapshot or (not snapshot.conversation_summaries and not snapshot.decisions):
            return {
                "status": "NO_HISTORY",
                "message": "No previous conversations found within the last 30 days.",
                "recalled_items": [],
            }

        relevant_items: List[Dict[str, Any]] = []
        q_lower = (topic_query or "").lower()

        for s in snapshot.conversation_summaries:
            if not q_lower or q_lower in s.get("summary", "").lower() or any(q_lower in str(t).lower() for t in s.get("topics", [])):
                relevant_items.append(s)

        if not relevant_items:
            relevant_items = snapshot.conversation_summaries[:5]

        return {
            "status": "SUCCESS",
            "user_email": user_email,
            "window_days": 30,
            "query_topic": topic_query or "All recent topics",
            "historical_notice": "⚠️ Historical figures reflect the state at the time of the original conversation. Would you like me to retrieve the latest live SuccessFactors numbers?",
            "recalled_count": len(relevant_items),
            "recalled_items": relevant_items[:10],
            "decisions": snapshot.decisions[:5],
        }

    def emit_memory_summary_event(
        self,
        user_object_id: str,
        user_email: str,
        conversation_id: str,
        topics: List[str],
        summary: str,
        decisions: Optional[List[str]] = None,
        importance: int = 1,
    ) -> None:
        """Create and enqueue a background `MEMORY_SUMMARY` audit record."""
        record = DataverseAuditRecord(
            record_type=RECORD_TYPE_MEMORY_SUMMARY,
            user_object_id=user_object_id,
            user_email=user_email,
            conversation_id=conversation_id,
            memory_eligible=True,
            memory_summary=summary,
            memory_topics=topics,
            memory_importance=importance,
            content_classification="INTERNAL_MEMORY",
            message_summary=f"Memory summary for {', '.join(topics) if topics else 'general conversation'}",
        )
        self.bg_logger.enqueue(record)


_global_memory_service = MemoryService()


def get_memory_service() -> MemoryService:
    return _global_memory_service
