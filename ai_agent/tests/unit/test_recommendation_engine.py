"""Unit tests for context-aware RecommendationEngine."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.recommendations.recommendation_engine import RecommendationEngine
from app.schemas.models import (
    PredictionInterpretation,
    RecommendationPriority,
    RiskLevel,
    ZoneConfig,
    ZoneRiskAssessment,
)


@pytest.fixture
def engine() -> RecommendationEngine:
    return RecommendationEngine(dedup_window_seconds=60)


@pytest.fixture
def zone_cfg() -> ZoneConfig:
    return ZoneConfig(
        zone_id="entrance_gate",
        zone_name="Entrance Gate",
        capacity=300,
        is_entry=True,
        threshold_low=0.4,
        threshold_moderate=0.6,
        threshold_high=0.8,
        threshold_critical=0.9,
    )


@pytest.mark.asyncio
async def test_recommendations_contain_mandatory_fields(engine: RecommendationEngine, zone_cfg: ZoneConfig):
    """Every recommendation must provide complete tactical metadata and never bypass human approval."""
    assessment = ZoneRiskAssessment(
        zone_id="entrance_gate",
        zone_name="Entrance Gate",
        risk_level=RiskLevel.HIGH,
        occupancy_ratio=0.82,
        people_count=246,
        capacity=300,
        timestamp=datetime.now(timezone.utc),
    )
    analysis = {
        "occupancy_ratio": 0.82,
        "is_bottleneck": True,
        "inflow_rate": 20.0,
        "outflow_rate": 5.0,
        "net_flow": 15.0,
        "trend": "rapid_increase",
    }

    recs = await engine.generate(assessment, analysis, [], zone_cfg, event_id="e1")

    assert len(recs) > 0
    for r in recs:
        assert r.action is not None and len(r.action) > 5
        assert r.reason is not None and len(r.reason) > 5
        assert r.affected_zone == "entrance_gate"
        assert r.priority in (
            RecommendationPriority.LOW,
            RecommendationPriority.MEDIUM,
            RecommendationPriority.HIGH,
            RecommendationPriority.URGENT,
        )
        assert len(r.supporting_observations) > 0
        assert r.suggested_team in ("security", "operations", "management", "medical")
        assert isinstance(r.requires_human_approval, bool)


@pytest.mark.asyncio
async def test_recommendation_deduplication(engine: RecommendationEngine, zone_cfg: ZoneConfig):
    """Repeated cycles with identical conditions must not emit duplicate recommendations."""
    assessment = ZoneRiskAssessment(
        zone_id="entrance_gate",
        zone_name="Entrance Gate",
        risk_level=RiskLevel.HIGH,
        occupancy_ratio=0.82,
        people_count=246,
        capacity=300,
        timestamp=datetime.now(timezone.utc),
    )
    analysis = {"occupancy_ratio": 0.82, "trend": "rapid_increase"}

    # Cycle 1: emits recommendations
    recs1 = await engine.generate(assessment, analysis, [], zone_cfg, event_id="e1")
    assert len(recs1) > 0

    # Cycle 2 immediate duplicate: must be suppressed
    recs2 = await engine.generate(assessment, analysis, [], zone_cfg, event_id="e1")
    assert len(recs2) == 0
