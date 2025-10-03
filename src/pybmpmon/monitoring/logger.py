"""Structured logging configuration using structlog."""

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from pybmpmon.config import settings


def add_log_level(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add log level to event dict."""
    event_dict["level"] = method_name.upper()
    return event_dict


def configure_logging() -> structlog.BoundLogger:
    """
    Configure structured logging with JSON output to stdout.

    When Sentry is enabled via sentry_helper functions:
    - TRACE/DEBUG: Not sent to Sentry (local only)
    - INFO: Captured as breadcrumbs only (provides context for errors)
    - WARNING: Sent as Sentry events (not issues)
    - ERROR/FATAL: Sent as Sentry issues

    Use sentry_helper.log_*() functions for dual logging (stdout + Sentry).
    Use structlog logger directly for stdout-only logging.
    Use sentry_helper.get_sentry_logger() for direct Sentry SDK logger access.
    """
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Initialize Sentry integration first (before configuring logging)
    # This ensures Sentry's LoggingIntegration can intercept all logs
    from pybmpmon.monitoring.sentry_helper import init_sentry

    sentry_enabled = init_sentry()

    # Configure standard library logging
    # Sentry's LoggingIntegration will intercept logs at this level
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Configure structlog
    # structlog logs will be passed to stdlib logging, which Sentry intercepts
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logger = structlog.get_logger()
    if sentry_enabled:
        logger.info("sentry_logging_enabled",
                    breadcrumbs="INFO+",
                    events="WARNING+",
                    issues="ERROR+")

    return logger  # type: ignore[no-any-return]


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    """
    Get a logger instance for a specific module.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return structlog.get_logger(name)  # type: ignore[no-any-return]


# Global logger instance
logger = configure_logging()
