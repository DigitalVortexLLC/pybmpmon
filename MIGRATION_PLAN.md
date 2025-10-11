# Migration Tracking System Implementation Plan

## Overview

This plan implements a robust database migration tracking system that:
- Tracks which migrations have been applied
- Validates migration integrity with checksums
- Applies migrations automatically on application startup
- Handles both fresh databases and existing installations
- Provides rollback capability for failed migrations

## Changes Summary

### New Files
1. `src/pybmpmon/database/migrations/000_bootstrap.sql` - Migration tracking table
2. `src/pybmpmon/database/migrations/007_optimize_compression.sql` - Compression optimizations
3. `tests/unit/test_migrations.py` - Unit tests for migration system

### Modified Files
1. `src/pybmpmon/database/migrations.py` - Complete rewrite with tracking
2. `src/pybmpmon/__main__.py` - Enhanced migration application
3. `tests/integration/test_database.py` - Integration tests

---

## File Changes Detail

### 1. New: `src/pybmpmon/database/migrations/000_bootstrap.sql`

Creates the migration tracking infrastructure.

```sql
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
```

**Placement**: This will be applied first, before any other migrations.

---

### 2. New: `src/pybmpmon/database/migrations/007_optimize_compression.sql`

Optimizes TimescaleDB compression settings for better space savings.

```sql
-- Optimize TimescaleDB compression for route_updates table
-- Expected compression ratio: 5-6x (from ~500GB to ~85GB per 5 years)

-- Drop existing compression policy (if any)
SELECT remove_compression_policy('route_updates', if_exists => true);

-- Update compression settings with better column ordering
-- Note: 'family' is in segmentby, so it cannot also be in orderby
-- (TimescaleDB constraint: columns cannot be in both)
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
```

**Benefits**:
- Reduces storage from ~500GB to ~85GB per 5 years (5-6x compression)
- Faster queries on compressed data
- Automatic compression after 7 days
- Better compression with optimized segmentby/orderby

---

### 3. Modified: `src/pybmpmon/database/migrations.py`

Complete rewrite with migration tracking and validation.

```python
"""Database migration system with tracking and validation."""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg  # type: ignore[import-untyped]

from pybmpmon.monitoring.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Migration:
    """Represents a database migration file."""

    version: int
    name: str
    file_path: Path

    @property
    def checksum(self) -> str:
        """Calculate SHA256 checksum of migration file."""
        return hashlib.sha256(self.file_path.read_bytes()).hexdigest()

    @property
    def sql(self) -> str:
        """Read migration SQL content."""
        return self.file_path.read_text()


class MigrationRunner:
    """Manages database migrations with tracking and validation."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        """
        Initialize migration runner.

        Args:
            pool: Database connection pool
        """
        self.pool = pool
        self.migrations_dir = (
            Path(__file__).parent / "migrations"
        )

    async def get_pending_migrations(self) -> list[Migration]:
        """
        Get list of pending migrations that haven't been applied.

        Returns:
            List of Migration objects to apply
        """
        # Load all migration files
        all_migrations = self._load_migrations()

        # Get applied migrations
        async with self.pool.acquire() as conn:
            # Check if schema_migrations table exists
            exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'schema_migrations'
                )
                """
            )

            if not exists:
                # Fresh database - all migrations are pending
                logger.info(
                    "schema_migrations_not_found",
                    pending_count=len(all_migrations),
                )
                return all_migrations

            # Get applied migration versions
            applied = await conn.fetch(
                "SELECT version, checksum FROM schema_migrations ORDER BY version"
            )

            applied_versions = {row["version"]: row["checksum"] for row in applied}

        # Find pending migrations
        pending = []
        for migration in all_migrations:
            if migration.version not in applied_versions:
                pending.append(migration)
            else:
                # Verify checksum hasn't changed
                if migration.checksum != applied_versions[migration.version]:
                    logger.error(
                        "migration_checksum_mismatch",
                        version=migration.version,
                        name=migration.name,
                        expected=applied_versions[migration.version],
                        actual=migration.checksum,
                    )
                    raise ValueError(
                        f"Migration {migration.version} checksum mismatch - "
                        f"file may have been tampered with"
                    )

        return pending

    async def apply_migrations(self) -> int:
        """
        Apply all pending migrations.

        Returns:
            Number of migrations applied

        Raises:
            Exception: If any migration fails
        """
        pending = await self.get_pending_migrations()

        if not pending:
            logger.info("migrations_up_to_date")
            return 0

        logger.info(
            "migrations_pending",
            count=len(pending),
            versions=[m.version for m in pending],
        )

        applied_count = 0
        for migration in pending:
            await self._apply_migration(migration)
            applied_count += 1

        logger.info("migrations_complete", applied_count=applied_count)
        return applied_count

    async def _apply_migration(self, migration: Migration) -> None:
        """
        Apply a single migration within a transaction.

        Args:
            migration: Migration to apply

        Raises:
            Exception: If migration fails
        """
        import time

        start_time = time.time()

        logger.info(
            "migration_applying",
            version=migration.version,
            name=migration.name,
        )

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                try:
                    # Execute migration SQL
                    await conn.execute(migration.sql)

                    # Record migration in tracking table
                    execution_time_ms = int((time.time() - start_time) * 1000)
                    await conn.execute(
                        """
                        INSERT INTO schema_migrations
                        (version, name, checksum, execution_time_ms)
                        VALUES ($1, $2, $3, $4)
                        """,
                        migration.version,
                        migration.name,
                        migration.checksum,
                        execution_time_ms,
                    )

                    logger.info(
                        "migration_applied",
                        version=migration.version,
                        name=migration.name,
                        duration_ms=execution_time_ms,
                    )

                except Exception as e:
                    logger.error(
                        "migration_failed",
                        version=migration.version,
                        name=migration.name,
                        error=str(e),
                    )
                    raise

    def _load_migrations(self) -> list[Migration]:
        """
        Load all migration files from migrations directory.

        Returns:
            List of Migration objects sorted by version
        """
        migrations = []

        for file_path in sorted(self.migrations_dir.glob("*.sql")):
            # Parse filename: 001_initial.sql -> version=1, name="initial"
            parts = file_path.stem.split("_", 1)
            if len(parts) != 2:
                logger.warning(
                    "migration_invalid_filename",
                    filename=file_path.name,
                )
                continue

            try:
                version = int(parts[0])
                name = parts[1]
            except ValueError:
                logger.warning(
                    "migration_invalid_version",
                    filename=file_path.name,
                )
                continue

            migrations.append(
                Migration(version=version, name=name, file_path=file_path)
            )

        return sorted(migrations, key=lambda m: m.version)


async def apply_migrations(pool: asyncpg.Pool) -> None:
    """
    Apply all pending database migrations.

    Args:
        pool: Database connection pool

    Raises:
        Exception: If migrations fail
    """
    runner = MigrationRunner(pool)
    await runner.apply_migrations()
```

**Key Features**:
- Checksum validation prevents tampering
- Transaction-based application (rollback on failure)
- Tracks execution time for each migration
- Handles both fresh and existing databases
- Clear logging at each step

---

### 4. Modified: `src/pybmpmon/__main__.py`

Update to use new migration system.

**Current code** (around line 60-70):
```python
# Apply database migrations
logger.info("applying_database_migrations")
await apply_migrations(pool)
```

**New code**:
```python
# Apply database migrations
logger.info("checking_database_migrations")
from pybmpmon.database.migrations import MigrationRunner

runner = MigrationRunner(pool)
applied_count = await runner.apply_migrations()

if applied_count > 0:
    logger.info("database_migrations_applied", count=applied_count)
else:
    logger.info("database_migrations_up_to_date")
```

---

### 5. New: `tests/unit/test_migrations.py`

Unit tests for migration system.

```python
"""Unit tests for migration system."""

from pathlib import Path
from unittest import mock

import pytest

from pybmpmon.database.migrations import Migration, MigrationRunner


class TestMigration:
    """Test Migration class."""

    def test_migration_checksum(self, tmp_path: Path) -> None:
        """Test migration checksum calculation."""
        # Create test migration file
        migration_file = tmp_path / "001_test.sql"
        migration_file.write_text("SELECT 1;")

        migration = Migration(
            version=1, name="test", file_path=migration_file
        )

        # Verify checksum is consistent
        checksum1 = migration.checksum
        checksum2 = migration.checksum
        assert checksum1 == checksum2

        # Verify checksum changes when content changes
        migration_file.write_text("SELECT 2;")
        checksum3 = migration.checksum
        assert checksum1 != checksum3

    def test_migration_sql_property(self, tmp_path: Path) -> None:
        """Test migration SQL content reading."""
        migration_file = tmp_path / "001_test.sql"
        sql_content = "CREATE TABLE test (id INTEGER);"
        migration_file.write_text(sql_content)

        migration = Migration(
            version=1, name="test", file_path=migration_file
        )

        assert migration.sql == sql_content


class TestMigrationRunner:
    """Test MigrationRunner class."""

    def test_load_migrations(self, tmp_path: Path) -> None:
        """Test loading migrations from directory."""
        # Create test migrations
        (tmp_path / "001_first.sql").write_text("SELECT 1;")
        (tmp_path / "002_second.sql").write_text("SELECT 2;")
        (tmp_path / "003_third.sql").write_text("SELECT 3;")

        # Mock runner with test directory
        runner = MigrationRunner(mock.MagicMock())
        runner.migrations_dir = tmp_path

        migrations = runner._load_migrations()

        assert len(migrations) == 3
        assert migrations[0].version == 1
        assert migrations[0].name == "first"
        assert migrations[1].version == 2
        assert migrations[1].name == "second"
        assert migrations[2].version == 3
        assert migrations[2].name == "third"

    def test_load_migrations_invalid_filename(self, tmp_path: Path) -> None:
        """Test loading migrations with invalid filenames."""
        # Create migrations with invalid names
        (tmp_path / "001_valid.sql").write_text("SELECT 1;")
        (tmp_path / "invalid.sql").write_text("SELECT 2;")
        (tmp_path / "abc_invalid.sql").write_text("SELECT 3;")

        runner = MigrationRunner(mock.MagicMock())
        runner.migrations_dir = tmp_path

        migrations = runner._load_migrations()

        # Only valid migration should be loaded
        assert len(migrations) == 1
        assert migrations[0].version == 1
        assert migrations[0].name == "valid"

    @pytest.mark.asyncio
    async def test_get_pending_migrations_fresh_database(
        self, tmp_path: Path
    ) -> None:
        """Test getting pending migrations on fresh database."""
        # Create test migrations
        (tmp_path / "001_first.sql").write_text("SELECT 1;")
        (tmp_path / "002_second.sql").write_text("SELECT 2;")

        # Mock pool that returns no schema_migrations table
        mock_conn = mock.MagicMock()
        mock_conn.fetchval = mock.AsyncMock(return_value=False)

        mock_pool = mock.MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        runner = MigrationRunner(mock_pool)
        runner.migrations_dir = tmp_path

        pending = await runner.get_pending_migrations()

        # All migrations should be pending
        assert len(pending) == 2
        assert pending[0].version == 1
        assert pending[1].version == 2

    @pytest.mark.asyncio
    async def test_get_pending_migrations_checksum_mismatch(
        self, tmp_path: Path
    ) -> None:
        """Test checksum validation detects tampering."""
        # Create test migration
        migration_file = tmp_path / "001_test.sql"
        migration_file.write_text("SELECT 1;")

        migration = Migration(
            version=1, name="test", file_path=migration_file
        )
        original_checksum = migration.checksum

        # Mock pool that returns different checksum
        mock_conn = mock.MagicMock()
        mock_conn.fetchval = mock.AsyncMock(return_value=True)
        mock_conn.fetch = mock.AsyncMock(
            return_value=[
                {"version": 1, "checksum": "wrong_checksum"}
            ]
        )

        mock_pool = mock.MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        runner = MigrationRunner(mock_pool)
        runner.migrations_dir = tmp_path

        # Should raise error on checksum mismatch
        with pytest.raises(ValueError, match="checksum mismatch"):
            await runner.get_pending_migrations()
```

---

### 6. Modified: `tests/integration/test_database.py`

Add integration test for migration system.

**Add this test**:
```python
@pytest.mark.asyncio
async def test_migration_system_integration(db_pool: asyncpg.Pool) -> None:
    """Test complete migration system workflow."""
    from pybmpmon.database.migrations import MigrationRunner

    runner = MigrationRunner(db_pool)

    # Apply migrations
    applied_count = await runner.apply_migrations()

    # Verify migrations were applied
    assert applied_count > 0

    # Verify schema_migrations table exists
    async with db_pool.acquire() as conn:
        exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'schema_migrations'
            )
            """
        )
        assert exists is True

        # Verify migrations were recorded
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM schema_migrations"
        )
        assert count == applied_count

    # Run migrations again - should be no-op
    applied_count2 = await runner.apply_migrations()
    assert applied_count2 == 0
```

---

## Implementation Order

1. **Create bootstrap migration** (`000_bootstrap.sql`)
2. **Update migrations.py** with new tracking system
3. **Create compression optimization** (`007_optimize_compression.sql`)
4. **Update __main__.py** to use new migration runner
5. **Add unit tests** (`test_migrations.py`)
6. **Add integration test** to `test_database.py`
7. **Run full test suite** to verify everything works
8. **Test on fresh database** - verify bootstrap works
9. **Test on existing database** - verify backfill works

---

## Testing Plan

### Unit Tests
- Migration checksum calculation
- Migration SQL loading
- Invalid filename handling
- Fresh database detection
- Checksum mismatch detection

### Integration Tests
- Complete migration workflow
- Bootstrap on fresh database
- Idempotent migrations (running twice)
- Checksum validation
- Rollback on failure

### Manual Testing
1. **Fresh database**: Start with empty PostgreSQL, verify all migrations apply
2. **Existing database**: Use production database, verify only new migrations apply
3. **Tampered migration**: Modify a migration file, verify checksum error
4. **Failed migration**: Create intentionally broken migration, verify rollback

---

## Rollback Plan

If issues are discovered after deployment:

1. **Revert compression settings** (if causing issues):
   ```sql
   -- Remove compression policy
   SELECT remove_compression_policy('route_updates');

   -- Restore old settings
   ALTER TABLE route_updates SET (
       timescaledb.compress,
       timescaledb.compress_segmentby = 'bmp_peer_ip, bgp_peer_ip',
       timescaledb.compress_orderby = 'time DESC'
   );

   -- Add old policy back
   SELECT add_compression_policy('route_updates', INTERVAL '30 days');
   ```

2. **Revert to old migration system**:
   - Git revert the feature branch
   - Old simple migration check will still work
   - schema_migrations table can remain (won't cause issues)

---

## Benefits

1. **Incremental Updates**: Can add migrations without re-running everything
2. **Tamper Detection**: Checksums prevent accidental or malicious changes
3. **Better Observability**: Track when each migration was applied
4. **Automatic Application**: No manual SQL scripts to run
5. **Better Compression**: 5-6x space savings with optimized settings
6. **Production Ready**: Transaction-based with rollback on failure

---

## Questions for Review

1. Should we manually compress existing chunks after applying 007, or wait for automatic compression?
2. Should compression interval be 7 days or keep at 30 days? (7 days = better compression, 30 days = less CPU)
3. Should we add a dry-run mode to preview migrations before applying?
4. Should we add a migration rollback command for development?

---

## Estimated Impact

- **Code changes**: ~400 lines added/modified
- **Storage savings**: ~85% reduction (500GB → 85GB per 5 years)
- **Compression CPU**: Minimal (<1% of total), runs in background
- **Query performance**: Improved on compressed chunks
- **Migration time**: <1 second for bootstrap, <5 seconds for compression optimization
