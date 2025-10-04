"""Sentry integration helper functions.

This module provides unified logging that sends messages to both stdout (via structlog)
and Sentry (via sentry_sdk.logger).

Usage:
    from pybmpmon.monitoring.sentry_helper import (
        log_peer_up_event,
        log_peer_down_event,
        log_parse_error,
        log_route_processing_error,
        log_database_error,
        capture_parse_error,
        capture_peer_up_event,
        capture_peer_down_event,
        get_sentry_logger,
        get_sentry_sdk,
    )

    # Log peer events (INFO level -> breadcrumbs only)
    log_peer_up_event(peer_ip="192.0.2.1", bgp_peer="192.0.2.100", bgp_peer_asn=65001)

    # Log peer down (WARNING level -> Sentry events, not issues)
    log_peer_down_event(peer_ip="192.0.2.1", reason=1)

    # Log errors (ERROR level -> Sentry issues)
    log_parse_error(
        error_type="bmp_parse_error",
        peer_ip="192.0.2.1",
        error_message="Invalid message",
        data_hex="0300000006"
    )

    # Log critical database errors (FATAL level -> critical Sentry issues)
    log_database_error(
        operation="COPY",
        error_message="Connection pool exhausted",
        table="route_updates",
        row_count=1000
    )

    # Direct access to Sentry logger (advanced usage)
    sentry_logger = get_sentry_logger()
    if sentry_logger:
        sentry_logger.info("Custom message {var}", var=123)
        sentry_logger.warning(
            "Rate limit reached for {endpoint}", endpoint="/api/results/"
        )
        sentry_logger.error(
            "Failed to process payment. Order: {order_id}", order_id="or_2342"
        )

Sentry Level Mapping:
    - trace(), debug(): Not sent to Sentry (local only)
    - info(): Sent as breadcrumbs only (provides context for errors)
    - warning(): Sent as Sentry events (not issues)
    - error(), fatal(): Sent as Sentry issues
"""

import logging
from typing import Any

import structlog

from pybmpmon.config import settings

logger = structlog.get_logger(__name__)

# Track if Sentry is enabled
_sentry_enabled = False
_sentry_sdk = None
_sentry_logger = None


def init_sentry() -> bool:
    """
    Initialize Sentry SDK if configured.

    Logging integration:
    - TRACE and DEBUG: Not sent to Sentry (local only)
    - INFO and above: Captured as breadcrumbs (provides context for errors)
    - WARNING and above: Sent as events to Sentry (not issues)
    - ERROR and above: Sent as issues to Sentry

    Returns:
        True if Sentry was initialized, False otherwise
    """
    global _sentry_enabled, _sentry_sdk, _sentry_logger

    if not settings.sentry_dsn:
        logger.debug("sentry_disabled")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration

        _sentry_sdk = sentry_sdk
        # Use the regular structlog logger - LoggingIntegration handles Sentry
        _sentry_logger = logger

        # Configure logging integration:
        # - level=INFO: Capture INFO+ logs as breadcrumbs (context)
        # - event_level=logging.WARNING: Send WARNING+ logs as events
        # Note: Only ERROR+ become issues in Sentry UI
        sentry_logging = LoggingIntegration(
            level=logging.INFO,  # Breadcrumbs from INFO level
            event_level=logging.WARNING,  # Events from WARNING level
        )

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_environment,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            integrations=[sentry_logging],
            max_breadcrumbs=100,
        )

        _sentry_enabled = True
        logger.info("sentry_initialized", environment=settings.sentry_environment)
        return True

    except ImportError:
        logger.warning("sentry_sdk_not_installed", sentry_dsn=settings.sentry_dsn)
        return False


def is_sentry_enabled() -> bool:
    """
    Check if Sentry is enabled.

    Returns:
        True if Sentry is enabled
    """
    return _sentry_enabled


def get_sentry_logger() -> Any:
    """
    Get Sentry logger instance for direct logging.

    Returns sentry_sdk.logger which sends:
    - trace(), debug(): Not sent to Sentry (local only)
    - info(): Sent as breadcrumbs only
    - warning(): Sent as Sentry events (not issues)
    - error(), fatal(): Sent as Sentry issues

    Returns:
        Sentry logger instance or None if Sentry not enabled
    """
    return _sentry_logger if _sentry_enabled else None


def get_sentry_sdk() -> Any:
    """
    Get Sentry SDK instance for direct use (spans, transactions, etc.).

    Returns:
        Sentry SDK instance or None if Sentry not enabled
    """
    return _sentry_sdk if _sentry_enabled else None


def log_peer_up_event(peer_ip: str, bgp_peer: str, bgp_peer_asn: int) -> None:
    """
    Log BMP peer up event to both stdout and Sentry.

    INFO level events are sent to Sentry as breadcrumbs (not issues).
    Use this for informational events that provide context.

    Args:
        peer_ip: BMP peer IP address
        bgp_peer: BGP peer IP address
        bgp_peer_asn: BGP peer ASN
    """
    # Always log to stdout via structlog
    logger.info(
        "peer_up",
        bmp_peer=peer_ip,
        bgp_peer=bgp_peer,
        bgp_peer_asn=bgp_peer_asn,
    )

    # Send to Sentry as breadcrumb only (if enabled)
    if _sentry_logger:
        msg = (
            "BMP peer {peer_ip} established session with "
            "BGP peer {bgp_peer} (AS{bgp_peer_asn})"
        )
        _sentry_logger.info(
            msg,
            peer_ip=peer_ip,
            bgp_peer=bgp_peer,
            bgp_peer_asn=bgp_peer_asn,
        )


def log_peer_down_event(peer_ip: str, reason: int) -> None:
    """
    Log BMP peer down event to both stdout and Sentry.

    WARNING level events are sent to Sentry as events (not issues).
    Use this for noteworthy events that aren't errors.

    Args:
        peer_ip: BMP peer IP address
        reason: Peer down reason code
    """
    # Always log to stdout via structlog
    logger.warning(
        "peer_down",
        bmp_peer=peer_ip,
        reason_code=reason,
    )

    # Send to Sentry as warning event (if enabled)
    if _sentry_logger:
        _sentry_logger.warning(
            "BMP peer {peer_ip} disconnected (reason code: {reason_code})",
            peer_ip=peer_ip,
            reason_code=reason,
        )


def log_parse_error(
    error_type: str,
    peer_ip: str,
    error_message: str,
    data_hex: str | None = None,
) -> None:
    """
    Log parse error to both stdout and Sentry.

    ERROR level events are sent to Sentry as issues.
    Use this for actual errors that need attention.

    Args:
        error_type: Type of error (bmp_parse_error, bgp_parse_error, etc.)
        peer_ip: BMP peer IP address
        error_message: Error message
        data_hex: Hex dump of problematic data (optional)
    """
    # Always log to stdout via structlog
    log_data = {
        "error_type": error_type,
        "peer_ip": peer_ip,
        "error": error_message,
    }
    if data_hex:
        # Truncate hex data (first 256 chars for stdout)
        log_data["data_hex"] = data_hex[:256]

    logger.error("parse_error", **log_data)

    # Send to Sentry as error issue (if enabled)
    if _sentry_logger:
        _sentry_logger.error(
            "{error_type} from {peer_ip}: {error_message}",
            error_type=error_type,
            peer_ip=peer_ip,
            error_message=error_message,
            data_hex=data_hex[:512] if data_hex else None,
        )


def log_route_processing_error(
    peer_ip: str,
    error_message: str,
    route_count: int | None = None,
) -> None:
    """
    Log route processing error to both stdout and Sentry.

    ERROR level events are sent to Sentry as issues.
    Use this for route processing failures.

    Args:
        peer_ip: BMP peer IP address
        error_message: Error message
        route_count: Number of routes being processed (optional)
    """
    # Always log to stdout via structlog
    log_data: dict[str, Any] = {
        "peer_ip": peer_ip,
        "error": error_message,
    }
    if route_count is not None:
        log_data["route_count"] = route_count

    logger.error("route_processing_error", **log_data)

    # Send to Sentry as error issue (if enabled)
    if _sentry_logger:
        _sentry_logger.error(
            "Route processing error from {peer_ip}: {error_message}",
            peer_ip=peer_ip,
            error_message=error_message,
            route_count=route_count,
        )


def log_database_error(
    operation: str,
    error_message: str,
    table: str | None = None,
    row_count: int | None = None,
) -> None:
    """
    Log database error to both stdout and Sentry.

    FATAL level events are sent to Sentry as critical issues.
    Use this for database failures that may require immediate attention.

    Args:
        operation: Database operation being performed
        error_message: Error message
        table: Table name (optional)
        row_count: Number of rows being processed (optional)
    """
    # Always log to stdout via structlog
    log_data: dict[str, Any] = {
        "operation": operation,
        "error": error_message,
    }
    if table:
        log_data["table"] = table
    if row_count is not None:
        log_data["row_count"] = row_count

    logger.error("database_error", **log_data)

    # Send to Sentry as fatal issue (if enabled)
    if _sentry_logger:
        _sentry_logger.fatal(
            "Database {operation} failed: {error_message}",
            operation=operation,
            error_message=error_message,
            table=table,
            row_count=row_count,
        )


def capture_parse_error(
    error_type: str,
    peer_ip: str,
    error_message: str,
    data_hex: str | None = None,
    exception: Exception | None = None,
) -> None:
    """
    Capture parse error to both stdout and Sentry with exception tracking.

    ERROR level events are sent to Sentry as issues with full exception context.
    Use this for actual errors that need attention.

    Args:
        error_type: Type of error (bmp_parse_error, bgp_parse_error, etc.)
        peer_ip: BMP peer IP address
        error_message: Error message
        data_hex: Hex dump of problematic data (optional)
        exception: Exception object to capture in Sentry (optional)
    """
    # Always log to stdout via structlog
    log_data = {
        "error_type": error_type,
        "peer_ip": peer_ip,
        "error": error_message,
    }
    if data_hex:
        # Truncate hex data (first 256 chars for stdout)
        log_data["data_hex"] = data_hex[:256]

    logger.error("parse_error", **log_data)

    # Send to Sentry with exception context (if enabled)
    if _sentry_sdk and exception:
        with _sentry_sdk.push_scope() as scope:
            scope.set_tag("error_type", error_type)
            scope.set_tag("peer_ip", peer_ip)
            if data_hex:
                scope.set_context("parse_data", {"hex": data_hex[:512]})
            _sentry_sdk.capture_exception(exception)
    elif _sentry_logger:
        # Fallback if no exception provided
        _sentry_logger.error(
            "{error_type} from {peer_ip}: {error_message}",
            error_type=error_type,
            peer_ip=peer_ip,
            error_message=error_message,
            data_hex=data_hex[:512] if data_hex else None,
        )


def capture_peer_up_event(peer_ip: str, bgp_peer: str, bgp_peer_asn: int) -> None:
    """
    Capture BMP peer up event to both stdout and Sentry.

    Alias for log_peer_up_event for backward compatibility.

    Args:
        peer_ip: BMP peer IP address
        bgp_peer: BGP peer IP address
        bgp_peer_asn: BGP peer ASN
    """
    log_peer_up_event(peer_ip, bgp_peer, bgp_peer_asn)


def capture_peer_down_event(peer_ip: str, reason: int) -> None:
    """
    Capture BMP peer down event to both stdout and Sentry.

    Alias for log_peer_down_event for backward compatibility.

    Args:
        peer_ip: BMP peer IP address
        reason: Peer down reason code
    """
    log_peer_down_event(peer_ip, reason)
