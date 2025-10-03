"""Application entry point."""

import asyncio
import functools
import signal
import sys

import structlog

from pybmpmon.config import settings
from pybmpmon.database.migrations import initialize_database_schema
from pybmpmon.listener import run_listener
from pybmpmon.monitoring.logger import configure_logging

logger: structlog.BoundLogger | None = None


def setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    """
    Setup signal handlers for graceful shutdown.

    Args:
        loop: Asyncio event loop
    """

    def signal_handler(sig: int) -> None:
        """Handle shutdown signals."""
        if logger:
            logger.info("signal_received", signal=signal.Signals(sig).name)
        # Cancel all tasks to trigger graceful shutdown
        for task in asyncio.all_tasks(loop):
            task.cancel()

    # Register signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, functools.partial(signal_handler, sig))


def main() -> None:
    """Main application entry point."""
    global logger

    try:
        # Configure logging first
        logger = configure_logging()

        logger.info(
            "pybmpmon_starting",
            version="0.1.0",
            python_version=sys.version.split()[0],
            listen_host=settings.bmp_listen_host,
            listen_port=settings.bmp_listen_port,
            log_level=settings.log_level,
        )

        # Create event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Setup signal handlers
        setup_signal_handlers(loop)

        # Initialize database schema if needed
        logger.info("initializing_database")
        loop.run_until_complete(
            initialize_database_schema(
                host=settings.db_host,
                port=settings.db_port,
                database=settings.db_name,
                user=settings.db_user,
                password=settings.db_password,
            )
        )

        # Run the listener
        try:
            loop.run_until_complete(run_listener())
        except asyncio.CancelledError:
            logger.info("shutdown_initiated")
        except KeyboardInterrupt:
            logger.info("keyboard_interrupt")
        finally:
            # Cancel all remaining tasks
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()

            # Wait for all tasks to complete
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )

            loop.close()
            logger.info("pybmpmon_stopped")

    except Exception as e:
        if logger:
            logger.critical("startup_error", error=str(e), exc_info=True)
        else:
            print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
