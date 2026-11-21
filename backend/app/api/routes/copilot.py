"""AI Copilot backend API endpoints for CROWD VISION Phase 3."""
from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Annotated, Any, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.copilot.executor import CopilotToolExecutor
from app.copilot.provider import get_llm_provider
from app.copilot.service import CopilotService
from app.copilot.tools import get_all_tools
from app.database.session import get_db
from app.integrations.agent_client import AIAgentClient
from app.schemas.api_schemas import (
    CopilotActionExecuteRequest,
    CopilotActionExecuteResponse,
    CopilotActionProposal,
    CopilotActionValidateRequest,
    CopilotActionValidateResponse,
    CopilotQueryRequest,
    CopilotQueryResponse,
    CopilotToolDefinition,
)

router = APIRouter(prefix="/copilot", tags=["AI Copilot"])
agent_client = AIAgentClient()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/status")
async def get_copilot_status():
    """Retrieve Copilot provider connectivity, active model, and tool readiness."""
    settings = get_settings()
    provider = get_llm_provider()
    tools = get_all_tools()

    has_gemini = bool(getattr(settings, "gemini_api_key", "") or os.environ.get("GEMINI_API_KEY"))
    has_anthropic = bool(getattr(settings, "anthropic_api_key", "") or os.environ.get("ANTHROPIC_API_KEY"))
    has_openai = bool(getattr(settings, "openai_api_key", "") or os.environ.get("OPENAI_API_KEY"))

    return {
        "status": "ONLINE",
        "active_provider": provider.name,
        "model_name": getattr(provider, "model_name", "deterministic_spatial_v3"),
        "is_llm_configured": has_gemini or has_anthropic or has_openai,
        "circuit_breaker": getattr(getattr(provider, "circuit_breaker", None), "state", "CLOSED"),
        "fallback_mode": "DETERMINISTIC_SPATIAL_INTELLIGENCE",
        "available_tools_count": len(tools),
        "available_tools": tools,
        "agent_service_connected": agent_client._enabled(),
    }


@router.get("/tools", response_model=list[CopilotToolDefinition])
async def list_copilot_tools():
    """List all available Copilot tools, their schemas, and confirmation requirements."""
    tools = get_all_tools()
    return [
        CopilotToolDefinition(
            name=t["name"],
            description=t["description"],
            category=t["category"],
            requires_confirmation=t["requires_confirmation"],
            parameters=t["parameters"],
        )
        for t in tools
    ]


@router.post("/query", response_model=CopilotQueryResponse)
async def query_copilot(
    payload: CopilotQueryRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Context-aware Copilot inquiry grounded in the active task, spatial layout, and real-time telemetry."""
    copilot_service = CopilotService(db)
    return await copilot_service.query(
        message=payload.message,
        task_id=payload.task_id,
        session_id=payload.session_id,
        context_override=payload.context,
    )


@router.post("/validate-action", response_model=CopilotActionValidateResponse)
async def validate_copilot_action(
    payload: CopilotActionValidateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Validate safety, constraints, and impact before applying an AI Copilot action proposal."""
    executor = CopilotToolExecutor(db)
    is_valid, errors, impact = await executor.validate_action(
        action_type=payload.action_type,
        parameters=payload.parameters,
        task_id=payload.task_id,
    )
    return CopilotActionValidateResponse(
        is_valid=is_valid,
        validation_errors=errors,
        simulated_impact=impact,
        can_execute=is_valid,
    )


@router.post("/execute-action", response_model=CopilotActionExecuteResponse)
async def execute_copilot_action(
    payload: CopilotActionExecuteRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Safely execute an operator-approved Copilot action and persist audit logs."""
    executor = CopilotToolExecutor(db)
    try:
        result = await executor.execute_action(
            action_type=payload.action_type,
            parameters=payload.parameters,
            task_id=payload.task_id,
            confirmed_by=payload.confirmed_by or "operator",
        )
        return CopilotActionExecuteResponse(
            success=True,
            action_type=payload.action_type,
            result=result,
            message=f"Action '{payload.action_type}' executed successfully.",
            task_id=payload.task_id,
            timestamp=_utcnow(),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to execute action '{payload.action_type}': {str(exc)}",
        )
