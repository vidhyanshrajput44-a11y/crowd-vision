"""Tool definitions for LLM structured tool calling."""

from __future__ import annotations

from typing import Any

# OpenAPI / JSON-schema style tool definitions for function calling
AGENT_TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "get_zone_status",
        "description": "Retrieve current occupancy, people count, density, and flow velocity for a specific zone.",
        "parameters": {
            "type": "object",
            "properties": {
                "zone_id": {
                    "type": "string",
                    "description": "Identifier of the zone (e.g. 'main_stage', 'entrance_a')",
                }
            },
            "required": ["zone_id"],
        },
    },
    {
        "name": "get_all_zones_summary",
        "description": "Retrieve high-level summary of all monitored zones including people count, occupancy percentage, and risk level.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_zone_risk",
        "description": "Retrieve detailed multi-factor risk assessment and contributing risk factors for a specific zone.",
        "parameters": {
            "type": "object",
            "properties": {
                "zone_id": {
                    "type": "string",
                    "description": "Zone identifier",
                }
            },
            "required": ["zone_id"],
        },
    },
    {
        "name": "get_zone_prediction",
        "description": "Retrieve predictive crowd forecast and projected growth trend for a zone.",
        "parameters": {
            "type": "object",
            "properties": {
                "zone_id": {
                    "type": "string",
                    "description": "Zone identifier",
                },
                "horizon_minutes": {
                    "type": "integer",
                    "description": "Forecast horizon in minutes (e.g. 1, 3, 5)",
                },
            },
            "required": ["zone_id"],
        },
    },
    {
        "name": "get_active_alerts",
        "description": "List current unresolved alerts, optionally filtered by zone or severity priority.",
        "parameters": {
            "type": "object",
            "properties": {
                "zone_id": {
                    "type": "string",
                    "description": "Optional zone filter",
                },
                "priority": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                    "description": "Optional priority severity filter",
                },
            },
        },
    },
    {
        "name": "get_recommendations",
        "description": "Retrieve active context-aware crowd management recommendations.",
        "parameters": {
            "type": "object",
            "properties": {
                "zone_id": {
                    "type": "string",
                    "description": "Optional zone filter",
                }
            },
        },
    },
    {
        "name": "get_most_crowded_zone",
        "description": "Identify which venue zone currently exhibits the highest absolute people count and occupancy ratio.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_highest_risk_zone",
        "description": "Identify which venue zone currently possesses the highest operational risk classification.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "compare_current_vs_predicted",
        "description": "Perform comparative analysis between current measurements and model predictions across all zones.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_zones_with_increasing_inflow",
        "description": "Filter zones that are experiencing positive net inflow or accelerating arrival rates.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
]
