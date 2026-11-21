"""Tool Executor and Action Validation Engine for CROWD VISION AI Copilot."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database.models import (
    Alert,
    CrowdMetric,
    DetectionSummary,
    Event,
    OperatorAction,
    Prediction,
    ProcessingJob,
    Report,
    RiskAssessment,
    Task,
    TaskHistory,
    VenueLayout,
    Zone,
)
from app.services.video_processor import VideoProcessor, get_shared_detector
from app.services.ws_manager import ws_manager

logger = get_logger("copilot.executor")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CopilotToolExecutor:
    """Executes read-only inspection tools and validated actions against the database and telemetry."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ────────────────────────────────────────────────────────────────────────
    # READ-ONLY QUERY TOOLS
    # ────────────────────────────────────────────────────────────────────────

    async def get_active_task(self, task_id: str) -> dict[str, Any]:
        task = await self.db.get(Task, task_id)
        if not task:
            return {"error": f"Task '{task_id}' not found."}
        return {
            "id": task.id,
            "name": task.name,
            "description": task.description,
            "location": task.location,
            "state": task.state,
            "video_config": task.video_config,
            "analysis_settings": task.analysis_settings,
            "notes": task.notes,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }

    async def get_layout_zones(self, task_id: str) -> dict[str, Any]:
        task = await self.db.get(Task, task_id)
        if not task:
            return {"error": f"Task '{task_id}' not found."}
        snapshot = task.layout_snapshot or {}
        zones = snapshot.get("zones_data", [])
        return {
            "task_id": task.id,
            "task_name": task.name,
            "zones_count": len(zones),
            "zones": zones,
        }

    async def get_latest_telemetry(self, task_id: str) -> dict[str, Any]:
        # Check active telemetry cache
        cached = VideoProcessor.get_latest_telemetry(task_id)
        if cached:
            return cached

        # Fallback to latest database detection summary
        stmt = (
            select(DetectionSummary)
            .where(DetectionSummary.event_id == task_id)
            .order_by(desc(DetectionSummary.video_timestamp_sec))
            .limit(1)
        )
        det = (await self.db.execute(stmt)).scalar_one_or_none()
        if not det:
            return {
                "task_id": task_id,
                "status": "NO_TELEMETRY",
                "total_people": 0,
                "video_timestamp_sec": 0.0,
                "message": "No real-time video telemetry recorded yet for this task."
            }

        return {
            "task_id": task_id,
            "video_timestamp_sec": det.video_timestamp_sec,
            "total_people": det.total_people,
            "inference_ms": det.inference_ms,
            "detections_count": len(det.detections),
            "detections": det.detections[:10],
        }

    async def get_zone_metrics(self, task_id: str, zone_id: Optional[str] = None) -> dict[str, Any]:
        # Find latest metric timestamp for the task
        latest_ts = (
            await self.db.execute(
                select(func.max(CrowdMetric.video_timestamp_sec)).where(CrowdMetric.event_id == task_id)
            )
        ).scalar_one_or_none()

        if latest_ts is None:
            return {"task_id": task_id, "metrics": [], "message": "No zone metrics recorded yet."}

        stmt = select(CrowdMetric).where(
            CrowdMetric.event_id == task_id,
            func.abs(CrowdMetric.video_timestamp_sec - float(latest_ts)) < 0.1,
        )
        if zone_id:
            stmt = stmt.where(CrowdMetric.zone_id == zone_id)

        rows = (await self.db.execute(stmt)).scalars().all()
        return {
            "task_id": task_id,
            "video_timestamp_sec": float(latest_ts),
            "metrics": [
                {
                    "zone_id": m.zone_id,
                    "zone_name": m.zone_name,
                    "people_count": m.people_count,
                    "occupancy_ratio": m.occupancy_ratio,
                    "capacity_utilization_pct": m.capacity_utilization_pct,
                    "density_value": m.density_value,
                    "inflow_rate": m.inflow_rate,
                    "outflow_rate": m.outflow_rate,
                    "net_flow": m.net_flow,
                    "avg_speed": m.avg_speed,
                    "movement_direction": m.movement_direction,
                    "is_bottleneck": m.is_bottleneck,
                    "is_counterflow": m.is_counterflow,
                }
                for m in rows
            ],
        }

    async def get_zone_risk(self, task_id: str, zone_id: Optional[str] = None) -> dict[str, Any]:
        latest_ts = (
            await self.db.execute(
                select(func.max(RiskAssessment.video_timestamp_sec)).where(RiskAssessment.event_id == task_id)
            )
        ).scalar_one_or_none()

        if latest_ts is None:
            return {"task_id": task_id, "risks": [], "message": "No risk assessments recorded yet."}

        stmt = select(RiskAssessment).where(
            RiskAssessment.event_id == task_id,
            func.abs(RiskAssessment.video_timestamp_sec - float(latest_ts)) < 0.1,
        )
        if zone_id:
            stmt = stmt.where(RiskAssessment.zone_id == zone_id)

        rows = (await self.db.execute(stmt)).scalars().all()
        return {
            "task_id": task_id,
            "video_timestamp_sec": float(latest_ts),
            "risks": [
                {
                    "zone_id": r.zone_id,
                    "zone_name": r.zone_name,
                    "risk_level": r.risk_level,
                    "reason": r.reason,
                    "monitoring_priority": r.monitoring_priority,
                    "requires_human_review": r.requires_human_review,
                }
                for r in rows
            ],
        }

    async def get_predictions(self, task_id: str, horizon_seconds: Optional[int] = None) -> dict[str, Any]:
        latest_ts = (
            await self.db.execute(
                select(func.max(Prediction.video_timestamp_sec)).where(Prediction.event_id == task_id)
            )
        ).scalar_one_or_none()

        if latest_ts is None:
            return {"task_id": task_id, "predictions": [], "message": "No predictions generated yet."}

        stmt = select(Prediction).where(
            Prediction.event_id == task_id,
            func.abs(Prediction.video_timestamp_sec - float(latest_ts)) < 0.1,
        )
        if horizon_seconds:
            stmt = stmt.where(Prediction.horizon_seconds == horizon_seconds)

        rows = (await self.db.execute(stmt)).scalars().all()
        return {
            "task_id": task_id,
            "video_timestamp_sec": float(latest_ts),
            "predictions": [
                {
                    "zone_id": p.zone_id,
                    "zone_name": p.zone_name,
                    "horizon_seconds": p.horizon_seconds,
                    "predicted_occupancy": p.predicted_occupancy,
                    "predicted_change_pct": p.predicted_change_pct,
                    "estimated_trend": p.estimated_trend,
                    "risk_category": p.risk_category,
                    "confidence": p.confidence,
                }
                for p in rows
            ],
        }

    async def get_active_alerts(self, task_id: str, severity: Optional[str] = None) -> dict[str, Any]:
        stmt = select(Alert).where(Alert.event_id == task_id, Alert.status == "ACTIVE").order_by(desc(Alert.created_at))
        if severity:
            stmt = stmt.where(Alert.severity == severity.upper())

        rows = (await self.db.execute(stmt.limit(25))).scalars().all()
        return {
            "task_id": task_id,
            "active_alerts_count": len(rows),
            "alerts": [
                {
                    "id": a.id,
                    "zone_id": a.zone_id,
                    "zone_name": a.zone_name,
                    "severity": a.severity,
                    "category": a.category,
                    "title": a.title,
                    "description": a.description,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in rows
            ],
        }

    async def get_task_history(self, task_id: str, limit: int = 15) -> dict[str, Any]:
        stmt = select(TaskHistory).where(TaskHistory.task_id == task_id).order_by(desc(TaskHistory.timestamp)).limit(limit)
        rows = (await self.db.execute(stmt)).scalars().all()
        return {
            "task_id": task_id,
            "history": [
                {
                    "id": h.id,
                    "event_type": h.event_type,
                    "details": h.details,
                    "timestamp": h.timestamp.isoformat() if h.timestamp else None,
                }
                for h in rows
            ],
        }

    async def get_system_health(self) -> dict[str, Any]:
        detector = get_shared_detector()
        return {
            "status": "HEALTHY",
            "detector_backend": detector.backend_name,
            "ws_active_connections": ws_manager.connection_count(),
            "timestamp": _utcnow().isoformat(),
        }

    # ────────────────────────────────────────────────────────────────────────
    # ACTION VALIDATION
    # ────────────────────────────────────────────────────────────────────────

    async def validate_action(
        self,
        action_type: str,
        parameters: dict[str, Any],
        task_id: Optional[str] = None,
    ) -> tuple[bool, list[str], Optional[str]]:
        errors: list[str] = []
        impact: Optional[str] = None
        act = action_type.lower().strip()

        tid = task_id or parameters.get("task_id")

        if act == "adjust_zone_capacity":
            cap = parameters.get("new_capacity")
            zid = parameters.get("zone_id")
            if not tid:
                errors.append("Task ID is required for zone capacity adjustment.")
            if not zid:
                if tid:
                    t = await self.db.get(Task, tid)
                    if t and t.layout_snapshot and t.layout_snapshot.get("zones_data"):
                        zid = t.layout_snapshot["zones_data"][0].get("id") or "zone-1"
                        parameters["zone_id"] = zid
                    else:
                        zid = "zone-1"
                        parameters["zone_id"] = zid
                else:
                    errors.append("Zone ID is required.")
            if cap is None or not isinstance(cap, int) or cap <= 0:
                errors.append("New capacity must be a positive integer greater than zero.")
            elif cap > 50000:
                errors.append("Capacity exceeds the safe maximum architectural limit of 50,000.")
            else:
                impact = f"Re-calibrates warning threshold to {int(cap * 0.7)} and critical threshold to {int(cap * 0.9)} occupants for zone {zid}."

        elif act == "transition_task_state":
            new_st = str(parameters.get("new_state", "")).upper()
            allowed = {"DRAFT", "CONFIGURING", "READY", "PROCESSING", "LIVE", "PAUSED", "COMPLETED"}
            if not tid:
                errors.append("Task ID is required.")
            if new_st not in allowed:
                errors.append(f"Invalid target state '{new_st}'. Must be one of: {', '.join(sorted(allowed))}.")
            else:
                impact = f"Transitions task lifecycle state to '{new_st}'. Updates system monitoring state."

        elif act in ("start_task_analysis", "pause_task_analysis", "resume_task_analysis", "stop_task_analysis"):
            if not tid:
                errors.append("Task ID is required.")
            else:
                task = await self.db.get(Task, tid)
                if not task:
                    errors.append(f"Task '{tid}' does not exist.")
                else:
                    impact = f"Applies operational action '{act}' to processing pipeline for task '{task.name}'."

        elif act == "acknowledge_alert":
            aid = parameters.get("alert_id")
            if not aid:
                errors.append("Alert ID is required.")
            else:
                alert = await self.db.get(Alert, aid)
                if not alert:
                    errors.append(f"Alert '{aid}' not found.")
                elif alert.status == "RESOLVED":
                    errors.append("Alert is already resolved.")
                else:
                    impact = f"Marks alert '{alert.title}' as ACKNOWLEDGED."

        elif act == "resolve_alert":
            aid = parameters.get("alert_id")
            if not aid:
                errors.append("Alert ID is required.")
            else:
                alert = await self.db.get(Alert, aid)
                if not alert:
                    errors.append(f"Alert '{aid}' not found.")
                else:
                    impact = f"Marks alert '{alert.title}' as RESOLVED and records resolution notes."

        elif act == "generate_incident_report":
            if not tid:
                errors.append("Task ID is required.")
            else:
                impact = f"Generates an official post-incident summary report for task {tid}."

        else:
            errors.append(f"Unrecognized or unsupported action type '{action_type}'.")

        return len(errors) == 0, errors, impact

    # ────────────────────────────────────────────────────────────────────────
    # ACTION EXECUTION
    # ────────────────────────────────────────────────────────────────────────

    async def execute_action(
        self,
        action_type: str,
        parameters: dict[str, Any],
        task_id: Optional[str] = None,
        confirmed_by: str = "operator",
    ) -> dict[str, Any]:
        is_valid, errors, impact = await self.validate_action(action_type, parameters, task_id)
        if not is_valid:
            raise ValueError(f"Action validation failed: {'; '.join(errors)}")

        tid = task_id or parameters.get("task_id")
        act = action_type.lower().strip()
        result: dict[str, Any] = {}
        now = _utcnow()

        if act == "adjust_zone_capacity":
            zid = parameters.get("zone_id")
            new_cap = int(parameters["new_capacity"])
            task = await self.db.get(Task, tid)
            if not task:
                raise ValueError(f"Task '{tid}' not found.")

            snapshot = task.layout_snapshot or {}
            zones = snapshot.get("zones_data", [])
            if not zid and zones:
                zid = zones[0].get("id") or zones[0].get("zone_id") or "zone-1"
            updated = False
            for z in zones:
                if z.get("id") == zid or z.get("zone_id") == zid:
                    z["capacity"] = new_cap
                    z["max_capacity"] = new_cap
                    updated = True
                    break

            if not updated and zones:
                zones[0]["capacity"] = new_cap
                zones[0]["max_capacity"] = new_cap

            task.layout_snapshot = {**snapshot, "zones_data": zones}
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(task, "layout_snapshot")
            task.updated_at = now

            # Audit log
            hist = TaskHistory(
                task_id=task.id,
                event_type="CAPACITY_ADJUSTED_BY_COPILOT",
                details={"zone_id": zid, "new_capacity": new_cap, "confirmed_by": confirmed_by},
                timestamp=now,
            )
            self.db.add(hist)
            await self.db.commit()
            await self.db.refresh(task)

            result = {"task_id": task.id, "zone_id": zid, "new_capacity": new_cap, "zones": zones}

        elif act == "transition_task_state":
            new_state = str(parameters["new_state"]).upper()
            reason = parameters.get("reason", f"State transition initiated via Copilot by {confirmed_by}")
            task = await self.db.get(Task, tid)
            if not task:
                raise ValueError(f"Task '{tid}' not found.")

            old_state = task.state
            task.state = new_state
            task.updated_at = now

            hist = TaskHistory(
                task_id=task.id,
                event_type="STATE_CHANGED",
                details={"from": old_state, "to": new_state, "reason": reason, "confirmed_by": confirmed_by},
                timestamp=now,
            )
            self.db.add(hist)
            await self.db.commit()
            await self.db.refresh(task)

            result = {"task_id": task.id, "old_state": old_state, "new_state": new_state, "reason": reason}

        elif act == "start_task_analysis":
            fps = float(parameters.get("sample_fps", 2.0))
            task = await self.db.get(Task, tid)
            if not task:
                raise ValueError(f"Task '{tid}' not found.")

            video_id = task.video_config.get("video_id") or task.video_config.get("file_id") or task.id
            job_id = f"job_{uuid.uuid4().hex[:12]}"
            job = ProcessingJob(
                id=job_id,
                event_id=task.id,
                video_file_id=video_id,
                status="RUNNING",
                sample_fps=fps,
                camera_perspective=task.video_config.get("camera_perspective", "drone_top_down"),
                layout_id=task.layout_id,
                started_at=now,
            )
            self.db.add(job)
            task.state = "PROCESSING"
            task.updated_at = now

            hist = TaskHistory(
                task_id=task.id,
                event_type="ANALYSIS_STARTED_BY_COPILOT",
                details={"job_id": job_id, "sample_fps": fps, "confirmed_by": confirmed_by},
                timestamp=now,
            )
            self.db.add(hist)
            await self.db.commit()

            VideoProcessor.launch_job(
                job_id=job_id,
                video_id=video_id,
                event_id=task.id,
                sample_fps=fps,
                layout_id=task.layout_id,
                camera_perspective=task.video_config.get("camera_perspective", "drone_top_down"),
            )
            result = {"task_id": task.id, "job_id": job_id, "status": "RUNNING"}

        elif act == "pause_task_analysis":
            stmt = select(ProcessingJob).where(ProcessingJob.event_id == tid).order_by(desc(ProcessingJob.created_at)).limit(1)
            job = (await self.db.execute(stmt)).scalar_one_or_none()
            if job:
                VideoProcessor.pause_processing(job.id)
                job.status = "PAUSED"
            task = await self.db.get(Task, tid)
            if task:
                task.state = "PAUSED"
                task.updated_at = now
                hist = TaskHistory(
                    task_id=task.id,
                    event_type="ANALYSIS_PAUSED_BY_COPILOT",
                    details={"confirmed_by": confirmed_by},
                    timestamp=now,
                )
                self.db.add(hist)
            await self.db.commit()
            result = {"task_id": tid, "status": "PAUSED"}

        elif act == "resume_task_analysis":
            stmt = select(ProcessingJob).where(ProcessingJob.event_id == tid).order_by(desc(ProcessingJob.created_at)).limit(1)
            job = (await self.db.execute(stmt)).scalar_one_or_none()
            if job:
                VideoProcessor.resume_processing(job.id)
                job.status = "RUNNING"
            task = await self.db.get(Task, tid)
            if task:
                task.state = "PROCESSING"
                task.updated_at = now
                hist = TaskHistory(
                    task_id=task.id,
                    event_type="ANALYSIS_RESUMED_BY_COPILOT",
                    details={"confirmed_by": confirmed_by},
                    timestamp=now,
                )
                self.db.add(hist)
            await self.db.commit()
            result = {"task_id": tid, "status": "PROCESSING"}

        elif act == "stop_task_analysis":
            stmt = select(ProcessingJob).where(ProcessingJob.event_id == tid).order_by(desc(ProcessingJob.created_at)).limit(1)
            job = (await self.db.execute(stmt)).scalar_one_or_none()
            if job:
                VideoProcessor.stop_processing(job.id)
                job.status = "STOPPED"
                job.completed_at = now
            task = await self.db.get(Task, tid)
            if task:
                task.state = "COMPLETED"
                task.updated_at = now
                hist = TaskHistory(
                    task_id=task.id,
                    event_type="ANALYSIS_STOPPED_BY_COPILOT",
                    details={"confirmed_by": confirmed_by},
                    timestamp=now,
                )
                self.db.add(hist)
            await self.db.commit()
            result = {"task_id": tid, "status": "STOPPED"}

        elif act == "acknowledge_alert":
            aid = parameters["alert_id"]
            note = parameters.get("note", "Acknowledged via Copilot action")
            alert = await self.db.get(Alert, aid)
            if not alert:
                raise ValueError(f"Alert '{aid}' not found.")
            alert.status = "ACKNOWLEDGED"
            alert.acknowledged_by = confirmed_by
            alert.acknowledged_at = now
            if note:
                alert.resolution_note = (f"[Ack: {note}] " + (alert.resolution_note or "")).strip()
            await self.db.commit()
            result = {"alert_id": alert.id, "status": "ACKNOWLEDGED"}

        elif act == "resolve_alert":
            aid = parameters["alert_id"]
            res_note = parameters.get("resolution_note", f"Resolved via Copilot by {confirmed_by}")
            alert = await self.db.get(Alert, aid)
            if not alert:
                raise ValueError(f"Alert '{aid}' not found.")
            alert.status = "RESOLVED"
            alert.resolved_by = confirmed_by
            alert.resolved_at = now
            alert.resolution_note = res_note
            await self.db.commit()
            result = {"alert_id": alert.id, "status": "RESOLVED"}

        elif act == "generate_incident_report":
            title = parameters.get("title", f"Incident Report for Task {tid}")
            # Ensure event exists or link to task
            ev = await self.db.get(Event, tid)
            event_id = ev.id if ev else tid
            # If event not present in events table, ensure a dummy event entry or report record
            report = Report(
                event_id=event_id,
                title=title,
                generated_by=confirmed_by,
                summary_data={
                    "task_id": tid,
                    "generated_at": now.isoformat(),
                    "source": "AI_COPILOT_ACTION",
                    "status": "OFFICIAL",
                },
                created_at=now,
            )
            # Check if event exists to satisfy FK constraint if needed
            if ev:
                self.db.add(report)
                await self.db.commit()
            result = {"task_id": tid, "title": title, "report_id": getattr(report, "id", None)}

        # Also record in OperatorAction table
        action_log = OperatorAction(
            event_id=tid,
            user_email=confirmed_by,
            action_type=action_type,
            target_type="TASK" if tid else "SYSTEM",
            target_id=tid or "SYSTEM",
            details=parameters,
            created_at=now,
        )
        self.db.add(action_log)
        await self.db.commit()

        return result
