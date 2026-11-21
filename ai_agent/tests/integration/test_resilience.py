"""Integration tests for error resilience, offline LLM fallback, and graceful degradation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from app.dependencies import get_llm_provider
from app.schemas.models import ChatRequest


@pytest.mark.asyncio
async def test_offline_llm_graceful_degradation(registered_event: str):
    """When LLM is unconfigured, chat continues serving deterministic answers without errors."""
    provider = get_llm_provider()
    provider.is_connected = False  # simulate offline or unconfigured LLM

    from app.dependencies import get_tool_executor
    executor = get_tool_executor()

    req = ChatRequest(
        event_id=registered_event,
        message="Which area is currently most crowded?",
    )
    response = await provider.chat(req, executor)

    assert response.response is not None
    assert len(response.response) > 0
    assert "most crowded" in response.response.lower() or "area" in response.response.lower()


@pytest.mark.asyncio
async def test_invalid_negative_counts_rejected(async_client: AsyncClient, registered_event: str):
    """Analytics with negative people counts must be rejected by validation."""
    payload = {
        "data": [
            {
                "event_id": registered_event,
                "venue_id": "venue_01",
                "zone_id": "main_stage",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "people_count": -50,  # Invalid
            }
        ]
    }
    # Pydantic schema validation returns 422
    res = await async_client.post("/api/v1/agent/analyze", json=payload)
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_message_idempotency(async_client: AsyncClient, registered_event: str):
    """Identical message IDs sent consecutively must be recognized as duplicates."""
    msg_id = "test_msg_unique_12345"
    payload = {
        "data": [
            {
                "event_id": registered_event,
                "venue_id": "venue_01",
                "zone_id": "main_stage",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "people_count": 200,
                "message_id": msg_id,
            }
        ]
    }

    # First send
    res1 = await async_client.post("/api/v1/agent/analyze", json=payload)
    assert res1.status_code == 200
    assert res1.json()["accepted"] == 1

    # Immediate second send with same message_id
    res2 = await async_client.post("/api/v1/agent/analyze", json=payload)
    assert res2.status_code == 200
    assert res2.json()["duplicates_skipped"] == 1
