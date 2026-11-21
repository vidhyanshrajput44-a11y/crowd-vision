"""Configurable alert rules and evaluation engine."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.schemas.models import (
    AlertPriority,
    RiskLevel,
    ZoneConfig,
    ZoneRiskAssessment,
)


@dataclass
class AlertRule:
    """Configurable rule governing automatic alert generation."""
    rule_id: str
    alert_type: str
    title_template: str
    description_template: str
    condition: Callable[[ZoneRiskAssessment, dict[str, Any], ZoneConfig], bool]
    priority_fn: Callable[[ZoneRiskAssessment, dict[str, Any]], AlertPriority]
    cooldown_seconds: int = 60


def _rule_critical_occupancy_cond(assessment: ZoneRiskAssessment, analysis: dict[str, Any], config: ZoneConfig) -> bool:
    return assessment.risk_level == RiskLevel.CRITICAL or (
        assessment.occupancy_ratio is not None and assessment.occupancy_ratio >= config.threshold_critical
    )


def _rule_critical_occupancy_prio(assessment: ZoneRiskAssessment, analysis: dict[str, Any]) -> AlertPriority:
    return AlertPriority.CRITICAL


def _rule_high_occupancy_cond(assessment: ZoneRiskAssessment, analysis: dict[str, Any], config: ZoneConfig) -> bool:
    return assessment.risk_level == RiskLevel.HIGH or (
        assessment.occupancy_ratio is not None and assessment.occupancy_ratio >= config.threshold_high
    )


def _rule_high_occupancy_prio(assessment: ZoneRiskAssessment, analysis: dict[str, Any]) -> AlertPriority:
    return AlertPriority.HIGH


def _rule_bottleneck_cond(assessment: ZoneRiskAssessment, analysis: dict[str, Any], config: ZoneConfig) -> bool:
    return bool(analysis.get("is_bottleneck"))


def _rule_bottleneck_prio(assessment: ZoneRiskAssessment, analysis: dict[str, Any]) -> AlertPriority:
    occ = analysis.get("occupancy_ratio", 0.0)
    return AlertPriority.CRITICAL if occ >= 0.85 else AlertPriority.HIGH


def _rule_counterflow_cond(assessment: ZoneRiskAssessment, analysis: dict[str, Any], config: ZoneConfig) -> bool:
    return bool(analysis.get("is_counterflow"))


def _rule_counterflow_prio(assessment: ZoneRiskAssessment, analysis: dict[str, Any]) -> AlertPriority:
    return AlertPriority.HIGH


def _rule_rapid_growth_cond(assessment: ZoneRiskAssessment, analysis: dict[str, Any], config: ZoneConfig) -> bool:
    return analysis.get("trend") == "rapid_increase" and (analysis.get("occupancy_ratio", 0) >= 0.60)


def _rule_rapid_growth_prio(assessment: ZoneRiskAssessment, analysis: dict[str, Any]) -> AlertPriority:
    occ = analysis.get("occupancy_ratio", 0.0)
    return AlertPriority.HIGH if occ >= 0.80 else AlertPriority.MEDIUM


def _rule_sustained_congestion_cond(assessment: ZoneRiskAssessment, analysis: dict[str, Any], config: ZoneConfig) -> bool:
    dur = analysis.get("congestion_duration_seconds")
    return dur is not None and dur >= 600  # >= 10 mins


def _rule_sustained_congestion_prio(assessment: ZoneRiskAssessment, analysis: dict[str, Any]) -> AlertPriority:
    dur = analysis.get("congestion_duration_seconds", 0)
    return AlertPriority.CRITICAL if dur >= 1200 else AlertPriority.HIGH


def _rule_sudden_change_cond(assessment: ZoneRiskAssessment, analysis: dict[str, Any], config: ZoneConfig) -> bool:
    return analysis.get("sudden_change") is not None


def _rule_sudden_change_prio(assessment: ZoneRiskAssessment, analysis: dict[str, Any]) -> AlertPriority:
    return AlertPriority.MEDIUM


# Default rule suite
DEFAULT_ALERT_RULES: list[AlertRule] = [
    AlertRule(
        rule_id="rule_critical_occupancy",
        alert_type="CRITICAL_OCCUPANCY",
        title_template="CRITICAL CAPACITY: {zone_name}",
        description_template="Zone {zone_name} has breached critical safety capacity at {occupancy:.1f}% ({count}/{capacity} people). Immediate crowd management response required.",
        condition=_rule_critical_occupancy_cond,
        priority_fn=_rule_critical_occupancy_prio,
        cooldown_seconds=45,
    ),
    AlertRule(
        rule_id="rule_high_occupancy",
        alert_type="HIGH_OCCUPANCY",
        title_template="HIGH DENSITY WARNING: {zone_name}",
        description_template="Zone {zone_name} has reached {occupancy:.1f}% capacity ({count}/{capacity} people), exceeding safe operational threshold.",
        condition=_rule_high_occupancy_cond,
        priority_fn=_rule_high_occupancy_prio,
        cooldown_seconds=60,
    ),
    AlertRule(
        rule_id="rule_bottleneck",
        alert_type="BOTTLENECK_DETECTED",
        title_template="BOTTLENECK: {zone_name}",
        description_template="Localized physical or operational bottleneck identified in {zone_name}. Movement suppressed or inflow severely outstripping egress.",
        condition=_rule_bottleneck_cond,
        priority_fn=_rule_bottleneck_prio,
        cooldown_seconds=90,
    ),
    AlertRule(
        rule_id="rule_counterflow",
        alert_type="COUNTERFLOW_HAZARD",
        title_template="COUNTERFLOW CONFLICT: {zone_name}",
        description_template="Opposing crowd stream collisions detected in {zone_name}, creating severe compression hazard.",
        condition=_rule_counterflow_cond,
        priority_fn=_rule_counterflow_prio,
        cooldown_seconds=90,
    ),
    AlertRule(
        rule_id="rule_rapid_growth",
        alert_type="RAPID_ACCUMULATION",
        title_template="RAPID SURGE: {zone_name}",
        description_template="Steep sustained crowd accumulation in {zone_name}. Inflow trajectory suggests impending threshold breach.",
        condition=_rule_rapid_growth_cond,
        priority_fn=_rule_rapid_growth_prio,
        cooldown_seconds=60,
    ),
    AlertRule(
        rule_id="rule_sustained_congestion",
        alert_type="SUSTAINED_CONGESTION",
        title_template="EXTENDED CONGESTION: {zone_name}",
        description_template="Persistent continuous congestion observed in {zone_name} for exceeding safe dwell duration thresholds.",
        condition=_rule_sustained_congestion_cond,
        priority_fn=_rule_sustained_congestion_prio,
        cooldown_seconds=120,
    ),
    AlertRule(
        rule_id="rule_sudden_change",
        alert_type="SUDDEN_DENSITY_SHIFT",
        title_template="SUDDEN CROWD SHIFT: {zone_name}",
        description_template="Abrupt change detected in {zone_name}: {sudden_change}.",
        condition=_rule_sudden_change_cond,
        priority_fn=_rule_sudden_change_prio,
        cooldown_seconds=60,
    ),
]
