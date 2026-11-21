"""LLM provider integration with circuit breaker, retries, and offline fallback."""

from __future__ import annotations

import warnings
warnings.filterwarnings("ignore")

import asyncio
import time
from typing import Any, Optional

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.llm.prompts import SYSTEM_PROMPT
from app.llm.response_parser import ToolExecutor
from app.llm.tools import AGENT_TOOLS_SCHEMA
from app.monitoring.logger import get_logger
from app.schemas.models import ChatRequest, ChatResponse

logger = get_logger("llm.provider")

try:
    import google.generativeai as genai
    _GENAI_AVAILABLE = True
except ImportError:
    genai = None  # type: ignore
    _GENAI_AVAILABLE = False


class CircuitBreaker:
    """Protects against cascading external API failures."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout_seconds: float = 60.0) -> None:
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
            logger.warning("LLM Circuit Breaker tripped to OPEN", failure_count=self.failure_count)


class LLMProvider:
    """Async client for Conversational AI with Google Gemini and deterministic fallback."""

    def __init__(
        self,
        api_key: str = "",
        model_name: str = "gemini-2.5-flash",
        timeout: int = 30,
        max_retries: int = 3,
        enabled: bool = True,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.timeout = timeout
        self.max_retries = max_retries
        self.enabled = enabled
        self.circuit_breaker = CircuitBreaker()
        self.is_connected = False
        self._model = None

    async def initialize(self) -> bool:
        """Initialize Google Gemini client."""
        if not self.enabled:
            logger.info("LLM disabled via configuration; operating in deterministic fallback mode")
            return False

        if not self.api_key or self.api_key in ("YOUR_GEMINI_API_KEY", "CHANGE_ME"):
            logger.info("No Gemini API key supplied; operating in deterministic fallback mode")
            return False

        if not _GENAI_AVAILABLE:
            logger.warning("google-generativeai library not available; operating in fallback mode")
            return False

        try:
            genai.configure(api_key=self.api_key)
            self._model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=SYSTEM_PROMPT,
            )
            self.is_connected = True
            logger.info("Initialized Gemini LLM provider", model=self.model_name)
            return True
        except Exception as exc:
            logger.warning("Failed to initialize Gemini client; operating in fallback mode", error=str(exc))
            self.is_connected = False
            return False

    async def chat(
        self,
        request: ChatRequest,
        tool_executor: ToolExecutor,
    ) -> ChatResponse:
        """Process conversational user inquiry using tools and contextual reasoning."""
        context = tool_executor.orchestrator.event_context_manager.get_context(request.event_id)
        if not context:
            return ChatResponse(
                session_id=request.session_id,
                response=f"Event '{request.event_id}' is not registered or currently active.",
                tool_calls_made=[],
                data_sources=[],
                is_data_stale=True,
                stale_warning="Event context unavailable",
            )

        # 1. Deterministic Intent Routing (always runs first or as resilient fallback)
        intent, tool_name, tool_args = self._classify_intent(request.message, context)

        tool_calls_made = []
        data_sources = []
        tool_output: dict[str, Any] = {}

        if tool_name:
            tool_calls_made.append(f"{tool_name}({tool_args})")
            tool_output = await tool_executor.execute_tool(tool_name, tool_args, request.event_id)
            data_sources.append(tool_name)

        # If LLM is available and circuit breaker is closed, formulate response via Gemini
        if self.is_connected and not self.circuit_breaker.is_open and self._model:
            try:
                llm_response = await self._query_gemini(
                    user_message=request.message,
                    tool_data=tool_output,
                    context=context,
                )
                if llm_response:
                    self.circuit_breaker.record_success()
                    return ChatResponse(
                        session_id=request.session_id,
                        response=llm_response,
                        tool_calls_made=tool_calls_made,
                        data_sources=data_sources,
                        is_data_stale=context.is_data_stale,
                        stale_warning="Warning: Live crowd analytics are over 60 seconds old" if context.is_data_stale else None,
                    )
            except Exception as exc:
                self.circuit_breaker.record_failure()
                logger.error("LLM generation failed, falling back to deterministic response", error=str(exc))

        # 2. Resilient Deterministic Fallback Response
        fallback_text = self._build_deterministic_response(
            intent=intent,
            tool_name=tool_name,
            tool_data=tool_output,
            context=context,
        )

        return ChatResponse(
            session_id=request.session_id,
            response=fallback_text,
            tool_calls_made=tool_calls_made,
            data_sources=data_sources,
            is_data_stale=context.is_data_stale,
            stale_warning="Warning: Live crowd analytics are over 60 seconds old" if context.is_data_stale else None,
        )

    def _classify_intent(self, message: str, context: EventContext) -> tuple[str, Optional[str], dict[str, Any]]:
        """Map user natural language inquiry to corresponding authoritative tool."""
        msg_lower = message.lower()

        # Check for specific zone mention
        target_zone_id = None
        for z in context.venue.zones:
            if z.zone_id.lower() in msg_lower or z.zone_name.lower() in msg_lower:
                target_zone_id = z.zone_id
                break

        if "most crowded" in msg_lower or "highest crowd" in msg_lower or "busiest" in msg_lower:
            return "most_crowded", "get_most_crowded_zone", {}

        elif "highest risk" in msg_lower or "most dangerous" in msg_lower or "most critical" in msg_lower:
            return "highest_risk", "get_highest_risk_zone", {}

        elif "alert" in msg_lower or "unresolved" in msg_lower or "warning" in msg_lower:
            return "alerts", "get_active_alerts", {"zone_id": target_zone_id}

        elif "recommend" in msg_lower or "action" in msg_lower or "what should we do" in msg_lower:
            return "recommendations", "get_recommendations", {"zone_id": target_zone_id}

        elif "compare" in msg_lower or "predict vs current" in msg_lower or "current vs predicted" in msg_lower:
            return "compare", "compare_current_vs_predicted", {}

        elif "inflow" in msg_lower or "entering" in msg_lower or "increasing" in msg_lower:
            return "inflow", "get_zones_with_increasing_inflow", {}

        elif target_zone_id:
            if "predict" in msg_lower or "forecast" in msg_lower or "minute" in msg_lower:
                return "prediction", "get_zone_prediction", {"zone_id": target_zone_id}
            elif "risk" in msg_lower or "why" in msg_lower or "flagged" in msg_lower:
                return "risk", "get_zone_risk", {"zone_id": target_zone_id}
            else:
                return "status", "get_zone_status", {"zone_id": target_zone_id}

        # Default overview
        return "all_zones", "get_all_zones_summary", {}

    def _build_deterministic_response(
        self,
        intent: str,
        tool_name: Optional[str],
        tool_data: dict[str, Any],
        context: EventContext,
    ) -> str:
        """Compose structured natural language response from verified tool output."""
        stale_prefix = "[STALE DATA WARNING: Analytics have not updated in >60s]\n\n" if context.is_data_stale else ""

        if intent == "most_crowded":
            zname = tool_data.get("zone_name", "Unknown")
            count = tool_data.get("people_count", 0)
            occ = tool_data.get("occupancy_pct", 0)
            return (
                f"{stale_prefix}The most crowded area is currently **{zname}** with **{count} people** "
                f"({occ}% of capacity)."
            )

        elif intent == "highest_risk":
            zname = tool_data.get("zone_name", "Unknown")
            level = tool_data.get("risk_level", "NORMAL")
            expl = tool_data.get("explanation", "Nominal conditions.")
            return (
                f"{stale_prefix}The highest risk area is **{zname}** currently evaluated at **{level}** risk.\n"
                f"Assessment rationale: {expl}"
            )

        elif intent == "alerts":
            alerts = tool_data.get("alerts", [])
            if not alerts:
                return f"{stale_prefix}There are currently **no active unacknowledged high-priority alerts** for this event."
            lines = [f"{stale_prefix}There are **{len(alerts)} active alerts**:"]
            for a in alerts[:5]:
                lines.append(f"- **[{a.get('priority')}] {a.get('title')}**: {a.get('description')}")
            return "\n".join(lines)

        elif intent == "recommendations":
            recs = tool_data.get("recommendations", [])
            if not recs:
                return f"{stale_prefix}No active operational interventions currently flagged. Conditions remain within normal parameters."
            lines = [f"{stale_prefix}Active operational recommendations:"]
            for r in recs[:4]:
                approval = "*(Human Approval Required)*" if r.get("requires_human_approval") else "*(Routine SOP)*"
                lines.append(f"- **[{r.get('priority')}] {r.get('action')}** for {r.get('affected_zone_name')}: {r.get('reason')} {approval}")
            return "\n".join(lines)

        elif intent == "compare":
            comparisons = tool_data.get("comparisons", [])
            lines = [f"{stale_prefix}Current vs Predicted Crowd Density:"]
            for c in comparisons:
                pred = f"{c.get('predicted_occupancy_pct')}%" if c.get("predicted_occupancy_pct") is not None else "N/A"
                lines.append(f"- **{c.get('zone_name')}**: Current: {c.get('current_occupancy_pct')}% | Predicted: {pred}")
            lines.append("\n*(Note: Predictions represent short-term probabilistic forecasts)*")
            return "\n".join(lines)

        elif intent == "inflow":
            zones = tool_data.get("increasing_zones", [])
            if not zones:
                return f"{stale_prefix}No zones currently exhibit accelerating positive net inflow."
            lines = [f"{stale_prefix}Zones with positive net inflow:"]
            for z in zones:
                lines.append(f"- **{z.get('zone_name')}**: Inflow {z.get('inflow_rate')}/min vs Outflow {z.get('outflow_rate')}/min (Net: +{z.get('net_inflow')}/min)")
            return "\n".join(lines)

        elif intent == "risk":
            zname = tool_data.get("zone_name", "Zone")
            level = tool_data.get("risk_level", "NORMAL")
            expl = tool_data.get("explanation", "Nominal conditions.")
            return f"{stale_prefix}**{zname}** Risk Level: **{level}**.\nRationale: {expl}"

        elif intent == "prediction":
            preds = tool_data.get("predictions", [])
            zname = tool_data.get("zone_name", "Zone")
            if not preds:
                return f"{stale_prefix}No predictive model output currently available for {zname}."
            lines = [f"{stale_prefix}Forecast for **{zname}**:"]
            for p in preds:
                lines.append(f"- +{p.get('forecast_horizon_seconds', 0)//60}m projection: {p.get('explanation')}")
            return "\n".join(lines)

        elif intent == "status":
            zname = tool_data.get("zone_name", "Zone")
            count = tool_data.get("people_count", 0)
            occ = tool_data.get("occupancy_pct", 0)
            inflow = tool_data.get("inflow_rate", 0)
            return f"{stale_prefix}**{zname}**: {count} people ({occ}% occupancy). Inflow rate: {inflow}/min."

        else:
            zones = tool_data.get("zones", [])
            lines = [f"{stale_prefix}Venue Status Overview ({context.event_name}):"]
            for z in zones:
                lines.append(f"- **{z.get('zone_name')}**: {z.get('people_count')} people ({z.get('occupancy_pct')}%) | Risk: {z.get('risk_level')}")
            return "\n".join(lines)

    async def _query_gemini(
        self,
        user_message: str,
        tool_data: dict[str, Any],
        context: EventContext,
    ) -> Optional[str]:
        """Call Gemini model asynchronously with timeout and structured tools context."""
        prompt = (
            f"Event Context: {context.event_name} (ID: {context.event_id})\n"
            f"Data Stale: {context.is_data_stale} (seconds since update: {context.seconds_since_last_update:.1f})\n"
            f"Authoritative Application Tool Result:\n{tool_data}\n\n"
            f"User Question: {user_message}\n\n"
            "Formulate an objective, precise, and professional response using ONLY the provided authoritative data. "
            "Never invent measurements. If data is stale, state it clearly. Explicitly mention when human approval is required."
        )

        loop = asyncio.get_running_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: self._model.generate_content(prompt)),
            timeout=self.timeout,
        )
        return response.text if response and hasattr(response, "text") else None
