"""Async client for communicating with the CrowdVision AI Agent (port 8100)."""
from __future__ import annotations

from typing import Any, Optional

import httpx

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger("integrations.agent_client")


class AIAgentClient:
    """Async client for communicating with the CrowdVision AI Agent (port 8100)."""

    def __init__(self):
        self._registered_events: set[str] = set()

    def _headers(self) -> dict[str, str]:
        settings = get_settings()
        headers = {"Content-Type": "application/json"}
        if settings.ai_agent_api_key:
            headers["X-API-Key"] = settings.ai_agent_api_key
        return headers

    def _base_url(self) -> str:
        settings = get_settings()
        return (getattr(settings, "ai_agent_url", None) or getattr(settings, "ai_agent_base_url", "http://localhost:8001")).rstrip("/")

    def _timeout(self) -> float:
        return get_settings().ai_agent_timeout_seconds

    def _enabled(self) -> bool:
        return get_settings().ai_agent_enabled

    def _client(self, timeout: Optional[float] = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout or self._timeout(), trust_env=False)

    async def get_health(self) -> dict[str, Any]:
        if not self._enabled():
            return {"status": "DISABLED", "detail": "AI Agent integration is disabled in settings"}
        try:
            async with self._client(timeout=3.0) as client:
                resp = await client.get(f"{self._base_url()}/health", headers=self._headers())
                if resp.status_code == 200:
                    return resp.json()
                return {"status": "UNHEALTHY", "status_code": resp.status_code}
        except Exception as exc:
            logger.warning("AI Agent health check failed", error=str(exc))
            return {"status": "UNREACHABLE", "error": str(exc)}

    async def register_event(
        self,
        event_id: str,
        event_name: str,
        venue_id: str,
        venue_name: str,
        zones: list[dict[str, Any]],
        total_capacity: int,
    ) -> Optional[dict[str, Any]]:
        if not self._enabled():
            return None

        payload = {
            "event_id": event_id,
            "event_name": event_name,
            "venue": {
                "venue_id": venue_id,
                "venue_name": venue_name,
                "total_capacity": total_capacity,
                "zones": zones,
            },
        }

        try:
            async with self._client() as client:
                resp = await client.post(
                    f"{self._base_url()}/api/v1/agent/events",
                    json=payload,
                    headers=self._headers(),
                )
                if resp.status_code in (200, 201):
                    self._registered_events.add(event_id)
                    return resp.json()
                logger.warning(
                    "AI Agent event registration failed", status_code=resp.status_code, text=resp.text
                )
                return None
        except Exception as exc:
            logger.warning("AI Agent event registration failed", error=str(exc))
            return None

    async def send_analytics(
        self,
        event_id: str,
        video_timestamp_sec: float,
        zones_data: list[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        if not self._enabled():
            return None

        payload = {
            "event_id": event_id,
            "video_timestamp_sec": video_timestamp_sec,
            "zones": zones_data,
        }

        try:
            async with self._client() as client:
                resp = await client.post(
                    f"{self._base_url()}/api/v1/agent/analytics",
                    json=payload,
                    headers=self._headers(),
                )
                if resp.status_code in (200, 201):
                    return resp.json()
                logger.warning("AI Agent analytics ingest failed", status_code=resp.status_code)
                return None
        except Exception as exc:
            logger.warning("AI Agent analytics ingest failed", error=str(exc))
            return None

    async def chat(
        self,
        event_id: str,
        message: str,
        session_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        if not self._enabled():
            return None

        payload: dict[str, Any] = {
            "event_id": event_id,
            "message": message,
        }
        if session_id:
            payload["session_id"] = session_id
        if context:
            payload["context"] = context

        try:
            # allow longer timeout for LLM inference
            async with self._client(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._base_url()}/api/v1/agent/chat",
                    json=payload,
                    headers=self._headers(),
                )
                if resp.status_code == 200:
                    return resp.json()
                logger.warning("AI Agent /chat returned non-200", status_code=resp.status_code)
                return None
        except Exception as exc:
            logger.warning("AI Agent /chat request failed", error=str(exc))
            return None

    async def get_recommendations(self, event_id: str) -> Optional[list[dict[str, Any]]]:
        if not self._enabled():
            return None

        try:
            async with self._client() as client:
                resp = await client.get(
                    f"{self._base_url()}/api/v1/agent/recommendations/{event_id}",
                    headers=self._headers(),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data if isinstance(data, list) else data.get("recommendations", [])
                logger.warning("AI Agent /recommendations returned non-200", status_code=resp.status_code)
                return None
        except Exception as exc:
            logger.warning("AI Agent /recommendations failed", error=str(exc))
            return None

    def is_event_registered(self, event_id: str) -> bool:
        return event_id in self._registered_events
