"""Integration tests for database operations using testcontainers."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pybmpmon.database.batch_writer import BatchWriter
from pybmpmon.database.connection import DatabasePool
from pybmpmon.database.operations import (
    get_all_active_peers,
    get_bmp_peer,
    get_route_count,
    get_route_count_by_family,
    get_route_count_by_peer,
    insert_peer_event,
    insert_route_update,
    mark_peer_inactive,
    upsert_bmp_peer,
)
from pybmpmon.database.schema import (
    EVENT_PEER_DOWN,
    EVENT_PEER_UP,
    FAMILY_EVPN,
    FAMILY_IPV4_UNICAST,
    FAMILY_IPV6_UNICAST,
)
from pybmpmon.models.bmp_peer import BMPPeer, PeerEvent
from pybmpmon.models.route import RouteUpdate
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def postgres_container():
    """Start PostgreSQL/TimescaleDB container for tests."""
    with PostgresContainer("timescale/timescaledb:latest-pg16") as postgres:
        # Wait for container to be ready
        await asyncio.sleep(2)
        yield postgres


@pytest.fixture(scope="session")
async def db_pool(postgres_container):
    """Create database pool and run migrations."""
    # Extract connection parameters
    connection_url = postgres_container.get_connection_url()

    # Parse URL (format: postgresql://user:pass@host:port/db)
    import re

    match = re.match(r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", connection_url)
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
        await conn.execute("TRUNCATE TABLE bmp_peers CASCADE")
        await conn.execute("TRUNCATE TABLE peer_events")
    yield


class TestBMPPeerOperations:
    """Test BMP peer CRUD operations."""

    async def test_upsert_new_peer(self, db_pool, clean_db):
        """Test inserting a new BMP peer."""
        peer = BMPPeer(
            peer_ip="192.0.2.1",
            router_id="192.0.2.1",
            first_seen=datetime.utcnow(),
            last_seen=datetime.utcnow(),
            is_active=True,
        )

        await upsert_bmp_peer(db_pool.get_pool(), peer)

        # Verify insertion
        retrieved = await get_bmp_peer(db_pool.get_pool(), "192.0.2.1")
        assert retrieved is not None
        assert str(retrieved.peer_ip) == "192.0.2.1"
        assert str(retrieved.router_id) == "192.0.2.1"
        assert retrieved.is_active is True

    async def test_upsert_existing_peer(self, db_pool, clean_db):
        """Test updating an existing BMP peer."""
        peer = BMPPeer(
            peer_ip="192.0.2.1",
            router_id="192.0.2.1",
            is_active=True,
        )

        # Insert
        await upsert_bmp_peer(db_pool.get_pool(), peer)

        # Update
        peer.is_active = False
        await upsert_bmp_peer(db_pool.get_pool(), peer)

        # Verify update
        retrieved = await get_bmp_peer(db_pool.get_pool(), "192.0.2.1")
        assert retrieved is not None
        assert retrieved.is_active is False

    async def test_get_nonexistent_peer(self, db_pool, clean_db):
        """Test retrieving a peer that doesn't exist."""
        retrieved = await get_bmp_peer(db_pool.get_pool(), "192.0.2.99")
        assert retrieved is None

    async def test_get_all_active_peers(self, db_pool, clean_db):
        """Test retrieving all active peers."""
        # Insert active peers
        peer1 = BMPPeer(peer_ip="192.0.2.1", is_active=True)
        peer2 = BMPPeer(peer_ip="192.0.2.2", is_active=True)
        peer3 = BMPPeer(peer_ip="192.0.2.3", is_active=False)

        await upsert_bmp_peer(db_pool.get_pool(), peer1)
        await upsert_bmp_peer(db_pool.get_pool(), peer2)
        await upsert_bmp_peer(db_pool.get_pool(), peer3)

        # Get active peers
        active = await get_all_active_peers(db_pool.get_pool())

        assert len(active) == 2
        active_ips = [str(p.peer_ip) for p in active]
        assert "192.0.2.1" in active_ips
        assert "192.0.2.2" in active_ips
        assert "192.0.2.3" not in active_ips

    async def test_mark_peer_inactive(self, db_pool, clean_db):
        """Test marking a peer as inactive."""
        peer = BMPPeer(peer_ip="192.0.2.1", is_active=True)
        await upsert_bmp_peer(db_pool.get_pool(), peer)

        # Mark inactive
        await mark_peer_inactive(db_pool.get_pool(), "192.0.2.1")

        # Verify
        retrieved = await get_bmp_peer(db_pool.get_pool(), "192.0.2.1")
        assert retrieved is not None
        assert retrieved.is_active is False


class TestPeerEventOperations:
    """Test peer event operations."""

    async def test_insert_peer_up_event(self, db_pool, clean_db):
        """Test inserting a peer up event."""
        event = PeerEvent(
            time=datetime.utcnow(),
            peer_ip="192.0.2.1",
            event_type=EVENT_PEER_UP,
        )

        await insert_peer_event(db_pool.get_pool(), event)

        # Verify insertion
        async with db_pool.get_pool().acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM peer_events")
            assert count == 1

    async def test_insert_peer_down_event(self, db_pool, clean_db):
        """Test inserting a peer down event."""
        event = PeerEvent(
            time=datetime.utcnow(),
            peer_ip="192.0.2.1",
            event_type=EVENT_PEER_DOWN,
            reason_code=1,
        )

        await insert_peer_event(db_pool.get_pool(), event)

        # Verify insertion with reason code
        async with db_pool.get_pool().acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM peer_events LIMIT 1")
            assert row["event_type"] == EVENT_PEER_DOWN
            assert row["reason_code"] == 1


class TestRouteUpdateOperations:
    """Test route update operations."""

    async def test_insert_ipv4_route(self, db_pool, clean_db):
        """Test inserting an IPv4 unicast route."""
        route = RouteUpdate(
            time=datetime.utcnow(),
            bmp_peer_ip="192.0.2.1",
            bmp_peer_asn=65000,
            bgp_peer_ip="192.0.2.100",
            bgp_peer_asn=65001,
            family=FAMILY_IPV4_UNICAST,
            prefix="10.0.0.0/8",
            next_hop="192.0.2.254",
            as_path=[65000, 65001, 65002],
            communities=["65000:100", "65000:200"],
            med=100,
            local_pref=200,
            is_withdrawn=False,
        )

        await insert_route_update(db_pool.get_pool(), route)

        # Verify insertion
        count = await get_route_count(db_pool.get_pool())
        assert count == 1

    async def test_insert_ipv6_route(self, db_pool, clean_db):
        """Test inserting an IPv6 unicast route."""
        route = RouteUpdate(
            time=datetime.utcnow(),
            bmp_peer_ip="2001:db8::1",
            bgp_peer_ip="2001:db8::100",
            family=FAMILY_IPV6_UNICAST,
            prefix="2001:db8::/32",
            next_hop="2001:db8::254",
            as_path=[65000],
        )

        await insert_route_update(db_pool.get_pool(), route)

        count = await get_route_count(db_pool.get_pool())
        assert count == 1

    async def test_insert_evpn_route(self, db_pool, clean_db):
        """Test inserting an EVPN route."""
        route = RouteUpdate(
            time=datetime.utcnow(),
            bmp_peer_ip="192.0.2.1",
            bgp_peer_ip="192.0.2.100",
            family=FAMILY_EVPN,
            evpn_route_type=2,  # MAC/IP Advertisement
            evpn_rd="65000:100",
            evpn_esi="00:11:22:33:44:55:66:77:88:99",
            mac_address="00:11:22:33:44:55",
            next_hop="192.0.2.254",
        )

        await insert_route_update(db_pool.get_pool(), route)

        count = await get_route_count(db_pool.get_pool())
        assert count == 1

    async def test_get_route_count_by_peer(self, db_pool, clean_db):
        """Test counting routes by BMP peer."""
        # Insert routes from two different peers
        route1 = RouteUpdate(
            bmp_peer_ip="192.0.2.1",
            bgp_peer_ip="192.0.2.100",
            family=FAMILY_IPV4_UNICAST,
            prefix="10.0.0.0/8",
        )
        route2 = RouteUpdate(
            bmp_peer_ip="192.0.2.1",
            bgp_peer_ip="192.0.2.100",
            family=FAMILY_IPV4_UNICAST,
            prefix="172.16.0.0/12",
        )
        route3 = RouteUpdate(
            bmp_peer_ip="192.0.2.2",
            bgp_peer_ip="192.0.2.101",
            family=FAMILY_IPV4_UNICAST,
            prefix="192.168.0.0/16",
        )

        await insert_route_update(db_pool.get_pool(), route1)
        await insert_route_update(db_pool.get_pool(), route2)
        await insert_route_update(db_pool.get_pool(), route3)

        # Count routes by peer
        count_peer1 = await get_route_count_by_peer(db_pool.get_pool(), "192.0.2.1")
        count_peer2 = await get_route_count_by_peer(db_pool.get_pool(), "192.0.2.2")

        assert count_peer1 == 2
        assert count_peer2 == 1

    async def test_get_route_count_by_family(self, db_pool, clean_db):
        """Test counting routes by address family."""
        # Insert routes of different families
        route1 = RouteUpdate(
            bmp_peer_ip="192.0.2.1",
            bgp_peer_ip="192.0.2.100",
            family=FAMILY_IPV4_UNICAST,
            prefix="10.0.0.0/8",
        )
        route2 = RouteUpdate(
            bmp_peer_ip="192.0.2.1",
            bgp_peer_ip="192.0.2.100",
            family=FAMILY_IPV4_UNICAST,
            prefix="172.16.0.0/12",
        )
        route3 = RouteUpdate(
            bmp_peer_ip="192.0.2.1",
            bgp_peer_ip="192.0.2.100",
            family=FAMILY_IPV6_UNICAST,
            prefix="2001:db8::/32",
        )

        await insert_route_update(db_pool.get_pool(), route1)
        await insert_route_update(db_pool.get_pool(), route2)
        await insert_route_update(db_pool.get_pool(), route3)

        # Count by family
        count_ipv4 = await get_route_count_by_family(
            db_pool.get_pool(), FAMILY_IPV4_UNICAST
        )
        count_ipv6 = await get_route_count_by_family(
            db_pool.get_pool(), FAMILY_IPV6_UNICAST
        )

        assert count_ipv4 == 2
        assert count_ipv6 == 1

    async def test_insert_withdrawn_route(self, db_pool, clean_db):
        """Test inserting a withdrawn route."""
        route = RouteUpdate(
            bmp_peer_ip="192.0.2.1",
            bgp_peer_ip="192.0.2.100",
            family=FAMILY_IPV4_UNICAST,
            prefix="10.0.0.0/8",
            is_withdrawn=True,
        )

        await insert_route_update(db_pool.get_pool(), route)

        # Verify withdrawal flag
        async with db_pool.get_pool().acquire() as conn:
            is_withdrawn = await conn.fetchval(
                "SELECT is_withdrawn FROM route_updates LIMIT 1"
            )
            assert is_withdrawn is True


class TestDatabasePool:
    """Test database pool functionality."""

    async def test_pool_connection(self, db_pool):
        """Test that pool is properly connected."""
        pool = db_pool.get_pool()
        assert pool is not None

        # Test simple query
        async with pool.acquire() as conn:
            version = await conn.fetchval("SELECT version()")
            assert "PostgreSQL" in version

    async def test_pool_execute(self, db_pool, clean_db):
        """Test pool execute method."""
        result = await db_pool.execute("SELECT 1")
        assert result == "SELECT 1"

    async def test_pool_fetch(self, db_pool, clean_db):
        """Test pool fetch method."""
        rows = await db_pool.fetch("SELECT 1 as num")
        assert len(rows) == 1
        assert rows[0]["num"] == 1

    async def test_pool_fetchval(self, db_pool, clean_db):
        """Test pool fetchval method."""
        value = await db_pool.fetchval("SELECT 42")
        assert value == 42


class TestBatchWriterEVPN:
    """Test BatchWriter with EVPN routes containing MAC addresses."""

    async def test_batch_writer_evpn_mac_addresses(self, db_pool, clean_db):
        """
        Test that BatchWriter correctly handles EVPN routes with MAC addresses.

        This test ensures the MACADDR codec works correctly with COPY operations,
        preventing regressions like "no binary format encoder for type macaddr".
        """
        pool = db_pool.get_pool()
        batch_writer = BatchWriter(pool, batch_size=10, batch_timeout=0.5)
        await batch_writer.start()

        try:
            # Add 25 EVPN routes with different MAC addresses
            for i in range(25):
                route = RouteUpdate(
                    time=datetime.now(UTC),
                    bmp_peer_ip="192.0.2.1",
                    bmp_peer_asn=65001,
                    bgp_peer_ip="192.0.2.2",
                    bgp_peer_asn=65002,
                    family=FAMILY_EVPN,
                    prefix=f"10.0.{i}.0/24",
                    next_hop="192.0.2.3",
                    is_withdrawn=False,
                    evpn_route_type=2,  # MAC/IP Advertisement
                    evpn_rd=f"65001:{i}",
                    evpn_esi=f"00:11:22:33:44:55:66:77:88:{i:02x}",
                    mac_address=f"aa:bb:cc:dd:ee:{i:02x}",
                )
                await batch_writer.add_route(route)

            # Force flush
            await batch_writer.flush()

            # Verify routes were inserted
            count = await get_route_count_by_family(pool, FAMILY_EVPN)
            assert count == 25

            # Verify MAC addresses are stored correctly
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT evpn_rd, mac_address
                    FROM route_updates
                    WHERE family = $1
                    ORDER BY evpn_rd
                    LIMIT 5
                    """,
                    FAMILY_EVPN,
                )

                # Check first 5 MAC addresses
                expected_macs = [
                    ("65001:0", "aa:bb:cc:dd:ee:00"),
                    ("65001:1", "aa:bb:cc:dd:ee:01"),
                    ("65001:10", "aa:bb:cc:dd:ee:0a"),
                    ("65001:11", "aa:bb:cc:dd:ee:0b"),
                    ("65001:12", "aa:bb:cc:dd:ee:0c"),
                ]

                for row, (expected_rd, expected_mac) in zip(
                    rows, expected_macs, strict=False
                ):
                    assert row["evpn_rd"] == expected_rd
                    assert row["mac_address"] == expected_mac

        finally:
            await batch_writer.stop()

    async def test_batch_writer_mixed_routes_with_mac(self, db_pool, clean_db):
        """Test BatchWriter with mixed route types including EVPN with MAC addresses."""
        pool = db_pool.get_pool()
        batch_writer = BatchWriter(pool, batch_size=20, batch_timeout=0.5)
        await batch_writer.start()

        try:
            # Add IPv4 routes (no MAC)
            for i in range(10):
                route = RouteUpdate(
                    time=datetime.now(UTC),
                    bmp_peer_ip="192.0.2.1",
                    bmp_peer_asn=65001,
                    bgp_peer_ip="192.0.2.2",
                    bgp_peer_asn=65002,
                    family=FAMILY_IPV4_UNICAST,
                    prefix=f"10.{i}.0.0/16",
                    next_hop="192.0.2.3",
                    is_withdrawn=False,
                )
                await batch_writer.add_route(route)

            # Add EVPN routes (with MAC)
            for i in range(10):
                route = RouteUpdate(
                    time=datetime.now(UTC),
                    bmp_peer_ip="192.0.2.1",
                    bmp_peer_asn=65001,
                    bgp_peer_ip="192.0.2.2",
                    bgp_peer_asn=65002,
                    family=FAMILY_EVPN,
                    prefix=f"172.16.{i}.0/24",
                    next_hop="192.0.2.3",
                    is_withdrawn=False,
                    evpn_route_type=2,
                    evpn_rd=f"65001:100{i}",
                    mac_address=f"bb:cc:dd:ee:ff:{i:02x}",
                )
                await batch_writer.add_route(route)

            await batch_writer.flush()

            # Verify counts
            ipv4_count = await get_route_count_by_family(pool, FAMILY_IPV4_UNICAST)
            evpn_count = await get_route_count_by_family(pool, FAMILY_EVPN)

            assert ipv4_count == 10
            assert evpn_count == 10

            # Verify EVPN routes have MAC addresses, IPv4 routes don't
            async with pool.acquire() as conn:
                evpn_macs = await conn.fetch(
                    "SELECT mac_address FROM route_updates WHERE family = $1",
                    FAMILY_EVPN,
                )
                ipv4_macs = await conn.fetch(
                    "SELECT mac_address FROM route_updates WHERE family = $1",
                    FAMILY_IPV4_UNICAST,
                )

                # All EVPN routes should have MAC addresses
                assert all(row["mac_address"] is not None for row in evpn_macs)
                # All IPv4 routes should have NULL MAC addresses
                assert all(row["mac_address"] is None for row in ipv4_macs)

        finally:
            await batch_writer.stop()
