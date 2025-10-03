"""Database migration management."""

from pathlib import Path

import asyncpg  # type: ignore[import-untyped]
import structlog

logger = structlog.get_logger(__name__)


async def check_schema_exists(conn: asyncpg.Connection) -> bool:
    """
    Check if database schema exists by looking for route_updates table.

    Args:
        conn: Database connection

    Returns:
        True if schema exists, False otherwise
    """
    result = await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = 'route_updates'
        )
        """
    )
    return bool(result)


async def run_migrations(conn: asyncpg.Connection) -> None:
    """
    Run all migration files in order.

    Args:
        conn: Database connection

    Raises:
        FileNotFoundError: If migrations directory not found
        Exception: On SQL execution errors
    """
    # Find migrations directory
    migrations_dir = Path(__file__).parent / "migrations"

    if not migrations_dir.exists():
        raise FileNotFoundError(f"Migrations directory not found: {migrations_dir}")

    # Get all .sql files sorted by name
    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        logger.warning("no_migration_files", directory=str(migrations_dir))
        return

    logger.info("running_migrations", count=len(migration_files))

    for filepath in migration_files:
        logger.info("running_migration", file=filepath.name)

        # Read SQL content
        sql = filepath.read_text()

        try:
            # Execute migration
            await conn.execute(sql)
            logger.info("migration_completed", file=filepath.name)
        except Exception as e:
            logger.error(
                "migration_failed", file=filepath.name, error=str(e), exc_info=True
            )
            raise


async def initialize_database_schema(
    host: str, port: int, database: str, user: str, password: str
) -> None:
    """
    Initialize database schema if it doesn't exist.

    Checks if schema exists and runs migrations if needed.

    Args:
        host: Database host
        port: Database port
        database: Database name
        user: Database user
        password: Database password

    Raises:
        asyncpg.PostgresError: On database connection errors
        Exception: On migration errors
    """
    logger.info(
        "checking_database_schema",
        host=host,
        port=port,
        database=database,
    )

    # Connect to database
    conn = await asyncpg.connect(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
    )

    try:
        # Check if schema exists
        schema_exists = await check_schema_exists(conn)

        if schema_exists:
            logger.info("database_schema_exists")
        else:
            logger.info("database_schema_missing_initializing")
            await run_migrations(conn)
            logger.info("database_schema_initialized")

    finally:
        await conn.close()
