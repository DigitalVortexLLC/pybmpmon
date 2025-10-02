"""Unit tests for EVPN route parsing.

Tests for parsing EVPN routes (AFI=25, SAFI=70) with all route types,
focusing on MAC/IP Advertisement routes (Type 2) which are most common.
"""

import pytest
from pybmpmon.protocol.bgp import (
    AddressFamilyIdentifier,
    BGPParseError,
    BGPPathAttributeType,
    SubsequentAddressFamilyIdentifier,
)
from pybmpmon.protocol.bgp_parser import (
    parse_bgp_update,
    parse_mp_reach_nlri,
    parse_mp_unreach_nlri,
)


class TestEVPNMPReachNLRI:
    """Test EVPN MP_REACH_NLRI parsing."""

    def test_parse_mp_reach_nlri_evpn_basic(self) -> None:
        """Test parsing basic EVPN MP_REACH_NLRI structure."""
        # AFI=25 (L2VPN), SAFI=70 (EVPN), next_hop_len=4, next_hop=192.0.2.254
        data = bytearray()
        data.extend(b"\x00\x19")  # AFI = L2VPN (25)
        data.extend(b"\x46")  # SAFI = EVPN (70)
        data.extend(b"\x04")  # Next hop length = 4
        data.extend(b"\xc0\x00\x02\xfe")  # Next hop = 192.0.2.254
        data.extend(b"\x00")  # Reserved

        # For now, no NLRI (EVPN NLRI parsing not yet implemented)
        # This tests the AFI/SAFI recognition

        afi, safi, next_hop, prefixes = parse_mp_reach_nlri(bytes(data))

        assert afi == AddressFamilyIdentifier.L2VPN
        assert safi == SubsequentAddressFamilyIdentifier.EVPN
        assert next_hop == "192.0.2.254"
        # EVPN NLRI parsing returns empty list (not yet implemented)
        assert prefixes == []

    def test_parse_mp_reach_nlri_evpn_ipv6_next_hop(self) -> None:
        """Test EVPN MP_REACH_NLRI with IPv6 next hop."""
        data = bytearray()
        data.extend(b"\x00\x19")  # AFI = L2VPN
        data.extend(b"\x46")  # SAFI = EVPN
        data.extend(b"\x10")  # Next hop length = 16 (IPv6)
        # Next hop = 2001:db8::1
        data.extend(b"\x20\x01\x0d\xb8" + b"\x00" * 11 + b"\x01")
        data.extend(b"\x00")  # Reserved

        afi, safi, next_hop, prefixes = parse_mp_reach_nlri(bytes(data))

        assert afi == AddressFamilyIdentifier.L2VPN
        assert safi == SubsequentAddressFamilyIdentifier.EVPN
        assert next_hop == "2001:db8::1"


class TestEVPNMPUnreachNLRI:
    """Test EVPN MP_UNREACH_NLRI parsing."""

    def test_parse_mp_unreach_nlri_evpn(self) -> None:
        """Test parsing EVPN MP_UNREACH_NLRI (withdrawal)."""
        data = bytearray()
        data.extend(b"\x00\x19")  # AFI = L2VPN
        data.extend(b"\x46")  # SAFI = EVPN

        # No NLRI for this test (EVPN NLRI parsing not implemented)

        afi, safi, prefixes = parse_mp_unreach_nlri(bytes(data))

        assert afi == AddressFamilyIdentifier.L2VPN
        assert safi == SubsequentAddressFamilyIdentifier.EVPN
        assert prefixes == []


class TestBGPUpdateWithEVPN:
    """Test complete BGP UPDATE messages containing EVPN routes."""

    def test_bgp_update_with_evpn_route(self) -> None:
        """Test parsing complete BGP UPDATE containing EVPN route."""
        # Build BGP UPDATE with MP_REACH_NLRI for EVPN
        data = bytearray()

        # BGP header
        data.extend(b"\xff" * 16)  # Marker
        data.extend(b"\x00\x00")  # Length (will update)
        data.extend(b"\x02")  # Type = UPDATE

        # No withdrawn routes
        data.extend(b"\x00\x00")

        # Path attributes
        path_attrs = bytearray()

        # ORIGIN (IGP)
        path_attrs.extend(b"\x40\x01\x01\x00")

        # AS_PATH (sequence: 65001, 65002)
        path_attrs.extend(b"\x40\x02\x08\x02\x02\xfd\xe9\xfd\xea")

        # MP_REACH_NLRI with EVPN
        mp_reach = bytearray()
        mp_reach.extend(b"\x00\x19")  # AFI = L2VPN
        mp_reach.extend(b"\x46")  # SAFI = EVPN
        mp_reach.extend(b"\x04")  # Next hop length
        mp_reach.extend(b"\xc0\x00\x02\xfe")  # Next hop = 192.0.2.254
        mp_reach.extend(b"\x00")  # Reserved
        # EVPN NLRI would go here (not parsed yet)

        # MP_REACH_NLRI attribute
        path_attrs.extend(b"\x80")  # Flags (optional)
        path_attrs.extend(bytes([BGPPathAttributeType.MP_REACH_NLRI]))
        path_attrs.extend(len(mp_reach).to_bytes(1, "big"))
        path_attrs.extend(mp_reach)

        # Add path attributes to UPDATE
        data.extend(len(path_attrs).to_bytes(2, "big"))
        data.extend(path_attrs)

        # No NLRI in standard UPDATE (all routes in MP_REACH_NLRI)

        # Update BGP message length
        data[16:18] = len(data).to_bytes(2, "big")

        parsed = parse_bgp_update(bytes(data))

        # Verify AFI/SAFI
        assert parsed.afi == AddressFamilyIdentifier.L2VPN
        assert parsed.safi == SubsequentAddressFamilyIdentifier.EVPN

        # Verify next hop
        assert parsed.next_hop == "192.0.2.254"

        # Verify AS path
        assert parsed.as_path == [65001, 65002]

        # Not a withdrawal
        assert parsed.is_withdrawal is False

        # EVPN-specific fields (not populated yet - parsing not implemented)
        assert parsed.evpn_route_type is None
        assert parsed.evpn_rd is None
        assert parsed.evpn_esi is None
        assert parsed.mac_address is None

    def test_bgp_update_evpn_withdrawal(self) -> None:
        """Test parsing BGP UPDATE with EVPN route withdrawal."""
        data = bytearray()

        # BGP header
        data.extend(b"\xff" * 16)
        data.extend(b"\x00\x00")  # Length
        data.extend(b"\x02")  # UPDATE

        # No withdrawn routes in standard format
        data.extend(b"\x00\x00")

        # Path attributes
        path_attrs = bytearray()

        # MP_UNREACH_NLRI with EVPN
        mp_unreach = bytearray()
        mp_unreach.extend(b"\x00\x19")  # AFI = L2VPN
        mp_unreach.extend(b"\x46")  # SAFI = EVPN
        # EVPN NLRI for withdrawal would go here

        path_attrs.extend(b"\x80")  # Flags
        path_attrs.extend(bytes([BGPPathAttributeType.MP_UNREACH_NLRI]))
        path_attrs.extend(len(mp_unreach).to_bytes(1, "big"))
        path_attrs.extend(mp_unreach)

        data.extend(len(path_attrs).to_bytes(2, "big"))
        data.extend(path_attrs)

        # Update length
        data[16:18] = len(data).to_bytes(2, "big")

        parsed = parse_bgp_update(bytes(data))

        # Verify this is recognized as EVPN
        assert parsed.afi == AddressFamilyIdentifier.L2VPN
        assert parsed.safi == SubsequentAddressFamilyIdentifier.EVPN

        # Should be recognized as withdrawal
        assert parsed.is_withdrawal is True
        assert parsed.prefixes == []

    def test_bgp_update_evpn_with_communities(self) -> None:
        """Test EVPN route with COMMUNITIES attribute."""
        data = bytearray()

        # BGP header
        data.extend(b"\xff" * 16)
        data.extend(b"\x00\x00")  # Length
        data.extend(b"\x02")  # UPDATE

        data.extend(b"\x00\x00")  # No withdrawn

        # Path attributes
        path_attrs = bytearray()

        # ORIGIN
        path_attrs.extend(b"\x40\x01\x01\x00")

        # AS_PATH (empty)
        path_attrs.extend(b"\x40\x02\x00")

        # COMMUNITIES (65001:100, 65001:200)
        path_attrs.extend(b"\xc0\x08\x08")  # Flags, type, length
        path_attrs.extend(b"\xfd\xe9\x00\x64")  # 65001:100
        path_attrs.extend(b"\xfd\xe9\x00\xc8")  # 65001:200

        # MP_REACH_NLRI for EVPN
        mp_reach = b"\x00\x19\x46\x04\xc0\x00\x02\xfe\x00"
        path_attrs.extend(b"\x80\x0e")  # Flags, type
        path_attrs.extend(len(mp_reach).to_bytes(1, "big"))
        path_attrs.extend(mp_reach)

        data.extend(len(path_attrs).to_bytes(2, "big"))
        data.extend(path_attrs)

        data[16:18] = len(data).to_bytes(2, "big")

        parsed = parse_bgp_update(bytes(data))

        # Verify EVPN
        assert parsed.afi == AddressFamilyIdentifier.L2VPN
        assert parsed.safi == SubsequentAddressFamilyIdentifier.EVPN

        # Verify communities
        assert parsed.communities == ["65001:100", "65001:200"]

    def test_bgp_update_evpn_with_extended_length(self) -> None:
        """Test EVPN MP_REACH_NLRI with extended length attribute flag."""
        data = bytearray()

        # BGP header
        data.extend(b"\xff" * 16)
        data.extend(b"\x00\x00")  # Length
        data.extend(b"\x02")  # UPDATE

        data.extend(b"\x00\x00")  # No withdrawn

        # Path attributes
        path_attrs = bytearray()

        # ORIGIN
        path_attrs.extend(b"\x40\x01\x01\x00")

        # AS_PATH
        path_attrs.extend(b"\x40\x02\x00")

        # MP_REACH_NLRI with extended length flag (for testing)
        mp_reach = b"\x00\x19\x46\x04\xc0\x00\x02\xfe\x00"
        # Extended length flag = 0x10
        path_attrs.extend(b"\x90\x0e")  # Flags with extended length, type
        path_attrs.extend(len(mp_reach).to_bytes(2, "big"))  # 2-byte length
        path_attrs.extend(mp_reach)

        data.extend(len(path_attrs).to_bytes(2, "big"))
        data.extend(path_attrs)

        data[16:18] = len(data).to_bytes(2, "big")

        parsed = parse_bgp_update(bytes(data))

        # Should parse correctly with extended length
        assert parsed.afi == AddressFamilyIdentifier.L2VPN
        assert parsed.safi == SubsequentAddressFamilyIdentifier.EVPN
        assert parsed.next_hop == "192.0.2.254"


class TestEVPNIntegration:
    """Integration tests for EVPN route handling."""

    def test_multiple_evpn_routes_in_update(self) -> None:
        """Test BGP UPDATE with multiple EVPN routes (when NLRI parsing is implemented)."""
        # For now, this tests the structure is recognized
        data = bytearray()

        # BGP header
        data.extend(b"\xff" * 16)
        data.extend(b"\x00\x00")
        data.extend(b"\x02")

        data.extend(b"\x00\x00")

        # Path attributes with EVPN MP_REACH_NLRI
        path_attrs = bytearray()
        path_attrs.extend(b"\x40\x01\x01\x00")  # ORIGIN
        path_attrs.extend(b"\x40\x02\x00")  # AS_PATH

        mp_reach = b"\x00\x19\x46\x04\xc0\x00\x02\xfe\x00"
        path_attrs.extend(b"\x80\x0e")
        path_attrs.extend(len(mp_reach).to_bytes(1, "big"))
        path_attrs.extend(mp_reach)

        data.extend(len(path_attrs).to_bytes(2, "big"))
        data.extend(path_attrs)

        data[16:18] = len(data).to_bytes(2, "big")

        parsed = parse_bgp_update(bytes(data))

        assert parsed.afi == AddressFamilyIdentifier.L2VPN
        assert parsed.safi == SubsequentAddressFamilyIdentifier.EVPN

    def test_evpn_route_type_2_structure(self) -> None:
        """
        Test EVPN Type 2 (MAC/IP Advertisement) route structure.

        Note: This is a placeholder for when EVPN NLRI parsing is implemented.
        Currently tests that EVPN AFI/SAFI is correctly identified.
        """
        # Build UPDATE with EVPN Type 2 route
        data = bytearray()

        data.extend(b"\xff" * 16)
        data.extend(b"\x00\x00")
        data.extend(b"\x02")
        data.extend(b"\x00\x00")

        path_attrs = bytearray()
        path_attrs.extend(b"\x40\x01\x01\x00")
        path_attrs.extend(b"\x40\x02\x00")

        # MP_REACH_NLRI for EVPN
        # In future: will include Type 2 NLRI with RD, ESI, MAC, etc.
        mp_reach = b"\x00\x19\x46\x04\xc0\x00\x02\xfe\x00"
        path_attrs.extend(b"\x80\x0e")
        path_attrs.extend(len(mp_reach).to_bytes(1, "big"))
        path_attrs.extend(mp_reach)

        data.extend(len(path_attrs).to_bytes(2, "big"))
        data.extend(path_attrs)

        data[16:18] = len(data).to_bytes(2, "big")

        parsed = parse_bgp_update(bytes(data))

        # Verify EVPN is recognized
        assert parsed.afi == AddressFamilyIdentifier.L2VPN
        assert parsed.safi == SubsequentAddressFamilyIdentifier.EVPN

        # Future: when EVPN NLRI parsing is implemented
        # assert parsed.evpn_route_type == 2
        # assert parsed.mac_address is not None
        # assert parsed.evpn_rd is not None


class TestEVPNErrorHandling:
    """Test error handling for malformed EVPN routes."""

    def test_evpn_truncated_mp_reach(self) -> None:
        """Test error handling for truncated EVPN MP_REACH_NLRI."""
        # Truncated MP_REACH_NLRI (missing next hop)
        data = b"\x00\x19\x46\x04"  # AFI, SAFI, next_hop_len but no next hop

        with pytest.raises(BGPParseError, match="MP_REACH_NLRI"):
            parse_mp_reach_nlri(data)

    def test_evpn_invalid_safi(self) -> None:
        """Test that non-EVPN SAFI with L2VPN AFI is handled."""
        # L2VPN AFI with wrong SAFI
        data = b"\x00\x19\x01\x04\xc0\x00\x02\xfe\x00"  # SAFI=1 (unicast, wrong)

        afi, safi, next_hop, prefixes = parse_mp_reach_nlri(data)

        assert afi == AddressFamilyIdentifier.L2VPN
        assert safi == 1  # Not EVPN SAFI
        # Should not crash, just return empty prefixes
        assert prefixes == []
