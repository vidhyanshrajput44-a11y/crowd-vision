"""Chat endpoint proxying operator inquiries to the AI Agent with robust database grounding fallback."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Alert, CrowdMetric, Event, Prediction, ProcessingJob, RiskAssessment
from app.database.session import get_db
from app.integrations.agent_client import AIAgentClient
from app.schemas.api_schemas import ChatProxyRequest, ChatProxyResponse

router = APIRouter()
agent_client = AIAgentClient()


@router.post("", response_model=ChatProxyResponse)
@router.post("/", response_model=ChatProxyResponse, include_in_schema=False)
@router.post("/chat", response_model=ChatProxyResponse, include_in_schema=False)
async def chat_with_analyst(
    payload: ChatProxyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    ev = await db.get(Event, payload.event_id)
    if not ev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    session_id = payload.session_id or f"sess_{uuid.uuid4().hex[:12]}"

    # Attempt to proxy directly to the dedicated AI Agent
    agent_response = None
    if agent_client._enabled():
        try:
            agent_response = await agent_client.chat(
                event_id=ev.id,
                message=payload.message,
                session_id=session_id,
            )
        except Exception:
            agent_response = None

    if agent_response and "response" in agent_response:
        return ChatProxyResponse(
            session_id=agent_response.get("session_id", session_id),
            response=agent_response.get("response", ""),
            source="ai_agent",
            data_sources=agent_response.get("data_sources", ["ai_agent"]),
            is_data_stale=agent_response.get("is_data_stale", False),
            stale_warning=agent_response.get("stale_warning"),
            timestamp=datetime.now(timezone.utc),
        )

    # Pure deterministic DB-grounded intelligence fallback
    answer_text, sources = await _build_db_grounded_answer(db, ev, payload.message)
    return ChatProxyResponse(
        session_id=session_id,
        response=answer_text,
        source="rule_engine_grounded",
        data_sources=sources,
        is_data_stale=False,
        stale_warning=None,
        timestamp=datetime.now(timezone.utc),
    )


async def _build_db_grounded_answer(
    db: AsyncSession, ev: Event, message: str
) -> tuple[str, list[str]]:
    q = message.lower()
    sources = ["crowd_metrics", "risk_assessments", "predictions", "alerts"]

    # 1. Fetch latest processing job
    latest_job = (
        await db.execute(
            select(ProcessingJob)
            .where(ProcessingJob.event_id == ev.id)
            .order_by(desc(ProcessingJob.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    if not latest_job or latest_job.frames_processed == 0:
        return (
            f"No video analysis telemetry has been recorded yet for **{ev.name}**. "
            "Upload and process a recorded video in the Video Analysis module to generate real crowd density, "
            "zone occupancy, risk assessments, and multi-horizon forecasts.",
            ["processing_jobs"],
        )

    # 2. Find latest timestamp
    latest_ts = (
        await db.execute(
            select(func.max(CrowdMetric.video_timestamp_sec)).where(
                CrowdMetric.job_id == latest_job.id
            )
        )
    ).scalar_one_or_none()

    if latest_ts is None:
        return (
            f"Processing job `{latest_job.id[:8]}` ({latest_job.status}) has not produced zone metrics yet.",
            ["processing_jobs"],
        )

    # 3. Fetch latest metrics
    metrics = (
        await db.execute(
            select(CrowdMetric).where(
                CrowdMetric.job_id == latest_job.id,
                func.abs(CrowdMetric.video_timestamp_sec - float(latest_ts)) < 0.1,
            )
        )
    ).scalars().all()

    # 4. Fetch latest risks
    risks = (
        await db.execute(
            select(RiskAssessment).where(
                RiskAssessment.job_id == latest_job.id,
                func.abs(RiskAssessment.video_timestamp_sec - float(latest_ts)) < 0.1,
            )
        )
    ).scalars().all()

    # 5. Fetch active alerts
    alerts = (
        await db.execute(
            select(Alert)
            .where(Alert.event_id == ev.id, Alert.status == "ACTIVE")
            .order_by(desc(Alert.created_at))
            .limit(10)
        )
    ).scalars().all()

    # 6. Fetch 1m/3m predictions
    preds = (
        await db.execute(
            select(Prediction).where(
                Prediction.job_id == latest_job.id,
                func.abs(Prediction.video_timestamp_sec - float(latest_ts)) < 0.1,
            )
        )
    ).scalars().all()

    total_people = sum(m.people_count for m in metrics)
    max_metric = max(metrics, key=lambda m: m.occupancy_ratio) if metrics else None
    critical_risks = [r for r in risks if r.risk_level in ("HIGH", "CRITICAL")]

    # Synthesize tailored answers based on prompt context
    if any(k in q for k in ("risk", "danger", "critical", "safety", "hazard")):
        if critical_risks:
            details = "\n".join(
                f"- **{r.zone_name}**: `{r.risk_level}` priority `{r.monitoring_priority}`. {r.reason}"
                for r in critical_risks
            )
            return (
                f"### High-Risk Zones at timestamp {latest_ts:.1f}s\n"
                f"{details}\n\n"
                f"**Active alerts**: {len(alerts)} alert(s) currently unacknowledged.",
                sources,
            )
        else:
            return (
                f"All zones are currently operating within nominal parameters at timestamp {latest_ts:.1f}s. "
                f"No zones exhibit HIGH or CRITICAL risk. Highest occupancy is currently **{max_metric.zone_name if max_metric else 'N/A'}** "
                f"at {max_metric.occupancy_ratio * 100.0:.1f}% capacity.",
                sources,
            )

    if any(k in q for k in ("predict", "future", "forecast", "horizon", "trend", "grow")):
        forecast_lines = []
        for p in preds:
            if p.horizon_seconds in (60, 180):
                forecast_lines.append(
                    f"- **{p.zone_name}** (+{p.horizon_seconds}s): predicted occupancy {p.predicted_occupancy:.0f} "
                    f"({p.predicted_change_pct:+.1f}%), trend **{p.estimated_trend}**, category `{p.risk_category}` (conf: {p.confidence:.2f})"
                )
        if forecast_lines:
            return (
                f"### Short-Term Density Forecasts (Timestamp {latest_ts:.1f}s)\n"
                + "\n".join(forecast_lines)
                + "\n\n*Note: Predictions are probabilistic estimates based on localized trajectory and spatial momentum.*",
                sources,
            )

    if any(k in q for k in ("alert", "incident", "warning")):
        if alerts:
            al_text = "\n".join(
                f"- **[{a.severity}]** {a.title} ({a.zone_name}): {a.description}"
                for a in alerts
            )
            return f"### Active Event Alerts\n{al_text}", sources
        return "There are currently no active alerts for this event.", sources

    # Default overview
    zone_status = "\n".join(
        f"- **{m.zone_name}**: {m.people_count} people ({m.occupancy_ratio * 100.0:.1f}% cap), "
        f"flow {m.net_flow:+.1f}/min, speed {m.avg_speed:.2f} px/s [{m.movement_direction}]"
        for m in metrics
    )
    return (
        f"### Event Crowd Intelligence: {ev.name}\n"
        f"**Telemetry timestamp**: {latest_ts:.1f}s | **Total detected**: {total_people} people | **Active alerts**: {len(alerts)}\n\n"
        f"#### Current Zone Breakdown\n{zone_status}\n\n"
        f"Ask me about specific zones, 1m/3m predictions, high-risk areas, or recommended mitigation actions.",
        sources,
    )
