"""Unit tests for deterministic RiskAssessmentEngine with hysteresis."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.intelligence.risk_assessment import RiskAssessmentEngine
from app.schemas.models import (
    CrowdDataInput,
    RiskLevel,
    ZoneConfig,
    ZoneRiskAssessment,
)


@pytest.fixture
def risk_engine() -> RiskAssessmentEngine:
    return RiskAssessmentEngine()


@pytest.fixture
def zone_cfg() -> ZoneConfig:
    return ZoneConfig(
        zone_id="stage_zone",
        zone_name="Concert Stage",
        capacity=500,
        area_sqm=1000.0,
        adjacent_zones=["plaza"],
        threshold_low=0.5,
        threshold_moderate=0.7,
        threshold_high=0.85,
        threshold_critical=0.95,
        density_moderate=2.0,
        density_high=3.5,
        density_critical=5.0,
    )


def make_input(people_count: int) -> CrowdDataInput:
    return CrowdDataInput(
        event_id="e1",
        venue_id="v1",
        zone_id="stage_zone",
        timestamp=datetime.now(timezone.utc),
        people_count=people_count,
        current_occupancy=people_count / 500.0,
    )


@pytest.mark.asyncio
async def test_normal_risk_classification(risk_engine: RiskAssessmentEngine, zone_cfg: ZoneConfig):
    """Low occupancy results in NORMAL risk."""
    data = make_input(100)  # 20%
    analysis = {"occupancy_ratio": 0.20, "density": 0.10, "net_flow": 0.0}
    assessment = await risk_engine.assess(data, zone_cfg, analysis)
    assert assessment.risk_level == RiskLevel.NORMAL


@pytest.mark.asyncio
async def test_hysteresis_dampens_single_noisy_spike(risk_engine: RiskAssessmentEngine, zone_cfg: ZoneConfig):
    """A single noisy reading into CRITICAL capacity must NOT immediately confirm CRITICAL."""
    # Baseline normal reading
    d_normal = make_input(100)
    a_normal = {"occupancy_ratio": 0.20, "density": 0.10}
    await risk_engine.assess(d_normal, zone_cfg, a_normal)

    # Single spike to 98% (Critical)
    d_spike = make_input(490)
    a_spike = {"occupancy_ratio": 0.98, "density": 4.9}
    res_spike = await risk_engine.assess(d_spike, zone_cfg, a_spike)

    # Must remain dampened due to hysteresis (requires 3 cycles)
    assert res_spike.risk_level == RiskLevel.NORMAL
    # But factor is captured
    assert any(f.severity == RiskLevel.CRITICAL for f in res_spike.risk_factors)


@pytest.mark.asyncio
async def test_hysteresis_confirms_after_consecutive_cycles(risk_engine: RiskAssessmentEngine, zone_cfg: ZoneConfig):
    """Three consecutive high-occupancy cycles confirm escalation to HIGH/CRITICAL."""
    d_high = make_input(450)  # 90% -> High
    a_high = {"occupancy_ratio": 0.90, "density": 0.45}

    # Cycle 1
    res1 = await risk_engine.assess(d_high, zone_cfg, a_high)
    assert res1.risk_level == RiskLevel.NORMAL

    # Cycle 2
    res2 = await risk_engine.assess(d_high, zone_cfg, a_high)
    assert res2.risk_level == RiskLevel.NORMAL

    # Cycle 3 -> Confirmed!
    res3 = await risk_engine.assess(d_high, zone_cfg, a_high)
    assert res3.risk_level == RiskLevel.HIGH


@pytest.mark.asyncio
async def test_adjacent_zone_spillover_evaluated(risk_engine: RiskAssessmentEngine, zone_cfg: ZoneConfig):
    """If adjacent zones are CRITICAL, risk spillover is registered."""
    adj_assessment = ZoneRiskAssessment(
        zone_id="plaza",
        zone_name="Plaza",
        risk_level=RiskLevel.CRITICAL,
        timestamp=datetime.now(timezone.utc),
    )

    data = make_input(200)
    analysis = {"occupancy_ratio": 0.40}
    assessment = await risk_engine.assess(data, zone_cfg, analysis, adjacent_assessments=[adj_assessment])

    assert any(f.factor == "adjacent_spillover" for f in assessment.risk_factors)
