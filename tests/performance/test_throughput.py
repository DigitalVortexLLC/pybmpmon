"""Performance tests for route processing throughput."""

import asyncio
import time
from datetime import UTC, datetime

import pytest
from pybmpmon.database.batch_writer import BatchWriter
from pybmpmon.models.route import RouteUpdate


@pytest.mark.asyncio
async def test_batch_writer_throughput():
    """
    Test BatchWriter can process 15k+ routes/sec.

    Success criteria: Process 50,000 routes with throughput >= 15,000 routes/sec
    """

    # Create mock pool that doesn't actually write to database
    class MockConnection:
        async def executemany(self, query, records):
            # Simulate some processing time
            await asyncio.sleep(0.001)  # 1ms per batch

    class MockPoolContext:
        def __init__(self, conn):
            self.conn = conn

        async def __aenter__(self):
            return self.conn

        async def __aexit__(self, *args):
            pass

    class MockPool:
        def __init__(self):
            self.conn = MockConnection()

        def acquire(self):
            return MockPoolContext(self.conn)

    pool = MockPool()  # type: ignore[assignment]
    batch_writer = BatchWriter(pool, batch_size=1000, batch_timeout=0.5)
    await batch_writer.start()

    try:
        # Generate 50k routes
        num_routes = 50_000
        start_time = time.time()

        for i in range(num_routes):
            route = RouteUpdate(
                time=datetime.now(UTC),
                bmp_peer_ip=f"192.0.2.{i % 256}",
                bmp_peer_asn=65000,
                bgp_peer_ip=f"198.51.100.{i % 256}",
                bgp_peer_asn=65001,
                family="ipv4_unicast",
                prefix=f"10.{(i >> 16) & 0xFF}.{(i >> 8) & 0xFF}.{i & 0xFF}/24",
                next_hop=f"203.0.113.{i % 256}",
                as_path=[65000, 65001, 65002],
                communities=["65000:100"],
                med=100,
                local_pref=200,
                is_withdrawn=False,
            )
            await batch_writer.add_route(route)

        # Wait for final flush
        await batch_writer.flush()

        elapsed = time.time() - start_time
        throughput = num_routes / elapsed

        print(f"\nProcessed {num_routes:,} routes in {elapsed:.2f}s")
        print(f"Throughput: {throughput:,.0f} routes/sec")
        print(f"Batches written: {batch_writer.total_batches_written}")

        # Verify throughput meets requirement
        assert (
            throughput >= 15_000
        ), f"Throughput {throughput:.0f} routes/sec is below target 15,000"

        # Verify all routes were written
        assert batch_writer.total_routes_written == num_routes

    finally:
        await batch_writer.stop()


@pytest.mark.asyncio
async def test_batch_writer_timeout_flush():
    """Test that batch writer flushes on timeout even if batch not full."""

    class MockConnection:
        def __init__(self, pool):
            self.pool = pool

        async def executemany(self, query, records):
            self.pool.flush_count += 1

    class MockPoolContext:
        def __init__(self, conn):
            self.conn = conn

        async def __aenter__(self):
            return self.conn

        async def __aexit__(self, *args):
            pass

    class MockPool:
        def __init__(self):
            self.flush_count = 0
            self.conn = MockConnection(self)

        def acquire(self):
            return MockPoolContext(self.conn)

    pool = MockPool()  # type: ignore[assignment]
    batch_writer = BatchWriter(pool, batch_size=1000, batch_timeout=0.2)
    await batch_writer.start()

    try:
        # Add only 100 routes (less than batch size)
        for i in range(100):
            route = RouteUpdate(
                time=datetime.now(UTC),
                bmp_peer_ip="192.0.2.1",
                bgp_peer_ip="198.51.100.1",
                family="ipv4_unicast",
                prefix=f"10.0.{i}.0/24",
            )
            await batch_writer.add_route(route)

        # Wait for timeout to trigger flush
        await asyncio.sleep(0.3)

        # Verify flush happened
        assert pool.flush_count >= 1
        assert batch_writer.total_routes_written == 100

    finally:
        await batch_writer.stop()


@pytest.mark.asyncio
async def test_batch_writer_size_flush():
    """Test that batch writer flushes when batch size is reached."""

    class MockConnection:
        def __init__(self, pool):
            self.pool = pool

        async def executemany(self, query, records):
            self.pool.flush_count += 1

    class MockPoolContext:
        def __init__(self, conn):
            self.conn = conn

        async def __aenter__(self):
            return self.conn

        async def __aexit__(self, *args):
            pass

    class MockPool:
        def __init__(self):
            self.flush_count = 0
            self.conn = MockConnection(self)

        def acquire(self):
            return MockPoolContext(self.conn)

    pool = MockPool()  # type: ignore[assignment]
    batch_writer = BatchWriter(pool, batch_size=100, batch_timeout=10.0)
    await batch_writer.start()

    try:
        # Add exactly 100 routes (batch size)
        for i in range(100):
            route = RouteUpdate(
                time=datetime.now(UTC),
                bmp_peer_ip="192.0.2.1",
                bgp_peer_ip="198.51.100.1",
                family="ipv4_unicast",
                prefix=f"10.0.{i}.0/24",
            )
            await batch_writer.add_route(route)

        # Verify flush happened immediately (no need to wait for timeout)
        assert pool.flush_count == 1
        assert batch_writer.total_routes_written == 100
        assert len(batch_writer.batch) == 0  # Batch should be empty

    finally:
        await batch_writer.stop()
