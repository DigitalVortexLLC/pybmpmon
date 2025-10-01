"""Pydantic models for BMP peer state."""

from datetime import datetime

from pydantic import BaseModel, Field, IPvAnyAddress


class BMPPeer(BaseModel):
    """
    BMP peer session state.

    Tracks BMP peering sessions with routers.
    """

    peer_ip: IPvAnyAddress = Field(..., description="BMP peer IP address")
    router_id: IPvAnyAddress | None = Field(
        None, description="BGP router ID of the peer"
    )
    first_seen: datetime = Field(
        default_factory=datetime.utcnow, description="First time peer was seen"
    )
    last_seen: datetime = Field(
        default_factory=datetime.utcnow, description="Last time peer was seen"
    )
    is_active: bool = Field(True, description="Whether the peer is currently active")

    class Config:
        """Pydantic model configuration."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class PeerEvent(BaseModel):
    """
    BMP peer up/down event.

    Logs when BMP peers connect or disconnect.
    """

    time: datetime = Field(
        default_factory=datetime.utcnow, description="Event timestamp"
    )
    peer_ip: IPvAnyAddress = Field(..., description="BMP peer IP address")
    event_type: str = Field(..., description="Event type: 'peer_up' or 'peer_down'")
    reason_code: int | None = Field(
        None, description="Reason code for peer down events"
    )

    class Config:
        """Pydantic model configuration."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
