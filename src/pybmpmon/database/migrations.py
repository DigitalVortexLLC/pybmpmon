"""Database migration system with tracking and validation."""

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

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
        self.migrations_dir = Path(__file__).parent / "migrations"

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
