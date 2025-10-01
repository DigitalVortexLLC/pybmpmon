-- Convert tables to TimescaleDB hypertables and configure retention policies

-- Convert route_updates to hypertable with 1-week chunks
SELECT create_hypertable(
    'route_updates',
    'time',
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists => TRUE
);

-- Convert peer_events to hypertable with 1-week chunks
SELECT create_hypertable(
    'peer_events',
    'time',
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists => TRUE
);

-- Add 5-year retention policy for route_updates
SELECT add_retention_policy(
    'route_updates',
    INTERVAL '5 years',
    if_not_exists => TRUE
);

-- Add 6-month retention policy for peer_events
SELECT add_retention_policy(
    'peer_events',
    INTERVAL '6 months',
    if_not_exists => TRUE
);

-- Enable compression for route_updates (compress data older than 30 days)
ALTER TABLE route_updates SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'bmp_peer_ip,bgp_peer_ip',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy(
    'route_updates',
    INTERVAL '30 days',
    if_not_exists => TRUE
);

-- Enable compression for peer_events
ALTER TABLE peer_events SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'peer_ip',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy(
    'peer_events',
    INTERVAL '30 days',
    if_not_exists => TRUE
);
