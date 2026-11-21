"""Integration tests verifying all FastAPI endpoints end-to-end."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_endpoint(async_client: AsyncClient):
    """GET /health returns healthy status."""
    res = await async_client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "agent_core" in data["checks"]


@pytest.mark.asyncio
async def test_agent_status_endpoint(async_client: AsyncClient):
    """GET /api/v1/agent/status returns operational metrics."""
    res = await async_client.get("/api/v1/agent/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "operational"
    assert data["uptime_seconds"] >= 0


@pytest.mark.asyncio
async def test_event_registration(async_client: AsyncClient):
    """POST /api/v1/agent/events registers a new venue."""
    payload = {
        "event_id": "api_test_event_1",
        "event_name": "API Test Festival",
        "venue": {
            "venue_id": "v_test_1",
            "venue_name": "Test Stadium",
            "zones": [
                {
                    "zone_id": "zone_1",
                    "zone_name": "North Gate",
                    "capacity": 300,
                    "threshold_low": 0.5,
                    "threshold_moderate": 0.7,
                    "threshold_high": 0.85,
                    "threshold_critical": 0.95,
                }
            ],
        },
    }
    res = await async_client.post("/api/v1/agent/events", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["event_id"] == "api_test_event_1"
    assert data["zones_count"] == 1


@pytest.mark.asyncio
async def test_analyze_endpoint_flow(async_client: AsyncClient, registered_event: str):
    """POST /api/v1/agent/analyze processes batch analytics and returns results."""
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "data": [
            {
                "event_id": registered_event,
                "venue_id": "venue_01",
                "zone_id": "main_stage",
                "timestamp": now_iso,
                "people_count": 350,
                "current_occupancy": 0.70,
                "estimated_density": 0.35,
                "inflow_rate": 15.0,
                "outflow_rate": 5.0,
                "movement_speed": 1.1,
                "predicted_occupancy": 0.88,
                "forecast_horizon_seconds": 300,
                "forecast_confidence": 0.80,
            }
        ]
    }
    res = await async_client.post("/api/v1/agent/analyze", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["accepted"] == 1
    assert data["results"] is not None
    assert len(data["results"]["risk_assessments"]) == 1
    assert data["processing_time_ms"] > 0


@pytest.mark.asyncio
async def test_zone_analysis_endpoint(async_client: AsyncClient, registered_event: str):
    """GET /api/v1/agent/zones/{zone_id}/analysis returns deep analytical view."""
    res = await async_client.get(f"/api/v1/agent/zones/main_stage/analysis?event_id={registered_event}")
    assert res.status_code == 200
    data = res.json()
    assert data["zone_id"] == "main_stage"
    assert "risk_assessment" in data


@pytest.mark.asyncio
async def test_alerts_and_acknowledgement(async_client: AsyncClient, registered_event: str):
    """GET /alerts, POST acknowledge, and POST resolve."""
    # 1. Query alerts
    res = await async_client.get(f"/api/v1/agent/alerts?event_id={registered_event}")
    assert res.status_code == 200
    data = res.json()
    alerts = data["alerts"]

    if alerts:
        alert_id = alerts[0]["id"]
        # 2. Acknowledge
        ack_res = await async_client.post(
            f"/api/v1/agent/alerts/{alert_id}/acknowledge",
            json={"acknowledged_by": "Ops Desk Lead"},
        )
        assert ack_res.status_code == 200
        assert ack_res.json()["state"] == "ACKNOWLEDGED"

        # 3. Resolve
        res_res = await async_client.post(
            f"/api/v1/agent/alerts/{alert_id}/resolve",
            json={"resolved_by": "Safety Officer", "resolution_note": "Capacity stabilized"},
        )
        assert res_res.status_code == 200
        assert res_res.json()["state"] == "RESOLVED"


@pytest.mark.asyncio
async def test_recommendations_endpoint(async_client: AsyncClient, registered_event: str):
    """GET /api/v1/agent/recommendations returns active recommendations."""
    res = await async_client.get(f"/api/v1/agent/recommendations?event_id={registered_event}")
    assert res.status_code == 200
    data = res.json()
    assert "recommendations" in data


@pytest.mark.asyncio
async def test_conversational_chat_endpoint(async_client: AsyncClient, registered_event: str):
    """POST /api/v1/agent/chat provides factual tool-grounded responses."""
    payload = {
        "event_id": registered_event,
        "message": "Which area is currently most crowded?",
    }
    res = await async_client.post("/api/v1/agent/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["response"] is not None
    assert len(data["response"]) > 0
    assert "get_most_crowded_zone" in data["data_sources"] or len(data["data_sources"]) > 0


@pytest.mark.asyncio
async def test_operator_feedback_endpoint(async_client: AsyncClient, registered_event: str):
    """POST /api/v1/agent/feedback logs human operational ratings."""
    payload = {
        "event_id": registered_event,
        "target_type": "alert",
        "target_id": "test_alert_id_123",
        "feedback": "helpful",
        "comment": "Prevented bottleneck at Main Stage entrance",
        "submitted_by": "Chief Inspector",
    }
    res = await async_client.post("/api/v1/agent/feedback", json=payload)
    assert res.status_code == 200
    assert res.json()["received"] is True
