"""Single image analysis upload and retrieval routes."""
from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.models import SingleImageAnalysis
from app.database.session import get_db
from app.schemas.api_schemas import SingleImageAnalysisResponse
from app.services.image_analyzer import SingleImageAnalyzer
from app.services.video_processor import get_shared_detector

router = APIRouter(prefix="/images", tags=["images"])


@router.post("/analyze", response_model=SingleImageAnalysisResponse)
async def analyze_single_image(
    file: UploadFile = File(...),
    event_id: Optional[str] = Form(None),
    venue_id: Optional[str] = Form(None),
    layout_id: Optional[str] = Form(None),
    camera_perspective: Optional[str] = Form(None),
):
    allowed_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    raw_name = Path(file.filename or "image.jpg").name
    filename = re.sub(r"[^\w\.-]", "_", raw_name)
    ext = Path(filename).suffix.lower()
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image extension '{ext}'. Allowed: {', '.join(allowed_exts)}",
        )

    settings = get_settings()
    max_bytes = getattr(settings, "max_image_size_mb", 25) * 1024 * 1024
    image_bytes = await file.read()
    if len(image_bytes) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded image is empty")
    if len(image_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds maximum upload limit of {settings.max_image_size_mb} MB",
        )

    detector = get_shared_detector()
    analyzer = SingleImageAnalyzer(detector=detector)

    try:
        result = await analyzer.analyze_image(
            image_bytes=image_bytes,
            filename=filename,
            event_id=event_id,
            venue_id=venue_id,
            layout_id=layout_id,
            camera_perspective=camera_perspective,
        )
        return SingleImageAnalysisResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/{analysis_id}", response_model=SingleImageAnalysisResponse)
async def get_single_image_analysis(
    analysis_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    analysis = await db.get(SingleImageAnalysis, analysis_id)
    if not analysis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis record not found")
    return SingleImageAnalysisResponse.model_validate(analysis)


@router.get("", response_model=list[SingleImageAnalysisResponse])
async def list_single_image_analyses(
    db: Annotated[AsyncSession, Depends(get_db)],
    event_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    stmt = select(SingleImageAnalysis).order_by(desc(SingleImageAnalysis.created_at))
    if event_id:
        stmt = stmt.where(SingleImageAnalysis.event_id == event_id)
    stmt = stmt.limit(limit)

    records = (await db.execute(stmt)).scalars().all()
    return [SingleImageAnalysisResponse.model_validate(r) for r in records]
