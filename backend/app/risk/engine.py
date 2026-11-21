"""Deterministic risk assessment engine — no LLM dependency."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.analytics.crowd_analytics import ZoneAnalyticsSnapshot
from app.analytics.zone_mapper import ZoneDefinition
from app.prediction.engine import PredictionResult
from app.core.logging import get_logger

logger = get_logger("crowdvision.risk.engine")

# Ordered risk levels (index = severity rank)
_RISK_LEVELS = ["NORMAL", "LOW", "MODERATE", "HIGH", "CRITICAL"]
_RISK_INDEX = {level: idx for idx, level in enumerate(_RISK_LEVELS)}

_MONITORING = {
    "NORMAL": "ROUTINE",
    "LOW": "ROUTINE",
    "MODERATE": "ELEVATED",
    "HIGH": "HIGH",
    "CRITICAL": "IMMEDIATE",
}


@dataclass
class RiskResult:
    """Assessed risk for a single zone."""

    zone_id: str
    zone_name: str
    risk_level: str  # NORMAL / LOW / MODERATE / HIGH / CRITICAL
    reason: str
    supporting_measurements: dict
    monitoring_priority: str  # ROUTINE / ELEVATED / HIGH / IMMEDIATE
    requires_human_review: bool
    contributing_factors: list[str]
    video_timestamp_sec: float = 0.0


class RiskEngine:
    """Purely deterministic, multi-indicator risk assessor with hysteresis."""

    def __init__(
        self,
        sustained_frames_threshold: int = 3,
        event_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        self.sustained_frames_threshold = sustained_frames_threshold
        self.event_id = event_id
        # Per-zone previous risk level for hysteresis
        self._prev_risk: dict[str, str] = {}
        # Per-zone count of consecutive frames above MODERATE (sustained congestion)
        self._sustained_congestion_count: dict[str, int] = {}
        logger.info("RiskEngine initialised", sustained_threshold=sustained_frames_threshold)

    def evaluate_frame_risk(
        self,
        snapshots: list[ZoneAnalyticsSnapshot],
        predictions: list[Any],
        video_timestamp_sec: float = 0.0,
        zone_defs: Optional[list[ZoneDefinition]] = None,
    ) -> list[RiskResult]:
        defs = zone_defs or [
            ZoneDefinition(
                zone_id=s.zone_id,
                name=s.zone_name,
                capacity=int(round(s.people_count / max(0.01, s.capacity_utilization_pct / 100.0))) if s.capacity_utilization_pct > 0 else 100,
            )
            for s in snapshots
        ]
        return self.assess(zone_snapshots=snapshots, predictions=predictions, zone_defs=defs)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assess(
        self,
        zone_snapshots: list[ZoneAnalyticsSnapshot],
        predictions: list[PredictionResult],
        zone_defs: list[ZoneDefinition],
    ) -> list[RiskResult]:
        """Evaluate risk for every zone present in *zone_snapshots*."""

        zone_def_map: dict[str, ZoneDefinition] = {z.zone_id: z for z in zone_defs}
        pred_map: dict[str, list[PredictionResult]] = {}
        for p in predictions:
            pred_map.setdefault(p.zone_id, []).append(p)

        results: list[RiskResult] = []
        for snap in zone_snapshots:
            zdef = zone_def_map.get(snap.zone_id)
            if zdef is None:
                continue
            zone_preds = pred_map.get(snap.zone_id, [])
            result = self._assess_zone(snap, zdef, zone_preds)
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Per-zone assessment
    # ------------------------------------------------------------------

    def _assess_zone(
        self,
        snap: ZoneAnalyticsSnapshot,
        zdef: ZoneDefinition,
        predictions: list[PredictionResult],
    ) -> RiskResult:
        factors: list[str] = []
        indicator_levels: list[str] = []
        measurements: dict = {
            "occupancy_ratio": snap.occupancy_ratio,
            "people_count": snap.people_count,
            "capacity": snap.capacity,
            "density_value": snap.density_value,
            "inflow_rate": snap.inflow_rate,
            "outflow_rate": snap.outflow_rate,
            "net_flow": snap.net_flow,
        }

        # 1. Occupancy vs configurable thresholds
        occ_level = self._occupancy_risk(snap.occupancy_ratio, zdef)
        if _RISK_INDEX[occ_level] > _RISK_INDEX["NORMAL"]:
            factors.append(
                f"Occupancy at {snap.occupancy_ratio:.0%} "
                f"(threshold: {occ_level})"
            )
        indicator_levels.append(occ_level)

        # 2. Rapid accumulation rate
        if snap.net_flow > 10.0 and snap.occupancy_ratio > 0.4:
            factors.append(
                f"Rapid accumulation: net_flow={snap.net_flow:.1f} people/min"
            )
            indicator_levels.append("HIGH")
        else:
            indicator_levels.append("NORMAL")

        # 3. High inflow with restricted outflow
        if (
            snap.inflow_rate > 2.0 * max(snap.outflow_rate, 0.001)
            and snap.occupancy_ratio > 0.5
        ):
            factors.append(
                f"Restricted outflow: inflow={snap.inflow_rate:.1f}, "
                f"outflow={snap.outflow_rate:.1f}"
            )
            indicator_levels.append("MODERATE")
        else:
            indicator_levels.append("NORMAL")

        # 4. Bottleneck detected
        if snap.is_bottleneck:
            factors.append("Bottleneck detected")
            indicator_levels.append("HIGH")
        else:
            indicator_levels.append("NORMAL")

        # 5. Counterflow detected
        if snap.is_counterflow:
            factors.append("Counterflow detected")
            indicator_levels.append("MODERATE")
        else:
            indicator_levels.append("NORMAL")

        # 6. Predicted occupancy exceeding thresholds
        worst_pred_level = "NORMAL"
        for pred in predictions:
            pred_level = self._occupancy_risk(pred.predicted_occupancy, zdef)
            if _RISK_INDEX[pred_level] > _RISK_INDEX[worst_pred_level]:
                worst_pred_level = pred_level
                measurements["predicted_occupancy"] = pred.predicted_occupancy
                measurements["prediction_horizon_sec"] = pred.horizon_seconds
        if _RISK_INDEX[worst_pred_level] > _RISK_INDEX["NORMAL"]:
            factors.append(
                f"Predicted occupancy reaches {worst_pred_level} level"
            )
        indicator_levels.append(worst_pred_level)

        # 7. Sustained congestion
        occ_above_moderate = snap.occupancy_ratio >= zdef.threshold_moderate
        prev_count = self._sustained_congestion_count.get(snap.zone_id, 0)
        if occ_above_moderate:
            prev_count += 1
        else:
            prev_count = 0
        self._sustained_congestion_count[snap.zone_id] = prev_count

        if prev_count >= 5:
            factors.append(
                f"Sustained congestion for {prev_count} consecutive frames"
            )
            indicator_levels.append("HIGH")
        elif prev_count >= 3:
            factors.append(
                f"Building congestion ({prev_count} consecutive frames above moderate)"
            )
            indicator_levels.append("MODERATE")
        else:
            indicator_levels.append("NORMAL")

        # --- Aggregate: max of all indicator levels ---
        raw_level = _RISK_LEVELS[
            max(_RISK_INDEX[lvl] for lvl in indicator_levels)
        ]

        # Hysteresis: don't downgrade more than 1 level per evaluation
        prev_level = self._prev_risk.get(snap.zone_id, "NORMAL")
        final_level = self._apply_hysteresis(prev_level, raw_level)
        self._prev_risk[snap.zone_id] = final_level

        reason = "; ".join(factors) if factors else "All indicators normal"

        return RiskResult(
            zone_id=snap.zone_id,
            zone_name=snap.zone_name,
            risk_level=final_level,
            reason=reason,
            supporting_measurements=measurements,
            monitoring_priority=_MONITORING[final_level],
            requires_human_review=final_level in ("HIGH", "CRITICAL"),
            contributing_factors=factors,
            video_timestamp_sec=getattr(snap, "video_timestamp_sec", 0.0),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _occupancy_risk(occ: float, zdef: ZoneDefinition) -> str:
        if occ >= zdef.threshold_critical:
            return "CRITICAL"
        if occ >= zdef.threshold_high:
            return "HIGH"
        if occ >= zdef.threshold_moderate:
            return "MODERATE"
        if occ >= zdef.threshold_low:
            return "LOW"
        return "NORMAL"

    @staticmethod
    def _apply_hysteresis(prev: str, raw: str) -> str:
        """Don't allow risk to drop more than 1 level per evaluation cycle."""
        prev_idx = _RISK_INDEX.get(prev, 0)
        raw_idx = _RISK_INDEX.get(raw, 0)
        if raw_idx < prev_idx:
            # Allow at most 1-level drop
            final_idx = max(raw_idx, prev_idx - 1)
            return _RISK_LEVELS[final_idx]
        return raw
