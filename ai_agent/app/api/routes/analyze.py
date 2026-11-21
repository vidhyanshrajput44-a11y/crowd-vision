"""Real-time crowd analytics ingestion and zone analysis route handlers."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.middleware.auth import verify_api_key
from app.core.event_context import EventContextManager
from app.core.orchestrator import AgentOrchestrator
from app.dependencies import (
    get_event_manager,
    get_ingestion,
    get_metrics,
    get_orchestrator,
)
from app.monitoring.logger import get_logger
from app.monitoring.metrics import MetricsCollector
from app.schemas.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    EventCreate,
    EventResponse,
    ZoneAnalysisResponse,
)
from app.services.ingestion import IngestionService

logger = get_logger("routes.analyze")
router = APIRouter(prefix="/api/v1/agent", tags=["analytics"])


@router.post("/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def register_event(
    request: EventCreate,
    event_manager: EventContextManager = Depends(get_event_manager),
    _: str = Depends(verify_api_key),
) -> EventResponse:
    """Register or update an event and its venue zone configuration."""
    ctx = event_manager.register_event(
        event_id=request.event_id,
        event_name=request.event_name,
        venue=request.venue,
    )
    return EventResponse(
        event_id=ctx.event_id,
        event_name=ctx.event_name,
        venue_id=ctx.venue.venue_id,
        status="active",
        created_at=datetime.now(timezone.utc),
        zones_count=len(ctx.venue.zones),
    )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_crowd_data(
    request: AnalyzeRequest,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    ingestion: IngestionService = Depends(get_ingestion),
    metrics: MetricsCollector = Depends(get_metrics),
    _: str = Depends(verify_api_key),
) -> AnalyzeResponse:
    """Ingest, validate, and analyze batch crowd measurements via the intelligence pipeline."""
    start_ts = time.monotonic()
    metrics.increment("requests_analyze_total")

    if not request.data:
        return AnalyzeResponse(
            accepted=0,
            duplicates_skipped=0,
            results=None,
            processing_time_ms=0.0,
        )

    # Ingest batch through deduplication and backpressure
    accepted_count, dup_count, rejected_count = await ingestion.ingest_batch(request.data)

    # If any were rejected due to backpressure under extreme load
    if rejected_count > 0:
        logger.warning("Backpressure applied to batch ingestion", rejected=rejected_count)

    # Drain and process all available batch items through the intelligence pipeline
    batch_items = await ingestion.get_batch(max_batch_size=len(request.data) + 10, timeout_seconds=0.05)
    if not batch_items and request.data:
        # If queue had immediate items, process request items directly
        batch_items = [d for d in request.data if d.people_count >= 0]

    analysis_result = await orchestrator.process_batch(batch_items)

    total_latency_ms = (time.monotonic() - start_ts) * 1000.0
    metrics.observe("analyze_latency_ms", total_latency_ms)

    return AnalyzeResponse(
        accepted=accepted_count,
        duplicates_skipped=dup_count,
        results=analysis_result,
        processing_time_ms=round(total_latency_ms, 2),
    )


@router.get("/zones/{zone_id}/analysis", response_model=ZoneAnalysisResponse)
async def get_zone_analysis(
    zone_id: str,
    event_id: str,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    _: str = Depends(verify_api_key),
) -> ZoneAnalysisResponse:
    """Retrieve comprehensive multi-dimensional analytical view for a single zone."""
    try:
        return await orchestrator.get_zone_analysis(event_id=event_id, zone_id=zone_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
