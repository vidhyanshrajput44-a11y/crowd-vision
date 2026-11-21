"""Integration tests verifying strict data and contextual isolation across simultaneous events."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.event_context import EventContextManager
from app.dependencies import get_event_manager, get_orchestrator
from app.schemas.models import (
    CrowdDataInput,
    VenueConfig,
    ZoneConfig,
)


@pytest.fixture
def two_events(registered_event: str) -> tuple[str, str]:
    em = get_event_manager()
    event_b_id = "event_bravo_002"
    v_b = VenueConfig(
        venue_id="venue_bravo",
        venue_name="Bravo Convention Center",
        zones=[
            ZoneConfig(
                zone_id="main_stage",  # identical zone_id to test collision resistance
                zone_name="Bravo Keynote Hall",
                capacity=1000,
                threshold_low=0.5,
                threshold_moderate=0.7,
                threshold_high=0.85,
                threshold_critical=0.95,
            )
        ],
    )
    em.register_event(event_b_id, "Tech Summit Bravo", v_b)
    return registered_event, event_b_id


@pytest.mark.asyncio
async def test_event_isolation_and_no_leakage(two_events: tuple[str, str]):
    """Verify that updates to Event A do not contaminate Event B, even with identical zone_ids."""
    event_a, event_b = two_events
    orchestrator = get_orchestrator()

    now = datetime.now(timezone.utc)

    # Ingest data into Event A (Main Stage: 450/500 = 90% occupancy)
    data_a = CrowdDataInput(
        event_id=event_a,
        venue_id="venue_01",
        zone_id="main_stage",
        timestamp=now,
        people_count=450,
        current_occupancy=0.90,
    )
    await orchestrator.process_batch([data_a])

    # Ingest data into Event B (Main Stage: 100/1000 = 10% occupancy)
    data_b = CrowdDataInput(
        event_id=event_b,
        venue_id="venue_bravo",
        zone_id="main_stage",
        timestamp=now,
        people_count=100,
        current_occupancy=0.10,
    )
    await orchestrator.process_batch([data_b])

    # Fetch analysis for Event A
    analysis_a = await orchestrator.get_zone_analysis(event_a, "main_stage")
    assert analysis_a.risk_assessment.people_count == 450
    assert analysis_a.risk_assessment.capacity == 500

    # Fetch analysis for Event B
    analysis_b = await orchestrator.get_zone_analysis(event_b, "main_stage")
    assert analysis_b.risk_assessment.people_count == 100
    assert analysis_b.risk_assessment.capacity == 1000
    assert analysis_b.zone_name == "Bravo Keynote Hall"
