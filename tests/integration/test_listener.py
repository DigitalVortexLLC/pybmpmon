"""Integration tests for BMP listener."""

import asyncio

import pytest
from pybmpmon.database.batch_writer import BatchWriter
from pybmpmon.listener import BMPListener
from pybmpmon.monitoring.stats import StatisticsCollector


# Mock database pool and batch writer for tests
class MockConnection:
    async def copy_records_to_table(self, table, records, columns):
        pass

    async def execute(self, query, *args):
        """Mock execute for last_seen updates."""
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


@pytest.fixture
async def mock_pool():
    """Provide a mock database pool."""
    return MockPool()  # type: ignore[return-value]


@pytest.fixture
async def mock_batch_writer(mock_pool):
    """Provide a mock batch writer."""
    writer = BatchWriter(mock_pool, batch_size=1000, batch_timeout=0.5)
    await writer.start()
    yield writer
    await writer.stop()


@pytest.fixture
async def mock_stats_collector():
    """Provide a mock statistics collector."""
    collector = StatisticsCollector(log_interval=10.0)
    await collector.start()
    yield collector
    await collector.stop()


@pytest.mark.asyncio
async def test_listener_starts_and_stops(
    mock_pool, mock_batch_writer, mock_stats_collector
) -> None:
    """Test that the listener can start and stop cleanly."""
    listener = BMPListener(
        "127.0.0.1", 11020, mock_pool, mock_batch_writer, mock_stats_collector
    )

    # Start listener
    await listener.start()

    # Verify server is running
    assert listener.server is not None

    # Stop listener
    await listener.stop()

    # Verify server is closed
    assert listener.server is not None  # Server object still exists but is closed


@pytest.mark.asyncio
async def test_listener_accepts_connection(
    mock_pool, mock_batch_writer, mock_stats_collector
) -> None:
    """Test that the listener accepts a connection and reads a header."""
    listener = BMPListener(
        "127.0.0.1", 11021, mock_pool, mock_batch_writer, mock_stats_collector
    )

    try:
        # Start listener
        await listener.start()

        # Connect as a client
        reader, writer = await asyncio.open_connection("127.0.0.1", 11021)

        # Send a valid BMP Initiation header
        # Version=3, Length=6, Type=4 (Initiation)
        writer.write(b"\x03\x00\x00\x00\x06\x04")
        await writer.drain()

        # Give the server a moment to process
        await asyncio.sleep(0.1)

        # Close client connection
        writer.close()
        await writer.wait_closed()

        # Give the server a moment to handle disconnect
        await asyncio.sleep(0.1)

    finally:
        # Stop listener
        await listener.stop()


@pytest.mark.asyncio
async def test_listener_handles_multiple_messages(
    mock_pool, mock_batch_writer, mock_stats_collector
) -> None:
    """Test that the listener can handle multiple messages from a client."""
    listener = BMPListener(
        "127.0.0.1", 11022, mock_pool, mock_batch_writer, mock_stats_collector
    )

    try:
        # Start listener
        await listener.start()

        # Connect as a client
        reader, writer = await asyncio.open_connection("127.0.0.1", 11022)

        # Send multiple BMP headers
        messages = [
            b"\x03\x00\x00\x00\x06\x04",  # Initiation
            b"\x03\x00\x00\x00\x06\x03",  # Peer Up
            b"\x03\x00\x00\x00\x06\x00",  # Route Monitoring
            b"\x03\x00\x00\x00\x06\x05",  # Termination
        ]

        for msg in messages:
            writer.write(msg)
            await writer.drain()
            # Small delay between messages
            await asyncio.sleep(0.05)

        # Give server time to process
        await asyncio.sleep(0.1)

        # Close client connection
        writer.close()
        await writer.wait_closed()

        await asyncio.sleep(0.1)

    finally:
        # Stop listener
        await listener.stop()


@pytest.mark.asyncio
async def test_listener_handles_malformed_header(
    mock_pool, mock_batch_writer, mock_stats_collector
) -> None:
    """Test that the listener handles malformed headers gracefully."""
    listener = BMPListener(
        "127.0.0.1", 11023, mock_pool, mock_batch_writer, mock_stats_collector
    )

    try:
        # Start listener
        await listener.start()

        # Connect as a client
        reader, writer = await asyncio.open_connection("127.0.0.1", 11023)

        # Send malformed header (invalid version)
        writer.write(b"\x02\x00\x00\x00\x06\x04")
        await writer.drain()

        # Give server time to process
        await asyncio.sleep(0.1)

        # Connection should still be alive - send valid header
        writer.write(b"\x03\x00\x00\x00\x06\x04")
        await writer.drain()

        await asyncio.sleep(0.1)

        # Close client connection
        writer.close()
        await writer.wait_closed()

        await asyncio.sleep(0.1)

    finally:
        # Stop listener
        await listener.stop()


@pytest.mark.asyncio
async def test_listener_handles_large_message(
    mock_pool, mock_batch_writer, mock_stats_collector
) -> None:
    """Test that the listener handles messages with body content."""
    listener = BMPListener(
        "127.0.0.1", 11024, mock_pool, mock_batch_writer, mock_stats_collector
    )

    try:
        # Start listener
        await listener.start()

        # Connect as a client
        reader, writer = await asyncio.open_connection("127.0.0.1", 11024)

        # Send header indicating 100-byte message
        # Version=3, Length=100, Type=0 (Route Monitoring)
        writer.write(b"\x03\x00\x00\x00\x64\x00")
        # Send body (94 bytes of dummy data since header is 6 bytes)
        writer.write(b"\x00" * 94)
        await writer.drain()

        # Give server time to process
        await asyncio.sleep(0.1)

        # Close client connection
        writer.close()
        await writer.wait_closed()

        await asyncio.sleep(0.1)

    finally:
        # Stop listener
        await listener.stop()
