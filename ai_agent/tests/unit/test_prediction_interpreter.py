"""Unit tests for PredictionInterpreter."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.intelligence.prediction_interpreter import PredictionInterpreter
from app.schemas.models import (
    CrowdDataInput,
    ForecastPoint,
    RiskLevel,
    ZoneConfig,
)


@pytest.fixture
def interpreter() -> PredictionInterpreter:
    return PredictionInterpreter()


@pytest.fixture
def zone_cfg() -> ZoneConfig:
    return ZoneConfig(
        zone_id="main_stage",
        zone_name="Main Stage",
        capacity=500,
        threshold_low=0.5,
        threshold_moderate=0.7,
        threshold_high=0.85,
        threshold_critical=0.95,
    )


@pytest.mark.asyncio
async def test_emerging_hotspot_flagged(interpreter: PredictionInterpreter, zone_cfg: ZoneConfig):
    """Current risk is MODERATE, but 5m forecast predicts HIGH -> Emerging Hotspot."""
    data = CrowdDataInput(
        event_id="e1",
        venue_id="v1",
        zone_id="main_stage",
        timestamp=datetime.now(timezone.utc),
        people_count=300,
        current_occupancy=0.60,
        predicted_occupancy=0.90,  # 90% in 5m
        forecast_horizon_seconds=300,
        forecast_confidence=0.85,
    )
    results = await interpreter.interpret(data, zone_cfg, current_risk=RiskLevel.MODERATE)

    assert len(results) == 1
    interp = results[0]
    assert interp.predicted_risk == RiskLevel.HIGH
    assert interp.is_emerging_hotspot is True
    assert interp.growth_trend in ("rapid_increase", "increasing")


@pytest.mark.asyncio
async def test_low_confidence_forecast_flagged(interpreter: PredictionInterpreter, zone_cfg: ZoneConfig):
    """Forecast with confidence < 0.50 must be explicitly flagged."""
    data = CrowdDataInput(
        event_id="e1",
        venue_id="v1",
        zone_id="main_stage",
        timestamp=datetime.now(timezone.utc),
        people_count=200,
        predicted_occupancy=0.88,
        forecast_horizon_seconds=300,
        forecast_confidence=0.35,  # low confidence
    )
    results = await interpreter.interpret(data, zone_cfg, current_risk=RiskLevel.LOW)
    assert len(results) == 1
    assert results[0].is_low_confidence is True


@pytest.mark.asyncio
async def test_multi_horizon_forecasting(interpreter: PredictionInterpreter, zone_cfg: ZoneConfig):
    """Support multiple forecast horizons (1m, 3m, 5m)."""
    data = CrowdDataInput(
        event_id="e1",
        venue_id="v1",
        zone_id="main_stage",
        timestamp=datetime.now(timezone.utc),
        people_count=250,
        current_occupancy=0.50,
        multi_horizon_forecasts=[
            ForecastPoint(horizon_seconds=60, predicted_occupancy=0.55, confidence=0.90),
            ForecastPoint(horizon_seconds=180, predicted_occupancy=0.68, confidence=0.82),
            ForecastPoint(horizon_seconds=300, predicted_occupancy=0.86, confidence=0.75),
        ],
    )
    results = await interpreter.interpret(data, zone_cfg, current_risk=RiskLevel.LOW)

    assert len(results) == 3
    assert results[0].forecast_horizon_seconds == 60
    assert results[1].forecast_horizon_seconds == 180
    assert results[2].forecast_horizon_seconds == 300
    assert results[2].predicted_risk == RiskLevel.HIGH
