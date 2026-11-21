"""Tool execution dispatcher and response sanitizer for the conversational agent."""

from __future__ import annotations

from typing import Any, Optional

from app.core.event_context import EventContext
from app.core.orchestrator import AgentOrchestrator
from app.monitoring.logger import get_logger
from app.schemas.models import AlertPriority, RiskLevel

logger = get_logger("llm.response_parser")


class ToolExecutor:
    """Executes authorized structured tool calls safely against the live application state."""

    def __init__(self, orchestrator: AgentOrchestrator) -> None:
        self.orchestrator = orchestrator

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any], event_id: str) -> dict[str, Any]:
        """Dispatch structured tool call to the authoritative backend service."""
        context = self.orchestrator.event_context_manager.get_context(event_id)
        if not context:
            return {"error": f"Event '{event_id}' is not registered or active."}

        try:
            if tool_name == "get_zone_status":
                return await self._get_zone_status(context, arguments.get("zone_id", ""))

            elif tool_name == "get_all_zones_summary":
                return await self._get_all_zones_summary(context)

            elif tool_name == "get_zone_risk":
                return await self._get_zone_risk(context, arguments.get("zone_id", ""))

            elif tool_name == "get_zone_prediction":
                return await self._get_zone_prediction(context, arguments.get("zone_id", ""))

            elif tool_name == "get_active_alerts":
                return await self._get_active_alerts(event_id, arguments)

            elif tool_name == "get_recommendations":
                return await self._get_recommendations(event_id, arguments.get("zone_id"))

            elif tool_name == "get_most_crowded_zone":
                return await self._get_most_crowded_zone(context)

            elif tool_name == "get_highest_risk_zone":
                return await self._get_highest_risk_zone(context)

            elif tool_name == "compare_current_vs_predicted":
                return await self._compare_current_vs_predicted(context)

            elif tool_name == "get_zones_with_increasing_inflow":
                return await self._get_zones_with_increasing_inflow(context)

            else:
                return {"error": f"Unrecognized or unauthorized tool: '{tool_name}'"}

        except Exception as exc:
            logger.error("Error executing tool call", tool=tool_name, error=str(exc))
            return {"error": f"Tool execution failed: {str(exc)}"}

    async def _get_zone_status(self, context: EventContext, zone_id: str) -> dict[str, Any]:
        zone_config = context.get_zone_config(zone_id)
        if not zone_config:
            return {"error": f"Zone '{zone_id}' not found in venue layout."}

        data = context.get_latest_data(zone_id)
        if not data:
            return {
                "zone_id": zone_id,
                "zone_name": zone_config.zone_name,
                "status": "No analytical data received yet for this zone",
            }

        occ_pct = (data.people_count / max(zone_config.capacity, 1)) * 100.0
        return {
            "zone_id": zone_id,
            "zone_name": zone_config.zone_name,
            "people_count": data.people_count,
            "capacity": zone_config.capacity,
            "occupancy_pct": round(occ_pct, 1),
            "density": data.estimated_density,
            "inflow_rate": data.inflow_rate,
            "outflow_rate": data.outflow_rate,
            "movement_speed": data.movement_speed,
            "movement_direction": data.movement_direction.value if data.movement_direction else None,
            "timestamp": data.timestamp.isoformat(),
            "data_is_stale": context.is_data_stale,
        }

    async def _get_all_zones_summary(self, context: EventContext) -> dict[str, Any]:
        zones = []
        for z in context.venue.zones:
            latest = context.get_latest_data(z.zone_id)
            assessment = context.get_latest_assessment(z.zone_id)
            occ_pct = ((latest.people_count / z.capacity) * 100.0) if latest and z.capacity > 0 else 0.0

            zones.append({
                "zone_id": z.zone_id,
                "zone_name": z.zone_name,
                "capacity": z.capacity,
                "people_count": latest.people_count if latest else 0,
                "occupancy_pct": round(occ_pct, 1),
                "risk_level": assessment.risk_level.value if assessment else "NORMAL",
            })
        return {"event_id": context.event_id, "zones": zones, "is_data_stale": context.is_data_stale}

    async def _get_zone_risk(self, context: EventContext, zone_id: str) -> dict[str, Any]:
        assessment = context.get_latest_assessment(zone_id)
        if not assessment:
            return {"zone_id": zone_id, "status": "No risk assessment computed yet"}

        return {
            "zone_id": assessment.zone_id,
            "zone_name": assessment.zone_name,
            "risk_level": assessment.risk_level.value,
            "previous_risk": assessment.previous_risk_level.value if assessment.previous_risk_level else None,
            "occupancy_ratio": assessment.occupancy_ratio,
            "density": assessment.density,
            "people_count": assessment.people_count,
            "risk_factors": [f.model_dump(mode="json") for f in assessment.risk_factors],
            "explanation": assessment.explanation,
        }

    async def _get_zone_prediction(self, context: EventContext, zone_id: str) -> dict[str, Any]:
        zone_config = context.get_zone_config(zone_id)
        data = context.get_latest_data(zone_id)
        if not data or not zone_config:
            return {"zone_id": zone_id, "status": "No prediction data available"}

        assessment = context.get_latest_assessment(zone_id)
        current_risk = assessment.risk_level if assessment else RiskLevel.NORMAL

        preds = await self.orchestrator.prediction_interpreter.interpret(data, zone_config, current_risk)
        return {
            "zone_id": zone_id,
            "zone_name": zone_config.zone_name,
            "predictions": [p.model_dump(mode="json") for p in preds],
        }

    async def _get_active_alerts(self, event_id: str, args: dict[str, Any]) -> dict[str, Any]:
        zone_id = args.get("zone_id")
        priority = args.get("priority")
        alerts = self.orchestrator.get_alerts(event_id, zone_id=zone_id, priority=priority)
        return {
            "count": len(alerts),
            "alerts": [a.model_dump(mode="json") for a in alerts],
        }

    async def _get_recommendations(self, event_id: str, zone_id: Optional[str]) -> dict[str, Any]:
        recs = self.orchestrator.get_recommendations(event_id)
        if zone_id:
            recs = [r for r in recs if r.affected_zone == zone_id]
        return {
            "count": len(recs),
            "recommendations": [r.model_dump(mode="json") for r in recs],
        }

    async def _get_most_crowded_zone(self, context: EventContext) -> dict[str, Any]:
        latest_items = context.get_all_latest()
        if not latest_items:
            return {"message": "No crowd data available for any zone"}

        highest_zone_id = None
        highest_occ = -1.0
        highest_count = -1

        for zid, data in latest_items.items():
            zcfg = context.get_zone_config(zid)
            cap = zcfg.capacity if zcfg else 100
            occ = data.people_count / max(cap, 1)
            if occ > highest_occ:
                highest_occ = occ
                highest_zone_id = zid
                highest_count = data.people_count

        zcfg = context.get_zone_config(highest_zone_id)
        return {
            "zone_id": highest_zone_id,
            "zone_name": zcfg.zone_name if zcfg else highest_zone_id,
            "people_count": highest_count,
            "capacity": zcfg.capacity if zcfg else None,
            "occupancy_pct": round(highest_occ * 100.0, 1),
        }

    async def _get_highest_risk_zone(self, context: EventContext) -> dict[str, Any]:
        assessments = context.get_all_latest_assessments()
        if not assessments:
            return {"message": "No risk assessments computed yet"}

        highest_assessment = max(assessments.values(), key=lambda a: a.risk_level.severity_order)
        return {
            "zone_id": highest_assessment.zone_id,
            "zone_name": highest_assessment.zone_name,
            "risk_level": highest_assessment.risk_level.value,
            "people_count": highest_assessment.people_count,
            "occupancy_ratio": highest_assessment.occupancy_ratio,
            "explanation": highest_assessment.explanation,
        }

    async def _compare_current_vs_predicted(self, context: EventContext) -> dict[str, Any]:
        comparisons = []
        for zone in context.venue.zones:
            data = context.get_latest_data(zone.zone_id)
            if not data:
                continue

            current_occ = (data.people_count / max(zone.capacity, 1)) * 100.0
            predicted_occ = (data.predicted_occupancy * 100.0) if data.predicted_occupancy is not None else None

            comparisons.append({
                "zone_id": zone.zone_id,
                "zone_name": zone.zone_name,
                "current_occupancy_pct": round(current_occ, 1),
                "predicted_occupancy_pct": round(predicted_occ, 1) if predicted_occ is not None else None,
                "forecast_horizon_seconds": data.forecast_horizon_seconds,
                "confidence": data.forecast_confidence,
            })
        return {"comparisons": comparisons}

    async def _get_zones_with_increasing_inflow(self, context: EventContext) -> dict[str, Any]:
        increasing_zones = []
        for zone in context.venue.zones:
            data = context.get_latest_data(zone.zone_id)
            if data and data.inflow_rate and data.outflow_rate:
                if data.inflow_rate > data.outflow_rate:
                    increasing_zones.append({
                        "zone_id": zone.zone_id,
                        "zone_name": zone.zone_name,
                        "inflow_rate": data.inflow_rate,
                        "outflow_rate": data.outflow_rate,
                        "net_inflow": round(data.inflow_rate - data.outflow_rate, 2),
                    })
        return {"increasing_zones": increasing_zones}
