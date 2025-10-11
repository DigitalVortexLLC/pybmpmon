"""Integration tests for database migration system."""

import asyncpg  # type: ignore[import-untyped]
import pytest
from pybmpmon.database.migrations import MigrationRunner
from testcontainers.postgres import PostgresContainer


@pytest.fixture
def postgres_container():
    """Start PostgreSQL/TimescaleDB container for tests."""
    with PostgresContainer("timescale/timescaledb:latest-pg16") as postgres:
        yield postgres


class TestMigrationSystem:
    """Test complete migration system workflow."""

    @pytest.mark.asyncio
    async def test_migration_system_fresh_database(self, postgres_container) -> None:
        """Test migration system on fresh database."""
        connection_url = postgres_container.get_connection_url()

        # Parse URL
        import re

        match = re.match(
            r"postgresql(?:\+\w+)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)",
            connection_url,
        )
        assert match is not None
        user, password, host, port, database = match.groups()

        # Create connection pool
        pool = await asyncpg.create_pool(
            host=host,
            port=int(port),
            database=database,
            user=user,
            password=password,
            min_size=1,
            max_size=2,
        )

        try:
            runner = MigrationRunner(pool)

            # Apply migrations
            applied_count = await runner.apply_migrations()

            # Should have applied migrations
            assert applied_count > 0

            # Verify schema_migrations table exists
            async with pool.acquire() as conn:
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
                count = await conn.fetchval("SELECT COUNT(*) FROM schema_migrations")
                assert count == applied_count

                # Verify core tables exist
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
                assert "schema_migrations" in table_names

        finally:
            await pool.close()

    @pytest.mark.asyncio
    async def test_migration_system_idempotent(self, postgres_container) -> None:
        """Test that migrations are idempotent (can run multiple times)."""
        connection_url = postgres_container.get_connection_url()

        # Parse URL
        import re

        match = re.match(
            r"postgresql(?:\+\w+)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)",
            connection_url,
        )
        assert match is not None
        user, password, host, port, database = match.groups()

        # Create connection pool
        pool = await asyncpg.create_pool(
            host=host,
            port=int(port),
            database=database,
            user=user,
            password=password,
            min_size=1,
            max_size=2,
        )

        try:
            runner = MigrationRunner(pool)

            # Apply migrations first time
            applied_count1 = await runner.apply_migrations()
            assert applied_count1 > 0

            # Apply migrations second time - should be no-op
            applied_count2 = await runner.apply_migrations()
            assert applied_count2 == 0

            # Verify data is preserved
            async with pool.acquire() as conn:
                # Insert test data
                await conn.execute(
                    """
                    INSERT INTO bmp_peers (peer_ip, is_active)
                    VALUES ('192.0.2.1', true)
                    """
                )

                count = await conn.fetchval("SELECT COUNT(*) FROM bmp_peers")
                assert count == 1

            # Run migrations again - data should still be there
            applied_count3 = await runner.apply_migrations()
            assert applied_count3 == 0

            async with pool.acquire() as conn:
                count = await conn.fetchval("SELECT COUNT(*) FROM bmp_peers")
                assert count == 1

        finally:
            await pool.close()

    @pytest.mark.asyncio
    async def test_migration_checksums_recorded(self, postgres_container) -> None:
        """Test that migration checksums are recorded correctly."""
        connection_url = postgres_container.get_connection_url()

        # Parse URL
        import re

        match = re.match(
            r"postgresql(?:\+\w+)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)",
            connection_url,
        )
        assert match is not None
        user, password, host, port, database = match.groups()

        # Create connection pool
        pool = await asyncpg.create_pool(
            host=host,
            port=int(port),
            database=database,
            user=user,
            password=password,
            min_size=1,
            max_size=2,
        )

        try:
            runner = MigrationRunner(pool)

            # Apply migrations
            await runner.apply_migrations()

            # Verify checksums were recorded
            async with pool.acquire() as conn:
                migrations = await conn.fetch(
                    """
                    SELECT version, name, checksum, execution_time_ms
                    FROM schema_migrations
                    ORDER BY version
                    """
                )

                # Should have at least bootstrap migration
                assert len(migrations) >= 1

                # Verify checksum format (SHA256 hex = 64 chars)
                for migration in migrations:
                    assert len(migration["checksum"]) == 64
                    assert migration["execution_time_ms"] >= 0

        finally:
            await pool.close()

    @pytest.mark.asyncio
    async def test_can_insert_data_after_migrations(self, postgres_container) -> None:
        """Test that we can insert data after running migrations."""
        connection_url = postgres_container.get_connection_url()

        # Parse URL
        import re

        match = re.match(
            r"postgresql(?:\+\w+)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)",
            connection_url,
        )
        assert match is not None
        user, password, host, port, database = match.groups()

        # Create connection pool
        pool = await asyncpg.create_pool(
            host=host,
            port=int(port),
            database=database,
            user=user,
            password=password,
            min_size=1,
            max_size=2,
        )

        try:
            runner = MigrationRunner(pool)

            # Apply migrations
            await runner.apply_migrations()

            # Insert test data into all tables
            async with pool.acquire() as conn:
                # Insert BMP peer
                await conn.execute(
                    """
                    INSERT INTO bmp_peers (peer_ip, is_active)
                    VALUES ('192.0.2.1', true)
                    """
                )

                # Insert peer event
                await conn.execute(
                    """
                    INSERT INTO peer_events (peer_ip, event_type, time)
                    VALUES ('192.0.2.1', 'peer_up', NOW())
                    """
                )

                # Insert route update
                await conn.execute(
                    """
                    INSERT INTO route_updates
                    (time, bmp_peer_ip, bgp_peer_ip, family, prefix)
                    VALUES
                    (NOW(), '192.0.2.1', '198.51.100.1', 'ipv4_unicast', '10.0.0.0/24')
                    """
                )

                # Verify data
                peer_count = await conn.fetchval("SELECT COUNT(*) FROM bmp_peers")
                event_count = await conn.fetchval("SELECT COUNT(*) FROM peer_events")
                route_count = await conn.fetchval("SELECT COUNT(*) FROM route_updates")

                assert peer_count == 1
                assert event_count == 1
                assert route_count == 1

        finally:
            await pool.close()
