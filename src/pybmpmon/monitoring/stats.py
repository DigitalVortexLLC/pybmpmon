"""Statistics tracking for BMP peers and routes."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PeerStats:
    """Statistics for a single BMP peer."""

    peer_ip: str
    routes_received: int = 0
    routes_processed: int = 0
    ipv4_routes: int = 0
    ipv6_routes: int = 0
    evpn_routes: int = 0
    errors: int = 0
    last_update: datetime = field(default_factory=datetime.utcnow)

    def increment_received(self) -> None:
        """Increment routes received counter."""
        self.routes_received += 1
        self.last_update = datetime.utcnow()

    def increment_processed(self, family: str) -> None:
        """
        Increment routes processed counter and family-specific counter.

        Args:
            family: Route family (ipv4_unicast, ipv6_unicast, evpn)
        """
        self.routes_processed += 1

        if family == "ipv4_unicast":
            self.ipv4_routes += 1
        elif family == "ipv6_unicast":
            self.ipv6_routes += 1
        elif family == "evpn":
            self.evpn_routes += 1

        self.last_update = datetime.utcnow()

    def increment_error(self) -> None:
        """Increment error counter."""
        self.errors += 1
        self.last_update = datetime.utcnow()

    def reset(self) -> None:
        """Reset all counters (for periodic reporting)."""
        self.routes_received = 0
        self.routes_processed = 0
        self.ipv4_routes = 0
        self.ipv6_routes = 0
        self.evpn_routes = 0
        self.errors = 0
        self.last_update = datetime.utcnow()


class StatisticsCollector:
    """Collect and report statistics for all BMP peers."""

    def __init__(self, log_interval: float = 10.0) -> None:
        """
        Initialize statistics collector.

        Args:
            log_interval: Interval in seconds between log outputs (default: 10.0)
        """
        self.log_interval = log_interval
        self._stats: dict[str, PeerStats] = {}
        self._logging_task: asyncio.Task[None] | None = None
        self._running = False

    def get_peer_stats(self, peer_ip: str) -> PeerStats:
        """
        Get statistics for a peer (creates if doesn't exist).

        Args:
            peer_ip: BMP peer IP address

        Returns:
            PeerStats for the peer
        """
        if peer_ip not in self._stats:
            self._stats[peer_ip] = PeerStats(peer_ip=peer_ip)
        return self._stats[peer_ip]

    def increment_received(self, peer_ip: str) -> None:
        """
        Increment routes received for a peer.

        Args:
            peer_ip: BMP peer IP address
        """
        stats = self.get_peer_stats(peer_ip)
        stats.increment_received()

    def increment_processed(self, peer_ip: str, family: str) -> None:
        """
        Increment routes processed for a peer.

        Args:
            peer_ip: BMP peer IP address
            family: Route family
        """
        stats = self.get_peer_stats(peer_ip)
        stats.increment_processed(family)

    def increment_error(self, peer_ip: str) -> None:
        """
        Increment error count for a peer.

        Args:
            peer_ip: BMP peer IP address
        """
        stats = self.get_peer_stats(peer_ip)
        stats.increment_error()

    def remove_peer(self, peer_ip: str) -> None:
        """
        Remove peer statistics (called when peer disconnects).

        Args:
            peer_ip: BMP peer IP address
        """
        if peer_ip in self._stats:
            del self._stats[peer_ip]

    async def start(self) -> None:
        """Start periodic statistics logging."""
        if self._running:
            return

        self._running = True
        self._logging_task = asyncio.create_task(self._periodic_logging())
        logger.info("statistics_collector_started", interval_seconds=self.log_interval)

    async def stop(self) -> None:
        """Stop periodic statistics logging."""
        self._running = False

        if self._logging_task:
            self._logging_task.cancel()
            try:
                await self._logging_task
            except asyncio.CancelledError:
                pass
            self._logging_task = None

        logger.info("statistics_collector_stopped")

    async def _periodic_logging(self) -> None:
        """Periodically log statistics for all peers."""
        while self._running:
            try:
                await asyncio.sleep(self.log_interval)

                # Log stats for each peer
                for peer_ip, stats in self._stats.items():
                    # Only log if there's been activity
                    if (
                        stats.routes_received > 0
                        or stats.routes_processed > 0
                        or stats.errors > 0
                    ):
                        # Calculate throughput
                        throughput_per_sec = int(
                            stats.routes_processed / self.log_interval
                        )

                        logger.info(
                            "route_stats",
                            peer=peer_ip,
                            received=stats.routes_received,
                            processed=stats.routes_processed,
                            ipv4=stats.ipv4_routes,
                            ipv6=stats.ipv6_routes,
                            evpn=stats.evpn_routes,
                            errors=stats.errors,
                            throughput_per_sec=throughput_per_sec,
                        )

                        # Reset counters after logging
                        stats.reset()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("stats_logging_error", error=str(e), exc_info=True)
