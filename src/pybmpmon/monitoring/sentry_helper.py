"""Sentry integration helper functions."""

import logging
from typing import Any

import structlog

from pybmpmon.config import settings

logger = structlog.get_logger(__name__)

# Track if Sentry is enabled
_sentry_enabled = False
_sentry_sdk = None


def init_sentry() -> bool:
    """
    Initialize Sentry SDK if configured.

    Returns:
        True if Sentry was initialized, False otherwise
    """
    global _sentry_enabled, _sentry_sdk

    if not settings.sentry_dsn:
        logger.debug("sentry_disabled")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration

        _sentry_sdk = sentry_sdk

        sentry_logging = LoggingIntegration(
            level=logging.INFO, event_level=logging.ERROR
        )

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_environment,
            traces_sample_rate=settings.sentry_traces_sample_rate,
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


def capture_peer_up_event(peer_ip: str, bgp_peer: str, bgp_peer_asn: int) -> None:
    """
    Capture BMP peer up event in Sentry.

    Args:
        peer_ip: BMP peer IP address
        bgp_peer: BGP peer IP address
        bgp_peer_asn: BGP peer ASN
    """
    if not _sentry_enabled or not _sentry_sdk:
        return

    with _sentry_sdk.push_scope() as scope:
        # Add context
        scope.set_context(
            "bmp_peer",
            {
                "peer_ip": peer_ip,
                "bgp_peer": bgp_peer,
                "bgp_peer_asn": bgp_peer_asn,
            },
        )

        # Add tags for filtering
        scope.set_tag("event_type", "peer_up")
        scope.set_tag("peer_ip", peer_ip)

        # Capture as informational message
        _sentry_sdk.capture_message(
            f"BMP peer {peer_ip} established session with BGP peer "
            f"{bgp_peer} (AS{bgp_peer_asn})",
            level="info",
        )


def capture_peer_down_event(peer_ip: str, reason: int) -> None:
    """
    Capture BMP peer down event in Sentry.

    Args:
        peer_ip: BMP peer IP address
        reason: Peer down reason code
    """
    if not _sentry_enabled or not _sentry_sdk:
        return

    with _sentry_sdk.push_scope() as scope:
        # Add context
        scope.set_context(
            "bmp_peer",
            {
                "peer_ip": peer_ip,
                "reason_code": reason,
            },
        )

        # Add tags for filtering
        scope.set_tag("event_type", "peer_down")
        scope.set_tag("peer_ip", peer_ip)

        # Capture as warning
        _sentry_sdk.capture_message(
            f"BMP peer {peer_ip} disconnected (reason code: {reason})",
            level="warning",
        )


def capture_parse_error(
    error_type: str,
    peer_ip: str,
    error_message: str,
    data_hex: str | None = None,
    exception: Exception | None = None,
) -> None:
    """
    Capture parse error in Sentry with full context.

    Args:
        error_type: Type of error (bmp_parse_error, bgp_parse_error, etc.)
        peer_ip: BMP peer IP address
        error_message: Error message
        data_hex: Hex dump of problematic data (optional)
        exception: Exception object if available (optional)
    """
    if not _sentry_enabled or not _sentry_sdk:
        return

    with _sentry_sdk.push_scope() as scope:
        # Add context
        context: dict[str, Any] = {
            "peer_ip": peer_ip,
            "error_message": error_message,
        }

        if data_hex:
            # Truncate hex data for Sentry (first 512 chars)
            context["data_hex"] = data_hex[:512]

        scope.set_context("parse_error", context)

        # Add tags for filtering
        scope.set_tag("error_type", error_type)
        scope.set_tag("peer_ip", peer_ip)

        # Capture exception or message
        if exception:
            _sentry_sdk.capture_exception(exception)
        else:
            _sentry_sdk.capture_message(
                f"{error_type}: {error_message} from {peer_ip}",
                level="error",
            )


def capture_route_processing_error(
    peer_ip: str,
    error_message: str,
    route_count: int | None = None,
    exception: Exception | None = None,
) -> None:
    """
    Capture route processing error in Sentry.

    Args:
        peer_ip: BMP peer IP address
        error_message: Error message
        route_count: Number of routes being processed (optional)
        exception: Exception object if available (optional)
    """
    if not _sentry_enabled or not _sentry_sdk:
        return

    with _sentry_sdk.push_scope() as scope:
        # Add context
        context: dict[str, Any] = {
            "peer_ip": peer_ip,
            "error_message": error_message,
        }

        if route_count is not None:
            context["route_count"] = route_count

        scope.set_context("route_processing", context)

        # Add tags for filtering
        scope.set_tag("error_type", "route_processing_error")
        scope.set_tag("peer_ip", peer_ip)

        # Capture exception or message
        if exception:
            _sentry_sdk.capture_exception(exception)
        else:
            _sentry_sdk.capture_message(
                f"Route processing error from {peer_ip}: {error_message}",
                level="error",
            )


def set_peer_context(peer_ip: str) -> None:
    """
    Set peer context for current Sentry scope.

    Args:
        peer_ip: BMP peer IP address
    """
    if not _sentry_enabled or not _sentry_sdk:
        return

    _sentry_sdk.set_tag("peer_ip", peer_ip)
    _sentry_sdk.set_context("peer", {"ip": peer_ip})
