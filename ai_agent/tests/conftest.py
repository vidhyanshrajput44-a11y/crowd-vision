"""Pytest configuration and shared test fixtures for CrowdVision AI Agent."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.event_context import EventContextManager
from app.dependencies import (
    get_event_manager,
    initialize_services,
    shutdown_services,
)
from app.main import app
from app.schemas.models import (
    CrowdDataInput,
    MovementDirection,
    VenueConfig,
    ZoneConfig,
)


@pytest_asyncio.fixture(autouse=True)
async def ensure_services_initialized() -> AsyncGenerator[None, None]:
    """Ensure system services are initialized before each test."""
    await initialize_services()
    yield


@pytest.fixture
def sample_zone_config() -> ZoneConfig:
    """Return a standard calibrated test zone configuration."""
    return ZoneConfig(
        zone_id="main_stage",
        zone_name="Main Stage",
        capacity=500,
        area_sqm=1000.0,
        adjacent_zones=["entrance_a", "food_court"],
        is_entry=False,
        is_exit=False,
        threshold_low=0.5,
        threshold_moderate=0.7,
        threshold_high=0.85,
        threshold_critical=0.95,
        density_moderate=2.0,
        density_high=3.5,
        density_critical=5.0,
    )


@pytest.fixture
def sample_venue_config(sample_zone_config: ZoneConfig) -> VenueConfig:
    """Return standard calibrated test venue configuration."""
    entrance_zone = ZoneConfig(
        zone_id="entrance_a",
        zone_name="Entrance Gate A",
        capacity=200,
        area_sqm=300.0,
        adjacent_zones=["main_stage"],
        is_entry=True,
        is_exit=False,
        threshold_low=0.4,
        threshold_moderate=0.6,
        threshold_high=0.8,
        threshold_critical=0.9,
    )
    food_zone = ZoneConfig(
        zone_id="food_court",
        zone_name="Food Court & Concessions",
        capacity=300,
        area_sqm=600.0,
        adjacent_zones=["main_stage"],
        is_entry=False,
        is_exit=False,
        threshold_low=0.5,
        threshold_moderate=0.7,
        threshold_high=0.85,
        threshold_critical=0.95,
    )
    return VenueConfig(
        venue_id="venue_01",
        venue_name="Metropolis Arena",
        zones=[sample_zone_config, entrance_zone, food_zone],
        total_capacity=1000,
    )


@pytest.fixture
def registered_event(sample_venue_config: VenueConfig) -> str:
    """Ensure a standard test event is registered in the event manager."""
    em = get_event_manager()
    event_id = "test_event_001"
    em.register_event(
        event_id=event_id,
        event_name="Summer Fest 2026",
        venue=sample_venue_config,
    )
    return event_id


@pytest.fixture
def make_crowd_input():
    """Factory fixture generating valid CrowdDataInput instances."""
    def _create(
        event_id: str = "test_event_001",
        zone_id: str = "main_stage",
        people_count: int = 150,
        inflow: float = 5.0,
        outflow: float = 4.0,
        direction: MovementDirection = MovementDirection.INWARD,
        speed: float = 1.2,
        pred_occ: float = 0.35,
        confidence: float = 0.85,
    ) -> CrowdDataInput:
        return CrowdDataInput(
            event_id=event_id,
            venue_id="venue_01",
            zone_id=zone_id,
            timestamp=datetime.now(timezone.utc),
            people_count=people_count,
            estimated_density=round(people_count / 1000.0, 3),
            current_occupancy=round(people_count / 500.0, 3),
            inflow_rate=inflow,
            outflow_rate=outflow,
            movement_direction=direction,
            movement_speed=speed,
            predicted_occupancy=pred_occ,
            forecast_horizon_seconds=300,
            forecast_confidence=confidence,
        )
    return _create


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async test client bound to the FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
