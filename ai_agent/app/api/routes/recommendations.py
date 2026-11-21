"""Operational recommendation retrieval route handlers."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.middleware.auth import verify_api_key
from app.core.orchestrator import AgentOrchestrator
from app.dependencies import get_orchestrator
from app.schemas.models import RecommendationListResponse

router = APIRouter(prefix="/api/v1/agent", tags=["recommendations"])


@router.get("/recommendations", response_model=RecommendationListResponse)
async def list_recommendations(
    event_id: str,
    zone_id: Optional[str] = None,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    _: str = Depends(verify_api_key),
) -> RecommendationListResponse:
    """Retrieve active context-aware operational recommendations for an event."""
    recs = orchestrator.get_recommendations(event_id)
    if zone_id:
        recs = [r for r in recs if r.affected_zone == zone_id]

    return RecommendationListResponse(
        recommendations=recs,
        total=len(recs),
    )
