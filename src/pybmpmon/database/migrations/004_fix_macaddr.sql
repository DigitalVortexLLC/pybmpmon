-- Restore MACADDR type with custom asyncpg codec
-- Previous migration (003) changed to TEXT due to missing binary encoder
-- Now we have a custom codec registered in connection.py
-- This migration converts back to MACADDR for proper type safety

-- Only run this migration if the column is currently TEXT
-- For fresh installs, 001_initial.sql already creates it as MACADDR
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'route_updates'
        AND column_name = 'mac_address'
        AND data_type = 'text'
    ) THEN
        -- Decompress the table before altering (required for hypertables)
        ALTER TABLE route_updates SET (
            timescaledb.compress = false
        );

        -- Alter column type
        ALTER TABLE route_updates
            ALTER COLUMN mac_address TYPE MACADDR USING mac_address::MACADDR;

        -- Re-enable compression
        ALTER TABLE route_updates SET (
            timescaledb.compress = true,
            timescaledb.compress_segmentby = 'bmp_peer_ip,bgp_peer_ip',
            timescaledb.compress_orderby = 'time DESC'
        );
    END IF;
END $$;
