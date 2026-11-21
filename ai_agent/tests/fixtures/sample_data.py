"""Test fixtures and sample data for CrowdVision AI Agent tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

from app.schemas.models import (
    CrowdDataInput,
    ForecastPoint,
    MovementDirection,
    VenueConfig,
    ZoneConfig,
)


def make_venue_config(
    venue_id: str = "venue_001",
    venue_name: str = "Test Arena",
    num_zones: int = 4,
) -> VenueConfig:
    """Create a test venue configuration."""
    zones = [
        ZoneConfig(
            zone_id="main_stage",
            zone_name="Main Stage",
            capacity=500,
            area_sqm=1000.0,
            adjacent_zones=["food_court", "vip_area"],
            is_entry=False,
            is_exit=False,
            threshold_low=0.5,
            threshold_moderate=0.7,
            threshold_high=0.85,
            threshold_critical=0.95,
            density_moderate=2.0,
            density_high=3.5,
            density_critical=5.0,
        ),
        ZoneConfig(
            zone_id="entrance_a",
            zone_name="Entrance A",
            capacity=200,
            area_sqm=300.0,
            adjacent_zones=["main_stage", "food_court"],
            is_entry=True,
            is_exit=True,
            threshold_low=0.4,
            threshold_moderate=0.6,
            threshold_high=0.8,
            threshold_critical=0.9,
            density_moderate=1.5,
            density_high=2.5,
            density_critical=4.0,
        ),
        ZoneConfig(
            zone_id="food_court",
            zone_name="Food Court",
            capacity=350,
            area_sqm=700.0,
            adjacent_zones=["main_stage", "entrance_a", "vip_area"],
            is_entry=False,
            is_exit=False,
            threshold_low=0.5,
            threshold_moderate=0.7,
            threshold_high=0.85,
            threshold_critical=0.95,
            density_moderate=2.0,
            density_high=3.0,
            density_critical=4.5,
        ),
        ZoneConfig(
            zone_id="vip_area",
            zone_name="VIP Area",
            capacity=100,
            area_sqm=200.0,
            adjacent_zones=["main_stage", "food_court"],
            is_entry=False,
            is_exit=False,
            threshold_low=0.5,
            threshold_moderate=0.7,
            threshold_high=0.85,
            threshold_critical=0.95,
            density_moderate=2.0,
            density_high=3.0,
            density_critical=4.0,
        ),
    ]

    return VenueConfig(
        venue_id=venue_id,
        venue_name=venue_name,
        zones=zones[:num_zones],
        total_capacity=sum(z.capacity for z in zones[:num_zones]),
    )


def make_crowd_data(
    event_id: str = "event_001",
    venue_id: str = "venue_001",
    zone_id: str = "main_stage",
    people_count: int = 250,
    capacity: int = 500,
    inflow_rate: Optional[float] = 10.0,
    outflow_rate: Optional[float] = 8.0,
    movement_direction: Optional[MovementDirection] = MovementDirection.INWARD,
    movement_speed: Optional[float] = 1.2,
    density_growth_rate: Optional[float] = 0.5,
    predicted_density: Optional[float] = None,
    predicted_occupancy: Optional[float] = None,
    forecast_horizon_seconds: Optional[int] = 300,
    forecast_confidence: Optional[float] = 0.8,
    timestamp: Optional[datetime] = None,
    area_sqm: float = 1000.0,
) -> CrowdDataInput:
    """Create a test crowd data input."""
    if timestamp is None:
        timestamp = datetime.utcnow()

    occupancy = people_count / capacity if capacity > 0 else 0
    density = people_count / area_sqm if area_sqm > 0 else None

    return CrowdDataInput(
        event_id=event_id,
        venue_id=venue_id,
        zone_id=zone_id,
        timestamp=timestamp,
        people_count=people_count,
        estimated_density=density,
        current_occupancy=occupancy,
        inflow_rate=inflow_rate,
        outflow_rate=outflow_rate,
        movement_direction=movement_direction,
        movement_speed=movement_speed,
        density_growth_rate=density_growth_rate,
        predicted_density=predicted_density,
        predicted_occupancy=predicted_occupancy or (occupancy + 0.1 if occupancy else None),
        forecast_horizon_seconds=forecast_horizon_seconds,
        forecast_confidence=forecast_confidence,
        message_id=str(uuid.uuid4()),
    )


def make_crowd_data_series(
    zone_id: str = "main_stage",
    start_count: int = 100,
    end_count: int = 450,
    num_points: int = 20,
    capacity: int = 500,
    area_sqm: float = 1000.0,
    event_id: str = "event_001",
    venue_id: str = "venue_001",
    start_time: Optional[datetime] = None,
    interval_seconds: int = 15,
) -> list[CrowdDataInput]:
    """Create a time series of crowd data showing gradual increase."""
    if start_time is None:
        start_time = datetime.utcnow() - timedelta(seconds=interval_seconds * num_points)

    series = []
    for i in range(num_points):
        progress = i / max(num_points - 1, 1)
        count = int(start_count + (end_count - start_count) * progress)
        ts = start_time + timedelta(seconds=i * interval_seconds)

        inflow = max(5, (end_count - start_count) / num_points + 5)
        outflow = max(2, inflow * 0.4)

        data = make_crowd_data(
            event_id=event_id,
            venue_id=venue_id,
            zone_id=zone_id,
            people_count=count,
            capacity=capacity,
            area_sqm=area_sqm,
            inflow_rate=inflow,
            outflow_rate=outflow,
            density_growth_rate=(end_count - start_count) / (num_points * area_sqm),
            timestamp=ts,
            predicted_occupancy=min(1.0, (count / capacity) + 0.1),
            forecast_confidence=0.75,
        )
        series.append(data)

    return series


# ── Sample JSON payloads for API documentation ──

SAMPLE_ANALYZE_REQUEST = {
    "data": [
        {
            "event_id": "event_001",
            "venue_id": "venue_001",
            "zone_id": "main_stage",
            "timestamp": "2026-11-17T20:00:00Z",
            "people_count": 350,
            "estimated_density": 0.35,
            "current_occupancy": 0.7,
            "inflow_rate": 15.0,
            "outflow_rate": 8.0,
            "movement_direction": "INWARD",
            "movement_speed": 1.1,
            "density_growth_rate": 0.8,
            "predicted_density": 0.45,
            "predicted_occupancy": 0.85,
            "forecast_horizon_seconds": 300,
            "forecast_confidence": 0.78,
        }
    ]
}

SAMPLE_EVENT_CREATE = {
    "event_id": "event_001",
    "event_name": "Summer Music Festival 2026",
    "venue": {
        "venue_id": "venue_001",
        "venue_name": "Central Park Arena",
        "zones": [
            {
                "zone_id": "main_stage",
                "zone_name": "Main Stage",
                "capacity": 500,
                "area_sqm": 1000.0,
                "adjacent_zones": ["food_court"],
                "threshold_low": 0.5,
                "threshold_moderate": 0.7,
                "threshold_high": 0.85,
                "threshold_critical": 0.95,
            },
            {
                "zone_id": "food_court",
                "zone_name": "Food Court",
                "capacity": 350,
                "area_sqm": 700.0,
                "adjacent_zones": ["main_stage"],
                "threshold_low": 0.5,
                "threshold_moderate": 0.7,
                "threshold_high": 0.85,
                "threshold_critical": 0.95,
            },
        ],
    },
}

SAMPLE_CHAT_REQUEST = {
    "event_id": "event_001",
    "message": "Which area is currently most crowded?",
}
