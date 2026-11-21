"""Comprehensive Unit & Integration Tests for CROWD VISION Phase 3.

Covers:
- AI Copilot Provider & Service
- Context-Aware Data Grounding
- Tool Execution & Confirmation Safety Policy
- Action Validation & Audit Logging
- Intelligent Alert Engine Lifecycle & Stats
- Historical Analytics Time-Series Endpoints
- System Health Monitoring with Phase 3 Indicators
"""
from __future__ import annotations

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.copilot.executor import CopilotToolExecutor
from app.copilot.provider import CircuitBreaker, DeterministicGroundedProvider, GeminiLLMProvider, get_llm_provider
from app.copilot.service import CopilotService
from app.copilot.tools import get_all_tools, get_tool_definition
from app.database.models import Alert, CrowdMetric, OperatorAction, Prediction, ProcessingJob, RiskAssessment, Task, TaskHistory
from app.database.session import get_session_factory
from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_copilot_tools_catalog():
    """Verify Copilot tool catalog contains all defined tools with required schema properties."""
    tools = get_all_tools()
    assert len(tools) >= 15

    names = {t["name"] for t in tools}
    assert "get_active_task" in names
    assert "get_layout_zones" in names
    assert "get_latest_telemetry" in names
    assert "get_zone_metrics" in names
    assert "get_zone_risk" in names
    assert "get_predictions" in names
    assert "get_active_alerts" in names
    assert "adjust_zone_capacity" in names
    assert "transition_task_state" in names
    assert "start_task_analysis" in names
    assert "stop_task_analysis" in names
    assert "acknowledge_alert" in names
    assert "resolve_alert" in names

    # Check confirmation safety policy separation
    for t in tools:
        assert "name" in t
        assert "description" in t
        assert "category" in t
        assert t["category"] in ("read_only", "action")
        assert "requires_confirmation" in t
        if t["category"] == "action":
            assert t["requires_confirmation"] is True
        else:
            assert t["requires_confirmation"] is False


@pytest.mark.asyncio
async def test_circuit_breaker():
    """Verify circuit breaker trips to OPEN after threshold and recovers."""
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout_seconds=0.1)
    assert cb.is_open is False

    cb.record_failure()
    cb.record_failure()
    assert cb.is_open is False

    cb.record_failure()
    assert cb.is_open is True

    # Wait for recovery timeout
    import asyncio
    await asyncio.sleep(0.15)
    # Should transition to HALF_OPEN (is_open returns False)
    assert cb.is_open is False
    cb.record_success()
    assert cb.state == "CLOSED"


@pytest.mark.asyncio
async def test_deterministic_provider_grounding():
    """Verify DeterministicGroundedProvider synthesizes fact-based answers from grounding context."""
    provider = DeterministicGroundedProvider()
    assert provider.is_available() is True

    context = {
        "task": {"id": f"task-test-{uuid.uuid4().hex[:6]}", "name": "Festival Main Arena", "state": "READY", "location": "North Gate"},
        "zones": [
            {"id": "zone-a", "name": "Stage Pit", "capacity": 300, "zone_type": "HIGH_DENSITY"},
            {"id": "zone-b", "name": "Concourse", "capacity": 800, "zone_type": "TRANSIT"},
        ],
        "telemetry": {"total_people": 142},
        "alerts": [{"id": "alt-1", "severity": "HIGH", "title": "Rapid Surge", "zone_name": "Stage Pit", "description": "High net inflow"}],
        "risks": [{"zone_name": "Stage Pit", "risk_level": "HIGH", "monitoring_priority": "IMMEDIATE", "reason": "Congestion building"}],
        "predictions": [{"zone_name": "Stage Pit", "horizon_seconds": 60, "predicted_occupancy": 210, "predicted_change_pct": 25.0, "estimated_trend": "increasing", "risk_category": "HIGH"}],
    }

    # Test risk question
    risk_ans = await provider.generate_response("System instructions", "What is the highest risk area?", context)
    assert "Stage Pit" in risk_ans
    assert "HIGH" in risk_ans

    # Test prediction question
    pred_ans = await provider.generate_response("System instructions", "What are the crowd forecasts?", context)
    assert "projected occupancy" in pred_ans
    assert "Stage Pit" in pred_ans

    # Test alerts question
    alert_ans = await provider.generate_response("System instructions", "Show active alerts", context)
    assert "Rapid Surge" in alert_ans
    assert "active alerts" in alert_ans.lower()

    # Test zones question
    zones_ans = await provider.generate_response("System instructions", "What are the zone capacities?", context)
    assert "1,100 persons" in zones_ans
    assert "Stage Pit" in zones_ans


@pytest.mark.asyncio
async def test_copilot_service_and_action_proposal():
    """Verify CopilotService detects action intent and generates structured action proposals."""
    session_factory = get_session_factory()
    task_id = f"task_copilot_{uuid.uuid4().hex[:8]}"
    async with session_factory() as session:
        # Create test task
        task = Task(
            id=task_id,
            name="Copilot Test Arena",
            location="Gate 4",
            state="READY",
            layout_snapshot={
                "zones_data": [
                    {"id": "z-1", "name": "Gate Area", "capacity": 100, "zone_type": "ENTRY"},
                ]
            },
            video_config={"source_type": "FILE"},
        )
        session.add(task)
        await session.commit()

        service = CopilotService(session)

        # 1. Ask general overview query
        overview_res = await service.query("What is the status of this task?", task_id=task.id)
        assert overview_res.response is not None
        assert "Copilot Overview" in overview_res.response or "Copilot Test Arena" in overview_res.response
        assert overview_res.action_proposal is None

        # 2. Ask to increase capacity
        cap_res = await service.query("Please increase capacity of Gate Area to 350 persons", task_id=task.id)
        assert cap_res.action_proposal is not None
        assert cap_res.action_proposal.action_type == "adjust_zone_capacity"
        assert cap_res.action_proposal.parameters["new_capacity"] == 350
        assert cap_res.action_proposal.parameters["zone_id"] == "z-1"
        assert cap_res.action_proposal.requires_approval is True

        # 3. Ask to pause task
        pause_res = await service.query("Pause monitoring on this task", task_id=task.id)
        assert pause_res.action_proposal is not None
        assert pause_res.action_proposal.action_type == "pause_task_analysis"


@pytest.mark.asyncio
async def test_copilot_api_status_and_tools():
    """Test /api/copilot/status and /api/copilot/tools endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Status
        res_status = await client.get("/api/copilot/status")
        assert res_status.status_code == 200
        data_status = res_status.json()
        assert data_status["status"] == "ONLINE"
        assert "active_provider" in data_status
        assert data_status["available_tools_count"] >= 15

        # Tools
        res_tools = await client.get("/api/copilot/tools")
        assert res_tools.status_code == 200
        data_tools = res_tools.json()
        assert len(data_tools) >= 15
        assert all("name" in t and "category" in t and "requires_confirmation" in t for t in data_tools)


@pytest.mark.asyncio
async def test_copilot_api_action_validation_and_execution():
    """Test action validation and execution lifecycle with safety checks and audit logs."""
    task_id = f"task_exec_{uuid.uuid4().hex[:8]}"
    session_factory = get_session_factory()
    async with session_factory() as session:
        task = Task(
            id=task_id,
            name="Execution Target Task",
            location="Sector 7",
            state="READY",
            layout_snapshot={
                "zones_data": [
                    {"id": "zone_north", "name": "North Gate", "capacity": 150, "zone_type": "ENTRY"},
                ]
            },
        )
        session.add(task)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Validate invalid capacity (negative)
        res_val_invalid = await client.post(
            "/api/copilot/validate-action",
            json={
                "action_type": "adjust_zone_capacity",
                "parameters": {"task_id": task_id, "zone_id": "zone_north", "new_capacity": -50},
                "task_id": task_id,
            },
        )
        assert res_val_invalid.status_code == 200
        val_data = res_val_invalid.json()
        assert val_data["is_valid"] is False
        assert len(val_data["validation_errors"]) > 0

        # 2. Validate valid capacity
        res_val_valid = await client.post(
            "/api/copilot/validate-action",
            json={
                "action_type": "adjust_zone_capacity",
                "parameters": {"task_id": task_id, "zone_id": "zone_north", "new_capacity": 450},
                "task_id": task_id,
            },
        )
        assert res_val_valid.status_code == 200
        assert res_val_valid.json()["is_valid"] is True
        assert "Re-calibrates" in res_val_valid.json()["simulated_impact"]

        # 3. Execute capacity adjustment
        res_exec = await client.post(
            "/api/copilot/execute-action",
            json={
                "action_type": "adjust_zone_capacity",
                "parameters": {"task_id": task_id, "zone_id": "zone_north", "new_capacity": 450},
                "task_id": task_id,
                "confirmed_by": "lead_operator@crowdvision.io",
            },
        )
        assert res_exec.status_code == 200
        exec_data = res_exec.json()
        assert exec_data["success"] is True
        assert exec_data["result"]["new_capacity"] == 450

        # Verify database was updated and audit log written
        async with session_factory() as session:
            updated_task = await session.get(Task, task_id)
            assert updated_task.layout_snapshot["zones_data"][0]["capacity"] == 450

            # Check TaskHistory audit record
            history_rows = (
                await session.execute(
                    TaskHistory.__table__.select().where(TaskHistory.task_id == task_id)
                )
            ).all()
            assert len(history_rows) >= 1

        # 4. Execute state transition action
        res_trans = await client.post(
            "/api/copilot/execute-action",
            json={
                "action_type": "transition_task_state",
                "parameters": {"task_id": task_id, "new_state": "PAUSED", "reason": "Precautionary crowd hold"},
                "task_id": task_id,
                "confirmed_by": "lead_operator@crowdvision.io",
            },
        )
        assert res_trans.status_code == 200
        assert res_trans.json()["success"] is True

        async with session_factory() as session:
            updated_task = await session.get(Task, task_id)
            assert updated_task.state == "PAUSED"


@pytest.mark.asyncio
async def test_alert_engine_api_and_stats():
    """Test Alert creation, statistics, acknowledge, resolve, and status patch workflows."""
    event_id = f"event_alert_{uuid.uuid4().hex[:8]}"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create an alert
        res_create = await client.post(
            "/api/alerts",
            json={
                "event_id": event_id,
                "zone_id": "zone_vip",
                "zone_name": "VIP Lounge",
                "category": "bottleneck",
                "severity": "HIGH",
                "title": "VIP Egress Bottleneck",
                "description": "Pedestrian flow restricted at VIP gate",
                "supporting_measurements": {"inflow": 12.5, "outflow": 2.1},
                "source": "AGENT_INJECTION",
            },
        )
        assert res_create.status_code == 201
        created_alert = res_create.json()
        alert_id = created_alert["id"]
        assert created_alert["status"] == "ACTIVE"

        # Check alert stats
        res_stats = await client.get(f"/api/alerts/stats?event_id={event_id}")
        assert res_stats.status_code == 200
        stats = res_stats.json()
        assert stats["total"] >= 1
        assert stats["active"] >= 1
        assert stats["by_severity"]["HIGH"] >= 1
        assert stats["by_category"]["bottleneck"] >= 1

        # Acknowledge alert via status patch
        res_ack = await client.patch(
            f"/api/alerts/{alert_id}/status",
            json={"status": "ACKNOWLEDGED", "note": "Stewards deployed to gate"},
        )
        assert res_ack.status_code == 200
        assert res_ack.json()["status"] == "ACKNOWLEDGED"

        # Resolve alert via status patch
        res_res = await client.patch(
            f"/api/alerts/{alert_id}/status",
            json={"status": "RESOLVED", "note": "Gate cleared and flow restored"},
        )
        assert res_res.status_code == 200
        assert res_res.json()["status"] == "RESOLVED"


@pytest.mark.asyncio
async def test_historical_analytics_endpoint():
    """Test /api/analytics/history time-series aggregation query."""
    task_id = f"task_hist_{uuid.uuid4().hex[:8]}"
    session_factory = get_session_factory()
    async with session_factory() as session:
        for i in range(5):
            m = CrowdMetric(
                event_id=task_id,
                job_id="job_hist_1",
                zone_id="zone_main",
                zone_name="Main Concierge",
                video_timestamp_sec=float(i * 2.0),
                people_count=10 + i * 5,
                occupancy_ratio=0.1 * (i + 1),
                density_value=0.5,
                inflow_rate=2.0,
                outflow_rate=1.0,
                net_flow=1.0,
                avg_speed=15.0 + i,
                movement_direction="STATIONARY",
            )
            session.add(m)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/analytics/history?task_id={task_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["task_id"] == task_id
        assert data["data_points"] == 5
        assert data["peak_people"] == 30
        assert len(data["timeline"]) == 5
        assert data["timeline"][-1]["total_people"] == 30


@pytest.mark.asyncio
async def test_health_endpoint_phase3():
    """Verify /api/health returns detailed Phase 3 diagnostic fields."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] in ("healthy", "degraded")
        assert "copilot_provider" in data
        assert "copilot_llm_configured" in data
        assert "copilot_tools_count" in data
        assert data["copilot_tools_count"] >= 15
