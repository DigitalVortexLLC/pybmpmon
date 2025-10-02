-- Fix MACADDR column to TEXT for asyncpg compatibility
-- asyncpg doesn't have a binary encoder for MACADDR type (OID 829)
-- Using TEXT allows MAC addresses to be stored as strings

ALTER TABLE route_updates
    ALTER COLUMN mac_address TYPE TEXT;

-- Update the index (it should still work with TEXT)
-- No need to recreate, PostgreSQL handles this automatically
