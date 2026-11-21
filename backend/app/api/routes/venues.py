"""Venue and physical zone configuration routes."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Optional
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.analytics.zone_mapper import ZoneMapper, validate_polygon_geometry
from app.config import get_settings
from app.database.models import Venue, Zone, ZoneCapacity
from app.database.session import get_db
from app.schemas.api_schemas import (
    HomographyCalibrationRequest,
    VenueCreateRequest,
    VenueResponse,
    VenueUpdateRequest,
    ZoneCreateRequest,
    ZoneResponse,
    ZoneUpdateRequest,
)

router = APIRouter()


@router.get("", response_model=list[VenueResponse])
async def list_venues(db: Annotated[AsyncSession, Depends(get_db)]):
    stmt = select(Venue).options(selectinload(Venue.zones).selectinload(Zone.capacity))
    venues = (await db.execute(stmt)).scalars().all()
    return [VenueResponse.model_validate(v) for v in venues]


@router.get("/{venue_id}", response_model=VenueResponse)
async def get_venue(
    venue_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    stmt = select(Venue).options(selectinload(Venue.zones).selectinload(Zone.capacity)).where(Venue.id == venue_id)
    venue = (await db.execute(stmt)).scalar_one_or_none()
    if not venue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")
    return VenueResponse.model_validate(venue)


@router.post("", response_model=VenueResponse, status_code=status.HTTP_201_CREATED)
async def create_venue(
    payload: VenueCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    venue = Venue(
        name=payload.name,
        location=payload.location,
        total_capacity=payload.total_capacity,
    )
    db.add(venue)
    await db.commit()
    await db.refresh(venue)
    # Reload with empty zones
    return VenueResponse(
        id=venue.id,
        name=venue.name,
        location=venue.location,
        total_capacity=venue.total_capacity,
        floorplan_url=venue.floorplan_url,
        is_calibrated=venue.is_calibrated,
        zones=[],
        created_at=venue.created_at,
    )


@router.patch("/{venue_id}", response_model=VenueResponse)
async def update_venue(
    venue_id: str,
    payload: VenueUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    venue = await db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")

    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(venue, k, v)

    await db.commit()
    await db.refresh(venue)
    stmt = select(Venue).options(selectinload(Venue.zones).selectinload(Zone.capacity)).where(Venue.id == venue_id)
    venue = (await db.execute(stmt)).scalar_one()
    return VenueResponse.model_validate(venue)


@router.post("/{venue_id}/floorplan")
async def upload_floorplan(
    venue_id: str,
    file: UploadFile = File(...),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    venue = await db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")

    settings = get_settings()
    ext = Path(file.filename or "plan.png").suffix.lower()
    stored_name = f"{venue_id}_floorplan_{uuid.uuid4().hex[:8]}{ext}"
    dest = settings.floorplans_dir / stored_name
    settings.floorplans_dir.mkdir(parents=True, exist_ok=True)

    contents = await file.read()
    with open(dest, "wb") as f:
        f.write(contents)

    venue.floorplan_url = f"/uploads/floorplans/{stored_name}"
    await db.commit()
    return {"floorplan_url": venue.floorplan_url}


@router.post("/{venue_id}/calibrate")
async def calibrate_homography(
    venue_id: str,
    payload: HomographyCalibrationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    venue = await db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")

    try:
        matrix = ZoneMapper.compute_homography(payload.image_points, payload.venue_points)
        venue.calibration_homography = matrix
        venue.is_calibrated = True
        await db.commit()
        return {"homography": matrix, "is_calibrated": True}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/{venue_id}/zones", response_model=ZoneResponse, status_code=status.HTTP_201_CREATED)
async def create_zone(
    venue_id: str,
    payload: ZoneCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    venue = await db.get(Venue, venue_id)
    if not venue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")

    is_valid, errs = validate_polygon_geometry(payload.polygon_points)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid zone geometry: {'; '.join(errs)}",
        )

    zone = Zone(
        venue_id=venue_id,
        name=payload.name,
        zone_type=payload.zone_type.upper(),
        polygon_points=payload.polygon_points,
        color=payload.color,
        is_entry=payload.is_entry,
        is_exit=payload.is_exit,
        is_emergency_exit=payload.is_emergency_exit,
        adjacent_zone_ids=payload.adjacent_zone_ids or [],
    )
    db.add(zone)
    await db.flush()

    capacity = ZoneCapacity(
        zone_id=zone.id,
        max_capacity=payload.max_capacity,
        area_sqm=payload.area_sqm,
        is_physically_calibrated=payload.is_physically_calibrated,
        threshold_low=payload.threshold_low,
        threshold_moderate=payload.threshold_moderate,
        threshold_high=payload.threshold_high,
        threshold_critical=payload.threshold_critical,
        density_moderate=payload.density_moderate,
        density_high=payload.density_high,
        density_critical=payload.density_critical,
    )
    db.add(capacity)
    await db.commit()

    stmt = select(Zone).options(selectinload(Zone.capacity)).where(Zone.id == zone.id)
    zone = (await db.execute(stmt)).scalar_one()
    return ZoneResponse.model_validate(zone)


@router.patch("/{venue_id}/zones/{zone_id}", response_model=ZoneResponse)
async def update_zone(
    venue_id: str,
    zone_id: str,
    payload: ZoneUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    stmt = select(Zone).options(selectinload(Zone.capacity)).where(Zone.id == zone_id, Zone.venue_id == venue_id)
    zone = (await db.execute(stmt)).scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")

    data = payload.model_dump(exclude_unset=True)

    if "polygon_points" in data and data["polygon_points"]:
        is_valid, errs = validate_polygon_geometry(data["polygon_points"])
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid zone geometry: {'; '.join(errs)}",
            )

    zone_fields = {"name", "zone_type", "polygon_points", "color", "is_entry", "is_exit", "is_emergency_exit", "adjacent_zone_ids"}
    for f in zone_fields:
        if f in data:
            val = data[f]
            if f == "zone_type" and val:
                val = val.upper()
            setattr(zone, f, val)

    cap_fields = {"max_capacity", "area_sqm", "is_physically_calibrated", "threshold_low", "threshold_moderate", "threshold_high", "threshold_critical", "density_moderate", "density_high", "density_critical"}
    if zone.capacity:
        for f in cap_fields:
            if f in data:
                setattr(zone.capacity, f, data[f])

    await db.commit()
    await db.refresh(zone)
    return ZoneResponse.model_validate(zone)


@router.delete("/{venue_id}/zones/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_zone(
    venue_id: str,
    zone_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    stmt = select(Zone).where(Zone.id == zone_id, Zone.venue_id == venue_id)
    zone = (await db.execute(stmt)).scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    await db.delete(zone)
    await db.commit()
    return None
