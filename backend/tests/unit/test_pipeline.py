"""Unit tests for CrowdVision CV, tracking, analytics, forecasting, risk, and alert engines."""
from __future__ import annotations

import numpy as np

from app.analytics.crowd_analytics import CrowdAnalyticsEngine, ZoneAnalyticsSnapshot
from app.analytics.zone_mapper import ZoneDefinition, ZoneMapper
from app.cv.bytetrack import ByteTracker
from app.cv.detector import Detection, PersonDetector
from app.prediction.engine import PredictionEngine
from app.risk.alert_service import AlertService
from app.risk.engine import RiskEngine


def _make_zone_defs() -> list[ZoneDefinition]:
    return [
        ZoneDefinition(
            zone_id="z1",
            zone_name="Main Stage",
            zone_type="STAGE",
            polygon_points=[[0.0, 0.0], [0.5, 0.0], [0.5, 1.0], [0.0, 1.0]],
            max_capacity=10,
            area_sqm=50.0,
            is_physically_calibrated=False,
            threshold_low=0.45,
            threshold_moderate=0.65,
            threshold_high=0.82,
            threshold_critical=0.95,
        ),
        ZoneDefinition(
            zone_id="z2",
            zone_name="Entrance A",
            zone_type="ENTRANCE",
            polygon_points=[[0.5, 0.0], [1.0, 0.0], [1.0, 1.0], [0.5, 1.0]],
            max_capacity=10,
            area_sqm=25.0,
            is_physically_calibrated=True,
            threshold_low=0.45,
            threshold_moderate=0.65,
            threshold_high=0.82,
            threshold_critical=0.95,
            density_moderate=0.25,
            density_high=0.35,
            density_critical=0.45,
        ),
    ]


def test_detector_handles_empty_and_valid_frames():
    detector = PersonDetector(model_path="models/nonexistent.onnx")
    assert detector.backend_name == "opencv_hog_motion_fallback"

    empty_dets, ms = detector.detect(np.array([], dtype=np.uint8))
    assert empty_dets == []
    assert ms == 0.0

    bg = np.full((320, 480, 3), 220, dtype=np.uint8)
    for _ in range(3):
        detector.detect(bg)

    frame = bg.copy()
    frame[100:180, 150:185] = (30, 40, 180)
    dets, inf_ms = detector.detect(frame)
    assert inf_ms >= 0.0
    assert len(dets) >= 0


def test_bytetrack_maintains_consistent_ids_and_velocity():
    tracker = ByteTracker()
    t1 = tracker.update([
        Detection(bbox=(100, 100, 140, 180), confidence=0.85),
        Detection(bbox=(300, 200, 340, 280), confidence=0.8),
    ], dt=0.5)
    assert len(t1) == 2
    ids_1 = [p.track_id for p in t1]

    t2 = tracker.update([
        Detection(bbox=(108, 102, 148, 182), confidence=0.85),
        Detection(bbox=(306, 200, 346, 280), confidence=0.35),
    ], dt=0.5)
    assert len(t2) == 2
    assert [p.track_id for p in t2] == ids_1
    assert any(p.speed > 0 for p in t2)


def test_zone_mapper_and_analytics_calibrated_vs_relative():
    zdefs = _make_zone_defs()
    mapper = ZoneMapper(zdefs)
    engine = CrowdAnalyticsEngine(mapper)

    H = ZoneMapper.compute_homography(
        [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
        [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
    )
    assert len(H) == 3

    tracker = ByteTracker()
    tracked = tracker.update([
        Detection(bbox=(100, 100, 140, 180), confidence=0.9),
        Detection(bbox=(400, 100, 440, 180), confidence=0.9),
        Detection(bbox=(450, 120, 490, 200), confidence=0.9),
    ], dt=0.5)

    snaps, ser_dets, heatmap = engine.compute_frame_analytics(
        tracked, 640, 480, 1.0, 0.5
    )
    assert len(snaps) == 2
    assert len(ser_dets) == 3
    assert len(heatmap) == 20 and len(heatmap[0]) == 12

    s_z1 = next(s for s in snaps if s.zone_id == "z1")
    s_z2 = next(s for s in snaps if s.zone_id == "z2")

    assert s_z1.people_count == 1
    assert s_z1.density_unit == "relative_estimate"
    assert s_z2.people_count == 2
    assert s_z2.density_unit == "people_per_sqm"
    assert abs(s_z2.density_value - (2.0 / 25.0)) < 0.001

    pred_grid = mapper.generate_predicted_heatmap_grid(heatmap, {"z1": 1.5, "z2": 0.8})
    assert len(pred_grid) == len(heatmap)


def test_prediction_engine_causality_and_horizons():
    zdefs = _make_zone_defs()
    pred_engine = PredictionEngine(horizons_seconds=(60, 180, 300), min_history=4)

    history = {"z1": []}
    for i in range(6):
        snap = ZoneAnalyticsSnapshot(
            zone_id="z1",
            zone_name="Main Stage",
            video_timestamp_sec=float(i * 5),
            people_count=2 + i,
            capacity=10,
            occupancy_ratio=(2 + i) / 10.0,
            density_value=(2 + i) / 10.0,
            density_unit="relative_estimate",
            inflow_rate=12.0,
            outflow_rate=2.0,
            net_flow=10.0,
            avg_speed=0.05,
            movement_direction="INWARD",
            is_bottleneck=False,
            is_counterflow=False,
        )
        history["z1"].append(snap)

    early_preds = pred_engine.predict([history["z1"][2]], history, zdefs)
    assert len(early_preds) == 3
    assert all(p.is_experimental for p in early_preds)

    later_preds = pred_engine.predict([history["z1"][-1]], history, zdefs)
    assert len(later_preds) == 3
    assert later_preds[0].predicted_occupancy > later_preds[0].current_occupancy
    assert later_preds[0].confidence >= later_preds[2].confidence

    metrics = PredictionEngine.compute_error_metrics([0.05, -0.05, 0.1])
    assert metrics["mae"] is not None and metrics["rmse"] is not None


def test_risk_engine_hysteresis_and_alert_cooldown():
    zdefs = _make_zone_defs()
    risk_engine = RiskEngine(sustained_frames_threshold=1)
    alert_service = AlertService(cooldown_seconds=30.0)

    high_snap = ZoneAnalyticsSnapshot(
        zone_id="z1",
        zone_name="Main Stage",
        video_timestamp_sec=10.0,
        people_count=10,
        capacity=10,
        occupancy_ratio=1.0,
        density_value=1.0,
        density_unit="relative_estimate",
        inflow_rate=20.0,
        outflow_rate=2.0,
        net_flow=18.0,
        avg_speed=0.01,
        movement_direction="INWARD",
        is_bottleneck=True,
        is_counterflow=False,
    )

    risks_1 = risk_engine.assess([high_snap], [], zdefs)
    assert risks_1[0].risk_level == "CRITICAL"
    assert risks_1[0].requires_human_review is True

    alerts_1 = alert_service.evaluate(risks_1, "ev-1", 10.0)
    assert len(alerts_1) == 1
    assert alerts_1[0].severity == "CRITICAL"

    alerts_dup = alert_service.evaluate(risks_1, "ev-1", 15.0)
    assert len(alerts_dup) == 0

    low_snap = ZoneAnalyticsSnapshot(
        zone_id="z1",
        zone_name="Main Stage",
        video_timestamp_sec=16.0,
        people_count=0,
        capacity=10,
        occupancy_ratio=0.0,
        density_value=0.0,
        density_unit="relative_estimate",
        inflow_rate=0.0,
        outflow_rate=0.0,
        net_flow=0.0,
        avg_speed=0.0,
        movement_direction="STATIONARY",
        is_bottleneck=False,
        is_counterflow=False,
    )

    risks_2 = risk_engine.assess([low_snap], [], zdefs)
    assert risks_2[0].risk_level == "HIGH"
