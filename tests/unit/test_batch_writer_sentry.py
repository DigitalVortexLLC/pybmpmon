"""Unit tests for BatchWriter Sentry span integration."""

import asyncio
from datetime import UTC, datetime
from unittest import mock

import pytest
from pybmpmon.database.batch_writer import BatchWriter
from pybmpmon.models.route import RouteUpdate
from pybmpmon.monitoring import sentry_helper


@pytest.mark.asyncio
async def test_batch_writer_creates_sentry_span():
    """Test that batch writer creates a Sentry span with correct data."""
    # Setup mock Sentry SDK
    mock_sentry_sdk = mock.MagicMock()
    mock_span = mock.MagicMock()
    mock_sentry_sdk.start_span.return_value.__enter__.return_value = mock_span

    # Enable Sentry
    sentry_helper._sentry_enabled = True
    sentry_helper._sentry_sdk = mock_sentry_sdk

    try:
        # Create mock connection
        class MockConnection:
            async def copy_records_to_table(self, table, records, columns):
                # Simulate some processing time
                await asyncio.sleep(0.001)

            async def execute(self, query, *args):
                # Mock execute for route state updates
                pass

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
        batch_writer = BatchWriter(pool, batch_size=10, batch_timeout=0.1)
        await batch_writer.start()

        try:
            # Add some routes
            for i in range(5):
                route = RouteUpdate(
                    time=datetime.now(UTC),
                    bmp_peer_ip="192.0.2.1",
                    bgp_peer_ip="198.51.100.1",
                    family="ipv4_unicast",
                    prefix=f"10.0.{i}.0/24",
                )
                await batch_writer.add_route(route)

            # Flush to trigger span creation
            await batch_writer.flush()

            # Verify span was created
            mock_sentry_sdk.start_span.assert_called_once()
            call_args = mock_sentry_sdk.start_span.call_args

            # Verify span operation and description
            assert call_args[1]["op"] == "db.batch_write"
            assert call_args[1]["description"] == "Batch write routes to database"

            # Verify span data was set
            mock_span.set_data.assert_any_call("batch.routes_count", 5)
            mock_span.set_data.assert_any_call("db.table", "route_updates")
            mock_span.set_data.assert_any_call("db.operation", "COPY")

            # Verify other span data was set (duration, throughput, totals)
            set_data_calls = [call[0][0] for call in mock_span.set_data.call_args_list]
            assert "batch.duration_ms" in set_data_calls
            assert "batch.routes_per_second" in set_data_calls
            assert "total.routes_written" in set_data_calls
            assert "total.batches_written" in set_data_calls

        finally:
            await batch_writer.stop()

    finally:
        # Cleanup
        sentry_helper._sentry_enabled = False
        sentry_helper._sentry_sdk = None


@pytest.mark.asyncio
async def test_batch_writer_works_without_sentry():
    """Test that batch writer works correctly when Sentry is disabled."""
    # Ensure Sentry is disabled
    sentry_helper._sentry_enabled = False
    sentry_helper._sentry_sdk = None

    # Create mock connection
    class MockConnection:
        async def copy_records_to_table(self, table, records, columns):
            await asyncio.sleep(0.001)

        async def execute(self, query, *args):
            pass

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
    batch_writer = BatchWriter(pool, batch_size=10, batch_timeout=0.1)
    await batch_writer.start()

    try:
        # Add and flush routes
        route = RouteUpdate(
            time=datetime.now(UTC),
            bmp_peer_ip="192.0.2.1",
            bgp_peer_ip="198.51.100.1",
            family="ipv4_unicast",
            prefix="10.0.0.0/24",
        )
        await batch_writer.add_route(route)
        await batch_writer.flush()

        # Verify it worked
        assert batch_writer.total_routes_written == 1
        assert batch_writer.total_batches_written == 1

    finally:
        await batch_writer.stop()
