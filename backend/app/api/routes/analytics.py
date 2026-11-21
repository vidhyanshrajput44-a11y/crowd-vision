"""Analytics query endpoints for crowd metrics, heatmaps, predictions, and risk assessments."""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.zone_mapper import ZoneDefinition, ZoneMapper
from app.database.models import (
    CrowdMetric,
    DetectionSummary,
    Event,
    Prediction,
    ProcessingJob,
    RiskAssessment,
    VenueLayout,
    Zone,
)
from app.database.session import get_db
from app.schemas.api_schemas import (
    CrowdMetricResponse,
    DetectionSummaryResponse,
    HeatmapResponse,
    PredictionResponse,
    RiskAssessmentResponse,
)

router = APIRouter()


async def _resolve_job_id(db: AsyncSession, identifier: str) -> str:
    """Resolve identifier which may be a job_id or a video_file_id."""
    stmt = (
        select(ProcessingJob.id)
        .where((ProcessingJob.id == identifier) | (ProcessingJob.video_file_id == identifier))
        .order_by(desc(ProcessingJob.created_at))
        .limit(1)
    )
    res = (await db.execute(stmt)).scalar_one_or_none()
    return res or identifier


@router.get("/metrics", response_model=list[CrowdMetricResponse])
async def query_metrics(
    db: Annotated[AsyncSession, Depends(get_db)],
    event_id: Annotated[Optional[str], Query()] = None,
    job_id: Annotated[Optional[str], Query()] = None,
    zone_id: Annotated[Optional[str], Query()] = None,
    start_ts: Annotated[Optional[float], Query()] = None,
    end_ts: Annotated[Optional[float], Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
):
    stmt = select(CrowdMetric).order_by(CrowdMetric.video_timestamp_sec.asc(), CrowdMetric.zone_id.asc())
    if event_id:
        stmt = stmt.where(CrowdMetric.event_id == event_id)
    if job_id:
        resolved_job_id = await _resolve_job_id(db, job_id)
        stmt = stmt.where((CrowdMetric.job_id == job_id) | (CrowdMetric.job_id == resolved_job_id))
    if zone_id:
        stmt = stmt.where(CrowdMetric.zone_id == zone_id)
    if start_ts is not None:
        stmt = stmt.where(CrowdMetric.video_timestamp_sec >= start_ts)
    if end_ts is not None:
        stmt = stmt.where(CrowdMetric.video_timestamp_sec <= end_ts)
    stmt = stmt.limit(limit)

    metrics = (await db.execute(stmt)).scalars().all()
    return [CrowdMetricResponse.model_validate(m) for m in metrics]


@router.get("/detections/{job_id}", response_model=DetectionSummaryResponse)
async def get_detections_by_job_id(
    job_id: str,
    ts: Optional[float] = Query(None),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    return await get_detections_at_timestamp(job_id=job_id, ts=ts, db=db)


@router.get("/detections", response_model=DetectionSummaryResponse)
async def get_detections_at_timestamp(
    job_id: str = Query(...),
    ts: Optional[float] = Query(None),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    actual_job_id = await _resolve_job_id(db, job_id)
    if ts is None:
        stmt = (
            select(DetectionSummary)
            .where((DetectionSummary.job_id == job_id) | (DetectionSummary.job_id == actual_job_id))
            .order_by(desc(DetectionSummary.video_timestamp_sec))
            .limit(1)
        )
    else:
        stmt = (
            select(DetectionSummary)
            .where((DetectionSummary.job_id == job_id) | (DetectionSummary.job_id == actual_job_id))
            .order_by(func.abs(DetectionSummary.video_timestamp_sec - ts))
            .limit(1)
        )

    det = (await db.execute(stmt)).scalar_one_or_none()
    if not det:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection summary not found for job")
    return DetectionSummaryResponse.model_validate(det)


@router.get("/detections/timeline")
async def get_detections_timeline(
    job_id: str = Query(...),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    actual_job_id = await _resolve_job_id(db, job_id)
    stmt = (
        select(DetectionSummary.video_timestamp_sec, DetectionSummary.total_people)
        .where((DetectionSummary.job_id == job_id) | (DetectionSummary.job_id == actual_job_id))
        .order_by(DetectionSummary.video_timestamp_sec.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [{"timestamp": r[0], "count": r[1]} for r in rows]


@router.get("/heatmap/{job_id}", response_model=HeatmapResponse)
async def get_heatmap_by_job_id(
    job_id: str,
    ts: Optional[float] = Query(None),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    return await get_heatmap_at_timestamp(job_id=job_id, ts=ts, db=db)


@router.get("/heatmap", response_model=HeatmapResponse)
async def get_heatmap_at_timestamp(
    job_id: str = Query(...),
    ts: Optional[float] = Query(None),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    actual_job_id = await _resolve_job_id(db, job_id)
    if ts is None:
        stmt = (
            select(DetectionSummary)
            .where((DetectionSummary.job_id == job_id) | (DetectionSummary.job_id == actual_job_id))
            .order_by(desc(DetectionSummary.video_timestamp_sec))
            .limit(1)
        )
    else:
        stmt = (
            select(DetectionSummary)
            .where((DetectionSummary.job_id == job_id) | (DetectionSummary.job_id == actual_job_id))
            .order_by(func.abs(DetectionSummary.video_timestamp_sec - ts))
            .limit(1)
        )

    det = (await db.execute(stmt)).scalar_one_or_none()
    if not det:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Heatmap data not found for job")

    # Fetch corresponding predictions to construct future heatmaps
    pred_stmt = select(Prediction).where(
        (Prediction.job_id == job_id) | (Prediction.job_id == actual_job_id),
        func.abs(Prediction.video_timestamp_sec - det.video_timestamp_sec) < 0.1,
    )
    preds = (await db.execute(pred_stmt)).scalars().all()

    # Build mapper
    job = await db.get(ProcessingJob, actual_job_id)
    zone_defs = []
    homography = None
    if job and job.layout_id:
        layout = await db.get(VenueLayout, job.layout_id)
        if layout and layout.zones_data:
            for z in layout.zones_data:
                zone_defs.append(
                    ZoneDefinition(
                        zone_id=str(z.get("zone_id") or z.get("id")),
                        name=str(z.get("zone_name") or z.get("name")),
                        polygon_points=z.get("polygon_points") or [],
                        capacity=int(z.get("max_capacity") or z.get("capacity") or 50),
                    )
                )
            homography = layout.calibration_homography

    mapper = ZoneMapper(zones=zone_defs, calibration_homography=homography)
    growth_by_zone = {p.zone_id: p.predicted_change_pct / 100.0 for p in preds if p.horizon_seconds in (60, 180)}

    grid_30 = mapper.generate_predicted_heatmap_grid(det.heatmap_grid, growth_by_zone, horizon_sec=30)
    grid_60 = mapper.generate_predicted_heatmap_grid(det.heatmap_grid, growth_by_zone, horizon_sec=60)
    grid_180 = mapper.generate_predicted_heatmap_grid(det.heatmap_grid, growth_by_zone, horizon_sec=180)
    grid_300 = mapper.generate_predicted_heatmap_grid(det.heatmap_grid, growth_by_zone, horizon_sec=300)

    predicted = {
        "30s": grid_30,
        "60s": grid_60,
        "180s": grid_180,
        "300s": grid_300,
        "30": grid_30,
        "60": grid_60,
        "180": grid_180,
        "300": grid_300,
    }

    return HeatmapResponse(
        job_id=job_id,
        video_timestamp_sec=det.video_timestamp_sec,
        current=det.heatmap_grid,
        predicted=predicted,
    )


@router.get("/predictions/{job_id}", response_model=list[PredictionResponse])
async def get_predictions_by_job_id(
    job_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    horizon_seconds: Annotated[Optional[int], Query()] = None,
    horizon: Annotated[Optional[str], Query()] = None,
    ts: Annotated[Optional[float], Query()] = None,
    zone_id: Annotated[Optional[str], Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    hz = horizon_seconds if horizon_seconds is not None else (int(horizon) if horizon and horizon.isdigit() else None)
    return await get_predictions(
        db=db,
        event_id=None,
        job_id=job_id,
        horizon_seconds=hz,
        ts=ts,
        zone_id=zone_id,
        limit=limit,
    )


@router.get("/predictions", response_model=list[PredictionResponse])
async def get_predictions(
    db: Annotated[AsyncSession, Depends(get_db)],
    event_id: Annotated[Optional[str], Query()] = None,
    job_id: Annotated[Optional[str], Query()] = None,
    zone_id: Annotated[Optional[str], Query()] = None,
    ts: Annotated[Optional[float], Query()] = None,
    horizon_seconds: Annotated[Optional[int], Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    stmt = select(Prediction).order_by(Prediction.video_timestamp_sec.asc(), Prediction.zone_id.asc())
    if event_id:
        stmt = stmt.where(Prediction.event_id == event_id)
    if job_id:
        actual_job_id = await _resolve_job_id(db, job_id)
        stmt = stmt.where((Prediction.job_id == job_id) | (Prediction.job_id == actual_job_id))
    if zone_id:
        stmt = stmt.where(Prediction.zone_id == zone_id)
    if horizon_seconds:
        stmt = stmt.where(Prediction.horizon_seconds == horizon_seconds)
    if ts is not None:
        stmt = stmt.where(func.abs(Prediction.video_timestamp_sec - ts) < 0.1)
    stmt = stmt.limit(limit)

    preds = (await db.execute(stmt)).scalars().all()
    return [PredictionResponse.model_validate(p) for p in preds]


@router.get("/risks", response_model=list[RiskAssessmentResponse])
async def get_risk_assessments(
    db: Annotated[AsyncSession, Depends(get_db)],
    event_id: Annotated[Optional[str], Query()] = None,
    job_id: Annotated[Optional[str], Query()] = None,
    zone_id: Annotated[Optional[str], Query()] = None,
    ts: Annotated[Optional[float], Query()] = None,
    risk_level: Annotated[Optional[str], Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    stmt = select(RiskAssessment).order_by(RiskAssessment.video_timestamp_sec.asc(), RiskAssessment.zone_id.asc())
    if event_id:
        stmt = stmt.where(RiskAssessment.event_id == event_id)
    if job_id:
        actual_job_id = await _resolve_job_id(db, job_id)
        stmt = stmt.where((RiskAssessment.job_id == job_id) | (RiskAssessment.job_id == actual_job_id))
    if zone_id:
        stmt = stmt.where(RiskAssessment.zone_id == zone_id)
    if risk_level:
        stmt = stmt.where(RiskAssessment.risk_level == risk_level.upper())
    if ts is not None:
        stmt = stmt.where(func.abs(RiskAssessment.video_timestamp_sec - ts) < 0.1)
    stmt = stmt.limit(limit)

    risks = (await db.execute(stmt)).scalars().all()
    return [RiskAssessmentResponse.model_validate(r) for r in risks]


@router.get("/zones/{event_id}/summary")
@router.get("/tasks/{event_id}/summary")
@router.get("/events/{event_id}/summary", include_in_schema=False)
async def get_event_zone_summary(
    event_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    ev = await db.get(Event, event_id)
    latest_job = None
    if not ev:
        job = await db.get(ProcessingJob, event_id)
        if job:
            latest_job = job
            ev = await db.get(Event, job.event_id)
            event_id = job.event_id
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    if not latest_job:
        latest_job = (
            await db.execute(
                select(ProcessingJob)
                .where(ProcessingJob.event_id == event_id)
                .order_by(desc(ProcessingJob.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()

    if not latest_job:
        return {
            "event_id": event_id,
            "status": "NO_ANALYSIS",
            "total_people": 0,
            "zone_count": 0,
            "zones": [],
            "trend_series": [],
            "total_occupancy": 0,
        }

    latest_ts = (
        await db.execute(
            select(func.max(CrowdMetric.video_timestamp_sec)).where(
                CrowdMetric.job_id == latest_job.id
            )
        )
    ).scalar_one_or_none()

    if latest_ts is None:
        return {
            "event_id": event_id,
            "status": latest_job.status,
            "total_people": 0,
            "zone_count": 0,
            "zones": [],
            "trend_series": [],
            "total_occupancy": 0,
        }

    metrics = (
        await db.execute(
            select(CrowdMetric).where(
                CrowdMetric.job_id == latest_job.id,
                func.abs(CrowdMetric.video_timestamp_sec - float(latest_ts)) < 0.1,
            )
        )
    ).scalars().all()

    risks = (
        await db.execute(
            select(RiskAssessment).where(
                RiskAssessment.job_id == latest_job.id,
                func.abs(RiskAssessment.video_timestamp_sec - float(latest_ts)) < 0.1,
            )
        )
    ).scalars().all()

    risk_map = {r.zone_id: r for r in risks}

    zone_summaries = []
    total_people = 0
    for m in metrics:
        r = risk_map.get(m.zone_id)
        total_people += m.people_count
        zone_summaries.append(
            {
                "zone_id": m.zone_id,
                "zone_name": m.zone_name,
                "people_count": m.people_count,
                "occupancy_ratio": m.occupancy_ratio,
                "capacity_utilization_pct": m.capacity_utilization_pct,
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
                "risk_level": r.risk_level if r else "NORMAL",
                "risk_reason": r.reason if r else "",
                "monitoring_priority": r.monitoring_priority if r else "ROUTINE",
            }
        )

    # Compute trend_series across frames for charts and reporting
    all_metrics = (
        (
            await db.execute(
                select(CrowdMetric)
                .where(CrowdMetric.job_id == latest_job.id)
                .order_by(CrowdMetric.video_timestamp_sec.asc())
                .limit(1200)
            )
        )
        .scalars()
        .all()
    )

    by_ts: dict[float, dict[str, Any]] = {}
    for m in all_metrics:
        t = round(m.video_timestamp_sec, 1)
        entry = by_ts.setdefault(
            t,
            {
                "timestamp_sec": t,
                "total_people": 0,
                "avg_occupancy": 0.0,
                "_count": 0,
            },
        )
        entry["total_people"] += m.people_count
        entry["avg_occupancy"] += m.occupancy_ratio
        entry["_count"] += 1
        entry[m.zone_name] = round(m.occupancy_ratio * 100.0, 1)

    trend_series: list[dict[str, Any]] = []
    for t in sorted(by_ts.keys()):
        item = by_ts[t]
        cnt = max(item.pop("_count", 1), 1)
        item["avg_occupancy_pct"] = round((item.pop("avg_occupancy", 0.0) / cnt) * 100.0, 1)
        trend_series.append(item)

    if not trend_series and zone_summaries:
        trend_series.append({
            "timestamp_sec": float(latest_ts),
            "total_people": total_people,
            "avg_occupancy_pct": round(sum(z["capacity_utilization_pct"] for z in zone_summaries) / max(1, len(zone_summaries)), 1),
        })

    return {
        "event_id": event_id,
        "job_id": latest_job.id,
        "video_timestamp_sec": float(latest_ts),
        "total_people": total_people,
        "zone_count": len(zone_summaries),
        "zones": zone_summaries,
        "trend_series": trend_series,
    }


@router.get("/history")
async def get_historical_analytics(
    db: Annotated[AsyncSession, Depends(get_db)],
    task_id: Annotated[Optional[str], Query()] = None,
    event_id: Annotated[Optional[str], Query()] = None,
    start_ts: Annotated[Optional[float], Query()] = None,
    end_ts: Annotated[Optional[float], Query()] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
):
    """Retrieve historical crowd analytics across time for charting and retrospective analysis."""
    target_id = task_id or event_id
    stmt = select(CrowdMetric).order_by(CrowdMetric.video_timestamp_sec.asc())
    if target_id:
        stmt = stmt.where(CrowdMetric.event_id == target_id)
    if start_ts is not None:
        stmt = stmt.where(CrowdMetric.video_timestamp_sec >= start_ts)
    if end_ts is not None:
        stmt = stmt.where(CrowdMetric.video_timestamp_sec <= end_ts)
    stmt = stmt.limit(limit)

    metrics = (await db.execute(stmt)).scalars().all()

    # Aggregate by timestamp bucket
    by_ts: dict[float, dict[str, Any]] = {}
    for m in metrics:
        t = round(m.video_timestamp_sec, 1)
        entry = by_ts.setdefault(
            t,
            {
                "timestamp_sec": t,
                "total_people": 0,
                "zone_counts": {},
                "avg_speed": 0.0,
                "_count": 0,
            },
        )
        entry["total_people"] += m.people_count
        entry["zone_counts"][m.zone_name] = m.people_count
        if m.avg_speed:
            entry["avg_speed"] += m.avg_speed
        entry["_count"] += 1

    timeline: list[dict[str, Any]] = []
    for t in sorted(by_ts.keys()):
        item = by_ts[t]
        c = max(item.pop("_count", 1), 1)
        item["avg_speed"] = round(item["avg_speed"] / c, 2)
        timeline.append(item)

    peak_people = max((pt["total_people"] for pt in timeline), default=0)

    return {
        "task_id": target_id,
        "data_points": len(timeline),
        "peak_people": peak_people,
        "timeline": timeline,
    }
