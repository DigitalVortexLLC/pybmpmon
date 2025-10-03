"""Batch writer for efficient bulk database inserts."""

import asyncio
from typing import Any

import asyncpg  # type: ignore[import-untyped]

from pybmpmon.database.schema import TABLE_ROUTE_UPDATES
from pybmpmon.models.route import RouteUpdate
from pybmpmon.monitoring.logger import get_logger

logger = get_logger(__name__)


class BatchWriter:
    """
    Batches route updates and writes them efficiently to database using COPY.

    Accumulates routes in memory and flushes when:
    - Batch size reaches 1,000 routes
    - Timeout of 500ms is reached
    - Manual flush is requested

    Uses PostgreSQL COPY for high-throughput bulk inserts.
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        batch_size: int = 1000,
        batch_timeout: float = 0.5,
    ) -> None:
        """
        Initialize batch writer.

        Args:
            pool: Database connection pool
            batch_size: Routes to accumulate before flushing (default: 1000)
            batch_timeout: Max time in seconds before flushing (default: 0.5)
        """
        self.pool = pool
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout

        self.batch: list[tuple[Any, ...]] = []
        self.batch_start_time: float | None = None
        self.flush_task: asyncio.Task[None] | None = None
        self.is_running = False

        # Statistics
        self.total_routes_written = 0
        self.total_batches_written = 0

    async def start(self) -> None:
        """Start the batch writer and periodic flush task."""
        self.is_running = True
        self.flush_task = asyncio.create_task(self._periodic_flush())
        logger.info(
            "batch_writer_started",
            batch_size=self.batch_size,
            batch_timeout=self.batch_timeout,
        )

    async def stop(self) -> None:
        """Stop the batch writer and flush remaining routes."""
        self.is_running = False

        # Cancel periodic flush task
        if self.flush_task:
            self.flush_task.cancel()
            try:
                await self.flush_task
            except asyncio.CancelledError:
                pass

        # Flush any remaining routes
        await self.flush()

        logger.info(
            "batch_writer_stopped",
            total_routes=self.total_routes_written,
            total_batches=self.total_batches_written,
        )

    async def add_route(self, route: RouteUpdate) -> None:
        """
        Add a route to the batch.

        Args:
            route: Route update to add

        Raises:
            RuntimeError: If batch writer is not running
        """
        if not self.is_running:
            raise RuntimeError("Batch writer is not running. Call start() first.")

        # Convert RouteUpdate to tuple for COPY
        route_tuple = (
            route.time,
            str(route.bmp_peer_ip),
            route.bmp_peer_asn,
            str(route.bgp_peer_ip),
            route.bgp_peer_asn,
            route.family,
            route.prefix,
            str(route.next_hop) if route.next_hop else None,
            route.as_path,
            route.communities,
            route.extended_communities,
            route.med,
            route.local_pref,
            route.is_withdrawn,
            route.evpn_route_type,
            route.evpn_rd,
            route.evpn_esi,
            route.mac_address,
        )

        self.batch.append(route_tuple)

        # Set batch start time on first route
        if self.batch_start_time is None:
            self.batch_start_time = asyncio.get_event_loop().time()

        # Flush if batch is full
        if len(self.batch) >= self.batch_size:
            await self.flush()

    async def flush(self) -> None:
        """Flush accumulated routes to database using COPY."""
        if len(self.batch) == 0:
            return

        batch_count = len(self.batch)
        start_time = asyncio.get_event_loop().time()

        try:
            async with self.pool.acquire() as conn:
                # Use fast binary COPY (mac_address is TEXT so binary works)
                await conn.copy_records_to_table(
                    TABLE_ROUTE_UPDATES,
                    records=self.batch,
                    columns=[
                        "time",
                        "bmp_peer_ip",
                        "bmp_peer_asn",
                        "bgp_peer_ip",
                        "bgp_peer_asn",
                        "family",
                        "prefix",
                        "next_hop",
                        "as_path",
                        "communities",
                        "extended_communities",
                        "med",
                        "local_pref",
                        "is_withdrawn",
                        "evpn_route_type",
                        "evpn_rd",
                        "evpn_esi",
                        "mac_address",
                    ],
                )

                # Update route state tracking for each route in batch
                for route_tuple in self.batch:
                    await conn.execute(
                        """
                        SELECT update_route_state(
                            $1::TIMESTAMPTZ,
                            $2::INET,
                            $3::INET,
                            $4::TEXT,
                            $5::CIDR,
                            $6::INET,
                            $7::INTEGER[],
                            $8::TEXT[],
                            $9::TEXT[],
                            $10::INTEGER,
                            $11::INTEGER,
                            $12::BOOLEAN,
                            $13::INTEGER,
                            $14::TEXT,
                            $15::TEXT,
                            $16::TEXT
                        )
                        """,
                        route_tuple[0],  # time
                        route_tuple[1],  # bmp_peer_ip
                        route_tuple[3],  # bgp_peer_ip
                        route_tuple[5],  # family
                        route_tuple[6],  # prefix
                        route_tuple[7],  # next_hop
                        route_tuple[8],  # as_path
                        route_tuple[9],  # communities
                        route_tuple[10],  # extended_communities
                        route_tuple[11],  # med
                        route_tuple[12],  # local_pref
                        route_tuple[13],  # is_withdrawn
                        route_tuple[14],  # evpn_route_type
                        route_tuple[15],  # evpn_rd
                        route_tuple[16],  # evpn_esi
                        route_tuple[17],  # mac_address
                    )

            elapsed = (asyncio.get_event_loop().time() - start_time) * 1000
            self.total_routes_written += batch_count
            self.total_batches_written += 1

            logger.debug(
                "batch_flushed",
                routes=batch_count,
                duration_ms=f"{elapsed:.2f}",
                total_routes=self.total_routes_written,
            )

        except Exception as e:
            logger.error(
                "batch_flush_failed",
                error=str(e),
                routes_in_batch=batch_count,
            )
            raise

        finally:
            # Clear batch
            self.batch = []
            self.batch_start_time = None

    async def _periodic_flush(self) -> None:
        """Periodically flush batch based on timeout."""
        while self.is_running:
            try:
                await asyncio.sleep(0.1)  # Check every 100ms

                # Flush if timeout exceeded and batch is not empty
                if self.batch_start_time is not None:
                    elapsed = asyncio.get_event_loop().time() - self.batch_start_time
                    if elapsed >= self.batch_timeout:
                        await self.flush()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("periodic_flush_error", error=str(e))

    def get_stats(self) -> dict[str, Any]:
        """
        Get batch writer statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "total_routes_written": self.total_routes_written,
            "total_batches_written": self.total_batches_written,
            "current_batch_size": len(self.batch),
            "is_running": self.is_running,
        }
