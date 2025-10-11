-- Bootstrap migration tracking system
-- This migration creates the schema_migrations table to track applied migrations

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    execution_time_ms INTEGER NOT NULL
);

-- Create index for quick lookups
CREATE INDEX IF NOT EXISTS idx_schema_migrations_applied_at
ON schema_migrations(applied_at DESC);

-- Add comment
COMMENT ON TABLE schema_migrations IS
'Tracks database migrations applied to this database';
