"""
Structured JSON Logging
=======================

All log output is structured JSON for machine-parseable audit trails.
Correlation IDs are automatically injected into every log entry.
No external log shipping — all output goes to local streams/files only.

Uses structlog for structured logging with stdlib integration.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.core.correlation import get_correlation_id, get_sub_correlation_ids


def _add_correlation_id(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Structlog processor: inject correlation ID into every log entry."""
    correlation_id = get_correlation_id()
    if correlation_id:
        event_dict["correlation_id"] = correlation_id
    sub_ids = get_sub_correlation_ids()
    if sub_ids:
        event_dict["sub_correlation_ids"] = sub_ids
    return event_dict


def _add_app_context(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Structlog processor: add application identity to every log entry."""
    event_dict["app"] = "isro-rag-framework"
    return event_dict


def configure_logging(log_level: str = "INFO") -> None:
    """
    Configure structured JSON logging for the application.

    Must be called once during application startup (in main.py).
    All output goes to stdout — no external log shipping.
    """
    # Configure stdlib logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _add_correlation_id,
            _add_app_context,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a named structured logger.

    Usage:
        logger = get_logger(__name__)
        logger.info("query_received", query_id="abc-123", user="user42")
    """
    return structlog.get_logger(name)
