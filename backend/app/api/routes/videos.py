"""Video upload, job lifecycle management, and inference startup routes."""
from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Annotated, Optional
import uuid

import cv2
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.cv.detector import assess_footage_perspective
from app.database.models import Camera, Event, ProcessingJob, Task, VenueLayout, VideoFile
from app.database.session import get_db
from app.schemas.api_schemas import (
    ProcessStartRequest,
    ProcessingJobResponse,
    VideoFileResponse,
    VideoUploadResponse,
)
from app.services.video_processor import VideoProcessor, get_shared_detector

router = APIRouter()


def _to_playback_url(stored_path: str, video_id: Optional[str] = None) -> str:
    if video_id:
        return f"/api/videos/{video_id}/stream"
    fname = Path(stored_path).name
    return f"/uploads/videos/{fname}"


def stream_video_file(file_path: Path, request: Request) -> Response:
    """Stream a video file with full HTTP 206 Partial Content byte-range support."""
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video file not found on disk")

    file_size = file_path.stat().st_size
    if file_size == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Video file is empty")

    ext = file_path.suffix.lower()
    content_types = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo",
    }
    content_type = content_types.get(ext, "video/mp4")

    range_header = request.headers.get("range")
    if not range_header:
        def full_iter():
            with open(file_path, "rb") as f:
                while chunk := f.read(256 * 1024):
                    yield chunk

        headers = {
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
            "Content-Type": content_type,
            "Cache-Control": "public, max-age=3600",
        }
        return StreamingResponse(full_iter(), status_code=status.HTTP_200_OK, headers=headers, media_type=content_type)

    try:
        range_val = range_header.strip().lower()
        if not range_val.startswith("bytes="):
            raise ValueError("Invalid range unit")
        range_spec = range_val[len("bytes="):].strip()
        parts = range_spec.split("-")
        if len(parts) != 2:
            raise ValueError("Invalid range specification")

        start_str, end_str = parts[0].strip(), parts[1].strip()
        if start_str and end_str:
            start = int(start_str)
            end = int(end_str)
        elif start_str:
            start = int(start_str)
            end = file_size - 1
        elif end_str:
            suffix = int(end_str)
            start = max(0, file_size - suffix)
            end = file_size - 1
        else:
            raise ValueError("Empty range")

        if start < 0 or start >= file_size or end < start or end >= file_size:
            return Response(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                headers={"Content-Range": f"bytes */{file_size}"},
            )
    except Exception:
        return Response(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    chunk_size = end - start + 1

    def range_iter(start_pos: int, bytes_to_read: int):
        with open(file_path, "rb") as f:
            f.seek(start_pos)
            remaining = bytes_to_read
            while remaining > 0:
                read_amount = min(remaining, 256 * 1024)
                chunk = f.read(read_amount)
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_size),
        "Content-Type": content_type,
        "Cache-Control": "public, max-age=3600",
    }
    return StreamingResponse(
        range_iter(start, chunk_size),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        headers=headers,
        media_type=content_type,
    )


@router.post("/upload", response_model=VideoUploadResponse)
async def upload_video(
    file: UploadFile = File(...),
    event_id: str = Form(...),
    camera_id: Optional[str] = Form(None),
    camera_perspective: Optional[str] = Form(None),
    layout_id: Optional[str] = Form(None),
    auto_start: bool = Form(True),
    sample_fps: float = Form(0.2),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    settings = get_settings()
    settings.videos_dir.mkdir(parents=True, exist_ok=True)

    allowed_exts = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
    # Sanitize original filename to prevent path traversal
    raw_name = Path(file.filename or "video.mp4").name
    orig_name = re.sub(r"[^\w\.-]", "_", raw_name)
    ext = Path(orig_name).suffix.lower()
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported video format '{ext}'. Allowed: {', '.join(allowed_exts)}",
        )

    vid_id = str(uuid.uuid4())
    stored_name = f"{vid_id}_{orig_name}"
    stored_path = settings.videos_dir / stored_name

    # Stream upload in chunks to prevent unbounded memory consumption (Resource Exhaustion / DoS)
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    total_bytes = 0
    try:
        with open(stored_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    f.close()
                    if stored_path.exists():
                        stored_path.unlink()
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds maximum upload size limit of {settings.max_upload_size_mb} MB",
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        if stored_path.exists():
            stored_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store uploaded video stream safely",
        )

    if total_bytes == 0:
        if stored_path.exists():
            stored_path.unlink()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

    cap = cv2.VideoCapture(str(stored_path))
    if not cap.isOpened():
        if stored_path.exists():
            stored_path.unlink()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not decode video file stream")

    ev = await db.get(Event, event_id)
    if not ev:
        cap.release()
        if stored_path.exists():
            stored_path.unlink()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 0
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 0
    duration = float(frame_count) / fps if fps > 0 else 0.0

    # Sanity checks on video dimensions and length to prevent resource exhaustion
    max_duration = getattr(settings, "max_video_duration_seconds", 14400.0)
    max_dim = getattr(settings, "max_video_dimension", 4096)

    if width <= 0 or height <= 0 or frame_count <= 0 or duration <= 0:
        cap.release()
        if stored_path.exists():
            stored_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid video stream dimensions or frame count",
        )

    if duration > max_duration:
        cap.release()
        if stored_path.exists():
            stored_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Video duration ({duration:.1f}s) exceeds maximum allowed {max_duration:.1f}s",
        )

    if width > max_dim or height > max_dim:
        cap.release()
        if stored_path.exists():
            stored_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Video resolution {width}x{height} exceeds maximum supported dimension {max_dim}px",
        )

    ret, first_frame = cap.read()
    cap.release()

    detected_perspective = "FIXED_CCTV"
    if ret and first_frame is not None:
        detected_perspective = assess_footage_perspective(first_frame)["recommended_perspective"]

    effective_perspective = camera_perspective or detected_perspective

    video_record = VideoFile(
        id=vid_id,
        event_id=event_id,
        camera_id=camera_id,
        original_filename=orig_name,
        stored_path=str(stored_path),
        file_size_bytes=total_bytes,
        duration_seconds=round(duration, 2),
        fps=round(fps, 2),
        frame_count=frame_count,
        width=width,
        height=height,
    )
    db.add(video_record)
    await db.flush()

    detector = get_shared_detector()
    job_id = str(uuid.uuid4())
    sample_step = max(1, int(round(fps / max(sample_fps, 0.05))))
    total_sampled = max(1, frame_count // sample_step)

    # Associate uploaded video file with the Task record directly
    task_rec = await db.get(Task, event_id)
    if task_rec:
        v_cfg = dict(task_rec.video_config or {})
        v_cfg["source_type"] = "FILE"
        v_cfg["video_id"] = vid_id
        v_cfg["stored_path"] = str(stored_path)
        v_cfg["stored_filename"] = stored_name
        v_cfg["original_filename"] = orig_name
        v_cfg["filename"] = orig_name
        v_cfg["playback_url"] = f"/api/videos/{vid_id}/stream"
        v_cfg["stream_url"] = f"/api/tasks/{task_rec.id}/video/stream"
        v_cfg["fps"] = round(fps, 2)
        v_cfg["duration_seconds"] = round(duration, 2)
        v_cfg["width"] = width
        v_cfg["height"] = height
        v_cfg["camera_perspective"] = effective_perspective
        task_rec.video_config = v_cfg

    job = ProcessingJob(
        id=job_id,
        event_id=event_id,
        video_file_id=vid_id,
        camera_id=camera_id,
        layout_id=layout_id,
        camera_perspective=effective_perspective,
        status="PENDING",
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
    await db.commit()

    if auto_start:
        VideoProcessor.launch_job(
            job_id=job_id,
            video_id=vid_id,
            event_id=event_id,
            sample_fps=sample_fps,
            camera_id=camera_id,
            layout_id=layout_id,
            camera_perspective=effective_perspective,
        )

    return VideoUploadResponse(
        video_id=vid_id,
        job_id=job_id,
        filename=orig_name,
        playback_url=_to_playback_url(str(stored_path), vid_id),
        duration_seconds=round(duration, 2),
        fps=round(fps, 2),
        frame_count=frame_count,
        width=width,
        height=height,
        file_size_bytes=total_bytes,
    )


@router.get("/stream/{video_id}")
@router.get("/{video_id}/stream")
async def stream_video(
    video_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Stream a video by its video ID with HTTP 206 Partial Content range support."""
    video = await db.get(VideoFile, video_id)
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video record not found")
    return stream_video_file(Path(video.stored_path), request)


@router.get("/tasks/{task_id}/stream")
async def stream_task_video(
    task_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Stream the video associated with a task with HTTP 206 Partial Content range support."""
    settings = get_settings()

    # Guaranteed persistent CCTV footage for demonstration scenario
    if task_id == "task_railway_cctv_analysis":
        for cand in [settings.videos_dir / "cctvfootagerailway.mp4", settings.videos_dir / "railway_cctv_analysis.mp4"]:
            if cand.exists():
                return stream_video_file(cand, request)

    # 1. Search VideoFile by event_id == task_id
    stmt = select(VideoFile).where(VideoFile.event_id == task_id).order_by(desc(VideoFile.created_at)).limit(1)
    video = (await db.execute(stmt)).scalar_one_or_none()
    if video and Path(video.stored_path).exists():
        return stream_video_file(Path(video.stored_path), request)

    # 2. Check Task video_config
    task = await db.get(Task, task_id)
    if task and task.video_config:
        cfg = task.video_config
        vid_id = cfg.get("video_id")
        if vid_id:
            v2 = await db.get(VideoFile, vid_id)
            if v2 and Path(v2.stored_path).exists():
                return stream_video_file(Path(v2.stored_path), request)

        stored_fn = cfg.get("stored_filename")
        if stored_fn:
            p = settings.videos_dir / stored_fn
            if p.exists():
                return stream_video_file(p, request)

        orig_fn = cfg.get("filename")
        if orig_fn:
            matches = list(settings.videos_dir.glob(f"*_{orig_fn}"))
            if matches:
                return stream_video_file(matches[0], request)
            direct_p = settings.videos_dir / orig_fn
            if direct_p.exists():
                return stream_video_file(direct_p, request)

    # 3. Fallback to sample video
    sample = settings.videos_dir / "sample_crowd_festival.mp4"
    if sample.exists():
        return stream_video_file(sample, request)

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No video file found for this task")


@router.get("", response_model=list[VideoFileResponse])
async def list_videos(
    db: Annotated[AsyncSession, Depends(get_db)],
    event_id: Optional[str] = Query(None),
):
    stmt = select(VideoFile).order_by(desc(VideoFile.created_at))
    if event_id:
        stmt = stmt.where(VideoFile.event_id == event_id)
    videos = (await db.execute(stmt)).scalars().all()
    res = []
    for v in videos:
        d = VideoFileResponse.model_validate(v)
        d.playback_url = _to_playback_url(v.stored_path, v.id)
        res.append(d)
    return res


@router.get("/jobs", response_model=list[ProcessingJobResponse])
async def list_jobs(
    db: Annotated[AsyncSession, Depends(get_db)],
    event_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    stmt = select(ProcessingJob).order_by(desc(ProcessingJob.created_at))
    if event_id:
        stmt = stmt.where(ProcessingJob.event_id == event_id)
    if status:
        stmt = stmt.where(ProcessingJob.status == status.upper())
    jobs = (await db.execute(stmt)).scalars().all()
    return [ProcessingJobResponse.model_validate(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=ProcessingJobResponse)
async def get_job(
    job_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    job = await db.get(ProcessingJob, job_id)
    if not job:
        stmt = (
            select(ProcessingJob)
            .where(ProcessingJob.video_file_id == job_id)
            .order_by(desc(ProcessingJob.created_at))
            .limit(1)
        )
        job = (await db.execute(stmt)).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return ProcessingJobResponse.model_validate(job)


@router.post("/jobs/{job_id}/stop")
async def stop_job(
    job_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    job = await db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    stopped = VideoProcessor.stop_processing(job_id)
    job.status = "STOPPED"
    await db.commit()
    return {"job_id": job_id, "stopped": stopped, "status": "STOPPED"}


@router.get("/{video_id}", response_model=VideoFileResponse)
async def get_video(
    video_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    video = await db.get(VideoFile, video_id)
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video file not found")
    res = VideoFileResponse.model_validate(video)
    res.playback_url = _to_playback_url(video.stored_path, video.id)
    return res


@router.post("/{video_id}/process", response_model=ProcessingJobResponse, status_code=status.HTTP_201_CREATED)
async def start_video_processing(
    video_id: str,
    payload: ProcessStartRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    video = await db.get(VideoFile, video_id)
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video file not found")

    sample_fps = payload.sample_fps or 0.2
    camera_id = payload.camera_id or video.camera_id
    layout_id = payload.layout_id

    perspective = payload.camera_perspective or payload.perspective or "FIXED_CCTV"
    if camera_id and not (payload.camera_perspective or payload.perspective):
        cam = await db.get(Camera, camera_id)
        if cam and cam.perspective:
            perspective = cam.perspective

    sample_step = max(1, int(round(video.fps / max(sample_fps, 0.05))))
    total_sampled = max(1, video.frame_count // sample_step)
    detector = get_shared_detector()

    job_id = str(uuid.uuid4())
    job = ProcessingJob(
        id=job_id,
        event_id=video.event_id,
        video_file_id=video.id,
        camera_id=camera_id,
        layout_id=layout_id,
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
    await db.commit()

    VideoProcessor.launch_job(
        job_id=job_id,
        video_id=video.id,
        event_id=video.event_id,
        sample_fps=sample_fps,
        camera_id=camera_id,
        layout_id=layout_id,
        camera_perspective=perspective,
    )
    return ProcessingJobResponse.model_validate(job)
