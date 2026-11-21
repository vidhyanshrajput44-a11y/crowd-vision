"""Intelligent recommendation engine.

Generates context-aware operational recommendations for event stewards,
security, operations, and management teams without performing autonomous physical interventions.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.monitoring.logger import get_logger
from app.recommendations.action_catalog import ACTION_CATALOG, ActionTemplate
from app.schemas.models import (
    PredictionInterpretation,
    Recommendation,
    RecommendationPriority,
    RiskLevel,
    ZoneConfig,
    ZoneRiskAssessment,
)

logger = get_logger("recommendations.engine")


class RecommendationEngine:
    """Generates context-aware, prioritized recommendations with deduplication."""

    def __init__(self, dedup_window_seconds: int = 300) -> None:
        self._dedup_window = timedelta(seconds=dedup_window_seconds)
        # key: f"{event_id}:{zone_id}:{action_hash}" -> datetime
        self._emitted_history: dict[str, datetime] = {}
        # active cache: event_id -> list[Recommendation]
        self._active_recommendations: dict[str, list[Recommendation]] = defaultdict(list)

    async def generate(
        self,
        risk_assessment: ZoneRiskAssessment,
        analysis: dict[str, Any],
        predictions: list[PredictionInterpretation],
        zone_config: ZoneConfig,
        event_id: str,
    ) -> list[Recommendation]:
        """Generate context-aware operational recommendations for a zone."""
        matched_scenarios = self._identify_scenarios(risk_assessment, analysis, predictions, zone_config)
        observations = self._build_supporting_observations(risk_assessment, analysis, predictions, zone_config)

        candidates: list[Recommendation] = []
        now = datetime.now(timezone.utc)

        for scenario in matched_scenarios:
            templates = ACTION_CATALOG.get(scenario, [])
            for tpl in templates:
                # Check risk threshold gate
                if risk_assessment.risk_level.severity_order < tpl.min_risk_level.severity_order:
                    continue

                occ_pct = (risk_assessment.occupancy_ratio or 0.0) * 100.0
                reason = tpl.reason_template.format(
                    zone_name=zone_config.zone_name,
                    occupancy=occ_pct,
                )

                rec = Recommendation(
                    id=str(uuid.uuid4()),
                    action=tpl.action,
                    reason=reason,
                    affected_zone=zone_config.zone_id,
                    affected_zone_name=zone_config.zone_name,
                    priority=tpl.priority,
                    supporting_observations=observations,
                    suggested_team=tpl.suggested_team,
                    requires_human_approval=tpl.requires_human_approval,
                    timestamp=now,
                    event_id=event_id,
                    expiry_seconds=int(self._dedup_window.total_seconds()),
                )

                # Deduplicate
                dedup_key = f"{event_id}:{zone_config.zone_id}:{tpl.action}"
                last_sent = self._emitted_history.get(dedup_key)
                if last_sent is None or (now - last_sent) >= self._dedup_window:
                    self._emitted_history[dedup_key] = now
                    candidates.append(rec)

        # Sort recommendations: URGENT > HIGH > MEDIUM > LOW
        priority_order = {
            RecommendationPriority.URGENT: 4,
            RecommendationPriority.HIGH: 3,
            RecommendationPriority.MEDIUM: 2,
            RecommendationPriority.LOW: 1,
        }
        candidates.sort(key=lambda r: priority_order.get(r.priority, 0), reverse=True)

        # Clean stale emitted keys
        self._prune_history(now)

        # Update active cache for this event
        if candidates:
            current_active = self._active_recommendations[event_id]
            current_active.extend(candidates)
            # Keep at most 100 recent recommendations per event
            self._active_recommendations[event_id] = current_active[-100:]

        return candidates

    def _identify_scenarios(
        self,
        risk_assessment: ZoneRiskAssessment,
        analysis: dict[str, Any],
        predictions: list[PredictionInterpretation],
        zone_config: ZoneConfig,
    ) -> list[str]:
        """Map current and projected conditions to catalog scenarios."""
        scenarios: list[str] = []
        occ = risk_assessment.occupancy_ratio or 0.0

        if occ >= zone_config.threshold_moderate:
            scenarios.append("high_occupancy")

        trend = analysis.get("trend")
        if trend in ("rapid_increase", "increasing"):
            scenarios.append("rapid_growth")

        if zone_config.is_entry and (occ >= 0.60 or analysis.get("is_bottleneck")):
            scenarios.append("entrance_congestion")

        if analysis.get("is_bottleneck"):
            scenarios.append("bottleneck")

        if analysis.get("is_counterflow"):
            scenarios.append("counterflow")

        congestion_dur = analysis.get("congestion_duration_seconds")
        if congestion_dur and congestion_dur >= 300:
            scenarios.append("sustained_congestion")

        if any(p.is_emerging_hotspot for p in predictions):
            scenarios.append("emerging_hotspot")

        if any(f.factor == "adjacent_spillover" for f in risk_assessment.risk_factors):
            scenarios.append("adjacent_spillover")

        return scenarios

    def _build_supporting_observations(
        self,
        risk_assessment: ZoneRiskAssessment,
        analysis: dict[str, Any],
        predictions: list[PredictionInterpretation],
        zone_config: ZoneConfig,
    ) -> list[str]:
        """Compile grounded, empirical observations supporting recommendations."""
        obs: list[str] = []

        occ = risk_assessment.occupancy_ratio or 0.0
        obs.append(
            f"Current occupancy: {occ*100:.1f}% ({risk_assessment.people_count}/{zone_config.capacity} persons)"
        )

        if risk_assessment.density is not None:
            obs.append(f"Calibrated density: {risk_assessment.density:.2f} persons/m²")

        net_flow = analysis.get("net_flow", 0.0)
        inflow = analysis.get("inflow_rate", 0.0)
        outflow = analysis.get("outflow_rate", 0.0)
        obs.append(f"Flow velocity: inflow {inflow:.1f}/min, outflow {outflow:.1f}/min (net: {net_flow:+.1f}/min)")

        trend = analysis.get("trend", "stable")
        obs.append(f"Short-term growth trend: {trend.replace('_', ' ')}")

        congestion_dur = analysis.get("congestion_duration_seconds")
        if congestion_dur:
            obs.append(f"Uninterrupted congestion duration: {congestion_dur/60.0:.1f} minutes")

        for p in predictions:
            if p.predicted_occupancy is not None:
                obs.append(
                    f"Forecast (+{p.forecast_horizon_seconds//60}m): projected {p.predicted_occupancy*100:.0f}% occupancy (trend: {p.growth_trend})"
                )

        return obs

    def _prune_history(self, now: datetime) -> None:
        """Evict expired deduplication tracking keys."""
        cutoff = now - self._dedup_window
        stale_keys = [k for k, v in self._emitted_history.items() if v < cutoff]
        for k in stale_keys:
            del self._emitted_history[k]

    def get_active_recommendations(self, event_id: str) -> list[Recommendation]:
        """Return non-expired recommendations for the event."""
        return list(self._active_recommendations.get(event_id, []))

    def clear(self) -> None:
        """Reset recommendation history and cache."""
        self._emitted_history.clear()
        self._active_recommendations.clear()
