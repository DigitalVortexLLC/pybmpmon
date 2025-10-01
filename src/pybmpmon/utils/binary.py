"""Binary data parsing utilities."""

import ipaddress
import struct


def read_uint8(data: bytes, offset: int = 0) -> int:
    """
    Read an unsigned 8-bit integer (1 byte) from binary data.

    Args:
        data: Binary data to read from
        offset: Byte offset to start reading from

    Returns:
        Unsigned 8-bit integer value

    Raises:
        ValueError: If not enough data available
    """
    if len(data) < offset + 1:
        raise ValueError(
            f"Not enough data to read uint8 at offset {offset}: "
            f"need {offset + 1} bytes, got {len(data)}"
        )
    return data[offset]


def read_uint16(data: bytes, offset: int = 0) -> int:
    """
    Read an unsigned 16-bit integer (2 bytes, network order) from binary data.

    Args:
        data: Binary data to read from
        offset: Byte offset to start reading from

    Returns:
        Unsigned 16-bit integer value

    Raises:
        ValueError: If not enough data available
    """
    if len(data) < offset + 2:
        raise ValueError(
            f"Not enough data to read uint16 at offset {offset}: "
            f"need {offset + 2} bytes, got {len(data)}"
        )
    result: int = struct.unpack_from("!H", data, offset)[0]
    return result


def read_uint32(data: bytes, offset: int = 0) -> int:
    """
    Read an unsigned 32-bit integer (4 bytes, network order) from binary data.

    Args:
        data: Binary data to read from
        offset: Byte offset to start reading from

    Returns:
        Unsigned 32-bit integer value

    Raises:
        ValueError: If not enough data available
    """
    if len(data) < offset + 4:
        raise ValueError(
            f"Not enough data to read uint32 at offset {offset}: "
            f"need {offset + 4} bytes, got {len(data)}"
        )
    result: int = struct.unpack_from("!I", data, offset)[0]
    return result


def read_bytes(data: bytes, offset: int, length: int) -> bytes:
    """
    Read a sequence of bytes from binary data.

    Args:
        data: Binary data to read from
        offset: Byte offset to start reading from
        length: Number of bytes to read

    Returns:
        Byte sequence of specified length

    Raises:
        ValueError: If not enough data available
    """
    if len(data) < offset + length:
        raise ValueError(
            f"Not enough data to read {length} bytes at offset {offset}: "
            f"need {offset + length} bytes, got {len(data)}"
        )
    return data[offset : offset + length]


def read_ipv4_address(data: bytes, offset: int = 0) -> str:
    """
    Read an IPv4 address (4 bytes) from binary data.

    Args:
        data: Binary data to read from
        offset: Byte offset to start reading from

    Returns:
        IPv4 address as string (e.g., "192.0.2.1")

    Raises:
        ValueError: If not enough data available
    """
    if len(data) < offset + 4:
        raise ValueError(
            f"Not enough data to read IPv4 address at offset {offset}: "
            f"need {offset + 4} bytes, got {len(data)}"
        )
    addr_bytes = data[offset : offset + 4]
    return str(ipaddress.IPv4Address(addr_bytes))


def read_ipv6_address(data: bytes, offset: int = 0) -> str:
    """
    Read an IPv6 address (16 bytes) from binary data.

    Args:
        data: Binary data to read from
        offset: Byte offset to start reading from

    Returns:
        IPv6 address as string (e.g., "2001:db8::1")

    Raises:
        ValueError: If not enough data available
    """
    if len(data) < offset + 16:
        raise ValueError(
            f"Not enough data to read IPv6 address at offset {offset}: "
            f"need {offset + 16} bytes, got {len(data)}"
        )
    addr_bytes = data[offset : offset + 16]
    return str(ipaddress.IPv6Address(addr_bytes))


def read_ip_address(data: bytes, offset: int = 0, is_ipv6: bool = False) -> str:
    """
    Read an IP address from 16-byte field (IPv4-mapped or IPv6).

    BMP uses 16-byte fields for IP addresses. IPv4 addresses are stored
    in the last 4 bytes with the first 12 bytes set to zero.

    Args:
        data: Binary data to read from
        offset: Byte offset to start reading from
        is_ipv6: True if IPv6 flag is set in peer header

    Returns:
        IP address as string

    Raises:
        ValueError: If not enough data available
    """
    if len(data) < offset + 16:
        raise ValueError(
            f"Not enough data to read IP address at offset {offset}: "
            f"need {offset + 16} bytes, got {len(data)}"
        )

    addr_bytes = data[offset : offset + 16]

    # Check if IPv6 or IPv4-mapped
    if is_ipv6 or any(addr_bytes[:12]):
        # True IPv6 address
        return str(ipaddress.IPv6Address(addr_bytes))
    else:
        # IPv4-mapped: last 4 bytes contain IPv4
        return str(ipaddress.IPv4Address(addr_bytes[12:16]))
