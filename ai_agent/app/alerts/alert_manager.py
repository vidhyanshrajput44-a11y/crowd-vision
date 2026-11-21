"""Full alert lifecycle management subsystem with deduplication, escalation, and audit trail."""

from __future__ import annotations

import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.alerts.alert_rules import DEFAULT_ALERT_RULES, AlertRule
from app.alerts.escalation import EscalationManager
from app.monitoring.logger import get_logger
from app.schemas.models import (
    AlertPriority,
    AlertResponse,
    AlertState,
    RiskLevel,
    ZoneConfig,
    ZoneRiskAssessment,
)

logger = get_logger("alerts.manager")


class AlertManager:
    """Manages alert creation, suppression, escalation, state transitions, and audit tracking."""

    def __init__(
        self,
        dedup_window_seconds: int = 60,
        escalation_timeout_seconds: int = 300,
        max_active: int = 500,
    ) -> None:
        self._dedup_window = timedelta(seconds=dedup_window_seconds)
        self._max_active = max_active
        self._escalation_manager = EscalationManager(escalation_timeout_seconds)

        # Primary storage: alert_id -> AlertResponse
        self._alerts: dict[str, AlertResponse] = {}

        # Indexes: event_id -> zone_id -> list of alert_ids
        self._event_zone_index: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

        # Deduplication cache: f"{event_id}:{zone_id}:{alert_type}" -> datetime
        self._dedup_cache: dict[str, datetime] = {}

        # Audit trail of state transitions
        self._history: deque[dict[str, Any]] = deque(maxlen=5000)

        # Subscribers for alert events (e.g. WebSocket notifications)
        self._change_callbacks: list[Callable[[AlertResponse, str], None]] = []

    def on_alert_change(self, callback: Callable[[AlertResponse, str], None]) -> None:
        """Register a callback for alert creation, escalation, or state change."""
        self._change_callbacks.append(callback)

    def _notify_callbacks(self, alert: AlertResponse, action: str) -> None:
        for cb in self._change_callbacks:
            try:
                cb(alert, action)
            except Exception as exc:
                logger.error("Error executing alert callback", error=str(exc))

    async def evaluate_and_create(
        self,
        risk_assessment: ZoneRiskAssessment,
        analysis: dict[str, Any],
        zone_config: ZoneConfig,
        event_id: str,
        rules: Optional[list[AlertRule]] = None,
    ) -> list[AlertResponse]:
        """Evaluate active rules against current assessment and generate non-duplicate alerts."""
        if len(self._alerts) >= self._max_active:
            logger.warning("Active alert limit reached; throttling new alert generation")
            return []

        active_rules = rules or DEFAULT_ALERT_RULES
        new_alerts: list[AlertResponse] = []
        now = datetime.now(timezone.utc)

        for rule in active_rules:
            if not rule.condition(risk_assessment, analysis, zone_config):
                continue

            dedup_key = f"{event_id}:{zone_config.zone_id}:{rule.alert_type}"
            last_alert_time = self._dedup_cache.get(dedup_key)
            cooldown = timedelta(seconds=rule.cooldown_seconds)

            # Suppress identical alert if within cooldown window
            if last_alert_time and (now - last_alert_time) < cooldown:
                continue

            priority = rule.priority_fn(risk_assessment, analysis)
            occ_pct = (risk_assessment.occupancy_ratio or 0.0) * 100.0

            title = rule.title_template.format(
                zone_name=zone_config.zone_name,
                risk_level=risk_assessment.risk_level.value,
            )
            description = rule.description_template.format(
                zone_name=zone_config.zone_name,
                occupancy=occ_pct,
                count=risk_assessment.people_count,
                capacity=zone_config.capacity,
                sudden_change=analysis.get("sudden_change", ""),
            )

            alert_id = str(uuid.uuid4())
            alert = AlertResponse(
                id=alert_id,
                event_id=event_id,
                zone_id=zone_config.zone_id,
                zone_name=zone_config.zone_name,
                alert_type=rule.alert_type,
                title=title,
                description=description,
                priority=priority,
                risk_level=risk_assessment.risk_level,
                state=AlertState.NEW,
                risk_factors=risk_assessment.risk_factors,
                created_at=now,
                metadata={
                    "occupancy_ratio": risk_assessment.occupancy_ratio,
                    "people_count": risk_assessment.people_count,
                    "net_flow": analysis.get("net_flow"),
                },
            )

            self._alerts[alert_id] = alert
            self._event_zone_index[event_id][zone_config.zone_id].append(alert_id)
            self._dedup_cache[dedup_key] = now
            new_alerts.append(alert)

            self._record_history(alert_id, "CREATED", None, AlertState.NEW, "system")
            self._notify_callbacks(alert, "created")

        return new_alerts

    async def acknowledge(self, alert_id: str, by: str) -> Optional[AlertResponse]:
        """Acknowledge an alert, pausing unacknowledged escalation timeouts."""
        alert = self._alerts.get(alert_id)
        if not alert:
            return None

        old_state = alert.state
        now = datetime.now(timezone.utc)
        alert.state = AlertState.ACKNOWLEDGED
        alert.acknowledged_at = now
        alert.acknowledged_by = by
        alert.updated_at = now

        self._record_history(alert_id, "ACKNOWLEDGED", old_state, alert.state, by)
        self._notify_callbacks(alert, "acknowledged")
        return alert

    async def resolve(self, alert_id: str, by: str, note: Optional[str] = None) -> Optional[AlertResponse]:
        """Resolve an active alert."""
        alert = self._alerts.get(alert_id)
        if not alert:
            return None

        old_state = alert.state
        now = datetime.now(timezone.utc)
        alert.state = AlertState.RESOLVED
        alert.resolved_at = now
        alert.resolved_by = by
        alert.resolution_note = note
        alert.updated_at = now

        self._record_history(alert_id, "RESOLVED", old_state, alert.state, by, note)
        self._notify_callbacks(alert, "resolved")
        return alert

    async def dismiss(self, alert_id: str, by: str) -> Optional[AlertResponse]:
        """Dismiss an alert as false positive or operationally irrelevant."""
        alert = self._alerts.get(alert_id)
        if not alert:
            return None

        old_state = alert.state
        now = datetime.now(timezone.utc)
        alert.state = AlertState.DISMISSED
        alert.updated_at = now

        self._record_history(alert_id, "DISMISSED", old_state, alert.state, by)
        self._notify_callbacks(alert, "dismissed")
        return alert

    async def check_escalations(self) -> list[AlertResponse]:
        """Inspect all active NEW alerts and apply escalation rules."""
        escalated: list[AlertResponse] = []
        now = datetime.now(timezone.utc)

        for alert in list(self._alerts.values()):
            updated = self._escalation_manager.check_escalation(alert, now)
            if updated:
                escalated.append(updated)
                self._record_history(
                    updated.id,
                    "ESCALATED",
                    updated.state,
                    updated.state,
                    "escalation_service",
                    f"Promoted to {updated.priority.value}",
                )
                self._notify_callbacks(updated, "escalated")

        return escalated

    def get_active_alerts(
        self,
        event_id: str,
        zone_id: Optional[str] = None,
        priority: Optional[AlertPriority] = None,
        state: Optional[AlertState] = None,
    ) -> list[AlertResponse]:
        """Retrieve matching active alerts sorted by priority severity and recency."""
        results = [
            a for a in self._alerts.values()
            if a.event_id == event_id
            and (zone_id is None or a.zone_id == zone_id)
            and (priority is None or a.priority == priority)
            and (state is None or a.state == state)
            and (state is not None or a.state in (AlertState.NEW, AlertState.ACKNOWLEDGED, AlertState.IN_PROGRESS))
        ]

        priority_order = {
            AlertPriority.CRITICAL: 4,
            AlertPriority.HIGH: 3,
            AlertPriority.MEDIUM: 2,
            AlertPriority.LOW: 1,
        }

        return sorted(
            results,
            key=lambda a: (priority_order.get(a.priority, 0), a.created_at),
            reverse=True,
        )

    def get_alert(self, alert_id: str) -> Optional[AlertResponse]:
        """Fetch alert by unique ID."""
        return self._alerts.get(alert_id)

    def _record_history(
        self,
        alert_id: str,
        action: str,
        old_state: Optional[AlertState],
        new_state: AlertState,
        actor: Optional[str],
        note: Optional[str] = None,
    ) -> None:
        """Append to in-memory audit log."""
        self._history.append({
            "alert_id": alert_id,
            "action": action,
            "old_state": old_state.value if old_state else None,
            "new_state": new_state.value,
            "actor": actor,
            "note": note,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_alert_history(self, alert_id: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        """Return audit history records."""
        if alert_id:
            records = [h for h in self._history if h["alert_id"] == alert_id]
        else:
            records = list(self._history)
        return records[-limit:]

    @property
    def active_count(self) -> int:
        """Count of unresolved active alerts."""
        return sum(
            1 for a in self._alerts.values()
            if a.state in (AlertState.NEW, AlertState.ACKNOWLEDGED, AlertState.IN_PROGRESS)
        )

    def clear(self) -> None:
        """Reset all alert states."""
        self._alerts.clear()
        self._event_zone_index.clear()
        self._dedup_cache.clear()
        self._history.clear()
