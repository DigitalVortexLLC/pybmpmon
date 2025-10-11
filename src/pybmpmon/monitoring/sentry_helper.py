"""Sentry integration helper functions.

This module configures Sentry with LoggingIntegration, which automatically captures
logs from Python's logging module (which structlog writes to). This means:

1. All structlog logs at INFO+ level are automatically sent to Sentry as breadcrumbs
2. All structlog logs at ERROR+ level are automatically sent to Sentry as issues
3. No manual capture_message() calls needed for standard logging

Additionally, this module provides helper functions for:
- Adding structured context to Sentry issues
- Manual exception capture with custom context
- Direct access to Sentry SDK for advanced features (spans, transactions, etc.)

Usage:
    # Standard logging (automatically captured by Sentry via LoggingIntegration)
    from pybmpmon.monitoring.logger import get_logger

    logger = get_logger(__name__)
    logger.info("peer_connected", peer="192.0.2.1")  # → Sentry breadcrumb
    # → Sentry issue
    logger.error("parse_error", peer="192.0.2.1", error="Invalid data")

    # Advanced usage: Manual exception capture with context
    from pybmpmon.monitoring.sentry_helper import (
        capture_parse_error,
        get_sentry_sdk,
    )

    try:
        parse_bmp_message(data)
    except BMPParseError as e:
        capture_parse_error(
            error_type="bmp_parse_error",
            peer_ip="192.0.2.1",
            error_message=str(e),
            data_hex=data.hex(),
            exception=e  # Full exception context in Sentry
        )

    # Direct access to Sentry SDK (for spans, transactions, etc.)
    sentry_sdk = get_sentry_sdk()
    if sentry_sdk:
        with sentry_sdk.start_span(op="db.query", description="Fetch routes"):
            # Your code here
            pass

Sentry Level Mapping (via LoggingIntegration):
    - DEBUG: Not sent to Sentry (local only)
    - INFO: Captured as breadcrumbs (provides context for errors)
    - ERROR: Captured as Sentry issues
"""

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

    Logging integration (via LoggingIntegration):
    - TRACE and DEBUG: Not sent to Sentry (local only)
    - INFO and above: Captured as breadcrumbs (provides context for errors)
    - ERROR and above: Sent as issues to Sentry

    Returns:
        True if Sentry was initialized, False otherwise
    """
    global _sentry_enabled, _sentry_sdk, _sentry_logger

    if not settings.sentry_dsn:
        logger.debug("sentry_disabled")
        return False

    try:
        import logging as stdlib_logging

        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration

        _sentry_sdk = sentry_sdk

        # Configure LoggingIntegration
        # This automatically captures logs from Python's logging module
        # (which structlog writes to via LoggerFactory)
        sentry_logging = LoggingIntegration(
            level=stdlib_logging.INFO,  # Capture INFO+ as breadcrumbs
            event_level=stdlib_logging.ERROR,  # Capture ERROR+ as events/issues
        )

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_environment,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            max_breadcrumbs=100,
            integrations=[sentry_logging],
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
    Get Sentry logger instance (deprecated - returns None).

    This function is deprecated. Use get_sentry_sdk() instead to access
    Sentry SDK directly for capture_message(), capture_exception(), etc.

    Returns:
        None (deprecated)
    """
    return None  # Deprecated - we use Sentry SDK directly now


def get_sentry_sdk() -> Any:
    """
    Get Sentry SDK instance for direct use (spans, transactions, etc.).

    Returns:
        Sentry SDK instance or None if Sentry not enabled
    """
    return _sentry_sdk if _sentry_enabled else None


def log_peer_up_event(peer_ip: str, bgp_peer: str, bgp_peer_asn: int) -> None:
    """
    Log BMP peer up event to stdout (automatically sent to Sentry as breadcrumb).

    INFO level logs are automatically captured by Sentry's LoggingIntegration
    as breadcrumbs (not issues). They provide context for later errors.

    Args:
        peer_ip: BMP peer IP address
        bgp_peer: BGP peer IP address
        bgp_peer_asn: BGP peer ASN
    """
    # Log to stdout via structlog
    # LoggingIntegration automatically sends INFO+ to Sentry as breadcrumbs
    logger.info(
        "peer_up",
        bmp_peer=peer_ip,
        bgp_peer=bgp_peer,
        bgp_peer_asn=bgp_peer_asn,
    )


def log_peer_down_event(peer_ip: str, reason: int) -> None:
    """
    Log BMP peer down event to stdout (automatically sent to Sentry as breadcrumb).

    INFO level logs are automatically captured by Sentry's LoggingIntegration
    as breadcrumbs. Peer disconnections are normal operational events, not errors.

    Args:
        peer_ip: BMP peer IP address
        reason: Peer down reason code
    """
    # Log to stdout via structlog
    # LoggingIntegration automatically sends INFO+ to Sentry as breadcrumbs
    logger.info(
        "peer_down",
        bmp_peer=peer_ip,
        reason_code=reason,
    )


def log_parse_error(
    error_type: str,
    peer_ip: str,
    error_message: str,
    data_hex: str | None = None,
) -> None:
    """
    Log parse error to stdout (automatically sent to Sentry as issue).

    ERROR level logs are automatically captured by Sentry's LoggingIntegration
    as issues. All structured log data is included in the Sentry event.

    Args:
        error_type: Type of error (bmp_parse_error, bgp_parse_error, etc.)
        peer_ip: BMP peer IP address
        error_message: Error message
        data_hex: Hex dump of problematic data (optional)
    """
    # Log to stdout via structlog
    # LoggingIntegration automatically sends ERROR+ to Sentry as issues
    log_data = {
        "error_type": error_type,
        "peer_ip": peer_ip,
        "error": error_message,
    }
    if data_hex:
        # Truncate hex data (first 256 chars for stdout/Sentry)
        log_data["data_hex"] = data_hex[:256]

    logger.error("parse_error", **log_data)


def log_route_processing_error(
    peer_ip: str,
    error_message: str,
    route_count: int | None = None,
) -> None:
    """
    Log route processing error to stdout (automatically sent to Sentry as issue).

    ERROR level logs are automatically captured by Sentry's LoggingIntegration
    as issues. All structured log data is included in the Sentry event.

    Args:
        peer_ip: BMP peer IP address
        error_message: Error message
        route_count: Number of routes being processed (optional)
    """
    # Log to stdout via structlog
    # LoggingIntegration automatically sends ERROR+ to Sentry as issues
    log_data: dict[str, Any] = {
        "peer_ip": peer_ip,
        "error": error_message,
    }
    if route_count is not None:
        log_data["route_count"] = route_count

    logger.error("route_processing_error", **log_data)


def log_database_error(
    operation: str,
    error_message: str,
    table: str | None = None,
    row_count: int | None = None,
) -> None:
    """
    Log database error to stdout (automatically sent to Sentry as critical issue).

    ERROR level logs are automatically captured by Sentry's LoggingIntegration
    as issues. All structured log data is included in the Sentry event.

    Args:
        operation: Database operation being performed
        error_message: Error message
        table: Table name (optional)
        row_count: Number of rows being processed (optional)
    """
    # Log to stdout via structlog
    # LoggingIntegration automatically sends ERROR+ to Sentry as issues
    log_data: dict[str, Any] = {
        "operation": operation,
        "error": error_message,
    }
    if table:
        log_data["table"] = table
    if row_count is not None:
        log_data["row_count"] = row_count

    logger.error("database_error", **log_data)


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
    if _sentry_sdk:
        if exception:
            # Capture exception with full context
            with _sentry_sdk.push_scope() as scope:
                scope.set_tag("error_type", error_type)
                scope.set_tag("peer_ip", peer_ip)
                if data_hex:
                    scope.set_context("parse_data", {"hex": data_hex[:512]})
                _sentry_sdk.capture_exception(exception)
        else:
            # Fallback if no exception provided - use capture_message
            extras = {"error_type": error_type, "peer_ip": peer_ip}
            if data_hex:
                extras["data_hex"] = data_hex[:512]
            _sentry_sdk.capture_message(
                f"{error_type} from {peer_ip}: {error_message}",
                level="error",
                extras=extras,
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
