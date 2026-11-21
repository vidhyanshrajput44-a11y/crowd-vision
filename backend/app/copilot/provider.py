"""Modular LLM Provider Architecture for CROWD VISION AI Copilot."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
import time
from typing import Any, Optional

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger("copilot.provider")

try:
    import google.generativeai as genai
    _GENAI_AVAILABLE = True
except ImportError:
    genai = None  # type: ignore
    _GENAI_AVAILABLE = False


class CircuitBreaker:
    """Circuit breaker preventing cascading LLM call failures."""

    def __init__(self, failure_threshold: int = 4, recovery_timeout_seconds: float = 45.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout_seconds
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    @property
    def is_open(self) -> bool:
        if self.state == "OPEN":
            if self.last_failure_time and (time.monotonic() - self.last_failure_time) > self.recovery_timeout:
                self.state = "HALF_OPEN"
                return False
            return True
        return False

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning("Copilot LLM Circuit Breaker tripped to OPEN", failures=self.failure_count)


class BaseLLMProvider:
    """Base interface for Copilot LLM providers."""

    name: str = "base"

    def is_available(self) -> bool:
        raise NotImplementedError

    async def generate_response(
        self,
        system_instruction: str,
        user_message: str,
        grounding_context: dict[str, Any],
    ) -> Optional[str]:
        raise NotImplementedError


class GeminiLLMProvider(BaseLLMProvider):
    """Google Gemini LLM provider integration with structured grounding."""

    name: str = "google_gemini"

    def __init__(self, api_key: str = "", model_name: str = "gemini-2.5-flash", timeout: float = 25.0) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model_name = model_name
        self.timeout = timeout
        self.circuit_breaker = CircuitBreaker()
        self._model = None
        self._initialized = False

    def is_available(self) -> bool:
        return bool(_GENAI_AVAILABLE and self.api_key and self.api_key not in ("CHANGE_ME", "YOUR_GEMINI_API_KEY"))

    def _ensure_init(self) -> bool:
        if self._initialized and self._model is not None:
            return True
        if not self.is_available():
            return False
        try:
            genai.configure(api_key=self.api_key)
            self._model = genai.GenerativeModel(model_name=self.model_name)
            self._initialized = True
            logger.info("Initialized Gemini Copilot provider", model=self.model_name)
            return True
        except Exception as exc:
            logger.error("Failed to initialize Gemini model", error=str(exc))
            self._initialized = False
            return False

    async def generate_response(
        self,
        system_instruction: str,
        user_message: str,
        grounding_context: dict[str, Any],
    ) -> Optional[str]:
        if not self._ensure_init() or self.circuit_breaker.is_open or not self._model:
            return None

        prompt = (
            f"SYSTEM INSTRUCTIONS:\n{system_instruction}\n\n"
            f"GROUNDING CONTEXT (Authoritative DB & Telemetry):\n"
            f"{grounding_context}\n\n"
            f"OPERATOR QUERY:\n{user_message}\n\n"
            f"Please respond as CROWD VISION AI Copilot. Answer factually based on the grounding context. "
            f"Never hallucinate numbers, zone IDs, or occupancy percentages. If an action is required, explicitly reference it."
        )

        loop = asyncio.get_running_loop()
        try:
            resp = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: self._model.generate_content(prompt)),
                timeout=self.timeout,
            )
            if resp and hasattr(resp, "text") and resp.text:
                self.circuit_breaker.record_success()
                return resp.text.strip()
            return None
        except Exception as exc:
            self.circuit_breaker.record_failure()
            logger.warning("Gemini generation call failed, falling back", error=str(exc))
            return None


class DeterministicGroundedProvider(BaseLLMProvider):
    """High-reliability deterministic spatial intelligence engine when LLM is unavailable."""

    name: str = "deterministic_grounded_engine"

    def is_available(self) -> bool:
        return True

    async def generate_response(
        self,
        system_instruction: str,
        user_message: str,
        grounding_context: dict[str, Any],
    ) -> Optional[str]:
        # Formulate grounded response based on context fields
        task = grounding_context.get("task", {})
        zones = grounding_context.get("zones", [])
        telemetry = grounding_context.get("telemetry", {})
        alerts = grounding_context.get("alerts", [])
        risks = grounding_context.get("risks", [])
        predictions = grounding_context.get("predictions", [])

        msg_lower = user_message.lower().strip()
        task_name = task.get("name", "Active Task")

        if any(w in msg_lower for w in ("risk", "danger", "critical", "safety", "hazard")):
            if risks:
                lines = [f"### Zone Risk Analysis for **{task_name}**:\n"]
                for r in risks:
                    lines.append(f"- **{r.get('zone_name')}**: Level `{r.get('risk_level')}` (Priority: `{r.get('monitoring_priority')}`). {r.get('reason')}")
                if alerts:
                    lines.append(f"\nThere are currently **{len(alerts)} active alerts** requiring attention.")
                return "\n".join(lines)
            return f"All monitored zones in **{task_name}** are currently evaluated as **NORMAL**. No elevated risk indicators detected."

        if any(w in msg_lower for w in ("predict", "forecast", "future", "trend", "horizon")):
            if predictions:
                lines = [f"### Short-Term Crowd Predictions for **{task_name}**:\n"]
                for p in predictions:
                    lines.append(
                        f"- **{p.get('zone_name')}** (+{p.get('horizon_seconds')}s): projected occupancy **{p.get('predicted_occupancy', 0):.0f} persons** "
                        f"({p.get('predicted_change_pct', 0.0):+.1f}%), trend **{p.get('estimated_trend')}**, category `{p.get('risk_category')}`."
                    )
                return "\n".join(lines)
            return f"No predictive horizon data has been generated yet for **{task_name}**. Start video analysis to generate real-time 30s/60s/180s/300s forecasts."

        if any(w in msg_lower for w in ("alert", "warning", "incident")):
            if alerts:
                lines = [f"### Active Alerts for **{task_name}** ({len(alerts)} active alerts):\n"]
                for a in alerts:
                    lines.append(f"- **[{a.get('severity')}] {a.get('title')}** ({a.get('zone_name')}): {a.get('description')}")
                return "\n".join(lines)
            return f"There are currently **no active unacknowledged alerts** for **{task_name}**. All parameters are within design limits."

        if any(w in msg_lower for w in ("zone", "layout", "capacity", "area")):
            if zones:
                lines = [f"### Spatial Zones & Capacities for **{task_name}**:\n"]
                tot_cap = 0
                for z in zones:
                    name = z.get("name") or z.get("zone_name") or "Zone"
                    cap = int(z.get("capacity") or z.get("max_capacity") or 0)
                    tot_cap += cap
                    ztype = z.get("zone_type", "GENERAL")
                    lines.append(f"- **{name}** ({ztype}): design capacity **{cap:,} persons**, warning threshold: {int(cap * 0.7)}, critical: {int(cap * 0.9)}.")
                lines.append(f"\nTotal venue design capacity across {len(zones)} zones is **{tot_cap:,} persons**.")
                return "\n".join(lines)
            return f"No spatial zones have been defined yet for **{task_name}**. Use the Spatial Layout Builder to create polygon boundaries."

        # Default comprehensive overview
        total_people = telemetry.get("total_people", 0)
        state = task.get("state", "UNKNOWN")
        lines = [
            f"### Copilot Overview: **{task_name}**\n",
            f"- **Lifecycle State:** `{state}`",
            f"- **Location:** {task.get('location', 'Unspecified Site')}",
            f"- **Monitored Zones:** {len(zones)} zones configured",
            f"- **Current Total Count:** {total_people} persons detected",
            f"- **Active Alerts:** {len(alerts)} unacknowledged alerts\n",
            "Ask me about specific zones, predictive density trends, active alerts, or propose capacity adjustments."
        ]
        return "\n".join(lines)


def get_llm_provider() -> BaseLLMProvider:
    """Resolve the appropriate active LLM provider based on environment and availability."""
    settings = get_settings()
    configured_provider = getattr(settings, "llm_provider", "auto").lower()

    gemini_key = getattr(settings, "gemini_api_key", "") or os.environ.get("GEMINI_API_KEY", "")
    if configured_provider in ("auto", "gemini", "google_gemini") and gemini_key:
        provider = GeminiLLMProvider(api_key=gemini_key, model_name=getattr(settings, "gemini_model", "gemini-2.5-flash"))
        if provider.is_available():
            return provider

    return DeterministicGroundedProvider()
