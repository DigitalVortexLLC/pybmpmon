"""BGP UPDATE message parser implementation."""

from ipaddress import IPv4Address, IPv6Address
from typing import Any

from pybmpmon.protocol.bgp import (
    ATTR_FLAG_EXTENDED_LENGTH,
    BGP_HEADER_SIZE,
    BGP_MARKER,
    AddressFamilyIdentifier,
    BGPASPathSegmentType,
    BGPHeader,
    BGPMessageType,
    BGPParseError,
    BGPPathAttribute,
    BGPPathAttributeType,
    BGPUpdateMessage,
    ParsedBGPUpdate,
    SubsequentAddressFamilyIdentifier,
)
from pybmpmon.utils.binary import read_bytes, read_uint8, read_uint16, read_uint32


def parse_bgp_header(data: bytes) -> BGPHeader:
    """
    Parse BGP message header.

    Args:
        data: Binary data containing BGP header

    Returns:
        Parsed BGP header

    Raises:
        BGPParseError: If header is invalid
    """
    if len(data) < BGP_HEADER_SIZE:
        raise BGPParseError(
            f"Message too short: need {BGP_HEADER_SIZE} bytes, got {len(data)}"
        )

    marker = read_bytes(data, 0, 16)
    if marker != BGP_MARKER:
        raise BGPParseError("Invalid BGP marker")

    length = read_uint16(data, 16)
    msg_type_raw = read_uint8(data, 18)

    try:
        msg_type = BGPMessageType(msg_type_raw)
    except ValueError as e:
        raise BGPParseError(f"Invalid BGP message type: {msg_type_raw}") from e

    return BGPHeader(marker=marker, length=length, msg_type=msg_type)


def parse_bgp_update_structure(data: bytes) -> BGPUpdateMessage:
    """
    Parse BGP UPDATE message structure (RFC4271 Section 4.3).

    Args:
        data: Complete BGP UPDATE message including header

    Returns:
        Parsed BGP UPDATE message structure

    Raises:
        BGPParseError: If message is malformed
    """
    header = parse_bgp_header(data)

    if header.msg_type != BGPMessageType.UPDATE:
        raise BGPParseError(f"Expected UPDATE message, got {header.msg_type.name}")

    if len(data) < header.length:
        raise BGPParseError(
            f"Incomplete message: expected {header.length} bytes, got {len(data)}"
        )

    offset = BGP_HEADER_SIZE

    # Parse withdrawn routes length (2 bytes)
    if offset + 2 > header.length:
        raise BGPParseError("Message too short for withdrawn routes length")

    withdrawn_routes_length = read_uint16(data, offset)
    offset += 2

    # Parse withdrawn routes
    if offset + withdrawn_routes_length > header.length:
        raise BGPParseError("Message too short for withdrawn routes")

    withdrawn_routes = read_bytes(data, offset, withdrawn_routes_length)
    offset += withdrawn_routes_length

    # Parse total path attribute length (2 bytes)
    if offset + 2 > header.length:
        raise BGPParseError("Message too short for path attribute length")

    total_path_attr_length = read_uint16(data, offset)
    offset += 2

    # Parse path attributes
    path_attrs_end = offset + total_path_attr_length
    if path_attrs_end > header.length:
        raise BGPParseError("Message too short for path attributes")

    path_attributes = parse_path_attributes(data, offset, path_attrs_end)
    offset = path_attrs_end

    # Remaining data is NLRI
    nlri = read_bytes(data, offset, header.length - offset)

    return BGPUpdateMessage(
        withdrawn_routes_length=withdrawn_routes_length,
        withdrawn_routes=withdrawn_routes,
        total_path_attr_length=total_path_attr_length,
        path_attributes=path_attributes,
        nlri=nlri,
    )


def parse_path_attributes(data: bytes, start: int, end: int) -> list[BGPPathAttribute]:
    """
    Parse BGP path attributes.

    Args:
        data: Binary data containing path attributes
        start: Starting offset
        end: Ending offset (exclusive)

    Returns:
        List of parsed path attributes

    Raises:
        BGPParseError: If attributes are malformed
    """
    attributes: list[BGPPathAttribute] = []
    offset = start

    while offset < end:
        # Need at least 3 bytes (flags, type, length)
        if offset + 3 > end:
            raise BGPParseError(f"Incomplete path attribute at offset {offset}")

        flags = read_uint8(data, offset)
        type_code_raw = read_uint8(data, offset + 1)

        try:
            type_code = BGPPathAttributeType(type_code_raw)
        except ValueError:
            # Unknown attribute type - create a placeholder
            # We'll store the raw value instead of failing
            type_code = type_code_raw  # type: ignore[assignment]

        # Check if extended length flag is set
        if flags & ATTR_FLAG_EXTENDED_LENGTH:
            if offset + 4 > end:
                raise BGPParseError("Incomplete extended length attribute")
            length = read_uint16(data, offset + 2)
            value_offset = offset + 4
        else:
            length = read_uint8(data, offset + 2)
            value_offset = offset + 3

        if value_offset + length > end:
            raise BGPParseError("Attribute value exceeds message bounds")

        value = read_bytes(data, value_offset, length)

        attributes.append(
            BGPPathAttribute(
                flags=flags, type_code=type_code, length=length, value=value
            )
        )

        offset = value_offset + length

    return attributes


def parse_ipv4_prefix(data: bytes, offset: int) -> tuple[str, int]:
    """
    Parse IPv4 prefix in BGP format (length + prefix bytes).

    Args:
        data: Binary data
        offset: Starting offset

    Returns:
        Tuple of (prefix_string, bytes_consumed)

    Raises:
        BGPParseError: If prefix is malformed
    """
    if offset >= len(data):
        raise BGPParseError("No data for IPv4 prefix")

    prefix_len = read_uint8(data, offset)
    if prefix_len > 32:
        raise BGPParseError(f"Invalid IPv4 prefix length: {prefix_len}")

    # Calculate number of bytes needed for prefix
    prefix_bytes = (prefix_len + 7) // 8
    if offset + 1 + prefix_bytes > len(data):
        raise BGPParseError("Incomplete IPv4 prefix")

    # Read prefix bytes and pad to 4 bytes
    prefix_data = read_bytes(data, offset + 1, prefix_bytes)
    prefix_data = prefix_data + b"\x00" * (4 - prefix_bytes)

    prefix_ip = str(IPv4Address(prefix_data))
    return f"{prefix_ip}/{prefix_len}", 1 + prefix_bytes


def parse_ipv6_prefix(data: bytes, offset: int) -> tuple[str, int]:
    """
    Parse IPv6 prefix in BGP format (length + prefix bytes).

    Args:
        data: Binary data
        offset: Starting offset

    Returns:
        Tuple of (prefix_string, bytes_consumed)

    Raises:
        BGPParseError: If prefix is malformed
    """
    if offset >= len(data):
        raise BGPParseError("No data for IPv6 prefix")

    prefix_len = read_uint8(data, offset)
    if prefix_len > 128:
        raise BGPParseError(f"Invalid IPv6 prefix length: {prefix_len}")

    # Calculate number of bytes needed for prefix
    prefix_bytes = (prefix_len + 7) // 8
    if offset + 1 + prefix_bytes > len(data):
        raise BGPParseError("Incomplete IPv6 prefix")

    # Read prefix bytes and pad to 16 bytes
    prefix_data = read_bytes(data, offset + 1, prefix_bytes)
    prefix_data = prefix_data + b"\x00" * (16 - prefix_bytes)

    prefix_ip = str(IPv6Address(prefix_data))
    return f"{prefix_ip}/{prefix_len}", 1 + prefix_bytes


def parse_as_path(value: bytes) -> list[int]:
    """
    Parse AS_PATH attribute.

    Args:
        value: AS_PATH attribute value

    Returns:
        List of AS numbers in path order

    Raises:
        BGPParseError: If AS_PATH is malformed
    """
    as_path: list[int] = []
    offset = 0

    while offset < len(value):
        if offset + 2 > len(value):
            raise BGPParseError("Incomplete AS_PATH segment")

        segment_type = read_uint8(value, offset)
        segment_length = read_uint8(value, offset + 1)
        offset += 2

        # Detect AS size: calculate remaining bytes and divide by segment length
        # Modern BGP uses 4-byte AS numbers (RFC 6793), legacy uses 2-byte
        remaining_bytes = len(value) - offset
        if segment_length > 0:
            bytes_per_as = remaining_bytes // segment_length
            # Should be either 2 or 4 bytes per AS
            if bytes_per_as == 4:
                as_size = 4
            elif bytes_per_as == 2:
                as_size = 2
            else:
                # Try to determine from first segment
                as_size = 4 if remaining_bytes >= segment_length * 4 else 2
        else:
            as_size = 4  # Default to 4-byte for empty segments

        if offset + (segment_length * as_size) > len(value):
            raise BGPParseError("Incomplete AS_PATH segment data")

        for _ in range(segment_length):
            if as_size == 4:
                as_num = read_uint32(value, offset)
            else:
                as_num = read_uint16(value, offset)
            if segment_type == BGPASPathSegmentType.AS_SEQUENCE:
                as_path.append(as_num)
            elif segment_type == BGPASPathSegmentType.AS_SET:
                # For AS_SET, we still add to path but note it's a set
                as_path.append(as_num)
            offset += as_size

    return as_path


def parse_communities(value: bytes) -> list[str]:
    """
    Parse COMMUNITIES attribute.

    Args:
        value: COMMUNITIES attribute value

    Returns:
        List of community strings in "AS:value" format

    Raises:
        BGPParseError: If COMMUNITIES is malformed
    """
    if len(value) % 4 != 0:
        raise BGPParseError("Invalid COMMUNITIES length (must be multiple of 4)")

    communities: list[str] = []
    offset = 0

    while offset < len(value):
        as_num = read_uint16(value, offset)
        comm_value = read_uint16(value, offset + 2)
        communities.append(f"{as_num}:{comm_value}")
        offset += 4

    return communities


def parse_extended_communities(value: bytes) -> list[str]:
    """
    Parse EXTENDED_COMMUNITIES attribute (RFC4360).

    Extended communities are 8-byte values with various types:
    - Type 0x00/0x02: Two-octet AS Route Target/Origin (AS:value)
    - Type 0x01/0x03: IPv4 Address Route Target/Origin (IP:value)
    - Type 0x02/0x0a: Four-octet AS Route Target/Origin (AS:value)
    - Type 0x03/0x0b: Opaque Extended Community
    - Type 0x06: EVPN (various subtypes)
    - Type 0x08: Flow spec redirect
    - Type 0x80+: Experimental

    Args:
        value: EXTENDED_COMMUNITIES attribute value

    Returns:
        List of extended community strings

    Raises:
        BGPParseError: If EXTENDED_COMMUNITIES is malformed
    """
    if len(value) % 8 != 0:
        raise BGPParseError(
            "Invalid EXTENDED_COMMUNITIES length (must be multiple of 8)"
        )

    extended_communities: list[str] = []
    offset = 0

    while offset < len(value):
        ext_type = read_uint8(value, offset)
        ext_subtype = read_uint8(value, offset + 1)

        # OSPF Domain ID (0x03, subtype 0x0c) - check before IPv4 Route Origin
        if ext_type == 0x03 and ext_subtype == 0x0C:
            domain_bytes = read_bytes(value, offset + 2, 6)
            # Last 4 bytes are the domain ID
            domain_id_bytes = domain_bytes[2:6]
            domain_id = str(IPv4Address(domain_id_bytes))
            extended_communities.append(f"OSPF-Domain:{domain_id}")

        # Two-octet AS specific (0x00 = Route Target, 0x02 = Route Origin)
        elif ext_type == 0x00 and ext_subtype == 0x02:
            as_num = read_uint16(value, offset + 2)
            assigned = read_uint32(value, offset + 4)
            extended_communities.append(f"RT:{as_num}:{assigned}")

        elif ext_type == 0x02 and ext_subtype == 0x00:
            as_num = read_uint16(value, offset + 2)
            assigned = read_uint32(value, offset + 4)
            extended_communities.append(f"RO:{as_num}:{assigned}")

        # IPv4 Address specific (0x01 = Route Target, 0x03 = Route Origin)
        elif ext_type == 0x01 and ext_subtype == 0x02:
            ip_bytes = read_bytes(value, offset + 2, 4)
            ip = str(IPv4Address(ip_bytes))
            assigned = read_uint16(value, offset + 6)
            extended_communities.append(f"RT:{ip}:{assigned}")

        elif ext_type == 0x03 and ext_subtype == 0x00:
            ip_bytes = read_bytes(value, offset + 2, 4)
            ip = str(IPv4Address(ip_bytes))
            assigned = read_uint16(value, offset + 6)
            extended_communities.append(f"RO:{ip}:{assigned}")

        # Four-octet AS specific (0x02 = Route Target, 0x0a = Route Origin)
        elif ext_type == 0x02 and ext_subtype == 0x02:
            as_num = read_uint32(value, offset + 2)
            assigned = read_uint16(value, offset + 6)
            extended_communities.append(f"RT:{as_num}:{assigned}")

        elif ext_type == 0x0A and ext_subtype == 0x02:
            as_num = read_uint32(value, offset + 2)
            assigned = read_uint16(value, offset + 6)
            extended_communities.append(f"RO:{as_num}:{assigned}")

        # Opaque Extended Community (0x03)
        elif ext_type == 0x03:
            opaque_value = read_bytes(value, offset + 2, 6)
            extended_communities.append(f"Opaque:{opaque_value.hex()}")

        # EVPN Extended Community (0x06)
        elif ext_type == 0x06:
            # Common EVPN subtypes:
            # 0x00 = MAC Mobility
            # 0x01 = ESI Label
            # 0x02 = ES-Import Route Target
            if ext_subtype == 0x00:
                # MAC Mobility: flags (1) + seq (4) + reserved (1)
                _ = read_uint8(value, offset + 2)  # flags (unused for now)
                seq = read_uint32(value, offset + 3)
                extended_communities.append(f"EVPN-MAC-Mobility:{seq}")
            elif ext_subtype == 0x01:
                # ESI Label: flags (1) + reserved (2) + label (3)
                label_bytes = read_bytes(value, offset + 5, 3)
                label = (
                    (label_bytes[0] << 12)
                    | (label_bytes[1] << 4)
                    | (label_bytes[2] >> 4)
                )
                extended_communities.append(f"EVPN-ESI-Label:{label}")
            elif ext_subtype == 0x02:
                # ES-Import RT: MAC address (6 bytes)
                mac_bytes = read_bytes(value, offset + 2, 6)
                mac = ":".join(f"{b:02x}" for b in mac_bytes)
                extended_communities.append(f"EVPN-ES-Import:{mac}")
            else:
                # Unknown EVPN subtype
                evpn_value = read_bytes(value, offset + 2, 6)
                extended_communities.append(
                    f"EVPN-{ext_subtype:02x}:{evpn_value.hex()}"
                )

        # Flow spec redirect (0x08)
        elif ext_type == 0x08:
            as_num = read_uint16(value, offset + 2)
            assigned = read_uint32(value, offset + 4)
            extended_communities.append(f"Redirect:{as_num}:{assigned}")

        # Unknown or experimental types
        else:
            ext_value = read_bytes(value, offset, 8)
            extended_communities.append(f"Unknown-{ext_type:02x}:{ext_value.hex()}")

        offset += 8

    return extended_communities


def parse_route_distinguisher(value: bytes, offset: int) -> str:
    """
    Parse Route Distinguisher (8 bytes) per RFC4364.

    Args:
        value: Binary data containing RD
        offset: Starting offset

    Returns:
        RD as string in format "ASN:value" or "IP:value"

    Raises:
        BGPParseError: If RD is malformed
    """
    if len(value) < offset + 8:
        raise BGPParseError("Route Distinguisher too short")

    rd_type = read_uint16(value, offset)

    if rd_type == 0:
        # Type 0: 2-byte administrator + 4-byte assigned number
        admin = read_uint16(value, offset + 2)
        assigned = read_uint32(value, offset + 4)
        return f"{admin}:{assigned}"
    elif rd_type == 1:
        # Type 1: 4-byte IP address + 2-byte assigned number
        ip_bytes = read_bytes(value, offset + 2, 4)
        ip = str(IPv4Address(ip_bytes))
        assigned = read_uint16(value, offset + 6)
        return f"{ip}:{assigned}"
    elif rd_type == 2:
        # Type 2: 4-byte administrator + 2-byte assigned number
        admin = read_uint32(value, offset + 2)
        assigned = read_uint16(value, offset + 6)
        return f"{admin}:{assigned}"
    else:
        # Unknown type - return hex representation
        rd_bytes = read_bytes(value, offset, 8)
        return rd_bytes.hex()


def parse_ethernet_segment_id(value: bytes, offset: int) -> str:
    """
    Parse Ethernet Segment Identifier (10 bytes) per RFC7432.

    Args:
        value: Binary data containing ESI
        offset: Starting offset

    Returns:
        ESI as colon-separated hex string

    Raises:
        BGPParseError: If ESI is malformed
    """
    if len(value) < offset + 10:
        raise BGPParseError("Ethernet Segment Identifier too short")

    esi_bytes = read_bytes(value, offset, 10)
    # Format as colon-separated hex pairs
    return ":".join(f"{b:02x}" for b in esi_bytes)


def parse_evpn_nlri(value: bytes, offset: int) -> tuple[dict[str, Any] | None, int]:
    """
    Parse EVPN NLRI per RFC7432 Section 7.

    Args:
        value: Binary data containing EVPN NLRI
        offset: Starting offset

    Returns:
        Tuple of (route_info dict or None, bytes_consumed)
        route_info contains: route_type, rd, esi, mac_address, ip_address

    Raises:
        BGPParseError: If NLRI is malformed
    """
    if len(value) < offset + 2:
        return None, 0

    route_type = read_uint8(value, offset)
    length = read_uint8(value, offset + 1)

    # Check if we have enough data for the route
    if len(value) < offset + 2 + length:
        raise BGPParseError(f"EVPN NLRI truncated: need {length} bytes")

    route_offset = offset + 2

    # Type 2: MAC/IP Advertisement Route (most common)
    if route_type == 2:
        # Minimum: 8 (RD) + 10 (ESI) + 4 (Tag) + 1 (MAC len)
        #          + 6 (MAC) + 1 (IP len) + 3 (Label)
        if length < 33:
            raise BGPParseError("EVPN Type 2 NLRI too short")

        # Parse Route Distinguisher (8 bytes)
        rd = parse_route_distinguisher(value, route_offset)
        route_offset += 8

        # Parse Ethernet Segment Identifier (10 bytes)
        esi = parse_ethernet_segment_id(value, route_offset)
        route_offset += 10

        # Skip Ethernet Tag ID (4 bytes)
        route_offset += 4

        # Parse MAC Address Length (1 byte, should be 48 bits)
        mac_len = read_uint8(value, route_offset)
        route_offset += 1

        mac_address = None
        if mac_len == 48:  # 48 bits = 6 bytes
            if len(value) >= route_offset + 6:
                mac_bytes = read_bytes(value, route_offset, 6)
                mac_address = ":".join(f"{b:02x}" for b in mac_bytes)
                route_offset += 6

        # Parse IP Address Length (1 byte)
        ip_len = read_uint8(value, route_offset)
        route_offset += 1

        ip_address = None
        if ip_len == 32 and len(value) >= route_offset + 4:
            # IPv4 address
            ip_bytes = read_bytes(value, route_offset, 4)
            ip_address = str(IPv4Address(ip_bytes))
            route_offset += 4
        elif ip_len == 128 and len(value) >= route_offset + 16:
            # IPv6 address
            ip_bytes = read_bytes(value, route_offset, 16)
            ip_address = str(IPv6Address(ip_bytes))
            route_offset += 16

        # Note: MPLS labels (3 bytes each) are at the end but we don't parse them

        return {
            "route_type": route_type,
            "rd": rd,
            "esi": esi,
            "mac_address": mac_address,
            "ip_address": ip_address,
        }, 2 + length

    # For other route types, just skip for now
    return {"route_type": route_type}, 2 + length


def parse_mp_reach_nlri(
    value: bytes,
) -> tuple[int, int, str | None, list[str | dict[str, Any]]]:
    """
    Parse MP_REACH_NLRI attribute (RFC4760).

    Args:
        value: MP_REACH_NLRI attribute value

    Returns:
        Tuple of (AFI, SAFI, next_hop, prefixes)
        For EVPN routes, prefixes contains dicts with route_info
        For IPv4/IPv6 routes, prefixes contains prefix strings

    Raises:
        BGPParseError: If attribute is malformed
    """
    if len(value) < 5:
        raise BGPParseError("MP_REACH_NLRI too short")

    afi = read_uint16(value, 0)
    safi = read_uint8(value, 2)
    next_hop_len = read_uint8(value, 3)

    if len(value) < 4 + next_hop_len + 1:
        raise BGPParseError("MP_REACH_NLRI incomplete")

    # Parse next hop
    next_hop_data = read_bytes(value, 4, next_hop_len)
    next_hop: str | None = None

    if afi == AddressFamilyIdentifier.IPV4:
        if next_hop_len >= 4:
            next_hop = str(IPv4Address(next_hop_data[:4]))
    elif afi == AddressFamilyIdentifier.IPV6:
        if next_hop_len >= 16:
            next_hop = str(IPv6Address(next_hop_data[:16]))
    elif afi == AddressFamilyIdentifier.L2VPN:
        # L2VPN (EVPN) can have IPv4 or IPv6 next hop
        if next_hop_len == 4:
            next_hop = str(IPv4Address(next_hop_data[:4]))
        elif next_hop_len == 16:
            next_hop = str(IPv6Address(next_hop_data[:16]))

    # Reserved byte
    offset = 4 + next_hop_len + 1

    # Parse NLRI based on AFI/SAFI
    prefixes: list[str | dict[str, Any]] = []

    if (
        afi == AddressFamilyIdentifier.IPV4
        and safi == SubsequentAddressFamilyIdentifier.UNICAST
    ):
        while offset < len(value):
            prefix, consumed = parse_ipv4_prefix(value, offset)
            prefixes.append(prefix)
            offset += consumed
    elif (
        afi == AddressFamilyIdentifier.IPV6
        and safi == SubsequentAddressFamilyIdentifier.UNICAST
    ):
        while offset < len(value):
            prefix, consumed = parse_ipv6_prefix(value, offset)
            prefixes.append(prefix)
            offset += consumed
    elif (
        afi == AddressFamilyIdentifier.L2VPN
        and safi == SubsequentAddressFamilyIdentifier.EVPN
    ):
        # Parse EVPN NLRI - returns dicts with route_info
        while offset < len(value):
            route_info, consumed = parse_evpn_nlri(value, offset)
            if route_info:
                prefixes.append(route_info)
            if consumed == 0:
                break  # Avoid infinite loop
            offset += consumed

    return afi, safi, next_hop, prefixes


def parse_mp_unreach_nlri(
    value: bytes,
) -> tuple[int, int, list[str | dict[str, Any]]]:
    """
    Parse MP_UNREACH_NLRI attribute (RFC4760).

    Args:
        value: MP_UNREACH_NLRI attribute value

    Returns:
        Tuple of (AFI, SAFI, withdrawn_prefixes)
        For EVPN routes, withdrawn_prefixes contains dicts with route_info
        For IPv4/IPv6 routes, withdrawn_prefixes contains prefix strings

    Raises:
        BGPParseError: If attribute is malformed
    """
    if len(value) < 3:
        raise BGPParseError("MP_UNREACH_NLRI too short")

    afi = read_uint16(value, 0)
    safi = read_uint8(value, 2)
    offset = 3

    # Parse withdrawn routes based on AFI/SAFI
    prefixes: list[str | dict[str, Any]] = []

    if (
        afi == AddressFamilyIdentifier.IPV4
        and safi == SubsequentAddressFamilyIdentifier.UNICAST
    ):
        while offset < len(value):
            prefix, consumed = parse_ipv4_prefix(value, offset)
            prefixes.append(prefix)
            offset += consumed
    elif (
        afi == AddressFamilyIdentifier.IPV6
        and safi == SubsequentAddressFamilyIdentifier.UNICAST
    ):
        while offset < len(value):
            prefix, consumed = parse_ipv6_prefix(value, offset)
            prefixes.append(prefix)
            offset += consumed
    elif (
        afi == AddressFamilyIdentifier.L2VPN
        and safi == SubsequentAddressFamilyIdentifier.EVPN
    ):
        # Parse EVPN NLRI withdrawals - returns dicts with route_info
        while offset < len(value):
            route_info, consumed = parse_evpn_nlri(value, offset)
            if route_info:
                prefixes.append(route_info)
            if consumed == 0:
                break  # Avoid infinite loop
            offset += consumed

    return afi, safi, prefixes


def parse_bgp_update(data: bytes) -> ParsedBGPUpdate:
    """
    Parse complete BGP UPDATE message and extract route information.

    Args:
        data: Complete BGP UPDATE message including header

    Returns:
        Parsed BGP UPDATE with all route information

    Raises:
        BGPParseError: If message cannot be parsed
    """
    update = parse_bgp_update_structure(data)

    # Initialize parsed data
    afi: int | None = None
    safi: int | None = None
    prefixes: list[str | dict[str, Any]] = []
    withdrawn_prefixes: list[str | dict[str, Any]] = []
    origin: int | None = None
    as_path: list[int] | None = None
    next_hop: str | None = None
    med: int | None = None
    local_pref: int | None = None
    communities: list[str] | None = None
    extended_communities: list[str] | None = None
    evpn_route_type: int | None = None
    evpn_rd: str | None = None
    evpn_esi: str | None = None
    mac_address: str | None = None
    has_mp_unreach: bool = False

    # Parse withdrawn routes (IPv4 only in standard UPDATE)
    offset = 0
    while offset < len(update.withdrawn_routes):
        prefix, consumed = parse_ipv4_prefix(update.withdrawn_routes, offset)
        withdrawn_prefixes.append(prefix)
        offset += consumed

    # Parse path attributes
    for attr in update.path_attributes:
        try:
            if attr.type_code == BGPPathAttributeType.ORIGIN:
                origin = read_uint8(attr.value, 0)
            elif attr.type_code == BGPPathAttributeType.AS_PATH:
                as_path = parse_as_path(attr.value)
            elif attr.type_code == BGPPathAttributeType.NEXT_HOP:
                if len(attr.value) >= 4:
                    next_hop = str(IPv4Address(attr.value[:4]))
            elif attr.type_code == BGPPathAttributeType.MULTI_EXIT_DISC:
                med = read_uint32(attr.value, 0)
            elif attr.type_code == BGPPathAttributeType.LOCAL_PREF:
                local_pref = read_uint32(attr.value, 0)
            elif attr.type_code == BGPPathAttributeType.COMMUNITIES:
                communities = parse_communities(attr.value)
            elif attr.type_code == BGPPathAttributeType.EXTENDED_COMMUNITIES:
                extended_communities = parse_extended_communities(attr.value)
            elif attr.type_code == BGPPathAttributeType.MP_REACH_NLRI:
                afi, safi, mp_next_hop, mp_prefixes = parse_mp_reach_nlri(attr.value)
                if mp_next_hop:
                    next_hop = mp_next_hop

                # For EVPN routes, extract fields from route_info dict
                if (
                    afi == AddressFamilyIdentifier.L2VPN
                    and safi == SubsequentAddressFamilyIdentifier.EVPN
                    and mp_prefixes
                ):
                    # Extract EVPN fields from first route
                    first_route = mp_prefixes[0]
                    if isinstance(first_route, dict):
                        evpn_route_type = first_route.get("route_type")
                        evpn_rd = first_route.get("rd")
                        evpn_esi = first_route.get("esi")
                        mac_address = first_route.get("mac_address")

                prefixes.extend(mp_prefixes)
            elif attr.type_code == BGPPathAttributeType.MP_UNREACH_NLRI:
                afi, safi, mp_withdrawn = parse_mp_unreach_nlri(attr.value)
                has_mp_unreach = True

                # For EVPN withdrawals, extract fields from route_info dict
                if (
                    afi == AddressFamilyIdentifier.L2VPN
                    and safi == SubsequentAddressFamilyIdentifier.EVPN
                    and mp_withdrawn
                ):
                    # Extract EVPN fields from first route
                    first_route = mp_withdrawn[0]
                    if isinstance(first_route, dict):
                        evpn_route_type = first_route.get("route_type")
                        evpn_rd = first_route.get("rd")
                        evpn_esi = first_route.get("esi")
                        mac_address = first_route.get("mac_address")

                withdrawn_prefixes.extend(mp_withdrawn)
        except Exception:
            # Skip malformed attributes
            continue

    # Parse NLRI (IPv4 unicast routes in standard UPDATE)
    if len(update.nlri) > 0:
        afi = AddressFamilyIdentifier.IPV4
        safi = SubsequentAddressFamilyIdentifier.UNICAST
        offset = 0
        while offset < len(update.nlri):
            prefix, consumed = parse_ipv4_prefix(update.nlri, offset)
            prefixes.append(prefix)
            offset += consumed

    # Determine if this is a withdrawal
    # A message is a withdrawal if:
    # 1. It has withdrawn routes, OR
    # 2. It has MP_UNREACH_NLRI (even with no actual NLRI) and no announced routes
    is_withdrawal = len(withdrawn_prefixes) > 0 or (
        has_mp_unreach and len(prefixes) == 0
    )

    return ParsedBGPUpdate(
        afi=afi,
        safi=safi,
        prefixes=prefixes,
        withdrawn_prefixes=withdrawn_prefixes,
        is_withdrawal=is_withdrawal,
        origin=origin,
        as_path=as_path,
        next_hop=next_hop,
        med=med,
        local_pref=local_pref,
        communities=communities,
        extended_communities=extended_communities,
        evpn_route_type=evpn_route_type,
        evpn_rd=evpn_rd,
        evpn_esi=evpn_esi,
        mac_address=mac_address,
    )
