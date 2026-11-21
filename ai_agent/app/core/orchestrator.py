"""Agent orchestrator coordinating the deterministic intelligence pipeline."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from app.alerts.alert_manager import AlertManager
from app.core.agent_state import AgentState
from app.core.event_context import EventContextManager
from app.intelligence.crowd_analyzer import CrowdAnalyzer
from app.intelligence.prediction_interpreter import PredictionInterpreter
from app.intelligence.risk_assessment import RiskAssessmentEngine
from app.monitoring.logger import get_logger
from app.recommendations.recommendation_engine import RecommendationEngine
from app.schemas.models import (
    AlertAcknowledgeRequest,
    AlertPriority,
    AlertResolveRequest,
    AlertResponse,
    AlertState,
    AnalysisResult,
    CrowdDataInput,
    PredictionInterpretation,
    Recommendation,
    RiskLevel,
    ZoneAnalysisResponse,
    ZoneRiskAssessment,
)
from app.services.cache import CacheService
from app.services.notification import NotificationService

logger = get_logger("core.orchestrator")


class AgentOrchestrator:
    """Central processing coordinator managing deterministic analytics, alerts, and notifications."""

    def __init__(
        self,
        crowd_analyzer: CrowdAnalyzer,
        risk_engine: RiskAssessmentEngine,
        prediction_interpreter: PredictionInterpreter,
        recommendation_engine: RecommendationEngine,
        alert_manager: AlertManager,
        notification_service: NotificationService,
        cache_service: CacheService,
        event_context_manager: EventContextManager,
        agent_state: AgentState,
    ) -> None:
        self.crowd_analyzer = crowd_analyzer
        self.risk_engine = risk_engine
        self.prediction_interpreter = prediction_interpreter
        self.recommendation_engine = recommendation_engine
        self.alert_manager = alert_manager
        self.notification_service = notification_service
        self.cache_service = cache_service
        self.event_context_manager = event_context_manager
        self.agent_state = agent_state

    async def process_batch(self, items: list[CrowdDataInput]) -> AnalysisResult:
        """Execute the end-to-end deterministic intelligence pipeline for incoming items."""
        start_time = time.monotonic()
        now = datetime.now(timezone.utc)

        all_assessments: list[ZoneRiskAssessment] = []
        all_predictions: list[PredictionInterpretation] = []
        all_recommendations: list[Recommendation] = []
        all_new_alerts: list[AlertResponse] = []

        if not items:
            return AnalysisResult(
                event_id="none",
                timestamp=now,
                zones_analyzed=0,
                processing_time_ms=0.0,
            )

        # Group data items by event_id
        items_by_event: dict[str, list[CrowdDataInput]] = defaultdict(list)
        for item in items:
            items_by_event[item.event_id].append(item)

        primary_event_id = items[0].event_id

        for event_id, event_items in items_by_event.items():
            context = self.event_context_manager.get_context(event_id)
            if not context:
                logger.warning("Received data for unregistered event; skipping", event_id=event_id)
                continue

            # Pre-fetch existing adjacent assessments to evaluate spillover
            existing_assessments = list(context.get_all_latest_assessments().values())

            for data in event_items:
                zone_config = context.get_zone_config(data.zone_id)
                if not zone_config:
                    logger.warning(
                        "Received data for zone not defined in venue layout; skipping",
                        event_id=event_id,
                        zone_id=data.zone_id,
                    )
                    continue

                # 1. Record raw snapshot in event context
                context.record_data(data)

                # 2. Run deterministic Crowd Analyzer
                analysis = await self.crowd_analyzer.analyze(data, zone_config)

                # 3. Run Risk Assessment Engine
                assessment = await self.risk_engine.assess(
                    data=data,
                    zone_config=zone_config,
                    analysis=analysis,
                    adjacent_assessments=existing_assessments,
                )
                context.record_assessment(assessment)
                all_assessments.append(assessment)

                # 4. Run Prediction Interpreter
                predictions = await self.prediction_interpreter.interpret(
                    data=data,
                    zone_config=zone_config,
                    current_risk=assessment.risk_level,
                )
                all_predictions.extend(predictions)

                # 5. Run Recommendation Engine
                recs = await self.recommendation_engine.generate(
                    risk_assessment=assessment,
                    analysis=analysis,
                    predictions=predictions,
                    zone_config=zone_config,
                    event_id=event_id,
                )
                all_recommendations.extend(recs)

                # 6. Run Alert Manager
                new_alerts = await self.alert_manager.evaluate_and_create(
                    risk_assessment=assessment,
                    analysis=analysis,
                    zone_config=zone_config,
                    event_id=event_id,
                )
                all_new_alerts.extend(new_alerts)

                # 7. Asynchronous notifications
                # A. Risk level change notification
                if assessment.previous_risk_level and assessment.previous_risk_level != assessment.risk_level:
                    await self.notification_service.notify_risk_change(
                        event_id=event_id,
                        zone_id=zone_config.zone_id,
                        zone_name=zone_config.zone_name,
                        old_risk=assessment.previous_risk_level,
                        new_risk=assessment.risk_level,
                        explanation=assessment.explanation,
                    )

                # B. New alert notifications
                for alert in new_alerts:
                    await self.notification_service.notify_alert(alert)

                # C. New recommendation notifications
                for rec in recs:
                    await self.notification_service.notify_recommendation(event_id, rec)

                # 8. Cache latest assessment in Redis/fallback
                cache_key = f"cv:risk:{event_id}:{zone_config.zone_id}"
                await self.cache_service.set_json(cache_key, assessment.model_dump(mode="json"), expire_seconds=300)

        elapsed_ms = (time.monotonic() - start_time) * 1000.0
        self.agent_state.record_analysis_cycle(len(items))

        return AnalysisResult(
            event_id=primary_event_id,
            timestamp=now,
            zones_analyzed=len(all_assessments),
            risk_assessments=all_assessments,
            predictions=all_predictions,
            recommendations=all_recommendations,
            new_alerts=all_new_alerts,
            processing_time_ms=round(elapsed_ms, 2),
        )

    async def get_zone_analysis(self, event_id: str, zone_id: str) -> ZoneAnalysisResponse:
        """Fetch comprehensive multi-dimensional analytical view for a zone."""
        context = self.event_context_manager.get_or_raise(event_id)
        zone_config = context.get_zone_config(zone_id)
        if not zone_config:
            raise ValueError(f"Zone '{zone_id}' not found in event '{event_id}'")

        assessment = context.get_latest_assessment(zone_id)
        active_alerts = self.alert_manager.get_active_alerts(event_id=event_id, zone_id=zone_id)
        all_recs = self.recommendation_engine.get_active_recommendations(event_id)
        zone_recs = [r for r in all_recs if r.affected_zone == zone_id]

        recent_history = [
            d.model_dump(mode="json")
            for d in context.get_zone_history(zone_id=zone_id, minutes=15)
        ]

        latest_data = context.get_latest_data(zone_id)
        latest_prediction = None
        if latest_data and assessment:
            preds = await self.prediction_interpreter.interpret(
                data=latest_data,
                zone_config=zone_config,
                current_risk=assessment.risk_level,
            )
            if preds:
                latest_prediction = preds[0]

        return ZoneAnalysisResponse(
            zone_id=zone_id,
            zone_name=zone_config.zone_name,
            risk_assessment=assessment,
            latest_prediction=latest_prediction,
            active_alerts=active_alerts,
            recommendations=zone_recs,
            recent_history=recent_history,
        )

    async def acknowledge_alert(self, alert_id: str, request: AlertAcknowledgeRequest) -> Optional[AlertResponse]:
        """Acknowledge alert and notify listeners."""
        alert = await self.alert_manager.acknowledge(alert_id, request.acknowledged_by)
        if alert:
            await self.notification_service.notify_alert(alert)
        return alert

    async def resolve_alert(self, alert_id: str, request: AlertResolveRequest) -> Optional[AlertResponse]:
        """Resolve alert and notify listeners."""
        alert = await self.alert_manager.resolve(alert_id, request.resolved_by, request.resolution_note)
        if alert:
            await self.notification_service.notify_alert(alert)
        return alert

    def get_alerts(
        self,
        event_id: str,
        zone_id: Optional[str] = None,
        priority: Optional[str] = None,
        state: Optional[str] = None,
    ) -> list[AlertResponse]:
        """Query active alerts."""
        prio_enum = AlertPriority(priority.upper()) if priority else None
        state_enum = AlertState(state.upper()) if state else None
        return self.alert_manager.get_active_alerts(
            event_id=event_id,
            zone_id=zone_id,
            priority=prio_enum,
            state=state_enum,
        )

    def get_recommendations(self, event_id: str) -> list[Recommendation]:
        """Fetch active recommendations for an event."""
        return self.recommendation_engine.get_active_recommendations(event_id)
