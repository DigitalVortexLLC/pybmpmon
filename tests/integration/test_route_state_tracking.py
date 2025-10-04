"""Tests for route state tracking and relearn events."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pybmpmon.database.batch_writer import BatchWriter
from pybmpmon.database.connection import DatabasePool
from pybmpmon.models.route import RouteUpdate
from testcontainers.postgres import PostgresContainer


@pytest.fixture
def postgres_container():
    """Start PostgreSQL/TimescaleDB container for tests."""
    with PostgresContainer("timescale/timescaledb:latest-pg16") as postgres:
        yield postgres


@pytest.fixture
async def db_pool(postgres_container):
    """Create database pool and run migrations."""
    # Extract connection parameters
    connection_url = postgres_container.get_connection_url()

    # Parse URL (format: postgresql://user:pass@host:port/db or postgresql+driver://...)
    import re

    # Handle both postgresql:// and postgresql+psycopg2:// URLs
    match = re.match(
        r"postgresql(?:\+\w+)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", connection_url
    )
    if not match:
        raise ValueError(f"Invalid connection URL: {connection_url}")

    user, password, host, port, database = match.groups()

    # Create connection pool
    pool = DatabasePool()
    await pool.connect(
        host=host,
        port=int(port),
        database=database,
        user=user,
        password=password,
    )

    # Run migrations
    migrations_dir = (
        Path(__file__).parent.parent.parent
        / "src"
        / "pybmpmon"
        / "database"
        / "migrations"
    )

    migration_files = sorted(migrations_dir.glob("*.sql"))

    async with pool.get_pool().acquire() as conn:
        for filepath in migration_files:
            sql = filepath.read_text()
            await conn.execute(sql)

    yield pool

    # Cleanup
    await pool.close()


@pytest.fixture
async def clean_db(db_pool):
    """Clean database tables before each test."""
    async with db_pool.get_pool().acquire() as conn:
        await conn.execute("TRUNCATE TABLE route_updates")
        await conn.execute("TRUNCATE TABLE route_state")
        await conn.execute("TRUNCATE TABLE bmp_peers CASCADE")
        await conn.execute("TRUNCATE TABLE peer_events")
    yield


class TestRouteStateTracking:
    """Test route state tracking functionality."""

    async def test_route_first_seen_tracking(self, db_pool, clean_db) -> None:
        """Test that first_seen timestamp is tracked correctly."""
        batch_writer = BatchWriter(db_pool.get_pool(), batch_size=10, batch_timeout=0.1)
        await batch_writer.start()

        try:
            # Create a route update
            route = RouteUpdate(
                time=datetime.now(UTC),
                bmp_peer_ip="192.0.2.1",
                bgp_peer_ip="192.0.2.2",
                family="ipv4_unicast",
                prefix="10.1.0.0/16",
                next_hop="192.0.2.3",
                as_path=[65001, 65002],
                is_withdrawn=False,
            )

            # Add route and flush
            await batch_writer.add_route(route)
            await batch_writer.flush()

            # Wait a moment for state update
            await asyncio.sleep(0.1)

            # Check route_state table
            async with db_pool.get_pool().acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT first_seen, last_seen, is_withdrawn,
                           learn_count, withdraw_count
                    FROM route_state
                    WHERE bmp_peer_ip = $1 AND bgp_peer_ip = $2 AND prefix = $3
                    """,
                    "192.0.2.1",
                    "192.0.2.2",
                    "10.1.0.0/16",
                )

            assert row is not None
            assert row["is_withdrawn"] is False
            assert row["learn_count"] == 1
            assert row["withdraw_count"] == 0
            assert row["first_seen"] is not None
            assert row["last_seen"] is not None

            # Store first_seen for later comparison
            first_seen = row["first_seen"]

            # Update same route again (should not change first_seen)
            await asyncio.sleep(0.1)
            route2 = RouteUpdate(
                time=datetime.now(UTC),
                bmp_peer_ip="192.0.2.1",
                bgp_peer_ip="192.0.2.2",
                family="ipv4_unicast",
                prefix="10.1.0.0/16",
                next_hop="192.0.2.4",  # Different next hop
                as_path=[65001, 65002],
                is_withdrawn=False,
            )
            await batch_writer.add_route(route2)
            await batch_writer.flush()
            await asyncio.sleep(0.1)

            # Check that first_seen hasn't changed
            async with db_pool.get_pool().acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT first_seen, last_seen, learn_count, next_hop
                    FROM route_state
                    WHERE bmp_peer_ip = $1 AND bgp_peer_ip = $2 AND prefix = $3
                    """,
                    "192.0.2.1",
                    "192.0.2.2",
                    "10.1.0.0/16",
                )

            assert row["first_seen"] == first_seen
            assert row["last_seen"] > first_seen
            assert row["learn_count"] == 1  # Still 1, not withdrawn then re-learned
            assert str(row["next_hop"]) == "192.0.2.4"  # Updated next hop

        finally:
            await batch_writer.stop()

    async def test_route_relearn_tracking(self, db_pool, clean_db) -> None:
        """Test that route relearn events are tracked correctly."""
        batch_writer = BatchWriter(db_pool.get_pool(), batch_size=10, batch_timeout=0.1)
        await batch_writer.start()

        try:
            base_time = datetime.now(UTC)

            # 1. Initial route advertisement
            route1 = RouteUpdate(
                time=base_time,
                bmp_peer_ip="192.0.2.1",
                bgp_peer_ip="192.0.2.2",
                family="ipv4_unicast",
                prefix="10.2.0.0/16",
                next_hop="192.0.2.3",
                as_path=[65001],
                is_withdrawn=False,
            )
            await batch_writer.add_route(route1)
            await batch_writer.flush()
            await asyncio.sleep(0.1)

            # Check initial state
            async with db_pool.get_pool().acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT is_withdrawn, learn_count, withdraw_count, last_state_change
                    FROM route_state
                    WHERE bmp_peer_ip = $1 AND bgp_peer_ip = $2 AND prefix = $3
                    """,
                    "192.0.2.1",
                    "192.0.2.2",
                    "10.2.0.0/16",
                )

            assert row["is_withdrawn"] is False
            assert row["learn_count"] == 1
            assert row["withdraw_count"] == 0
            first_state_change = row["last_state_change"]

            # 2. Withdraw route
            await asyncio.sleep(0.1)
            route2 = RouteUpdate(
                time=base_time + timedelta(seconds=1),
                bmp_peer_ip="192.0.2.1",
                bgp_peer_ip="192.0.2.2",
                family="ipv4_unicast",
                prefix="10.2.0.0/16",
                is_withdrawn=True,
            )
            await batch_writer.add_route(route2)
            await batch_writer.flush()
            await asyncio.sleep(0.1)

            # Check withdrawn state
            async with db_pool.get_pool().acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT is_withdrawn, learn_count, withdraw_count, last_state_change
                    FROM route_state
                    WHERE bmp_peer_ip = $1 AND bgp_peer_ip = $2 AND prefix = $3
                    """,
                    "192.0.2.1",
                    "192.0.2.2",
                    "10.2.0.0/16",
                )

            assert row["is_withdrawn"] is True
            assert row["learn_count"] == 1
            assert row["withdraw_count"] == 1
            assert row["last_state_change"] > first_state_change

            second_state_change = row["last_state_change"]

            # 3. Re-advertise route (relearn)
            await asyncio.sleep(0.1)
            route3 = RouteUpdate(
                time=base_time + timedelta(seconds=2),
                bmp_peer_ip="192.0.2.1",
                bgp_peer_ip="192.0.2.2",
                family="ipv4_unicast",
                prefix="10.2.0.0/16",
                next_hop="192.0.2.5",
                as_path=[65001, 65003],
                is_withdrawn=False,
            )
            await batch_writer.add_route(route3)
            await batch_writer.flush()
            await asyncio.sleep(0.1)

            # Check relearned state
            async with db_pool.get_pool().acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT is_withdrawn, learn_count, withdraw_count,
                           last_state_change, next_hop
                    FROM route_state
                    WHERE bmp_peer_ip = $1 AND bgp_peer_ip = $2 AND prefix = $3
                    """,
                    "192.0.2.1",
                    "192.0.2.2",
                    "10.2.0.0/16",
                )

            assert row["is_withdrawn"] is False
            assert row["learn_count"] == 2  # Incremented on relearn
            assert row["withdraw_count"] == 1
            assert row["last_state_change"] > second_state_change
            assert str(row["next_hop"]) == "192.0.2.5"

            # 4. Withdraw again
            await asyncio.sleep(0.1)
            route4 = RouteUpdate(
                time=base_time + timedelta(seconds=3),
                bmp_peer_ip="192.0.2.1",
                bgp_peer_ip="192.0.2.2",
                family="ipv4_unicast",
                prefix="10.2.0.0/16",
                is_withdrawn=True,
            )
            await batch_writer.add_route(route4)
            await batch_writer.flush()
            await asyncio.sleep(0.1)

            # 5. Re-advertise again
            await asyncio.sleep(0.1)
            route5 = RouteUpdate(
                time=base_time + timedelta(seconds=4),
                bmp_peer_ip="192.0.2.1",
                bgp_peer_ip="192.0.2.2",
                family="ipv4_unicast",
                prefix="10.2.0.0/16",
                next_hop="192.0.2.6",
                as_path=[65001],
                is_withdrawn=False,
            )
            await batch_writer.add_route(route5)
            await batch_writer.flush()
            await asyncio.sleep(0.1)

            # Check final state - should show multiple relearns
            async with db_pool.get_pool().acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT is_withdrawn, learn_count, withdraw_count
                    FROM route_state
                    WHERE bmp_peer_ip = $1 AND bgp_peer_ip = $2 AND prefix = $3
                    """,
                    "192.0.2.1",
                    "192.0.2.2",
                    "10.2.0.0/16",
                )

            assert row["is_withdrawn"] is False
            assert row["learn_count"] == 3  # Learned, relearned, relearned again
            assert row["withdraw_count"] == 2  # Withdrawn twice

        finally:
            await batch_writer.stop()

    async def test_route_churn_detection(self, db_pool, clean_db) -> None:
        """Test detection of high-churn (flapping) routes."""
        batch_writer = BatchWriter(db_pool.get_pool(), batch_size=10, batch_timeout=0.1)
        await batch_writer.start()

        try:
            base_time = datetime.now(UTC)

            # Simulate a flapping route (advertise, withdraw, repeat)
            for i in range(10):
                # Advertise
                route_adv = RouteUpdate(
                    time=base_time + timedelta(seconds=i * 2),
                    bmp_peer_ip="192.0.2.1",
                    bgp_peer_ip="192.0.2.2",
                    family="ipv4_unicast",
                    prefix="10.3.0.0/16",
                    next_hop="192.0.2.3",
                    as_path=[65001],
                    is_withdrawn=False,
                )
                await batch_writer.add_route(route_adv)
                await batch_writer.flush()
                await asyncio.sleep(0.05)

                # Withdraw
                route_wd = RouteUpdate(
                    time=base_time + timedelta(seconds=i * 2 + 1),
                    bmp_peer_ip="192.0.2.1",
                    bgp_peer_ip="192.0.2.2",
                    family="ipv4_unicast",
                    prefix="10.3.0.0/16",
                    is_withdrawn=True,
                )
                await batch_writer.add_route(route_wd)
                await batch_writer.flush()
                await asyncio.sleep(0.05)

            # Check that churn is tracked
            async with db_pool.get_pool().acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT learn_count, withdraw_count,
                           (learn_count + withdraw_count) as total_changes
                    FROM route_state
                    WHERE bmp_peer_ip = $1 AND bgp_peer_ip = $2 AND prefix = $3
                    """,
                    "192.0.2.1",
                    "192.0.2.2",
                    "10.3.0.0/16",
                )

            assert row is not None
            assert row["learn_count"] == 10
            assert row["withdraw_count"] == 10
            assert row["total_changes"] == 20

        finally:
            await batch_writer.stop()
