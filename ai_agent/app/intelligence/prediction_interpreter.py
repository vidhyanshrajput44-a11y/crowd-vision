"""Prediction interpretation engine.

Interprets, compares, ranks, and explains forecasts supplied by the main
computer vision and predictive modeling engine without running duplicate models.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from app.monitoring.logger import get_logger
from app.schemas.models import (
    CrowdDataInput,
    ForecastPoint,
    PredictionInterpretation,
    RiskLevel,
    ZoneConfig,
)

logger = get_logger("intelligence.prediction_interpreter")


@dataclass
class HistoricalForecast:
    """Historical forecast point recorded for consistency tracking."""
    timestamp: datetime
    horizon_seconds: int
    predicted_occupancy: Optional[float]
    predicted_density: Optional[float]
    confidence: Optional[float]


class PredictionInterpreter:
    """Interprets and explains external crowd predictions across multiple horizons."""

    def __init__(self) -> None:
        # zone_id -> bounded deque of past forecasts
        self._forecast_history: dict[str, deque[HistoricalForecast]] = {}

    def _get_history(self, zone_id: str) -> deque[HistoricalForecast]:
        if zone_id not in self._forecast_history:
            self._forecast_history[zone_id] = deque(maxlen=40)
        return self._forecast_history[zone_id]

    async def interpret(
        self,
        data: CrowdDataInput,
        zone_config: ZoneConfig,
        current_risk: RiskLevel,
    ) -> list[PredictionInterpretation]:
        """Interpret single or multi-horizon predictions for a zone."""
        interpretations: list[PredictionInterpretation] = []
        history = self._get_history(data.zone_id)

        # 1. Process primary forecast if present
        if data.predicted_occupancy is not None or data.predicted_density is not None:
            horizon = data.forecast_horizon_seconds or 300
            interp = self._interpret_single_point(
                data=data,
                zone_config=zone_config,
                current_risk=current_risk,
                horizon_seconds=horizon,
                predicted_occ=data.predicted_occupancy,
                predicted_density=data.predicted_density,
                confidence=data.forecast_confidence,
            )
            interpretations.append(interp)
            history.append(
                HistoricalForecast(
                    timestamp=data.timestamp,
                    horizon_seconds=horizon,
                    predicted_occupancy=data.predicted_occupancy,
                    predicted_density=data.predicted_density,
                    confidence=data.forecast_confidence,
                )
            )

        # 2. Process multi-horizon forecasts if provided
        if data.multi_horizon_forecasts:
            for fp in data.multi_horizon_forecasts:
                pred_occ = fp.predicted_occupancy
                if pred_occ is None and fp.predicted_count is not None and zone_config.capacity > 0:
                    pred_occ = fp.predicted_count / zone_config.capacity

                interp = self._interpret_single_point(
                    data=data,
                    zone_config=zone_config,
                    current_risk=current_risk,
                    horizon_seconds=fp.horizon_seconds,
                    predicted_occ=pred_occ,
                    predicted_density=fp.predicted_density,
                    confidence=fp.confidence,
                )
                interpretations.append(interp)

        return interpretations

    def _interpret_single_point(
        self,
        data: CrowdDataInput,
        zone_config: ZoneConfig,
        current_risk: RiskLevel,
        horizon_seconds: int,
        predicted_occ: Optional[float],
        predicted_density: Optional[float],
        confidence: Optional[float],
    ) -> PredictionInterpretation:
        """Interpret a single forecast horizon against zone configuration."""
        horizon_mins = max(1, horizon_seconds // 60)
        current_occ = data.current_occupancy
        if current_occ is None and zone_config.capacity > 0:
            current_occ = data.people_count / zone_config.capacity

        # Determine predicted risk level based on configured zone thresholds
        predicted_risk = RiskLevel.NORMAL
        if predicted_occ is not None:
            if predicted_occ >= zone_config.threshold_critical:
                predicted_risk = RiskLevel.CRITICAL
            elif predicted_occ >= zone_config.threshold_high:
                predicted_risk = RiskLevel.HIGH
            elif predicted_occ >= zone_config.threshold_moderate:
                predicted_risk = RiskLevel.MODERATE
            elif predicted_occ >= zone_config.threshold_low:
                predicted_risk = RiskLevel.LOW

        # Growth trend characterization
        growth_trend = self._characterize_growth_trend(current_occ, predicted_occ, horizon_seconds)

        # Emerging hotspot: current condition is safe/moderate, but forecast anticipates high/critical
        is_emerging_hotspot = (
            current_risk <= RiskLevel.MODERATE
            and predicted_risk >= RiskLevel.HIGH
            and (confidence is None or confidence >= 0.50)
        )

        # Low confidence warning
        is_low_confidence = (confidence is not None and confidence < 0.50)

        # Build analytical explanation
        explanation = self._generate_explanation(
            zone_name=zone_config.zone_name,
            current_occ=current_occ,
            predicted_occ=predicted_occ,
            growth_trend=growth_trend,
            horizon_mins=horizon_mins,
            confidence=confidence,
            is_emerging_hotspot=is_emerging_hotspot,
            is_low_confidence=is_low_confidence,
        )

        return PredictionInterpretation(
            zone_id=data.zone_id,
            zone_name=zone_config.zone_name,
            current_risk=current_risk,
            predicted_risk=predicted_risk,
            forecast_horizon_seconds=horizon_seconds,
            predicted_occupancy=round(predicted_occ, 4) if predicted_occ is not None else None,
            predicted_density=round(predicted_density, 4) if predicted_density is not None else None,
            growth_trend=growth_trend,
            confidence=round(confidence, 3) if confidence is not None else None,
            is_emerging_hotspot=is_emerging_hotspot,
            is_low_confidence=is_low_confidence,
            explanation=explanation,
        )

    def _characterize_growth_trend(
        self,
        current_occ: Optional[float],
        predicted_occ: Optional[float],
        horizon_seconds: int,
    ) -> str:
        """Classify predicted trajectory."""
        if current_occ is None or predicted_occ is None:
            return "stable"

        delta = predicted_occ - current_occ
        delta_per_5min = (delta / (horizon_seconds / 300.0)) if horizon_seconds > 0 else delta

        if delta_per_5min >= 0.15:
            return "rapid_increase"
        elif delta_per_5min >= 0.05:
            return "increasing"
        elif delta_per_5min <= -0.15:
            return "rapid_decrease"
        elif delta_per_5min <= -0.05:
            return "decreasing"
        else:
            return "stable"

    def _generate_explanation(
        self,
        zone_name: str,
        current_occ: Optional[float],
        predicted_occ: Optional[float],
        growth_trend: str,
        horizon_mins: int,
        confidence: Optional[float],
        is_emerging_hotspot: bool,
        is_low_confidence: bool,
    ) -> str:
        """Compose human-readable explanation emphasizing probabilistic nature."""
        parts = []

        if predicted_occ is not None and current_occ is not None:
            parts.append(
                f"{zone_name} is projected to shift from {current_occ*100:.0f}% to {predicted_occ*100:.0f}% capacity within {horizon_mins}m ({growth_trend.replace('_', ' ')})"
            )
        elif predicted_occ is not None:
            parts.append(
                f"{zone_name} is projected to reach {predicted_occ*100:.0f}% occupancy in {horizon_mins}m"
            )

        if is_emerging_hotspot:
            parts.append("ALERT: Identified as an emerging hotspot requiring proactive staging")

        if confidence is not None:
            parts.append(f"Forecast model confidence: {confidence*100:.0f}%")

        if is_low_confidence:
            parts.append("CAUTION: Low forecast confidence; operational decisions should await confirmatory trends")

        parts.append("(Note: Model forecasts represent probabilistic estimates, not certainty)")
        return ". ".join(parts) + "."

    def detect_conflicting_forecasts(self, zone_id: str) -> bool:
        """Determine whether successive forecasts for the same zone exhibit erratic contradictions."""
        history = self._get_history(zone_id)
        if len(history) < 4:
            return False

        recent = list(history)[-4:]
        trends = []
        for i in range(1, len(recent)):
            curr = recent[i].predicted_occupancy
            prev = recent[i - 1].predicted_occupancy
            if curr is not None and prev is not None:
                trends.append(curr - prev)

        if len(trends) >= 3:
            # Alternating signs indicate oscillation/instability in upstream model
            has_positive = any(t > 0.05 for t in trends)
            has_negative = any(t < -0.05 for t in trends)
            return has_positive and has_negative

        return False

    def rank_zones_by_predicted_risk(
        self,
        interpretations: list[PredictionInterpretation],
    ) -> list[PredictionInterpretation]:
        """Rank zones primarily by predicted risk severity, secondarily by predicted occupancy."""
        return sorted(
            interpretations,
            key=lambda x: (
                x.predicted_risk.severity_order,
                x.predicted_occupancy or 0.0,
                x.confidence or 0.0,
            ),
            reverse=True,
        )

    def get_emerging_hotspots(
        self,
        interpretations: list[PredictionInterpretation],
    ) -> list[PredictionInterpretation]:
        """Filter predictions to emerging hotspots."""
        return [i for i in interpretations if i.is_emerging_hotspot]
