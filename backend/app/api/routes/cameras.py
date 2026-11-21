"""Camera source configuration endpoints."""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Camera, Event
from app.database.session import get_db
from app.schemas.api_schemas import CameraCreateRequest, CameraResponse, CameraUpdateRequest

router = APIRouter()


@router.get("", response_model=list[CameraResponse])
async def list_cameras(
    db: Annotated[AsyncSession, Depends(get_db)],
    event_id: Optional[str] = Query(None),
):
    stmt = select(Camera).order_by(desc(Camera.created_at))
    if event_id:
        stmt = stmt.where(Camera.event_id == event_id)
    cameras = (await db.execute(stmt)).scalars().all()
    return [CameraResponse.model_validate(c) for c in cameras]


@router.post("", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def create_camera(
    payload: CameraCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    event = await db.get(Event, payload.event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    camera = Camera(
        event_id=payload.event_id,
        name=payload.name,
        location=payload.location,
        input_type=payload.input_type,
        perspective=payload.perspective,
        is_moving_camera=payload.is_moving_camera,
        layout_id=payload.layout_id,
        calibration_data=payload.calibration_data,
        source_uri=payload.source_uri,
        status="IDLE",
        associated_zone_ids=payload.associated_zone_ids,
        config=payload.config,
    )
    db.add(camera)
    await db.commit()
    await db.refresh(camera)
    return CameraResponse.model_validate(camera)


@router.patch("/{camera_id}", response_model=CameraResponse)
async def update_camera(
    camera_id: str,
    payload: CameraUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    camera = await db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(camera, k, v)

    await db.commit()
    await db.refresh(camera)
    return CameraResponse.model_validate(camera)


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(
    camera_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    camera = await db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    await db.delete(camera)
    await db.commit()
    return None
