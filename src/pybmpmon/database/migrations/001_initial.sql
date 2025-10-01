-- Initial database schema for pybmpmon
-- Creates core tables: route_updates, bmp_peers, peer_events

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- BMP peers table: tracks active BMP peering sessions
CREATE TABLE IF NOT EXISTS bmp_peers (
    peer_ip INET PRIMARY KEY,
    router_id INET,
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Route updates table (will be converted to hypertable)
-- Stores all route updates with full denormalization for simplicity
CREATE TABLE IF NOT EXISTS route_updates (
    time TIMESTAMPTZ NOT NULL,
    bmp_peer_ip INET NOT NULL,
    bmp_peer_asn INTEGER,
    bgp_peer_ip INET NOT NULL,
    bgp_peer_asn INTEGER,

    -- Route information
    family TEXT NOT NULL,  -- 'ipv4_unicast', 'ipv6_unicast', 'evpn'
    prefix CIDR,
    next_hop INET,
    as_path INTEGER[],
    communities TEXT[],
    med INTEGER,
    local_pref INTEGER,
    is_withdrawn BOOLEAN DEFAULT FALSE,

    -- EVPN-specific fields (NULL for IPv4/IPv6)
    evpn_route_type INTEGER,
    evpn_rd TEXT,
    evpn_esi TEXT,
    mac_address MACADDR
);

-- Peer events table (will be converted to hypertable)
-- Logs peer up/down events
CREATE TABLE IF NOT EXISTS peer_events (
    time TIMESTAMPTZ NOT NULL,
    peer_ip INET NOT NULL,
    event_type TEXT NOT NULL,  -- 'peer_up', 'peer_down'
    reason_code INTEGER
);

-- Create indexes on bmp_peers for faster lookups
CREATE INDEX IF NOT EXISTS idx_bmp_peers_active ON bmp_peers (is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_bmp_peers_last_seen ON bmp_peers (last_seen DESC);
