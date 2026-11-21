"""Alert escalation manager for unacknowledged critical and high alerts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.monitoring.logger import get_logger
from app.schemas.models import AlertPriority, AlertResponse, AlertState

logger = get_logger("alerts.escalation")


class EscalationManager:
    """Evaluates unacknowledged alerts and promotes their priority level when neglected."""

    def __init__(self, escalation_timeout_seconds: int = 300) -> None:
        self._escalation_timeout = escalation_timeout_seconds

    def check_escalation(self, alert: AlertResponse, now: Optional[datetime] = None) -> Optional[AlertResponse]:
        """Check if an unacknowledged alert requires priority escalation."""
        if alert.state != AlertState.NEW:
            return None

        # Already at maximum severity
        if alert.priority == AlertPriority.CRITICAL:
            return None

        if now is None:
            now = datetime.now(timezone.utc)

        # Ensure timezone-aware comparison
        alert_time = alert.created_at
        if alert_time.tzinfo is None:
            alert_time = alert_time.replace(tzinfo=timezone.utc)

        elapsed = (now - alert_time).total_seconds()
        if elapsed < self._escalation_timeout:
            return None

        # Determine escalated priority
        escalation_ladder = {
            AlertPriority.LOW: AlertPriority.MEDIUM,
            AlertPriority.MEDIUM: AlertPriority.HIGH,
            AlertPriority.HIGH: AlertPriority.CRITICAL,
        }
        new_priority = escalation_ladder.get(alert.priority, alert.priority)

        logger.warning(
            "Escalating unacknowledged alert",
            alert_id=alert.id,
            zone_id=alert.zone_id,
            old_priority=alert.priority.value,
            new_priority=new_priority.value,
            unacknowledged_seconds=elapsed,
        )

        alert.priority = new_priority
        alert.escalation_count += 1
        alert.updated_at = now
        return alert
