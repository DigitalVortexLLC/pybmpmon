#!/usr/bin/env python3
"""Decode a BMP message from hex string."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from pybmpmon.protocol.bmp_parser import parse_bmp_message
from pybmpmon.protocol.bgp_parser import parse_bgp_update


def decode_bmp_message(hex_string: str) -> None:
    """Decode and print BMP message details."""
    # Remove spaces and convert to bytes
    hex_string = hex_string.replace(" ", "").strip()
    data = bytes.fromhex(hex_string)

    print(f"Total message length: {len(data)} bytes\n")

    try:
        # Parse BMP message
        msg = parse_bmp_message(data)

        print("=== BMP Message ===")
        print(f"Version: {msg.header.version}")
        print(f"Length: {msg.header.length}")
        print(f"Type: {msg.header.msg_type.name}")
        print()

        # Check if it's a Route Monitoring message
        if hasattr(msg, "per_peer_header"):
            print("=== Per-Peer Header ===")
            pph = msg.per_peer_header
            print(f"Peer Type: {pph.peer_type.name}")
            print(f"Peer Flags: 0x{pph.peer_flags:02x}")
            print(f"Peer Address: {pph.peer_address}")
            print(f"Peer ASN: {pph.peer_asn}")
            print(f"Peer BGP ID: {pph.peer_bgp_id}")
            print(f"Timestamp: {pph.timestamp_sec}.{pph.timestamp_usec:06d}")
            print()

        # If it's Route Monitoring, parse the BGP UPDATE
        if hasattr(msg, "bgp_update"):
            print("=== BGP UPDATE ===")
            bgp_update = parse_bgp_update(msg.bgp_update)

            if bgp_update.afi and bgp_update.safi:
                print(f"AFI: {bgp_update.afi}, SAFI: {bgp_update.safi}")

            print(f"Is Withdrawal: {bgp_update.is_withdrawal}")

            if bgp_update.next_hop:
                print(f"Next Hop: {bgp_update.next_hop}")

            if bgp_update.as_path:
                print(f"AS Path: {bgp_update.as_path}")

            if bgp_update.origin is not None:
                origin_names = ["IGP", "EGP", "INCOMPLETE"]
                origin_name = (
                    origin_names[bgp_update.origin]
                    if bgp_update.origin < 3
                    else f"Unknown({bgp_update.origin})"
                )
                print(f"Origin: {origin_name}")

            if bgp_update.local_pref is not None:
                print(f"Local Preference: {bgp_update.local_pref}")

            if bgp_update.med is not None:
                print(f"MED: {bgp_update.med}")

            if bgp_update.communities:
                print(f"Communities: {bgp_update.communities}")

            if bgp_update.extended_communities:
                print(f"Extended Communities: {bgp_update.extended_communities}")

            print()
            print("=== Routes ===")

            if bgp_update.withdrawn_prefixes:
                print("Withdrawn Prefixes:")
                for prefix in bgp_update.withdrawn_prefixes:
                    print(f"  - {prefix}")

            if bgp_update.prefixes:
                print("Announced Prefixes:")
                for prefix in bgp_update.prefixes:
                    if isinstance(prefix, dict):
                        # EVPN route
                        print(f"  EVPN Route Type {prefix.get('route_type')}:")
                        if "rd" in prefix:
                            print(f"    RD: {prefix['rd']}")
                        if "esi" in prefix:
                            print(f"    ESI: {prefix['esi']}")
                        if "mac_address" in prefix:
                            print(f"    MAC: {prefix['mac_address']}")
                        if "ip_address" in prefix:
                            print(f"    IP: {prefix['ip_address']}")
                    else:
                        print(f"  - {prefix}")

            # EVPN-specific fields
            if bgp_update.evpn_route_type is not None:
                print()
                print(f"EVPN Route Type: {bgp_update.evpn_route_type}")
                if bgp_update.evpn_rd:
                    print(f"EVPN RD: {bgp_update.evpn_rd}")
                if bgp_update.evpn_esi:
                    print(f"EVPN ESI: {bgp_update.evpn_esi}")
                if bgp_update.mac_address:
                    print(f"MAC Address: {bgp_update.mac_address}")

    except Exception as e:
        print(f"Error parsing message: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    hex_msg = "03000000be0001c0000145a2eaf7d09f260494402000000000000000000002540000000045a2eafe68959a63000279a1ffffffffffffffffffffffffffffffff008e02000000774001010040020e020300000d1c00003b4100008e8c80040400004e3440050400000050400600c0070800008e8c88166821c00824d09f07d20d1c00030d1c00160d1c00560d1c023f0d1c02590d1c029a0d1c03850d1c07d4800e1c000201102604944020000000000000000000025400302604ca000163"
    decode_bmp_message(hex_msg)
