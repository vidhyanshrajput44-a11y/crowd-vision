"""High-throughput asynchronous ingestion service with bounded queues and backpressure."""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from app.monitoring.logger import get_logger
from app.schemas.models import CrowdDataInput

logger = get_logger("services.ingestion")


class IngestionService:
    """Validates incoming analytics, filters duplicates, and buffers them with backpressure."""

    def __init__(self, max_queue_size: int = 1000, dedup_window_seconds: float = 2.0) -> None:
        self._queue: asyncio.Queue[CrowdDataInput] = asyncio.Queue(maxsize=max_queue_size)
        self._dedup_window = dedup_window_seconds
        # key -> monotonic timestamp
        self._dedup_cache: dict[str, float] = {}
        self._stats = {
            "accepted": 0,
            "rejected_backpressure": 0,
            "duplicates_dropped": 0,
            "invalid_dropped": 0,
        }

    async def ingest(self, data: CrowdDataInput) -> tuple[bool, str]:
        """Validate, deduplicate, and enqueue a single analytical data point."""
        # 1. Validation
        if data.people_count < 0:
            self._stats["invalid_dropped"] += 1
            return False, "Negative people_count is invalid"

        # 2. Deduplication check
        dedup_key = data.message_id or f"{data.event_id}:{data.zone_id}:{data.timestamp.isoformat()}"
        now = time.monotonic()

        last_seen = self._dedup_cache.get(dedup_key)
        if last_seen and (now - last_seen) < self._dedup_window:
            self._stats["duplicates_dropped"] += 1
            return False, "Duplicate message suppressed"

        self._dedup_cache[dedup_key] = now
        self._prune_dedup_cache(now)

        # 3. Enqueue with backpressure check
        try:
            self._queue.put_nowait(data)
            self._stats["accepted"] += 1
            return True, "Accepted"
        except asyncio.QueueFull:
            self._stats["rejected_backpressure"] += 1
            logger.warning(
                "Ingestion queue full, applying backpressure",
                queue_depth=self._queue.qsize(),
                zone_id=data.zone_id,
            )
            return False, "Queue backlog exceeded safe threshold"

    async def ingest_batch(self, items: list[CrowdDataInput]) -> tuple[int, int, int]:
        """Ingest multiple items. Returns (accepted, duplicates, rejected)."""
        accepted = 0
        duplicates = 0
        rejected = 0

        for item in items:
            ok, reason = await self.ingest(item)
            if ok:
                accepted += 1
            elif "Duplicate" in reason:
                duplicates += 1
            else:
                rejected += 1

        return accepted, duplicates, rejected

    async def get_batch(self, max_batch_size: int = 20, timeout_seconds: float = 0.5) -> list[CrowdDataInput]:
        """Retrieve a batch of items from the queue for processing."""
        items: list[CrowdDataInput] = []

        # Wait for first item
        try:
            first_item = await asyncio.wait_for(self._queue.get(), timeout=timeout_seconds)
            items.append(first_item)
            self._queue.task_done()
        except asyncio.TimeoutError:
            return items

        # Drain additional available items up to max_batch_size without waiting
        while len(items) < max_batch_size:
            try:
                item = self._queue.get_nowait()
                items.append(item)
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break

        return items

    def _prune_dedup_cache(self, now: float) -> None:
        """Evict stale deduplication keys."""
        if len(self._dedup_cache) > 2000:
            stale_keys = [k for k, ts in self._dedup_cache.items() if (now - ts) > self._dedup_window]
            for k in stale_keys:
                del self._dedup_cache[k]

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)
