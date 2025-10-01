"""Unit tests for BMP header parsing."""

import pytest
from pybmpmon.protocol.bmp import (
    BMP_CURRENT_VERSION,
    BMPMessageType,
    BMPParseError,
)
from pybmpmon.protocol.bmp_parser import parse_bmp_header


class TestBMPHeaderParsing:
    """Test BMP common header parsing."""

    def test_parse_valid_initiation_message(self) -> None:
        """Test parsing valid Initiation message header."""
        # Version=3, Length=6, Type=4 (Initiation)
        data = b"\x03\x00\x00\x00\x06\x04"
        header = parse_bmp_header(data)

        assert header.version == BMP_CURRENT_VERSION
        assert header.length == 6
        assert header.msg_type == BMPMessageType.INITIATION

    def test_parse_valid_route_monitoring_message(self) -> None:
        """Test parsing valid Route Monitoring message header."""
        # Version=3, Length=100, Type=0 (Route Monitoring)
        data = b"\x03\x00\x00\x00\x64\x00"
        header = parse_bmp_header(data)

        assert header.version == BMP_CURRENT_VERSION
        assert header.length == 100
        assert header.msg_type == BMPMessageType.ROUTE_MONITORING

    def test_parse_valid_peer_up_message(self) -> None:
        """Test parsing valid Peer Up message header."""
        # Version=3, Length=200, Type=3 (Peer Up)
        data = b"\x03\x00\x00\x00\xc8\x03"
        header = parse_bmp_header(data)

        assert header.version == BMP_CURRENT_VERSION
        assert header.length == 200
        assert header.msg_type == BMPMessageType.PEER_UP_NOTIFICATION

    def test_parse_valid_peer_down_message(self) -> None:
        """Test parsing valid Peer Down message header."""
        # Version=3, Length=50, Type=2 (Peer Down)
        data = b"\x03\x00\x00\x00\x32\x02"
        header = parse_bmp_header(data)

        assert header.version == BMP_CURRENT_VERSION
        assert header.length == 50
        assert header.msg_type == BMPMessageType.PEER_DOWN_NOTIFICATION

    def test_parse_valid_statistics_report_message(self) -> None:
        """Test parsing valid Statistics Report message header."""
        # Version=3, Length=150, Type=1 (Statistics Report)
        data = b"\x03\x00\x00\x00\x96\x01"
        header = parse_bmp_header(data)

        assert header.version == BMP_CURRENT_VERSION
        assert header.length == 150
        assert header.msg_type == BMPMessageType.STATISTICS_REPORT

    def test_parse_valid_termination_message(self) -> None:
        """Test parsing valid Termination message header."""
        # Version=3, Length=20, Type=5 (Termination)
        data = b"\x03\x00\x00\x00\x14\x05"
        header = parse_bmp_header(data)

        assert header.version == BMP_CURRENT_VERSION
        assert header.length == 20
        assert header.msg_type == BMPMessageType.TERMINATION

    def test_parse_message_with_extra_data(self) -> None:
        """Test parsing header when extra data is present (should be ignored)."""
        # Header + extra bytes
        data = b"\x03\x00\x00\x00\x06\x04" + b"\xff" * 100
        header = parse_bmp_header(data)

        assert header.version == BMP_CURRENT_VERSION
        assert header.length == 6
        assert header.msg_type == BMPMessageType.INITIATION

    def test_parse_large_message_length(self) -> None:
        """Test parsing header with large message length."""
        # Version=3, Length=1000000, Type=0
        data = b"\x03\x00\x0f\x42\x40\x00"
        header = parse_bmp_header(data)

        assert header.version == BMP_CURRENT_VERSION
        assert header.length == 1000000
        assert header.msg_type == BMPMessageType.ROUTE_MONITORING


class TestBMPHeaderErrors:
    """Test BMP header parsing error cases."""

    def test_truncated_empty_message(self) -> None:
        """Test parsing completely empty message."""
        data = b""
        with pytest.raises(BMPParseError, match="Message too short"):
            parse_bmp_header(data)

    def test_truncated_single_byte(self) -> None:
        """Test parsing message with only 1 byte."""
        data = b"\x03"
        with pytest.raises(BMPParseError, match="Message too short"):
            parse_bmp_header(data)

    def test_truncated_partial_header(self) -> None:
        """Test parsing message with incomplete header (5 bytes)."""
        data = b"\x03\x00\x00\x00\x06"
        with pytest.raises(BMPParseError, match="Message too short"):
            parse_bmp_header(data)

    def test_invalid_version_zero(self) -> None:
        """Test parsing header with version 0."""
        data = b"\x00\x00\x00\x00\x06\x04"
        with pytest.raises(BMPParseError, match="Invalid BMP version"):
            parse_bmp_header(data)

    def test_invalid_version_one(self) -> None:
        """Test parsing header with version 1."""
        data = b"\x01\x00\x00\x00\x06\x04"
        with pytest.raises(BMPParseError, match="Invalid BMP version"):
            parse_bmp_header(data)

    def test_invalid_version_two(self) -> None:
        """Test parsing header with version 2."""
        data = b"\x02\x00\x00\x00\x06\x04"
        with pytest.raises(BMPParseError, match="Invalid BMP version"):
            parse_bmp_header(data)

    def test_invalid_version_four(self) -> None:
        """Test parsing header with version 4."""
        data = b"\x04\x00\x00\x00\x06\x04"
        with pytest.raises(BMPParseError, match="Invalid BMP version"):
            parse_bmp_header(data)

    def test_invalid_version_255(self) -> None:
        """Test parsing header with version 255."""
        data = b"\xff\x00\x00\x00\x06\x04"
        with pytest.raises(BMPParseError, match="Invalid BMP version"):
            parse_bmp_header(data)

    def test_unknown_message_type_six(self) -> None:
        """Test parsing header with unknown message type 6."""
        data = b"\x03\x00\x00\x00\x06\x06"
        with pytest.raises(BMPParseError, match="Unknown message type"):
            parse_bmp_header(data)

    def test_unknown_message_type_255(self) -> None:
        """Test parsing header with unknown message type 255."""
        data = b"\x03\x00\x00\x00\x06\xff"
        with pytest.raises(BMPParseError, match="Unknown message type"):
            parse_bmp_header(data)

    def test_invalid_message_length_too_small(self) -> None:
        """Test parsing header with message length smaller than header size."""
        # Length = 5 (less than 6-byte header size)
        data = b"\x03\x00\x00\x00\x05\x04"
        with pytest.raises(BMPParseError, match="Invalid message length"):
            parse_bmp_header(data)

    def test_invalid_message_length_zero(self) -> None:
        """Test parsing header with zero message length."""
        data = b"\x03\x00\x00\x00\x00\x04"
        with pytest.raises(BMPParseError, match="Invalid message length"):
            parse_bmp_header(data)


@pytest.mark.parametrize(
    "msg_type_int,expected_enum",
    [
        (0, BMPMessageType.ROUTE_MONITORING),
        (1, BMPMessageType.STATISTICS_REPORT),
        (2, BMPMessageType.PEER_DOWN_NOTIFICATION),
        (3, BMPMessageType.PEER_UP_NOTIFICATION),
        (4, BMPMessageType.INITIATION),
        (5, BMPMessageType.TERMINATION),
    ],
)
def test_all_valid_message_types(
    msg_type_int: int, expected_enum: BMPMessageType
) -> None:
    """Test parsing all valid BMP message types."""
    # Version=3, Length=6, Type=msg_type_int
    data = bytes([0x03, 0x00, 0x00, 0x00, 0x06, msg_type_int])
    header = parse_bmp_header(data)

    assert header.msg_type == expected_enum
    assert header.msg_type.value == msg_type_int


@pytest.mark.parametrize(
    "invalid_data,error_pattern",
    [
        (b"", "Message too short"),
        (b"\x03", "Message too short"),
        (b"\x03\x00", "Message too short"),
        (b"\x03\x00\x00", "Message too short"),
        (b"\x03\x00\x00\x00", "Message too short"),
        (b"\x03\x00\x00\x00\x06", "Message too short"),
        (b"\x02\x00\x00\x00\x06\x04", "Invalid BMP version"),
        (b"\x04\x00\x00\x00\x06\x04", "Invalid BMP version"),
        (b"\x03\x00\x00\x00\x06\x06", "Unknown message type"),
        (b"\x03\x00\x00\x00\x06\xff", "Unknown message type"),
        (b"\x03\x00\x00\x00\x00\x04", "Invalid message length"),
        (b"\x03\x00\x00\x00\x05\x04", "Invalid message length"),
    ],
)
def test_malformed_messages_parametrized(
    invalid_data: bytes, error_pattern: str
) -> None:
    """Test various malformed messages raise appropriate errors."""
    with pytest.raises(BMPParseError, match=error_pattern):
        parse_bmp_header(invalid_data)
