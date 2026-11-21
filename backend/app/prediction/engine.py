"""Multi-horizon short-term crowd occupancy forecasting engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from app.analytics.crowd_analytics import ZoneAnalyticsSnapshot
from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger("crowdvision.prediction.engine")

# ---------------------------------------------------------------------------
# Default zone thresholds (used when no ZoneDefinition is available)
# ---------------------------------------------------------------------------
_DEFAULT_THRESHOLD_LOW = 0.45
_DEFAULT_THRESHOLD_MODERATE = 0.65
_DEFAULT_THRESHOLD_HIGH = 0.82
_DEFAULT_THRESHOLD_CRITICAL = 0.95

# Risk level ordering for comparisons
_RISK_LEVELS = ("NORMAL", "LOW", "MODERATE", "HIGH", "CRITICAL")


@dataclass
class PredictionResult:
    """Forecast for a single zone at a single horizon."""

    zone_id: str
    zone_name: str
    video_timestamp_sec: float
    horizon_seconds: int
    current_occupancy: float
    current_density: float
    predicted_occupancy: float
    predicted_density: float
    estimated_trend: str  # stable / increasing / decreasing / rapid_increase / rapid_decrease
    risk_category: str  # NORMAL / LOW / MODERATE / HIGH / CRITICAL
    confidence: float  # 0-1
    is_experimental: bool
    model_name: str

    @property
    def predicted_change_pct(self) -> float:
        if self.current_occupancy > 0.001:
            return float(round(((self.predicted_occupancy - self.current_occupancy) / self.current_occupancy) * 100.0, 2))
        return 0.0


class PredictionEngine:
    """Strictly-causal, linear-trend extrapolation forecaster with EMA smoothing."""

    MODEL_NAME = "linear_trend_ema_v1"

    def __init__(
        self,
        horizons_seconds: Optional[list[int] | tuple[int, ...]] = None,
        min_history: Optional[int] = None,
        event_id: Optional[str] = None,
        horizons: Optional[list[int] | tuple[int, ...]] = None,
        **kwargs: Any,
    ) -> None:
        settings = get_settings()
        hz = horizons if horizons is not None else horizons_seconds
        self.horizons_seconds: list[int] = (
            list(hz) if hz is not None else settings.forecast_horizons_list
        )
        self.min_history: int = (
            min_history if min_history is not None else settings.min_history_for_prediction
        )
        self._horizons = self.horizons_seconds
        self._min_history = self.min_history
        self.event_id = event_id
        self._history: dict[str, list[ZoneAnalyticsSnapshot]] = {}
        self.model_name = "linear_trend_ema_v1"
        logger.info(
            "PredictionEngine initialised",
            horizons=self.horizons_seconds,
            min_history=self.min_history,
        )

    def update_and_predict(
        self,
        snapshots: list[ZoneAnalyticsSnapshot],
        video_timestamp_sec: float = 0.0,
        zone_defs: Optional[list[ZoneDefinition]] = None,
    ) -> list[PredictionResult]:
        for s in snapshots:
            hist = self._history.setdefault(s.zone_id, [])
            hist.append(s)
            if len(hist) > 50:
                hist.pop(0)
        return self.predict(zone_snapshots=snapshots, history=self._history, zone_defs=zone_defs)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(
        self,
        zone_snapshots: list[ZoneAnalyticsSnapshot],
        history: dict[str, list[ZoneAnalyticsSnapshot]],
        zone_defs: Optional[list[ZoneDefinition]] = None,
    ) -> list[PredictionResult]:
        """Generate multi-horizon predictions for every zone in *zone_snapshots*."""
        zone_map: dict[str, ZoneDefinition] = {z.zone_id: z for z in zone_defs} if zone_defs else {}
        results: list[PredictionResult] = []
        for snap in zone_snapshots:
            current_ts = snap.video_timestamp_sec
            # Build causal occupancy time-series
            past: list[ZoneAnalyticsSnapshot] = [
                s
                for s in history.get(snap.zone_id, [])
                if s.video_timestamp_sec <= current_ts
            ]
            # Append the current snapshot if not already the last entry
            if not past or past[-1].video_timestamp_sec < current_ts:
                past.append(snap)

            is_experimental = len(past) < self._min_history

            # EMA-smooth the occupancy series
            smoothed_occ = self._ema_smooth([s.occupancy_ratio for s in past])
            timestamps = [s.video_timestamp_sec for s in past]

            # Fit linear slope on the smoothed series
            slope = self._linear_slope(timestamps, smoothed_occ)

            for horizon in self._horizons:
                pred_occ = smoothed_occ[-1] + slope * horizon
                pred_occ = max(0.0, min(1.5, pred_occ))

                # Density scales proportionally to occupancy change
                occ_ratio = (
                    pred_occ / snap.occupancy_ratio
                    if snap.occupancy_ratio > 1e-9
                    else 1.0
                )
                pred_density = snap.density_value * occ_ratio

                trend = self._classify_trend(slope)
                risk = self._classify_risk(pred_occ)
                confidence = self._compute_confidence(
                    n_points=len(past),
                    horizon=horizon,
                )

                results.append(
                    PredictionResult(
                        zone_id=snap.zone_id,
                        zone_name=snap.zone_name,
                        video_timestamp_sec=current_ts,
                        horizon_seconds=horizon,
                        current_occupancy=snap.occupancy_ratio,
                        current_density=snap.density_value,
                        predicted_occupancy=round(pred_occ, 4),
                        predicted_density=round(pred_density, 4),
                        estimated_trend=trend,
                        risk_category=risk,
                        confidence=round(confidence, 4),
                        is_experimental=is_experimental,
                        model_name=self.MODEL_NAME,
                    )
                )
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ema_smooth(values: list[float], alpha: float = 0.3) -> list[float]:
        """Exponential moving average smoothing (causal)."""
        if not values:
            return []
        smoothed = [values[0]]
        for v in values[1:]:
            smoothed.append(alpha * v + (1.0 - alpha) * smoothed[-1])
        return smoothed

    @staticmethod
    def _linear_slope(timestamps: list[float], values: list[float]) -> float:
        """Ordinary least-squares slope on (timestamp, value) pairs.

        Returns slope in value-change per second.  Falls back to 0 when
        there are fewer than 2 data points or the time span is zero.
        """
        n = len(timestamps)
        if n < 2:
            return 0.0
        t0 = timestamps[0]
        ts = [t - t0 for t in timestamps]
        span = ts[-1] - ts[0]
        if span <= 0:
            return 0.0
        mean_t = sum(ts) / n
        mean_v = sum(values) / n
        num = sum((t - mean_t) * (v - mean_v) for t, v in zip(ts, values))
        den = sum((t - mean_t) ** 2 for t in ts)
        if den < 1e-15:
            return 0.0
        return num / den

    @staticmethod
    def _classify_trend(slope: float) -> str:
        abs_slope = abs(slope)
        if abs_slope > 0.015:
            return "rapid_increase" if slope > 0 else "rapid_decrease"
        if abs_slope > 0.003:
            return "increasing" if slope > 0 else "decreasing"
        return "stable"

    @staticmethod
    def _classify_risk(predicted_occupancy: float) -> str:
        if predicted_occupancy >= _DEFAULT_THRESHOLD_CRITICAL:
            return "CRITICAL"
        if predicted_occupancy >= _DEFAULT_THRESHOLD_HIGH:
            return "HIGH"
        if predicted_occupancy >= _DEFAULT_THRESHOLD_MODERATE:
            return "MODERATE"
        if predicted_occupancy >= _DEFAULT_THRESHOLD_LOW:
            return "LOW"
        return "NORMAL"

    @staticmethod
    def _compute_confidence(n_points: int, horizon: int) -> float:
        """Confidence degrades with longer horizons and less history."""
        # Base confidence from data availability (saturates around 10 points)
        data_conf = min(1.0, n_points / 10.0)
        # Horizon decay: shorter → higher confidence
        horizon_factor = 1.0 / (1.0 + horizon / 120.0)
        confidence = data_conf * horizon_factor
        return max(0.0, min(1.0, confidence))

    @staticmethod
    def compute_error_metrics(errors: list[float]) -> dict[str, Optional[float] | int]:
        if not errors:
            return {"mae": None, "rmse": None, "sample_count": 0}
        arr = np.array(errors, dtype=np.float64)
        mae = float(np.mean(np.abs(arr)))
        rmse = float(np.sqrt(np.mean(arr ** 2)))
        return {
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "sample_count": len(errors),
        }
