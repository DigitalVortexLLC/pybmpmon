"""Unit tests for Sentry integration."""

from unittest import mock

from pybmpmon.monitoring import sentry_helper


class TestSentryInitialization:
    """Test Sentry initialization."""

    def test_init_sentry_when_dsn_not_configured(self, monkeypatch):
        """Test that Sentry doesn't initialize when DSN is not set."""
        # Reset global state
        sentry_helper._sentry_enabled = False
        sentry_helper._sentry_sdk = None
        sentry_helper._sentry_logger = None

        # Ensure no DSN
        monkeypatch.setenv("SENTRY_DSN", "")

        # Reimport settings to pick up env change
        from pybmpmon.config import Settings

        settings = Settings()
        monkeypatch.setattr("pybmpmon.monitoring.sentry_helper.settings", settings)

        result = sentry_helper.init_sentry()

        assert result is False
        assert sentry_helper.is_sentry_enabled() is False

    def test_init_sentry_when_sdk_not_installed(self, monkeypatch):
        """Test Sentry init when sentry_sdk is not installed."""
        # Reset global state
        sentry_helper._sentry_enabled = False
        sentry_helper._sentry_sdk = None
        sentry_helper._sentry_logger = None

        # Set DSN
        monkeypatch.setenv("SENTRY_DSN", "https://example@sentry.io/123")

        from pybmpmon.config import Settings

        settings = Settings()
        monkeypatch.setattr("pybmpmon.monitoring.sentry_helper.settings", settings)

        # Mock the import to raise ImportError
        with mock.patch.dict("sys.modules", {"sentry_sdk": None}):
            result = sentry_helper.init_sentry()

            # Should return False due to ImportError
            assert result is False
            assert sentry_helper.is_sentry_enabled() is False

    def test_init_sentry_success(self, monkeypatch):
        """Test successful Sentry initialization with LoggingIntegration."""
        # Reset global state
        sentry_helper._sentry_enabled = False
        sentry_helper._sentry_sdk = None
        sentry_helper._sentry_logger = None

        # Set DSN
        monkeypatch.setenv("SENTRY_DSN", "https://example@sentry.io/123")
        monkeypatch.setenv("SENTRY_ENVIRONMENT", "test")

        from pybmpmon.config import Settings

        settings = Settings()
        monkeypatch.setattr("pybmpmon.monitoring.sentry_helper.settings", settings)

        # Mock sentry_sdk at the import location
        mock_sentry = mock.MagicMock()
        mock_logging_integration_class = mock.MagicMock()
        mock_logging_integration_instance = mock.MagicMock()
        mock_logging_integration_class.return_value = mock_logging_integration_instance

        with mock.patch.dict(
            "sys.modules",
            {
                "sentry_sdk": mock_sentry,
                "sentry_sdk.integrations": mock.MagicMock(),
                "sentry_sdk.integrations.logging": mock.MagicMock(
                    LoggingIntegration=mock_logging_integration_class
                ),
            },
        ):
            result = sentry_helper.init_sentry()

            assert result is True
            assert sentry_helper.is_sentry_enabled() is True

            # Verify sentry_sdk.init was called
            assert mock_sentry.init.called

            # Verify LoggingIntegration was created
            mock_logging_integration_class.assert_called_once()

            # Verify init was called with integrations parameter
            call_kwargs = mock_sentry.init.call_args[1]
            assert "integrations" in call_kwargs
            assert mock_logging_integration_instance in call_kwargs["integrations"]


class TestSentryDisabled:
    """Test Sentry helper functions when Sentry is disabled."""

    def setup_method(self):
        """Ensure Sentry is disabled for these tests."""
        sentry_helper._sentry_enabled = False
        sentry_helper._sentry_sdk = None
        sentry_helper._sentry_logger = None

    def test_log_peer_up_when_disabled(self):
        """Test that log_peer_up_event works when Sentry is disabled."""
        # Should not raise any errors, just logs to stdout
        sentry_helper.log_peer_up_event(
            peer_ip="192.0.2.1",
            bgp_peer="192.0.2.100",
            bgp_peer_asn=65001,
        )

    def test_log_peer_down_when_disabled(self):
        """Test that log_peer_down_event works when Sentry is disabled."""
        # Should not raise any errors, just logs to stdout
        sentry_helper.log_peer_down_event(
            peer_ip="192.0.2.1",
            reason=1,
        )

    def test_log_parse_error_when_disabled(self):
        """Test that log_parse_error works when Sentry is disabled."""
        # Should not raise any errors, just logs to stdout
        sentry_helper.log_parse_error(
            error_type="bmp_parse_error",
            peer_ip="192.0.2.1",
            error_message="Test error",
            data_hex="0300000006",
        )

    def test_get_sentry_logger_when_disabled(self):
        """Test that get_sentry_logger returns None when Sentry is disabled."""
        logger = sentry_helper.get_sentry_logger()
        assert logger is None


class TestSentryEnabled:
    """Test Sentry helper functions when Sentry is enabled.

    Note: With LoggingIntegration, the helper functions just log to structlog.
    Sentry automatically captures logs via LoggingIntegration, so we don't
    test manual capture_message() or add_breadcrumb() calls here.
    """

    def setup_method(self):
        """Setup mock Sentry SDK for these tests."""
        sentry_helper._sentry_enabled = True

        # Create mock sentry_sdk
        self.mock_sentry = mock.MagicMock()

        sentry_helper._sentry_sdk = self.mock_sentry
        sentry_helper._sentry_logger = None  # Not used anymore

    def teardown_method(self):
        """Reset Sentry state."""
        sentry_helper._sentry_enabled = False
        sentry_helper._sentry_sdk = None
        sentry_helper._sentry_logger = None

    def test_log_peer_up_event(self):
        """Test logging peer up event (captured automatically by LoggingIntegration)."""
        # Should not raise any errors
        sentry_helper.log_peer_up_event(
            peer_ip="192.0.2.1",
            bgp_peer="192.0.2.100",
            bgp_peer_asn=65001,
        )
        # Note: No assertions on Sentry SDK calls because LoggingIntegration
        # handles this automatically via Python's logging module

    def test_log_peer_down_event(self):
        """
        Test logging peer down event.

        Captured automatically by LoggingIntegration.
        """
        # Should not raise any errors
        sentry_helper.log_peer_down_event(
            peer_ip="192.0.2.1",
            reason=1,
        )
        # Note: No assertions on Sentry SDK calls because LoggingIntegration
        # handles this automatically via Python's logging module

    def test_log_parse_error(self):
        """
        Test logging parse error.

        Captured automatically by LoggingIntegration.
        """
        # Should not raise any errors
        sentry_helper.log_parse_error(
            error_type="bmp_parse_error",
            peer_ip="192.0.2.1",
            error_message="Invalid BMP version",
            data_hex="0200000006",
        )
        # Note: No assertions on Sentry SDK calls because LoggingIntegration
        # handles this automatically via Python's logging module

    def test_log_route_processing_error(self):
        """
        Test logging route processing error.

        Captured automatically by LoggingIntegration.
        """
        # Should not raise any errors
        sentry_helper.log_route_processing_error(
            peer_ip="192.0.2.1",
            error_message="Failed to insert routes",
            route_count=1000,
        )
        # Note: No assertions on Sentry SDK calls because LoggingIntegration
        # handles this automatically via Python's logging module

    def test_log_database_error(self):
        """
        Test logging database error.

        Captured automatically by LoggingIntegration.
        """
        # Should not raise any errors
        sentry_helper.log_database_error(
            operation="COPY",
            error_message="Connection lost",
            table="route_updates",
            row_count=1000,
        )
        # Note: No assertions on Sentry SDK calls because LoggingIntegration
        # handles this automatically via Python's logging module

    def test_capture_parse_error_with_exception(self):
        """
        Test capturing parse error with exception context.

        Uses manual capture_exception.
        """
        test_exception = ValueError("Test error")

        sentry_helper.capture_parse_error(
            error_type="bmp_parse_error",
            peer_ip="192.0.2.1",
            error_message="Invalid BMP version",
            data_hex="0200000006",
            exception=test_exception,
        )

        # Verify capture_exception was called (manual SDK call)
        self.mock_sentry.capture_exception.assert_called_once()

    def test_get_sentry_logger(self):
        """Test that get_sentry_logger returns None (deprecated)."""
        logger = sentry_helper.get_sentry_logger()
        assert logger is None

    def test_get_sentry_sdk(self):
        """Test getting Sentry SDK instance."""
        sdk = sentry_helper.get_sentry_sdk()
        assert sdk is self.mock_sentry

    def test_get_sentry_sdk_when_disabled(self):
        """Test that get_sentry_sdk returns None when disabled."""
        # Temporarily disable
        sentry_helper._sentry_enabled = False
        sdk = sentry_helper.get_sentry_sdk()
        assert sdk is None
        # Re-enable for other tests
        sentry_helper._sentry_enabled = True
