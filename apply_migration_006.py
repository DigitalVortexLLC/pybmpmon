#!/usr/bin/env python3
"""Apply migration 006 to fix EVPN prefix nullable constraint."""
import asyncio
import os
import sys
from pathlib import Path

import asyncpg


async def main():
    """Apply migration 006."""
    # Read database config from environment
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", "5432"))
    db_user = os.getenv("DB_USER", "bmpmon")
    db_password = os.getenv("DB_PASSWORD", "")
    db_name = os.getenv("DB_NAME", "bmpmon")

    print(f"Connecting to database at {db_host}:{db_port}...")

    # Connect to database
    conn = await asyncpg.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_password,
        database=db_name,
    )

    try:
        # Read migration file
        migration_file = Path(__file__).parent / "src/pybmpmon/database/migrations/006_fix_evpn_prefix_nullable.sql"
        migration_sql = migration_file.read_text()

        print("Applying migration 006...")
        await conn.execute(migration_sql)
        print("✓ Migration 006 applied successfully!")

        # Also update the function
        print("Updating update_route_state function...")
        function_file = Path(__file__).parent / "src/pybmpmon/database/migrations/005_add_route_state_tracking.sql"
        function_sql = function_file.read_text()

        # Extract just the CREATE OR REPLACE FUNCTION part
        function_start = function_sql.find("CREATE OR REPLACE FUNCTION update_route_state")
        if function_start >= 0:
            function_end = function_sql.find("$$ LANGUAGE plpgsql;", function_start)
            if function_end >= 0:
                function_only = function_sql[function_start:function_end + len("$$ LANGUAGE plpgsql;")]
                await conn.execute(function_only)
                print("✓ Function update_route_state updated successfully!")

        print("\n✓ All migrations applied successfully!")
        print("You can now restart the application.")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
