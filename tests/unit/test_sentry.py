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

        # Set DSN
        monkeypatch.setenv("SENTRY_DSN", "https://example@sentry.io/123")
        monkeypatch.setenv("SENTRY_ENVIRONMENT", "test")

        from pybmpmon.config import Settings

        settings = Settings()
        monkeypatch.setattr("pybmpmon.monitoring.sentry_helper.settings", settings)

        # Mock sentry_sdk at the import location
        mock_sentry = mock.MagicMock()
        mock_logging_integration = mock.MagicMock()
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

    def test_capture_peer_up_when_disabled(self):
        """Test that capture_peer_up_event does nothing when Sentry is disabled."""
        # Should not raise any errors
        sentry_helper.capture_peer_up_event(
            peer_ip="192.0.2.1",
            bgp_peer="192.0.2.100",
            bgp_peer_asn=65001,
        )

    def test_capture_peer_down_when_disabled(self):
        """Test that capture_peer_down_event does nothing when Sentry is disabled."""
        # Should not raise any errors
        sentry_helper.capture_peer_down_event(
            peer_ip="192.0.2.1",
            reason=1,
        )

    def test_capture_parse_error_when_disabled(self):
        """Test that capture_parse_error does nothing when Sentry is disabled."""
        # Should not raise any errors
        sentry_helper.capture_parse_error(
            error_type="bmp_parse_error",
            peer_ip="192.0.2.1",
            error_message="Test error",
            data_hex="0300000006",
        )

    def test_set_peer_context_when_disabled(self):
        """Test that set_peer_context does nothing when Sentry is disabled."""
        # Should not raise any errors
        sentry_helper.set_peer_context(peer_ip="192.0.2.1")


class TestSentryEnabled:
    """Test Sentry helper functions when Sentry is enabled."""

    def setup_method(self):
        """Setup mock Sentry SDK for these tests."""
        sentry_helper._sentry_enabled = True

        # Create mock sentry_sdk
        self.mock_sentry = mock.MagicMock()
        self.mock_scope = mock.MagicMock()

        # Setup push_scope context manager
        self.mock_sentry.push_scope.return_value.__enter__.return_value = (
            self.mock_scope
        )
        self.mock_sentry.push_scope.return_value.__exit__.return_value = None

        sentry_helper._sentry_sdk = self.mock_sentry

    def teardown_method(self):
        """Reset Sentry state."""
        sentry_helper._sentry_enabled = False
        sentry_helper._sentry_sdk = None

    def test_capture_peer_up_event(self):
        """Test capturing peer up event in Sentry."""
        sentry_helper.capture_peer_up_event(
            peer_ip="192.0.2.1",
            bgp_peer="192.0.2.100",
            bgp_peer_asn=65001,
        )

        # Verify scope was configured
        self.mock_scope.set_context.assert_called_once()
        self.mock_scope.set_tag.assert_any_call("event_type", "peer_up")
        self.mock_scope.set_tag.assert_any_call("peer_ip", "192.0.2.1")

        # Verify message was captured
        self.mock_sentry.capture_message.assert_called_once()
        call_args = self.mock_sentry.capture_message.call_args
        assert "192.0.2.1" in call_args[0][0]
        assert "192.0.2.100" in call_args[0][0]
        assert call_args[1]["level"] == "info"

    def test_capture_peer_down_event(self):
        """Test capturing peer down event in Sentry."""
        sentry_helper.capture_peer_down_event(
            peer_ip="192.0.2.1",
            reason=1,
        )

        # Verify scope was configured
        self.mock_scope.set_context.assert_called_once()
        self.mock_scope.set_tag.assert_any_call("event_type", "peer_down")
        self.mock_scope.set_tag.assert_any_call("peer_ip", "192.0.2.1")

        # Verify message was captured
        self.mock_sentry.capture_message.assert_called_once()
        call_args = self.mock_sentry.capture_message.call_args
        assert "192.0.2.1" in call_args[0][0]
        assert call_args[1]["level"] == "warning"

    def test_capture_parse_error_with_exception(self):
        """Test capturing parse error with exception in Sentry."""
        test_exception = ValueError("Test parse error")

        sentry_helper.capture_parse_error(
            error_type="bmp_parse_error",
            peer_ip="192.0.2.1",
            error_message="Invalid BMP version",
            data_hex="0200000006",
            exception=test_exception,
        )

        # Verify scope was configured
        self.mock_scope.set_context.assert_called_once()
        self.mock_scope.set_tag.assert_any_call("error_type", "bmp_parse_error")
        self.mock_scope.set_tag.assert_any_call("peer_ip", "192.0.2.1")

        # Verify exception was captured
        self.mock_sentry.capture_exception.assert_called_once_with(test_exception)

    def test_capture_parse_error_without_exception(self):
        """Test capturing parse error without exception in Sentry."""
        sentry_helper.capture_parse_error(
            error_type="bgp_parse_error",
            peer_ip="192.0.2.1",
            error_message="Invalid BGP marker",
        )

        # Verify message was captured instead of exception
        self.mock_sentry.capture_message.assert_called_once()
        call_args = self.mock_sentry.capture_message.call_args
        assert "bgp_parse_error" in call_args[0][0]
        assert "192.0.2.1" in call_args[0][0]
        assert call_args[1]["level"] == "error"

    def test_capture_parse_error_truncates_hex_data(self):
        """Test that hex data is truncated to 512 chars."""
        long_hex = "00" * 1000  # 2000 characters

        sentry_helper.capture_parse_error(
            error_type="bmp_parse_error",
            peer_ip="192.0.2.1",
            error_message="Test error",
            data_hex=long_hex,
        )

        # Verify context was set
        context_call = self.mock_scope.set_context.call_args[0][1]
        assert len(context_call["data_hex"]) == 512

    def test_capture_route_processing_error(self):
        """Test capturing route processing error in Sentry."""
        test_exception = RuntimeError("Database connection failed")

        sentry_helper.capture_route_processing_error(
            peer_ip="192.0.2.1",
            error_message="Failed to insert routes",
            route_count=1000,
            exception=test_exception,
        )

        # Verify scope was configured
        self.mock_scope.set_context.assert_called_once()
        context_call = self.mock_scope.set_context.call_args[0][1]
        assert context_call["route_count"] == 1000

        # Verify exception was captured
        self.mock_sentry.capture_exception.assert_called_once_with(test_exception)

    def test_set_peer_context(self):
        """Test setting peer context in Sentry."""
        sentry_helper.set_peer_context(peer_ip="192.0.2.1")

        # Verify tag and context were set
        self.mock_sentry.set_tag.assert_called_once_with("peer_ip", "192.0.2.1")
        self.mock_sentry.set_context.assert_called_once_with(
            "peer", {"ip": "192.0.2.1"}
        )
