"""Database schema definitions and table structures."""

from typing import Final

# Table names
TABLE_ROUTE_UPDATES: Final[str] = "route_updates"
TABLE_BMP_PEERS: Final[str] = "bmp_peers"
TABLE_PEER_EVENTS: Final[str] = "peer_events"

# Route families
FAMILY_IPV4_UNICAST: Final[str] = "ipv4_unicast"
FAMILY_IPV6_UNICAST: Final[str] = "ipv6_unicast"
FAMILY_EVPN: Final[str] = "evpn"

# Peer event types
EVENT_PEER_UP: Final[str] = "peer_up"
EVENT_PEER_DOWN: Final[str] = "peer_down"
