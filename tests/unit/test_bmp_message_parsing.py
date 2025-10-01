"""Comprehensive tests for BMP message parsing (Phase 2)."""

import pytest
from pybmpmon.protocol.bmp import (
    BMPMessageType,
    BMPParseError,
    BMPPeerDownReason,
    BMPPeerFlags,
    BMPPeerType,
)
from pybmpmon.protocol.bmp_parser import (
    parse_bmp_message,
    parse_initiation_message,
    parse_peer_down_message,
    parse_peer_up_message,
    parse_per_peer_header,
    parse_route_monitoring_message,
    parse_statistics_report_message,
    parse_termination_message,
)


class TestPerPeerHeaderParsing:
    """Test Per-Peer Header parsing."""

    def test_parse_ipv4_peer_header(self) -> None:
        """Test parsing Per-Peer Header with IPv4 peer."""
        # Build a 48-byte message (6 header + 42 per-peer header)
        data = bytearray()

        # BMP header: version=3, length=48, type=0 (route monitoring)
        data.extend(b"\x03")  # Version
        data.extend(b"\x00\x00\x00\x30")  # Length = 48
        data.extend(b"\x00")  # Message type = ROUTE_MONITORING

        # Per-Peer Header (42 bytes)
        data.extend(b"\x00")  # Peer Type = GLOBAL_INSTANCE
        data.extend(b"\x00")  # Peer Flags = 0 (IPv4, pre-policy, 4-byte AS)
        data.extend(b"\x00" * 8)  # Peer Distinguisher
        # Peer Address (16 bytes, IPv4-mapped: 192.0.2.1)
        data.extend(b"\x00" * 12 + b"\xc0\x00\x02\x01")
        data.extend(b"\x00\x00\xfd\xe8")  # Peer AS = 65000
        data.extend(b"\xc0\x00\x02\x01")  # Peer BGP ID = 192.0.2.1
        data.extend(b"\x00\x00\x00\x01")  # Timestamp seconds = 1
        data.extend(b"\x00\x00\x00\x00")  # Timestamp microseconds = 0

        per_peer_header = parse_per_peer_header(bytes(data), offset=6)

        assert per_peer_header.peer_type == BMPPeerType.GLOBAL_INSTANCE
        assert per_peer_header.peer_flags == 0
        assert per_peer_header.peer_address == "192.0.2.1"
        assert per_peer_header.peer_asn == 65000
        assert per_peer_header.peer_bgp_id == "192.0.2.1"
        assert per_peer_header.timestamp_sec == 1
        assert per_peer_header.timestamp_usec == 0

    def test_parse_ipv6_peer_header(self) -> None:
        """Test parsing Per-Peer Header with IPv6 peer."""
        # Build a 48-byte message
        data = bytearray()

        # BMP header
        data.extend(b"\x03\x00\x00\x00\x30\x00")

        # Per-Peer Header with IPv6 flag set
        data.extend(b"\x00")  # Peer Type = GLOBAL_INSTANCE
        data.extend(b"\x80")  # Peer Flags = 0x80 (IPv6 flag set)
        data.extend(b"\x00" * 8)  # Peer Distinguisher
        # Peer Address (16 bytes): 2001:db8::1
        data.extend(
            b"\x20\x01\x0d\xb8\x00\x00\x00\x00" b"\x00\x00\x00\x00\x00\x00\x00\x01"
        )
        data.extend(b"\x00\x00\xfd\xe8")  # Peer AS = 65000
        data.extend(b"\xc0\x00\x02\x01")  # Peer BGP ID
        data.extend(b"\x00\x00\x00\x01")  # Timestamp seconds
        data.extend(b"\x00\x00\x00\x00")  # Timestamp microseconds

        per_peer_header = parse_per_peer_header(bytes(data), offset=6)

        assert per_peer_header.peer_type == BMPPeerType.GLOBAL_INSTANCE
        assert per_peer_header.peer_flags == 0x80
        assert per_peer_header.peer_address == "2001:db8::1"
        assert per_peer_header.peer_asn == 65000

    def test_parse_peer_header_too_short(self) -> None:
        """Test error when Per-Peer Header is truncated."""
        # Only 20 bytes instead of required 42
        data = b"\x03\x00\x00\x00\x1a\x00" + b"\x00" * 20

        with pytest.raises(BMPParseError, match="too short for Per-Peer Header"):
            parse_per_peer_header(data, offset=6)

    def test_parse_peer_header_invalid_type(self) -> None:
        """Test error when peer type is invalid."""
        data = bytearray()
        data.extend(b"\x03\x00\x00\x00\x30\x00")  # Header
        data.extend(b"\xff")  # Invalid peer type
        data.extend(b"\x00" * 41)  # Rest of per-peer header

        with pytest.raises(BMPParseError, match="Invalid peer type"):
            parse_per_peer_header(bytes(data), offset=6)


class TestInitiationMessage:
    """Test Initiation message parsing."""

    def test_parse_initiation_with_tlvs(self) -> None:
        """Test parsing Initiation message with Information TLVs."""
        data = bytearray()

        # TLV 1: Type=1 (SYS_DESCR), Length=6, Value="Router"
        tlv1 = b"\x00\x01"  # Type = SYS_DESCR
        tlv1 += b"\x00\x06"  # Length = 6
        tlv1 += b"Router"  # Value

        # TLV 2: Type=2 (SYS_NAME), Length=2, Value="R1"
        tlv2 = b"\x00\x02"  # Type = SYS_NAME
        tlv2 += b"\x00\x02"  # Length = 2
        tlv2 += b"R1"  # Value

        # BMP header: version=3, length=6+len(tlvs), type=4 (INITIATION)
        total_length = 6 + len(tlv1) + len(tlv2)
        data.extend(b"\x03")  # Version
        data.extend(total_length.to_bytes(4, "big"))  # Length
        data.extend(b"\x04")  # Message type = INITIATION

        # Add TLVs
        data.extend(tlv1)
        data.extend(tlv2)

        msg = parse_initiation_message(bytes(data))

        assert msg.header.msg_type == BMPMessageType.INITIATION
        assert msg.header.length == total_length
        assert len(msg.information_tlvs) == 2
        assert msg.information_tlvs[0].info_type == 1
        assert msg.information_tlvs[0].info_value == b"Router"
        assert msg.information_tlvs[1].info_type == 2
        assert msg.information_tlvs[1].info_value == b"R1"

    def test_parse_initiation_empty_tlvs(self) -> None:
        """Test parsing Initiation message with no TLVs."""
        data = b"\x03\x00\x00\x00\x06\x04"  # Header only, length=6

        msg = parse_initiation_message(data)

        assert msg.header.msg_type == BMPMessageType.INITIATION
        assert len(msg.information_tlvs) == 0

    def test_parse_initiation_wrong_type(self) -> None:
        """Test error when message type is not INITIATION."""
        data = b"\x03\x00\x00\x00\x06\x00"  # Type = ROUTE_MONITORING

        with pytest.raises(BMPParseError, match="Expected INITIATION"):
            parse_initiation_message(data)

    def test_parse_initiation_truncated_tlv(self) -> None:
        """Test error when TLV is truncated."""
        data = bytearray()
        data.extend(b"\x03\x00\x00\x00\x0c\x04")  # Header, length=12
        data.extend(b"\x00\x01")  # TLV type
        data.extend(b"\x00\x0a")  # TLV length=10 (but not enough data)

        with pytest.raises(BMPParseError, match="Incomplete TLV"):
            parse_initiation_message(bytes(data))


class TestTerminationMessage:
    """Test Termination message parsing."""

    def test_parse_termination_with_reason(self) -> None:
        """Test parsing Termination message with reason TLV."""
        data = bytearray()

        # TLV: Type=0 (STRING), Length=4, Value="Exit"
        tlv = b"\x00\x00"  # Type = STRING
        tlv += b"\x00\x04"  # Length = 4
        tlv += b"Exit"  # Value

        # BMP header
        total_length = 6 + len(tlv)
        data.extend(b"\x03")  # Version
        data.extend(total_length.to_bytes(4, "big"))
        data.extend(b"\x05")  # Type = TERMINATION

        # Add TLV
        data.extend(tlv)

        msg = parse_termination_message(bytes(data))

        assert msg.header.msg_type == BMPMessageType.TERMINATION
        assert len(msg.information_tlvs) == 1
        assert msg.information_tlvs[0].info_value == b"Exit"


class TestRouteMonitoringMessage:
    """Test Route Monitoring message parsing."""

    def test_parse_route_monitoring_message(self) -> None:
        """Test parsing Route Monitoring message."""
        data = bytearray()

        # BMP header: type=0 (ROUTE_MONITORING), length=60
        data.extend(b"\x03\x00\x00\x00\x3c\x00")

        # Per-Peer Header (42 bytes)
        data.extend(b"\x00\x00")  # Type, Flags
        data.extend(b"\x00" * 8)  # Distinguisher
        data.extend(b"\x00" * 12 + b"\xc0\x00\x02\x01")  # IPv4: 192.0.2.1
        data.extend(b"\x00\x00\xfd\xe8")  # AS 65000
        data.extend(b"\xc0\x00\x02\x01")  # BGP ID
        data.extend(b"\x00\x00\x00\x01\x00\x00\x00\x00")  # Timestamp

        # BGP UPDATE PDU (12 bytes minimum)
        data.extend(b"\xff" * 16)  # BGP marker
        data.extend(b"\x00\x17")  # Length = 23
        data.extend(b"\x02")  # Type = UPDATE
        data.extend(b"\x00\x00")  # Withdrawn routes length = 0
        data.extend(b"\x00\x00")  # Path attributes length = 0

        msg = parse_route_monitoring_message(bytes(data)[:60])

        assert msg.header.msg_type == BMPMessageType.ROUTE_MONITORING
        assert msg.per_peer_header.peer_address == "192.0.2.1"
        assert len(msg.bgp_update) > 0

    def test_parse_route_monitoring_too_short(self) -> None:
        """Test error when Route Monitoring message is too short."""
        data = b"\x03\x00\x00\x00\x20\x00" + b"\x00" * 20

        with pytest.raises(BMPParseError, match="too short"):
            parse_route_monitoring_message(data)


class TestStatisticsReportMessage:
    """Test Statistics Report message parsing."""

    def test_parse_statistics_report(self) -> None:
        """Test parsing Statistics Report message."""
        data = bytearray()

        # Calculate total length: 6 (header) + 42 (per-peer) + 4 (count) + 2*8 (2 TLVs)
        total_length = 6 + 42 + 4 + 16

        # BMP header: type=1 (STATISTICS_REPORT)
        data.extend(b"\x03")  # Version
        data.extend(total_length.to_bytes(4, "big"))  # Length
        data.extend(b"\x01")  # Type = STATISTICS_REPORT

        # Per-Peer Header (42 bytes)
        data.extend(b"\x00\x00")  # Type, Flags
        data.extend(b"\x00" * 8)  # Distinguisher
        data.extend(b"\x00" * 12 + b"\xc0\x00\x02\x01")  # IPv4
        data.extend(b"\x00\x00\xfd\xe8")  # AS
        data.extend(b"\xc0\x00\x02\x01")  # BGP ID
        data.extend(b"\x00\x00\x00\x01\x00\x00\x00\x00")  # Timestamp

        # Stats count = 2
        data.extend(b"\x00\x00\x00\x02")

        # Stat 1: Type=7 (ROUTES_ADJ_RIB_IN), Length=4, Value=1000
        data.extend(b"\x00\x07\x00\x04")
        data.extend(b"\x00\x00\x03\xe8")

        # Stat 2: Type=8 (ROUTES_LOC_RIB), Length=4, Value=950
        data.extend(b"\x00\x08\x00\x04")
        data.extend(b"\x00\x00\x03\xb6")

        msg = parse_statistics_report_message(bytes(data))

        assert msg.header.msg_type == BMPMessageType.STATISTICS_REPORT
        assert msg.stats_count == 2
        assert len(msg.stats_tlvs) == 2
        assert msg.stats_tlvs[0].stat_type == 7
        assert msg.stats_tlvs[0].stat_value == 1000
        assert msg.stats_tlvs[1].stat_type == 8
        assert msg.stats_tlvs[1].stat_value == 950

    def test_parse_statistics_with_64bit_counter(self) -> None:
        """Test parsing Statistics Report with 64-bit counter."""
        data = bytearray()

        # Length: 6 (header) + 42 (per-peer) + 4 (count) + 12 (1 TLV)
        total_length = 6 + 42 + 4 + 12

        # BMP header
        data.extend(b"\x03")  # Version
        data.extend(total_length.to_bytes(4, "big"))  # Length
        data.extend(b"\x01")  # Type = STATISTICS_REPORT

        # Per-peer header
        data.extend(b"\x00\x00" + b"\x00" * 8)
        data.extend(b"\x00" * 12 + b"\xc0\x00\x02\x01")
        data.extend(b"\x00\x00\xfd\xe8\xc0\x00\x02\x01")
        data.extend(b"\x00\x00\x00\x01\x00\x00\x00\x00")

        # Stats count = 1
        data.extend(b"\x00\x00\x00\x01")

        # Stat: Type=7, Length=8, Value=0x0000000100000000 (4294967296)
        data.extend(b"\x00\x07\x00\x08")
        data.extend(b"\x00\x00\x00\x01\x00\x00\x00\x00")

        msg = parse_statistics_report_message(bytes(data))

        assert msg.stats_tlvs[0].stat_value == 4294967296


class TestPeerDownMessage:
    """Test Peer Down message parsing."""

    def test_parse_peer_down_local_notification(self) -> None:
        """Test parsing Peer Down with local notification."""
        data = bytearray()

        # BMP header: type=2 (PEER_DOWN), length=70
        data.extend(b"\x03\x00\x00\x00\x46\x02")

        # Per-Peer Header (42 bytes)
        data.extend(b"\x00\x00" + b"\x00" * 8)
        data.extend(b"\x00" * 12 + b"\xc0\x00\x02\x01")
        data.extend(b"\x00\x00\xfd\xe8\xc0\x00\x02\x01")
        data.extend(b"\x00\x00\x00\x01\x00\x00\x00\x00")

        # Reason = 1 (LOCAL_NOTIFICATION)
        data.extend(b"\x01")

        # BGP NOTIFICATION message (21 bytes)
        data.extend(b"\xff" * 16)  # Marker
        data.extend(b"\x00\x15")  # Length = 21
        data.extend(b"\x03")  # Type = NOTIFICATION
        data.extend(b"\x06")  # Error code = Cease
        data.extend(b"\x02")  # Error subcode = Admin shutdown

        msg = parse_peer_down_message(bytes(data))

        assert msg.header.msg_type == BMPMessageType.PEER_DOWN_NOTIFICATION
        assert msg.reason == BMPPeerDownReason.LOCAL_NOTIFICATION
        assert len(msg.data) == 21

    def test_parse_peer_down_invalid_reason(self) -> None:
        """Test error with invalid peer down reason."""
        data = bytearray()
        data.extend(b"\x03\x00\x00\x00\x31\x02")  # Header
        data.extend(b"\x00\x00" + b"\x00" * 40)  # Per-peer header
        data.extend(b"\xff")  # Invalid reason

        with pytest.raises(BMPParseError, match="Invalid peer down reason"):
            parse_peer_down_message(bytes(data))


class TestPeerUpMessage:
    """Test Peer Up message parsing."""

    def test_parse_peer_up_message(self) -> None:
        """Test parsing Peer Up message."""
        data = bytearray()

        # BMP header: type=3 (PEER_UP), length=106
        data.extend(b"\x03\x00\x00\x00\x6a\x03")

        # Per-Peer Header (42 bytes)
        data.extend(b"\x00\x00" + b"\x00" * 8)
        data.extend(b"\x00" * 12 + b"\xc0\x00\x02\x01")  # Peer: 192.0.2.1
        data.extend(b"\x00\x00\xfd\xe8\xc0\x00\x02\x01")
        data.extend(b"\x00\x00\x00\x01\x00\x00\x00\x00")

        # Local address (16 bytes): 192.0.2.254
        data.extend(b"\x00" * 12 + b"\xc0\x00\x02\xfe")

        # Local port = 179, Remote port = 50000
        data.extend(b"\x00\xb3")  # 179
        data.extend(b"\xc3\x50")  # 50000

        # Sent OPEN message (29 bytes minimum)
        data.extend(b"\xff" * 16)  # Marker
        data.extend(b"\x00\x1d")  # Length = 29
        data.extend(b"\x01")  # Type = OPEN
        data.extend(b"\x04")  # Version = 4
        data.extend(b"\xfd\xe8")  # My AS = 65000
        data.extend(b"\x00\xb4")  # Hold time = 180
        data.extend(b"\xc0\x00\x02\xfe")  # BGP ID
        data.extend(b"\x00")  # Opt params len = 0

        # Received OPEN message (29 bytes)
        data.extend(b"\xff" * 16)  # Marker
        data.extend(b"\x00\x1d")  # Length = 29
        data.extend(b"\x01")  # Type = OPEN
        data.extend(b"\x04")  # Version = 4
        data.extend(b"\xfd\xe8")  # Peer AS = 65000
        data.extend(b"\x00\xb4")  # Hold time = 180
        data.extend(b"\xc0\x00\x02\x01")  # BGP ID
        data.extend(b"\x00")  # Opt params len = 0

        msg = parse_peer_up_message(bytes(data))

        assert msg.header.msg_type == BMPMessageType.PEER_UP_NOTIFICATION
        assert msg.local_address == "192.0.2.254"
        assert msg.local_port == 179
        assert msg.remote_port == 50000
        assert len(msg.sent_open_message) == 29
        assert len(msg.received_open_message) == 29

    def test_parse_peer_up_too_short(self) -> None:
        """Test error when Peer Up message is truncated."""
        data = b"\x03\x00\x00\x00\x30\x03" + b"\x00" * 30

        with pytest.raises(BMPParseError, match="too short"):
            parse_peer_up_message(data)


class TestBMPMessageDispatcher:
    """Test the generic parse_bmp_message function."""

    def test_dispatch_to_initiation(self) -> None:
        """Test dispatching to Initiation parser."""
        data = b"\x03\x00\x00\x00\x06\x04"  # INITIATION message

        msg = parse_bmp_message(data)

        assert msg.header.msg_type == BMPMessageType.INITIATION

    def test_dispatch_to_termination(self) -> None:
        """Test dispatching to Termination parser."""
        data = b"\x03\x00\x00\x00\x06\x05"  # TERMINATION message

        msg = parse_bmp_message(data)

        assert msg.header.msg_type == BMPMessageType.TERMINATION

    def test_dispatch_incomplete_message(self) -> None:
        """Test error when message is incomplete."""
        data = b"\x03\x00\x00\x00\x20\x04"  # Header says 32 bytes, but only 6

        with pytest.raises(BMPParseError, match="Incomplete message"):
            parse_bmp_message(data)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_length_tlv_value(self) -> None:
        """Test TLV with zero-length value."""
        data = bytearray()
        data.extend(b"\x03\x00\x00\x00\x0a\x04")  # INITIATION, length=10
        data.extend(b"\x00\x00\x00\x00")  # TLV: Type=0, Length=0

        msg = parse_initiation_message(bytes(data))

        assert len(msg.information_tlvs) == 1
        assert msg.information_tlvs[0].info_length == 0
        assert msg.information_tlvs[0].info_value == b""

    def test_maximum_stats_count(self) -> None:
        """Test Statistics Report with many counters."""
        data = bytearray()

        # BMP header
        total_length = 6 + 42 + 4 + (100 * 8)  # 100 stats, 8 bytes each
        data.extend(b"\x03")
        data.extend(total_length.to_bytes(4, "big"))
        data.extend(b"\x01")  # STATISTICS_REPORT

        # Per-Peer Header
        data.extend(b"\x00\x00" + b"\x00" * 8)
        data.extend(b"\x00" * 12 + b"\xc0\x00\x02\x01")
        data.extend(b"\x00\x00\xfd\xe8\xc0\x00\x02\x01")
        data.extend(b"\x00\x00\x00\x01\x00\x00\x00\x00")

        # Stats count = 100
        data.extend(b"\x00\x00\x00\x64")

        # Add 100 stats
        for i in range(100):
            data.extend(b"\x00\x07")  # Type
            data.extend(b"\x00\x04")  # Length = 4
            data.extend(i.to_bytes(4, "big"))  # Value = i

        msg = parse_statistics_report_message(bytes(data))

        assert msg.stats_count == 100
        assert len(msg.stats_tlvs) == 100

    def test_peer_distinguisher_nonzero(self) -> None:
        """Test Per-Peer Header with non-zero peer distinguisher."""
        data = bytearray()
        data.extend(b"\x03\x00\x00\x00\x30\x00")  # Header
        data.extend(b"\x01")  # Peer Type = RD_INSTANCE
        data.extend(b"\x00")  # Flags
        data.extend(b"\x00\x01\x00\x02\x00\x03\x00\x04")  # Non-zero distinguisher
        data.extend(b"\x00" * 12 + b"\xc0\x00\x02\x01")
        data.extend(b"\x00\x00\xfd\xe8\xc0\x00\x02\x01")
        data.extend(b"\x00\x00\x00\x01\x00\x00\x00\x00")

        per_peer_header = parse_per_peer_header(bytes(data), offset=6)

        assert per_peer_header.peer_type == BMPPeerType.RD_INSTANCE
        assert per_peer_header.peer_distinguisher == b"\x00\x01\x00\x02\x00\x03\x00\x04"

    def test_post_policy_flag(self) -> None:
        """Test Per-Peer Header with post-policy flag set."""
        data = bytearray()
        data.extend(b"\x03\x00\x00\x00\x30\x00")
        data.extend(b"\x00")  # Type
        data.extend(b"\x40")  # Flags = 0x40 (POST_POLICY)
        data.extend(b"\x00" * 8)  # Distinguisher
        data.extend(b"\x00" * 12 + b"\xc0\x00\x02\x01")
        data.extend(b"\x00\x00\xfd\xe8\xc0\x00\x02\x01")
        data.extend(b"\x00\x00\x00\x01\x00\x00\x00\x00")

        per_peer_header = parse_per_peer_header(bytes(data), offset=6)

        assert per_peer_header.peer_flags & BMPPeerFlags.POST_POLICY
        assert not (per_peer_header.peer_flags & BMPPeerFlags.IPV6)
