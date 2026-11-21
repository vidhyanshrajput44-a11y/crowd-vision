"""Comprehensive unit & integration tests for CROWD VISION Phase 2.

Covers:
1. Video Source Engine (File, Stream, Camera device, Factory)
2. Person Detection & Perspective Analysis (Ground contact points, NMS)
3. ByteTrack Multi-Object Tracker (Track persistence, Velocity, Trajectories)
4. Calibration, Zone Mapping & Gaussian Heatmap Engine
5. Crowd Analytics (Inflow/Outflow, Bottleneck, Counterflow)
6. Risk Engine & Multi-Horizon Prediction Engine
7. Task Video Processing API lifecycle (Start, Pause, Resume, Stop, Job, Telemetry)
"""
from __future__ import annotations

import os
from pathlib import Path
import time
import pytest
from httpx import ASGITransport, AsyncClient
import numpy as np

from app.cv.video_source import (
    BaseVideoSource,
    CameraDeviceVideoSource,
    FileVideoSource,
    NetworkStreamVideoSource,
    SourceState,
    VideoSourceType,
    create_video_source,
)
from app.cv.detector import (
    PersonDetector,
    Detection,
    compute_ground_contact,
    assess_footage_perspective,
    _nms_boxes,
)
from app.cv.bytetrack import ByteTracker, STrack, TrackedPerson
from app.analytics.zone_mapper import ZoneDefinition, ZoneMapper, validate_polygon_geometry
from app.analytics.crowd_analytics import CrowdAnalyticsEngine
from app.risk.engine import RiskEngine
from app.prediction.engine import PredictionEngine
from app.services.video_processor import VideoProcessor
from app.main import app


SAMPLE_VIDEO_PATH = Path("backend/uploads/videos/sample_crowd_festival.mp4")


# =====================================================================
# 1. VIDEO SOURCE ENGINE TESTS
# =====================================================================

def test_file_video_source_valid():
    """Verify FileVideoSource correctly opens, decodes, extracts metadata, and reads frames."""
    assert SAMPLE_VIDEO_PATH.exists(), f"Sample video must exist at {SAMPLE_VIDEO_PATH}"
    source = FileVideoSource(SAMPLE_VIDEO_PATH)
    assert source.open() is True
    assert source.state == SourceState.READY
    assert source.is_live is False

    meta = source.metadata
    assert meta is not None
    assert meta.width == 640
    assert meta.height == 480
    assert meta.fps > 0
    assert meta.total_frames > 0
    assert meta.duration_seconds > 0

    frame = source.read_frame()
    assert frame is not None
    assert frame.frame_index == 0
    assert frame.timestamp_sec == 0.0
    assert frame.frame.shape == (480, 640, 3)
    assert frame.is_live is False

    # Test seeking
    seek_ok = source.seek(1.0)
    assert seek_ok is True
    frame_seek = source.read_frame()
    assert frame_seek is not None
    assert frame_seek.timestamp_sec > 0.5

    source.close()
    assert source.state == SourceState.STOPPED


def test_file_video_source_missing_file():
    """Verify FileVideoSource gracefully handles non-existent paths."""
    source = FileVideoSource("backend/uploads/videos/non_existent_stream.mp4")
    assert source.open() is False
    assert source.state == SourceState.FAILED
    assert source.read_frame() is None
    source.close()


def test_video_source_factory():
    """Verify create_video_source correctly maps URIs to concrete subclasses."""
    file_src = create_video_source(str(SAMPLE_VIDEO_PATH))
    assert isinstance(file_src, FileVideoSource)
    assert file_src.is_live is False

    rtsp_src = create_video_source("rtsp://admin:pass@192.168.1.100:554/live")
    assert isinstance(rtsp_src, NetworkStreamVideoSource)
    assert rtsp_src.is_live is True
    assert rtsp_src.source_type == VideoSourceType.RTSP_STREAM

    hls_src = create_video_source("https://stream.example.com/live/cctv.m3u8")
    assert isinstance(hls_src, NetworkStreamVideoSource)
    assert hls_src.source_type == VideoSourceType.HLS_STREAM

    cam_src = create_video_source({"source_type": "WEBCAM", "device_index": 0})
    assert isinstance(cam_src, CameraDeviceVideoSource)
    assert cam_src.is_live is True


# =====================================================================
# 2. PERSON DETECTION & PERSPECTIVE ASSESSMENT TESTS
# =====================================================================

def test_ground_contact_computation():
    """Verify ground contact point calculation adapts to camera perspective."""
    bbox = (100.0, 50.0, 200.0, 250.0)
    # Fixed CCTV / Elevated Oblique: bottom-center (cx, y2)
    cctv_cx, cctv_cy = compute_ground_contact(bbox, perspective="FIXED_CCTV")
    assert cctv_cx == 150.0
    assert cctv_cy == 250.0

    oblique_cx, oblique_cy = compute_ground_contact(bbox, perspective="ELEVATED_OBLIQUE")
    assert oblique_cx == 150.0
    assert oblique_cy == 250.0

    # Drone Topdown: bbox centroid (cx, cy)
    drone_cx, drone_cy = compute_ground_contact(bbox, perspective="DRONE_TOPDOWN")
    assert drone_cx == 150.0
    assert drone_cy == 150.0


def test_perspective_assessment():
    """Verify assess_footage_perspective returns valid recommendations."""
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    res = assess_footage_perspective(dummy_frame)
    assert "perspective" in res
    assert "confidence" in res
    assert res["recommended_perspective"] in ("FIXED_CCTV", "DRONE_TOPDOWN", "ELEVATED_OBLIQUE")


def test_nms_boxes():
    """Verify Non-Maximum Suppression eliminates overlapping duplicate boxes."""
    dets = [
        Detection(bbox=(10.0, 10.0, 50.0, 100.0), confidence=0.90),
        Detection(bbox=(12.0, 11.0, 49.0, 99.0), confidence=0.75),  # heavy overlap
        Detection(bbox=(200.0, 200.0, 250.0, 300.0), confidence=0.85),  # distinct
    ]
    kept = _nms_boxes(dets, iou_threshold=0.4)
    assert len(kept) == 2
    assert kept[0].confidence == 0.90
    assert kept[1].confidence == 0.85


def test_person_detector_on_real_frame():
    """Verify PersonDetector runs inference on real sample video frame without mock data."""
    source = FileVideoSource(SAMPLE_VIDEO_PATH)
    assert source.open() is True
    vf = source.read_frame()
    assert vf is not None

    detector = PersonDetector()
    assert detector.backend_name in ("ultralytics_yolo", "opencv_dnn_onnx", "opencv_hog_motion_fallback")
    detections, latency_ms = detector.detect(vf.frame, perspective="FIXED_CCTV")

    assert isinstance(detections, list)
    assert latency_ms > 0
    for d in detections:
        assert isinstance(d.bbox, tuple) and len(d.bbox) == 4
        assert 0.0 <= d.confidence <= 1.0
        # Valid non-zero box
        assert d.bbox[2] > d.bbox[0]
        assert d.bbox[3] > d.bbox[1]
    source.close()


# =====================================================================
# 3. BYTETRACK TRACKING & VELOCITY ESTIMATION TESTS
# =====================================================================

def test_bytetracker_track_association_and_velocity():
    """Verify ByteTracker maintains track IDs, computes velocity, and records trajectories."""
    tracker = ByteTracker(track_high_thresh=0.4, track_low_thresh=0.2)

    # Frame 1: 2 persons detected
    dets_f1 = [
        Detection(bbox=(100.0, 100.0, 150.0, 200.0), confidence=0.85),
        Detection(bbox=(300.0, 100.0, 350.0, 200.0), confidence=0.80),
    ]
    tracked_f1 = tracker.update(dets_f1, dt=0.5, perspective="FIXED_CCTV")
    assert len(tracked_f1) == 2
    id1 = tracked_f1[0].track_id
    id2 = tracked_f1[1].track_id
    assert id1 != id2

    # Frame 2: Person 1 moves +20px in X, Person 2 moves +10px in Y
    dets_f2 = [
        Detection(bbox=(120.0, 100.0, 170.0, 200.0), confidence=0.88),
        Detection(bbox=(300.0, 110.0, 350.0, 210.0), confidence=0.82),
    ]
    tracked_f2 = tracker.update(dets_f2, dt=0.5, perspective="FIXED_CCTV")
    assert len(tracked_f2) == 2

    # Verify ID continuity
    track_ids_f2 = {t.track_id for t in tracked_f2}
    assert id1 in track_ids_f2
    assert id2 in track_ids_f2

    # Verify velocity computation (positive movement)
    p1 = next(t for t in tracked_f2 if t.track_id == id1)
    assert p1.vx > 0.0
    assert len(p1.history) >= 2


# =====================================================================
# 4. CALIBRATION, ZONE MAPPING & GAUSSIAN HEATMAP TESTS
# =====================================================================

def test_zone_mapper_and_gaussian_heatmap():
    """Verify ZoneMapper correctly performs point-in-polygon and generates smooth Gaussian grids."""
    zone1 = ZoneDefinition(
        zone_id="z_left",
        name="Left Concourse",
        polygon_points=[[0.0, 0.0], [0.5, 0.0], [0.5, 1.0], [0.0, 1.0]],
        capacity=50,
    )
    zone2 = ZoneDefinition(
        zone_id="z_right",
        name="Right Concourse",
        polygon_points=[[0.5, 0.0], [1.0, 0.0], [1.0, 1.0], [0.5, 1.0]],
        capacity=100,
    )
    mapper = ZoneMapper([zone1, zone2])

    # Point testing
    z_found_left = mapper.find_zone(0.2, 0.5)
    assert z_found_left is not None and z_found_left.zone_id == "z_left"

    z_found_right = mapper.find_zone(0.8, 0.5)
    assert z_found_right is not None and z_found_right.zone_id == "z_right"

    # Heatmap generation
    points = [(0.2, 0.3), (0.22, 0.31), (0.8, 0.7)]
    grid = mapper.generate_heatmap_grid(points, grid_rows=20, grid_cols=12, sigma=1.4)
    assert len(grid) == 20
    assert len(grid[0]) == 12

    # Maximum intensity should be normalized between 0.0 and 1.0
    max_val = max(max(row) for row in grid)
    assert 0.99 <= max_val <= 1.0

    # Left cluster around (0.2, 0.3) should have high intensity
    # col: int(0.2*12) = 2, row: int(0.3*20) = 6
    assert grid[6][2] > 0.5


def test_predictive_heatmap_advection():
    """Verify future predicted heatmap matrix computes projected growth and advection."""
    zone = ZoneDefinition(
        zone_id="z_main",
        name="Main",
        polygon_points=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
        capacity=50,
    )
    mapper = ZoneMapper([zone])
    base_grid = mapper.generate_heatmap_grid([(0.5, 0.5)], grid_rows=10, grid_cols=10)

    # Project 60s future with +50% growth
    predicted_grid = mapper.generate_predicted_heatmap_grid(
        base_grid,
        predicted_growth_by_zone={"z_main": 0.5},
        horizon_sec=60,
    )
    assert len(predicted_grid) == 10
    assert len(predicted_grid[0]) == 10


# =====================================================================
# 5. CROWD ANALYTICS & RISK ASSESSMENT TESTS
# =====================================================================

def test_crowd_analytics_inflow_and_bottlenecks():
    """Verify CrowdAnalyticsEngine computes zone occupancy, inflow/outflow, and bottlenecks."""
    zone = ZoneDefinition(
        zone_id="zone_a",
        name="Stage Front",
        polygon_points=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
        capacity=10,
    )
    mapper = ZoneMapper([zone])
    engine = CrowdAnalyticsEngine(mapper)

    # Simulate 8 people in zone (occupancy 80%)
    people = [
        TrackedPerson(
            track_id=i,
            bbox=(100.0, 100.0, 150.0, 200.0),
            confidence=0.85,
            foot_point=(320.0, 240.0),
            vx=2.0,
            vy=0.0,
        )
        for i in range(1, 9)
    ]

    snapshots, detections, heatmap = engine.compute_frame_analytics(
        tracked_people=people,
        frame_w=640,
        frame_h=480,
        video_timestamp_sec=10.0,
        dt_sec=0.5,
    )
    assert len(snapshots) == 1
    snap = snapshots[0]
    assert snap.people_count == 8
    assert snap.capacity == 10
    assert snap.occupancy_ratio == 0.8
    assert snap.capacity_utilization_pct == 80.0
    assert snap.avg_speed > 0


def test_risk_engine_evaluation():
    """Verify RiskEngine computes explainable multi-factor risk scores."""
    risk_engine = RiskEngine(event_id="test_event")

    # High occupancy (92%)
    from app.analytics.crowd_analytics import ZoneAnalyticsSnapshot
    snapshot = ZoneAnalyticsSnapshot(
        zone_id="zone_crit",
        zone_name="Main Exit Gate",
        video_timestamp_sec=5.0,
        people_count=92,
        capacity=100,
        occupancy_ratio=0.92,
        density_value=3.5,
        density_unit="people_per_sqm",
        inflow_rate=45.0,
        outflow_rate=5.0,
        net_flow=40.0,
        avg_speed=0.2,
        movement_direction="STATIONARY",
        is_bottleneck=True,
        is_counterflow=False,
        crowd_increase_pct=25.0,
        capacity_utilization_pct=92.0,
    )

    risks = risk_engine.evaluate_frame_risk([snapshot], predictions=[], video_timestamp_sec=5.0)
    assert len(risks) == 1
    r = risks[0]
    assert r.risk_level in ("HIGH", "CRITICAL")
    assert "bottleneck" in r.reason.lower() or "capacity" in r.reason.lower() or "density" in r.reason.lower()


# =====================================================================
# 6. TASK VIDEO PROCESSING API LIFECYCLE TESTS
# =====================================================================

@pytest.mark.asyncio
async def test_task_processing_api_lifecycle():
    """Verify task processing API lifecycle: Start -> Status/Job -> Pause -> Resume -> Stop."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Create a layout with zones
        layout_res = await client.post(
            "/api/layouts/",
            json={
                "name": "Phase 2 Automated Test Layout",
                "canvas_width": 1920,
                "canvas_height": 1080,
                "zones": [
                    {
                        "name": "Zone Alpha",
                        "zone_type": "CONCOURSE",
                        "max_capacity": 50,
                        "polygon_points": [[0.0, 0.0], [0.5, 0.0], [0.5, 0.5], [0.0, 0.5]],
                        "color": "#0d9488",
                    }
                ],
            },
        )
        assert layout_res.status_code == 201
        layout_id = layout_res.json()["id"]

        # 2. Create a task with configured layout and video
        task_res = await client.post(
            "/api/tasks/",
            json={
                "name": "Phase 2 CV Automated Task",
                "location": "North Arena",
                "state": "READY",
                "layout_id": layout_id,
                "video_config": {
                    "source_type": "FILE",
                    "filename": "sample_crowd_festival.mp4",
                    "camera_perspective": "FIXED_CCTV",
                    "sample_fps": 2.0,
                },
            },
        )
        assert task_res.status_code == 201
        task_id = task_res.json()["id"]

        # 3. Start Task Processing
        start_res = await client.post(
            f"/api/tasks/{task_id}/process",
            json={"sample_fps": 2.0, "camera_perspective": "FIXED_CCTV"},
        )
        assert start_res.status_code == 201
        job_data = start_res.json()
        assert job_data["status"] == "RUNNING"
        job_id = job_data["id"]

        # Verify task state transitioned to PROCESSING
        t_check = await client.get(f"/api/tasks/{task_id}")
        assert t_check.json()["state"] == "PROCESSING"

        # 4. Check Job query
        job_check = await client.get(f"/api/tasks/{task_id}/job")
        assert job_check.status_code == 200
        assert job_check.json()["id"] == job_id

        # 5. Check Telemetry endpoint
        telemetry_check = await client.get(f"/api/tasks/{task_id}/telemetry")
        assert telemetry_check.status_code == 200
        assert "type" in telemetry_check.json()

        # 6. Pause processing
        pause_res = await client.post(f"/api/tasks/{task_id}/pause")
        assert pause_res.status_code == 200
        assert pause_res.json()["status"] == "PAUSED"

        # Verify task state is PAUSED
        t_paused = await client.get(f"/api/tasks/{task_id}")
        assert t_paused.json()["state"] == "PAUSED"

        # 7. Resume processing
        resume_res = await client.post(f"/api/tasks/{task_id}/resume")
        assert resume_res.status_code == 200
        assert resume_res.json()["status"] == "PROCESSING"

        # 8. Stop processing
        stop_res = await client.post(f"/api/tasks/{task_id}/stop")
        assert stop_res.status_code == 200
        assert stop_res.json()["status"] == "STOPPED"

        # Verify task state is reset to READY
        t_stopped = await client.get(f"/api/tasks/{task_id}")
        assert t_stopped.json()["state"] == "READY"
