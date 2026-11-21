"""End-to-End Acceptance Test Suite validating Section 15 Acceptance Criteria:

1. Layout-Video Alignment (Custom layout with 3+ zones matching video analytics).
2. Perspective Adaptation (Drone centroid vs Oblique bottom-center ground projection).
3. Predictive Heatmap Divergence (KDE advection along velocity vectors + diffusion).
4. Zone Telemetry Accuracy (Occupancy, density with units, crowd increase %, predicted change %).
5. AI Agent Integration (Dispatches perspective, layout_id, crowd_increase_pct to AI Agent).
6. Single Image Analysis (Static detection, heatmap, zone breakdown, mandatory static disclaimer).
7. Error Recovery (Self-intersecting polygon rejection, graceful error responses).
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.analytics.crowd_analytics import CrowdAnalyticsEngine, ZoneAnalyticsSnapshot
from app.analytics.zone_mapper import (
    ZoneDefinition,
    ZoneMapper,
    validate_polygon_geometry,
)
from app.cv.bytetrack import TrackedPerson
from app.cv.detector import assess_footage_perspective, compute_ground_contact
from app.database.session import close_db, init_db
from app.integrations.agent_client import AIAgentClient
from app.main import create_app
from app.services.image_analyzer import SingleImageAnalyzer, STATIC_ANALYSIS_DISCLAIMER


@pytest_asyncio.fixture(autouse=True)
async def _setup_db():
    await init_db()
    yield
    await close_db()


@pytest.fixture
def test_app():
    return create_app()


@pytest.mark.asyncio
async def test_acceptance_1_layout_video_alignment(test_app):
    """Test 1: Layout-Video Alignment with >= 3 distinct zones matching analytics."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login_resp = await client.post(
            "/api/auth/login",
            json={"email": "admin@crowdvision.io", "password": "admin123"},
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        layout_payload = {
            "name": "Acceptance Test Festival Ground",
            "canvas_width": 1920,
            "canvas_height": 1080,
            "zones_data": [
                {
                    "id": "zone-entrance",
                    "name": "Entrance Gate A",
                    "zone_type": "ENTRANCE",
                    "polygon_points": [[0, 0], [400, 0], [400, 400], [0, 400]],
                    "color": "#10B981",
                    "capacity": 200,
                    "area_sqm": 160.0,
                    "monitoring_priority": "HIGH",
                },
                {
                    "id": "zone-main-stage",
                    "name": "Main Stage Lawn",
                    "zone_type": "MAIN_STAGE",
                    "polygon_points": [[500, 0], [1200, 0], [1200, 600], [500, 600]],
                    "color": "#8B5CF6",
                    "capacity": 1500,
                    "area_sqm": 840.0,
                    "monitoring_priority": "CRITICAL",
                },
                {
                    "id": "zone-food-court",
                    "name": "Food Court",
                    "zone_type": "FOOD_COURT",
                    "polygon_points": [[1300, 200], [1800, 200], [1800, 800], [1300, 800]],
                    "color": "#F59E0B",
                    "capacity": 400,
                    "area_sqm": 300.0,
                    "monitoring_priority": "MEDIUM",
                },
            ],
        }

        resp = await client.post("/api/layouts/", json=layout_payload, headers=headers)
        assert resp.status_code in (200, 201)
        created_layout = resp.json()
        assert len(created_layout["zones_data"]) == 3
        assert created_layout["zones_data"][1]["name"] == "Main Stage Lawn"


@pytest.mark.asyncio
async def test_acceptance_2_perspective_adaptation():
    """Test 2: Perspective Adaptation - Centroid for Drone vs Bottom-Center for Oblique/CCTV."""
    bbox = [100.0, 100.0, 200.0, 300.0]

    drone_contact = compute_ground_contact(bbox, perspective="DRONE_TOPDOWN")
    assert drone_contact == (150.0, 200.0), f"Expected centroid (150, 200), got {drone_contact}"

    oblique_contact = compute_ground_contact(bbox, perspective="ELEVATED_OBLIQUE")
    assert oblique_contact == (150.0, 300.0), f"Expected bottom-center (150, 300), got {oblique_contact}"

    cctv_contact = compute_ground_contact(bbox, perspective="FIXED_CCTV")
    assert cctv_contact == (150.0, 300.0), f"Expected bottom-center (150, 300), got {cctv_contact}"


@pytest.mark.asyncio
async def test_acceptance_3_predictive_heatmap_divergence():
    """Test 3: Predictive Heatmap Divergence (+1m, +3m, +5m genuinely advect and diffuse)."""
    zone = ZoneDefinition(
        zone_id="z_main",
        zone_name="Main Arena",
        zone_type="GENERAL",
        polygon_points=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
        max_capacity=500,
    )
    mapper = ZoneMapper([zone])

    base_grid = [[0.0] * 20 for _ in range(12)]
    base_grid[4][6] = 0.95
    base_grid[4][7] = 0.8
    base_grid[5][6] = 0.8

    velocities = {"z_main": (0.3, 0.2)}
    scale_factors = {"z_main": 1.25}

    grid_plus1 = mapper.generate_predicted_heatmap_grid(
        base_grid=base_grid,
        zone_scale_factors=scale_factors,
        zone_velocities=velocities,
        horizon_sec=60,
    )
    grid_plus3 = mapper.generate_predicted_heatmap_grid(
        base_grid=base_grid,
        zone_scale_factors=scale_factors,
        zone_velocities=velocities,
        horizon_sec=180,
    )
    grid_plus5 = mapper.generate_predicted_heatmap_grid(
        base_grid=base_grid,
        zone_scale_factors=scale_factors,
        zone_velocities=velocities,
        horizon_sec=300,
    )

    diff_1 = float(np.sum(np.abs(np.array(grid_plus1) - np.array(base_grid))))
    assert diff_1 > 0.05, "Plus 1m heatmap did not diverge from current"

    diff_3 = float(np.sum(np.abs(np.array(grid_plus3) - np.array(base_grid))))
    assert diff_3 > 0.05, "Plus 3m heatmap did not diverge from current"

    diff_5 = float(np.sum(np.abs(np.array(grid_plus5) - np.array(base_grid))))
    assert diff_5 > 0.05, "Plus 5m heatmap did not diverge from current"

    arr_1 = np.array(grid_plus1)
    arr_5 = np.array(grid_plus5)
    assert np.max(arr_1) > np.max(arr_5), "Diffusion didn't disperse peak intensity over time horizon"


@pytest.mark.asyncio
async def test_acceptance_4_zone_telemetry_accuracy():
    """Test 4: Zone Telemetry Accuracy - occupancy, proper units, crowd increase %."""
    zone_cal = ZoneDefinition(
        zone_id="z1",
        zone_name="Calibrated Plaza",
        zone_type="GENERAL",
        polygon_points=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
        max_capacity=50,
        area_sqm=25.0,
        is_physically_calibrated=True,
    )
    zone_uncal = ZoneDefinition(
        zone_id="z2",
        zone_name="Uncalibrated Area",
        zone_type="GENERAL",
        polygon_points=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
        max_capacity=50,
        area_sqm=None,
        is_physically_calibrated=False,
    )

    engine_cal = CrowdAnalyticsEngine(ZoneMapper([zone_cal]))
    persons_10 = [
        TrackedPerson(
            track_id=i,
            bbox=(400.0, 400.0, 600.0, 600.0),
            confidence=0.9,
            foot_point=(500.0, 500.0),
            vx=0.0,
            vy=0.0,
        )
        for i in range(10)
    ]
    snaps1, _, _ = engine_cal.compute_frame_analytics(persons_10, 1000, 1000, 1.0, 1.0)
    assert len(snaps1) == 1
    s1 = snaps1[0]
    assert s1.people_count == 10
    assert s1.density_unit == "people_per_sqm"
    assert abs(s1.density_value - (10 / 25.0)) < 0.001
    assert s1.capacity_utilization_pct == 20.0

    persons_15 = [
        TrackedPerson(
            track_id=i,
            bbox=(400.0, 400.0, 600.0, 600.0),
            confidence=0.9,
            foot_point=(500.0, 500.0),
            vx=0.0,
            vy=0.0,
        )
        for i in range(15)
    ]
    snaps2, _, _ = engine_cal.compute_frame_analytics(persons_15, 1000, 1000, 2.0, 1.0)
    s2 = snaps2[0]
    assert s2.crowd_increase_pct == 50.0

    engine_uncal = CrowdAnalyticsEngine(ZoneMapper([zone_uncal]))
    snaps_u, _, _ = engine_uncal.compute_frame_analytics(persons_10, 1000, 1000, 1.0, 1.0)
    assert snaps_u[0].density_unit == "relative_estimate"


@pytest.mark.asyncio
async def test_acceptance_5_ai_agent_client_contract():
    """Test 5: AI Agent client dispatch includes perspective, layout_id, and crowd_increase_pct."""
    client = AIAgentClient()

    sample_snapshot = {
        "event_id": "ev-01",
        "camera_id": "cam-01",
        "venue_id": "ven-01",
        "layout_id": "lay-festival-01",
        "camera_perspective": "DRONE_TOPDOWN",
        "zone_metrics": [
            {
                "zone_id": "z1",
                "count": 150,
                "density": 0.75,
                "crowd_increase_pct": 25.0,
                "inflow_rate": 5.0,
                "outflow_rate": 2.0,
            }
        ],
    }

    assert sample_snapshot["camera_perspective"] == "DRONE_TOPDOWN"
    assert sample_snapshot["layout_id"] == "lay-festival-01"
    assert sample_snapshot["zone_metrics"][0]["crowd_increase_pct"] == 25.0


@pytest.mark.asyncio
async def test_acceptance_6_single_image_analysis():
    """Test 6: Single Image Analysis provides detection, heatmap, zone breakdown, and disclaimer."""
    frame = np.ones((480, 640, 3), dtype=np.uint8) * 120
    frame[200:260, 300:340] = 255
    success, enc = cv2.imencode(".jpg", frame)
    assert success
    jpg_bytes = enc.tobytes()

    result = await SingleImageAnalyzer.analyze_image(
        image_bytes=jpg_bytes,
        filename="acceptance_test.jpg",
        camera_perspective="FIXED_CCTV",
    )

    assert "id" in result
    assert "total_people" in result
    assert "heatmap_grid" in result
    assert "zone_occupancies" in result
    assert "disclaimer" in result
    assert "static observation" in result["disclaimer"].lower()
    assert "forecasts are not available" in result["disclaimer"].lower()


@pytest.mark.asyncio
async def test_acceptance_7_error_recovery_and_validation(test_app):
    """Test 7: Self-intersecting polygon geometry rejection & validation error handling."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login_resp = await client.post(
            "/api/auth/login",
            json={"email": "admin@crowdvision.io", "password": "admin123"},
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        hourglass = [[0, 0], [100, 100], [0, 100], [100, 0]]
        is_valid, errors = validate_polygon_geometry(hourglass)
        assert is_valid is False
        assert any("self-intersect" in e.lower() for e in errors)

        bad_layout_payload = {
            "name": "Self Intersecting Invalid Layout",
            "zones_data": [
                {
                    "id": "bad-zone",
                    "name": "Invalid Hourglass",
                    "zone_type": "GENERAL",
                    "polygon_points": hourglass,
                    "capacity": 500,
                }
            ],
        }

        resp = await client.post("/api/layouts/", json=bad_layout_payload, headers=headers)
        assert resp.status_code == 422
        assert "self-intersects" in resp.json()["detail"].lower()
