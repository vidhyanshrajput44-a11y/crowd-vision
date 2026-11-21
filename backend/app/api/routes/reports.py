"""Post-event analytics and operational safety report generation routes."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Alert,
    CrowdMetric,
    Event,
    Prediction,
    ProcessingJob,
    Recommendation,
    ReportRecord,
    RiskAssessment,
    Venue,
    Zone,
)
from app.database.session import get_db
from app.schemas.api_schemas import ReportGenerateRequest, ReportResponse

router = APIRouter()


@router.post("/generate", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def generate_report(
    payload: ReportGenerateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    ev = await db.get(Event, payload.event_id)
    if not ev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    venue = await db.get(Venue, ev.venue_id) if ev.venue_id else None

    job_stmt = select(ProcessingJob).where(ProcessingJob.event_id == ev.id).order_by(desc(ProcessingJob.created_at))
    if payload.job_id:
        job_stmt = job_stmt.where(
            (ProcessingJob.id == payload.job_id) | (ProcessingJob.video_file_id == payload.job_id)
        )
    job = (await db.execute(job_stmt)).scalars().first()

    metrics: list[CrowdMetric] = []
    risks: list[RiskAssessment] = []
    alerts: list[Alert] = []
    recs: list[Recommendation] = []
    preds: list[Prediction] = []

    if job:
        metrics = (
            await db.execute(
                select(CrowdMetric).where(CrowdMetric.job_id == job.id).order_by(CrowdMetric.video_timestamp_sec.asc())
            )
        ).scalars().all()

        risks = (
            await db.execute(
                select(RiskAssessment).where(RiskAssessment.job_id == job.id)
            )
        ).scalars().all()

        preds = (
            await db.execute(
                select(Prediction).where(Prediction.job_id == job.id)
            )
        ).scalars().all()

    alerts = (
        await db.execute(
            select(Alert).where(Alert.event_id == ev.id).order_by(Alert.created_at.desc())
        )
    ).scalars().all()

    recs = (
        await db.execute(
            select(Recommendation).where(Recommendation.event_id == ev.id).order_by(Recommendation.created_at.desc())
        )
    ).scalars().all()

    # Per-zone statistics aggregation
    zone_stats: dict[str, dict] = {}
    for m in metrics:
        if m.zone_id not in zone_stats:
            zone_stats[m.zone_id] = {
                "zone_name": m.zone_name,
                "peak_people": 0,
                "peak_occupancy_ratio": 0.0,
                "peak_capacity_utilization_pct": 0.0,
                "max_inflow": 0.0,
                "max_outflow": 0.0,
                "bottleneck_count": 0,
                "counterflow_count": 0,
                "sample_count": 0,
                "total_people": 0,
            }
        zs = zone_stats[m.zone_id]
        zs["sample_count"] += 1
        zs["total_people"] += m.people_count
        zs["peak_people"] = max(zs["peak_people"], m.people_count)
        zs["peak_occupancy_ratio"] = max(zs["peak_occupancy_ratio"], m.occupancy_ratio)
        zs["peak_capacity_utilization_pct"] = max(zs["peak_capacity_utilization_pct"], m.capacity_utilization_pct)
        zs["max_inflow"] = max(zs["max_inflow"], m.inflow_rate)
        zs["max_outflow"] = max(zs["max_outflow"], m.outflow_rate)
        if m.is_bottleneck:
            zs["bottleneck_count"] += 1
        if m.is_counterflow:
            zs["counterflow_count"] += 1

    for zs in zone_stats.values():
        if zs["sample_count"] > 0:
            zs["avg_people"] = round(float(zs["total_people"]) / zs["sample_count"], 1)
            zs["peak_occupancy_ratio"] = round(zs["peak_occupancy_ratio"], 3)
            zs["peak_capacity_utilization_pct"] = round(zs["peak_capacity_utilization_pct"], 1)

    # Risk breakdown
    risk_counts = {"NORMAL": 0, "LOW": 0, "MODERATE": 0, "HIGH": 0, "CRITICAL": 0}
    for r in risks:
        lvl = r.risk_level.upper()
        if lvl in risk_counts:
            risk_counts[lvl] += 1

    # Alert breakdown
    severity_counts = {"LOW": 0, "MODERATE": 0, "HIGH": 0, "CRITICAL": 0}
    for a in alerts:
        sev = a.severity.upper()
        if sev in severity_counts:
            severity_counts[sev] += 1

    report_title = payload.title or f"Crowd Safety & Spatial Analytics Report: {ev.name}"
    summary_data = {
        "event_id": ev.id,
        "event_name": ev.name,
        "event_type": ev.event_type,
        "venue_name": venue.name if venue else "Unknown Venue",
        "venue_location": venue.location if venue else "",
        "job_id": job.id if job else None,
        "detector_backend": job.detector_backend if job else "N/A",
        "camera_perspective": job.camera_perspective if job else "N/A",
        "frames_analyzed": job.frames_processed if job else 0,
        "max_concurrent_crowd": job.max_people_detected if job else 0,
        "zone_breakdown": zone_stats,
        "risk_distribution": risk_counts,
        "alert_metrics": {
            "total_alerts": len(alerts),
            "by_severity": severity_counts,
            "resolved_count": sum(1 for a in alerts if a.status == "RESOLVED"),
            "active_count": sum(1 for a in alerts if a.status == "ACTIVE"),
        },
        "recommendations_count": len(recs),
        "predictions_generated": len(preds),
        "generated_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    report_record = ReportRecord(
        event_id=ev.id,
        title=report_title,
        generated_by="System Operator",
        summary_data=summary_data,
    )
    db.add(report_record)
    await db.commit()
    await db.refresh(report_record)
    return ReportResponse.model_validate(report_record)


@router.get("", response_model=list[ReportResponse])
async def list_reports(
    db: Annotated[AsyncSession, Depends(get_db)],
    event_id: Optional[str] = Query(None),
):
    stmt = select(ReportRecord).order_by(desc(ReportRecord.created_at))
    if event_id:
        stmt = stmt.where(ReportRecord.event_id == event_id)
    reports = (await db.execute(stmt)).scalars().all()
    return [ReportResponse.model_validate(r) for r in reports]


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    report = await db.get(ReportRecord, report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return ReportResponse.model_validate(report)


@router.get("/{report_id}/export.csv", include_in_schema=False)
@router.get("/{report_id}/export/csv")
async def export_report_csv(
    report_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    report = await db.get(ReportRecord, report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["REPORT OVERVIEW"])
    writer.writerow(["Title", report.title])
    writer.writerow(["Event ID", report.event_id])
    writer.writerow(["Created At", str(report.created_at)])
    writer.writerow([])

    s = report.summary_data or {}
    writer.writerow(["METRICS SUMMARY"])
    writer.writerow(["Event Name", s.get("event_name")])
    writer.writerow(["Venue", s.get("venue_name")])
    writer.writerow(["Max People Detected", s.get("max_concurrent_crowd")])
    writer.writerow(["Frames Analyzed", s.get("frames_analyzed")])
    writer.writerow(["Total Alerts", s.get("alert_metrics", {}).get("total_alerts")])
    writer.writerow([])

    writer.writerow(["ZONE METRICS"])
    writer.writerow([
        "Zone ID",
        "Zone Name",
        "Peak People",
        "Avg People",
        "Peak Cap Util %",
        "Max Inflow",
        "Max Outflow",
        "Bottlenecks",
        "Counterflows",
    ])
    for zid, z in s.get("zone_breakdown", {}).items():
        writer.writerow([
            zid,
            z.get("zone_name"),
            z.get("peak_people"),
            z.get("avg_people"),
            z.get("peak_capacity_utilization_pct"),
            z.get("max_inflow"),
            z.get("max_outflow"),
            z.get("bottleneck_count"),
            z.get("counterflow_count"),
        ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=report_{report_id[:8]}.csv"},
    )
