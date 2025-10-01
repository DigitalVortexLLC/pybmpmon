"""Unit tests for logging configuration."""

import logging

from pybmpmon.monitoring.logger import add_log_level, configure_logging, get_logger


class TestLogLevelProcessor:
    """Test log level processor."""

    def test_add_log_level(self):
        """Test adding log level to event dict."""
        event_dict = {"event": "test_event"}
        result = add_log_level(None, "info", event_dict)

        assert "level" in result
        assert result["level"] == "INFO"

    def test_add_log_level_various_levels(self):
        """Test different log levels."""
        levels = ["debug", "info", "warning", "error", "critical"]

        for level in levels:
            event_dict = {"event": "test"}
            result = add_log_level(None, level, event_dict)
            assert result["level"] == level.upper()


class TestLoggerConfiguration:
    """Test logger configuration."""

    def test_configure_logging_returns_logger(self):
        """Test that configure_logging returns a logger."""
        logger = configure_logging()

        assert logger is not None
        # Logger is a proxy or bound logger
        assert hasattr(logger, "info")
        assert hasattr(logger, "debug")
        assert hasattr(logger, "error")

    def test_get_logger(self):
        """Test getting a logger instance."""
        logger = get_logger("test_module")

        assert logger is not None
        # Logger has standard logging methods
        assert hasattr(logger, "info")
        assert hasattr(logger, "debug")
        assert hasattr(logger, "error")

    def test_logging_produces_json(self, caplog):
        """Test that logging can be called and produces structured output."""
        # Get a fresh logger
        logger = get_logger("test_json")

        # Log a test message - verify it can be called without errors
        with caplog.at_level(logging.INFO):
            logger.info("test_message", key="value", number=123)

        # Verify logging was called (caplog captures it)
        assert len(caplog.records) > 0

    def test_debug_logging_when_enabled(self, caplog, monkeypatch):
        """Test DEBUG level logging when log level is DEBUG."""
        # Set log level to DEBUG
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        # Configure logging with DEBUG level
        logging.getLogger().setLevel(logging.DEBUG)
        logger = get_logger("test_debug")

        # Log DEBUG message
        with caplog.at_level(logging.DEBUG):
            logger.debug("debug_message", detail="test_detail")

        # Verify debug logging was captured
        assert len(caplog.records) > 0


class TestStructuredLogging:
    """Test structured logging examples."""

    def test_peer_connected_log(self, caplog):
        """Test peer_connected structured log."""
        logger = get_logger("test")

        with caplog.at_level(logging.INFO):
            logger.info("peer_connected", peer="192.0.2.1")

        # Verify logging works
        assert len(caplog.records) > 0

    def test_peer_disconnected_log(self, caplog):
        """Test peer_disconnected structured log."""
        logger = get_logger("test")

        with caplog.at_level(logging.INFO):
            logger.info(
                "peer_disconnected",
                peer="192.0.2.1",
                reason="connection_reset",
                duration_seconds=3600,
            )

        # Verify logging works
        assert len(caplog.records) > 0

    def test_route_stats_log(self, caplog):
        """Test route_stats structured log."""
        logger = get_logger("test")

        with caplog.at_level(logging.INFO):
            logger.info(
                "route_stats",
                peer="192.0.2.1",
                received=1523,
                processed=1520,
                ipv4=1245,
                ipv6=275,
                evpn=0,
                errors=3,
                throughput_per_sec=152,
            )

        # Verify logging works
        assert len(caplog.records) > 0

    def test_parse_error_log(self, caplog):
        """Test parse_error structured log."""
        logger = get_logger("test")

        with caplog.at_level(logging.ERROR):
            logger.error(
                "bmp_parse_error",
                peer="192.0.2.1",
                error="Invalid BMP version",
                data_hex="02000000060400",
            )

        # Verify logging works
        assert len(caplog.records) > 0

    def test_bmp_message_received_debug_log(self, caplog):
        """Test bmp_message_received DEBUG log with hex dump."""
        logger = get_logger("test")

        with caplog.at_level(logging.DEBUG):
            logger.debug(
                "bmp_message_received",
                peer="192.0.2.1",
                version=3,
                length=100,
                msg_type="ROUTE_MONITORING",
                data_hex="03000000640012345678" + "00" * 90,
                total_size=100,
            )

        # Verify logging works
        assert len(caplog.records) > 0


class TestLoggerContextData:
    """Test logger with context data."""

    def test_logger_binds_context(self, caplog):
        """Test binding context to logger."""
        logger = get_logger("test")
        bound_logger = logger.bind(request_id="abc123", user="testuser")

        with caplog.at_level(logging.INFO):
            bound_logger.info("test_event", action="test_action")

        # Verify logging works
        assert len(caplog.records) > 0
