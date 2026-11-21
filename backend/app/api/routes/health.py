"""Health check endpoint probing DB, AI Agent, detector, and Copilot status."""
from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.copilot.provider import get_llm_provider
from app.copilot.tools import get_all_tools
from app.database.session import get_db
from app.integrations.agent_client import AIAgentClient
from app.schemas.api_schemas import HealthResponse
from app.services.video_processor import VideoProcessor, get_shared_detector
from app.services.ws_manager import ws_manager

router = APIRouter()
agent_client = AIAgentClient()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@router.get("", response_model=HealthResponse)
@router.get("/", response_model=HealthResponse, include_in_schema=False)
@router.get("/health", response_model=HealthResponse, include_in_schema=False)
async def health_check(db: Annotated[AsyncSession, Depends(get_db)]):
    db_status = "healthy"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"unhealthy: {exc}"

    agent_status = "disabled"
    try:
        agent_health = await agent_client.get_health()
        agent_status = agent_health.get("status", "unreachable")
    except Exception:
        agent_status = "unreachable"

    detector = get_shared_detector()
    provider = get_llm_provider()
    tools = get_all_tools()
    settings = get_settings()

    has_gemini = bool(getattr(settings, "gemini_api_key", "") or os.environ.get("GEMINI_API_KEY"))
    has_anthropic = bool(getattr(settings, "anthropic_api_key", "") or os.environ.get("ANTHROPIC_API_KEY"))
    has_openai = bool(getattr(settings, "openai_api_key", "") or os.environ.get("OPENAI_API_KEY"))

    active_jobs_count = len([k for k, v in VideoProcessor._active_jobs.items() if v])

    return HealthResponse(
        status="healthy" if db_status == "healthy" else "degraded",
        database=db_status,
        ai_agent=agent_status,
        detector_backend=detector.backend_name,
        active_ws_connections=ws_manager.connection_count(),
        timestamp=_utcnow(),
        copilot_provider=provider.name,
        copilot_llm_configured=has_gemini or has_anthropic or has_openai,
        copilot_tools_count=len(tools),
        active_processing_jobs=active_jobs_count,
    )
