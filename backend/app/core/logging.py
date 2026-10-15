"""Structured logging with secret redaction."""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

_SENSITIVE_KEYS = re.compile(r"(password|secret|token|api_key|authorization|cookie|csrf)", re.I)
_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9\-_.]+")
_OPENAI_KEY = re.compile(r"sk-[A-Za-z0-9\-_]{8,}")


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        value = _BEARER.sub(r"\1[REDACTED]", value)
        return _OPENAI_KEY.sub("[REDACTED]", value)
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if _SENSITIVE_KEYS.search(str(k)) else _redact_value(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_value(v) for v in value]
    return value


def redact_processor(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key in list(event_dict.keys()):
        if key == "event":
            event_dict[key] = _redact_value(event_dict[key])
        elif _SENSITIVE_KEYS.search(key):
            event_dict[key] = "[REDACTED]"
        else:
            event_dict[key] = _redact_value(event_dict[key])
    return event_dict


def configure_logging(level: str = "INFO", json_logs: bool = True) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    renderer: Any = structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_processor,  # type: ignore[list-item]
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "bidgenie") -> Any:
    return structlog.get_logger(name)
