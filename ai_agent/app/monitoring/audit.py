"""Audit logging service for operational and security traceability."""

from __future__ import annotations

import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

from app.monitoring.logger import get_logger

logger = get_logger("monitoring.audit")


class AuditService:
    """Records chronological, immutable audit entries for system actions and operator commands."""

    def __init__(self, max_records: int = 5000) -> None:
        self._records: deque[dict[str, Any]] = deque(maxlen=max_records)

    async def record(
        self,
        action: str,
        entity_type: str,
        entity_id: str,
        event_id: Optional[str] = None,
        performed_by: Optional[str] = None,
        old_value: Optional[dict[str, Any]] = None,
        new_value: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Record and log an audit event."""
        entry = {
            "id": str(uuid.uuid4()),
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "event_id": event_id,
            "performed_by": performed_by or "system",
            "old_value": old_value,
            "new_value": new_value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._records.append(entry)
        logger.info(
            "Audit event",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=performed_by,
        )
        return entry

    def get_recent(self, limit: int = 100, event_id: Optional[str] = None) -> list[dict[str, Any]]:
        """Fetch recent audit records."""
        if event_id:
            filtered = [r for r in self._records if r.get("event_id") == event_id]
            return filtered[-limit:]
        return list(self._records)[-limit:]
