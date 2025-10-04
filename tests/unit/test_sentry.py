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
        """Test successful Sentry initialization."""
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
        mock_sentry_logger = mock.MagicMock()
        mock_logging_integration = mock.MagicMock()
        mock_sentry.logger = mock_sentry_logger
        mock_sentry.integrations.logging.LoggingIntegration = mock_logging_integration
        mock_sentry.init = mock.MagicMock()

        with mock.patch.dict(
            "sys.modules",
            {
                "sentry_sdk": mock_sentry,
                "sentry_sdk.integrations": mock.MagicMock(),
                "sentry_sdk.integrations.logging": mock.MagicMock(
                    LoggingIntegration=mock_logging_integration
                ),
            },
        ):
            result = sentry_helper.init_sentry()

            assert result is True
            assert sentry_helper.is_sentry_enabled() is True
            # The init should have been called
            assert mock_sentry.init.called


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
    """Test Sentry helper functions when Sentry is enabled."""

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
        """Test logging peer up event to Sentry."""
        sentry_helper.log_peer_up_event(
            peer_ip="192.0.2.1",
            bgp_peer="192.0.2.100",
            bgp_peer_asn=65001,
        )

        # Verify add_breadcrumb was called
        self.mock_sentry.add_breadcrumb.assert_called_once()
        call_args = self.mock_sentry.add_breadcrumb.call_args
        # Check category and level
        assert call_args[1]["category"] == "bmp.peer"
        assert call_args[1]["level"] == "info"
        # Check data
        assert call_args[1]["data"]["peer_ip"] == "192.0.2.1"
        assert call_args[1]["data"]["bgp_peer"] == "192.0.2.100"
        assert call_args[1]["data"]["bgp_peer_asn"] == 65001

    def test_log_peer_down_event(self):
        """Test logging peer down event to Sentry."""
        sentry_helper.log_peer_down_event(
            peer_ip="192.0.2.1",
            reason=1,
        )

        # Verify capture_message was called
        self.mock_sentry.capture_message.assert_called_once()
        call_args = self.mock_sentry.capture_message.call_args
        # Check message and level
        assert "192.0.2.1" in call_args[0][0]
        assert call_args[1]["level"] == "warning"
        # Check extras
        assert call_args[1]["extras"]["peer_ip"] == "192.0.2.1"
        assert call_args[1]["extras"]["reason_code"] == 1

    def test_log_parse_error(self):
        """Test logging parse error to Sentry."""
        sentry_helper.log_parse_error(
            error_type="bmp_parse_error",
            peer_ip="192.0.2.1",
            error_message="Invalid BMP version",
            data_hex="0200000006",
        )

        # Verify capture_message was called
        self.mock_sentry.capture_message.assert_called_once()
        call_args = self.mock_sentry.capture_message.call_args
        # Check message and level
        assert "bmp_parse_error" in call_args[0][0]
        assert "192.0.2.1" in call_args[0][0]
        assert call_args[1]["level"] == "error"
        # Check extras
        assert call_args[1]["extras"]["error_type"] == "bmp_parse_error"
        assert call_args[1]["extras"]["peer_ip"] == "192.0.2.1"

    def test_log_parse_error_truncates_hex_data(self):
        """Test that hex data is truncated to 512 chars for Sentry."""
        long_hex = "00" * 1000  # 2000 characters

        sentry_helper.log_parse_error(
            error_type="bmp_parse_error",
            peer_ip="192.0.2.1",
            error_message="Test error",
            data_hex=long_hex,
        )

        # Verify truncation
        call_args = self.mock_sentry.capture_message.call_args
        assert len(call_args[1]["extras"]["data_hex"]) == 512

    def test_log_route_processing_error(self):
        """Test logging route processing error to Sentry."""
        sentry_helper.log_route_processing_error(
            peer_ip="192.0.2.1",
            error_message="Failed to insert routes",
            route_count=1000,
        )

        # Verify capture_message was called
        self.mock_sentry.capture_message.assert_called_once()
        call_args = self.mock_sentry.capture_message.call_args
        assert "192.0.2.1" in call_args[0][0]
        assert call_args[1]["level"] == "error"
        assert call_args[1]["extras"]["peer_ip"] == "192.0.2.1"
        assert call_args[1]["extras"]["route_count"] == 1000

    def test_log_database_error(self):
        """Test logging database error to Sentry."""
        sentry_helper.log_database_error(
            operation="COPY",
            error_message="Connection lost",
            table="route_updates",
            row_count=1000,
        )

        # Verify capture_message was called
        self.mock_sentry.capture_message.assert_called_once()
        call_args = self.mock_sentry.capture_message.call_args
        assert "COPY" in call_args[0][0]
        assert call_args[1]["level"] == "fatal"
        assert call_args[1]["extras"]["operation"] == "COPY"
        assert call_args[1]["extras"]["table"] == "route_updates"
        assert call_args[1]["extras"]["row_count"] == 1000

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
