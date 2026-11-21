"""Unit tests for deterministic CrowdAnalyzer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.intelligence.crowd_analyzer import CrowdAnalyzer
from app.schemas.models import CrowdDataInput, MovementDirection, ZoneConfig


@pytest.fixture
def analyzer() -> CrowdAnalyzer:
    return CrowdAnalyzer()


@pytest.fixture
def zone_cfg() -> ZoneConfig:
    return ZoneConfig(
        zone_id="zone_a",
        zone_name="Zone A",
        capacity=500,
        area_sqm=1000.0,
        threshold_low=0.5,
        threshold_moderate=0.7,
        threshold_high=0.85,
        threshold_critical=0.95,
    )


@pytest.mark.asyncio
async def test_nominal_analysis(analyzer: CrowdAnalyzer, zone_cfg: ZoneConfig):
    """Test standard nominal crowd measurements."""
    data = CrowdDataInput(
        event_id="e1",
        venue_id="v1",
        zone_id="zone_a",
        timestamp=datetime.now(timezone.utc),
        people_count=100,
        inflow_rate=5.0,
        outflow_rate=5.0,
        movement_direction=MovementDirection.INWARD,
        movement_speed=1.2,
    )
    result = await analyzer.analyze(data, zone_cfg)

    assert result["occupancy_ratio"] == 0.20
    assert result["density"] == 0.10
    assert result["net_flow"] == 0.0
    assert result["is_bottleneck"] is False
    assert result["is_counterflow"] is False
    assert result["congestion_duration_seconds"] is None


@pytest.mark.asyncio
async def test_trend_detection_rapid_increase(analyzer: CrowdAnalyzer, zone_cfg: ZoneConfig):
    """Verify that steadily rising crowd numbers trigger rapid_increase trend."""
    now = datetime.now(timezone.utc)
    for i in range(12):
        ts = now + timedelta(seconds=i * 10)
        data = CrowdDataInput(
            event_id="e1",
            venue_id="v1",
            zone_id="zone_a",
            timestamp=ts,
            people_count=100 + (i * 30),  # 100 to 430
            inflow_rate=30.0,
            outflow_rate=5.0,
        )
        res = await analyzer.analyze(data, zone_cfg)

    assert res["trend"] in ("rapid_increase", "increasing")
    assert res["growth_slope"] > 0


@pytest.mark.asyncio
async def test_bottleneck_detection(analyzer: CrowdAnalyzer, zone_cfg: ZoneConfig):
    """Verify bottleneck flagged when inflow severely outstrips outflow under dense conditions."""
    data = CrowdDataInput(
        event_id="e1",
        venue_id="v1",
        zone_id="zone_a",
        timestamp=datetime.now(timezone.utc),
        people_count=350,  # 70% occupancy
        inflow_rate=25.0,
        outflow_rate=3.0,
        movement_speed=0.20,  # severely restricted
    )
    result = await analyzer.analyze(data, zone_cfg)
    assert result["is_bottleneck"] is True
    assert result["bottleneck_reason"] is not None


@pytest.mark.asyncio
async def test_counterflow_detection(analyzer: CrowdAnalyzer, zone_cfg: ZoneConfig):
    """Verify opposing flows or mixed directional movement triggers counterflow warning."""
    data = CrowdDataInput(
        event_id="e1",
        venue_id="v1",
        zone_id="zone_a",
        timestamp=datetime.now(timezone.utc),
        people_count=200,
        movement_direction=MovementDirection.MIXED,
    )
    result = await analyzer.analyze(data, zone_cfg)
    assert result["is_counterflow"] is True


@pytest.mark.asyncio
async def test_sudden_change_detection(analyzer: CrowdAnalyzer, zone_cfg: ZoneConfig):
    """Verify sudden surge (>15% occupancy jump in single cycle) is flagged."""
    now = datetime.now(timezone.utc)
    d1 = CrowdDataInput(
        event_id="e1",
        venue_id="v1",
        zone_id="zone_a",
        timestamp=now,
        people_count=100,  # 20%
    )
    await analyzer.analyze(d1, zone_cfg)

    d2 = CrowdDataInput(
        event_id="e1",
        venue_id="v1",
        zone_id="zone_a",
        timestamp=now + timedelta(seconds=10),
        people_count=250,  # 50% (+30% jump)
    )
    res = await analyzer.analyze(d2, zone_cfg)
    assert res["sudden_change"] is not None
    assert "surge" in res["sudden_change"]


@pytest.mark.asyncio
async def test_congestion_duration_tracking(analyzer: CrowdAnalyzer, zone_cfg: ZoneConfig):
    """Verify continuous time above moderate threshold is tracked."""
    now = datetime.now(timezone.utc)
    # First reading above moderate threshold (380 / 500 = 0.76 >= 0.70)
    d1 = CrowdDataInput(
        event_id="e1",
        venue_id="v1",
        zone_id="zone_a",
        timestamp=now,
        people_count=380,
    )
    res1 = await analyzer.analyze(d1, zone_cfg)
    assert res1["congestion_duration_seconds"] == 0.0

    # Second reading 120 seconds later
    d2 = CrowdDataInput(
        event_id="e1",
        venue_id="v1",
        zone_id="zone_a",
        timestamp=now + timedelta(seconds=120),
        people_count=390,
    )
    res2 = await analyzer.analyze(d2, zone_cfg)
    assert res2["congestion_duration_seconds"] == 120.0
