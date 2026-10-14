"""Structured JSON logging with correlation ids and secret redaction."""
import logging
import re
import sys

import structlog

from app.core.context import correlation_id_var

_SECRET_KEYS = re.compile(r"(token|secret|password|authorization|api_key|refresh|code_verifier)", re.I)


def _add_correlation_id(_, __, event_dict):
    event_dict.setdefault("correlation_id", correlation_id_var.get())
    return event_dict


def _redact(_, __, event_dict):
    for key in list(event_dict.keys()):
        if _SECRET_KEYS.search(key) and key != "event":
            event_dict[key] = "***redacted***"
    return event_dict


def configure_logging(level: str = "INFO", json_logs: bool = True, stream=None) -> None:
    stream = stream or sys.stdout
    logging.basicConfig(format="%(message)s", stream=stream, level=level.upper())
    renderer = structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_correlation_id,
            _redact,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(file=stream),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "sfai"):
    return structlog.get_logger(name)
