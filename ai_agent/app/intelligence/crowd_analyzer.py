"""Deterministic crowd intelligence analysis engine.

Processes structured measurements to detect trends, anomalies, bottlenecks,
counterflow, and congestion duration without invoking LLMs.
"""

from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.monitoring.logger import get_logger
from app.schemas.models import CrowdDataInput, MovementDirection, ZoneConfig

logger = get_logger("intelligence.crowd_analyzer")


@dataclass
class ZoneInternalState:
    """Internal temporal state maintained per venue zone."""
    last_data: Optional[CrowdDataInput] = None
    history: deque[CrowdDataInput] = field(default_factory=lambda: deque(maxlen=60))
    congestion_start: Optional[datetime] = None
    last_direction_history: deque[MovementDirection] = field(default_factory=lambda: deque(maxlen=10))


class CrowdAnalyzer:
    """High-performance deterministic crowd intelligence analyzer."""

    def __init__(self) -> None:
        self._zone_states: dict[str, ZoneInternalState] = {}

    def _get_or_create_state(self, zone_id: str) -> ZoneInternalState:
        if zone_id not in self._zone_states:
            self._zone_states[zone_id] = ZoneInternalState()
        return self._zone_states[zone_id]

    async def analyze(self, data: CrowdDataInput, zone_config: ZoneConfig) -> dict[str, Any]:
        """Perform comprehensive deterministic analysis on structured crowd data."""
        state = self._get_or_create_state(data.zone_id)
        prev_data = state.last_data

        # 1. Calculate occupancy ratio
        capacity = max(zone_config.capacity, 1)
        occupancy_ratio = data.people_count / capacity
        if data.current_occupancy is not None:
            # Prefer provided occupancy if calibrated, else calculate
            occupancy_ratio = data.current_occupancy

        # 2. Calculate density (people/sqm)
        density = data.estimated_density
        if density is None and zone_config.area_sqm and zone_config.area_sqm > 0:
            density = data.people_count / zone_config.area_sqm

        # 3. Flow analysis
        inflow = data.inflow_rate or 0.0
        outflow = data.outflow_rate or 0.0
        net_flow = inflow - outflow

        # 4. Record history
        state.history.append(data)
        if data.movement_direction and data.movement_direction != MovementDirection.UNKNOWN:
            state.last_direction_history.append(data.movement_direction)

        # 5. Trend analysis
        trend, growth_slope = self._detect_trend(state)

        # 6. Accumulation anomaly (statistical outlier)
        is_accumulation_anomaly = self._detect_accumulation_anomaly(state, occupancy_ratio)

        # 7. Bottleneck detection
        is_bottleneck, bottleneck_reason = self._detect_bottleneck(data, occupancy_ratio, inflow, outflow)

        # 8. Counterflow detection
        is_counterflow, counterflow_reason = self._detect_counterflow(state, data)

        # 9. Sudden changes detection
        sudden_change_desc = self._detect_sudden_change(prev_data, occupancy_ratio, zone_config)

        # 10. Congestion duration tracking
        congestion_duration = self._update_congestion_tracking(
            state, occupancy_ratio, zone_config.threshold_moderate, data.timestamp
        )

        state.last_data = data

        analysis_result = {
            "zone_id": data.zone_id,
            "zone_name": zone_config.zone_name,
            "timestamp": data.timestamp,
            "people_count": data.people_count,
            "capacity": zone_config.capacity,
            "occupancy_ratio": round(occupancy_ratio, 4),
            "density": round(density, 4) if density is not None else None,
            "inflow_rate": inflow,
            "outflow_rate": outflow,
            "net_flow": round(net_flow, 2),
            "trend": trend,
            "growth_slope": round(growth_slope, 4),
            "is_accumulation_anomaly": is_accumulation_anomaly,
            "is_bottleneck": is_bottleneck,
            "bottleneck_reason": bottleneck_reason,
            "is_counterflow": is_counterflow,
            "counterflow_reason": counterflow_reason,
            "sudden_change": sudden_change_desc,
            "congestion_duration_seconds": congestion_duration,
            "history_depth": len(state.history),
        }

        return analysis_result

    def _detect_trend(self, state: ZoneInternalState) -> tuple[str, float]:
        """Compute growth trend using linear regression over recent occupancy history."""
        if len(state.history) < 3:
            return "stable", 0.0

        recent_points = list(state.history)[-10:]
        occupancies = [
            (p.current_occupancy if p.current_occupancy is not None else p.people_count)
            for p in recent_points
        ]
        n = len(occupancies)
        x = list(range(n))
        x_mean = (n - 1) / 2.0
        y_mean = sum(occupancies) / n

        numerator = sum((x[i] - x_mean) * (occupancies[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        slope = (numerator / denominator) if denominator != 0 else 0.0

        # Check consecutive moves
        consecutive_increases = sum(
            1 for i in range(1, len(occupancies)) if occupancies[i] > occupancies[i - 1]
        )
        consecutive_decreases = sum(
            1 for i in range(1, len(occupancies)) if occupancies[i] < occupancies[i - 1]
        )

        if slope > 0.02 or consecutive_increases >= 5:
            trend = "rapid_increase" if slope > 0.05 else "increasing"
        elif slope < -0.02 or consecutive_decreases >= 5:
            trend = "rapid_decrease" if slope < -0.05 else "decreasing"
        else:
            trend = "stable"

        return trend, slope

    def _detect_accumulation_anomaly(self, state: ZoneInternalState, current_occupancy: float) -> bool:
        """Detect statistical outliers: current occupancy > mean + 2*sigma of recent window."""
        if len(state.history) < 8:
            return False

        occupancies = [
            (p.current_occupancy if p.current_occupancy is not None else p.people_count)
            for p in list(state.history)[:-1]
        ]
        if len(occupancies) < 5:
            return False

        try:
            mean = statistics.mean(occupancies)
            stdev = statistics.stdev(occupancies)
            if stdev > 0.01:
                return (current_occupancy - mean) > (2.0 * stdev)
        except statistics.StatisticsError:
            pass
        return False

    def _detect_bottleneck(
        self,
        data: CrowdDataInput,
        occupancy_ratio: float,
        inflow: float,
        outflow: float,
    ) -> tuple[bool, Optional[str]]:
        """Identify physical or operational bottleneck indicators."""
        # 1. Inflow substantially exceeds outflow at non-trivial volumes
        if inflow >= 10.0 and outflow <= (inflow * 0.35) and occupancy_ratio >= 0.60:
            return True, f"Inflow ({inflow:.1f}/min) outpaces outflow ({outflow:.1f}/min) at {occupancy_ratio*100:.0f}% occupancy"

        # 2. Movement speed severely suppressed while density is moderate or above
        if (
            data.movement_speed is not None
            and data.movement_speed < 0.30
            and occupancy_ratio >= 0.70
        ):
            return True, f"Locomotion severely restricted ({data.movement_speed:.2f} m/s) at {occupancy_ratio*100:.0f}% occupancy"

        return False, None

    def _detect_counterflow(
        self,
        state: ZoneInternalState,
        data: CrowdDataInput,
    ) -> tuple[bool, Optional[str]]:
        """Detect counterflow or opposing crowd trajectories."""
        if data.movement_direction == MovementDirection.MIXED:
            return True, "Simultaneous bi-directional opposing flows reported"

        history = list(state.last_direction_history)
        if len(history) >= 4:
            inward_count = sum(1 for d in history if d == MovementDirection.INWARD)
            outward_count = sum(1 for d in history if d == MovementDirection.OUTWARD)
            if inward_count >= 2 and outward_count >= 2:
                return True, f"Oscillating directional flow (inward: {inward_count}, outward: {outward_count})"

        return False, None

    def _detect_sudden_change(
        self,
        prev_data: Optional[CrowdDataInput],
        current_occupancy: float,
        zone_config: ZoneConfig,
    ) -> Optional[str]:
        """Detect sudden surge or evacuation (>15% occupancy shift in one cycle)."""
        if prev_data is None:
            return None

        prev_occ = prev_data.current_occupancy
        if prev_occ is None:
            prev_occ = prev_data.people_count / max(zone_config.capacity, 1)

        delta = current_occupancy - prev_occ
        if abs(delta) >= 0.15:
            direction = "surge" if delta > 0 else "drop"
            return f"Sudden {direction} of {abs(delta)*100:.1f}% capacity observed within a single update"

        return None

    def _update_congestion_tracking(
        self,
        state: ZoneInternalState,
        occupancy_ratio: float,
        threshold: float,
        current_time: datetime,
    ) -> Optional[float]:
        """Track how long the zone has been continuously congested."""
        if occupancy_ratio >= threshold:
            if state.congestion_start is None:
                state.congestion_start = current_time
            dt = (current_time - state.congestion_start).total_seconds()
            return max(0.0, dt)
        else:
            state.congestion_start = None
            return None

    def get_zone_summary(self, zone_id: str) -> Optional[dict[str, Any]]:
        """Return latest state summary for a zone."""
        state = self._zone_states.get(zone_id)
        if not state or not state.last_data:
            return None
        return {
            "zone_id": zone_id,
            "last_people_count": state.last_data.people_count,
            "last_occupancy": state.last_data.current_occupancy,
            "history_points": len(state.history),
            "is_congested": state.congestion_start is not None,
        }

    def clear(self) -> None:
        """Reset internal zone states."""
        self._zone_states.clear()
