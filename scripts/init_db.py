#!/usr/bin/env python3
"""
Database initialization script.

Connects to PostgreSQL and runs migration files to set up the schema.
Can be run standalone or as part of application startup.
"""

import asyncio
import sys
from pathlib import Path

import asyncpg

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pybmpmon.config import Settings


async def run_migration_file(conn: asyncpg.Connection, filepath: Path) -> None:
    """
    Execute a SQL migration file.

    Args:
        conn: Database connection
        filepath: Path to SQL file

    Raises:
        Exception: On SQL execution errors
    """
    print(f"Running migration: {filepath.name}")

    sql = filepath.read_text()

    try:
        await conn.execute(sql)
        print(f"✓ {filepath.name} completed successfully")
    except Exception as e:
        print(f"✗ {filepath.name} failed: {e}")
        raise


async def initialize_database(
    host: str, port: int, database: str, user: str, password: str
) -> None:
    """
    Initialize database with schema migrations.

    Args:
        host: Database host
        port: Database port
        database: Database name
        user: Database user
        password: Database password
    """
    print(f"Connecting to database at {host}:{port}/{database}")

    try:
        conn = await asyncpg.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
        )

        print("✓ Connected to database")

        # Find migration files
        migrations_dir = (
            Path(__file__).parent.parent
            / "src"
            / "pybmpmon"
            / "database"
            / "migrations"
        )

        if not migrations_dir.exists():
            print(f"✗ Migrations directory not found: {migrations_dir}")
            sys.exit(1)

        migration_files = sorted(migrations_dir.glob("*.sql"))

        if not migration_files:
            print(f"✗ No migration files found in {migrations_dir}")
            sys.exit(1)

        print(f"\nFound {len(migration_files)} migration file(s)")

        # Run migrations in order
        for filepath in migration_files:
            await run_migration_file(conn, filepath)

        print("\n✓ Database initialization completed successfully")

        await conn.close()

    except asyncpg.PostgresError as e:
        print(f"\n✗ Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    # Load settings from environment
    settings = Settings()

    print("=" * 60)
    print("PyBMPMon Database Initialization")
    print("=" * 60)
    print()

    asyncio.run(
        initialize_database(
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
        )
    )


if __name__ == "__main__":
    main()
