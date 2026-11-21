"""Event management endpoints."""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Event, Venue
from app.database.session import get_db
from app.schemas.api_schemas import EventCreateRequest, EventResponse, EventUpdateRequest

router = APIRouter()


@router.get("", response_model=list[EventResponse])
@router.get("/", response_model=list[EventResponse], include_in_schema=False)
async def list_events(
    db: Annotated[AsyncSession, Depends(get_db)],
    status: Optional[str] = Query(None),
    venue_id: Optional[str] = Query(None),
):
    stmt = select(Event).order_by(desc(Event.created_at))
    if status:
        stmt = stmt.where(Event.status == status.upper())
    if venue_id:
        stmt = stmt.where(Event.venue_id == venue_id)

    events = (await db.execute(stmt)).scalars().all()
    return [EventResponse.model_validate(e) for e in events]


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return EventResponse.model_validate(event)


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=EventResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_event(
    payload: EventCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    venue_id = payload.venue_id
    venue = await db.get(Venue, venue_id) if venue_id else None
    if not venue:
        existing_venue = (await db.execute(select(Venue).limit(1))).scalars().first()
        if existing_venue:
            venue_id = existing_venue.id
        else:
            new_v = Venue(
                name=f"{payload.name} Arena",
                total_capacity=payload.expected_attendance or 5000,
            )
            db.add(new_v)
            await db.flush()
            venue_id = new_v.id

    event = Event(
        venue_id=venue_id,
        name=payload.name,
        event_type=payload.event_type.upper(),
        status="UPCOMING",
        expected_attendance=payload.expected_attendance,
        start_time=payload.start_time,
        end_time=payload.end_time,
        settings=payload.settings or {},
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return EventResponse.model_validate(event)


@router.patch("/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: str,
    payload: EventUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    data = payload.model_dump(exclude_unset=True)
    for field, val in data.items():
        if field == "status" and val:
            setattr(event, field, val.upper())
        elif field == "event_type" and val:
            setattr(event, field, val.upper())
        else:
            setattr(event, field, val)

    await db.commit()
    await db.refresh(event)
    return EventResponse.model_validate(event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    await db.delete(event)
    await db.commit()
    return None
