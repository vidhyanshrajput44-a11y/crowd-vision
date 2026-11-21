"""Advanced deterministic risk assessment engine.

Features configurable thresholds per zone, multi-factor evaluation,
hysteresis to eliminate noisy false positives, and detailed factor attribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from app.monitoring.logger import get_logger
from app.schemas.models import (
    CrowdDataInput,
    RiskFactor,
    RiskLevel,
    ZoneConfig,
    ZoneRiskAssessment,
)

logger = get_logger("intelligence.risk_assessment")


@dataclass
class ZoneHysteresisState:
    """Tracks state transitions to enforce hysteresis and prevent flapping."""
    confirmed_risk: RiskLevel = RiskLevel.NORMAL
    pending_risk: Optional[RiskLevel] = None
    pending_count: int = 0
    last_raw_risk: RiskLevel = RiskLevel.NORMAL


class RiskAssessmentEngine:
    """Deterministic, configurable multi-factor risk assessment engine."""

    # Consecutive cycles required to confirm a transition
    HYSTERESIS_ESCALATE_CYCLES: int = 3
    HYSTERESIS_DEESCALATE_CYCLES: int = 5

    def __init__(self) -> None:
        self._zone_states: dict[str, ZoneHysteresisState] = {}

    def _get_or_create_state(self, zone_id: str) -> ZoneHysteresisState:
        if zone_id not in self._zone_states:
            self._zone_states[zone_id] = ZoneHysteresisState()
        return self._zone_states[zone_id]

    async def assess(
        self,
        data: CrowdDataInput,
        zone_config: ZoneConfig,
        analysis: dict[str, Any],
        adjacent_assessments: Optional[list[ZoneRiskAssessment]] = None,
    ) -> ZoneRiskAssessment:
        """Evaluate all risk dimensions and produce a stabilized ZoneRiskAssessment."""
        factors: list[RiskFactor] = []

        # 1. Occupancy vs configured thresholds
        occ_factor = self._evaluate_occupancy(analysis.get("occupancy_ratio", 0.0), zone_config)
        factors.append(occ_factor)

        # 2. Density (if area_sqm and density thresholds configured)
        density_factor = self._evaluate_density(analysis.get("density"), zone_config)
        if density_factor:
            factors.append(density_factor)

        # 3. Flow dynamics (sustained positive net inflow)
        flow_factor = self._evaluate_flow(analysis)
        if flow_factor:
            factors.append(flow_factor)

        # 4. Crowd accumulation rate (growth trend / slope)
        accumulation_factor = self._evaluate_accumulation(analysis)
        if accumulation_factor:
            factors.append(accumulation_factor)

        # 5. Predicted occupancy (weighted by confidence)
        prediction_factor = self._evaluate_predictions(data, zone_config)
        if prediction_factor:
            factors.append(prediction_factor)

        # 6. Congestion duration
        duration_factor = self._evaluate_congestion_duration(analysis.get("congestion_duration_seconds"))
        if duration_factor:
            factors.append(duration_factor)

        # 7. Movement irregularities (bottleneck / counterflow)
        movement_factor = self._evaluate_movement(analysis)
        if movement_factor:
            factors.append(movement_factor)

        # 8. Adjacent zone spillover
        adjacent_factor = self._evaluate_adjacent_zones(adjacent_assessments, zone_config)
        if adjacent_factor:
            factors.append(adjacent_factor)

        # Determine raw risk from the maximum contributing factor
        raw_risk = max((f.severity for f in factors), default=RiskLevel.NORMAL)

        # Apply hysteresis to ensure noisy readings don't trigger immediate critical alerts
        hysteresis_state = self._get_or_create_state(data.zone_id)
        prev_confirmed = hysteresis_state.confirmed_risk
        confirmed_risk = self._apply_hysteresis(hysteresis_state, raw_risk)

        explanation = self._build_explanation(confirmed_risk, factors, raw_risk != confirmed_risk)

        assessment = ZoneRiskAssessment(
            zone_id=data.zone_id,
            zone_name=zone_config.zone_name,
            risk_level=confirmed_risk,
            previous_risk_level=prev_confirmed,
            risk_factors=factors,
            occupancy_ratio=analysis.get("occupancy_ratio"),
            density=analysis.get("density"),
            people_count=data.people_count,
            capacity=zone_config.capacity,
            inflow_rate=analysis.get("inflow_rate"),
            outflow_rate=analysis.get("outflow_rate"),
            net_flow=analysis.get("net_flow"),
            congestion_duration_seconds=analysis.get("congestion_duration_seconds"),
            timestamp=data.timestamp,
            explanation=explanation,
        )

        return assessment

    def _evaluate_occupancy(self, occupancy: float, zone_config: ZoneConfig) -> RiskFactor:
        """Evaluate occupancy ratio against zone-specific calibrated thresholds."""
        if occupancy >= zone_config.threshold_critical:
            return RiskFactor(
                factor="occupancy_ratio",
                description=f"Occupancy ({occupancy*100:.1f}%) exceeds CRITICAL threshold ({zone_config.threshold_critical*100:.1f}%)",
                severity=RiskLevel.CRITICAL,
                value=occupancy,
                threshold=zone_config.threshold_critical,
            )
        elif occupancy >= zone_config.threshold_high:
            return RiskFactor(
                factor="occupancy_ratio",
                description=f"Occupancy ({occupancy*100:.1f}%) exceeds HIGH threshold ({zone_config.threshold_high*100:.1f}%)",
                severity=RiskLevel.HIGH,
                value=occupancy,
                threshold=zone_config.threshold_high,
            )
        elif occupancy >= zone_config.threshold_moderate:
            return RiskFactor(
                factor="occupancy_ratio",
                description=f"Occupancy ({occupancy*100:.1f}%) exceeds MODERATE threshold ({zone_config.threshold_moderate*100:.1f}%)",
                severity=RiskLevel.MODERATE,
                value=occupancy,
                threshold=zone_config.threshold_moderate,
            )
        elif occupancy >= zone_config.threshold_low:
            return RiskFactor(
                factor="occupancy_ratio",
                description=f"Occupancy ({occupancy*100:.1f}%) exceeds LOW threshold ({zone_config.threshold_low*100:.1f}%)",
                severity=RiskLevel.LOW,
                value=occupancy,
                threshold=zone_config.threshold_low,
            )
        else:
            return RiskFactor(
                factor="occupancy_ratio",
                description=f"Occupancy is nominal at {occupancy*100:.1f}%",
                severity=RiskLevel.NORMAL,
                value=occupancy,
                threshold=zone_config.threshold_low,
            )

    def _evaluate_density(self, density: Optional[float], zone_config: ZoneConfig) -> Optional[RiskFactor]:
        """Evaluate physical density when area and density thresholds are calibrated."""
        if density is None:
            return None

        if zone_config.density_critical and density >= zone_config.density_critical:
            return RiskFactor(
                factor="density",
                description=f"Physical density ({density:.2f} ppl/m²) exceeds CRITICAL threshold ({zone_config.density_critical:.1f})",
                severity=RiskLevel.CRITICAL,
                value=density,
                threshold=zone_config.density_critical,
            )
        elif zone_config.density_high and density >= zone_config.density_high:
            return RiskFactor(
                factor="density",
                description=f"Physical density ({density:.2f} ppl/m²) exceeds HIGH threshold ({zone_config.density_high:.1f})",
                severity=RiskLevel.HIGH,
                value=density,
                threshold=zone_config.density_high,
            )
        elif zone_config.density_moderate and density >= zone_config.density_moderate:
            return RiskFactor(
                factor="density",
                description=f"Physical density ({density:.2f} ppl/m²) exceeds MODERATE threshold ({zone_config.density_moderate:.1f})",
                severity=RiskLevel.MODERATE,
                value=density,
                threshold=zone_config.density_moderate,
            )
        return None

    def _evaluate_flow(self, analysis: dict[str, Any]) -> Optional[RiskFactor]:
        """Evaluate net crowd flow dynamics."""
        net_flow = analysis.get("net_flow", 0.0)
        occ = analysis.get("occupancy_ratio", 0.0)

        # High net inflow into an already saturated zone is dangerous
        if net_flow >= 20.0 and occ >= 0.70:
            return RiskFactor(
                factor="net_flow",
                description=f"Intense positive inflow (+{net_flow:.1f} ppl/min) into {occ*100:.0f}% occupied zone",
                severity=RiskLevel.HIGH,
                value=net_flow,
            )
        elif net_flow >= 10.0 and occ >= 0.60:
            return RiskFactor(
                factor="net_flow",
                description=f"Positive crowd accumulation flow (+{net_flow:.1f} ppl/min)",
                severity=RiskLevel.MODERATE,
                value=net_flow,
            )
        return None

    def _evaluate_accumulation(self, analysis: dict[str, Any]) -> Optional[RiskFactor]:
        """Evaluate crowd growth rate and statistical accumulation anomaly."""
        trend = analysis.get("trend")
        is_anomaly = analysis.get("is_accumulation_anomaly", False)

        if is_anomaly and trend in ("rapid_increase", "increasing"):
            return RiskFactor(
                factor="accumulation_rate",
                description="Statistically abnormal accumulation surge detected (+2σ above rolling baseline)",
                severity=RiskLevel.HIGH,
            )
        elif trend == "rapid_increase":
            return RiskFactor(
                factor="accumulation_rate",
                description="Rapid sustained crowd growth detected across consecutive updates",
                severity=RiskLevel.MODERATE,
            )
        return None

    def _evaluate_predictions(self, data: CrowdDataInput, zone_config: ZoneConfig) -> Optional[RiskFactor]:
        """Evaluate predicted occupancy, discounting unconfident forecasts."""
        predicted_occ = data.predicted_occupancy
        if predicted_occ is None:
            return None

        confidence = data.forecast_confidence if data.forecast_confidence is not None else 0.5
        horizon_m = (data.forecast_horizon_seconds or 300) // 60

        # Only evaluate predictions with reasonable confidence
        if confidence >= 0.60:
            if predicted_occ >= zone_config.threshold_critical:
                return RiskFactor(
                    factor="predicted_occupancy",
                    description=f"Forecast predicts CRITICAL occupancy ({predicted_occ*100:.0f}%) within {horizon_m}m (confidence: {confidence*100:.0f}%)",
                    severity=RiskLevel.HIGH if confidence < 0.85 else RiskLevel.CRITICAL,
                    value=predicted_occ,
                    threshold=zone_config.threshold_critical,
                )
            elif predicted_occ >= zone_config.threshold_high:
                return RiskFactor(
                    factor="predicted_occupancy",
                    description=f"Forecast predicts HIGH occupancy ({predicted_occ*100:.0f}%) within {horizon_m}m (confidence: {confidence*100:.0f}%)",
                    severity=RiskLevel.MODERATE if confidence < 0.85 else RiskLevel.HIGH,
                    value=predicted_occ,
                    threshold=zone_config.threshold_high,
                )
        return None

    def _evaluate_congestion_duration(self, duration_seconds: Optional[float]) -> Optional[RiskFactor]:
        """Prolonged congestion increases physical hazard and crowd fatigue."""
        if duration_seconds is None or duration_seconds < 120:
            return None

        mins = duration_seconds / 60.0
        if mins >= 20.0:
            return RiskFactor(
                factor="congestion_duration",
                description=f"Critical sustained congestion for {mins:.1f} minutes",
                severity=RiskLevel.CRITICAL,
                value=duration_seconds,
            )
        elif mins >= 10.0:
            return RiskFactor(
                factor="congestion_duration",
                description=f"Extended sustained congestion for {mins:.1f} minutes",
                severity=RiskLevel.HIGH,
                value=duration_seconds,
            )
        elif mins >= 5.0:
            return RiskFactor(
                factor="congestion_duration",
                description=f"Congestion persisting for {mins:.1f} minutes",
                severity=RiskLevel.MODERATE,
                value=duration_seconds,
            )
        return None

    def _evaluate_movement(self, analysis: dict[str, Any]) -> Optional[RiskFactor]:
        """Evaluate bottleneck and counterflow detection."""
        if analysis.get("is_bottleneck"):
            return RiskFactor(
                factor="bottleneck",
                description=f"Bottleneck condition: {analysis.get('bottleneck_reason')}",
                severity=RiskLevel.HIGH if analysis.get("occupancy_ratio", 0) >= 0.80 else RiskLevel.MODERATE,
            )
        if analysis.get("is_counterflow"):
            return RiskFactor(
                factor="counterflow",
                description=f"Counterflow hazard: {analysis.get('counterflow_reason')}",
                severity=RiskLevel.HIGH,
            )
        return None

    def _evaluate_adjacent_zones(
        self,
        adjacent_assessments: Optional[list[ZoneRiskAssessment]],
        zone_config: ZoneConfig,
    ) -> Optional[RiskFactor]:
        """Assess risk spillover from neighbouring zones."""
        if not adjacent_assessments or not zone_config.adjacent_zones:
            return None

        adj_map = {a.zone_id: a for a in adjacent_assessments}
        high_critical_count = sum(
            1 for z_id in zone_config.adjacent_zones
            if z_id in adj_map and adj_map[z_id].risk_level >= RiskLevel.HIGH
        )

        if high_critical_count >= 2:
            return RiskFactor(
                factor="adjacent_spillover",
                description=f"{high_critical_count} adjacent zones are at HIGH/CRITICAL risk, threatening overflow",
                severity=RiskLevel.HIGH,
            )
        elif high_critical_count == 1:
            return RiskFactor(
                factor="adjacent_spillover",
                description="Adjacent zone is experiencing high congestion with potential displacement",
                severity=RiskLevel.MODERATE,
            )
        return None

    def _apply_hysteresis(self, state: ZoneHysteresisState, raw_risk: RiskLevel) -> RiskLevel:
        """Prevent alert flapping using asymmetric temporal validation."""
        state.last_raw_risk = raw_risk

        if raw_risk == state.confirmed_risk:
            # Condition is stable at current confirmed level
            state.pending_risk = None
            state.pending_count = 0
            return state.confirmed_risk

        # Transition candidate
        if state.pending_risk != raw_risk:
            state.pending_risk = raw_risk
            state.pending_count = 1
        else:
            state.pending_count += 1

        is_escalation = raw_risk.severity_order > state.confirmed_risk.severity_order
        required_cycles = self.HYSTERESIS_ESCALATE_CYCLES if is_escalation else self.HYSTERESIS_DEESCALATE_CYCLES

        # Check if candidate risk has persisted for required cycles
        if state.pending_count >= required_cycles:
            state.confirmed_risk = raw_risk
            state.pending_risk = None
            state.pending_count = 0

        return state.confirmed_risk

    def _build_explanation(self, confirmed_risk: RiskLevel, factors: list[RiskFactor], is_stabilizing: bool) -> str:
        """Compose a concise explanation of risk classification and drivers."""
        significant_factors = [f for f in factors if f.severity >= RiskLevel.MODERATE]
        if not significant_factors:
            significant_factors = [f for f in factors if f.severity > RiskLevel.NORMAL]

        if not significant_factors:
            return "Crowd indicators are nominal. Normal operating parameters across all metrics."

        factor_bullets = "; ".join(f"{f.description}" for f in significant_factors[:3])
        explanation = f"Risk classified as {confirmed_risk.value} based on: {factor_bullets}."
        if is_stabilizing:
            explanation += " (Temporal hysteresis currently dampening transient fluctuations)."
        return explanation

    def get_current_risk(self, zone_id: str) -> Optional[RiskLevel]:
        """Return current confirmed risk level for a zone."""
        state = self._zone_states.get(zone_id)
        return state.confirmed_risk if state else None

    def reset(self) -> None:
        """Clear all internal hysteresis states."""
        self._zone_states.clear()
