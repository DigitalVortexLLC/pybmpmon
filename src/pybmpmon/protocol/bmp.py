"""BMP protocol definitions and message types per RFC7854."""

from enum import IntEnum
from typing import NamedTuple


class BMPVersion(IntEnum):
    """BMP protocol version."""

    VERSION_3 = 3


class BMPMessageType(IntEnum):
    """BMP message types per RFC7854 Section 4.1."""

    ROUTE_MONITORING = 0
    STATISTICS_REPORT = 1
    PEER_DOWN_NOTIFICATION = 2
    PEER_UP_NOTIFICATION = 3
    INITIATION = 4
    TERMINATION = 5


class BMPPeerType(IntEnum):
    """BMP Peer Type per RFC7854 Section 4.2."""

    GLOBAL_INSTANCE = 0
    RD_INSTANCE = 1
    LOCAL_INSTANCE = 2
    LOC_RIB_INSTANCE = 3


class BMPPeerFlags(IntEnum):
    """BMP Peer Flags per RFC7854 Section 4.2."""

    IPV6 = 0x80  # Bit 0: V flag (IPv6)
    POST_POLICY = 0x40  # Bit 1: L flag (Post-policy)
    AS_PATH_2BYTE = 0x20  # Bit 2: A flag (2-byte AS_PATH)


class BMPPeerDownReason(IntEnum):
    """BMP Peer Down Reason Codes per RFC7854 Section 4.9."""

    LOCAL_NOTIFICATION = 1  # Local system closed session with notification
    LOCAL_NO_NOTIFICATION = 2  # Local system closed session without notification
    REMOTE_NOTIFICATION = 3  # Remote system closed session with notification
    REMOTE_NO_NOTIFICATION = 4  # Remote system closed session without notification
    PEER_DE_CONFIGURED = 5  # Information for this peer will no longer be sent


class BMPInfoTLVType(IntEnum):
    """BMP Information TLV Types per RFC7854 Section 4.4."""

    STRING = 0  # Free-form UTF-8 string
    SYS_DESCR = 1  # System Description (sysDescr)
    SYS_NAME = 2  # System Name (sysName)


class BMPStatType(IntEnum):
    """BMP Statistics Types per RFC7854 Section 4.8."""

    REJECTED_PREFIXES = 0
    DUPLICATE_PREFIX_ADVERTISEMENTS = 1
    DUPLICATE_WITHDRAWALS = 2
    CLUSTER_LIST_LOOP = 3
    AS_PATH_LOOP = 4
    ORIGINATOR_ID_LOOP = 5
    AS_CONFED_LOOP = 6
    ROUTES_ADJ_RIB_IN = 7
    ROUTES_LOC_RIB = 8
    ROUTES_PER_AFI_SAFI_ADJ_RIB_IN = 9
    ROUTES_PER_AFI_SAFI_LOC_RIB = 10
    UPDATE_TREAT_AS_WITHDRAW = 11


class BMPHeader(NamedTuple):
    """BMP common header structure (6 bytes total)."""

    version: int  # 1 byte
    length: int  # 4 bytes (message length in bytes)
    msg_type: BMPMessageType  # 1 byte


class BMPPerPeerHeader(NamedTuple):
    """BMP Per-Peer Header per RFC7854 Section 4.2 (42 bytes total)."""

    peer_type: BMPPeerType  # 1 byte
    peer_flags: int  # 1 byte
    peer_distinguisher: bytes  # 8 bytes
    peer_address: str  # 16 bytes (IPv4 or IPv6)
    peer_asn: int  # 4 bytes
    peer_bgp_id: str  # 4 bytes (IPv4 address format)
    timestamp_sec: int  # 4 bytes
    timestamp_usec: int  # 4 bytes


class BMPInfoTLV(NamedTuple):
    """BMP Information TLV per RFC7854 Section 4.4."""

    info_type: int  # 2 bytes
    info_length: int  # 2 bytes
    info_value: bytes  # variable length


class BMPStatTLV(NamedTuple):
    """BMP Statistics TLV per RFC7854 Section 4.8."""

    stat_type: int  # 2 bytes
    stat_length: int  # 2 bytes
    stat_value: int  # variable (typically 4 or 8 bytes)


class BMPInitiationMessage(NamedTuple):
    """BMP Initiation Message per RFC7854 Section 4.3."""

    header: BMPHeader
    information_tlvs: list[BMPInfoTLV]


class BMPTerminationMessage(NamedTuple):
    """BMP Termination Message per RFC7854 Section 4.4."""

    header: BMPHeader
    information_tlvs: list[BMPInfoTLV]


class BMPRouteMonitoringMessage(NamedTuple):
    """BMP Route Monitoring Message per RFC7854 Section 4.6."""

    header: BMPHeader
    per_peer_header: BMPPerPeerHeader
    bgp_update: bytes  # Raw BGP UPDATE PDU


class BMPStatisticsReportMessage(NamedTuple):
    """BMP Statistics Report Message per RFC7854 Section 4.8."""

    header: BMPHeader
    per_peer_header: BMPPerPeerHeader
    stats_count: int  # 4 bytes
    stats_tlvs: list[BMPStatTLV]


class BMPPeerDownMessage(NamedTuple):
    """BMP Peer Down Notification per RFC7854 Section 4.9."""

    header: BMPHeader
    per_peer_header: BMPPerPeerHeader
    reason: BMPPeerDownReason
    data: bytes  # Additional data based on reason


class BMPPeerUpMessage(NamedTuple):
    """BMP Peer Up Notification per RFC7854 Section 4.10."""

    header: BMPHeader
    per_peer_header: BMPPerPeerHeader
    local_address: str  # 16 bytes (IPv4 or IPv6)
    local_port: int  # 2 bytes
    remote_port: int  # 2 bytes
    sent_open_message: bytes  # Variable length BGP OPEN
    received_open_message: bytes  # Variable length BGP OPEN
    information_tlvs: list[BMPInfoTLV]  # Optional


# Constants
BMP_HEADER_SIZE = 6  # bytes
BMP_PER_PEER_HEADER_SIZE = 42  # bytes
BMP_CURRENT_VERSION = BMPVersion.VERSION_3


class BMPParseError(Exception):
    """Exception raised when BMP message parsing fails."""

    pass
