"""AI Copilot Orchestration Service for CROWD VISION."""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Optional
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.copilot.executor import CopilotToolExecutor
from app.copilot.provider import get_llm_provider
from app.copilot.tools import get_all_tools
from app.core.logging import get_logger
from app.database.models import Task
from app.schemas.api_schemas import CopilotActionProposal, CopilotQueryResponse

logger = get_logger("copilot.service")

COPILOT_SYSTEM_PROMPT = """You are CROWD VISION AI Copilot, an intelligent operational copilot for computer vision-based crowd monitoring, risk analysis, and venue safety.
You are directly connected to authoritative database records, real-time video detection telemetry, zone capacities, and risk models.

OPERATING PRINCIPLES:
1. TRUTHFULNESS: Base all answers strictly on the authoritative context provided. Never fabricate crowd headcounts, density metrics, or risk levels.
2. ACTION PROPOSALS: When the operator indicates an operational change (e.g. adjust capacity, pause task, start analysis, acknowledge alerts), clearly articulate the proposed change and state that confirmation is required.
3. CONCISENESS & PROFESSIONALISM: Use clear markdown with bullet points, bold highlights, and technical clarity appropriate for emergency operations centers and venue safety controllers.
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CopilotService:
    """Coordinates context retrieval, tool execution, LLM synthesis, and action proposals."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.executor = CopilotToolExecutor(db)
        self.provider = get_llm_provider()

    async def query(
        self,
        message: str,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        context_override: Optional[dict[str, Any]] = None,
    ) -> CopilotQueryResponse:
        sess_id = session_id or f"copilot_sess_{uuid.uuid4().hex[:10]}"
        sources: list[str] = ["system_tools"]

        if not task_id:
            return CopilotQueryResponse(
                session_id=sess_id,
                response=(
                    "No active monitoring task is selected. Please select or create a task from the Topbar "
                    "to view spatial layout, zone capacities, and video telemetry."
                ),
                source="grounded_copilot_core",
                data_sources=sources,
                action_proposal=None,
                timestamp=_utcnow(),
            )

        # 1. Retrieve full grounding context for the task
        grounding_context: dict[str, Any] = {
            "task": {},
            "zones": [],
            "telemetry": {},
            "metrics": [],
            "risks": [],
            "predictions": [],
            "alerts": [],
        }

        task: Optional[Task] = None
        if task_id:
            task_res = await self.executor.get_active_task(task_id)
            if "error" not in task_res:
                grounding_context["task"] = task_res
                sources.append("tasks_database")

            zones_res = await self.executor.get_layout_zones(task_id)
            grounding_context["zones"] = zones_res.get("zones", [])
            sources.append("layout_snapshot")

            telem_res = await self.executor.get_latest_telemetry(task_id)
            grounding_context["telemetry"] = telem_res
            sources.append("video_telemetry")

            metrics_res = await self.executor.get_zone_metrics(task_id)
            grounding_context["metrics"] = metrics_res.get("metrics", [])
            sources.append("crowd_metrics")

            risks_res = await self.executor.get_zone_risk(task_id)
            grounding_context["risks"] = risks_res.get("risks", [])
            sources.append("risk_engine")

            preds_res = await self.executor.get_predictions(task_id)
            grounding_context["predictions"] = preds_res.get("predictions", [])
            sources.append("prediction_engine")

            alerts_res = await self.executor.get_active_alerts(task_id)
            grounding_context["alerts"] = alerts_res.get("alerts", [])
            sources.append("active_alerts")

        if context_override:
            grounding_context.update(context_override)

        # 2. Check for action proposal intent
        action_proposal = self._detect_action_proposal(message, task_id, grounding_context)

        # 3. Formulate response via active LLM provider (Gemini or Deterministic)
        response_text = await self.provider.generate_response(
            system_instruction=COPILOT_SYSTEM_PROMPT,
            user_message=message,
            grounding_context=grounding_context,
        )

        if not response_text:
            # Deterministic fallback guaranteed
            from app.copilot.provider import DeterministicGroundedProvider
            fallback = DeterministicGroundedProvider()
            response_text = await fallback.generate_response(
                system_instruction=COPILOT_SYSTEM_PROMPT,
                user_message=message,
                grounding_context=grounding_context,
            )

        # Append action confirmation notice if a proposal was formulated
        if action_proposal and "Action Proposal" not in response_text:
            response_text += (
                f"\n\n> [!NOTE]\n"
                f"> **Action Proposal Prepared:** `{action_proposal.action_type}`\n"
                f"> **Rationale:** {action_proposal.rationale}\n"
                f"> Review and click **Approve & Execute Action** below to apply this update."
            )

        return CopilotQueryResponse(
            session_id=sess_id,
            response=response_text or "No response generated.",
            source=self.provider.name,
            data_sources=sources,
            action_proposal=action_proposal,
            timestamp=_utcnow(),
        )

    def _detect_action_proposal(
        self,
        message: str,
        task_id: Optional[str],
        context: dict[str, Any],
    ) -> Optional[CopilotActionProposal]:
        if not task_id:
            return None

        msg = message.lower().strip()
        zones = context.get("zones", [])
        task = context.get("task", {})
        task_name = task.get("name", "Active Task")

        # Capacity adjustment
        if "capacity" in msg and any(k in msg for k in ("change", "increase", "set", "update", "adjust", "raise", "modify", "boost", "to")):
            nums = re.findall(r"\b\d+\b", msg)
            target_cap = int(nums[0]) if nums else 250
            target_zid = None
            target_zname = None

            for z in zones:
                zid = str(z.get("id") or z.get("zone_id") or "")
                zname = str(z.get("name") or z.get("zone_name") or "")
                if zid and zid.lower() in msg:
                    target_zid = zid
                    target_zname = zname
                    break
                if zname and zname.lower() in msg:
                    target_zid = zid
                    target_zname = zname
                    break

            if not target_zid and zones:
                first = zones[0]
                target_zid = first.get("id") or first.get("zone_id") or "zone-1"
                target_zname = first.get("name") or first.get("zone_name") or "Zone 1"

            if target_zid:
                return CopilotActionProposal(
                    action_type="adjust_zone_capacity",
                    parameters={"task_id": task_id, "zone_id": target_zid, "new_capacity": target_cap},
                    rationale=f"Operator requested updating maximum design capacity for {target_zname or target_zid} to {target_cap} persons.",
                    risk_assessment=f"Shifts warning threshold to {int(target_cap * 0.7)} and critical surge threshold to {int(target_cap * 0.9)}.",
                    requires_approval=True,
                )

        # Pause task / analysis
        if any(k in msg for k in ("pause", "halt", "suspend")) and any(k in msg for k in ("monitoring", "task", "analysis", "video", "job", "processing")):
            return CopilotActionProposal(
                action_type="pause_task_analysis",
                parameters={"task_id": task_id},
                rationale=f"Operator requested pause of real-time monitoring and inference on {task_name}.",
                risk_assessment="Halts CV frame inference and alerts ingestion until resumed.",
                requires_approval=True,
            )

        # Resume task / analysis
        if any(k in msg for k in ("resume", "unpause", "continue")) and any(k in msg for k in ("monitoring", "task", "analysis", "video", "job", "processing")):
            return CopilotActionProposal(
                action_type="resume_task_analysis",
                parameters={"task_id": task_id},
                rationale=f"Resume video inference and live risk telemetry ingestion for {task_name}.",
                risk_assessment="Resumes frame sampling and live WebSocket broadcast.",
                requires_approval=True,
            )

        # Stop task / analysis
        if any(k in msg for k in ("stop", "terminate", "kill", "cancel", "end")) and any(k in msg for k in ("monitoring", "task", "analysis", "video", "job", "processing")):
            return CopilotActionProposal(
                action_type="stop_task_analysis",
                parameters={"task_id": task_id},
                rationale=f"Permanently conclude video analysis pipeline for {task_name}.",
                risk_assessment="Concludes processing job and marks task as COMPLETED.",
                requires_approval=True,
            )

        # Transition state
        if "ready" in msg and any(v in msg for v in ("set", "mark", "state", "status", "transition")):
            return CopilotActionProposal(
                action_type="transition_task_state",
                parameters={"task_id": task_id, "new_state": "READY", "reason": "Operator configured and confirmed ready for analysis."},
                rationale=f"Transition task {task_name} to READY state.",
                risk_assessment="Allows processing jobs to be launched on this task.",
                requires_approval=True,
            )

        # Acknowledge all alerts
        alerts = context.get("alerts", [])
        if any(k in msg for k in ("acknowledge alert", "ack alert", "silence alert")) and alerts:
            first_alert = alerts[0]
            return CopilotActionProposal(
                action_type="acknowledge_alert",
                parameters={"alert_id": first_alert["id"], "note": "Acknowledged by operator via Copilot"},
                rationale=f"Acknowledge safety alert: {first_alert.get('title')}",
                risk_assessment="Changes alert state from ACTIVE to ACKNOWLEDGED.",
                requires_approval=True,
            )

        return None
