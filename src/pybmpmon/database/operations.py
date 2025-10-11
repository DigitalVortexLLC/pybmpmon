"""Database CRUD operations for BMP peers and routes."""

from datetime import UTC, datetime

import asyncpg  # type: ignore[import-untyped]

from pybmpmon.database.schema import (
    TABLE_BMP_PEERS,
    TABLE_PEER_EVENTS,
    TABLE_ROUTE_UPDATES,
)
from pybmpmon.models.bmp_peer import BMPPeer, PeerEvent
from pybmpmon.models.route import RouteUpdate


async def upsert_bmp_peer(pool: asyncpg.Pool, peer: BMPPeer) -> None:
    """
    Insert or update BMP peer in database.

    Uses INSERT ... ON CONFLICT to update existing peers.

    Args:
        pool: Database connection pool
        peer: BMP peer data

    Raises:
        asyncpg.PostgresError: On database errors
    """
    query = f"""
        INSERT INTO {TABLE_BMP_PEERS}
            (peer_ip, router_id, first_seen, last_seen, is_active)
        VALUES
            ($1, $2, $3, $4, $5)
        ON CONFLICT (peer_ip) DO UPDATE SET
            router_id = EXCLUDED.router_id,
            last_seen = EXCLUDED.last_seen,
            is_active = EXCLUDED.is_active
    """

    async with pool.acquire() as conn:
        await conn.execute(
            query,
            str(peer.peer_ip),
            str(peer.router_id) if peer.router_id else None,
            peer.first_seen,
            peer.last_seen,
            peer.is_active,
        )


async def get_bmp_peer(pool: asyncpg.Pool, peer_ip: str) -> BMPPeer | None:
    """
    Retrieve BMP peer from database.

    Args:
        pool: Database connection pool
        peer_ip: BMP peer IP address

    Returns:
        BMPPeer if found, None otherwise

    Raises:
        asyncpg.PostgresError: On database errors
    """
    query = f"""
        SELECT peer_ip, router_id, first_seen, last_seen, is_active
        FROM {TABLE_BMP_PEERS}
        WHERE peer_ip = $1
    """

    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, peer_ip)
        if row:
            return BMPPeer(
                peer_ip=row["peer_ip"],
                router_id=row["router_id"],
                first_seen=row["first_seen"],
                last_seen=row["last_seen"],
                is_active=row["is_active"],
            )
        return None


async def get_all_active_peers(pool: asyncpg.Pool) -> list[BMPPeer]:
    """
    Retrieve all active BMP peers.

    Args:
        pool: Database connection pool

    Returns:
        List of active BMP peers

    Raises:
        asyncpg.PostgresError: On database errors
    """
    query = f"""
        SELECT peer_ip, router_id, first_seen, last_seen, is_active
        FROM {TABLE_BMP_PEERS}
        WHERE is_active = TRUE
        ORDER BY last_seen DESC
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query)
        return [
            BMPPeer(
                peer_ip=row["peer_ip"],
                router_id=row["router_id"],
                first_seen=row["first_seen"],
                last_seen=row["last_seen"],
                is_active=row["is_active"],
            )
            for row in rows
        ]


async def mark_peer_inactive(pool: asyncpg.Pool, peer_ip: str) -> None:
    """
    Mark BMP peer as inactive.

    Args:
        pool: Database connection pool
        peer_ip: BMP peer IP address

    Raises:
        asyncpg.PostgresError: On database errors
    """
    query = f"""
        UPDATE {TABLE_BMP_PEERS}
        SET is_active = FALSE, last_seen = $2
        WHERE peer_ip = $1
    """

    async with pool.acquire() as conn:
        await conn.execute(query, peer_ip, datetime.now(UTC))


async def insert_peer_event(pool: asyncpg.Pool, event: PeerEvent) -> None:
    """
    Insert peer up/down event into database.

    Args:
        pool: Database connection pool
        event: Peer event data

    Raises:
        asyncpg.PostgresError: On database errors
    """
    query = f"""
        INSERT INTO {TABLE_PEER_EVENTS}
            (time, peer_ip, event_type, reason_code)
        VALUES
            ($1, $2, $3, $4)
    """

    async with pool.acquire() as conn:
        await conn.execute(
            query,
            event.time,
            str(event.peer_ip),
            event.event_type,
            event.reason_code,
        )


async def insert_route_update(pool: asyncpg.Pool, route: RouteUpdate) -> None:
    """
    Insert route update into database.

    Args:
        pool: Database connection pool
        route: Route update data

    Raises:
        asyncpg.PostgresError: On database errors
    """
    query = f"""
        INSERT INTO {TABLE_ROUTE_UPDATES} (
            time, bmp_peer_ip, bmp_peer_asn, bgp_peer_ip, bgp_peer_asn,
            family, prefix, next_hop, as_path, communities,
            med, local_pref, is_withdrawn,
            evpn_route_type, evpn_rd, evpn_esi, mac_address
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9, $10,
            $11, $12, $13,
            $14, $15, $16, $17
        )
    """

    async with pool.acquire() as conn:
        await conn.execute(
            query,
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
            route.med,
            route.local_pref,
            route.is_withdrawn,
            route.evpn_route_type,
            route.evpn_rd,
            route.evpn_esi,
            route.mac_address,
        )


async def get_route_count(pool: asyncpg.Pool) -> int:
    """
    Get total count of route updates in database.

    Args:
        pool: Database connection pool

    Returns:
        Total number of route updates

    Raises:
        asyncpg.PostgresError: On database errors
    """
    query = f"SELECT COUNT(*) FROM {TABLE_ROUTE_UPDATES}"

    async with pool.acquire() as conn:
        return await conn.fetchval(query)  # type: ignore[no-any-return]


async def get_route_count_by_peer(pool: asyncpg.Pool, peer_ip: str) -> int:
    """
    Get count of route updates for specific BMP peer.

    Args:
        pool: Database connection pool
        peer_ip: BMP peer IP address

    Returns:
        Number of routes from this peer

    Raises:
        asyncpg.PostgresError: On database errors
    """
    query = f"""
        SELECT COUNT(*)
        FROM {TABLE_ROUTE_UPDATES}
        WHERE bmp_peer_ip = $1
    """

    async with pool.acquire() as conn:
        return await conn.fetchval(query, peer_ip)  # type: ignore[no-any-return]


async def get_route_count_by_family(
    pool: asyncpg.Pool, family: str, peer_ip: str | None = None
) -> int:
    """
    Get count of routes by address family.

    Args:
        pool: Database connection pool
        family: Route family (ipv4_unicast, ipv6_unicast, evpn)
        peer_ip: Optional BMP peer IP filter

    Returns:
        Number of routes for this family

    Raises:
        asyncpg.PostgresError: On database errors
    """
    if peer_ip:
        query = f"""
            SELECT COUNT(*)
            FROM {TABLE_ROUTE_UPDATES}
            WHERE family = $1 AND bmp_peer_ip = $2
        """
        async with pool.acquire() as conn:
            return await conn.fetchval(query, family, peer_ip)  # type: ignore[no-any-return]
    else:
        query = f"""
            SELECT COUNT(*)
            FROM {TABLE_ROUTE_UPDATES}
            WHERE family = $1
        """
        async with pool.acquire() as conn:
            return await conn.fetchval(query, family)  # type: ignore[no-any-return]
