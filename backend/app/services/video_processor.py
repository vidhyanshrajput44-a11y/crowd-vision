"""Orchestrates asynchronous recorded video analysis jobs with OpenCV, YOLO, ByteTrack, prediction, risk, alerts, and AI agent integration."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import time
from typing import Any, Optional
import uuid

import cv2
import numpy as np
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.analytics.crowd_analytics import CrowdAnalyticsEngine, ZoneAnalyticsSnapshot
from app.analytics.zone_mapper import ZoneDefinition, ZoneMapper
from app.config import get_settings
from app.core.logging import get_logger
from app.cv.bytetrack import ByteTracker
from app.cv.camera_motion import CameraMotionCompensator
from app.cv.detector import PersonDetector, assess_footage_perspective
from app.cv.video_source import BaseVideoSource, SourceState, create_video_source
from app.database.models import (
    Alert,
    Camera,
    CrowdMetric,
    DetectionSummary,
    Event,
    Prediction,
    ProcessingJob,
    Recommendation,
    RiskAssessment,
    Task,
    Venue,
    VenueLayout,
    VideoFile,
    Zone,
)
from app.database.session import get_session_factory
from app.integrations.agent_client import AIAgentClient
from app.prediction.engine import PredictionEngine
from app.risk.alert_service import AlertService
from app.risk.engine import RiskEngine
from app.services.ws_manager import ws_manager

logger = get_logger("services.video_processor")

_shared_detector: Optional[PersonDetector] = None


def get_shared_detector() -> PersonDetector:
    global _shared_detector
    if _shared_detector is None:
        _shared_detector = PersonDetector()
    return _shared_detector


class VideoProcessor:
    """Orchestrates asynchronous recorded video analysis jobs with OpenCV, YOLO, ByteTrack, prediction, risk, alerts, and AI agent integration."""

    _active_jobs: dict[str, bool] = {}
    _paused_jobs: dict[str, bool] = {}
    _running_tasks: dict[str, asyncio.Task[Any]] = {}
    _latest_telemetry: dict[str, dict[str, Any]] = {}

    @classmethod
    def launch_job(
        cls,
        job_id: str,
        video_id: str,
        event_id: str,
        sample_fps: float = 0.2,
        camera_id: Optional[str] = None,
        layout_id: Optional[str] = None,
        camera_perspective: str = "FIXED_CCTV",
    ) -> None:
        cls._active_jobs[job_id] = True
        cls._paused_jobs[job_id] = False
        task = asyncio.create_task(
            cls.start_processing(
                job_id=job_id,
                video_id=video_id,
                event_id=event_id,
                sample_fps=sample_fps,
                camera_id=camera_id,
                layout_id=layout_id,
                camera_perspective=camera_perspective,
            )
        )
        cls._running_tasks[job_id] = task

    @classmethod
    def pause_processing(cls, job_id: str) -> bool:
        if job_id in cls._active_jobs:
            cls._paused_jobs[job_id] = True
            logger.info("Video processing paused", job_id=job_id)
            return True
        return False

    @classmethod
    def resume_processing(cls, job_id: str) -> bool:
        if job_id in cls._active_jobs:
            cls._paused_jobs[job_id] = False
            logger.info("Video processing resumed", job_id=job_id)
            return True
        return False

    @classmethod
    def is_paused(cls, job_id: str) -> bool:
        return cls._paused_jobs.get(job_id, False)

    @classmethod
    def stop_processing(cls, job_id: str) -> bool:
        if job_id in cls._active_jobs:
            cls._active_jobs[job_id] = False
            cls._paused_jobs.pop(job_id, None)
            task = cls._running_tasks.get(job_id)
            if task and not task.done():
                task.cancel()
            return True
        return False

    @classmethod
    def is_running(cls, job_id: str) -> bool:
        return cls._active_jobs.get(job_id, False)

    @classmethod
    def get_latest_telemetry(cls, key: str) -> Optional[dict[str, Any]]:
        return cls._latest_telemetry.get(key)

    @classmethod
    async def start_processing(
        cls,
        job_id: str,
        video_id: str,
        event_id: str,
        sample_fps: float = 0.2,
        camera_id: Optional[str] = None,
        layout_id: Optional[str] = None,
        camera_perspective: str = "FIXED_CCTV",
    ) -> None:
        session_factory = get_session_factory()
        detector = get_shared_detector()
        agent_client = AIAgentClient()

        logger.info("Starting video processing job", job_id=job_id, video_id=video_id, sample_fps=sample_fps)

        async with session_factory() as session:
            job = await session.get(ProcessingJob, job_id)
            if not job:
                logger.error("Processing job not found", job_id=job_id)
                return
            job.status = "RUNNING"
            job.started_at = datetime.now(timezone.utc)
            job.detector_backend = detector.backend_name
            job.camera_perspective = camera_perspective
            if layout_id:
                job.layout_id = layout_id
            await session.commit()

            video_path = None
            if video_id:
                video = await session.get(VideoFile, video_id)
                if video:
                    video_path = video.stored_path

            event = await session.get(Event, event_id)
            venue_id = event.venue_id if event else None

            # Look up Task record for snapshot zones or configured video
            task = await session.get(Task, event_id)
            if not video_path and task and task.video_config:
                vcfg = task.video_config
                cand = vcfg.get("stored_path") or vcfg.get("source_uri") or vcfg.get("filename")
                if cand:
                    if os.path.exists(cand):
                        video_path = cand
                    elif (get_settings().videos_dir / Path(cand).name).exists():
                        video_path = str(get_settings().videos_dir / Path(cand).name)

            if not video_path and video_id:
                cand = get_settings().videos_dir / Path(video_id).name
                if cand.exists():
                    video_path = str(cand)

            if not video_path:
                default_file = get_settings().videos_dir / "sample_crowd_festival.mp4"
                if default_file.exists():
                    video_path = str(default_file)

            if not video_path:
                logger.error("No valid video source found for job", job_id=job_id)
                job.status = "FAILED"
                job.error_message = f"No valid video source found for {video_id or event_id}"
                await session.commit()
                return

            # Build zones & homography
            zone_defs: list[ZoneDefinition] = []
            calibration_homography = None

            if task and task.layout_snapshot and task.layout_snapshot.get("zones_data"):
                zone_defs = cls._build_zone_definitions_from_snapshot(task.layout_snapshot.get("zones_data", []))
                calibration_homography = task.layout_snapshot.get("calibration_homography")
            elif layout_id:
                layout = await session.get(VenueLayout, layout_id)
                if layout:
                    zone_defs = cls._build_zone_definitions_from_layout(layout)
                    calibration_homography = layout.calibration_homography
            elif venue_id:
                stmt = select(Venue).options(selectinload(Venue.zones).selectinload(Zone.capacity)).where(Venue.id == venue_id)
                venue = (await session.execute(stmt)).scalar_one_or_none()
                if venue:
                    zone_defs = cls._build_zone_definitions(venue.zones)
                    calibration_homography = venue.calibration_homography

        source = create_video_source(video_path, base_dir=get_settings().videos_dir)
        if not source.open():
            logger.error("Could not open video source", path=video_path)
            async with session_factory() as session:
                job = await session.get(ProcessingJob, job_id)
                if job:
                    job.status = "FAILED"
                    job.error_message = f"Could not open video source: {video_path}"
                    await session.commit()
            return

        meta = source.metadata
        fps = meta.fps if meta and meta.fps > 0 else 25.0
        total_frames = meta.total_frames or 0
        video_w = meta.width or 1920
        video_h = meta.height or 1080
        duration = meta.duration_seconds or (float(total_frames) / fps if fps > 0 else 0.0)

        sample_step = max(1, int(round(fps / max(sample_fps, 0.05))))
        total_sampled_frames = max(1, total_frames // sample_step) if total_frames > 0 else 100

        mapper = ZoneMapper(zones=zone_defs, calibration_homography=calibration_homography)
        tracker = ByteTracker(track_high_thresh=0.45, track_low_thresh=0.20, match_iou_thresh=0.2)
        analytics_engine = CrowdAnalyticsEngine(mapper)
        analytics_engine.perspective = camera_perspective
        prediction_engine = PredictionEngine(event_id=event_id, horizons=[30, 60, 180, 300])
        risk_engine = RiskEngine(event_id=event_id)
        alert_service = AlertService()
        motion_compensator = CameraMotionCompensator()

        frame_idx = 0
        sampled_count = 0
        max_people = 0
        total_inference_ms = 0.0
        recs_cooldown: dict[tuple[str, str], float] = {}

        try:
            while cls._active_jobs.get(job_id, False):
                if cls._paused_jobs.get(job_id, False):
                    await asyncio.sleep(0.2)
                    continue

                v_frame = source.read_frame()
                if v_frame is None:
                    if source.state in (SourceState.STOPPED, SourceState.FAILED):
                        break
                    await asyncio.sleep(0.01)
                    continue

                frame = v_frame.frame
                v_ts = v_frame.timestamp_sec
                frame_idx = v_frame.frame_index

                if frame_idx % sample_step != 0:
                    continue

                dt = float(sample_step) / fps

                # Optical flow motion compensation
                _, motion_metrics = motion_compensator.update(frame)

                # Detection
                t_det0 = time.perf_counter()
                detections, inf_ms = detector.detect(frame, perspective=camera_perspective)
                total_inference_ms += inf_ms

                # Tracking
                tracked = tracker.update(detections, dt=dt, perspective=camera_perspective)
                people_count = len(tracked)
                max_people = max(max_people, people_count)

                # Analytics
                snapshots, serialized_dets, heatmap_grid = analytics_engine.compute_frame_analytics(
                    tracked_people=tracked,
                    frame_w=video_w,
                    frame_h=video_h,
                    video_timestamp_sec=v_ts,
                    dt_sec=dt,
                )
                accum_grid = analytics_engine.get_accumulated_heatmap_grid()

                # Predictions
                predictions = prediction_engine.update_and_predict(
                    snapshots=snapshots,
                    video_timestamp_sec=v_ts,
                )

                # Predictive heatmap for horizons (+60s, +180s, +300s)
                growth_by_zone = {p.zone_id: p.predicted_change_pct / 100.0 for p in predictions if p.horizon_seconds == 60}
                predicted_heatmaps = {
                    "30s": mapper.generate_predicted_heatmap_grid(heatmap_grid, growth_by_zone, horizon_sec=30),
                    "60s": mapper.generate_predicted_heatmap_grid(heatmap_grid, growth_by_zone, horizon_sec=60),
                    "180s": mapper.generate_predicted_heatmap_grid(heatmap_grid, growth_by_zone, horizon_sec=180),
                    "300s": mapper.generate_predicted_heatmap_grid(heatmap_grid, growth_by_zone, horizon_sec=300),
                }

                # Risk assessments & alerts
                risk_assessments = risk_engine.evaluate_frame_risk(
                    snapshots=snapshots,
                    predictions=predictions,
                    video_timestamp_sec=v_ts,
                )

                new_alerts = alert_service.process_risk_assessments(
                    risk_assessments=risk_assessments,
                    snapshots=snapshots,
                    video_timestamp_sec=v_ts,
                )

                sampled_count += 1
                progress = min(100.0, (float(sampled_count) / float(total_sampled_frames)) * 100.0)

                # Persist batch to DB
                async with session_factory() as session:
                    # Metrics
                    for s in snapshots:
                        metric = CrowdMetric(
                            event_id=event_id,
                            job_id=job_id,
                            zone_id=s.zone_id,
                            zone_name=s.zone_name,
                            video_timestamp_sec=s.video_timestamp_sec,
                            people_count=s.people_count,
                            occupancy_ratio=s.occupancy_ratio,
                            density_value=s.density_value,
                            density_unit=s.density_unit,
                            inflow_rate=s.inflow_rate,
                            outflow_rate=s.outflow_rate,
                            net_flow=s.net_flow,
                            avg_speed=s.avg_speed,
                            movement_direction=s.movement_direction,
                            crowd_increase_pct=s.crowd_increase_pct,
                            capacity_utilization_pct=s.capacity_utilization_pct,
                            is_bottleneck=s.is_bottleneck,
                            is_counterflow=s.is_counterflow,
                        )
                        session.add(metric)

                    # Summary
                    summary = DetectionSummary(
                        job_id=job_id,
                        event_id=event_id,
                        frame_index=frame_idx,
                        video_timestamp_sec=v_ts,
                        total_people=people_count,
                        inference_ms=inf_ms,
                        detections=serialized_dets,
                        heatmap_grid=heatmap_grid,
                    )
                    session.add(summary)

                    # Predictions
                    for p in predictions:
                        pred_record = Prediction(
                            event_id=event_id,
                            job_id=job_id,
                            zone_id=p.zone_id,
                            zone_name=p.zone_name,
                            video_timestamp_sec=p.video_timestamp_sec,
                            horizon_seconds=p.horizon_seconds,
                            current_occupancy=p.current_occupancy,
                            current_density=p.current_density,
                            predicted_occupancy=p.predicted_occupancy,
                            predicted_density=p.predicted_density,
                            predicted_change_pct=p.predicted_change_pct,
                            estimated_trend=p.estimated_trend,
                            risk_category=p.risk_category,
                            confidence=p.confidence,
                            is_experimental=p.is_experimental,
                            model_name=p.model_name,
                        )
                        session.add(pred_record)

                    # Risks
                    for r in risk_assessments:
                        risk_record = RiskAssessment(
                            event_id=event_id,
                            job_id=job_id,
                            zone_id=r.zone_id,
                            zone_name=r.zone_name,
                            video_timestamp_sec=r.video_timestamp_sec,
                            risk_level=r.risk_level,
                            reason=r.reason,
                            supporting_measurements=r.supporting_measurements,
                            monitoring_priority=r.monitoring_priority,
                            requires_human_review=r.requires_human_review,
                        )
                        session.add(risk_record)

                    # Alerts
                    for a in new_alerts:
                        z_id = a.get("zone_id") if isinstance(a, dict) else getattr(a, "zone_id", None)
                        z_name = a.get("zone_name") if isinstance(a, dict) else getattr(a, "zone_name", "")
                        cat = a.get("category", "CROWD_DENSITY") if isinstance(a, dict) else getattr(a, "category", "CROWD_DENSITY")
                        sev = a.get("severity", "HIGH") if isinstance(a, dict) else getattr(a, "severity", "HIGH")
                        tit = a.get("title", "High Risk Alert") if isinstance(a, dict) else getattr(a, "title", "High Risk Alert")
                        desc = a.get("description", "") if isinstance(a, dict) else getattr(a, "description", "")
                        supp = a.get("supporting_measurements", {}) if isinstance(a, dict) else getattr(a, "supporting_measurements", {})
                        alert_record = Alert(
                            event_id=event_id,
                            zone_id=z_id,
                            zone_name=z_name,
                            category=cat,
                            severity=sev,
                            title=tit,
                            description=desc,
                            supporting_measurements=supp,
                            status="ACTIVE",
                            video_timestamp_sec=v_ts,
                            source="RISK_ENGINE",
                        )
                        session.add(alert_record)

                    # Update job progress
                    await session.execute(
                        update(ProcessingJob)
                        .where(ProcessingJob.id == job_id)
                        .values(
                            frames_processed=sampled_count,
                            total_sampled_frames=total_sampled_frames,
                            progress_pct=round(progress, 1),
                            processing_fps=round(float(sampled_count) / max(time.perf_counter() - t_det0, 0.1), 2),
                            avg_inference_ms=round(total_inference_ms / max(sampled_count, 1), 2),
                            max_people_detected=max_people,
                        )
                    )
                    await session.commit()

                # Live WebSocket Broadcast
                ws_payload = {
                    "type": "FRAME_UPDATE",
                    "job_id": job_id,
                    "event_id": event_id,
                    "frame_index": frame_idx,
                    "video_timestamp_sec": round(v_ts, 2),
                    "progress_pct": round(progress, 1),
                    "total_people": people_count,
                    "frame_w": video_w,
                    "frame_h": video_h,
                    "perspective": camera_perspective,
                    "detections": serialized_dets,
                    "heatmap_grid": heatmap_grid,
                    "accumulated_heatmap_grid": accum_grid,
                    "predicted_heatmaps": predicted_heatmaps,
                    "snapshots": [
                        {
                            "zone_id": s.zone_id,
                            "zone_name": s.zone_name,
                            "people_count": s.people_count,
                            "occupancy_ratio": s.occupancy_ratio,
                            "density_value": s.density_value,
                            "density_unit": s.density_unit,
                            "inflow_rate": s.inflow_rate,
                            "outflow_rate": s.outflow_rate,
                            "net_flow": s.net_flow,
                            "avg_speed": s.avg_speed,
                            "movement_direction": s.movement_direction,
                            "is_bottleneck": s.is_bottleneck,
                            "is_counterflow": s.is_counterflow,
                            "crowd_increase_pct": s.crowd_increase_pct,
                            "capacity_utilization_pct": s.capacity_utilization_pct,
                        }
                        for s in snapshots
                    ],
                    "predictions": [
                        {
                            "zone_id": p.zone_id,
                            "horizon_seconds": p.horizon_seconds,
                            "predicted_occupancy": p.predicted_occupancy,
                            "predicted_change_pct": p.predicted_change_pct,
                            "estimated_trend": p.estimated_trend,
                            "risk_category": p.risk_category,
                            "confidence": p.confidence,
                        }
                        for p in predictions
                    ],
                    "risks": [
                        {
                            "zone_id": r.zone_id,
                            "risk_level": r.risk_level,
                            "reason": r.reason,
                            "monitoring_priority": r.monitoring_priority,
                        }
                        for r in risk_assessments
                    ],
                    "alerts": [
                        asdict(a) if is_dataclass(a) else (a if isinstance(a, dict) else a.__dict__)
                        for a in new_alerts
                    ],
                }
                cls._latest_telemetry[event_id] = ws_payload
                cls._latest_telemetry[job_id] = ws_payload

                await ws_manager.broadcast(event_id, ws_payload)

                # Dispatch analytics & recommendations to AI Agent (async background non-blocking)
                await cls._dispatch_to_ai_agent(
                    agent_client=agent_client,
                    event_id=event_id,
                    video_timestamp_sec=v_ts,
                    snapshots=snapshots,
                    predictions=predictions,
                    risks=risk_assessments,
                    recs_cooldown=recs_cooldown,
                )

                frame_idx += 1
                # Pace the stream processing to provide real-time playback experience to UI
                pace = min(0.35, max(0.04, 1.0 / max(sample_fps, 0.1)))
                await asyncio.sleep(pace)

            source.close()

            # Mark job complete if not explicitly stopped
            async with session_factory() as session:
                job = await session.get(ProcessingJob, job_id)
                if job:
                    if job.status != "STOPPED":
                        job.status = "COMPLETED"
                        job.progress_pct = 100.0
                    job.completed_at = datetime.now(timezone.utc)
                task = await session.get(Task, event_id)
                if task and job and job.status == "COMPLETED":
                    task.state = "COMPLETED"
                    task.updated_at = datetime.now(timezone.utc)
                await session.commit()

            await ws_manager.broadcast(
                event_id,
                {
                    "type": "JOB_COMPLETED",
                    "job_id": job_id,
                    "event_id": event_id,
                    "total_sampled_frames": sampled_count,
                    "max_people_detected": max_people,
                },
            )
            logger.info("Video processing job completed", job_id=job_id, sampled_frames=sampled_count)

        except Exception as exc:
            logger.error("Exception during video processing", job_id=job_id, error=str(exc))
            if "source" in locals() and source is not None:
                source.close()
            async with session_factory() as session:
                job = await session.get(ProcessingJob, job_id)
                if job:
                    job.status = "FAILED"
                    job.error_message = str(exc)
                    await session.commit()
            await ws_manager.broadcast(
                event_id,
                {"type": "JOB_FAILED", "job_id": job_id, "error": str(exc)},
            )
        finally:
            cls._active_jobs[job_id] = False
            cls._paused_jobs.pop(job_id, None)
            cls._running_tasks.pop(job_id, None)

    @staticmethod
    def _build_zone_definitions_from_snapshot(zones_data: list[Any]) -> list[ZoneDefinition]:
        defs = []
        for z in zones_data:
            if isinstance(z, dict):
                zid = str(z.get("zone_id") or z.get("id") or uuid.uuid4())
                zname = str(z.get("zone_name") or z.get("name") or zid)
                raw_pts = z.get("polygon_points") or z.get("boundary_coordinates") or []
                pts = []
                for p in raw_pts:
                    if isinstance(p, dict) and "x" in p and "y" in p:
                        pts.append([float(p["x"]), float(p["y"])])
                    elif isinstance(p, (list, tuple)) and len(p) >= 2:
                        pts.append([float(p[0]), float(p[1])])
                cap = int(z.get("max_capacity") or z.get("capacity") or 50)
                area = float(z["area_sqm"]) if z.get("area_sqm") else None
                defs.append(
                    ZoneDefinition(
                        zone_id=zid,
                        name=zname,
                        polygon_points=pts,
                        capacity=cap,
                        area_sqm=area,
                        is_entry=bool(z.get("is_entry", False)),
                        is_exit=bool(z.get("is_exit", False)),
                        is_emergency_exit=bool(z.get("is_emergency_exit", False)),
                        adjacent_zone_ids=list(z.get("adjacent_zone_ids", [])),
                        color=str(z.get("color") or "#0d9488"),
                        monitoring_priority=str(z.get("monitoring_priority") or "ROUTINE"),
                    )
                )
        return defs

    @staticmethod
    def _build_zone_definitions(zones: list[Zone]) -> list[ZoneDefinition]:
        defs = []
        for z in zones:
            cap = z.capacity.max_capacity if z.capacity else 50
            area = z.capacity.area_sqm if z.capacity else None
            defs.append(
                ZoneDefinition(
                    zone_id=z.id,
                    name=z.name,
                    polygon_points=z.polygon_points or [],
                    capacity=cap,
                    area_sqm=area,
                    is_entry=z.is_entry,
                    is_exit=z.is_exit,
                    is_emergency_exit=z.is_emergency_exit,
                    adjacent_zone_ids=z.adjacent_zone_ids or [],
                    color=z.color or "#0d9488",
                )
            )
        return defs

    @staticmethod
    def _build_zone_definitions_from_layout(layout: VenueLayout) -> list[ZoneDefinition]:
        defs = []
        for z in layout.zones_data or []:
            if isinstance(z, dict):
                zid = str(z.get("zone_id") or z.get("id") or uuid.uuid4())
                zname = str(z.get("zone_name") or z.get("name") or zid)
                pts = z.get("polygon_points") or z.get("boundary_coordinates") or []
                cap = int(z.get("max_capacity") or z.get("capacity") or 50)
                area = float(z["area_sqm"]) if z.get("area_sqm") else None
                defs.append(
                    ZoneDefinition(
                        zone_id=zid,
                        name=zname,
                        polygon_points=pts,
                        capacity=cap,
                        area_sqm=area,
                        is_entry=bool(z.get("is_entry", False)),
                        is_exit=bool(z.get("is_exit", False)),
                        is_emergency_exit=bool(z.get("is_emergency_exit", False)),
                        adjacent_zone_ids=list(z.get("adjacent_zone_ids", [])),
                        color=str(z.get("color") or "#0d9488"),
                        monitoring_priority=str(z.get("monitoring_priority") or "ROUTINE"),
                    )
                )
        return defs

    @classmethod
    async def _dispatch_to_ai_agent(
        cls,
        agent_client: AIAgentClient,
        event_id: str,
        video_timestamp_sec: float,
        snapshots: list[ZoneAnalyticsSnapshot],
        predictions: list[Any],
        risks: list[Any],
        recs_cooldown: dict[tuple[str, str], float],
    ) -> None:
        if not agent_client._enabled():
            fallback_recs = cls._generate_fallback_recommendations(risks, video_timestamp_sec, recs_cooldown)
            if fallback_recs:
                await cls._save_recommendations(event_id, fallback_recs)
            return

        # Prepare payload for AI agent
        zones_payload = []
        for s in snapshots:
            matching_preds = [p for p in predictions if p.zone_id == s.zone_id]
            matching_risk = next((r for r in risks if r.zone_id == s.zone_id), None)
            zones_payload.append(
                {
                    "zone_id": s.zone_id,
                    "zone_name": s.zone_name,
                    "people_count": s.people_count,
                    "capacity": s.capacity,
                    "occupancy_ratio": s.occupancy_ratio,
                    "density_value": s.density_value,
                    "density_unit": s.density_unit,
                    "inflow_rate": s.inflow_rate,
                    "outflow_rate": s.outflow_rate,
                    "net_flow": s.net_flow,
                    "avg_speed": s.avg_speed,
                    "movement_direction": s.movement_direction,
                    "is_bottleneck": s.is_bottleneck,
                    "is_counterflow": s.is_counterflow,
                    "crowd_increase_pct": s.crowd_increase_pct,
                    "capacity_utilization_pct": s.capacity_utilization_pct,
                    "risk_level": matching_risk.risk_level if matching_risk else "NORMAL",
                    "predictions": [
                        {
                            "horizon_seconds": p.horizon_seconds,
                            "predicted_occupancy": p.predicted_occupancy,
                            "predicted_change_pct": p.predicted_change_pct,
                            "estimated_trend": p.estimated_trend,
                            "risk_category": p.risk_category,
                            "confidence": p.confidence,
                        }
                        for p in matching_preds
                    ],
                }
            )

        try:
            res = await agent_client.send_analytics(
                event_id=event_id,
                video_timestamp_sec=video_timestamp_sec,
                zones_data=zones_payload,
            )
            if res and "recommendations" in res:
                await cls._save_recommendations(event_id, res["recommendations"])
            elif not res:
                fallback_recs = cls._generate_fallback_recommendations(risks, video_timestamp_sec, recs_cooldown)
                if fallback_recs:
                    await cls._save_recommendations(event_id, fallback_recs)
        except Exception as exc:
            logger.debug("Failed dispatching to AI Agent", error=str(exc))
            fallback_recs = cls._generate_fallback_recommendations(risks, video_timestamp_sec, recs_cooldown)
            if fallback_recs:
                await cls._save_recommendations(event_id, fallback_recs)

    @staticmethod
    def _generate_fallback_recommendations(
        risks: list[Any],
        v_ts: float,
        cooldown_map: dict[tuple[str, str], float],
    ) -> list[dict[str, Any]]:
        recs = []
        for r in risks:
            if r.risk_level not in ("MODERATE", "HIGH", "CRITICAL"):
                continue

            key = (r.zone_id, r.risk_level)
            last_ts = cooldown_map.get(key)
            if last_ts is not None and abs(v_ts - last_ts) < 45.0:
                continue
            cooldown_map[key] = v_ts

            m = r.supporting_measurements or {}
            occ_pct = float(m.get("occupancy_ratio", 0.0)) * 100.0
            is_bottleneck = bool(m.get("is_bottleneck", False))
            is_counterflow = bool(m.get("is_counterflow", False))

            if r.risk_level == "CRITICAL":
                action = f"Initiate immediate crowd diversion from {r.zone_name}"
                reason = f"Critical congestion detected (occupancy {occ_pct:.1f}%). High surge hazard."
                priority = "P1_CRITICAL"
                team = "SECURITY_LEAD"
            elif r.risk_level == "HIGH":
                if is_bottleneck:
                    action = f"Deploy stewards to relieve bottleneck at {r.zone_name}"
                    reason = f"High congestion with restricted exit flow in {r.zone_name}."
                    priority = "P2_HIGH"
                    team = "GROUND_STEWARDS"
                elif is_counterflow:
                    action = f"Establish one-way pedestrian lanes in {r.zone_name}"
                    reason = "Significant opposing counterflow vectors detected."
                    priority = "P2_HIGH"
                    team = "SECURITY_OPERATOR"
                else:
                    action = f"Monitor access gates into {r.zone_name}"
                    reason = f"Approaching high risk threshold ({occ_pct:.1f}% capacity)."
                    priority = "P2_HIGH"
                    team = "OPERATIONS"
            else:
                action = f"Increase surveillance and prepare buffer zones for {r.zone_name}"
                reason = "Moderate crowd accumulation trend observed."
                priority = "P3_MODERATE"
                team = "MONITORING"

            recs.append(
                {
                    "zone_id": r.zone_id,
                    "zone_name": r.zone_name,
                    "action": action,
                    "reason": reason,
                    "priority": priority,
                    "suggested_team": team,
                    "supporting_data": [f"Occupancy: {occ_pct:.1f}%", f"Risk: {r.risk_level}"],
                    "source": "RULE_FALLBACK",
                }
            )
        return recs

    @staticmethod
    async def _save_recommendations(event_id: str, recs: list[dict[str, Any]]) -> None:
        session_factory = get_session_factory()
        async with session_factory() as session:
            for rec in recs:
                rec_record = Recommendation(
                    event_id=event_id,
                    zone_id=rec.get("zone_id"),
                    zone_name=rec.get("zone_name"),
                    action=rec.get("action", ""),
                    reason=rec.get("reason", ""),
                    priority=rec.get("priority", "P3_MODERATE"),
                    suggested_team=rec.get("suggested_team", "OPERATIONS"),
                    supporting_data=rec.get("supporting_data", []),
                    review_status="PENDING",
                    source=rec.get("source", "AI_AGENT"),
                )
                session.add(rec_record)
            await session.commit()
