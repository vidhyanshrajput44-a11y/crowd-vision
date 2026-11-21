"""Tool definitions and schemas for CROWD VISION AI Copilot."""
from __future__ import annotations

from typing import Any

# Complete catalog of supported Copilot Tools with parameter specifications
COPILOT_TOOLS_CATALOG: list[dict[str, Any]] = [
    # ── Read-Only Query Tools ───────────────────────────────────────────────
    {
        "name": "get_active_task",
        "description": "Retrieve comprehensive configuration, lifecycle state, video source, and location for the active task.",
        "category": "read_only",
        "requires_confirmation": False,
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Unique identifier of the task"}
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "get_layout_zones",
        "description": "Inspect configured spatial zones, polygon boundaries, design capacities, and alert thresholds.",
        "category": "read_only",
        "requires_confirmation": False,
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Unique identifier of the task"}
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "get_latest_telemetry",
        "description": "Retrieve the latest real-time computer vision telemetry (headcounts, velocities, heatmap grid) for a task.",
        "category": "read_only",
        "requires_confirmation": False,
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Unique identifier of the task"}
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "get_zone_metrics",
        "description": "Retrieve detailed analytical metrics (occupancy ratio, inflow/outflow, speed, bottleneck status) for zones.",
        "category": "read_only",
        "requires_confirmation": False,
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Unique identifier of the task"},
                "zone_id": {"type": "string", "description": "Optional zone identifier to filter by"}
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "get_zone_risk",
        "description": "Retrieve current multi-factor risk assessments and contributing hazards for monitored zones.",
        "category": "read_only",
        "requires_confirmation": False,
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Unique identifier of the task"},
                "zone_id": {"type": "string", "description": "Optional zone filter"}
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "get_predictions",
        "description": "Retrieve predictive crowd forecasts across 30s, 60s, 180s, and 300s horizons.",
        "category": "read_only",
        "requires_confirmation": False,
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Unique identifier of the task"},
                "horizon_seconds": {"type": "integer", "description": "Forecast horizon (30, 60, 180, 300)"}
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "get_active_alerts",
        "description": "List current unacknowledged safety alerts and threshold breaches for the task.",
        "category": "read_only",
        "requires_confirmation": False,
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Unique identifier of the task"},
                "severity": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"], "description": "Optional severity filter"}
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "get_task_history",
        "description": "Retrieve chronological audit log of task lifecycle state transitions and operator actions.",
        "category": "read_only",
        "requires_confirmation": False,
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Unique identifier of the task"},
                "limit": {"type": "integer", "description": "Maximum number of history events to retrieve", "default": 20}
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "get_system_health",
        "description": "Inspect underlying system status including database connectivity, CV detector backend, and active pipelines.",
        "category": "read_only",
        "requires_confirmation": False,
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },

    # ── Action Tools (Require Confirmation Policy) ──────────────────────────
    {
        "name": "adjust_zone_capacity",
        "description": "Propose updating the design maximum occupancy capacity for a spatial zone and re-calibrating thresholds.",
        "category": "action",
        "requires_confirmation": True,
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Target task identifier"},
                "zone_id": {"type": "string", "description": "Zone identifier to update"},
                "new_capacity": {"type": "integer", "description": "New maximum design capacity (positive integer)"}
            },
            "required": ["task_id", "zone_id", "new_capacity"],
        },
    },
    {
        "name": "transition_task_state",
        "description": "Propose transitioning the lifecycle state of a task (e.g., READY, PROCESSING, PAUSED, COMPLETED).",
        "category": "action",
        "requires_confirmation": True,
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Target task identifier"},
                "new_state": {"type": "string", "enum": ["DRAFT", "CONFIGURING", "READY", "PROCESSING", "LIVE", "PAUSED", "COMPLETED"], "description": "Target state"},
                "reason": {"type": "string", "description": "Operational rationale for the transition"}
            },
            "required": ["task_id", "new_state"],
        },
    },
    {
        "name": "start_task_analysis",
        "description": "Propose launching asynchronous computer vision video analysis on the configured video source.",
        "category": "action",
        "requires_confirmation": True,
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Target task identifier"},
                "sample_fps": {"type": "number", "description": "Sampling FPS rate", "default": 2.0}
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "pause_task_analysis",
        "description": "Propose pausing the active computer vision analysis pipeline for a task.",
        "category": "action",
        "requires_confirmation": True,
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Target task identifier"}
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "resume_task_analysis",
        "description": "Propose resuming paused computer vision analysis for a task.",
        "category": "action",
        "requires_confirmation": True,
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Target task identifier"}
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "stop_task_analysis",
        "description": "Propose stopping and terminating the computer vision analysis job for a task.",
        "category": "action",
        "requires_confirmation": True,
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Target task identifier"}
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "acknowledge_alert",
        "description": "Acknowledge an active safety alert with operator attribution and notes.",
        "category": "action",
        "requires_confirmation": True,
        "parameters": {
            "type": "object",
            "properties": {
                "alert_id": {"type": "string", "description": "Alert identifier"},
                "note": {"type": "string", "description": "Operator acknowledgement note"}
            },
            "required": ["alert_id"],
        },
    },
    {
        "name": "resolve_alert",
        "description": "Resolve an active safety alert marking the condition as mitigated.",
        "category": "action",
        "requires_confirmation": True,
        "parameters": {
            "type": "object",
            "properties": {
                "alert_id": {"type": "string", "description": "Alert identifier"},
                "resolution_note": {"type": "string", "description": "Mitigation explanation"}
            },
            "required": ["alert_id"],
        },
    },
    {
        "name": "generate_incident_report",
        "description": "Generate and persist an official executive incident summary report for the task.",
        "category": "action",
        "requires_confirmation": True,
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Target task identifier"},
                "title": {"type": "string", "description": "Report title"}
            },
            "required": ["task_id"],
        },
    },
]


def get_all_tools() -> list[dict[str, Any]]:
    """Return complete list of copilot tool definitions."""
    return COPILOT_TOOLS_CATALOG


def get_tool_definition(tool_name: str) -> dict[str, Any] | None:
    """Find tool definition by name."""
    for t in COPILOT_TOOLS_CATALOG:
        if t["name"] == tool_name:
            return t
    return None
