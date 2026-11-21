"""Health and operational telemetry route handlers."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.agent_state import AgentState
from app.core.event_context import EventContextManager
from app.dependencies import (
    get_agent_state,
    get_alert_manager,
    get_event_manager,
    get_health_checker,
    get_ingestion,
    get_metrics,
)
from app.monitoring.health import HealthChecker
from app.monitoring.metrics import MetricsCollector
from app.schemas.models import AgentStatus, HealthResponse
from app.services.ingestion import IngestionService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def check_health(
    health_checker: HealthChecker = Depends(get_health_checker),
) -> HealthResponse:
    """Diagnostic health check verifying internal subsystems and dependency connectivity."""
    return await health_checker.check_health()


@router.get("/api/v1/agent/status", response_model=AgentStatus)
async def get_agent_status(
    agent_state: AgentState = Depends(get_agent_state),
    event_manager: EventContextManager = Depends(get_event_manager),
    ingestion: IngestionService = Depends(get_ingestion),
    alert_mgr = Depends(get_alert_manager),
) -> AgentStatus:
    """Return operational state, uptime, monitored event counts, and resource backlogs."""
    return agent_state.get_status_model(
        active_events=len(event_manager.active_event_ids),
        zones_monitored=event_manager.total_monitored_zones,
        alerts_active=alert_mgr.active_count,
        queue_depth=ingestion.queue_depth,
    )


@router.get("/api/v1/agent/metrics")
async def get_metrics_summary(
    metrics: MetricsCollector = Depends(get_metrics),
) -> dict:
    """Return internal latency and throughput metrics (p50, p95, p99)."""
    return metrics.get_summary()
