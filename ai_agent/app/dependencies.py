"""FastAPI dependency injection container and service singletons."""

from __future__ import annotations

from typing import Optional

from app.alerts.alert_manager import AlertManager
from app.config import Settings, get_settings
from app.core.agent_state import AgentState
from app.core.event_context import EventContextManager
from app.core.orchestrator import AgentOrchestrator
from app.database.session import close_db, init_db, is_database_available
from app.intelligence.crowd_analyzer import CrowdAnalyzer
from app.intelligence.prediction_interpreter import PredictionInterpreter
from app.intelligence.risk_assessment import RiskAssessmentEngine
from app.llm.provider import LLMProvider
from app.llm.response_parser import ToolExecutor
from app.monitoring.audit import AuditService
from app.monitoring.health import HealthChecker
from app.monitoring.logger import get_logger
from app.monitoring.metrics import MetricsCollector
from app.recommendations.recommendation_engine import RecommendationEngine
from app.services.cache import CacheService
from app.services.ingestion import IngestionService
from app.services.notification import NotificationService

logger = get_logger("dependencies")

# Singleton containers
_cache_service: Optional[CacheService] = None
_notification_service: Optional[NotificationService] = None
_ingestion_service: Optional[IngestionService] = None
_event_context_manager: Optional[EventContextManager] = None
_agent_state: Optional[AgentState] = None
_alert_manager: Optional[AlertManager] = None
_orchestrator: Optional[AgentOrchestrator] = None
_llm_provider: Optional[LLMProvider] = None
_tool_executor: Optional[ToolExecutor] = None
_metrics_collector: Optional[MetricsCollector] = None
_audit_service: Optional[AuditService] = None
_health_checker: Optional[HealthChecker] = None


async def initialize_services() -> None:
    """Instantiate and wire up all subsystem singletons on application startup."""
    global _cache_service, _notification_service, _ingestion_service
    global _event_context_manager, _agent_state, _alert_manager
    global _orchestrator, _llm_provider, _tool_executor
    global _metrics_collector, _audit_service, _health_checker

    settings = get_settings()

    # 1. Database
    db_ok = await init_db()

    # 2. State & Metrics
    _agent_state = AgentState()
    _agent_state.database_available = db_ok
    _metrics_collector = MetricsCollector()
    _audit_service = AuditService()

    # 3. Services
    _cache_service = CacheService()
    redis_ok = await _cache_service.connect(settings.redis_url, settings.redis_max_connections)
    _agent_state.redis_available = redis_ok

    _notification_service = NotificationService()
    _ingestion_service = IngestionService(
        max_queue_size=settings.agent_max_queue_size,
        dedup_window_seconds=settings.agent_dedup_window,
    )
    _event_context_manager = EventContextManager()

    # 4. Intelligence & Recommendations
    crowd_analyzer = CrowdAnalyzer()
    risk_engine = RiskAssessmentEngine()
    prediction_interpreter = PredictionInterpreter()
    recommendation_engine = RecommendationEngine(dedup_window_seconds=int(settings.alert_dedup_window))
    _alert_manager = AlertManager(
        dedup_window_seconds=settings.alert_dedup_window,
        escalation_timeout_seconds=settings.alert_escalation_timeout,
        max_active=settings.alert_max_active,
    )

    # 5. Central Orchestrator
    _orchestrator = AgentOrchestrator(
        crowd_analyzer=crowd_analyzer,
        risk_engine=risk_engine,
        prediction_interpreter=prediction_interpreter,
        recommendation_engine=recommendation_engine,
        alert_manager=_alert_manager,
        notification_service=_notification_service,
        cache_service=_cache_service,
        event_context_manager=_event_context_manager,
        agent_state=_agent_state,
    )

    # 6. LLM Provider
    _llm_provider = LLMProvider(
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_model,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
        enabled=settings.llm_enabled,
    )
    llm_ok = await _llm_provider.initialize()
    _agent_state.llm_available = llm_ok

    # 7. LLM Tool Executor
    _tool_executor = ToolExecutor(_orchestrator)

    # 8. Health Checker
    _health_checker = HealthChecker(_cache_service, _agent_state)

    logger.info("All CrowdVision AI Agent dependencies initialized successfully")


async def shutdown_services() -> None:
    """Tear down and close all active resource pools gracefully."""
    global _cache_service, _orchestrator

    if _cache_service:
        await _cache_service.close()

    await close_db()
    logger.info("All CrowdVision AI Agent dependencies shut down")


# ── Dependency Injection Providers ──────────────────────────────

def get_orchestrator() -> AgentOrchestrator:
    if _orchestrator is None:
        raise RuntimeError("Orchestrator not initialized")
    return _orchestrator


def get_cache() -> CacheService:
    if _cache_service is None:
        raise RuntimeError("CacheService not initialized")
    return _cache_service


def get_notification() -> NotificationService:
    if _notification_service is None:
        raise RuntimeError("NotificationService not initialized")
    return _notification_service


def get_ingestion() -> IngestionService:
    if _ingestion_service is None:
        raise RuntimeError("IngestionService not initialized")
    return _ingestion_service


def get_event_manager() -> EventContextManager:
    if _event_context_manager is None:
        raise RuntimeError("EventContextManager not initialized")
    return _event_context_manager


def get_agent_state() -> AgentState:
    if _agent_state is None:
        raise RuntimeError("AgentState not initialized")
    return _agent_state


def get_alert_manager() -> AlertManager:
    if _alert_manager is None:
        raise RuntimeError("AlertManager not initialized")
    return _alert_manager


def get_llm_provider() -> LLMProvider:
    if _llm_provider is None:
        raise RuntimeError("LLMProvider not initialized")
    return _llm_provider


def get_tool_executor() -> ToolExecutor:
    if _tool_executor is None:
        raise RuntimeError("ToolExecutor not initialized")
    return _tool_executor


def get_metrics() -> MetricsCollector:
    if _metrics_collector is None:
        raise RuntimeError("MetricsCollector not initialized")
    return _metrics_collector


def get_audit_service() -> AuditService:
    if _audit_service is None:
        raise RuntimeError("AuditService not initialized")
    return _audit_service


def get_health_checker() -> HealthChecker:
    if _health_checker is None:
        raise RuntimeError("HealthChecker not initialized")
    return _health_checker
