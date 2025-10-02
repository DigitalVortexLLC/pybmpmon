-- Restore MACADDR type with custom asyncpg codec
-- Previous migration (003) changed to TEXT due to missing binary encoder
-- Now we have a custom codec registered in connection.py
-- This migration converts back to MACADDR for proper type safety

ALTER TABLE route_updates
    ALTER COLUMN mac_address TYPE MACADDR USING mac_address::MACADDR;

-- Update the index (it should still work with MACADDR)
-- No need to recreate, PostgreSQL handles this automatically
