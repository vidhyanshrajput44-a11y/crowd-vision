"""Alert generation service with cooldown deduplication."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.logging import get_logger
from app.risk.engine import RiskResult

logger = get_logger("crowdvision.risk.alert_service")

RISK_TO_SEVERITY = {
    "MODERATE": "MEDIUM",
    "HIGH": "HIGH",
    "CRITICAL": "CRITICAL",
}

DEFAULT_COOLDOWN_SECONDS = 30.0


@dataclass
class AlertData:
    """An alert emitted by the risk pipeline."""

    event_id: str
    zone_id: str
    zone_name: str
    category: str
    severity: str  # LOW / MEDIUM / HIGH / CRITICAL
    title: str
    description: str
    supporting_measurements: dict
    video_timestamp_sec: float
    source: str = "RISK_ENGINE"


class AlertService:
    """Generates alerts from RiskResult objects, deduplicating via per-zone cooldowns."""

    def __init__(self, cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS) -> None:
        self.cooldown_seconds = cooldown_seconds
        self._last_fired: dict[tuple[str, str, str], float] = {}
        logger.info("AlertService initialised", cooldown_seconds=self.cooldown_seconds)

    def process_risk_assessments(
        self,
        risk_assessments: list[RiskResult],
        snapshots: Optional[list[Any]] = None,
        video_timestamp_sec: float = 0.0,
        event_id: str = "event_default",
    ) -> list[Any]:
        return self.evaluate(
            risk_results=risk_assessments,
            event_id=event_id,
            video_timestamp_sec=video_timestamp_sec,
        )

    def evaluate(
        self,
        risk_results: list[RiskResult],
        event_id: str,
        video_timestamp_sec: float,
    ) -> list[AlertData]:
        alerts: list[AlertData] = []
        for res in risk_results:
            if res.risk_level not in RISK_TO_SEVERITY:
                continue

            severity = RISK_TO_SEVERITY[res.risk_level]
            category = self._determine_category(res)
            cooldown_key = (event_id, res.zone_id, category)

            last_ts = self._last_fired.get(cooldown_key)
            if last_ts is not None and abs(video_timestamp_sec - last_ts) < self.cooldown_seconds:
                continue

            self._last_fired[cooldown_key] = video_timestamp_sec

            m = res.supporting_measurements or {}
            occ_pct = float(m.get("occupancy_ratio", 0.0)) * 100.0
            people = m.get("people_count", 0)
            cap = m.get("capacity", 0)
            inflow = m.get("inflow_rate", 0.0)
            outflow = m.get("outflow_rate", 0.0)

            title = self._build_title(category, res.risk_level, res.zone_name, occ_pct)
            description = (
                f"{res.reason} | Current count: {people}/{cap} ({occ_pct:.1f}%), "
                f"inflow: {inflow:.1f}/min, outflow: {outflow:.1f}/min. "
                f"Monitoring priority: {res.monitoring_priority}."
            )
            if res.requires_human_review:
                description += " Human safety-team review recommended."

            alerts.append(
                AlertData(
                    event_id=event_id,
                    zone_id=res.zone_id,
                    zone_name=res.zone_name,
                    category=category,
                    severity=severity,
                    title=title,
                    description=description,
                    supporting_measurements=m,
                    video_timestamp_sec=round(video_timestamp_sec, 2),
                    source="RISK_ENGINE",
                )
            )

        return alerts

    def _determine_category(self, res: RiskResult) -> str:
        factors_joined = " ".join(res.contributing_factors)
        if res.risk_level == "CRITICAL":
            return "critical_density"
        elif "bottleneck_detected" in factors_joined:
            return "bottleneck"
        elif "counterflow_detected" in factors_joined:
            return "counterflow"
        elif "rapid_accumulation" in factors_joined:
            return "rapid_accumulation"
        return "occupancy_warning"

    def _build_title(self, category: str, risk_level: str, zone_name: str, occ_pct: float) -> str:
        if category == "critical_density":
            return f"Critical Density Alert: {zone_name} at {occ_pct:.0f}%"
        elif category == "bottleneck":
            return f"Bottleneck Detected: {zone_name}"
        elif category == "counterflow":
            return f"Counterflow Detected: {zone_name}"
        elif category == "rapid_accumulation":
            return f"Rapid Crowd Accumulation: {zone_name}"
        return f"{risk_level} Risk Warning: {zone_name}"
