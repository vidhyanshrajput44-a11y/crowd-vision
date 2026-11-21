"""Conversational AI analyst and operator feedback route handlers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.middleware.auth import verify_api_key
from app.core.event_context import EventContextManager
from app.dependencies import (
    get_audit_service,
    get_event_manager,
    get_llm_provider,
    get_tool_executor,
)
from app.llm.provider import LLMProvider
from app.llm.response_parser import ToolExecutor
from app.monitoring.audit import AuditService
from app.schemas.models import (
    ChatRequest,
    ChatResponse,
    FeedbackRequest,
    FeedbackResponse,
)

router = APIRouter(prefix="/api/v1/agent", tags=["conversational"])


@router.post("/chat", response_model=ChatResponse)
async def chat_with_agent(
    request: ChatRequest,
    llm_provider: LLMProvider = Depends(get_llm_provider),
    tool_executor: ToolExecutor = Depends(get_tool_executor),
    _: str = Depends(verify_api_key),
) -> ChatResponse:
    """Natural language inquiry interface backed by authoritative tools and Gemini."""
    return await llm_provider.chat(request, tool_executor)


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    event_manager: EventContextManager = Depends(get_event_manager),
    audit_service: AuditService = Depends(get_audit_service),
    _: str = Depends(verify_api_key),
) -> FeedbackResponse:
    """Submit human operator feedback on alerts, recommendations, or analyses."""
    context = event_manager.get_context(request.event_id)
    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event '{request.event_id}' not found",
        )

    feedback_id = str(uuid.uuid4())
    context.record_feedback(request.model_dump(mode="json"))

    await audit_service.record(
        action="OPERATOR_FEEDBACK",
        entity_type=request.target_type,
        entity_id=request.target_id,
        event_id=request.event_id,
        performed_by=request.submitted_by,
        new_value={"feedback": request.feedback, "comment": request.comment},
    )

    return FeedbackResponse(
        id=feedback_id,
        received=True,
        timestamp=datetime.now(timezone.utc),
    )
