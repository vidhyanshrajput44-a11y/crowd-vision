"""Task management API routes for CROWD VISION Phase 1."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import (
    Alert,
    CrowdMetric,
    DetectionSummary,
    Event,
    ProcessingJob,
    RiskAssessment,
    Task,
    TaskHistory,
    Venue,
    VenueLayout,
    VideoFile,
)
from app.database.session import get_db
from app.schemas.api_schemas import (
    ProcessStartRequest,
    ProcessingJobResponse,
    TaskCreateRequest,
    TaskHistoryItemResponse,
    TaskResponse,
    TaskStateUpdateRequest,
    TaskUpdateRequest,
)
from app.services.video_processor import VideoProcessor, get_shared_detector

router = APIRouter(prefix="/tasks", tags=["Tasks"])

VALID_STATES = {"DRAFT", "CONFIGURING", "READY", "PROCESSING", "LIVE", "PAUSED", "COMPLETED", "FAILED"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _task_to_response(task: Task) -> TaskResponse:
    hist_items = []
    try:
        if task.history:
            hist_items = [TaskHistoryItemResponse.model_validate(h) for h in task.history]
    except Exception:
        hist_items = []

    v_cfg = dict(task.video_config or {})
    if not v_cfg.get("stream_url"):
        v_cfg["stream_url"] = f"/api/tasks/{task.id}/video/stream"
    if not v_cfg.get("playback_url"):
        v_cfg["playback_url"] = f"/api/tasks/{task.id}/video/stream"

    return TaskResponse(
        id=task.id,
        name=task.name,
        description=task.description,
        location=task.location,
        state=task.state,
        layout_id=task.layout_id,
        layout_snapshot=task.layout_snapshot or {},
        video_config=v_cfg,
        analysis_settings=task.analysis_settings or {},
        notes=task.notes,
        created_at=task.created_at,
        updated_at=task.updated_at,
        history=hist_items,
    )


async def _capture_layout_snapshot(db: AsyncSession, layout_id: Optional[str]) -> dict:
    if not layout_id:
        return {}
    layout = await db.get(VenueLayout, layout_id)
    if not layout:
        return {}
    return {
        "layout_id": layout.id,
        "name": layout.name,
        "description": layout.description,
        "version": layout.version,
        "canvas_width": layout.canvas_width,
        "canvas_height": layout.canvas_height,
        "scale_pixels_per_meter": layout.scale_pixels_per_meter,
        "background_image_url": layout.background_image_url,
        "zones_count": len(layout.zones_data or []),
        "zones_data": list(layout.zones_data or []),
        "snapshot_created_at": _utcnow().isoformat(),
    }


async def _sync_event_record(db: AsyncSession, task: Task) -> None:
    """Maintain synchronous Event record for backward-compatibility with CV pipeline."""
    ev = await db.get(Event, task.id)
    if not ev:
        venue = (await db.execute(select(Venue).limit(1))).scalars().first()
        venue_id = venue.id if venue else None
        ev = Event(
            id=task.id,
            venue_id=venue_id,
            name=task.name,
            event_type="SURVEILLANCE",
            status=task.state,
            settings=task.analysis_settings or {},
        )
        db.add(ev)
    else:
        ev.name = task.name
        ev.status = task.state
        if task.analysis_settings:
            ev.settings = task.analysis_settings


@router.get("", response_model=list[TaskResponse])
@router.get("/", response_model=list[TaskResponse], include_in_schema=False)
async def list_tasks(
    db: Annotated[AsyncSession, Depends(get_db)],
    state: Optional[str] = Query(None, description="Filter by task lifecycle state"),
    search: Optional[str] = Query(None, description="Search task name or location"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    stmt = select(Task).order_by(desc(Task.created_at)).limit(limit).offset(offset)
    if state and state.upper() != "ALL":
        stmt = stmt.where(Task.state == state.upper())
    if search:
        term = f"%{search.lower()}%"
        stmt = stmt.where(
            (Task.name.ilike(term)) | (Task.location.ilike(term)) | (Task.description.ilike(term))
        )

    tasks = (await db.execute(stmt)).scalars().all()

    # If no tasks exist in DB, migrate or backfill from existing events
    if not tasks and offset == 0 and not state and not search:
        events = (await db.execute(select(Event).order_by(desc(Event.created_at)))).scalars().all()
        for ev in events:
            # Look up layout
            layout = (await db.execute(select(VenueLayout).limit(1))).scalars().first()
            snapshot = await _capture_layout_snapshot(db, layout.id if layout else None)
            new_task = Task(
                id=ev.id,
                name=ev.name,
                description=f"Surveillance monitoring for {ev.name}",
                location="Venue Grounds",
                state=ev.status if ev.status in VALID_STATES else "READY",
                layout_id=layout.id if layout else None,
                layout_snapshot=snapshot,
                video_config={
                    "source_type": "FILE",
                    "camera_perspective": "DRONE_TOPDOWN",
                    "sample_fps": 2.0,
                },
                analysis_settings={"detector": "yolov8m", "density_method": "gaussian"},
            )
            db.add(new_task)
            hist = TaskHistory(
                task_id=new_task.id,
                event_type="INITIALIZED",
                details={"message": "Backfilled task from existing event record"},
            )
            db.add(hist)
        if events:
            await db.commit()
            tasks = (await db.execute(stmt)).scalars().all()

    return [_task_to_response(t) for t in tasks]


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_task(
    payload: TaskCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    target_state = payload.state.upper() if payload.state else "DRAFT"
    if target_state not in VALID_STATES:
        target_state = "DRAFT"

    layout_snapshot = payload.layout_snapshot
    if not layout_snapshot and payload.layout_id:
        layout_snapshot = await _capture_layout_snapshot(db, payload.layout_id)

    task = Task(
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        location=payload.location.strip() if payload.location else None,
        state=target_state,
        layout_id=payload.layout_id,
        layout_snapshot=layout_snapshot or {},
        video_config=payload.video_config or {},
        analysis_settings=payload.analysis_settings or {},
        notes=payload.notes,
    )
    db.add(task)
    await db.flush()

    # Record history
    hist = TaskHistory(
        task_id=task.id,
        event_type="CREATED",
        details={
            "name": task.name,
            "state": task.state,
            "layout_id": task.layout_id,
            "zones_count": len(task.layout_snapshot.get("zones_data", [])),
        },
    )
    db.add(hist)

    # Sync Event
    await _sync_event_record(db, task)

    await db.commit()
    await db.refresh(task)
    return _task_to_response(task)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    stmt = select(Task).where(Task.id == task_id).options(selectinload(Task.history))
    task = (await db.execute(stmt)).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return _task_to_response(task)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    payload: TaskUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    stmt = select(Task).where(Task.id == task_id).options(selectinload(Task.history))
    task = (await db.execute(stmt)).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    data = payload.model_dump(exclude_unset=True)
    changes = {}

    for field in ["name", "description", "location", "notes"]:
        if field in data and data[field] is not None:
            old_val = getattr(task, field)
            new_val = data[field].strip() if isinstance(data[field], str) else data[field]
            if old_val != new_val:
                setattr(task, field, new_val)
                changes[field] = {"old": old_val, "new": new_val}

    if "state" in data and data["state"]:
        new_state = data["state"].upper()
        if new_state in VALID_STATES and task.state != new_state:
            changes["state"] = {"old": task.state, "new": new_state}
            task.state = new_state

    if "video_config" in data and data["video_config"] is not None:
        task.video_config = data["video_config"]
        changes["video_config"] = "updated"

    if "analysis_settings" in data and data["analysis_settings"] is not None:
        task.analysis_settings = data["analysis_settings"]
        changes["analysis_settings"] = "updated"

    if "layout_id" in data and data["layout_id"] != task.layout_id:
        old_lid = task.layout_id
        task.layout_id = data["layout_id"]
        task.layout_snapshot = await _capture_layout_snapshot(db, task.layout_id)
        changes["layout"] = {"old_layout_id": old_lid, "new_layout_id": task.layout_id}
    elif "layout_snapshot" in data and data["layout_snapshot"] is not None:
        task.layout_snapshot = data["layout_snapshot"]
        changes["layout_snapshot"] = "custom_snapshot_updated"

    if changes:
        hist = TaskHistory(
            task_id=task.id,
            event_type="UPDATED",
            details={"changes": changes},
        )
        db.add(hist)
        await _sync_event_record(db, task)

    task.updated_at = _utcnow()
    await db.commit()
    await db.refresh(task)
    return _task_to_response(task)


@router.post("/{task_id}/duplicate", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_task(
    task_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    src = await db.get(Task, task_id)
    if not src:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source task not found")

    clone = Task(
        name=f"{src.name} (Copy)",
        description=src.description,
        location=src.location,
        state="DRAFT",
        layout_id=src.layout_id,
        layout_snapshot=dict(src.layout_snapshot or {}),
        video_config=dict(src.video_config or {}),
        analysis_settings=dict(src.analysis_settings or {}),
        notes=src.notes,
    )
    db.add(clone)
    await db.flush()

    hist = TaskHistory(
        task_id=clone.id,
        event_type="DUPLICATED",
        details={"source_task_id": src.id, "source_name": src.name},
    )
    db.add(hist)

    await _sync_event_record(db, clone)
    await db.commit()
    await db.refresh(clone)
    return TaskResponse.model_validate(clone)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    # Clean up associated event if present
    ev = await db.get(Event, task_id)
    if ev:
        await db.delete(ev)

    await db.delete(task)
    await db.commit()
    return None


@router.post("/{task_id}/state", response_model=TaskResponse)
async def change_task_state(
    task_id: str,
    payload: TaskStateUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    new_state = payload.state.upper()
    if new_state not in VALID_STATES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state '{new_state}'. Allowed: {', '.join(sorted(VALID_STATES))}",
        )

    # State validation checks
    if new_state in ("READY", "LIVE", "PROCESSING"):
        if not task.layout_snapshot or not task.layout_snapshot.get("zones_data"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Task cannot enter operational state without configured spatial layout and zones.",
            )

    old_state = task.state
    task.state = new_state
    task.updated_at = _utcnow()

    hist = TaskHistory(
        task_id=task.id,
        event_type="STATE_CHANGED",
        details={
            "old_state": old_state,
            "new_state": new_state,
            "reason": payload.reason or "Manual operator state transition",
        },
    )
    db.add(hist)

    await _sync_event_record(db, task)
    await db.commit()
    await db.refresh(task)
    return _task_to_response(task)


@router.get("/{task_id}/history", response_model=list[TaskHistoryItemResponse])
async def get_task_history(
    task_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    stmt = select(TaskHistory).where(TaskHistory.task_id == task_id).order_by(desc(TaskHistory.timestamp))
    items = (await db.execute(stmt)).scalars().all()
    return [TaskHistoryItemResponse.model_validate(h) for h in items]


@router.post("/{task_id}/process", response_model=ProcessingJobResponse, status_code=status.HTTP_201_CREATED)
async def start_task_processing(
    task_id: str,
    payload: Optional[ProcessStartRequest] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    # Validate spatial zones
    has_zones = bool(task.layout_snapshot and task.layout_snapshot.get("zones_data"))
    if not has_zones and task.layout_id:
        task.layout_snapshot = await _capture_layout_snapshot(db, task.layout_id)
        has_zones = bool(task.layout_snapshot and task.layout_snapshot.get("zones_data"))

    if not has_zones:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Task cannot enter processing without configured spatial layout and zones.",
        )

    # Determine video file / source
    video_id = (payload.video_id if payload and hasattr(payload, "video_id") else None) or (task.video_config or {}).get("video_id")
    video_record = None
    if video_id:
        video_record = await db.get(VideoFile, video_id)

    if not video_record:
        v_stmt = select(VideoFile).where(VideoFile.event_id == task.id).order_by(desc(VideoFile.created_at)).limit(1)
        video_record = (await db.execute(v_stmt)).scalar_one_or_none()

    if not video_record:
        v_any_stmt = select(VideoFile).order_by(desc(VideoFile.created_at)).limit(1)
        video_record = (await db.execute(v_any_stmt)).scalar_one_or_none()

    effective_vid_id = video_record.id if video_record else str(uuid.uuid4())
    effective_fps = video_record.fps if video_record else 25.0
    effective_frames = video_record.frame_count if video_record else 250

    sample_fps = (payload.sample_fps if payload and payload.sample_fps else None) or (task.video_config or {}).get("sample_fps") or 2.0
    sample_step = max(1, int(round(effective_fps / max(sample_fps, 0.05))))
    total_sampled = max(1, effective_frames // sample_step)

    perspective = (
        (payload.camera_perspective or payload.perspective if payload else None)
        or (task.video_config or {}).get("camera_perspective")
        or "FIXED_CCTV"
    )

    detector = get_shared_detector()
    job_id = str(uuid.uuid4())

    job = ProcessingJob(
        id=job_id,
        event_id=task.id,
        video_file_id=effective_vid_id,
        camera_id=payload.camera_id if payload else None,
        layout_id=task.layout_id,
        camera_perspective=perspective,
        status="RUNNING",
        detector_backend=detector.backend_name,
        sample_fps=sample_fps,
        frames_processed=0,
        total_sampled_frames=total_sampled,
        progress_pct=0.0,
        processing_fps=0.0,
        avg_inference_ms=0.0,
        max_people_detected=0,
    )
    db.add(job)

    old_state = task.state
    task.state = "PROCESSING"
    task.updated_at = _utcnow()

    hist = TaskHistory(
        task_id=task.id,
        event_type="PROCESSING_STARTED",
        details={
            "job_id": job_id,
            "sample_fps": sample_fps,
            "perspective": perspective,
            "old_state": old_state,
            "new_state": "PROCESSING",
        },
    )
    db.add(hist)
    await _sync_event_record(db, task)
    await db.commit()

    VideoProcessor.launch_job(
        job_id=job_id,
        video_id=effective_vid_id,
        event_id=task.id,
        sample_fps=sample_fps,
        camera_id=payload.camera_id if payload else None,
        layout_id=task.layout_id,
        camera_perspective=perspective,
    )

    return ProcessingJobResponse.model_validate(job)


@router.post("/{task_id}/pause")
async def pause_task_processing(
    task_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    stmt = (
        select(ProcessingJob)
        .where(ProcessingJob.event_id == task_id)
        .where(ProcessingJob.status.in_(["RUNNING", "PENDING"]))
        .order_by(desc(ProcessingJob.created_at))
        .limit(1)
    )
    job = (await db.execute(stmt)).scalar_one_or_none()
    if not job:
        for j_id, active in VideoProcessor._active_jobs.items():
            if active:
                candidate_job = await db.get(ProcessingJob, j_id)
                if candidate_job and candidate_job.event_id == task_id:
                    job = candidate_job
                    break

    if job:
        VideoProcessor.pause_processing(job.id)
        job.status = "PAUSED"

    task.state = "PAUSED"
    task.updated_at = _utcnow()
    hist = TaskHistory(
        task_id=task.id,
        event_type="PROCESSING_PAUSED",
        details={"job_id": job.id if job else None},
    )
    db.add(hist)
    await _sync_event_record(db, task)
    await db.commit()

    return {"task_id": task_id, "job_id": job.id if job else None, "status": "PAUSED"}


@router.post("/{task_id}/resume")
async def resume_task_processing(
    task_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    stmt = (
        select(ProcessingJob)
        .where(ProcessingJob.event_id == task_id)
        .where(ProcessingJob.status == "PAUSED")
        .order_by(desc(ProcessingJob.created_at))
        .limit(1)
    )
    job = (await db.execute(stmt)).scalar_one_or_none()
    if job:
        VideoProcessor.resume_processing(job.id)
        job.status = "RUNNING"

    task.state = "PROCESSING"
    task.updated_at = _utcnow()
    hist = TaskHistory(
        task_id=task.id,
        event_type="PROCESSING_RESUMED",
        details={"job_id": job.id if job else None},
    )
    db.add(hist)
    await _sync_event_record(db, task)
    await db.commit()

    return {"task_id": task_id, "job_id": job.id if job else None, "status": "PROCESSING"}


@router.post("/{task_id}/stop")
async def stop_task_processing(
    task_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    stmt = (
        select(ProcessingJob)
        .where(ProcessingJob.event_id == task_id)
        .where(ProcessingJob.status.in_(["RUNNING", "PENDING", "PAUSED"]))
        .order_by(desc(ProcessingJob.created_at))
        .limit(1)
    )
    job = (await db.execute(stmt)).scalar_one_or_none()
    if job:
        VideoProcessor.stop_processing(job.id)
        job.status = "STOPPED"

    task.state = "READY"
    task.updated_at = _utcnow()
    hist = TaskHistory(
        task_id=task.id,
        event_type="PROCESSING_STOPPED",
        details={"job_id": job.id if job else None},
    )
    db.add(hist)
    await _sync_event_record(db, task)
    await db.commit()

    return {"task_id": task_id, "job_id": job.id if job else None, "status": "STOPPED"}


@router.get("/{task_id}/job", response_model=Optional[ProcessingJobResponse])
async def get_task_job(
    task_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    stmt = (
        select(ProcessingJob)
        .where(ProcessingJob.event_id == task_id)
        .order_by(desc(ProcessingJob.created_at))
        .limit(1)
    )
    job = (await db.execute(stmt)).scalar_one_or_none()
    if not job:
        return None
    return ProcessingJobResponse.model_validate(job)


@router.get("/{task_id}/telemetry")
async def get_task_telemetry(
    task_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ts: Optional[float] = Query(None, description="Video timestamp in seconds for synchronized frame telemetry"),
):
    import json
    from app.analytics.zone_mapper import ZoneMapper

    # If live processing is actively running in memory with 36x64 grid and no explicit ts is requested
    live = VideoProcessor.get_latest_telemetry(task_id)
    if live and live.get("total_people", 0) > 0 and ts is None:
        grid = live.get("heatmap_grid", [])
        if grid and len(grid) == 36 and len(grid[0]) == 64:
            return live

    # Look up best available completed or processed job for this task
    best_job_stmt = (
        select(ProcessingJob)
        .where(ProcessingJob.event_id == task_id)
        .order_by(desc(ProcessingJob.frames_processed), desc(ProcessingJob.created_at))
        .limit(1)
    )
    best_job = (await db.execute(best_job_stmt)).scalar_one_or_none()
    target_job_id = best_job.id if best_job else None

    # Locate detection summary
    summary_stmt = select(DetectionSummary).where(DetectionSummary.event_id == task_id)
    if target_job_id:
        summary_stmt = summary_stmt.where(DetectionSummary.job_id == target_job_id)

    if ts is not None:
        summary_stmt = summary_stmt.order_by(func.abs(DetectionSummary.video_timestamp_sec - ts)).limit(1)
    else:
        if task_id == "task_railway_cctv_analysis":
            # Default to the 8.0s peak doorway surge for primary demo task
            summary_stmt = summary_stmt.order_by(func.abs(DetectionSummary.video_timestamp_sec - 8.0)).limit(1)
        else:
            summary_stmt = summary_stmt.order_by(desc(DetectionSummary.video_timestamp_sec)).limit(1)

    summary = (await db.execute(summary_stmt)).scalar_one_or_none()
    if not summary:
        any_stmt = (
            select(DetectionSummary)
            .where(DetectionSummary.event_id == task_id)
            .order_by(desc(DetectionSummary.created_at))
            .limit(1)
        )
        summary = (await db.execute(any_stmt)).scalar_one_or_none()

    if not summary:
        return {
            "type": "STANDBY",
            "task_id": task_id,
            "total_people": 0,
            "detections": [],
            "heatmap_grid": [],
            "snapshots": [],
            "risks": [],
            "alerts": [],
        }

    # Parse detections
    raw_dets = summary.detections or []
    if isinstance(raw_dets, str):
        try:
            detections_list = json.loads(raw_dets)
        except Exception:
            detections_list = []
    else:
        detections_list = list(raw_dets)

    # Generate or calibrate 36x64 16:9 spatial heatmap
    zm = ZoneMapper([])
    pts = []
    for d in detections_list:
        np_pt = d.get("norm_point")
        if np_pt and len(np_pt) == 2:
            pts.append((float(np_pt[0]), float(np_pt[1])))
        elif "foot_point" in d:
            fp = d["foot_point"]
            pts.append((fp[0] / 1280.0, fp[1] / 720.0))

    grid_36x64 = zm.generate_heatmap_grid(pts, grid_rows=36, grid_cols=64, sigma=2.5)

    # Multi-horizon predicted heatmaps
    predicted_heatmaps = {
        "30s": zm.generate_predicted_heatmap_grid(grid_36x64, horizon_sec=30),
        "60s": zm.generate_predicted_heatmap_grid(grid_36x64, horizon_sec=60),
        "180s": zm.generate_predicted_heatmap_grid(grid_36x64, horizon_sec=180),
        "300s": zm.generate_predicted_heatmap_grid(grid_36x64, horizon_sec=300),
    }

    # Fetch corresponding zone metrics
    m_stmt = (
        select(CrowdMetric)
        .where(CrowdMetric.job_id == summary.job_id)
        .where(func.abs(CrowdMetric.video_timestamp_sec - summary.video_timestamp_sec) < 0.35)
    )
    metrics = (await db.execute(m_stmt)).scalars().all()

    # Fetch corresponding zone risks
    r_stmt = (
        select(RiskAssessment)
        .where(RiskAssessment.job_id == summary.job_id)
        .where(func.abs(RiskAssessment.video_timestamp_sec - summary.video_timestamp_sec) < 0.35)
    )
    risks = (await db.execute(r_stmt)).scalars().all()

    # Fetch active alerts for this task
    a_stmt = (
        select(Alert)
        .where(Alert.event_id == task_id)
        .order_by(desc(Alert.created_at))
        .limit(5)
    )
    alerts = (await db.execute(a_stmt)).scalars().all()

    return {
        "type": "FRAME_UPDATE",
        "task_id": task_id,
        "job_id": summary.job_id,
        "frame_index": summary.frame_index,
        "video_timestamp_sec": summary.video_timestamp_sec,
        "total_people": summary.total_people,
        "frame_w": 1280,
        "frame_h": 720,
        "perspective": "FIXED_CCTV",
        "detections": detections_list,
        "heatmap_grid": grid_36x64,
        "accumulated_heatmap_grid": grid_36x64,
        "predicted_heatmaps": predicted_heatmaps,
        "snapshots": [
            {
                "zone_id": m.zone_id,
                "zone_name": m.zone_name,
                "people_count": m.people_count,
                "occupancy_ratio": m.occupancy_ratio,
                "density_value": m.density_value,
                "density_unit": m.density_unit,
                "inflow_rate": m.inflow_rate,
                "outflow_rate": m.outflow_rate,
                "net_flow": m.net_flow,
                "avg_speed": m.avg_speed,
                "movement_direction": m.movement_direction,
                "is_bottleneck": m.is_bottleneck,
                "is_counterflow": m.is_counterflow,
                "crowd_increase_pct": m.crowd_increase_pct,
                "capacity_utilization_pct": m.capacity_utilization_pct,
            }
            for m in metrics
        ],
        "risks": [
            {
                "zone_id": r.zone_id,
                "risk_level": r.risk_level,
                "reason": r.reason,
                "monitoring_priority": r.monitoring_priority,
            }
            for r in risks
        ],
        "alerts": [
            {
                "id": getattr(a, "id", ""),
                "event_id": getattr(a, "event_id", ""),
                "zone_id": getattr(a, "zone_id", ""),
                "alert_type": getattr(a, "category", getattr(a, "alert_type", "INCIDENT")),
                "severity": getattr(a, "severity", "CRITICAL"),
                "message": getattr(a, "title", getattr(a, "description", getattr(a, "message", ""))),
                "status": getattr(a, "status", "ACTIVE"),
                "created_at": a.created_at.isoformat() if hasattr(a, "created_at") and a.created_at else None,
            }
            for a in alerts
        ],
    }


@router.get("/{task_id}/video/stream")
async def stream_task_video_endpoint(
    task_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from app.api.routes.videos import stream_task_video
    return await stream_task_video(task_id, request, db)
