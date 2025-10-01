-- Create indexes for efficient queries on route_updates and peer_events

-- Route lookups by prefix
CREATE INDEX IF NOT EXISTS idx_route_prefix
    ON route_updates (prefix)
    WHERE prefix IS NOT NULL;

-- Route lookups by family and time
CREATE INDEX IF NOT EXISTS idx_route_family
    ON route_updates (family, time DESC);

-- EVPN MAC address lookups
CREATE INDEX IF NOT EXISTS idx_route_mac
    ON route_updates (mac_address)
    WHERE mac_address IS NOT NULL;

-- EVPN RD lookups
CREATE INDEX IF NOT EXISTS idx_route_evpn_rd
    ON route_updates (evpn_rd)
    WHERE evpn_rd IS NOT NULL;

-- AS path searches using GIN index
CREATE INDEX IF NOT EXISTS idx_route_aspath
    ON route_updates USING GIN (as_path);

-- BMP peer lookups
CREATE INDEX IF NOT EXISTS idx_route_bmp_peer
    ON route_updates (bmp_peer_ip, time DESC);

-- BGP peer lookups
CREATE INDEX IF NOT EXISTS idx_route_bgp_peer
    ON route_updates (bgp_peer_ip, time DESC);

-- Withdrawn routes lookup
CREATE INDEX IF NOT EXISTS idx_route_withdrawn
    ON route_updates (is_withdrawn, time DESC)
    WHERE is_withdrawn = TRUE;

-- Next hop lookups
CREATE INDEX IF NOT EXISTS idx_route_next_hop
    ON route_updates (next_hop)
    WHERE next_hop IS NOT NULL;

-- Peer events lookups
CREATE INDEX IF NOT EXISTS idx_peer_events_peer
    ON peer_events (peer_ip, time DESC);

CREATE INDEX IF NOT EXISTS idx_peer_events_type
    ON peer_events (event_type, time DESC);
