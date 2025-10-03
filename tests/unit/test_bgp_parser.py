"""Unit tests for BGP UPDATE message parsing."""

import pytest
from pybmpmon.protocol.bgp import (
    AddressFamilyIdentifier,
    BGPMessageType,
    BGPParseError,
    SubsequentAddressFamilyIdentifier,
)
from pybmpmon.protocol.bgp_parser import (
    parse_as_path,
    parse_bgp_header,
    parse_bgp_update,
    parse_bgp_update_structure,
    parse_communities,
    parse_extended_communities,
    parse_ipv4_prefix,
    parse_ipv6_prefix,
    parse_mp_reach_nlri,
    parse_mp_unreach_nlri,
)


class TestBGPHeader:
    """Test BGP header parsing."""

    def test_parse_valid_update_header(self) -> None:
        """Test parsing valid UPDATE message header."""
        # BGP header: marker (16 bytes) + length (2 bytes) + type (1 byte)
        data = b"\xff" * 16  # Marker
        data += b"\x00\x35"  # Length = 53
        data += b"\x02"  # Type = UPDATE
        data += b"\x00" * 34  # Padding to match length

        header = parse_bgp_header(data)

        assert header.marker == b"\xff" * 16
        assert header.length == 53
        assert header.msg_type == BGPMessageType.UPDATE

    def test_parse_invalid_marker(self) -> None:
        """Test error with invalid marker."""
        data = b"\x00" * 16  # Invalid marker
        data += b"\x00\x13\x02"  # Length + type

        with pytest.raises(BGPParseError, match="Invalid BGP marker"):
            parse_bgp_header(data)

    def test_parse_truncated_header(self) -> None:
        """Test error with truncated header."""
        data = b"\xff" * 10  # Only 10 bytes

        with pytest.raises(BGPParseError, match="Message too short"):
            parse_bgp_header(data)


class TestIPv4Prefix:
    """Test IPv4 prefix parsing."""

    def test_parse_ipv4_prefix_24(self) -> None:
        """Test parsing /24 prefix."""
        data = b"\x18\xc0\xa8\x01"  # 192.168.1.0/24
        prefix, consumed = parse_ipv4_prefix(data, 0)

        assert prefix == "192.168.1.0/24"
        assert consumed == 4

    def test_parse_ipv4_prefix_32(self) -> None:
        """Test parsing /32 prefix (host route)."""
        data = b"\x20\xc0\x00\x02\x01"  # 192.0.2.1/32
        prefix, consumed = parse_ipv4_prefix(data, 0)

        assert prefix == "192.0.2.1/32"
        assert consumed == 5

    def test_parse_ipv4_prefix_8(self) -> None:
        """Test parsing /8 prefix."""
        data = b"\x08\x0a"  # 10.0.0.0/8
        prefix, consumed = parse_ipv4_prefix(data, 0)

        assert prefix == "10.0.0.0/8"
        assert consumed == 2

    def test_parse_ipv4_prefix_0(self) -> None:
        """Test parsing default route /0."""
        data = b"\x00"  # 0.0.0.0/0
        prefix, consumed = parse_ipv4_prefix(data, 0)

        assert prefix == "0.0.0.0/0"
        assert consumed == 1

    def test_parse_ipv4_prefix_invalid_length(self) -> None:
        """Test error with invalid prefix length."""
        data = b"\x21\xc0\x00\x02\x01"  # Invalid: 33 bits

        with pytest.raises(BGPParseError, match="Invalid IPv4 prefix length"):
            parse_ipv4_prefix(data, 0)


class TestIPv6Prefix:
    """Test IPv6 prefix parsing."""

    def test_parse_ipv6_prefix_48(self) -> None:
        """Test parsing /48 prefix."""
        data = b"\x30\x20\x01\x0d\xb8\x00\x00"  # 2001:db8::/48
        prefix, consumed = parse_ipv6_prefix(data, 0)

        assert prefix == "2001:db8::/48"
        assert consumed == 7

    def test_parse_ipv6_prefix_128(self) -> None:
        """Test parsing /128 prefix (host route)."""
        data = (
            b"\x80"
            + b"\x20\x01\x0d\xb8\x00\x00\x00\x00"
            + b"\x00\x00\x00\x00\x00\x00\x00\x01"
        )  # 2001:db8::1/128
        prefix, consumed = parse_ipv6_prefix(data, 0)

        assert prefix == "2001:db8::1/128"
        assert consumed == 17

    def test_parse_ipv6_prefix_invalid_length(self) -> None:
        """Test error with invalid prefix length."""
        data = b"\x81\x20\x01"  # Invalid: 129 bits

        with pytest.raises(BGPParseError, match="Invalid IPv6 prefix length"):
            parse_ipv6_prefix(data, 0)


class TestASPath:
    """Test AS_PATH parsing."""

    def test_parse_as_path_sequence(self) -> None:
        """Test parsing AS_SEQUENCE."""
        # AS_SEQUENCE with 3 ASNs: 65000, 65001, 65002
        data = b"\x02\x03\xfd\xe8\xfd\xe9\xfd\xea"
        as_path = parse_as_path(data)

        assert as_path == [65000, 65001, 65002]

    def test_parse_as_path_empty(self) -> None:
        """Test parsing empty AS_PATH."""
        data = b""
        as_path = parse_as_path(data)

        assert as_path == []

    def test_parse_as_path_set(self) -> None:
        """Test parsing AS_SET."""
        # AS_SET with 2 ASNs
        data = b"\x01\x02\xfd\xe8\xfd\xe9"
        as_path = parse_as_path(data)

        assert len(as_path) == 2
        assert 65000 in as_path
        assert 65001 in as_path

    def test_parse_as_path_truncated(self) -> None:
        """Test error with truncated AS_PATH."""
        data = b"\x02\x03\xfd\xe8"  # Says 3 ASNs but only 1 provided

        with pytest.raises(BGPParseError, match="Incomplete AS_PATH"):
            parse_as_path(data)


class TestCommunities:
    """Test COMMUNITIES parsing."""

    def test_parse_communities_single(self) -> None:
        """Test parsing single community."""
        # Community 65000:100
        data = b"\xfd\xe8\x00\x64"
        communities = parse_communities(data)

        assert communities == ["65000:100"]

    def test_parse_communities_multiple(self) -> None:
        """Test parsing multiple communities."""
        # Communities: 65000:100, 65000:200
        data = b"\xfd\xe8\x00\x64\xfd\xe8\x00\xc8"
        communities = parse_communities(data)

        assert communities == ["65000:100", "65000:200"]

    def test_parse_communities_invalid_length(self) -> None:
        """Test error with invalid length."""
        data = b"\xfd\xe8\x00"  # Incomplete community

        with pytest.raises(BGPParseError, match="Invalid COMMUNITIES length"):
            parse_communities(data)


class TestMPReachNLRI:
    """Test MP_REACH_NLRI parsing."""

    def test_parse_mp_reach_ipv4_unicast(self) -> None:
        """Test parsing IPv4 unicast MP_REACH_NLRI."""
        # AFI=1 (IPv4), SAFI=1 (unicast), next_hop_len=4, next_hop=192.0.2.254,
        # reserved=0, prefix=10.0.0.0/8
        data = (
            b"\x00\x01"  # AFI = IPv4
            b"\x01"  # SAFI = unicast
            b"\x04"  # Next hop length = 4
            b"\xc0\x00\x02\xfe"  # Next hop = 192.0.2.254
            b"\x00"  # Reserved
            b"\x08\x0a"  # Prefix = 10.0.0.0/8
        )

        afi, safi, next_hop, prefixes = parse_mp_reach_nlri(data)

        assert afi == AddressFamilyIdentifier.IPV4
        assert safi == SubsequentAddressFamilyIdentifier.UNICAST
        assert next_hop == "192.0.2.254"
        assert prefixes == ["10.0.0.0/8"]

    def test_parse_mp_reach_ipv6_unicast(self) -> None:
        """Test parsing IPv6 unicast MP_REACH_NLRI."""
        # AFI=2 (IPv6), SAFI=1, next_hop_len=16, next_hop=2001:db8::1,
        # reserved=0, prefix=2001:db8::/32
        data = (
            b"\x00\x02"  # AFI = IPv6
            b"\x01"  # SAFI = unicast
            b"\x10"  # Next hop length = 16
            + b"\x20\x01\x0d\xb8"
            + b"\x00" * 12  # Next hop = 2001:db8::
            + b"\x00"  # Reserved
            b"\x20\x20\x01\x0d\xb8"  # Prefix = 2001:db8::/32
        )

        afi, safi, next_hop, prefixes = parse_mp_reach_nlri(data)

        assert afi == AddressFamilyIdentifier.IPV6
        assert safi == SubsequentAddressFamilyIdentifier.UNICAST
        assert next_hop == "2001:db8::"
        assert prefixes == ["2001:db8::/32"]


class TestMPUnreachNLRI:
    """Test MP_UNREACH_NLRI parsing."""

    def test_parse_mp_unreach_ipv4(self) -> None:
        """Test parsing IPv4 MP_UNREACH_NLRI."""
        data = (
            b"\x00\x01"  # AFI = IPv4
            b"\x01"  # SAFI = unicast
            b"\x18\xc0\xa8\x01"  # Withdrawn: 192.168.1.0/24
        )

        afi, safi, prefixes = parse_mp_unreach_nlri(data)

        assert afi == AddressFamilyIdentifier.IPV4
        assert safi == SubsequentAddressFamilyIdentifier.UNICAST
        assert prefixes == ["192.168.1.0/24"]

    def test_parse_mp_unreach_ipv6(self) -> None:
        """Test parsing IPv6 MP_UNREACH_NLRI."""
        data = (
            b"\x00\x02"  # AFI = IPv6
            b"\x01"  # SAFI = unicast
            b"\x30\x20\x01\x0d\xb8\x00\x00"  # Withdrawn: 2001:db8::/48
        )

        afi, safi, prefixes = parse_mp_unreach_nlri(data)

        assert afi == AddressFamilyIdentifier.IPV6
        assert safi == SubsequentAddressFamilyIdentifier.UNICAST
        assert prefixes == ["2001:db8::/48"]


class TestBGPUpdate:
    """Test complete BGP UPDATE parsing."""

    def test_parse_ipv4_update_with_attributes(self) -> None:
        """Test parsing IPv4 UPDATE with path attributes."""
        # Build a minimal UPDATE message
        data = bytearray()

        # BGP header
        data.extend(b"\xff" * 16)  # Marker
        data.extend(b"\x00\x00")  # Length (will update)
        data.extend(b"\x02")  # Type = UPDATE

        # UPDATE message
        data.extend(b"\x00\x00")  # Withdrawn routes length = 0

        # Path attributes
        path_attrs = bytearray()

        # ORIGIN (type=1, IGP=0)
        path_attrs.extend(b"\x40\x01\x01\x00")  # Flags, type, len, value

        # AS_PATH (type=2, sequence of 65000)
        path_attrs.extend(b"\x40\x02\x04\x02\x01\xfd\xe8")  # AS_SEQUENCE, 1 AS (len=4)

        # NEXT_HOP (type=3, 192.0.2.254)
        path_attrs.extend(b"\x40\x03\x04\xc0\x00\x02\xfe")

        # Total path attributes length
        data.extend(len(path_attrs).to_bytes(2, "big"))
        data.extend(path_attrs)

        # NLRI: 10.0.0.0/8
        data.extend(b"\x08\x0a")

        # Update message length in header
        data[16:18] = len(data).to_bytes(2, "big")

        parsed = parse_bgp_update(bytes(data))

        assert parsed.afi == AddressFamilyIdentifier.IPV4
        assert parsed.safi == SubsequentAddressFamilyIdentifier.UNICAST
        assert parsed.prefixes == ["10.0.0.0/8"]
        assert parsed.withdrawn_prefixes == []
        assert parsed.is_withdrawal is False
        assert parsed.origin == 0
        assert parsed.as_path == [65000]
        assert parsed.next_hop == "192.0.2.254"

    def test_parse_ipv4_withdrawal(self) -> None:
        """Test parsing IPv4 withdrawal."""
        data = bytearray()

        # BGP header
        data.extend(b"\xff" * 16)
        data.extend(b"\x00\x00")  # Length
        data.extend(b"\x02")  # UPDATE

        # Withdrawn routes: 10.0.0.0/8
        withdrawn = b"\x08\x0a"
        data.extend(len(withdrawn).to_bytes(2, "big"))
        data.extend(withdrawn)

        # No path attributes
        data.extend(b"\x00\x00")

        # No NLRI

        # Update length
        data[16:18] = len(data).to_bytes(2, "big")

        parsed = parse_bgp_update(bytes(data))

        assert parsed.prefixes == []
        assert parsed.withdrawn_prefixes == ["10.0.0.0/8"]
        assert parsed.is_withdrawal is True

    def test_parse_update_with_communities(self) -> None:
        """Test parsing UPDATE with COMMUNITIES attribute."""
        data = bytearray()

        # BGP header
        data.extend(b"\xff" * 16)
        data.extend(b"\x00\x00")
        data.extend(b"\x02")

        data.extend(b"\x00\x00")  # No withdrawn routes

        # Path attributes
        path_attrs = bytearray()

        # ORIGIN
        path_attrs.extend(b"\x40\x01\x01\x00")

        # AS_PATH (empty)
        path_attrs.extend(b"\x40\x02\x00")

        # NEXT_HOP
        path_attrs.extend(b"\x40\x03\x04\xc0\x00\x02\xfe")

        # COMMUNITIES (65000:100, 65000:200)
        path_attrs.extend(
            b"\xc0\x08\x08"  # Flags, type, len
            b"\xfd\xe8\x00\x64"  # 65000:100
            b"\xfd\xe8\x00\xc8"  # 65000:200
        )

        data.extend(len(path_attrs).to_bytes(2, "big"))
        data.extend(path_attrs)

        # NLRI
        data.extend(b"\x18\xc0\xa8\x01")  # 192.168.1.0/24

        data[16:18] = len(data).to_bytes(2, "big")

        parsed = parse_bgp_update(bytes(data))

        assert parsed.communities == ["65000:100", "65000:200"]
        assert parsed.prefixes == ["192.168.1.0/24"]

    def test_parse_update_with_med_local_pref(self) -> None:
        """Test parsing UPDATE with MED and LOCAL_PREF."""
        data = bytearray()

        # BGP header
        data.extend(b"\xff" * 16)
        data.extend(b"\x00\x00")
        data.extend(b"\x02")

        data.extend(b"\x00\x00")  # No withdrawn

        path_attrs = bytearray()

        # ORIGIN
        path_attrs.extend(b"\x40\x01\x01\x00")

        # AS_PATH
        path_attrs.extend(b"\x40\x02\x00")

        # NEXT_HOP
        path_attrs.extend(b"\x40\x03\x04\xc0\x00\x02\xfe")

        # MED (type=4, value=100)
        path_attrs.extend(b"\x80\x04\x04\x00\x00\x00\x64")

        # LOCAL_PREF (type=5, value=200)
        path_attrs.extend(b"\x40\x05\x04\x00\x00\x00\xc8")

        data.extend(len(path_attrs).to_bytes(2, "big"))
        data.extend(path_attrs)

        # NLRI
        data.extend(b"\x08\x0a")

        data[16:18] = len(data).to_bytes(2, "big")

        parsed = parse_bgp_update(bytes(data))

        assert parsed.med == 100
        assert parsed.local_pref == 200


class TestBGPUpdateStructure:
    """Test BGP UPDATE message structure parsing."""

    def test_parse_empty_update(self) -> None:
        """Test parsing empty UPDATE (keepalive-like)."""
        data = bytearray()

        # BGP header
        data.extend(b"\xff" * 16)
        data.extend(b"\x00\x17")  # Length = 23 (header only)
        data.extend(b"\x02")

        # Empty UPDATE
        data.extend(b"\x00\x00")  # No withdrawn
        data.extend(b"\x00\x00")  # No path attrs
        # No NLRI

        update = parse_bgp_update_structure(bytes(data))

        assert update.withdrawn_routes_length == 0
        assert update.total_path_attr_length == 0
        assert len(update.path_attributes) == 0
        assert len(update.nlri) == 0

    def test_parse_update_wrong_type(self) -> None:
        """Test error when message is not UPDATE."""
        data = b"\xff" * 16 + b"\x00\x13\x01"  # OPEN message

        with pytest.raises(BGPParseError, match="Expected UPDATE"):
            parse_bgp_update_structure(data)


class TestExtendedCommunities:
    """Test extended communities parsing."""

    def test_parse_two_octet_as_route_target(self) -> None:
        """Test parsing two-octet AS Route Target (type 0x00, 0x02)."""
        # Type 0x00 (RT), Subtype 0x02, AS=42, Assigned=1
        data = b"\x00\x02\x00\x2a\x00\x00\x00\x01"
        communities = parse_extended_communities(data)

        assert len(communities) == 1
        assert communities[0] == "RT:42:1"

    def test_parse_ipv4_address_route_target(self) -> None:
        """Test parsing IPv4 address Route Target (type 0x01, 0x02)."""
        # Type 0x01 (RT), Subtype 0x02, IP=10.1.0.45, Assigned=42
        data = b"\x01\x02\x0a\x01\x00\x2d\x00\x2a"
        communities = parse_extended_communities(data)

        assert len(communities) == 1
        assert communities[0] == "RT:10.1.0.45:42"

    def test_parse_four_octet_as_route_target(self) -> None:
        """Test parsing four-octet AS Route Target (type 0x02, 0x02)."""
        # Type 0x02 (RT), Subtype 0x02, AS=65536, Assigned=1
        data = b"\x02\x02\x00\x01\x00\x00\x00\x01"
        communities = parse_extended_communities(data)

        assert len(communities) == 1
        assert communities[0] == "RT:65536:1"

    def test_parse_ospf_domain_id(self) -> None:
        """Test parsing OSPF Domain ID (type 0x03, subtype 0x0c)."""
        # Type 0x03, Subtype 0x0c, padding + Domain ID 0.0.0.10
        data = b"\x03\x0c\x00\x00\x00\x00\x00\x0a"
        communities = parse_extended_communities(data)

        assert len(communities) == 1
        assert communities[0] == "OSPF-Domain:0.0.0.10"

    def test_parse_evpn_mac_mobility(self) -> None:
        """Test parsing EVPN MAC Mobility (type 0x06, subtype 0x00)."""
        # Type 0x06, Subtype 0x00, flags=0x01, seq=12345, reserved
        data = b"\x06\x00\x01\x00\x00\x30\x39\x00"
        communities = parse_extended_communities(data)

        assert len(communities) == 1
        assert communities[0] == "EVPN-MAC-Mobility:12345"

    def test_parse_evpn_esi_label(self) -> None:
        """Test parsing EVPN ESI Label (type 0x06, subtype 0x01)."""
        # Type 0x06, Subtype 0x01, flags, reserved (2), label=100 (0x000064)
        data = b"\x06\x01\x00\x00\x00\x00\x06\x40"
        communities = parse_extended_communities(data)

        assert len(communities) == 1
        assert communities[0] == "EVPN-ESI-Label:100"

    def test_parse_evpn_es_import(self) -> None:
        """Test parsing EVPN ES-Import Route Target (type 0x06, subtype 0x02)."""
        # Type 0x06, Subtype 0x02, MAC=30:ce:e4:4a:13:e3
        data = b"\x06\x02\x30\xce\xe4\x4a\x13\xe3"
        communities = parse_extended_communities(data)

        assert len(communities) == 1
        assert communities[0] == "EVPN-ES-Import:30:ce:e4:4a:13:e3"

    def test_parse_multiple_extended_communities(self) -> None:
        """Test parsing multiple extended communities."""
        # Two communities: RT:42:1 and OSPF-Domain:0.0.0.10
        data = b"\x00\x02\x00\x2a\x00\x00\x00\x01"  # RT:42:1
        data += b"\x03\x0c\x00\x00\x00\x00\x00\x0a"  # OSPF-Domain:0.0.0.10
        communities = parse_extended_communities(data)

        assert len(communities) == 2
        assert communities[0] == "RT:42:1"
        assert communities[1] == "OSPF-Domain:0.0.0.10"

    def test_parse_unknown_extended_community(self) -> None:
        """Test parsing unknown extended community type."""
        # Type 0xFF (unknown), arbitrary data
        data = b"\xff\x00\x01\x02\x03\x04\x05\x06"
        communities = parse_extended_communities(data)

        assert len(communities) == 1
        assert communities[0].startswith("Unknown-ff:")

    def test_parse_extended_communities_invalid_length(self) -> None:
        """Test error with invalid length (not multiple of 8)."""
        data = b"\x00\x02\x00\x2a\x00"  # Only 5 bytes

        with pytest.raises(BGPParseError, match="Invalid EXTENDED_COMMUNITIES length"):
            parse_extended_communities(data)

    def test_parse_route_origin(self) -> None:
        """Test parsing Route Origin communities (type 0x02, subtype 0x00)."""
        # Type 0x02 (two-octet AS RO), Subtype 0x00, AS=100, Assigned=200
        data = b"\x02\x00\x00\x64\x00\x00\x00\xc8"
        communities = parse_extended_communities(data)

        assert len(communities) == 1
        assert communities[0] == "RO:100:200"
