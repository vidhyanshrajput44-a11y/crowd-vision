"""Camera and venue spatial homography calibration endpoints."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Optional

import cv2
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.zone_mapper import ZoneMapper
from app.config import get_settings
from app.cv.detector import assess_footage_perspective
from app.database.models import VideoFile
from app.database.session import get_db
from app.schemas.api_schemas import (
    CameraCalibrationRequest,
    HomographyCalibrationRequest,
    PerspectiveAssessmentRequest,
    PerspectiveAssessmentResponse,
)

router = APIRouter(prefix="/calibration", tags=["calibration"])


@router.post("/perspective/assess", response_model=PerspectiveAssessmentResponse)
async def assess_perspective(
    payload: PerspectiveAssessmentRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    video = await db.get(VideoFile, payload.video_file_id)
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video file not found")

    video_path = video.stored_path
    if not os.path.exists(video_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video file missing on disk")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not open video file")

    target_frame = payload.frame_index or 0
    if target_frame > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, float(target_frame))

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not extract video frame")

    assessment = assess_footage_perspective(frame)
    return PerspectiveAssessmentResponse(**assessment)


@router.post("/homography")
@router.post("/homography/calculate", include_in_schema=False)
async def calculate_homography(
    payload: HomographyCalibrationRequest,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    if len(payload.image_points) < 4 or len(payload.venue_points) < 4:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Homography calibration requires at least 4 corresponding point pairs.",
        )
    try:
        matrix = ZoneMapper.compute_homography(payload.image_points, payload.venue_points)
        return {
            "success": True,
            "homography_matrix": matrix,
            "homography": matrix,
            "perspective": payload.perspective or "FIXED_CCTV",
            "scale_factor_m_per_px": payload.scale_factor_m_per_px,
            "points_count": len(payload.image_points),
            "status": "CALIBRATED",
        }
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed computing homography matrix: {exc}")


@router.get("/frame/{video_id}")
async def get_calibration_frame(
    video_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    frame_index: int = Query(0, ge=0),
):
    video = await db.get(VideoFile, video_id)
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video file not found")

    video_path = video.stored_path
    if not os.path.exists(video_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video file missing on disk")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not open video")

    cap.set(cv2.CAP_PROP_POS_FRAMES, float(frame_index))
    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to grab frame")

    success, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Frame encode failed")

    return Response(content=buffer.tobytes(), media_type="image/jpeg")
