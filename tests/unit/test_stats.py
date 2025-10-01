"""Unit tests for statistics collector."""

import asyncio

import pytest
from pybmpmon.monitoring.stats import PeerStats, StatisticsCollector


class TestPeerStats:
    """Test PeerStats class."""

    def test_peer_stats_initialization(self):
        """Test PeerStats initialization."""
        stats = PeerStats(peer_ip="192.0.2.1")

        assert stats.peer_ip == "192.0.2.1"
        assert stats.routes_received == 0
        assert stats.routes_processed == 0
        assert stats.ipv4_routes == 0
        assert stats.ipv6_routes == 0
        assert stats.evpn_routes == 0
        assert stats.errors == 0

    def test_increment_received(self):
        """Test incrementing received counter."""
        stats = PeerStats(peer_ip="192.0.2.1")

        stats.increment_received()
        assert stats.routes_received == 1

        stats.increment_received()
        assert stats.routes_received == 2

    def test_increment_processed_ipv4(self):
        """Test incrementing processed counter for IPv4."""
        stats = PeerStats(peer_ip="192.0.2.1")

        stats.increment_processed("ipv4_unicast")

        assert stats.routes_processed == 1
        assert stats.ipv4_routes == 1
        assert stats.ipv6_routes == 0
        assert stats.evpn_routes == 0

    def test_increment_processed_ipv6(self):
        """Test incrementing processed counter for IPv6."""
        stats = PeerStats(peer_ip="192.0.2.1")

        stats.increment_processed("ipv6_unicast")

        assert stats.routes_processed == 1
        assert stats.ipv4_routes == 0
        assert stats.ipv6_routes == 1
        assert stats.evpn_routes == 0

    def test_increment_processed_evpn(self):
        """Test incrementing processed counter for EVPN."""
        stats = PeerStats(peer_ip="192.0.2.1")

        stats.increment_processed("evpn")

        assert stats.routes_processed == 1
        assert stats.ipv4_routes == 0
        assert stats.ipv6_routes == 0
        assert stats.evpn_routes == 1

    def test_increment_processed_multiple_families(self):
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

    def test_increment_error(self):
        """Test incrementing error counter."""
        stats = PeerStats(peer_ip="192.0.2.1")

        stats.increment_error()
        assert stats.errors == 1

        stats.increment_error()
        assert stats.errors == 2

    def test_reset(self):
        """Test resetting all counters."""
        stats = PeerStats(peer_ip="192.0.2.1")

        # Set some counters
        stats.increment_received()
        stats.increment_processed("ipv4_unicast")
        stats.increment_processed("ipv6_unicast")
        stats.increment_error()

        # Reset
        stats.reset()

        # Verify all counters are zero
        assert stats.routes_received == 0
        assert stats.routes_processed == 0
        assert stats.ipv4_routes == 0
        assert stats.ipv6_routes == 0
        assert stats.evpn_routes == 0
        assert stats.errors == 0


class TestStatisticsCollector:
    """Test StatisticsCollector class."""

    def test_collector_initialization(self):
        """Test StatisticsCollector initialization."""
        collector = StatisticsCollector(log_interval=5.0)

        assert collector.log_interval == 5.0
        assert len(collector._stats) == 0
        assert collector._running is False

    def test_get_peer_stats_creates_new(self):
        """Test getting peer stats creates entry if not exists."""
        collector = StatisticsCollector()

        stats = collector.get_peer_stats("192.0.2.1")

        assert stats.peer_ip == "192.0.2.1"
        assert "192.0.2.1" in collector._stats

    def test_get_peer_stats_returns_existing(self):
        """Test getting peer stats returns existing entry."""
        collector = StatisticsCollector()

        stats1 = collector.get_peer_stats("192.0.2.1")
        stats1.increment_received()

        stats2 = collector.get_peer_stats("192.0.2.1")

        assert stats2 is stats1
        assert stats2.routes_received == 1

    def test_increment_received(self):
        """Test increment_received method."""
        collector = StatisticsCollector()

        collector.increment_received("192.0.2.1")

        stats = collector.get_peer_stats("192.0.2.1")
        assert stats.routes_received == 1

    def test_increment_processed(self):
        """Test increment_processed method."""
        collector = StatisticsCollector()

        collector.increment_processed("192.0.2.1", "ipv4_unicast")

        stats = collector.get_peer_stats("192.0.2.1")
        assert stats.routes_processed == 1
        assert stats.ipv4_routes == 1

    def test_increment_error(self):
        """Test increment_error method."""
        collector = StatisticsCollector()

        collector.increment_error("192.0.2.1")

        stats = collector.get_peer_stats("192.0.2.1")
        assert stats.errors == 1

    def test_remove_peer(self):
        """Test removing peer stats."""
        collector = StatisticsCollector()

        collector.increment_received("192.0.2.1")
        assert "192.0.2.1" in collector._stats

        collector.remove_peer("192.0.2.1")
        assert "192.0.2.1" not in collector._stats

    def test_remove_nonexistent_peer(self):
        """Test removing nonexistent peer doesn't raise error."""
        collector = StatisticsCollector()

        # Should not raise
        collector.remove_peer("192.0.2.99")

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        """Test starting and stopping collector."""
        collector = StatisticsCollector(log_interval=1.0)

        await collector.start()
        assert collector._running is True
        assert collector._logging_task is not None

        await asyncio.sleep(0.1)  # Let it run briefly

        await collector.stop()
        assert collector._running is False

    @pytest.mark.asyncio
    async def test_start_twice(self):
        """Test starting collector twice doesn't create multiple tasks."""
        collector = StatisticsCollector(log_interval=1.0)

        await collector.start()
        task1 = collector._logging_task

        await collector.start()
        task2 = collector._logging_task

        assert task1 is task2

        await collector.stop()

    @pytest.mark.asyncio
    async def test_periodic_logging_resets_counters(self):
        """Test that periodic logging resets counters after logging."""
        collector = StatisticsCollector(log_interval=0.5)

        # Add some stats
        collector.increment_received("192.0.2.1")
        collector.increment_processed("192.0.2.1", "ipv4_unicast")

        await collector.start()

        # Wait for one log interval plus buffer
        await asyncio.sleep(0.7)

        await collector.stop()

        # Counters should be reset after logging
        stats = collector.get_peer_stats("192.0.2.1")
        assert stats.routes_received == 0
        assert stats.routes_processed == 0
        assert stats.ipv4_routes == 0

    @pytest.mark.asyncio
    async def test_multiple_peers(self):
        """Test tracking multiple peers simultaneously."""
        collector = StatisticsCollector()

        collector.increment_received("192.0.2.1")
        collector.increment_received("192.0.2.2")
        collector.increment_received("192.0.2.1")

        stats1 = collector.get_peer_stats("192.0.2.1")
        stats2 = collector.get_peer_stats("192.0.2.2")

        assert stats1.routes_received == 2
        assert stats2.routes_received == 1
