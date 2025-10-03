"""Pydantic models for BGP route updates."""

from datetime import datetime

from pydantic import BaseModel, Field, IPvAnyAddress


class RouteUpdate(BaseModel):
    """
    BGP route update from BMP monitoring.

    Stores complete route information with all BGP attributes.
    Supports IPv4 unicast, IPv6 unicast, and EVPN route families.
    """

    time: datetime = Field(
        default_factory=datetime.utcnow, description="Route update timestamp"
    )
    bmp_peer_ip: IPvAnyAddress = Field(..., description="BMP peer IP address")
    bmp_peer_asn: int | None = Field(None, description="BMP peer ASN")
    bgp_peer_ip: IPvAnyAddress = Field(
        ..., description="BGP peer IP address (from Per-Peer Header)"
    )
    bgp_peer_asn: int | None = Field(None, description="BGP peer ASN")

    # Route information
    family: str = Field(
        ..., description="Route family: ipv4_unicast, ipv6_unicast, or evpn"
    )
    prefix: str | None = Field(None, description="IP prefix (CIDR notation)")
    next_hop: IPvAnyAddress | None = Field(None, description="BGP next hop")
    as_path: list[int] | None = Field(None, description="AS_PATH attribute")
    communities: list[str] | None = Field(None, description="BGP communities")
    extended_communities: list[str] | None = Field(
        None, description="BGP extended communities"
    )
    med: int | None = Field(None, description="Multi-Exit Discriminator")
    local_pref: int | None = Field(None, description="Local preference")
    is_withdrawn: bool = Field(False, description="Whether route is withdrawn")

    # EVPN-specific fields (NULL for IPv4/IPv6)
    evpn_route_type: int | None = Field(None, description="EVPN route type")
    evpn_rd: str | None = Field(None, description="EVPN Route Distinguisher")
    evpn_esi: str | None = Field(None, description="EVPN Ethernet Segment Identifier")
    mac_address: str | None = Field(None, description="MAC address for EVPN")

    class Config:
        """Pydantic model configuration."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
