"""Global agent operational state and telemetry tracker."""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

from app.schemas.models import AgentStatus


class AgentState:
    """Tracks operational statistics, uptime, error history, and subsystem availability."""

    def __init__(self) -> None:
        self._start_time = datetime.now(timezone.utc)
        self._start_monotonic = time.monotonic()
        self._total_analyses: int = 0
        self._total_alerts_emitted: int = 0
        self._last_analysis_at: Optional[datetime] = None
        self._recent_errors: deque[dict[str, Any]] = deque(maxlen=100)

        # Subsystem availability flags
        self.llm_available: bool = False
        self.redis_available: bool = False
        self.database_available: bool = False

    def record_analysis_cycle(self, items_processed: int) -> None:
        """Record completed analysis cycle."""
        self._total_analyses += items_processed
        self._last_analysis_at = datetime.now(timezone.utc)

    def record_alert(self) -> None:
        """Increment alert counter."""
        self._total_alerts_emitted += 1

    def record_error(self, message: str, exc_type: Optional[str] = None) -> None:
        """Log error to recent errors buffer."""
        self._recent_errors.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": message,
            "type": exc_type,
        })

    @property
    def uptime_seconds(self) -> float:
        """Return running duration in seconds."""
        return time.monotonic() - self._start_monotonic

    def get_status_model(
        self,
        active_events: int = 0,
        zones_monitored: int = 0,
        alerts_active: int = 0,
        queue_depth: int = 0,
    ) -> AgentStatus:
        """Generate AgentStatus response model."""
        return AgentStatus(
            status="operational",
            uptime_seconds=round(self.uptime_seconds, 2),
            events_active=active_events,
            zones_monitored=zones_monitored,
            alerts_active=alerts_active,
            queue_depth=queue_depth,
            llm_available=self.llm_available,
            redis_available=self.redis_available,
            database_available=self.database_available,
            last_analysis_at=self._last_analysis_at,
            version="1.0.0",
        )
