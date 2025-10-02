"""Integration tests for BMP listener end-to-end flow.

Tests complete flow: TCP connection → BMP parsing → Database storage.
Uses testcontainers for real PostgreSQL/TimescaleDB database.
"""

import asyncio
from pathlib import Path

import pytest
from pybmpmon.database.batch_writer import BatchWriter
from pybmpmon.database.connection import DatabasePool
from pybmpmon.database.operations import (
    get_bmp_peer,
    get_route_count,
    get_route_count_by_family,
    get_route_count_by_peer,
)
from pybmpmon.database.schema import FAMILY_IPV4_UNICAST
from pybmpmon.listener import BMPListener
from pybmpmon.monitoring.stats import StatisticsCollector
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
        await asyncio.sleep(2)
        yield postgres


@pytest.fixture(scope="session")
async def db_pool(postgres_container):
    """Create database pool and run migrations."""
    import re

    connection_url = postgres_container.get_connection_url()
    match = re.match(r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", connection_url)
    if not match:
        raise ValueError(f"Invalid connection URL: {connection_url}")

    user, password, host, port, database = match.groups()

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
    await pool.close()


@pytest.fixture
async def clean_db(db_pool):
    """Clean database tables before each test."""
    async with db_pool.get_pool().acquire() as conn:
        await conn.execute("TRUNCATE TABLE route_updates")
        await conn.execute("TRUNCATE TABLE bmp_peers CASCADE")
        await conn.execute("TRUNCATE TABLE peer_events")
    yield


@pytest.fixture
async def batch_writer(db_pool):
    """Create batch writer for tests."""
    writer = BatchWriter(db_pool.get_pool(), batch_size=10, batch_timeout=0.5)
    await writer.start()
    yield writer
    await writer.stop()


@pytest.fixture
async def stats_collector():
    """Create statistics collector for tests."""
    collector = StatisticsCollector(log_interval=10.0)
    await collector.start()
    yield collector
    await collector.stop()


@pytest.fixture
async def listener(db_pool, batch_writer, stats_collector):
    """Create BMP listener for tests."""
    listener = BMPListener(
        host="127.0.0.1",
        port=0,  # Let OS assign port
        pool=db_pool.get_pool(),
        batch_writer=batch_writer,
        stats_collector=stats_collector,
    )
    await listener.start()
    yield listener
    await listener.stop()


def build_bmp_header(length: int, msg_type: int) -> bytes:
    """Build BMP common header."""
    data = bytearray()
    data.extend(b"\x03")  # Version
    data.extend(length.to_bytes(4, "big"))  # Length
    data.extend(bytes([msg_type]))  # Type
    return bytes(data)


def build_per_peer_header(peer_ip: str, peer_asn: int) -> bytes:
    """Build BMP Per-Peer Header."""
    data = bytearray()
    data.extend(b"\x00")  # Peer Type = Global
    data.extend(b"\x00")  # Peer Flags = IPv4
    data.extend(b"\x00" * 8)  # Peer Distinguisher

    # Peer Address (IPv4-mapped)
    octets = [int(x) for x in peer_ip.split(".")]
    data.extend(b"\x00" * 10 + b"\xff\xff" + bytes(octets))

    data.extend(peer_asn.to_bytes(4, "big"))  # Peer AS
    data.extend(bytes(octets))  # BGP ID (same as peer IP)
    data.extend(b"\x00\x00\x00\x01")  # Timestamp sec
    data.extend(b"\x00\x00\x00\x00")  # Timestamp usec

    return bytes(data)


def build_bgp_update(prefix: str, next_hop: str, as_path: list[int]) -> bytes:
    """Build minimal BGP UPDATE message."""
    data = bytearray()

    # BGP header
    data.extend(b"\xff" * 16)  # Marker
    data.extend(b"\x00\x00")  # Length (will update)
    data.extend(b"\x02")  # Type = UPDATE

    # No withdrawn routes
    data.extend(b"\x00\x00")

    # Path attributes
    path_attrs = bytearray()

    # ORIGIN
    path_attrs.extend(b"\x40\x01\x01\x00")

    # AS_PATH
    as_path_data = bytearray()
    as_path_data.extend(b"\x02")  # AS_SEQUENCE
    as_path_data.extend(bytes([len(as_path)]))
    for asn in as_path:
        as_path_data.extend(asn.to_bytes(2, "big"))

    path_attrs.extend(b"\x40\x02")
    path_attrs.extend(bytes([len(as_path_data)]))
    path_attrs.extend(as_path_data)

    # NEXT_HOP
    nh_octets = [int(x) for x in next_hop.split(".")]
    path_attrs.extend(b"\x40\x03\x04")
    path_attrs.extend(bytes(nh_octets))

    data.extend(len(path_attrs).to_bytes(2, "big"))
    data.extend(path_attrs)

    # NLRI (prefix)
    prefix_parts = prefix.split("/")
    prefix_len = int(prefix_parts[1])
    prefix_octets = [int(x) for x in prefix_parts[0].split(".")]
    prefix_bytes = (prefix_len + 7) // 8

    data.extend(bytes([prefix_len]))
    data.extend(bytes(prefix_octets[:prefix_bytes]))

    # Update BGP length
    data[16:18] = len(data).to_bytes(2, "big")

    return bytes(data)


def build_route_monitoring_message(
    peer_ip: str, peer_asn: int, prefix: str, next_hop: str, as_path: list[int]
) -> bytes:
    """Build complete BMP Route Monitoring message."""
    # Build BGP UPDATE
    bgp_update = build_bgp_update(prefix, next_hop, as_path)

    # Build BMP message
    data = bytearray()

    # Per-Peer Header
    per_peer = build_per_peer_header(peer_ip, peer_asn)
    data.extend(per_peer)

    # BGP UPDATE
    data.extend(bgp_update)

    # Build BMP header
    total_length = 6 + len(data)  # Header + body
    header = build_bmp_header(total_length, 0)  # Type 0 = Route Monitoring

    return header + bytes(data)


def build_peer_up_message(peer_ip: str, peer_asn: int) -> bytes:
    """Build BMP Peer Up message."""
    data = bytearray()

    # Per-Peer Header
    per_peer = build_per_peer_header(peer_ip, peer_asn)
    data.extend(per_peer)

    # Local Address (IPv4-mapped)
    data.extend(b"\x00" * 10 + b"\xff\xff" + b"\xc0\x00\x02\xfe")  # 192.0.2.254
    data.extend(b"\x00\xb3")  # Local port = 179
    data.extend(b"\xc3\x50")  # Remote port = 50000

    # Sent OPEN message (minimal)
    sent_open = b"\xff" * 16 + b"\x00\x1d\x01\x04\x00\x01\x00\xb4\xc0\x00\x02\xfe\x00"
    data.extend(sent_open)

    # Received OPEN message (minimal)
    recv_open = b"\xff" * 16 + b"\x00\x1d\x01\x04\x00\x01\x00\xb4\xc0\x00\x02\x01\x00"
    data.extend(recv_open)

    # Build BMP header
    total_length = 6 + len(data)
    header = build_bmp_header(total_length, 3)  # Type 3 = Peer Up

    return header + bytes(data)


def build_peer_down_message(peer_ip: str, peer_asn: int, reason: int) -> bytes:
    """Build BMP Peer Down message."""
    data = bytearray()

    # Per-Peer Header
    per_peer = build_per_peer_header(peer_ip, peer_asn)
    data.extend(per_peer)

    # Reason code
    data.extend(bytes([reason]))

    # Build BMP header
    total_length = 6 + len(data)
    header = build_bmp_header(total_length, 2)  # Type 2 = Peer Down

    return header + bytes(data)


class TestEndToEndFlow:
    """Test complete BMP to database flow."""

    @pytest.mark.asyncio
    async def test_bmp_to_database_complete_flow(
        self, listener, db_pool, batch_writer, clean_db
    ):
        """Test full flow: TCP → BMP Parse → Database."""
        # Get listener port
        if not listener.server or not listener.server.sockets:
            pytest.skip("Listener not started")

        port = listener.server.sockets[0].getsockname()[1]

        # Connect to listener
        reader, writer = await asyncio.open_connection("127.0.0.1", port)

        try:
            # Send Peer Up
            peer_up = build_peer_up_message("192.0.2.1", 65001)
            writer.write(peer_up)
            await writer.drain()

            # Wait for processing
            await asyncio.sleep(0.5)

            # Verify peer in database
            peer = await get_bmp_peer(db_pool.get_pool(), "192.0.2.1")
            assert peer is not None
            assert peer.is_active is True

            # Send Route Monitoring message
            route_msg = build_route_monitoring_message(
                peer_ip="192.0.2.1",
                peer_asn=65001,
                prefix="10.0.0.0/8",
                next_hop="192.0.2.254",
                as_path=[65001, 65002],
            )
            writer.write(route_msg)
            await writer.drain()

            # Force batch flush
            await batch_writer.flush()
            await asyncio.sleep(0.5)

            # Verify route in database
            count = await get_route_count(db_pool.get_pool())
            assert count == 1

            count_by_peer = await get_route_count_by_peer(
                db_pool.get_pool(), "192.0.2.1"
            )
            assert count_by_peer == 1

            # Send Peer Down
            peer_down = build_peer_down_message("192.0.2.1", 65001, 1)
            writer.write(peer_down)
            await writer.drain()

            await asyncio.sleep(0.5)

            # Verify peer marked inactive
            peer = await get_bmp_peer(db_pool.get_pool(), "192.0.2.1")
            assert peer is not None
            assert peer.is_active is False

        finally:
            writer.close()
            await writer.wait_closed()

    @pytest.mark.asyncio
    async def test_multiple_route_monitoring_messages(
        self, listener, db_pool, batch_writer, clean_db
    ):
        """Test processing multiple Route Monitoring messages."""
        if not listener.server or not listener.server.sockets:
            pytest.skip("Listener not started")

        port = listener.server.sockets[0].getsockname()[1]

        reader, writer = await asyncio.open_connection("127.0.0.1", port)

        try:
            # Send Peer Up
            peer_up = build_peer_up_message("192.0.2.10", 65100)
            writer.write(peer_up)
            await writer.drain()
            await asyncio.sleep(0.3)

            # Send 50 route messages
            for i in range(50):
                route_msg = build_route_monitoring_message(
                    peer_ip="192.0.2.10",
                    peer_asn=65100,
                    prefix=f"10.{i}.0.0/16",
                    next_hop="192.0.2.254",
                    as_path=[65100, 65200],
                )
                writer.write(route_msg)

            await writer.drain()

            # Force flush and wait
            await batch_writer.flush()
            await asyncio.sleep(1.0)

            # Verify all 50 routes in database
            count = await get_route_count_by_peer(db_pool.get_pool(), "192.0.2.10")
            assert count == 50

            count_ipv4 = await get_route_count_by_family(
                db_pool.get_pool(), FAMILY_IPV4_UNICAST
            )
            assert count_ipv4 == 50

        finally:
            writer.close()
            await writer.wait_closed()

    @pytest.mark.asyncio
    async def test_peer_lifecycle(self, listener, db_pool, batch_writer, clean_db):
        """Test Peer Up → Routes → Peer Down flow."""
        if not listener.server or not listener.server.sockets:
            pytest.skip("Listener not started")

        port = listener.server.sockets[0].getsockname()[1]

        reader, writer = await asyncio.open_connection("127.0.0.1", port)

        try:
            # Phase 1: Peer Up
            peer_up = build_peer_up_message("192.0.2.20", 65200)
            writer.write(peer_up)
            await writer.drain()
            await asyncio.sleep(0.3)

            # Verify peer is active
            peer = await get_bmp_peer(db_pool.get_pool(), "192.0.2.20")
            assert peer is not None
            assert peer.is_active is True

            # Phase 2: Send routes
            for i in range(10):
                route_msg = build_route_monitoring_message(
                    peer_ip="192.0.2.20",
                    peer_asn=65200,
                    prefix=f"172.16.{i}.0/24",
                    next_hop="192.0.2.254",
                    as_path=[65200],
                )
                writer.write(route_msg)

            await writer.drain()
            await batch_writer.flush()
            await asyncio.sleep(0.5)

            # Verify routes
            count = await get_route_count_by_peer(db_pool.get_pool(), "192.0.2.20")
            assert count == 10

            # Phase 3: Peer Down
            peer_down = build_peer_down_message("192.0.2.20", 65200, 2)
            writer.write(peer_down)
            await writer.drain()
            await asyncio.sleep(0.3)

            # Verify peer is inactive
            peer = await get_bmp_peer(db_pool.get_pool(), "192.0.2.20")
            assert peer is not None
            assert peer.is_active is False

            # Routes should still be in database (historical data)
            count = await get_route_count_by_peer(db_pool.get_pool(), "192.0.2.20")
            assert count == 10

        finally:
            writer.close()
            await writer.wait_closed()
