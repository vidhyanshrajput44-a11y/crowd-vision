"""Action catalog providing curated, scenario-driven operational action templates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.schemas.models import RecommendationPriority, RiskLevel


@dataclass
class ActionTemplate:
    """Action template for crowd management response."""
    action: str
    reason_template: str
    priority: RecommendationPriority
    suggested_team: str  # "security", "operations", "management", "medical"
    requires_human_approval: bool = True
    min_risk_level: RiskLevel = RiskLevel.LOW


# Standard catalog categorized by physical/operational scenarios
ACTION_CATALOG: dict[str, list[ActionTemplate]] = {
    # ── High Occupancy / Saturation ──────────────────────────────
    "high_occupancy": [
        ActionTemplate(
            action="Deploy crowd monitors to observe flow dynamics and identify local pinches",
            reason_template="Zone {zone_name} occupancy is at {occupancy:.0f}% capacity, approaching saturation limits",
            priority=RecommendationPriority.MEDIUM,
            suggested_team="operations",
            requires_human_approval=False,
            min_risk_level=RiskLevel.MODERATE,
        ),
        ActionTemplate(
            action="Alert security detail to stand by for active crowd metering",
            reason_template="Crowd density in {zone_name} has reached elevated levels ({occupancy:.0f}% capacity)",
            priority=RecommendationPriority.HIGH,
            suggested_team="security",
            requires_human_approval=False,
            min_risk_level=RiskLevel.HIGH,
        ),
        ActionTemplate(
            action="Inspect all emergency exits and egress corridors to ensure zero obstruction",
            reason_template="High crowd concentration requires uncompromised emergency pathways",
            priority=RecommendationPriority.HIGH,
            suggested_team="security",
            requires_human_approval=False,
            min_risk_level=RiskLevel.HIGH,
        ),
        ActionTemplate(
            action="Coordinate crowd diversion to adjacent lower-density zones",
            reason_template="Redistribution from {zone_name} ({occupancy:.0f}%) is necessary to relieve structural pressure",
            priority=RecommendationPriority.URGENT,
            suggested_team="operations",
            requires_human_approval=True,
            min_risk_level=RiskLevel.CRITICAL,
        ),
        ActionTemplate(
            action="Request event management authorization for temporary zone ingress pause",
            reason_template="Critical capacity exceeded ({occupancy:.0f}%); ingress metering required to prevent crowd crush",
            priority=RecommendationPriority.URGENT,
            suggested_team="management",
            requires_human_approval=True,
            min_risk_level=RiskLevel.CRITICAL,
        ),
    ],

    # ── Rapid Growth Inflow ──────────────────────────────────────
    "rapid_growth": [
        ActionTemplate(
            action="Monitor incoming visitor rate at access corridors",
            reason_template="Zone {zone_name} is experiencing an accelerating accumulation trend",
            priority=RecommendationPriority.LOW,
            suggested_team="operations",
            requires_human_approval=False,
            min_risk_level=RiskLevel.LOW,
        ),
        ActionTemplate(
            action="Pre-position additional stewarding staff at inbound bottlenecks",
            reason_template="Rapid inflow threatens to overwhelm {zone_name} before standard shift rotation",
            priority=RecommendationPriority.MEDIUM,
            suggested_team="operations",
            requires_human_approval=True,
            min_risk_level=RiskLevel.MODERATE,
        ),
        ActionTemplate(
            action="Prepare secondary ingress corridors and signage for redirection",
            reason_template="Surging crowd trajectory indicates potential saturation within minutes",
            priority=RecommendationPriority.HIGH,
            suggested_team="operations",
            requires_human_approval=True,
            min_risk_level=RiskLevel.HIGH,
        ),
    ],

    # ── Entrance / Access Bottlenecks ─────────────────────────────
    "entrance_congestion": [
        ActionTemplate(
            action="Audit ticket validation throughput and bag check lane efficiency",
            reason_template="Entrance bottleneck forming in {zone_name}; queue length growing rapidly",
            priority=RecommendationPriority.MEDIUM,
            suggested_team="operations",
            requires_human_approval=False,
            min_risk_level=RiskLevel.MODERATE,
        ),
        ActionTemplate(
            action="Request operational approval to open supplementary staffed entry lanes",
            reason_template="Inflow capacity at {zone_name} is currently insufficient for arrival volume",
            priority=RecommendationPriority.HIGH,
            suggested_team="management",
            requires_human_approval=True,
            min_risk_level=RiskLevel.HIGH,
        ),
        ActionTemplate(
            action="Inform event management of ingress delays to evaluate gate schedule adjustments",
            reason_template="Entrance congestion may delay event commencement or create perimeter pressure",
            priority=RecommendationPriority.MEDIUM,
            suggested_team="management",
            requires_human_approval=False,
            min_risk_level=RiskLevel.MODERATE,
        ),
    ],

    # ── Bottlenecks & Constricted Movement ───────────────────────
    "bottleneck": [
        ActionTemplate(
            action="Dispatch floor stewards to investigate physical obstruction or stoppage",
            reason_template="Flow velocity in {zone_name} has dropped below 0.3 m/s under dense conditions",
            priority=RecommendationPriority.HIGH,
            suggested_team="security",
            requires_human_approval=False,
            min_risk_level=RiskLevel.MODERATE,
        ),
        ActionTemplate(
            action="Establish one-way circulation pattern using temporary barriers if approved",
            reason_template="Constricted throughput in {zone_name} is producing localized compression",
            priority=RecommendationPriority.HIGH,
            suggested_team="operations",
            requires_human_approval=True,
            min_risk_level=RiskLevel.HIGH,
        ),
    ],

    # ── Counterflow / Opposing Streams ────────────────────────────
    "counterflow": [
        ActionTemplate(
            action="Station security staff to separate opposing pedestrian traffic lanes",
            reason_template="Counterflow turbulence in {zone_name} poses high turbulence and falling hazard",
            priority=RecommendationPriority.HIGH,
            suggested_team="security",
            requires_human_approval=False,
            min_risk_level=RiskLevel.MODERATE,
        ),
        ActionTemplate(
            action="Implement directional flow control on primary pathways",
            reason_template="Opposing crowd movements in {zone_name} are creating stationary turbulence",
            priority=RecommendationPriority.HIGH,
            suggested_team="operations",
            requires_human_approval=True,
            min_risk_level=RiskLevel.HIGH,
        ),
    ],

    # ── Emerging Hotspot (Forecast Ahead) ─────────────────────────
    "emerging_hotspot": [
        ActionTemplate(
            action="Increase video and sensor surveillance on projected congestion zone",
            reason_template="Predictive model identifies {zone_name} as an emerging hotspot within upcoming forecast horizon",
            priority=RecommendationPriority.MEDIUM,
            suggested_team="operations",
            requires_human_approval=False,
            min_risk_level=RiskLevel.LOW,
        ),
        ActionTemplate(
            action="Pre-deploy response personnel adjacent to {zone_name} prior to predicted peak",
            reason_template="Early positioning ensures readiness before forecasted crowd surge arrives",
            priority=RecommendationPriority.HIGH,
            suggested_team="security",
            requires_human_approval=True,
            min_risk_level=RiskLevel.MODERATE,
        ),
    ],

    # ── Adjacent Spillover ───────────────────────────────────────
    "adjacent_spillover": [
        ActionTemplate(
            action="Increase observation of boundary between {zone_name} and neighbouring saturated zones",
            reason_template="Adjacent zones are experiencing critical occupancy with risk of displacement spillover",
            priority=RecommendationPriority.MEDIUM,
            suggested_team="security",
            requires_human_approval=False,
            min_risk_level=RiskLevel.MODERATE,
        ),
    ],

    # ── Sustained Congestion ─────────────────────────────────────
    "sustained_congestion": [
        ActionTemplate(
            action="Evaluate environmental comfort, water access, and crowd fatigue indicators",
            reason_template="{zone_name} has experienced unbroken congestion for over 10 minutes",
            priority=RecommendationPriority.HIGH,
            suggested_team="medical",
            requires_human_approval=False,
            min_risk_level=RiskLevel.HIGH,
        ),
        ActionTemplate(
            action="Brief incident commander on persistent density status and review dispersal plan",
            reason_template="Sustained congestion duration exceeds baseline safety tolerance",
            priority=RecommendationPriority.URGENT,
            suggested_team="management",
            requires_human_approval=True,
            min_risk_level=RiskLevel.HIGH,
        ),
    ],
}
