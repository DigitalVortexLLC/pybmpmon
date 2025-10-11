"""Unit tests for listener EVPN route handling."""

from pybmpmon.listener import BMPListener


class TestListenerEVPNHelper:
    """Test listener's EVPN prefix extraction helper."""

    def test_extract_prefix_string_ipv4_cidr(self) -> None:
        """Test extracting prefix from IPv4 CIDR string."""
        listener = BMPListener.__new__(BMPListener)  # Create without __init__

        prefix = "10.0.0.0/24"
        result = listener._extract_prefix_string(prefix)

        assert result == "10.0.0.0/24"

    def test_extract_prefix_string_ipv6_cidr(self) -> None:
        """Test extracting prefix from IPv6 CIDR string."""
        listener = BMPListener.__new__(BMPListener)

        prefix = "2001:db8::/32"
        result = listener._extract_prefix_string(prefix)

        assert result == "2001:db8::/32"

    def test_extract_prefix_string_evpn_with_ipv4(self) -> None:
        """Test extracting prefix from EVPN dict with IPv4 address."""
        listener = BMPListener.__new__(BMPListener)

        evpn_route = {
            "route_type": 2,
            "rd": "65001:100",
            "esi": "00:11:22:33:44:55:66:77:88:99",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "ip_address": "192.168.1.10",
        }
        result = listener._extract_prefix_string(evpn_route)

        assert result == "192.168.1.10/32"

    def test_extract_prefix_string_evpn_with_ipv6(self) -> None:
        """Test extracting prefix from EVPN dict with IPv6 address."""
        listener = BMPListener.__new__(BMPListener)

        evpn_route = {
            "route_type": 2,
            "rd": "65001:100",
            "esi": "00:11:22:33:44:55:66:77:88:99",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "ip_address": "2001:db8::1",
        }
        result = listener._extract_prefix_string(evpn_route)

        assert result == "2001:db8::1/128"

    def test_extract_prefix_string_evpn_without_ip(self) -> None:
        """Test extracting prefix from EVPN dict without IP (MAC-only)."""
        listener = BMPListener.__new__(BMPListener)

        evpn_route = {
            "route_type": 2,
            "rd": "65001:100",
            "esi": "00:11:22:33:44:55:66:77:88:99",
            "mac_address": "aa:bb:cc:dd:ee:ff",
        }
        result = listener._extract_prefix_string(evpn_route)

        # No IP address - returns None (prefix will be NULL in database)
        assert result is None

    def test_extract_prefix_string_evpn_with_none_ip(self) -> None:
        """Test extracting prefix from EVPN dict with explicit None IP."""
        listener = BMPListener.__new__(BMPListener)

        evpn_route = {
            "route_type": 2,
            "rd": "65001:100",
            "esi": "00:11:22:33:44:55:66:77:88:99",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "ip_address": None,
        }
        result = listener._extract_prefix_string(evpn_route)

        assert result is None
