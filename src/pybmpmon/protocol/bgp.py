"""BGP protocol definitions and message types per RFC4271 and RFC4760."""

from enum import IntEnum
from typing import Any, NamedTuple


class BGPMessageType(IntEnum):
    """BGP message types per RFC4271."""

    OPEN = 1
    UPDATE = 2
    NOTIFICATION = 3
    KEEPALIVE = 4


class BGPPathAttributeType(IntEnum):
    """BGP path attribute types per RFC4271."""

    ORIGIN = 1
    AS_PATH = 2
    NEXT_HOP = 3
    MULTI_EXIT_DISC = 4
    LOCAL_PREF = 5
    ATOMIC_AGGREGATE = 6
    AGGREGATOR = 7
    COMMUNITIES = 8
    MP_REACH_NLRI = 14  # RFC4760 - Multiprotocol Extensions
    MP_UNREACH_NLRI = 15  # RFC4760 - Multiprotocol Extensions
    EXTENDED_COMMUNITIES = 16
    AS4_PATH = 17
    AS4_AGGREGATOR = 18


class BGPOrigin(IntEnum):
    """BGP origin codes."""

    IGP = 0
    EGP = 1
    INCOMPLETE = 2


class BGPASPathSegmentType(IntEnum):
    """BGP AS_PATH segment types."""

    AS_SET = 1
    AS_SEQUENCE = 2


class AddressFamilyIdentifier(IntEnum):
    """Address Family Identifier per RFC4760."""

    IPV4 = 1
    IPV6 = 2
    L2VPN = 25  # EVPN uses L2VPN AFI


class SubsequentAddressFamilyIdentifier(IntEnum):
    """Subsequent Address Family Identifier per RFC4760."""

    UNICAST = 1
    MULTICAST = 2
    MPLS_LABELED_VPN = 128
    EVPN = 70  # RFC7432


class EVPNRouteType(IntEnum):
    """EVPN route types per RFC7432."""

    ETHERNET_AUTO_DISCOVERY = 1
    MAC_IP_ADVERTISEMENT = 2
    INCLUSIVE_MULTICAST = 3
    ETHERNET_SEGMENT = 4
    IP_PREFIX = 5


class BGPHeader(NamedTuple):
    """BGP message header (19 bytes)."""

    marker: bytes  # 16 bytes, all ones
    length: int  # 2 bytes
    msg_type: BGPMessageType  # 1 byte


class BGPPathAttribute(NamedTuple):
    """BGP path attribute."""

    flags: int  # 1 byte
    type_code: BGPPathAttributeType  # 1 byte
    length: int  # 1 or 2 bytes depending on extended length flag
    value: bytes  # Variable length


class BGPUpdateMessage(NamedTuple):
    """BGP UPDATE message structure."""

    withdrawn_routes_length: int
    withdrawn_routes: bytes
    total_path_attr_length: int
    path_attributes: list[BGPPathAttribute]
    nlri: bytes  # Network Layer Reachability Information


class ParsedBGPUpdate(NamedTuple):
    """Parsed BGP UPDATE message with extracted data."""

    # Basic route information
    afi: int | None  # Address Family Identifier
    safi: int | None  # Subsequent Address Family Identifier
    # Prefixes can be strings (IPv4/IPv6 CIDR) or dicts (EVPN route info)
    prefixes: list[str | dict[str, Any]]
    withdrawn_prefixes: list[str | dict[str, Any]]
    is_withdrawal: bool  # True if this is a withdrawal

    # Path attributes
    origin: int | None
    as_path: list[int] | None
    next_hop: str | None
    med: int | None
    local_pref: int | None
    communities: list[str] | None
    extended_communities: list[str] | None

    # EVPN-specific
    evpn_route_type: int | None
    evpn_rd: str | None
    evpn_esi: str | None
    mac_address: str | None


# Constants
BGP_HEADER_SIZE = 19  # bytes
BGP_MARKER = b"\xff" * 16

# Path attribute flags
ATTR_FLAG_OPTIONAL = 0x80
ATTR_FLAG_TRANSITIVE = 0x40
ATTR_FLAG_PARTIAL = 0x20
ATTR_FLAG_EXTENDED_LENGTH = 0x10


class BGPParseError(Exception):
    """Exception raised when BGP message parsing fails."""

    pass
