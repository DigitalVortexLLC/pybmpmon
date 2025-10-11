-- Optimize TimescaleDB compression for route_updates table
-- Expected compression ratio: 5-6x (from ~500GB to ~85GB per 5 years)

-- Drop existing compression policy (if any)
SELECT remove_compression_policy('route_updates', if_exists => true);

-- Update compression settings with better column ordering
ALTER TABLE route_updates SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'bmp_peer_ip, bgp_peer_ip, family',
    timescaledb.compress_orderby = 'time DESC, prefix'
);

-- Add compression policy: compress chunks older than 7 days
-- (reduced from 30 days for better compression ratio)
SELECT add_compression_policy(
    'route_updates',
    INTERVAL '7 days',
    if_not_exists => true
);

-- Note: Compression happens automatically for chunks older than 7 days
-- To manually compress existing chunks, run:
-- SELECT compress_chunk(i, if_not_compressed => true)
-- FROM show_chunks('route_updates', older_than => INTERVAL '7 days') i;
