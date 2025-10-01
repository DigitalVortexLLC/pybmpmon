"""BMP message parser implementation."""

from pybmpmon.protocol.bmp import (
    BMP_CURRENT_VERSION,
    BMP_HEADER_SIZE,
    BMP_PER_PEER_HEADER_SIZE,
    BMPHeader,
    BMPInfoTLV,
    BMPInitiationMessage,
    BMPMessageType,
    BMPParseError,
    BMPPeerDownMessage,
    BMPPeerDownReason,
    BMPPeerFlags,
    BMPPeerType,
    BMPPeerUpMessage,
    BMPPerPeerHeader,
    BMPRouteMonitoringMessage,
    BMPStatisticsReportMessage,
    BMPStatTLV,
    BMPTerminationMessage,
)
from pybmpmon.utils.binary import (
    read_bytes,
    read_ip_address,
    read_ipv4_address,
    read_uint8,
    read_uint16,
    read_uint32,
)


def parse_bmp_header(data: bytes) -> BMPHeader:
    """
    Parse BMP common header from binary data.

    Per RFC7854 Section 4.1, the BMP header structure is:
        - Version (1 byte): BMP protocol version (must be 3)
        - Message Length (4 bytes): Total message length in bytes
        - Message Type (1 byte): Type of BMP message (0-5)

    Args:
        data: Binary data containing at least the 6-byte BMP header

    Returns:
        Parsed BMP header

    Raises:
        BMPParseError: If header is invalid or malformed
    """
    # Validate minimum size
    if len(data) < BMP_HEADER_SIZE:
        raise BMPParseError(
            f"Message too short: need at least {BMP_HEADER_SIZE} bytes for header, "
            f"got {len(data)} bytes"
        )

    try:
        # Parse version (byte 0)
        version = read_uint8(data, 0)

        # Validate version
        if version != BMP_CURRENT_VERSION:
            raise BMPParseError(
                f"Invalid BMP version: expected {BMP_CURRENT_VERSION}, got {version}"
            )

        # Parse message length (bytes 1-4, network order)
        length = read_uint32(data, 1)

        # Validate message length
        if length < BMP_HEADER_SIZE:
            raise BMPParseError(
                f"Invalid message length: {length} bytes is less than minimum "
                f"header size of {BMP_HEADER_SIZE} bytes"
            )

        # Parse message type (byte 5)
        msg_type_raw = read_uint8(data, 5)

        # Validate message type
        try:
            msg_type = BMPMessageType(msg_type_raw)
        except ValueError as e:
            raise BMPParseError(
                f"Unknown message type: {msg_type_raw} "
                f"(valid types: 0-{max(BMPMessageType)})"
            ) from e

        return BMPHeader(version=version, length=length, msg_type=msg_type)

    except ValueError as e:
        # Convert binary parsing errors to BMPParseError
        raise BMPParseError(f"Failed to parse BMP header: {e}") from e


def parse_per_peer_header(data: bytes, offset: int = 0) -> BMPPerPeerHeader:
    """
    Parse BMP Per-Peer Header from binary data.

    Per RFC7854 Section 4.2, the Per-Peer Header is 42 bytes and contains:
        - Peer Type (1 byte)
        - Peer Flags (1 byte)
        - Peer Distinguisher (8 bytes)
        - Peer Address (16 bytes)
        - Peer AS (4 bytes)
        - Peer BGP ID (4 bytes)
        - Timestamp Seconds (4 bytes)
        - Timestamp Microseconds (4 bytes)

    Args:
        data: Binary data containing the per-peer header
        offset: Byte offset to start parsing from

    Returns:
        Parsed per-peer header

    Raises:
        BMPParseError: If header is invalid or malformed
    """
    if len(data) < offset + BMP_PER_PEER_HEADER_SIZE:
        raise BMPParseError(
            f"Message too short for Per-Peer Header: need {BMP_PER_PEER_HEADER_SIZE} "
            f"bytes at offset {offset}, got {len(data) - offset} bytes"
        )

    try:
        # Parse peer type and flags
        peer_type_raw = read_uint8(data, offset)
        peer_flags = read_uint8(data, offset + 1)

        # Validate peer type
        try:
            peer_type = BMPPeerType(peer_type_raw)
        except ValueError as e:
            raise BMPParseError(f"Invalid peer type: {peer_type_raw}") from e

        # Parse peer distinguisher (8 bytes)
        peer_distinguisher = read_bytes(data, offset + 2, 8)

        # Parse peer address (16 bytes) - check IPv6 flag
        is_ipv6 = bool(peer_flags & BMPPeerFlags.IPV6)
        peer_address = read_ip_address(data, offset + 10, is_ipv6)

        # Parse peer AS (4 bytes)
        peer_asn = read_uint32(data, offset + 26)

        # Parse peer BGP ID (4 bytes) as IPv4 address
        peer_bgp_id = read_ipv4_address(data, offset + 30)

        # Parse timestamp
        timestamp_sec = read_uint32(data, offset + 34)
        timestamp_usec = read_uint32(data, offset + 38)

        return BMPPerPeerHeader(
            peer_type=peer_type,
            peer_flags=peer_flags,
            peer_distinguisher=peer_distinguisher,
            peer_address=peer_address,
            peer_asn=peer_asn,
            peer_bgp_id=peer_bgp_id,
            timestamp_sec=timestamp_sec,
            timestamp_usec=timestamp_usec,
        )

    except ValueError as e:
        raise BMPParseError(f"Failed to parse Per-Peer Header: {e}") from e


def parse_information_tlvs(data: bytes, offset: int, end: int) -> list[BMPInfoTLV]:
    """
    Parse Information TLVs from BMP Initiation/Termination messages.

    TLV format per RFC7854 Section 4.4:
        - Information Type (2 bytes)
        - Information Length (2 bytes)
        - Information Value (variable)

    Args:
        data: Binary data containing TLVs
        offset: Starting offset
        end: End offset (exclusive)

    Returns:
        List of parsed Information TLVs

    Raises:
        BMPParseError: If TLVs are malformed
    """
    tlvs: list[BMPInfoTLV] = []
    pos = offset

    while pos < end:
        # Need at least 4 bytes for TLV header
        if pos + 4 > end:
            raise BMPParseError(
                f"Incomplete TLV header at offset {pos}: "
                f"need 4 bytes, got {end - pos}"
            )

        try:
            info_type = read_uint16(data, pos)
            info_length = read_uint16(data, pos + 2)

            # Check if we have enough data for the value
            if pos + 4 + info_length > end:
                raise BMPParseError(
                    f"Incomplete TLV value at offset {pos}: "
                    f"need {info_length} bytes, got {end - pos - 4}"
                )

            info_value = read_bytes(data, pos + 4, info_length)

            tlvs.append(
                BMPInfoTLV(
                    info_type=info_type, info_length=info_length, info_value=info_value
                )
            )

            pos += 4 + info_length

        except ValueError as e:
            raise BMPParseError(f"Failed to parse TLV at offset {pos}: {e}") from e

    return tlvs


def parse_initiation_message(data: bytes) -> BMPInitiationMessage:
    """
    Parse BMP Initiation Message per RFC7854 Section 4.3.

    Args:
        data: Complete BMP message including header

    Returns:
        Parsed Initiation message

    Raises:
        BMPParseError: If message is malformed
    """
    header = parse_bmp_header(data)

    if header.msg_type != BMPMessageType.INITIATION:
        raise BMPParseError(
            f"Expected INITIATION message type, got {header.msg_type.name}"
        )

    # Parse Information TLVs from offset 6 to end of message
    tlvs = parse_information_tlvs(data, BMP_HEADER_SIZE, header.length)

    return BMPInitiationMessage(header=header, information_tlvs=tlvs)


def parse_termination_message(data: bytes) -> BMPTerminationMessage:
    """
    Parse BMP Termination Message per RFC7854 Section 4.4.

    Args:
        data: Complete BMP message including header

    Returns:
        Parsed Termination message

    Raises:
        BMPParseError: If message is malformed
    """
    header = parse_bmp_header(data)

    if header.msg_type != BMPMessageType.TERMINATION:
        raise BMPParseError(
            f"Expected TERMINATION message type, got {header.msg_type.name}"
        )

    # Parse Information TLVs from offset 6 to end of message
    tlvs = parse_information_tlvs(data, BMP_HEADER_SIZE, header.length)

    return BMPTerminationMessage(header=header, information_tlvs=tlvs)


def parse_route_monitoring_message(data: bytes) -> BMPRouteMonitoringMessage:
    """
    Parse BMP Route Monitoring Message per RFC7854 Section 4.6.

    Args:
        data: Complete BMP message including header

    Returns:
        Parsed Route Monitoring message

    Raises:
        BMPParseError: If message is malformed
    """
    header = parse_bmp_header(data)

    if header.msg_type != BMPMessageType.ROUTE_MONITORING:
        raise BMPParseError(
            f"Expected ROUTE_MONITORING message type, got {header.msg_type.name}"
        )

    # Parse Per-Peer Header
    per_peer_header = parse_per_peer_header(data, BMP_HEADER_SIZE)

    # Remaining bytes are the BGP UPDATE PDU
    bgp_update_offset = BMP_HEADER_SIZE + BMP_PER_PEER_HEADER_SIZE
    bgp_update = read_bytes(data, bgp_update_offset, header.length - bgp_update_offset)

    return BMPRouteMonitoringMessage(
        header=header, per_peer_header=per_peer_header, bgp_update=bgp_update
    )


def parse_statistics_report_message(data: bytes) -> BMPStatisticsReportMessage:
    """
    Parse BMP Statistics Report Message per RFC7854 Section 4.8.

    Args:
        data: Complete BMP message including header

    Returns:
        Parsed Statistics Report message

    Raises:
        BMPParseError: If message is malformed
    """
    header = parse_bmp_header(data)

    if header.msg_type != BMPMessageType.STATISTICS_REPORT:
        raise BMPParseError(
            f"Expected STATISTICS_REPORT message type, got {header.msg_type.name}"
        )

    # Parse Per-Peer Header
    per_peer_header = parse_per_peer_header(data, BMP_HEADER_SIZE)

    # Parse stats count (4 bytes)
    stats_offset = BMP_HEADER_SIZE + BMP_PER_PEER_HEADER_SIZE
    if len(data) < stats_offset + 4:
        raise BMPParseError("Message too short for stats count")

    stats_count = read_uint32(data, stats_offset)

    # Parse statistics TLVs
    tlv_offset = stats_offset + 4
    stats_tlvs: list[BMPStatTLV] = []

    for _ in range(stats_count):
        if tlv_offset + 4 > header.length:
            raise BMPParseError(f"Incomplete stats TLV at offset {tlv_offset}")

        try:
            stat_type = read_uint16(data, tlv_offset)
            stat_length = read_uint16(data, tlv_offset + 2)

            if tlv_offset + 4 + stat_length > header.length:
                raise BMPParseError(
                    f"Stats TLV value exceeds message length at offset {tlv_offset}"
                )

            # Read stat value based on length (typically 4 or 8 bytes)
            if stat_length == 4:
                stat_value = read_uint32(data, tlv_offset + 4)
            elif stat_length == 8:
                # Read as two 32-bit values for 64-bit counter
                high = read_uint32(data, tlv_offset + 4)
                low = read_uint32(data, tlv_offset + 8)
                stat_value = (high << 32) | low
            else:
                # Unknown length, just read as bytes and convert
                stat_bytes = read_bytes(data, tlv_offset + 4, stat_length)
                stat_value = int.from_bytes(stat_bytes, byteorder="big")

            stats_tlvs.append(
                BMPStatTLV(
                    stat_type=stat_type, stat_length=stat_length, stat_value=stat_value
                )
            )

            tlv_offset += 4 + stat_length

        except ValueError as e:
            raise BMPParseError(
                f"Failed to parse stats TLV at offset {tlv_offset}: {e}"
            ) from e

    return BMPStatisticsReportMessage(
        header=header,
        per_peer_header=per_peer_header,
        stats_count=stats_count,
        stats_tlvs=stats_tlvs,
    )


def parse_peer_down_message(data: bytes) -> BMPPeerDownMessage:
    """
    Parse BMP Peer Down Notification per RFC7854 Section 4.9.

    Args:
        data: Complete BMP message including header

    Returns:
        Parsed Peer Down message

    Raises:
        BMPParseError: If message is malformed
    """
    header = parse_bmp_header(data)

    if header.msg_type != BMPMessageType.PEER_DOWN_NOTIFICATION:
        raise BMPParseError(
            f"Expected PEER_DOWN_NOTIFICATION message type, got {header.msg_type.name}"
        )

    # Parse Per-Peer Header
    per_peer_header = parse_per_peer_header(data, BMP_HEADER_SIZE)

    # Parse reason code (1 byte)
    reason_offset = BMP_HEADER_SIZE + BMP_PER_PEER_HEADER_SIZE
    if len(data) < reason_offset + 1:
        raise BMPParseError("Message too short for reason code")

    try:
        reason_raw = read_uint8(data, reason_offset)
        reason = BMPPeerDownReason(reason_raw)
    except ValueError as e:
        raise BMPParseError(f"Invalid peer down reason: {reason_raw}") from e

    # Remaining bytes are additional data (BGP notification, etc.)
    data_offset = reason_offset + 1
    additional_data = read_bytes(data, data_offset, header.length - data_offset)

    return BMPPeerDownMessage(
        header=header,
        per_peer_header=per_peer_header,
        reason=reason,
        data=additional_data,
    )


def parse_peer_up_message(data: bytes) -> BMPPeerUpMessage:
    """
    Parse BMP Peer Up Notification per RFC7854 Section 4.10.

    Args:
        data: Complete BMP message including header

    Returns:
        Parsed Peer Up message

    Raises:
        BMPParseError: If message is malformed
    """
    header = parse_bmp_header(data)

    if header.msg_type != BMPMessageType.PEER_UP_NOTIFICATION:
        raise BMPParseError(
            f"Expected PEER_UP_NOTIFICATION message type, got {header.msg_type.name}"
        )

    # Parse Per-Peer Header
    per_peer_header = parse_per_peer_header(data, BMP_HEADER_SIZE)

    # Parse local address (16 bytes)
    local_addr_offset = BMP_HEADER_SIZE + BMP_PER_PEER_HEADER_SIZE
    if len(data) < local_addr_offset + 20:  # 16 + 2 + 2
        raise BMPParseError("Message too short for Peer Up fields")

    # Determine if IPv6 based on peer flags
    is_ipv6 = bool(per_peer_header.peer_flags & BMPPeerFlags.IPV6)
    local_address = read_ip_address(data, local_addr_offset, is_ipv6)

    # Parse local and remote ports (2 bytes each)
    local_port = read_uint16(data, local_addr_offset + 16)
    remote_port = read_uint16(data, local_addr_offset + 18)

    # Parse sent OPEN message
    # BGP OPEN has a 19-byte minimum header
    sent_open_offset = local_addr_offset + 20
    if len(data) < sent_open_offset + 19:
        raise BMPParseError("Message too short for sent OPEN message")

    # Read BGP message length from OPEN header (bytes 16-17)
    sent_open_length = read_uint16(data, sent_open_offset + 16)
    if len(data) < sent_open_offset + sent_open_length:
        raise BMPParseError("Message too short for complete sent OPEN message")

    sent_open_message = read_bytes(data, sent_open_offset, sent_open_length)

    # Parse received OPEN message
    recv_open_offset = sent_open_offset + sent_open_length
    if len(data) < recv_open_offset + 19:
        raise BMPParseError("Message too short for received OPEN message")

    recv_open_length = read_uint16(data, recv_open_offset + 16)
    if len(data) < recv_open_offset + recv_open_length:
        raise BMPParseError("Message too short for complete received OPEN message")

    received_open_message = read_bytes(data, recv_open_offset, recv_open_length)

    # Parse optional Information TLVs (remaining bytes)
    tlv_offset = recv_open_offset + recv_open_length
    information_tlvs = parse_information_tlvs(data, tlv_offset, header.length)

    return BMPPeerUpMessage(
        header=header,
        per_peer_header=per_peer_header,
        local_address=local_address,
        local_port=local_port,
        remote_port=remote_port,
        sent_open_message=sent_open_message,
        received_open_message=received_open_message,
        information_tlvs=information_tlvs,
    )


def parse_bmp_message(
    data: bytes,
) -> (
    BMPInitiationMessage
    | BMPTerminationMessage
    | BMPRouteMonitoringMessage
    | BMPStatisticsReportMessage
    | BMPPeerDownMessage
    | BMPPeerUpMessage
):
    """
    Parse a complete BMP message and return the appropriate message type.

    Args:
        data: Complete BMP message binary data

    Returns:
        Parsed BMP message of the appropriate type

    Raises:
        BMPParseError: If message cannot be parsed
    """
    # Parse header first to determine message type
    header = parse_bmp_header(data)

    # Validate we have the complete message
    if len(data) < header.length:
        raise BMPParseError(
            f"Incomplete message: expected {header.length} bytes, got {len(data)}"
        )

    # Dispatch to appropriate parser based on message type
    if header.msg_type == BMPMessageType.INITIATION:
        return parse_initiation_message(data)
    elif header.msg_type == BMPMessageType.TERMINATION:
        return parse_termination_message(data)
    elif header.msg_type == BMPMessageType.ROUTE_MONITORING:
        return parse_route_monitoring_message(data)
    elif header.msg_type == BMPMessageType.STATISTICS_REPORT:
        return parse_statistics_report_message(data)
    elif header.msg_type == BMPMessageType.PEER_DOWN_NOTIFICATION:
        return parse_peer_down_message(data)
    elif header.msg_type == BMPMessageType.PEER_UP_NOTIFICATION:
        return parse_peer_up_message(data)
    else:
        # This should never happen due to header validation
        raise BMPParseError(f"Unhandled message type: {header.msg_type}")
