"""BMP TCP listener using asyncio."""

import asyncio
import time
from datetime import datetime

import asyncpg  # type: ignore[import-untyped]
import structlog

from pybmpmon.config import settings
from pybmpmon.database.batch_writer import BatchWriter
from pybmpmon.database.operations import (
    insert_peer_event,
    mark_peer_inactive,
    upsert_bmp_peer,
)
from pybmpmon.models.bmp_peer import BMPPeer, PeerEvent
from pybmpmon.models.route import RouteUpdate
from pybmpmon.monitoring.sentry_helper import (
    capture_parse_error,
    capture_peer_down_event,
    capture_peer_up_event,
)
from pybmpmon.monitoring.stats import StatisticsCollector
from pybmpmon.protocol.bgp import AddressFamilyIdentifier, BGPParseError
from pybmpmon.protocol.bgp_parser import parse_bgp_update
from pybmpmon.protocol.bmp import (
    BMP_HEADER_SIZE,
    BMPMessageType,
    BMPParseError,
)
from pybmpmon.protocol.bmp_parser import (
    parse_bmp_header,
    parse_peer_down_message,
    parse_peer_up_message,
    parse_route_monitoring_message,
)

logger = structlog.get_logger(__name__)


class BMPListener:
    """Asyncio TCP server for BMP connections."""

    def __init__(
        self,
        host: str,
        port: int,
        pool: asyncpg.Pool,
        batch_writer: BatchWriter,
        stats_collector: StatisticsCollector,
    ) -> None:
        """
        Initialize BMP listener.

        Args:
            host: Host address to bind to
            port: TCP port to listen on
            pool: Database connection pool
            batch_writer: Batch writer for route updates
            stats_collector: Statistics collector for monitoring
        """
        self.host = host
        self.port = port
        self.pool = pool
        self.batch_writer = batch_writer
        self.stats_collector = stats_collector
        self.server: asyncio.Server | None = None
        self._active_connections: set[asyncio.Task[None]] = set()
        self._connection_start_times: dict[str, float] = {}

    async def start(self) -> None:
        """Start the TCP server."""
        self.server = await asyncio.start_server(
            self._handle_connection, self.host, self.port
        )

        addr = self.server.sockets[0].getsockname() if self.server.sockets else None
        logger.info(
            "bmp_listener_started",
            host=self.host,
            port=self.port,
            address=addr,
        )

    async def stop(self) -> None:
        """Stop the TCP server and close all connections."""
        if self.server:
            logger.info("bmp_listener_stopping")
            self.server.close()
            await self.server.wait_closed()

            # Wait for all active connections to close
            if self._active_connections:
                logger.info(
                    "waiting_for_connections", count=len(self._active_connections)
                )
                await asyncio.gather(*self._active_connections, return_exceptions=True)

            logger.info("bmp_listener_stopped")

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """
        Handle an incoming BMP connection.

        Args:
            reader: Asyncio stream reader
            writer: Asyncio stream writer
        """
        peer_addr = writer.get_extra_info("peername")
        peer_ip = peer_addr[0] if peer_addr else "unknown"

        # Track connection start time for session duration
        connection_start_time = time.time()
        self._connection_start_times[peer_ip] = connection_start_time

        logger.info("peer_connected", peer=peer_ip)

        # Create task for this connection
        task = asyncio.current_task()
        if task:
            self._active_connections.add(task)

        try:
            while True:
                # Read BMP common header (6 bytes)
                header_data = await reader.readexactly(BMP_HEADER_SIZE)

                if not header_data:
                    # Connection closed
                    break

                try:
                    # Parse header
                    header = parse_bmp_header(header_data)

                    # Read rest of message
                    remaining_bytes = header.length - BMP_HEADER_SIZE
                    if remaining_bytes > 0:
                        message_body = await reader.readexactly(remaining_bytes)
                    else:
                        message_body = b""

                    # Complete message data
                    full_message = header_data + message_body

                    # DEBUG: Log complete message with hex dump
                    logger.debug(
                        "bmp_message_received",
                        peer=peer_ip,
                        version=header.version,
                        length=header.length,
                        msg_type=header.msg_type.name,
                        data_hex=full_message[:256].hex(),  # First 256 bytes
                        total_size=len(full_message),
                    )

                    # Update last_seen timestamp for peer
                    await self._update_peer_last_seen(peer_ip)

                    # Increment received counter
                    self.stats_collector.increment_received(peer_ip)

                    # Handle message based on type
                    await self._handle_bmp_message(
                        header.msg_type, full_message, peer_ip
                    )

                except BMPParseError as e:
                    logger.error(
                        "bmp_parse_error",
                        peer=peer_ip,
                        error=str(e),
                        data_hex=header_data[:256].hex(),
                    )
                    # Track error in stats
                    self.stats_collector.increment_error(peer_ip)
                    # Capture in Sentry
                    capture_parse_error(
                        error_type="bmp_parse_error",
                        peer_ip=peer_ip,
                        error_message=str(e),
                        data_hex=header_data[:256].hex(),
                        exception=e,
                    )
                    # Continue processing despite parse error
                    continue
                except BGPParseError as e:
                    logger.error(
                        "bgp_parse_error",
                        peer=peer_ip,
                        error=str(e),
                    )
                    # Track error in stats
                    self.stats_collector.increment_error(peer_ip)
                    # Capture in Sentry
                    capture_parse_error(
                        error_type="bgp_parse_error",
                        peer_ip=peer_ip,
                        error_message=str(e),
                        exception=e,
                    )
                    # Continue processing despite parse error
                    continue
                except Exception as e:
                    logger.error(
                        "message_processing_error",
                        peer=peer_ip,
                        error=str(e),
                    )
                    # Track error in stats
                    self.stats_collector.increment_error(peer_ip)
                    # Capture in Sentry
                    capture_parse_error(
                        error_type="message_processing_error",
                        peer_ip=peer_ip,
                        error_message=str(e),
                        exception=e,
                    )
                    # Continue processing despite error
                    continue

        except asyncio.IncompleteReadError:
            # Calculate session duration
            duration_seconds = int(time.time() - connection_start_time)
            logger.info(
                "peer_disconnected",
                peer=peer_ip,
                reason="incomplete_read",
                duration_seconds=duration_seconds,
            )
        except ConnectionResetError:
            # Calculate session duration
            duration_seconds = int(time.time() - connection_start_time)
            logger.info(
                "peer_disconnected",
                peer=peer_ip,
                reason="connection_reset",
                duration_seconds=duration_seconds,
            )
        except Exception as e:
            logger.error("connection_error", peer=peer_ip, error=str(e), exc_info=True)
        finally:
            writer.close()
            await writer.wait_closed()
            if task:
                self._active_connections.discard(task)

            # Clean up connection tracking
            if peer_ip in self._connection_start_times:
                duration_seconds = int(
                    time.time() - self._connection_start_times[peer_ip]
                )
                del self._connection_start_times[peer_ip]
            else:
                duration_seconds = 0

            # Remove peer from stats collector
            self.stats_collector.remove_peer(peer_ip)

            logger.info(
                "peer_connection_closed",
                peer=peer_ip,
                duration_seconds=duration_seconds,
            )

    async def _handle_bmp_message(
        self, msg_type: BMPMessageType, data: bytes, bmp_peer_ip: str
    ) -> None:
        """
        Handle BMP message based on type.

        Args:
            msg_type: BMP message type
            data: Complete BMP message data
            bmp_peer_ip: BMP peer IP address
        """
        if msg_type == BMPMessageType.ROUTE_MONITORING:
            await self._handle_route_monitoring(data, bmp_peer_ip)
        elif msg_type == BMPMessageType.PEER_UP_NOTIFICATION:
            await self._handle_peer_up(data, bmp_peer_ip)
        elif msg_type == BMPMessageType.PEER_DOWN_NOTIFICATION:
            await self._handle_peer_down(data, bmp_peer_ip)
        elif msg_type in (
            BMPMessageType.INITIATION,
            BMPMessageType.TERMINATION,
            BMPMessageType.STATISTICS_REPORT,
        ):
            # Log but don't process these message types yet
            logger.debug(
                "bmp_message_received",
                peer=bmp_peer_ip,
                msg_type=msg_type.name,
            )

    async def _handle_route_monitoring(self, data: bytes, bmp_peer_ip: str) -> None:
        """
        Handle Route Monitoring message - parse BGP UPDATE and add to batch.

        Args:
            data: Complete BMP Route Monitoring message
            bmp_peer_ip: BMP peer IP address
        """
        # Parse BMP Route Monitoring message
        parsed = parse_route_monitoring_message(data)

        # Parse BGP UPDATE message
        bgp_update = parse_bgp_update(parsed.bgp_update)

        # Determine route family
        family = self._determine_family(bgp_update.afi, bgp_update.safi)

        # DEBUG: Log BGP UPDATE details
        logger.debug(
            "bgp_update_parsed",
            peer=bmp_peer_ip,
            bgp_peer=parsed.per_peer_header.peer_address,
            family=family,
            prefixes_count=len(bgp_update.prefixes),
            withdrawn_count=len(bgp_update.withdrawn_prefixes),
            as_path=bgp_update.as_path,
            next_hop=str(bgp_update.next_hop) if bgp_update.next_hop else None,
        )

        # Process announced prefixes
        for prefix in bgp_update.prefixes:
            route = RouteUpdate(
                time=datetime.utcnow(),
                bmp_peer_ip=bmp_peer_ip,  # type: ignore[arg-type]
                bmp_peer_asn=None,  # Will be populated from peer_header if needed
                bgp_peer_ip=parsed.per_peer_header.peer_address,  # type: ignore[arg-type]
                bgp_peer_asn=parsed.per_peer_header.peer_asn,
                family=family,
                prefix=prefix,
                next_hop=bgp_update.next_hop,  # type: ignore[arg-type]
                as_path=bgp_update.as_path,
                communities=bgp_update.communities,
                med=bgp_update.med,
                local_pref=bgp_update.local_pref,
                is_withdrawn=False,
                evpn_route_type=bgp_update.evpn_route_type,
                evpn_rd=bgp_update.evpn_rd,
                evpn_esi=bgp_update.evpn_esi,
                mac_address=bgp_update.mac_address,
            )
            await self.batch_writer.add_route(route)
            # Track processed route in stats
            self.stats_collector.increment_processed(bmp_peer_ip, family)

        # Process withdrawn prefixes
        for prefix in bgp_update.withdrawn_prefixes:
            route = RouteUpdate(
                time=datetime.utcnow(),
                bmp_peer_ip=bmp_peer_ip,  # type: ignore[arg-type]
                bmp_peer_asn=None,
                bgp_peer_ip=parsed.per_peer_header.peer_address,  # type: ignore[arg-type]
                bgp_peer_asn=parsed.per_peer_header.peer_asn,
                family=family,
                prefix=prefix,
                next_hop=None,
                as_path=None,
                communities=None,
                med=None,
                local_pref=None,
                is_withdrawn=True,
                evpn_route_type=None,
                evpn_rd=None,
                evpn_esi=None,
                mac_address=None,
            )
            await self.batch_writer.add_route(route)
            # Track processed route in stats
            self.stats_collector.increment_processed(bmp_peer_ip, family)

    async def _handle_peer_up(self, data: bytes, bmp_peer_ip: str) -> None:
        """
        Handle Peer Up Notification - update database immediately.

        Args:
            data: Complete BMP Peer Up message
            bmp_peer_ip: BMP peer IP address
        """
        parsed = parse_peer_up_message(data)

        # Create/update BMP peer
        peer = BMPPeer(
            peer_ip=bmp_peer_ip,  # type: ignore[arg-type]
            router_id=None,  # Could extract from BGP OPEN if needed
            first_seen=datetime.utcnow(),
            last_seen=datetime.utcnow(),
            is_active=True,
        )
        await upsert_bmp_peer(self.pool, peer)

        # Insert peer event
        event = PeerEvent(
            time=datetime.utcnow(),
            peer_ip=bmp_peer_ip,  # type: ignore[arg-type]
            event_type="peer_up",
            reason_code=None,
        )
        await insert_peer_event(self.pool, event)

        logger.info(
            "bmp_peer_up",
            peer=bmp_peer_ip,
            bgp_peer=parsed.per_peer_header.peer_address,
            bgp_peer_asn=parsed.per_peer_header.peer_asn,
        )

        # Capture in Sentry
        capture_peer_up_event(
            peer_ip=bmp_peer_ip,
            bgp_peer=parsed.per_peer_header.peer_address,
            bgp_peer_asn=parsed.per_peer_header.peer_asn,
        )

    async def _handle_peer_down(self, data: bytes, bmp_peer_ip: str) -> None:
        """
        Handle Peer Down Notification - update database immediately.

        Args:
            data: Complete BMP Peer Down message
            bmp_peer_ip: BMP peer IP address
        """
        parsed = parse_peer_down_message(data)

        # Mark peer as inactive
        await mark_peer_inactive(self.pool, bmp_peer_ip)

        # Insert peer event
        event = PeerEvent(
            time=datetime.utcnow(),
            peer_ip=bmp_peer_ip,  # type: ignore[arg-type]
            event_type="peer_down",
            reason_code=parsed.reason,
        )
        await insert_peer_event(self.pool, event)

        logger.info(
            "bmp_peer_down",
            peer=bmp_peer_ip,
            reason=parsed.reason,
        )

        # Capture in Sentry
        capture_peer_down_event(
            peer_ip=bmp_peer_ip,
            reason=parsed.reason,
        )

    def _determine_family(self, afi: int | None, safi: int | None) -> str:
        """
        Determine route family string from AFI/SAFI.

        Args:
            afi: Address Family Identifier
            safi: Subsequent Address Family Identifier

        Returns:
            Route family string
        """
        if afi == AddressFamilyIdentifier.IPV4:
            return "ipv4_unicast"
        elif afi == AddressFamilyIdentifier.IPV6:
            return "ipv6_unicast"
        elif afi == AddressFamilyIdentifier.L2VPN:
            return "evpn"
        else:
            return "unknown"

    async def _update_peer_last_seen(self, peer_ip: str) -> None:
        """
        Update last_seen timestamp for BMP peer.

        Args:
            peer_ip: BMP peer IP address
        """
        query = """
            UPDATE bmp_peers
            SET last_seen = $2
            WHERE peer_ip = $1
        """

        async with self.pool.acquire() as conn:
            await conn.execute(query, peer_ip, datetime.utcnow())


async def run_listener(
    pool: asyncpg.Pool | None = None,
    batch_writer: BatchWriter | None = None,
    stats_collector: StatisticsCollector | None = None,
) -> None:
    """
    Run the BMP listener (main entry point for asyncio).

    Args:
        pool: Optional database pool (for testing)
        batch_writer: Optional batch writer (for testing)
        stats_collector: Optional statistics collector (for testing)
    """
    # Create database pool if not provided
    if pool is None:
        pool = await asyncpg.create_pool(
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            command_timeout=30.0,
            timeout=5.0,
        )
        logger.info("database_pool_created")

    # Create batch writer if not provided
    if batch_writer is None:
        batch_writer = BatchWriter(pool, batch_size=1000, batch_timeout=0.5)
        await batch_writer.start()
        logger.info("batch_writer_started")

    # Create statistics collector if not provided
    if stats_collector is None:
        stats_collector = StatisticsCollector(log_interval=10.0)
        await stats_collector.start()
        logger.info("stats_collector_started")

    listener = BMPListener(
        settings.bmp_listen_host,
        settings.bmp_listen_port,
        pool,
        batch_writer,
        stats_collector,
    )

    try:
        await listener.start()
        # Keep running until interrupted
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("listener_cancelled")
    finally:
        await listener.stop()
        await batch_writer.stop()
        await stats_collector.stop()
        if pool:
            await pool.close()
            logger.info("database_pool_closed")
