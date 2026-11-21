"""Recommendation review and retrieval endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.database.models import Recommendation, User
from app.database.session import get_db
from app.schemas.api_schemas import RecommendationResponse, RecommendationReviewRequest

router = APIRouter()


@router.get("", response_model=list[RecommendationResponse])
async def list_recommendations(
    db: Annotated[AsyncSession, Depends(get_db)],
    event_id: Optional[str] = Query(None),
    review_status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    stmt = select(Recommendation).order_by(desc(Recommendation.created_at))
    if event_id:
        stmt = stmt.where(Recommendation.event_id == event_id)
    if review_status:
        stmt = stmt.where(Recommendation.review_status == review_status.upper())
    if priority:
        stmt = stmt.where(Recommendation.priority == priority.upper())
    stmt = stmt.offset(offset).limit(limit)

    recs = (await db.execute(stmt)).scalars().all()
    return [RecommendationResponse.model_validate(r) for r in recs]


@router.post("/{rec_id}/review", response_model=RecommendationResponse)
async def review_recommendation(
    rec_id: str,
    payload: RecommendationReviewRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    rec = await db.get(Recommendation, rec_id)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")

    rec.review_status = payload.review_status.upper()
    rec.reviewed_by = current_user.email
    rec.reviewed_at = datetime.utcnow()
    if payload.review_note:
        rec.review_note = payload.review_note

    await db.commit()
    await db.refresh(rec)
    return RecommendationResponse.model_validate(rec)
