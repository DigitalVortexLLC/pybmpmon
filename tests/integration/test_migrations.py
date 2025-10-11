"""Integration tests for database migration functionality."""

import asyncpg  # type: ignore[import-untyped]
import pytest
from pybmpmon.database.migrations import (
    check_schema_exists,
    initialize_database_schema,
    run_migrations,
)
from testcontainers.postgres import PostgresContainer


@pytest.fixture
def postgres_container():
    """Start PostgreSQL/TimescaleDB container for tests."""
    with PostgresContainer("timescale/timescaledb:latest-pg16") as postgres:
        yield postgres


class TestDatabaseMigrations:
    """Test database migration functionality."""

    async def test_check_schema_exists_empty_database(self, postgres_container):
        """Test schema check on empty database returns False."""
        connection_url = postgres_container.get_connection_url()

        # Parse URL
        import re

        match = re.match(
            r"postgresql(?:\+\w+)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)",
            connection_url,
        )
        assert match is not None
        user, password, host, port, database = match.groups()

        # Connect to empty database
        conn = await asyncpg.connect(
            host=host,
            port=int(port),
            database=database,
            user=user,
            password=password,
        )

        try:
            # Check schema - should not exist
            exists = await check_schema_exists(conn)
            assert exists is False
        finally:
            await conn.close()

    async def test_run_migrations(self, postgres_container):
        """Test running migrations creates all tables."""
        connection_url = postgres_container.get_connection_url()

        # Parse URL
        import re

        match = re.match(
            r"postgresql(?:\+\w+)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)",
            connection_url,
        )
        assert match is not None
        user, password, host, port, database = match.groups()

        # Connect to database
        conn = await asyncpg.connect(
            host=host,
            port=int(port),
            database=database,
            user=user,
            password=password,
        )

        try:
            # Run migrations
            await run_migrations(conn)

            # Verify tables were created
            tables = await conn.fetch(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
                """
            )

            table_names = [row["table_name"] for row in tables]

            # Check for core tables
            assert "route_updates" in table_names
            assert "route_state" in table_names
            assert "bmp_peers" in table_names
            assert "peer_events" in table_names

            # Check schema exists now
            exists = await check_schema_exists(conn)
            assert exists is True

        finally:
            await conn.close()

    async def test_initialize_database_schema_empty_db(self, postgres_container):
        """Test initialize_database_schema on empty database."""
        connection_url = postgres_container.get_connection_url()

        # Parse URL
        import re

        match = re.match(
            r"postgresql(?:\+\w+)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)",
            connection_url,
        )
        assert match is not None
        user, password, host, port, database = match.groups()

        # Initialize schema
        await initialize_database_schema(
            host=host,
            port=int(port),
            database=database,
            user=user,
            password=password,
        )

        # Verify schema was created
        conn = await asyncpg.connect(
            host=host,
            port=int(port),
            database=database,
            user=user,
            password=password,
        )

        try:
            exists = await check_schema_exists(conn)
            assert exists is True

            # Verify we can insert data
            await conn.execute(
                """
                INSERT INTO bmp_peers (peer_ip, is_active)
                VALUES ('192.0.2.1', true)
                """
            )

            count = await conn.fetchval("SELECT COUNT(*) FROM bmp_peers")
            assert count == 1

        finally:
            await conn.close()

    async def test_initialize_database_schema_existing_schema(self, postgres_container):
        """Test initialize_database_schema on database with existing schema."""
        connection_url = postgres_container.get_connection_url()

        # Parse URL
        import re

        match = re.match(
            r"postgresql(?:\+\w+)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)",
            connection_url,
        )
        assert match is not None
        user, password, host, port, database = match.groups()

        # Initialize schema first time
        await initialize_database_schema(
            host=host,
            port=int(port),
            database=database,
            user=user,
            password=password,
        )

        # Insert test data
        conn = await asyncpg.connect(
            host=host,
            port=int(port),
            database=database,
            user=user,
            password=password,
        )

        try:
            await conn.execute(
                """
                INSERT INTO bmp_peers (peer_ip, is_active)
                VALUES ('192.0.2.1', true)
                """
            )
        finally:
            await conn.close()

        # Initialize schema second time - should skip migrations
        await initialize_database_schema(
            host=host,
            port=int(port),
            database=database,
            user=user,
            password=password,
        )

        # Verify data is still there (migrations didn't drop/recreate)
        conn = await asyncpg.connect(
            host=host,
            port=int(port),
            database=database,
            user=user,
            password=password,
        )

        try:
            count = await conn.fetchval("SELECT COUNT(*) FROM bmp_peers")
            assert count == 1
        finally:
            await conn.close()
