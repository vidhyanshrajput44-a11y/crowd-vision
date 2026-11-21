"""Event-scoped context manager enforcing strict isolation between simultaneous events."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.monitoring.logger import get_logger
from app.schemas.models import (
    CrowdDataInput,
    VenueConfig,
    ZoneConfig,
    ZoneRiskAssessment,
)

logger = get_logger("core.event_context")


class EventContext:
    """Encapsulates all transient and configuration state for a single active event."""

    def __init__(self, event_id: str, event_name: str, venue: VenueConfig) -> None:
        self.event_id = event_id
        self.event_name = event_name
        self.venue = venue

        # zone_id -> deque of recent CrowdDataInputs (bounded)
        self._zone_history: dict[str, deque[CrowdDataInput]] = {
            z.zone_id: deque(maxlen=120) for z in venue.zones
        }
        # zone_id -> latest CrowdDataInput
        self._latest_data: dict[str, CrowdDataInput] = {}
        # zone_id -> latest ZoneRiskAssessment
        self._latest_assessments: dict[str, ZoneRiskAssessment] = {}

        self._feedback_records: list[dict[str, Any]] = []
        self._created_at = datetime.now(timezone.utc)
        self._last_analysis_at: Optional[datetime] = None

    def record_data(self, data: CrowdDataInput) -> None:
        """Record latest data point in zone history."""
        if data.zone_id not in self._zone_history:
            self._zone_history[data.zone_id] = deque(maxlen=120)
        self._zone_history[data.zone_id].append(data)
        self._latest_data[data.zone_id] = data
        self._last_analysis_at = datetime.now(timezone.utc)

    def record_assessment(self, assessment: ZoneRiskAssessment) -> None:
        """Store most recent confirmed risk assessment for a zone."""
        self._latest_assessments[assessment.zone_id] = assessment

    def get_latest_data(self, zone_id: str) -> Optional[CrowdDataInput]:
        """Fetch latest raw data for a specific zone."""
        return self._latest_data.get(zone_id)

    def get_all_latest(self) -> dict[str, CrowdDataInput]:
        """Return latest data dictionary across all zones."""
        return dict(self._latest_data)

    def get_latest_assessment(self, zone_id: str) -> Optional[ZoneRiskAssessment]:
        """Fetch latest risk assessment for a specific zone."""
        return self._latest_assessments.get(zone_id)

    def get_all_latest_assessments(self) -> dict[str, ZoneRiskAssessment]:
        """Return all current risk assessments."""
        return dict(self._latest_assessments)

    def get_zone_config(self, zone_id: str) -> Optional[ZoneConfig]:
        """Look up zone configuration in the venue layout."""
        return self.venue.get_zone(zone_id)

    def get_zone_history(self, zone_id: str, minutes: int = 15) -> list[CrowdDataInput]:
        """Retrieve recent historical data within the specified time window."""
        history = self._zone_history.get(zone_id)
        if not history:
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return [
            d for d in history
            if (d.timestamp.tzinfo is not None and d.timestamp >= cutoff)
            or (d.timestamp.tzinfo is None and d.timestamp.replace(tzinfo=timezone.utc) >= cutoff)
        ]

    def record_feedback(self, feedback: dict[str, Any]) -> None:
        """Store operator feedback."""
        self._feedback_records.append(feedback)

    @property
    def is_data_stale(self) -> bool:
        """Data is deemed stale if no analytics updates have arrived within 60 seconds."""
        if self._last_analysis_at is None:
            return True
        elapsed = (datetime.now(timezone.utc) - self._last_analysis_at).total_seconds()
        return elapsed > 60.0

    @property
    def seconds_since_last_update(self) -> float:
        """Elapsed seconds since last incoming analytics snapshot."""
        if self._last_analysis_at is None:
            return float("inf")
        return (datetime.now(timezone.utc) - self._last_analysis_at).total_seconds()

    def build_llm_context(self, target_zone_id: Optional[str] = None, max_items: int = 50) -> dict[str, Any]:
        """Compile a bounded, structured context dictionary for LLM reasoning."""
        zones_summary = []
        for zone in self.venue.zones:
            latest = self._latest_data.get(zone.zone_id)
            assessment = self._latest_assessments.get(zone.zone_id)

            occ_pct = ((latest.people_count / zone.capacity) * 100.0) if latest and zone.capacity > 0 else 0.0

            zones_summary.append({
                "zone_id": zone.zone_id,
                "zone_name": zone.zone_name,
                "capacity": zone.capacity,
                "current_people_count": latest.people_count if latest else 0,
                "occupancy_pct": round(occ_pct, 1),
                "risk_level": assessment.risk_level.value if assessment else "NORMAL",
                "inflow_rate": latest.inflow_rate if latest else None,
                "outflow_rate": latest.outflow_rate if latest else None,
                "explanation": assessment.explanation if assessment else None,
            })

        return {
            "event_id": self.event_id,
            "event_name": self.event_name,
            "venue_id": self.venue.venue_id,
            "venue_name": self.venue.venue_name,
            "is_data_stale": self.is_data_stale,
            "seconds_since_last_update": round(self.seconds_since_last_update, 1),
            "zones": zones_summary[:max_items],
            "total_venue_capacity": self.venue.total_capacity,
        }


class EventContextManager:
    """Registry maintaining active event contexts with strict isolation guarantees."""

    def __init__(self) -> None:
        self._contexts: dict[str, EventContext] = {}

    def register_event(self, event_id: str, event_name: str, venue: VenueConfig) -> EventContext:
        """Register a new event context or update existing venue layout."""
        if event_id in self._contexts:
            ctx = self._contexts[event_id]
            ctx.event_name = event_name
            ctx.venue = venue
            logger.info("Updated existing event context", event_id=event_id)
            return ctx

        ctx = EventContext(event_id, event_name, venue)
        self._contexts[event_id] = ctx
        logger.info("Registered new event context", event_id=event_id, venue_id=venue.venue_id)
        return ctx

    def get_context(self, event_id: str) -> Optional[EventContext]:
        """Fetch event context by event_id."""
        return self._contexts.get(event_id)

    def get_or_raise(self, event_id: str) -> EventContext:
        """Fetch event context or raise ValueError if unregistered."""
        ctx = self._contexts.get(event_id)
        if not ctx:
            raise ValueError(f"Event ID '{event_id}' is not registered with the AI agent service")
        return ctx

    def unregister_event(self, event_id: str) -> bool:
        """Remove event context from active registry."""
        if event_id in self._contexts:
            del self._contexts[event_id]
            logger.info("Unregistered event context", event_id=event_id)
            return True
        return False

    @property
    def active_event_ids(self) -> list[str]:
        return list(self._contexts.keys())

    @property
    def total_monitored_zones(self) -> int:
        return sum(len(ctx.venue.zones) for ctx in self._contexts.values())
