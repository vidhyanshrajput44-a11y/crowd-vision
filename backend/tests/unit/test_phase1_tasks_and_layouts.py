"""Unit and integration tests for CROWD VISION Phase 1 Foundation, Tasks, Layouts, and Copilot."""
from __future__ import annotations

import io
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_task_crud_lifecycle_and_snapshots(client: TestClient):
    """Verify task creation, layout snapshot freezing, update, state transition, and deletion."""
    # 1. Create a spatial layout first
    layout_payload = {
        "name": "Arena North Concourse",
        "canvas_width": 1920,
        "canvas_height": 1080,
        "zones_data": [
            {
                "id": "zone-gate-1",
                "name": "Gate 1 Turnstiles",
                "zone_type": "ENTRANCE",
                "polygon_points": [[0.1, 0.1], [0.4, 0.1], [0.4, 0.4], [0.1, 0.4]],
                "capacity": 200,
                "color": "#06B6D4",
            },
            {
                "id": "zone-gate-2",
                "name": "Concourse Corridor",
                "zone_type": "CONCOURSE",
                "polygon_points": [[0.5, 0.1], [0.9, 0.1], [0.9, 0.4], [0.5, 0.4]],
                "capacity": 350,
                "color": "#3B82F6",
            },
        ],
    }
    res_layout = client.post("/api/layouts/", json=layout_payload)
    assert res_layout.status_code == 201, res_layout.text
    layout = res_layout.json()
    layout_id = layout["id"]

    # 2. Create Task referencing this layout
    task_payload = {
        "name": "Friday Match Crowd Watch",
        "description": "Surveillance of North Concourse entries",
        "location": "North Arena Sector 4",
        "state": "CONFIGURING",
        "layout_id": layout_id,
        "video_config": {
            "source_type": "CCTV_STREAM",
            "source_uri": "rtsp://10.0.0.50:554/live/stream1",
            "camera_perspective": "FIXED_CCTV",
            "sample_fps": 2.5,
        },
        "notes": "Monitor for queue bottlenecks near Gate 1",
    }
    res_task = client.post("/api/tasks/", json=task_payload)
    assert res_task.status_code == 201, res_task.text
    task = res_task.json()
    task_id = task["id"]

    assert task["name"] == "Friday Match Crowd Watch"
    assert task["state"] == "CONFIGURING"
    assert task["location"] == "North Arena Sector 4"
    assert task["layout_id"] == layout_id
    # Confirm layout snapshot is captured and contains the 2 zones
    assert "zones_data" in task["layout_snapshot"]
    assert len(task["layout_snapshot"]["zones_data"]) == 2

    # 3. Retrieve task
    res_get = client.get(f"/api/tasks/{task_id}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == task_id

    # 4. Update task details
    res_patch = client.patch(
        f"/api/tasks/{task_id}",
        json={"name": "Friday Match Crowd Watch (Priority)", "notes": "High attendance expected"},
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["name"] == "Friday Match Crowd Watch (Priority)"

    # 5. Transition state to READY
    res_state = client.post(
        f"/api/tasks/{task_id}/state",
        json={"state": "READY", "reason": "Operator verification complete"},
    )
    assert res_state.status_code == 200
    assert res_state.json()["state"] == "READY"

    # 6. Audit History
    res_hist = client.get(f"/api/tasks/{task_id}/history")
    assert res_hist.status_code == 200
    history = res_hist.json()
    assert len(history) >= 3  # CREATED, UPDATED, STATE_CHANGED
    assert any(h["event_type"] == "CREATED" for h in history)
    assert any(h["event_type"] == "STATE_CHANGED" for h in history)

    # 7. Duplicate task
    res_dup = client.post(f"/api/tasks/{task_id}/duplicate")
    assert res_dup.status_code == 201
    dup_task = res_dup.json()
    assert dup_task["id"] != task_id
    assert "(Copy)" in dup_task["name"]
    assert dup_task["state"] == "DRAFT"

    # 8. Delete task
    res_del = client.delete(f"/api/tasks/{task_id}")
    assert res_del.status_code == 204

    # Confirm 404
    res_not_found = client.get(f"/api/tasks/{task_id}")
    assert res_not_found.status_code == 404


def test_copilot_status_and_context_reasoning(client: TestClient):
    """Verify AI Copilot provider status and context management."""
    # 1. Copilot status
    res_status = client.get("/api/copilot/status")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["status"] == "ONLINE"
    assert "available_tools" in status_data
    assert len(status_data["available_tools"]) >= 3

    # 2. Query Copilot without task
    res_query_no_task = client.post(
        "/api/copilot/query",
        json={"message": "What is the status of the venue?"},
    )
    assert res_query_no_task.status_code == 200
    assert "No active monitoring task" in res_query_no_task.json()["response"]

    # 3. Create a task with layout and query Copilot with context
    res_task = client.post(
        "/api/tasks/",
        json={
            "name": "Festival Main Lawn Monitoring",
            "location": "Lawn Section A",
            "state": "READY",
            "layout_snapshot": {
                "zones_data": [
                    {
                        "id": "zone-stage-lawn",
                        "name": "Stage Lawn",
                        "zone_type": "STAGE",
                        "capacity": 500,
                        "polygon_points": [[0.1, 0.1], [0.8, 0.1], [0.8, 0.5], [0.1, 0.5]],
                    }
                ]
            },
        },
    )
    assert res_task.status_code == 201
    task_id = res_task.json()["id"]

    res_query_zones = client.post(
        "/api/copilot/query",
        json={"task_id": task_id, "message": "Tell me about the configured zones and capacity"},
    )
    assert res_query_zones.status_code == 200
    ans = res_query_zones.json()["response"]
    assert "Stage Lawn" in ans
    assert "500" in ans

    # 4. Action proposal validation
    res_val = client.post(
        "/api/copilot/validate-action",
        json={
            "action_type": "adjust_zone_capacity",
            "parameters": {"new_capacity": 600},
            "task_id": task_id,
        },
    )
    assert res_val.status_code == 200
    assert res_val.json()["is_valid"] is True

    # 5. Invalid action rejection
    res_val_invalid = client.post(
        "/api/copilot/validate-action",
        json={
            "action_type": "adjust_zone_capacity",
            "parameters": {"new_capacity": -50},
            "task_id": task_id,
        },
    )
    assert res_val_invalid.status_code == 200
    assert res_val_invalid.json()["is_valid"] is False
    assert len(res_val_invalid.json()["validation_errors"]) > 0


def test_layout_snapshot_immutability_and_isolation(client: TestClient):
    """Verify that mutating a layout does not mutate previously created task snapshots."""
    # 1. Create Layout with Zone Alpha
    res_layout = client.post(
        "/api/layouts/",
        json={
            "name": "Original Ground Plan",
            "zones_data": [
                {
                    "id": "zone-alpha",
                    "name": "Zone Alpha",
                    "zone_type": "STAGE",
                    "capacity": 300,
                    "polygon_points": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]],
                }
            ],
        },
    )
    assert res_layout.status_code == 201
    layout_id = res_layout.json()["id"]

    # 2. Create Task 1 referencing this layout
    res_task1 = client.post(
        "/api/tasks/",
        json={
            "name": "Surveillance Alpha Task",
            "location": "North Ground",
            "layout_id": layout_id,
            "state": "READY",
        },
    )
    assert res_task1.status_code == 201
    task1 = res_task1.json()
    assert len(task1["layout_snapshot"]["zones_data"]) == 1
    assert task1["layout_snapshot"]["zones_data"][0]["name"] == "Zone Alpha"

    # 3. Mutate Layout: Add Zone Beta & change name
    res_patch_layout = client.patch(
        f"/api/layouts/{layout_id}",
        json={
            "name": "Mutated Ground Plan v2",
            "zones_data": [
                {
                    "id": "zone-alpha-renamed",
                    "name": "Zone Alpha Reconfigured",
                    "zone_type": "STAGE",
                    "capacity": 999,
                    "polygon_points": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]],
                },
                {
                    "id": "zone-beta",
                    "name": "Zone Beta",
                    "zone_type": "CONCOURSE",
                    "capacity": 150,
                    "polygon_points": [[0.6, 0.1], [0.9, 0.1], [0.9, 0.5], [0.6, 0.5]],
                },
            ],
        },
    )
    assert res_patch_layout.status_code == 200
    assert res_patch_layout.json()["version"] >= 2

    # 4. Check Task 1: MUST NOT have changed! (Frozen snapshot guarantee)
    res_get_task1 = client.get(f"/api/tasks/{task1['id']}")
    assert res_get_task1.status_code == 200
    task1_fresh = res_get_task1.json()
    assert len(task1_fresh["layout_snapshot"]["zones_data"]) == 1
    assert task1_fresh["layout_snapshot"]["zones_data"][0]["name"] == "Zone Alpha"
    assert task1_fresh["layout_snapshot"]["zones_data"][0]["capacity"] == 300

    # 5. Create Task 2 referencing the mutated layout: should receive the new v2 zones
    res_task2 = client.post(
        "/api/tasks/",
        json={
            "name": "Surveillance Beta Task",
            "location": "South Ground",
            "layout_id": layout_id,
            "state": "READY",
        },
    )
    assert res_task2.status_code == 201
    task2 = res_task2.json()
    assert len(task2["layout_snapshot"]["zones_data"]) == 2
    assert task2["layout_snapshot"]["zones_data"][0]["name"] == "Zone Alpha Reconfigured"

    # 6. Task Isolation check: Task 1 and Task 2 snapshots are strictly isolated
    assert task1_fresh["id"] != task2["id"]
    assert len(task1_fresh["layout_snapshot"]["zones_data"]) != len(task2["layout_snapshot"]["zones_data"])


def test_geometry_validation_and_invalid_polygons(client: TestClient):
    """Verify geometry validation endpoint detects self-intersection and bounds errors."""
    # Valid rectangle
    res_valid = client.post(
        "/api/layouts/validate-geometry",
        json={"polygon_points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]},
    )
    assert res_valid.status_code == 200
    assert res_valid.json()["is_valid"] is True
    assert len(res_valid.json()["errors"]) == 0

    # Under minimum 3 vertices
    res_under = client.post(
        "/api/layouts/validate-geometry",
        json={"polygon_points": [[0.1, 0.1], [0.9, 0.1]]},
    )
    assert res_under.status_code == 200
    assert res_under.json()["is_valid"] is False
    assert any("at least 3" in e.lower() for e in res_under.json()["errors"])

    # Self-intersecting bowtie
    res_bowtie = client.post(
        "/api/layouts/validate-geometry",
        json={"polygon_points": [[0.1, 0.1], [0.9, 0.9], [0.1, 0.9], [0.9, 0.1]]},
    )
    assert res_bowtie.status_code == 200
    assert res_bowtie.json()["is_valid"] is False
    assert any("self-intersects" in e.lower() for e in res_bowtie.json()["errors"])

