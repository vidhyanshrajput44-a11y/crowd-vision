"""Unit tests for AlertManager, escalation, and lifecycle state transitions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.alerts.alert_manager import AlertManager
from app.schemas.models import (
    AlertPriority,
    AlertState,
    RiskLevel,
    ZoneConfig,
    ZoneRiskAssessment,
)


@pytest.fixture
def alert_mgr() -> AlertManager:
    return AlertManager(dedup_window_seconds=60, escalation_timeout_seconds=300)


@pytest.fixture
def zone_cfg() -> ZoneConfig:
    return ZoneConfig(
        zone_id="zone_b",
        zone_name="Zone B",
        capacity=400,
        threshold_low=0.5,
        threshold_moderate=0.7,
        threshold_high=0.85,
        threshold_critical=0.95,
    )


@pytest.mark.asyncio
async def test_alert_generation_and_deduplication(alert_mgr: AlertManager, zone_cfg: ZoneConfig):
    """High occupancy triggers alert on cycle 1, but suppresses duplicates on cycle 2."""
    assessment = ZoneRiskAssessment(
        zone_id="zone_b",
        zone_name="Zone B",
        risk_level=RiskLevel.HIGH,
        occupancy_ratio=0.88,
        people_count=352,
        capacity=400,
        timestamp=datetime.now(timezone.utc),
    )
    analysis = {"occupancy_ratio": 0.88}

    # Cycle 1: creates alert
    alerts1 = await alert_mgr.evaluate_and_create(assessment, analysis, zone_cfg, event_id="e1")
    assert len(alerts1) > 0
    assert alerts1[0].priority in (AlertPriority.HIGH, AlertPriority.CRITICAL)
    assert alerts1[0].state == AlertState.NEW

    # Cycle 2: suppressed
    alerts2 = await alert_mgr.evaluate_and_create(assessment, analysis, zone_cfg, event_id="e1")
    assert len(alerts2) == 0


@pytest.mark.asyncio
async def test_alert_lifecycle_state_transitions(alert_mgr: AlertManager, zone_cfg: ZoneConfig):
    """Verify NEW -> ACKNOWLEDGED -> RESOLVED state transitions and audit logging."""
    assessment = ZoneRiskAssessment(
        zone_id="zone_b",
        zone_name="Zone B",
        risk_level=RiskLevel.HIGH,
        occupancy_ratio=0.88,
        people_count=352,
        capacity=400,
        timestamp=datetime.now(timezone.utc),
    )
    alerts = await alert_mgr.evaluate_and_create(assessment, {"occupancy_ratio": 0.88}, zone_cfg, "e1")
    alert = alerts[0]

    # 1. Acknowledge
    ack_alert = await alert_mgr.acknowledge(alert.id, by="Officer Smith")
    assert ack_alert.state == AlertState.ACKNOWLEDGED
    assert ack_alert.acknowledged_by == "Officer Smith"

    # 2. Resolve
    res_alert = await alert_mgr.resolve(alert.id, by="Commander Jane", note="Crowd redistributed to Plaza")
    assert res_alert.state == AlertState.RESOLVED
    assert res_alert.resolution_note == "Crowd redistributed to Plaza"

    # Check history
    history = alert_mgr.get_alert_history(alert.id)
    assert len(history) >= 3  # CREATED, ACKNOWLEDGED, RESOLVED


@pytest.mark.asyncio
async def test_alert_escalation_after_timeout(alert_mgr: AlertManager, zone_cfg: ZoneConfig):
    """Unacknowledged alert exceeding timeout promotes priority from HIGH to CRITICAL."""
    assessment = ZoneRiskAssessment(
        zone_id="zone_b",
        zone_name="Zone B",
        risk_level=RiskLevel.HIGH,
        occupancy_ratio=0.88,
        people_count=352,
        capacity=400,
        timestamp=datetime.now(timezone.utc),
    )
    alerts = await alert_mgr.evaluate_and_create(assessment, {"occupancy_ratio": 0.88}, zone_cfg, "e1")
    alert = alerts[0]
    alert.priority = AlertPriority.HIGH

    # Simulate 350 seconds elapsed since creation (timeout is 300s)
    alert.created_at = datetime.now(timezone.utc) - timedelta(seconds=350)

    escalated = await alert_mgr.check_escalations()
    assert len(escalated) == 1
    assert escalated[0].priority == AlertPriority.CRITICAL
    assert escalated[0].escalation_count == 1
