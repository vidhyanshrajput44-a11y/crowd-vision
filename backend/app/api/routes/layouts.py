"""Customizable venue layouts with interactive polygon zones and homography mapping."""
from __future__ import annotations

from typing import Annotated, Optional
import io
from pathlib import Path
import uuid
from PIL import Image as PILImage

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.zone_mapper import validate_polygon_geometry
from app.config import get_settings
from app.database.models import Venue, VenueLayout
from app.database.session import get_db
from app.schemas.api_schemas import (
    GeometryValidationRequest,
    GeometryValidationResponse,
    VenueLayoutCreateRequest,
    VenueLayoutResponse,
    VenueLayoutUpdateRequest,
)

router = APIRouter(prefix="/layouts", tags=["layouts"])


@router.get("", response_model=list[VenueLayoutResponse])
@router.get("/", response_model=list[VenueLayoutResponse], include_in_schema=False)
async def list_layouts(
    db: Annotated[AsyncSession, Depends(get_db)],
    venue_id: Optional[str] = Query(None),
    event_id: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
):
    stmt = select(VenueLayout).order_by(desc(VenueLayout.created_at))
    if venue_id:
        stmt = stmt.where(VenueLayout.venue_id == venue_id)
    if event_id:
        stmt = stmt.where(VenueLayout.event_id == event_id)
    if is_active is not None:
        stmt = stmt.where(VenueLayout.is_active == is_active)

    layouts = (await db.execute(stmt)).scalars().all()
    return [VenueLayoutResponse.model_validate(l) for l in layouts]


@router.get("/{layout_id}", response_model=VenueLayoutResponse)
async def get_layout(
    layout_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    layout = await db.get(VenueLayout, layout_id)
    if not layout:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Layout not found")
    return VenueLayoutResponse.model_validate(layout)


@router.post("", response_model=VenueLayoutResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=VenueLayoutResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_layout(
    payload: VenueLayoutCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    serialized_zones = []
    for z in payload.zones_data:
        z_dict = z.model_dump()
        # Guarantee both name/zone_name and id/zone_id are populated
        zid = z.id or z.zone_id or str(uuid.uuid4())
        zname = z.name or z.zone_name or zid
        cap = z.capacity or z.max_capacity or 100
        z_dict["id"] = zid
        z_dict["zone_id"] = zid
        z_dict["name"] = zname
        z_dict["zone_name"] = zname
        z_dict["capacity"] = int(cap)
        z_dict["max_capacity"] = int(cap)

        if "polygon_points" in z_dict and z_dict["polygon_points"]:
            is_valid, errs = validate_polygon_geometry(z_dict["polygon_points"])
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Zone '{z_dict.get('name')}' geometry error: {'; '.join(errs)}",
                )
        serialized_zones.append(z_dict)

    venue_id = payload.venue_id
    if not venue_id:
        first_venue = (await db.execute(select(Venue).limit(1))).scalar_one_or_none()
        venue_id = first_venue.id if first_venue else "venue-default"

    layout = VenueLayout(
        venue_id=venue_id,
        event_id=payload.event_id,
        name=payload.name,
        description=payload.description,
        version=1,
        is_active=True,
        scale_pixels_per_meter=payload.scale_pixels_per_meter or payload.scale_factor or 18.5,
        canvas_width=payload.canvas_width,
        canvas_height=payload.canvas_height,
        background_image_url=payload.background_image_url,
        zones_data=serialized_zones,
    )
    db.add(layout)
    await db.commit()
    await db.refresh(layout)
    return VenueLayoutResponse.model_validate(layout)


@router.patch("/{layout_id}", response_model=VenueLayoutResponse)
async def update_layout(
    layout_id: str,
    payload: VenueLayoutUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    layout = await db.get(VenueLayout, layout_id)
    if not layout:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Layout not found")

    data = payload.model_dump(exclude_unset=True)

    if "zones_data" in data and data["zones_data"] is not None:
        validated_zones = []
        for z in payload.zones_data:
            z_dict = z.model_dump()
            zid = z.id or getattr(z, "zone_id", None) or str(uuid.uuid4())
            zname = getattr(z, "name", None) or getattr(z, "zone_name", None) or zid
            cap = getattr(z, "capacity", None) or getattr(z, "max_capacity", None) or 100
            z_dict["id"] = zid
            z_dict["zone_id"] = zid
            z_dict["name"] = zname
            z_dict["zone_name"] = zname
            z_dict["capacity"] = int(cap)
            z_dict["max_capacity"] = int(cap)

            if "polygon_points" in z_dict and z_dict["polygon_points"]:
                is_valid, errs = validate_polygon_geometry(z_dict["polygon_points"])
                if not is_valid:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Zone '{z_dict.get('name')}' geometry error: {'; '.join(errs)}",
                    )
            validated_zones.append(z_dict)
        layout.zones_data = validated_zones

    fields = ["name", "description", "event_id", "venue_id", "is_active", "canvas_width", "canvas_height", "scale_pixels_per_meter", "background_image_url", "calibration_homography"]
    for f in fields:
        if f in data:
            setattr(layout, f, data[f])

    layout.version += 1
    await db.commit()
    await db.refresh(layout)
    return VenueLayoutResponse.model_validate(layout)


@router.post("/{layout_id}/duplicate", response_model=VenueLayoutResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_layout(
    layout_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    src = await db.get(VenueLayout, layout_id)
    if not src:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source layout not found")

    copy_layout = VenueLayout(
        venue_id=src.venue_id,
        event_id=src.event_id,
        name=f"{src.name} (Copy)",
        description=src.description,
        version=1,
        is_active=True,
        scale_pixels_per_meter=src.scale_pixels_per_meter,
        canvas_width=src.canvas_width,
        canvas_height=src.canvas_height,
        background_image_url=src.background_image_url,
        zones_data=list(src.zones_data or []),
    )
    db.add(copy_layout)
    await db.commit()
    await db.refresh(copy_layout)
    return VenueLayoutResponse.model_validate(copy_layout)


@router.post("/upload-background")
async def upload_background_image(
    file: UploadFile = File(...),
):
    """Upload a floor plan, aerial photo, or schematic as a locked layout background."""
    settings = get_settings()
    ext = Path(file.filename or "").suffix.lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image format '{ext}'. Allowed: .jpg, .jpeg, .png, .webp",
        )

    content = await file.read()
    max_bytes = settings.max_image_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image file exceeds maximum size of {settings.max_image_size_mb}MB",
        )

    try:
        pil_img = PILImage.open(io.BytesIO(content))
        width, height = pil_img.size
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or unreadable image file: {str(e)}",
        )

    clean_name = Path(file.filename or "background.jpg").name.replace(" ", "_")
    stored_name = f"{uuid.uuid4().hex[:12]}_{clean_name}"
    save_path = settings.floorplans_dir / stored_name
    save_path.write_bytes(content)

    return {
        "image_url": f"/uploads/floorplans/{stored_name}",
        "width": width,
        "height": height,
        "filename": file.filename,
    }


@router.delete("/{layout_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_layout(
    layout_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    layout = await db.get(VenueLayout, layout_id)
    if not layout:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Layout not found")
    await db.delete(layout)
    await db.commit()
    return None


@router.post("/validate-geometry", response_model=GeometryValidationResponse)
async def validate_geometry(payload: GeometryValidationRequest):
    is_valid, errors = validate_polygon_geometry(payload.polygon_points)
    warnings = []
    if len(payload.polygon_points) > 20:
        warnings.append("High vertex count may increase computation latency.")
    return GeometryValidationResponse(
        is_valid=is_valid,
        errors=errors,
        vertex_count=len(payload.polygon_points),
        warnings=warnings,
    )
