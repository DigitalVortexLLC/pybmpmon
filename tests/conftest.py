"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def valid_bmp_header() -> bytes:
    """Return a valid BMP header (Initiation message)."""
    # Version=3, Length=6, Type=4 (Initiation)
    return b"\x03\x00\x00\x00\x06\x04"


@pytest.fixture
def valid_bmp_route_monitoring_header() -> bytes:
    """Return a valid BMP Route Monitoring message header."""
    # Version=3, Length=100, Type=0 (Route Monitoring)
    return b"\x03\x00\x00\x00\x64\x00"
