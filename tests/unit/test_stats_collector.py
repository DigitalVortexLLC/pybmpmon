"""Unit tests for statistics collector.

Tests for tracking and reporting route processing statistics with
periodic logging and throughput calculations.
"""

import asyncio
from datetime import datetime

import pytest
from pybmpmon.monitoring.stats import PeerStats, StatisticsCollector


class TestPeerStats:
    """Test PeerStats dataclass functionality."""

    def test_create_peer_stats(self) -> None:
        """Test creating PeerStats instance."""
        stats = PeerStats(peer_ip="192.0.2.1")

        assert stats.peer_ip == "192.0.2.1"
        assert stats.routes_received == 0
        assert stats.routes_processed == 0
        assert stats.ipv4_routes == 0
        assert stats.ipv6_routes == 0
        assert stats.evpn_routes == 0
        assert stats.errors == 0
        assert isinstance(stats.last_update, datetime)

    def test_increment_received(self) -> None:
        """Test incrementing received counter."""
        stats = PeerStats(peer_ip="192.0.2.1")
        initial_time = stats.last_update

        # Wait a bit to ensure time changes
        import time

        time.sleep(0.01)

        stats.increment_received()

        assert stats.routes_received == 1
        assert stats.last_update > initial_time

        stats.increment_received()
        assert stats.routes_received == 2

    def test_increment_processed_ipv4(self) -> None:
        """Test incrementing processed counter for IPv4 routes."""
        stats = PeerStats(peer_ip="192.0.2.1")

        stats.increment_processed("ipv4_unicast")

        assert stats.routes_processed == 1
        assert stats.ipv4_routes == 1
        assert stats.ipv6_routes == 0
        assert stats.evpn_routes == 0

    def test_increment_processed_ipv6(self) -> None:
        """Test incrementing processed counter for IPv6 routes."""
        stats = PeerStats(peer_ip="192.0.2.1")

        stats.increment_processed("ipv6_unicast")

        assert stats.routes_processed == 1
        assert stats.ipv4_routes == 0
        assert stats.ipv6_routes == 1
        assert stats.evpn_routes == 0

    def test_increment_processed_evpn(self) -> None:
        """Test incrementing processed counter for EVPN routes."""
        stats = PeerStats(peer_ip="192.0.2.1")

        stats.increment_processed("evpn")

        assert stats.routes_processed == 1
        assert stats.ipv4_routes == 0
        assert stats.ipv6_routes == 0
        assert stats.evpn_routes == 1

    def test_increment_processed_unknown_family(self) -> None:
        """Test incrementing processed counter with unknown family."""
        stats = PeerStats(peer_ip="192.0.2.1")

        stats.increment_processed("unknown")

        # Should increment processed but not any family counter
        assert stats.routes_processed == 1
        assert stats.ipv4_routes == 0
        assert stats.ipv6_routes == 0
        assert stats.evpn_routes == 0

    def test_increment_processed_multiple_families(self) -> None:
        """Test incrementing processed counter for multiple families."""
        stats = PeerStats(peer_ip="192.0.2.1")

        stats.increment_processed("ipv4_unicast")
        stats.increment_processed("ipv4_unicast")
        stats.increment_processed("ipv6_unicast")
        stats.increment_processed("evpn")

        assert stats.routes_processed == 4
        assert stats.ipv4_routes == 2
        assert stats.ipv6_routes == 1
        assert stats.evpn_routes == 1

    def test_increment_error(self) -> None:
        """Test incrementing error counter."""
        stats = PeerStats(peer_ip="192.0.2.1")

        stats.increment_error()

        assert stats.errors == 1

        stats.increment_error()
        assert stats.errors == 2

    def test_reset_counters(self) -> None:
        """Test resetting all counters."""
        stats = PeerStats(peer_ip="192.0.2.1")

        # Set some values
        stats.routes_received = 100
        stats.routes_processed = 95
        stats.ipv4_routes = 50
        stats.ipv6_routes = 30
        stats.evpn_routes = 15
        stats.errors = 5

        # Reset
        stats.reset()

        # All counters should be zero
        assert stats.routes_received == 0
        assert stats.routes_processed == 0
        assert stats.ipv4_routes == 0
        assert stats.ipv6_routes == 0
        assert stats.evpn_routes == 0
        assert stats.errors == 0


class TestStatisticsCollector:
    """Test StatisticsCollector functionality."""

    @pytest.mark.asyncio
    async def test_create_collector(self) -> None:
        """Test creating StatisticsCollector instance."""
        collector = StatisticsCollector(log_interval=10.0)

        assert collector.log_interval == 10.0
        assert collector._running is False
        assert collector._logging_task is None
        assert len(collector._stats) == 0

    @pytest.mark.asyncio
    async def test_get_peer_stats(self) -> None:
        """Test getting stats for a peer (creates if doesn't exist)."""
        collector = StatisticsCollector()

        # Get stats for new peer
        stats = collector.get_peer_stats("192.0.2.1")

        assert stats.peer_ip == "192.0.2.1"
        assert stats.routes_received == 0

        # Get same peer again (should return same instance)
        stats2 = collector.get_peer_stats("192.0.2.1")
        assert stats2 is stats

    @pytest.mark.asyncio
    async def test_increment_received(self) -> None:
        """Test incrementing received counter via collector."""
        collector = StatisticsCollector()

        collector.increment_received("192.0.2.1")

        stats = collector.get_peer_stats("192.0.2.1")
        assert stats.routes_received == 1

    @pytest.mark.asyncio
    async def test_increment_processed(self) -> None:
        """Test incrementing processed counter via collector."""
        collector = StatisticsCollector()

        collector.increment_processed("192.0.2.1", "ipv4_unicast")
        collector.increment_processed("192.0.2.1", "ipv6_unicast")

        stats = collector.get_peer_stats("192.0.2.1")
        assert stats.routes_processed == 2
        assert stats.ipv4_routes == 1
        assert stats.ipv6_routes == 1

    @pytest.mark.asyncio
    async def test_increment_error(self) -> None:
        """Test incrementing error counter via collector."""
        collector = StatisticsCollector()

        collector.increment_error("192.0.2.1")
        collector.increment_error("192.0.2.1")

        stats = collector.get_peer_stats("192.0.2.1")
        assert stats.errors == 2

    @pytest.mark.asyncio
    async def test_remove_peer(self) -> None:
        """Test removing peer statistics."""
        collector = StatisticsCollector()

        # Add peer
        collector.increment_received("192.0.2.1")
        assert "192.0.2.1" in collector._stats

        # Remove peer
        collector.remove_peer("192.0.2.1")
        assert "192.0.2.1" not in collector._stats

    @pytest.mark.asyncio
    async def test_remove_nonexistent_peer(self) -> None:
        """Test removing peer that doesn't exist (should not error)."""
        collector = StatisticsCollector()

        # Should not raise exception
        collector.remove_peer("192.0.2.99")

    @pytest.mark.asyncio
    async def test_start_stop_collector(self) -> None:
        """Test starting and stopping the collector."""
        collector = StatisticsCollector(log_interval=10.0)

        # Start collector
        await collector.start()

        assert collector._running is True
        assert collector._logging_task is not None

        # Stop collector
        await collector.stop()

        assert collector._running is False
        assert collector._logging_task is None

    @pytest.mark.asyncio
    async def test_start_already_running(self) -> None:
        """Test starting collector when already running (should be idempotent)."""
        collector = StatisticsCollector()

        await collector.start()
        first_task = collector._logging_task

        # Start again
        await collector.start()

        # Should still be the same task
        assert collector._logging_task is first_task

        await collector.stop()

    @pytest.mark.asyncio
    async def test_throughput_calculation(self) -> None:
        """Test throughput calculation in periodic logging."""
        collector = StatisticsCollector(log_interval=1.0)

        # Add some routes
        for i in range(100):
            collector.increment_received("192.0.2.1")
            collector.increment_processed("192.0.2.1", "ipv4_unicast")

        # Start collector and wait for one logging interval
        await collector.start()
        await asyncio.sleep(1.2)  # Wait for one log interval

        # Stats should be reset after logging
        stats = collector.get_peer_stats("192.0.2.1")
        # Counters reset after logging
        assert stats.routes_received == 0
        assert stats.routes_processed == 0

        await collector.stop()

    @pytest.mark.asyncio
    async def test_multiple_peers_stats(self) -> None:
        """Test statistics for multiple peers."""
        collector = StatisticsCollector()

        # Add stats for 3 peers
        collector.increment_received("192.0.2.1")
        collector.increment_processed("192.0.2.1", "ipv4_unicast")

        collector.increment_received("192.0.2.2")
        collector.increment_received("192.0.2.2")
        collector.increment_processed("192.0.2.2", "ipv6_unicast")

        collector.increment_received("192.0.2.3")
        collector.increment_processed("192.0.2.3", "evpn")

        # Verify each peer has correct stats
        stats1 = collector.get_peer_stats("192.0.2.1")
        assert stats1.routes_received == 1
        assert stats1.ipv4_routes == 1

        stats2 = collector.get_peer_stats("192.0.2.2")
        assert stats2.routes_received == 2
        assert stats2.ipv6_routes == 1

        stats3 = collector.get_peer_stats("192.0.2.3")
        assert stats3.routes_received == 1
        assert stats3.evpn_routes == 1

    @pytest.mark.asyncio
    async def test_periodic_logging_no_activity(self) -> None:
        """Test that periodic logging skips peers with no activity."""
        collector = StatisticsCollector(log_interval=0.5)

        # Add peer but no activity
        collector.get_peer_stats("192.0.2.1")

        await collector.start()
        await asyncio.sleep(0.6)  # Wait for one interval

        # Stats should not be reset (no activity to log)
        stats = collector.get_peer_stats("192.0.2.1")
        assert stats.routes_received == 0

        await collector.stop()

    @pytest.mark.asyncio
    async def test_stats_collector_cancel_task(self) -> None:
        """Test that stopping collector properly cancels logging task."""
        collector = StatisticsCollector(log_interval=10.0)

        await collector.start()

        task = collector._logging_task
        assert task is not None
        assert not task.done()

        await collector.stop()

        # Task should be cancelled and done
        assert task.done()
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_concurrent_stats_updates(self) -> None:
        """Test concurrent updates to statistics from multiple coroutines."""
        collector = StatisticsCollector()

        async def update_stats(peer_ip: str, count: int):
            """Update stats multiple times."""
            for _ in range(count):
                collector.increment_received(peer_ip)
                collector.increment_processed(peer_ip, "ipv4_unicast")
                await asyncio.sleep(0.001)

        # Run concurrent updates
        await asyncio.gather(
            update_stats("192.0.2.1", 50),
            update_stats("192.0.2.1", 50),
            update_stats("192.0.2.2", 30),
        )

        # Verify final counts
        stats1 = collector.get_peer_stats("192.0.2.1")
        assert stats1.routes_received == 100
        assert stats1.routes_processed == 100

        stats2 = collector.get_peer_stats("192.0.2.2")
        assert stats2.routes_received == 30
        assert stats2.routes_processed == 30
