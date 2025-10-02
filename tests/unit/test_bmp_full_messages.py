"""Unit tests for complete BMP message parsing.

Tests for parsing full BMP messages (not just headers) to ensure RFC7854
compliance for all message types with realistic binary data.
"""

import pytest
from pybmpmon.protocol.bmp import (
    BMP_CURRENT_VERSION,
    BMPInfoTLVType,
    BMPMessageType,
    BMPParseError,
    BMPPeerDownReason,
    BMPPeerFlags,
    BMPPeerType,
    BMPStatType,
)
from pybmpmon.protocol.bmp_parser import (
    parse_bmp_message,
    parse_initiation_message,
    parse_peer_down_message,
    parse_peer_up_message,
    parse_route_monitoring_message,
    parse_statistics_report_message,
    parse_termination_message,
)


class TestInitiationMessage:
    """Test BMP Initiation message parsing with TLVs."""

    def test_parse_initiation_message_with_tlvs(self) -> None:
        """Test parsing Initiation message with system info TLVs."""
        # Build complete Initiation message
        data = bytearray()

        # BMP header (6 bytes)
        data.extend(b"\x03")  # Version = 3
        data.extend(b"\x00\x00\x00\x00")  # Length (will update)
        data.extend(b"\x04")  # Type = Initiation

        # TLV 1: String (type=0)
        data.extend(b"\x00\x00")  # Type = STRING
        string_value = b"BMP Test Router v1.0"
        data.extend(len(string_value).to_bytes(2, "big"))  # Length
        data.extend(string_value)  # Value

        # TLV 2: System Description (type=1)
        data.extend(b"\x00\x01")  # Type = SYS_DESCR
        sys_descr = b"Test Router OS v2.5.1"
        data.extend(len(sys_descr).to_bytes(2, "big"))
        data.extend(sys_descr)

        # TLV 3: System Name (type=2)
        data.extend(b"\x00\x02")  # Type = SYS_NAME
        sys_name = b"router-lab-01"
        data.extend(len(sys_name).to_bytes(2, "big"))
        data.extend(sys_name)

        # Update message length
        data[1:5] = len(data).to_bytes(4, "big")

        # Parse message
        msg = parse_initiation_message(bytes(data))

        # Verify header
        assert msg.header.version == BMP_CURRENT_VERSION
        assert msg.header.length == len(data)
        assert msg.header.msg_type == BMPMessageType.INITIATION

        # Verify TLVs
        assert len(msg.information_tlvs) == 3

        # TLV 1: String
        assert msg.information_tlvs[0].info_type == BMPInfoTLVType.STRING
        assert msg.information_tlvs[0].info_length == len(string_value)
        assert msg.information_tlvs[0].info_value == string_value

        # TLV 2: System Description
        assert msg.information_tlvs[1].info_type == BMPInfoTLVType.SYS_DESCR
        assert msg.information_tlvs[1].info_value == sys_descr

        # TLV 3: System Name
        assert msg.information_tlvs[2].info_type == BMPInfoTLVType.SYS_NAME
        assert msg.information_tlvs[2].info_value == sys_name

    def test_parse_initiation_message_empty(self) -> None:
        """Test parsing Initiation message with no TLVs."""
        data = bytearray()

        # BMP header only
        data.extend(b"\x03")  # Version
        data.extend(b"\x00\x00\x00\x06")  # Length = 6 (header only)
        data.extend(b"\x04")  # Type = Initiation

        msg = parse_initiation_message(bytes(data))

        assert msg.header.msg_type == BMPMessageType.INITIATION
        assert len(msg.information_tlvs) == 0


class TestTerminationMessage:
    """Test BMP Termination message parsing."""

    def test_parse_termination_message_with_tlvs(self) -> None:
        """Test parsing Termination message with reason TLVs."""
        data = bytearray()

        # BMP header
        data.extend(b"\x03")  # Version
        data.extend(b"\x00\x00\x00\x00")  # Length (will update)
        data.extend(b"\x05")  # Type = Termination

        # TLV: String with termination reason
        data.extend(b"\x00\x00")  # Type = STRING
        reason = b"Administrator shutdown"
        data.extend(len(reason).to_bytes(2, "big"))
        data.extend(reason)

        # Update length
        data[1:5] = len(data).to_bytes(4, "big")

        msg = parse_termination_message(bytes(data))

        assert msg.header.msg_type == BMPMessageType.TERMINATION
        assert len(msg.information_tlvs) == 1
        assert msg.information_tlvs[0].info_value == reason


class TestPeerUpMessage:
    """Test BMP Peer Up message parsing."""

    def test_parse_peer_up_message_complete(self) -> None:
        """Test parsing complete Peer Up with BGP OPEN messages."""
        data = bytearray()

        # BMP header
        data.extend(b"\x03")  # Version
        data.extend(b"\x00\x00\x00\x00")  # Length (will update)
        data.extend(b"\x03")  # Type = Peer Up

        # Per-Peer Header (42 bytes)
        data.extend(b"\x00")  # Peer Type = Global Instance
        data.extend(b"\x00")  # Peer Flags = IPv4
        data.extend(b"\x00" * 8)  # Peer Distinguisher
        # Peer Address (16 bytes, IPv4-mapped)
        data.extend(b"\x00" * 10 + b"\xff\xff" + b"\xc0\x00\x02\x01")  # 192.0.2.1
        data.extend(b"\x00\x01\x00\x00")  # Peer AS = 65536
        data.extend(b"\xc0\x00\x02\x01")  # Peer BGP ID = 192.0.2.1
        data.extend(b"\x00\x00\x00\x64")  # Timestamp seconds = 100
        data.extend(b"\x00\x00\x00\x00")  # Timestamp microseconds = 0

        # Local Address (16 bytes, IPv4-mapped)
        data.extend(b"\x00" * 10 + b"\xff\xff" + b"\xc0\x00\x02\xfe")  # 192.0.2.254
        # Local Port
        data.extend(b"\x00\xb3")  # Port = 179 (BGP)
        # Remote Port
        data.extend(b"\xc3\x50")  # Port = 50000

        # Sent OPEN message (BGP OPEN structure)
        sent_open = bytearray()
        sent_open.extend(b"\xff" * 16)  # BGP marker
        sent_open.extend(b"\x00\x1d")  # Length = 29
        sent_open.extend(b"\x01")  # Type = OPEN
        sent_open.extend(b"\x04")  # Version = 4
        sent_open.extend(b"\x00\x01")  # My AS = 1
        sent_open.extend(b"\x00\xb4")  # Hold Time = 180
        sent_open.extend(b"\xc0\x00\x02\xfe")  # BGP Identifier = 192.0.2.254
        sent_open.extend(b"\x00")  # Optional Parameters Length = 0
        data.extend(sent_open)

        # Received OPEN message (same structure)
        recv_open = bytearray()
        recv_open.extend(b"\xff" * 16)  # BGP marker
        recv_open.extend(b"\x00\x1d")  # Length = 29
        recv_open.extend(b"\x01")  # Type = OPEN
        recv_open.extend(b"\x04")  # Version = 4
        recv_open.extend(b"\x00\x01")  # My AS = 1
        recv_open.extend(b"\x00\xb4")  # Hold Time = 180
        recv_open.extend(b"\xc0\x00\x02\x01")  # BGP Identifier = 192.0.2.1
        recv_open.extend(b"\x00")  # Optional Parameters Length = 0
        data.extend(recv_open)

        # No Information TLVs in this test

        # Update BMP message length
        data[1:5] = len(data).to_bytes(4, "big")

        msg = parse_peer_up_message(bytes(data))

        # Verify header
        assert msg.header.msg_type == BMPMessageType.PEER_UP_NOTIFICATION

        # Verify Per-Peer Header
        assert msg.per_peer_header.peer_type == BMPPeerType.GLOBAL_INSTANCE
        assert msg.per_peer_header.peer_flags == 0
        assert (
            msg.per_peer_header.peer_address == "::ffff:192.0.2.1"
        )  # IPv4-mapped IPv6
        assert msg.per_peer_header.peer_asn == 65536
        assert msg.per_peer_header.peer_bgp_id == "192.0.2.1"
        assert msg.per_peer_header.timestamp_sec == 100

        # Verify local address and ports
        assert msg.local_address == "::ffff:192.0.2.254"  # IPv4-mapped IPv6
        assert msg.local_port == 179
        assert msg.remote_port == 50000

        # Verify OPEN messages
        assert len(msg.sent_open_message) == 29
        assert len(msg.received_open_message) == 29
        assert msg.sent_open_message == bytes(sent_open)
        assert msg.received_open_message == bytes(recv_open)

        # Verify no TLVs
        assert len(msg.information_tlvs) == 0

    def test_parse_peer_up_message_with_ipv6(self) -> None:
        """Test parsing Peer Up message with IPv6 addresses."""
        data = bytearray()

        # BMP header
        data.extend(b"\x03")
        data.extend(b"\x00\x00\x00\x00")  # Length
        data.extend(b"\x03")  # Peer Up

        # Per-Peer Header with IPv6 flag
        data.extend(b"\x00")  # Peer Type
        data.extend(b"\x80")  # Peer Flags = IPv6 (bit 0 set)
        data.extend(b"\x00" * 8)  # Peer Distinguisher
        # Peer Address (16 bytes, full IPv6)
        data.extend(b"\x20\x01\x0d\xb8" + b"\x00" * 12)  # 2001:db8::
        data.extend(b"\x00\x00\xfd\xe8")  # Peer AS = 65000
        data.extend(b"\xc0\x00\x02\x01")  # Peer BGP ID
        data.extend(b"\x00\x00\x00\x01")  # Timestamp sec
        data.extend(b"\x00\x00\x00\x00")  # Timestamp usec

        # Local Address (full IPv6)
        data.extend(b"\x20\x01\x0d\xb8" + b"\x00" * 11 + b"\x01")  # 2001:db8::1
        data.extend(b"\x00\xb3")  # Local port
        data.extend(b"\xc3\x50")  # Remote port

        # Minimal OPEN messages
        for _ in range(2):
            open_msg = (
                b"\xff" * 16 + b"\x00\x1d\x01\x04\x00\x01\x00\xb4\xc0\x00\x02\x01\x00"
            )
            data.extend(open_msg)

        # Update length
        data[1:5] = len(data).to_bytes(4, "big")

        msg = parse_peer_up_message(bytes(data))

        # Verify IPv6 flag and address
        assert msg.per_peer_header.peer_flags & BMPPeerFlags.IPV6
        assert msg.per_peer_header.peer_address == "2001:db8::"
        assert msg.local_address == "2001:db8::1"


class TestPeerDownMessage:
    """Test BMP Peer Down message parsing."""

    def test_parse_peer_down_with_notification(self) -> None:
        """Test parsing Peer Down with various reason codes."""
        # Test all valid reason codes
        test_cases = [
            (BMPPeerDownReason.LOCAL_NOTIFICATION, "Local notification"),
            (BMPPeerDownReason.LOCAL_NO_NOTIFICATION, "Local no notification"),
            (BMPPeerDownReason.REMOTE_NOTIFICATION, "Remote notification"),
            (BMPPeerDownReason.REMOTE_NO_NOTIFICATION, "Remote no notification"),
            (BMPPeerDownReason.PEER_DE_CONFIGURED, "Peer de-configured"),
        ]

        for reason_code, description in test_cases:
            data = bytearray()

            # BMP header
            data.extend(b"\x03")
            data.extend(b"\x00\x00\x00\x00")  # Length
            data.extend(b"\x02")  # Peer Down

            # Per-Peer Header (minimal)
            data.extend(b"\x00")  # Peer Type
            data.extend(b"\x00")  # Peer Flags
            data.extend(b"\x00" * 8)  # Peer Distinguisher
            data.extend(b"\x00" * 10 + b"\xff\xff" + b"\xc0\x00\x02\x01")  # Peer Addr
            data.extend(b"\x00\x00\xfd\xe8")  # Peer AS
            data.extend(b"\xc0\x00\x02\x01")  # BGP ID
            data.extend(b"\x00\x00\x00\x64")  # Timestamp sec
            data.extend(b"\x00\x00\x00\x00")  # Timestamp usec

            # Reason code
            data.extend(bytes([reason_code]))

            # Additional data (BGP notification if reason = 1 or 3)
            if reason_code in (
                BMPPeerDownReason.LOCAL_NOTIFICATION,
                BMPPeerDownReason.REMOTE_NOTIFICATION,
            ):
                # BGP NOTIFICATION message
                bgp_notif = b"\xff" * 16  # Marker
                bgp_notif += b"\x00\x15"  # Length = 21
                bgp_notif += b"\x03"  # Type = NOTIFICATION
                bgp_notif += b"\x06"  # Error Code = Cease
                bgp_notif += b"\x04"  # Error Subcode = Admin shutdown
                data.extend(bgp_notif)

            # Update length
            data[1:5] = len(data).to_bytes(4, "big")

            msg = parse_peer_down_message(bytes(data))

            # Verify reason code
            assert msg.reason == reason_code, f"Failed for {description}"
            assert msg.header.msg_type == BMPMessageType.PEER_DOWN_NOTIFICATION

            # Verify additional data
            if reason_code in (
                BMPPeerDownReason.LOCAL_NOTIFICATION,
                BMPPeerDownReason.REMOTE_NOTIFICATION,
            ):
                assert len(msg.data) == 21  # BGP notification length
            else:
                assert len(msg.data) == 0


class TestRouteMonitoringMessage:
    """Test BMP Route Monitoring message parsing."""

    def test_parse_route_monitoring_message_complete(self) -> None:
        """Test parsing Route Monitoring with embedded BGP UPDATE."""
        data = bytearray()

        # BMP header
        data.extend(b"\x03")
        data.extend(b"\x00\x00\x00\x00")  # Length
        data.extend(b"\x00")  # Type = Route Monitoring

        # Per-Peer Header
        data.extend(b"\x00")  # Peer Type
        data.extend(b"\x00")  # Peer Flags (IPv4)
        data.extend(b"\x00" * 8)  # Peer Distinguisher
        data.extend(b"\x00" * 10 + b"\xff\xff" + b"\xc0\x00\x02\x01")  # 192.0.2.1
        data.extend(b"\x00\x00\xfd\xe8")  # AS 65000
        data.extend(b"\xc0\x00\x02\x01")  # BGP ID
        data.extend(b"\x00\x00\x00\x01")  # Timestamp
        data.extend(b"\x00\x00\x00\x00")

        # BGP UPDATE message
        bgp_update = bytearray()
        bgp_update.extend(b"\xff" * 16)  # BGP marker
        bgp_update.extend(b"\x00\x00")  # Length (will update)
        bgp_update.extend(b"\x02")  # Type = UPDATE

        # Withdrawn routes length
        bgp_update.extend(b"\x00\x00")

        # Path attributes
        path_attrs = bytearray()
        # ORIGIN (IGP)
        path_attrs.extend(b"\x40\x01\x01\x00")
        # AS_PATH (sequence: 65000)
        path_attrs.extend(b"\x40\x02\x04\x02\x01\xfd\xe8")
        # NEXT_HOP
        path_attrs.extend(b"\x40\x03\x04\xc0\x00\x02\xfe")  # 192.0.2.254

        bgp_update.extend(len(path_attrs).to_bytes(2, "big"))
        bgp_update.extend(path_attrs)

        # NLRI: 10.0.0.0/8
        bgp_update.extend(b"\x08\x0a")

        # Update BGP message length
        bgp_update[16:18] = len(bgp_update).to_bytes(2, "big")

        data.extend(bgp_update)

        # Update BMP message length
        data[1:5] = len(data).to_bytes(4, "big")

        msg = parse_route_monitoring_message(bytes(data))

        # Verify message type
        assert msg.header.msg_type == BMPMessageType.ROUTE_MONITORING

        # Verify Per-Peer Header
        assert (
            msg.per_peer_header.peer_address == "::ffff:192.0.2.1"
        )  # IPv4-mapped IPv6
        assert msg.per_peer_header.peer_asn == 65000

        # Verify BGP UPDATE is present
        assert len(msg.bgp_update) > 0
        assert msg.bgp_update == bytes(bgp_update)


class TestStatisticsReportMessage:
    """Test BMP Statistics Report message parsing."""

    def test_parse_statistics_report_with_counters(self) -> None:
        """Test parsing Statistics Report with counter TLVs."""
        data = bytearray()

        # BMP header
        data.extend(b"\x03")
        data.extend(b"\x00\x00\x00\x00")  # Length
        data.extend(b"\x01")  # Type = Statistics Report

        # Per-Peer Header
        data.extend(b"\x00")  # Peer Type
        data.extend(b"\x00")  # Peer Flags
        data.extend(b"\x00" * 8)  # Peer Distinguisher
        data.extend(b"\x00" * 10 + b"\xff\xff" + b"\xc0\x00\x02\x01")  # Peer Addr
        data.extend(b"\x00\x00\xfd\xe8")  # AS 65000
        data.extend(b"\xc0\x00\x02\x01")  # BGP ID
        data.extend(b"\x00\x00\x00\x01")  # Timestamp
        data.extend(b"\x00\x00\x00\x00")

        # Stats count
        data.extend(b"\x00\x00\x00\x04")  # 4 statistics

        # Stat 1: Number of prefixes rejected (32-bit counter)
        data.extend(b"\x00\x00")  # Type = REJECTED_PREFIXES
        data.extend(b"\x00\x04")  # Length = 4
        data.extend(b"\x00\x00\x00\x0a")  # Value = 10

        # Stat 2: Number of duplicate prefix advertisements (32-bit)
        data.extend(b"\x00\x01")  # Type = DUPLICATE_PREFIX_ADVERTISEMENTS
        data.extend(b"\x00\x04")  # Length = 4
        data.extend(b"\x00\x00\x00\x05")  # Value = 5

        # Stat 3: Number of routes in Adj-RIB-In (64-bit counter)
        data.extend(b"\x00\x07")  # Type = ROUTES_ADJ_RIB_IN
        data.extend(b"\x00\x08")  # Length = 8
        data.extend(b"\x00\x00\x00\x00")  # High 32 bits = 0
        data.extend(b"\x00\x10\xC8\xE0")  # Low 32 bits = 1,100,000

        # Stat 4: Number of routes in Loc-RIB (64-bit)
        data.extend(b"\x00\x08")  # Type = ROUTES_LOC_RIB
        data.extend(b"\x00\x08")  # Length = 8
        data.extend(b"\x00\x00\x00\x00")  # High = 0
        data.extend(b"\x00\x07\xa1\x20")  # Low = 500,000

        # Update BMP message length
        data[1:5] = len(data).to_bytes(4, "big")

        msg = parse_statistics_report_message(bytes(data))

        # Verify header
        assert msg.header.msg_type == BMPMessageType.STATISTICS_REPORT

        # Verify stats count
        assert msg.stats_count == 4
        assert len(msg.stats_tlvs) == 4

        # Verify stat values
        assert msg.stats_tlvs[0].stat_type == BMPStatType.REJECTED_PREFIXES
        assert msg.stats_tlvs[0].stat_value == 10

        assert (
            msg.stats_tlvs[1].stat_type == BMPStatType.DUPLICATE_PREFIX_ADVERTISEMENTS
        )
        assert msg.stats_tlvs[1].stat_value == 5

        assert msg.stats_tlvs[2].stat_type == BMPStatType.ROUTES_ADJ_RIB_IN
        assert msg.stats_tlvs[2].stat_value == 1_100_000

        assert msg.stats_tlvs[3].stat_type == BMPStatType.ROUTES_LOC_RIB
        assert msg.stats_tlvs[3].stat_value == 500_000


class TestBMPMessageDispatch:
    """Test parse_bmp_message dispatcher function."""

    def test_parse_bmp_message_dispatches_correctly(self) -> None:
        """Test that parse_bmp_message dispatches to correct parser."""
        # Create minimal Initiation message
        data = b"\x03\x00\x00\x00\x06\x04"

        msg = parse_bmp_message(data)

        # Should return BMPInitiationMessage
        assert msg.header.msg_type == BMPMessageType.INITIATION
        assert hasattr(msg, "information_tlvs")

    def test_parse_bmp_message_validates_length(self) -> None:
        """Test that parse_bmp_message validates complete message."""
        # Header says 100 bytes, but provide only 50
        data = b"\x03\x00\x00\x00\x64\x04" + b"\x00" * 44

        with pytest.raises(BMPParseError, match="Incomplete message"):
            parse_bmp_message(data)
