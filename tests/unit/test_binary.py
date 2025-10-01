"""Unit tests for binary parsing utilities."""

import pytest
from pybmpmon.utils.binary import read_bytes, read_uint8, read_uint16, read_uint32


class TestReadUint8:
    """Test read_uint8 function."""

    def test_read_uint8_simple(self) -> None:
        """Test reading uint8 from simple data."""
        data = b"\x42"
        assert read_uint8(data, 0) == 0x42

    def test_read_uint8_with_offset(self) -> None:
        """Test reading uint8 with offset."""
        data = b"\x00\x01\x02\x03"
        assert read_uint8(data, 0) == 0x00
        assert read_uint8(data, 1) == 0x01
        assert read_uint8(data, 2) == 0x02
        assert read_uint8(data, 3) == 0x03

    def test_read_uint8_max_value(self) -> None:
        """Test reading maximum uint8 value (255)."""
        data = b"\xff"
        assert read_uint8(data, 0) == 255

    def test_read_uint8_insufficient_data(self) -> None:
        """Test reading uint8 with insufficient data."""
        data = b"\x42"
        with pytest.raises(ValueError, match="Not enough data"):
            read_uint8(data, 1)


class TestReadUint16:
    """Test read_uint16 function."""

    def test_read_uint16_simple(self) -> None:
        """Test reading uint16 from simple data (network order)."""
        data = b"\x01\x02"
        assert read_uint16(data, 0) == 0x0102

    def test_read_uint16_with_offset(self) -> None:
        """Test reading uint16 with offset."""
        data = b"\x00\x01\x02\x03\x04"
        assert read_uint16(data, 0) == 0x0001
        assert read_uint16(data, 1) == 0x0102
        assert read_uint16(data, 2) == 0x0203
        assert read_uint16(data, 3) == 0x0304

    def test_read_uint16_max_value(self) -> None:
        """Test reading maximum uint16 value (65535)."""
        data = b"\xff\xff"
        assert read_uint16(data, 0) == 65535

    def test_read_uint16_insufficient_data(self) -> None:
        """Test reading uint16 with insufficient data."""
        data = b"\x01"
        with pytest.raises(ValueError, match="Not enough data"):
            read_uint16(data, 0)


class TestReadUint32:
    """Test read_uint32 function."""

    def test_read_uint32_simple(self) -> None:
        """Test reading uint32 from simple data (network order)."""
        data = b"\x00\x00\x00\x06"
        assert read_uint32(data, 0) == 6

    def test_read_uint32_with_offset(self) -> None:
        """Test reading uint32 with offset."""
        data = b"\x00\x00\x00\x01\x00\x00\x00\x02"
        assert read_uint32(data, 0) == 1
        assert read_uint32(data, 4) == 2

    def test_read_uint32_large_value(self) -> None:
        """Test reading large uint32 value."""
        data = b"\x00\x0f\x42\x40"
        assert read_uint32(data, 0) == 1000000

    def test_read_uint32_max_value(self) -> None:
        """Test reading maximum uint32 value (4294967295)."""
        data = b"\xff\xff\xff\xff"
        assert read_uint32(data, 0) == 4294967295

    def test_read_uint32_insufficient_data(self) -> None:
        """Test reading uint32 with insufficient data."""
        data = b"\x00\x00\x00"
        with pytest.raises(ValueError, match="Not enough data"):
            read_uint32(data, 0)


class TestReadBytes:
    """Test read_bytes function."""

    def test_read_bytes_simple(self) -> None:
        """Test reading bytes from simple data."""
        data = b"\x01\x02\x03\x04"
        assert read_bytes(data, 0, 4) == b"\x01\x02\x03\x04"

    def test_read_bytes_with_offset(self) -> None:
        """Test reading bytes with offset."""
        data = b"\x00\x01\x02\x03\x04"
        assert read_bytes(data, 1, 3) == b"\x01\x02\x03"

    def test_read_bytes_zero_length(self) -> None:
        """Test reading zero bytes."""
        data = b"\x01\x02\x03"
        assert read_bytes(data, 0, 0) == b""

    def test_read_bytes_insufficient_data(self) -> None:
        """Test reading bytes with insufficient data."""
        data = b"\x01\x02"
        with pytest.raises(ValueError, match="Not enough data"):
            read_bytes(data, 0, 3)
