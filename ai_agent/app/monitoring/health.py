"""Health check evaluators for system and dependencies."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.agent_state import AgentState
from app.database.session import is_database_available
from app.monitoring.logger import get_logger
from app.schemas.models import HealthResponse
from app.services.cache import CacheService

logger = get_logger("monitoring.health")


class HealthChecker:
    """Verifies operational health of database, cache, agent orchestrator, and external providers."""

    def __init__(self, cache_service: CacheService, agent_state: AgentState) -> None:
        self.cache_service = cache_service
        self.agent_state = agent_state

    async def check_health(self) -> HealthResponse:
        """Run diagnostic checks against all internal and external dependencies."""
        checks: dict[str, str] = {}

        # 1. Database check
        checks["database"] = "healthy" if is_database_available() else "degraded (in-memory mode)"

        # 2. Cache check
        if self.cache_service.is_redis_available:
            checks["cache"] = "healthy (redis)"
        else:
            checks["cache"] = "healthy (in-memory fallback)"

        # 3. Agent runtime check
        checks["agent_core"] = "healthy" if self.agent_state.uptime_seconds >= 0 else "unhealthy"

        # 4. LLM provider check
        checks["llm_provider"] = "connected" if self.agent_state.llm_available else "offline (deterministic fallback active)"

        overall_status = "healthy"
        if checks["agent_core"] == "unhealthy":
            overall_status = "unhealthy"

        return HealthResponse(
            status=overall_status,
            checks=checks,
            timestamp=datetime.now(timezone.utc),
        )
