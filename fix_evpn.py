import asyncio, asyncpg, os
async def fix():
    c = await asyncpg.connect(host=os.getenv('DB_HOST'), port=int(os.getenv('DB_PORT', '5432')), user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'), database=os.getenv('DB_NAME'))
    try:
        print("Dropping old primary key...")
        await c.execute('ALTER TABLE route_state DROP CONSTRAINT IF EXISTS route_state_pkey')
        print("Making prefix nullable...")
        await c.execute('ALTER TABLE route_state ALTER COLUMN prefix DROP NOT NULL')
        print("Creating IP routes unique index...")
        await c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_route_state_ip_routes ON route_state (bmp_peer_ip, bgp_peer_ip, family, prefix) WHERE family IN ('ipv4_unicast', 'ipv6_unicast') AND prefix IS NOT NULL")
        print("Creating EVPN routes unique index...")
        await c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_route_state_evpn_routes ON route_state (bmp_peer_ip, bgp_peer_ip, family, COALESCE(evpn_rd, ''), COALESCE(evpn_esi, ''), COALESCE(mac_address, ''), COALESCE(prefix::TEXT, '')) WHERE family = 'evpn'")
        print("✓ Migration completed successfully!")
    finally:
        await c.close()
asyncio.run(fix())
