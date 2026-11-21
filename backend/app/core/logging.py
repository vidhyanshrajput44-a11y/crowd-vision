"""Structured logging for CrowdVision Main Backend."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """Formats log records as JSON lines with standardized fields."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            log_obj.update(record.extra_fields)
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


class StructuredLogger(logging.LoggerAdapter):
    """Adapter allowing keyword arguments to be embedded in structured log output."""

    def process(self, msg: Any, kwargs: Any) -> tuple[Any, Any]:
        extra = kwargs.get("extra", {})
        extra_fields = {k: v for k, v in kwargs.items() if k not in ("extra", "exc_info", "stack_info")}
        extra["extra_fields"] = extra_fields
        for k in extra_fields:
            kwargs.pop(k, None)
        kwargs["extra"] = extra
        return msg, kwargs


def setup_logging(log_level: str = "INFO", json_logs: bool = False) -> None:
    """Configure root logger with appropriate formatter."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    if json_logs:
        handler.setFormatter(JSONFormatter())
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)

    root.addHandler(handler)


def get_logger(name: str = "crowdvision") -> StructuredLogger:
    """Return a structured logger adapter."""
    return StructuredLogger(logging.getLogger(name), {})
