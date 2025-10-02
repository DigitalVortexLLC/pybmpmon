"""Database connection pool management using asyncpg."""

import asyncpg  # type: ignore[import-untyped]

from pybmpmon.monitoring.logger import get_logger

logger = get_logger(__name__)


def _encode_macaddr(value: str | None) -> bytes | None:
    """Encode MAC address string to binary format for PostgreSQL MACADDR type."""
    if value is None:
        return None
    # PostgreSQL expects MAC address as 6 bytes
    # Convert "08:00:2b:01:02:03" to bytes
    parts = value.replace("-", ":").split(":")
    return bytes(int(part, 16) for part in parts)


def _decode_macaddr(value: bytes | None) -> str | None:
    """Decode binary MACADDR from PostgreSQL to string format."""
    if value is None:
        return None
    # Convert 6 bytes to "08:00:2b:01:02:03" format
    return ":".join(f"{b:02x}" for b in value)


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Initialize connection with custom type codecs."""
    # Register MACADDR codec (OID 829) for binary protocol support
    await conn.set_type_codec(
        "macaddr",
        encoder=_encode_macaddr,
        decoder=_decode_macaddr,
        schema="pg_catalog",
        format="binary",
    )


class DatabasePool:
    """
    Manages asyncpg connection pool for database operations.

    Provides connection pool with 5-10 connections for concurrent operations.
    Handles connection lifecycle and proper cleanup.
    """

    def __init__(self) -> None:
        """Initialize database pool manager."""
        self.pool: asyncpg.Pool | None = None

    async def connect(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        min_size: int = 5,
        max_size: int = 10,
        command_timeout: float = 30.0,
        timeout: float = 5.0,
    ) -> None:
        """
        Create and initialize the connection pool.

        Args:
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            min_size: Minimum number of connections in pool (default: 5)
            max_size: Maximum number of connections in pool (default: 10)
            command_timeout: Command execution timeout in seconds (default: 30)
            timeout: Connection timeout in seconds (default: 5)

        Raises:
            asyncpg.PostgresError: If connection fails
        """
        logger.info(
            "database_pool_connecting",
            host=host,
            port=port,
            database=database,
            min_size=min_size,
            max_size=max_size,
        )

        try:
            self.pool = await asyncpg.create_pool(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                min_size=min_size,
                max_size=max_size,
                command_timeout=command_timeout,
                timeout=timeout,
                init=_init_connection,
            )

            # Test connection
            async with self.pool.acquire() as conn:
                version = await conn.fetchval("SELECT version()")
                logger.info("database_pool_connected", postgres_version=version)

        except Exception as e:
            logger.error("database_pool_connection_failed", error=str(e))
            raise

    async def close(self) -> None:
        """Close the connection pool and cleanup resources."""
        if self.pool:
            logger.info("database_pool_closing")
            await self.pool.close()
            self.pool = None
            logger.info("database_pool_closed")

    def get_pool(self) -> asyncpg.Pool:
        """
        Get the connection pool.

        Returns:
            asyncpg.Pool: The active connection pool

        Raises:
            RuntimeError: If pool is not initialized
        """
        if self.pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        return self.pool

    async def execute(self, query: str, *args: object) -> str:
        """
        Execute a query that does not return results.

        Args:
            query: SQL query to execute
            *args: Query parameters

        Returns:
            Status string from database

        Raises:
            RuntimeError: If pool not initialized
            asyncpg.PostgresError: On database errors
        """
        pool = self.get_pool()
        async with pool.acquire() as conn:
            return await conn.execute(query, *args)  # type: ignore[no-any-return]

    async def fetch(self, query: str, *args: object) -> list[asyncpg.Record]:
        """
        Execute a query and return all results.

        Args:
            query: SQL query to execute
            *args: Query parameters

        Returns:
            List of records

        Raises:
            RuntimeError: If pool not initialized
            asyncpg.PostgresError: On database errors
        """
        pool = self.get_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *args)  # type: ignore[no-any-return]

    async def fetchrow(self, query: str, *args: object) -> asyncpg.Record | None:
        """
        Execute a query and return first result.

        Args:
            query: SQL query to execute
            *args: Query parameters

        Returns:
            Single record or None if no results

        Raises:
            RuntimeError: If pool not initialized
            asyncpg.PostgresError: On database errors
        """
        pool = self.get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: object, column: int = 0) -> int:
        """
        Execute a query and return single value.

        Args:
            query: SQL query to execute
            *args: Query parameters
            column: Column index to return (default: 0)

        Returns:
            Single value from first row

        Raises:
            RuntimeError: If pool not initialized
            asyncpg.PostgresError: On database errors
        """
        pool = self.get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(query, *args, column=column)  # type: ignore[no-any-return]


# Global database pool instance
_db_pool: DatabasePool | None = None


async def get_database_pool(
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
) -> DatabasePool:
    """
    Get or create the global database pool.

    Args:
        host: Database host
        port: Database port
        database: Database name
        user: Database user
        password: Database password

    Returns:
        DatabasePool instance
    """
    global _db_pool

    if _db_pool is None:
        _db_pool = DatabasePool()
        await _db_pool.connect(host, port, database, user, password)

    return _db_pool


async def close_database_pool() -> None:
    """Close the global database pool."""
    global _db_pool

    if _db_pool is not None:
        await _db_pool.close()
        _db_pool = None
