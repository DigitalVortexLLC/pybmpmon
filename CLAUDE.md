# Project Overview

This application is a BGP Monitoring Protocol (BMP) listener and analyzer that receives BMP traffic from routers, processes it, and stores the data in a PostgreSQL/TimescaleDB database for analysis. It's designed to handle high-throughput BGP route data with support for multiple address families.

# Technical Requirements

## Environment
- **Python Versions**: 3.11, 3.12, and 3.13
- **Platforms**: Linux and macOS
- **Container**: Docker with Docker Compose
- **Database**: PostgreSQL with TimescaleDB plugin

## Deployment Configuration
- The app should start listening on port 11019 on startup
- Docker container should include all necessary services by default
- Docker Compose should allow disabling services by setting replicas to 0 (for external hosting)
- All configuration via `.env` file:
  - Listen port (default: 11019)
  - Database connection parameters
  - Log level (INFO/DEBUG)
  - Sentry configuration (with option to disable)

## Configuration
- Use Pydantic Settings to load from `.env` file
- Application will fail fast with clear errors if misconfigured
- Let PostgreSQL and asyncpg handle connection errors naturally

## Health Monitoring
Monitor application health using simple process checks:
- **BMP port accessibility**: `nc -z localhost 11019`
- **Database connectivity**: `pg_isready -h <db_host>`
- **Process running**: `pgrep -f pybmpmon`
- **Docker healthcheck**: Combine above checks in Dockerfile HEALTHCHECK directive

No separate HTTP server needed for health checks.

## Quality Standards
- ALL code must have test coverage
- After any code change, ensure all tests pass
- After any code change, ensure all formatting and linting tests pass
- Use type hints throughout the codebase

## Architecture Overview

### Simplified Design Philosophy
Start simple. Add complexity only when profiling shows it's needed. This is a monitoring tool, not a distributed system.

### Component Interaction Flow
1. **Asyncio TCP Server**: Accepts BMP connections on port 11019, handles multiple peers concurrently
2. **BMP Parser**: Parse BMP messages inline in async handlers
3. **BGP Parser**: Parse BGP UPDATEs inline in async handlers
4. **Batch Writer**: Accumulate routes in memory, flush to database using PostgreSQL COPY
5. **Statistics Logger**: Log per-peer statistics every 10 seconds

### Data Flow
```
BMP Peer → TCP Socket → Asyncio Handler
                              ↓
                       BMP Message Parser
                              ↓
              ┌───────────────┴───────────────┐
              ↓                               ↓
        State Messages                  Route Messages
        (Peer Up/Down,                (Route Monitoring)
         Statistics, etc.)                   ↓
              ↓                        BGP UPDATE Parser
        Handle Inline                        ↓
              ↓                         Batch Accumulator
         Database                      (1000 routes/batch)
                                             ↓
                                    PostgreSQL COPY
                                             ↓
                                         Database
```

### Concurrency Model
- **Asyncio only**: All I/O operations (network, database) use async/await
- **No multiprocessing**: BGP parsing is fast enough inline (~50μs per route)
- **No threading**: Keep it simple, asyncio handles thousands of concurrent connections
- **Expected throughput**: 15-20k routes/sec (sufficient for 1.1M routes in ~60 seconds)

## Core Technology Stack

### Primary Libraries
- **asyncio**: Built-in TCP server and all concurrency
- **asyncpg**: Fast async PostgreSQL driver with connection pooling
- **Pydantic v2**: Type-safe configuration from `.env` files
- **structlog**: Structured JSON logging to stdout
- **sentry-sdk** (optional): Error tracking and monitoring

### Development Tools
- **pytest**: Test framework with async support
- **pytest-asyncio**: Async test fixtures
- **black**: Code formatting (line length 88)
- **ruff**: Fast linting and import sorting
- **mypy**: Static type checking (strict mode)

# Core Features

## BMP Protocol Support
- Full RFC7854 compliance for all BMP Message Types
- Reference: https://datatracker.ietf.org/doc/html/rfc7854
- Support BMP message types: Route Monitoring, Statistics Report, Peer Down Notification, Peer Up Notification, Initiation, Termination

## BGP Family Support
- **IPv4 Unicast**
- **IPv6 Unicast**
- **EVPN**: All route types

## BMP Peer Tracking
- Track all BMP peers in the database
- Record start time and last seen time for each BMP peer
- Track all available data on peering sessions reported by the BMP peer
- Log BMP peer up events: "BMP peer {ip_address} has established a session"
- Log BMP peer down events with timestamp and reason code

## Route Tracking
- Track whether a route is currently withdrawn
- Track route churn to identify routing instabilities
- Track first appearance and last seen time for each route
- Store all available BMP metadata for each route

## Logging and Monitoring
- Every 10 seconds: Log INFO message with statistics per BMP peer:
  - Routes received
  - Routes processed
  - Routes learned (by family type)
- DEBUG level: Dump BMP message packet details
- All logs output to stdout and optionally to Sentry

## Performance

### Processing Architecture
- **Asyncio TCP Server**: Handle all BMP connections concurrently
- **Inline Parsing**: Parse BMP and BGP messages in async handlers (no separate workers)
- **Batch Accumulator**: Collect parsed routes in memory, flush to database periodically
- **PostgreSQL COPY**: Bulk insert 1,000 routes per operation

### Performance Targets
- **Route Processing**: 15,000-20,000 routes/second (sufficient for requirements)
- **Initial Load Time**: Complete 1.1M route table in ~60 seconds
- **Batch Size**: 1,000 routes per COPY operation
- **Batch Timeout**: 500ms maximum wait before flush
- **Database Connections**: 5-10 (connection pool via asyncpg)

### Why This is Fast Enough
- **BGP parsing**: ~50μs per route in Python
- **Database batch insert**: ~100μs per route (with COPY)
- **Throughput**: ~6,600 routes/sec single-threaded theoretical
- **With batching**: 15-20k routes/sec achievable
- **1.1M routes**: ~60 seconds (well under 5-8 minute requirement)

### Database Connection Pool
Simple asyncpg pool configuration:
```python
pool = await asyncpg.create_pool(
    settings.database_url,
    min_size=5,
    max_size=10,
    command_timeout=30.0,
    timeout=5.0,
)
```

## Scaling
- IPv4 route table: ~1.1M routes per peer
- IPv6 route table: ~500k routes per peer
- EVPN route table: ~250k routes per peer
- Expected throughput: 15-20k routes/sec
- Initial peer load: 1-2 minutes (well under 5-8 minute target)
- Data retention: 5 years for routes (configurable), 6 months for session state

## Recovery and Error Handling

### Application Crashes
- When application crashes, routers close BMP sessions
- On restart, routers reconnect and resend full route table
- **This is acceptable** - BMP protocol handles this naturally

### Malformed Messages
Log ERROR with context and continue processing:
```python
try:
    parsed = parse_bmp_message(data)
except BMPParseError as e:
    logger.error("malformed_message",
                 peer=peer_addr,
                 error=str(e),
                 data_hex=data[:256].hex())
    if sentry_enabled:
        sentry_sdk.capture_exception(e)
    continue  # Skip bad message, keep processing
```

### Database Unavailability
Simple retry with backoff:
```python
while True:
    try:
        await db_pool.execute(query, *params)
        break
    except ConnectionError:
        logger.warning("database_unavailable", retry_in=5)
        await asyncio.sleep(5)  # Simple retry every 5 seconds
```

If database is down for extended period, close BMP connections and exit. Routers will reconnect when service restarts.

## Sentry Integration
- Use Sentry logging to output logging to both Sentry and stdout
- Report peer up/down events as Sentry issues with trace and message context
- Report route processing errors as Sentry issues with trace and message context
- Allow complete disabling of Sentry via `.env` configuration

## Monitoring Through Logs

**Philosophy**: Start with structured logging. Add Prometheus metrics later if monitoring needs emerge.

Use structured JSON logging (structlog) for all monitoring. Log aggregation systems (Loki, CloudWatch, etc.) can parse these logs for dashboards.

### Structured Log Examples

**Peer connection tracking:**
```python
logger.info("peer_connected", peer=peer_addr, router_id=router_id)
logger.info("peer_disconnected", peer=peer_addr, duration_seconds=session_duration)
```

**Route processing stats (every 10 seconds):**
```python
logger.info("route_stats",
            peer=peer_addr,
            received=1523,
            processed=1520,
            ipv4=1245,
            ipv6=275,
            evpn=0,
            throughput_per_sec=152)
```

**Errors:**
```python
logger.error("parse_error",
             peer=peer_addr,
             message_type="route_monitoring",
             error=str(e),
             data_hex=data[:256].hex())
```

**Database operations:**
```python
logger.debug("database_copy",
             rows=1000,
             duration_ms=250,
             table="route_updates")
```

All logs output as JSON to stdout. Use log aggregation tools for analysis and alerting.

## Graceful Shutdown

**Purpose**: Preserve in-flight data and cleanly terminate all components when application is stopped.

**Signal Handling**:
- **SIGTERM** (Docker stop, Kubernetes pod termination): Graceful shutdown
- **SIGINT** (Ctrl+C): Graceful shutdown
- **SIGKILL** (kill -9, force kill): No cleanup possible, acceptable data loss

**Shutdown Procedure** (on receiving SIGTERM or SIGINT):

### Phase 1: Stop Accepting New Connections (Immediate)
- Close TCP listener (stop accepting new BMP connections)
- Existing BMP connections remain open
- Log INFO: "Shutdown initiated, stopping new connections"

### Phase 2: Drain Worker Queues (Max 30 seconds)
- Stop adding new messages to worker input queues
- Allow workers to process remaining messages in queue
- Monitor queue depth, wait for drain to zero
- Bulk writer continues flushing pending batches
- Timeout: 30 seconds maximum
- If timeout exceeded: Log WARNING "Shutdown timeout, forcing drain"

### Phase 3: Close BMP Peer Connections (After drain)
- Send TCP FIN to all active BMP peers
- Wait up to 5 seconds for graceful close
- Log INFO: "Closing {count} BMP peer connections"
- Routers will detect closure and reconnect on next application start

### Phase 4: Terminate Workers (After queues empty)
- Send SIGTERM (poison pill) to each worker process
- Wait up to 5 seconds for each worker to exit cleanly
- If worker doesn't exit: Send SIGKILL
- Log INFO: "Terminated {count} worker processes"

### Phase 5: Close Database Connections
- Flush connection pool (ensure all in-flight writes complete)
- Close all database connections gracefully
- Wait up to 5 seconds for close confirmation
- Log INFO: "Database connections closed"

### Phase 6: Exit
- Exit with code 0 (clean shutdown)
- Exit with code 1 if errors occurred during shutdown

**Shutdown Timeout**: 60 seconds total
- After 60 seconds: Force exit regardless of state
- Log WARNING: "Forced shutdown after 60 second timeout"
- Some in-flight data may be lost (acceptable)

**Implementation** (in `__main__.py`):
```python
import signal
import asyncio

class Application:
    def __init__(self):
        self.shutdown_event = asyncio.Event()
        self.tcp_server = None
        self.workers = []
        self.db_pool = None

    async def shutdown(self):
        """Gracefully shutdown application."""
        logger.info("shutdown_initiated")
        start_time = time.time()

        try:
            # Phase 1: Stop accepting connections (immediate)
            if self.tcp_server:
                self.tcp_server.close()
                await self.tcp_server.wait_closed()
                logger.info("tcp_listener_closed")

            # Phase 2: Drain worker queues (max 30 seconds)
            self.stop_queuing = True
            drain_timeout = 30
            while self.queue_depth() > 0 and time.time() - start_time < drain_timeout:
                await asyncio.sleep(0.1)

            remaining = self.queue_depth()
            if remaining > 0:
                logger.warning("shutdown_queue_not_empty", remaining=remaining)

            # Phase 3: Close BMP peer connections
            await self.close_all_peers()
            logger.info("bmp_peers_closed")

            # Phase 4: Terminate workers
            for worker in self.workers:
                self.worker_queue.put(None)  # Poison pill

            for worker in self.workers:
                worker.join(timeout=5.0)
                if worker.is_alive():
                    worker.terminate()
                    logger.warning("worker_force_terminated", pid=worker.pid)

            logger.info("workers_terminated", count=len(self.workers))

            # Phase 5: Close database connections
            if self.db_pool:
                await self.db_pool.close()
                logger.info("database_closed")

            # Phase 6: Exit
            elapsed = time.time() - start_time
            logger.info("shutdown_complete", elapsed_seconds=elapsed)
            return 0  # Success

        except Exception as e:
            logger.error("shutdown_error", error=str(e))
            return 1  # Error

def setup_signal_handlers(app):
    """Setup graceful shutdown signal handlers."""
    def signal_handler(sig, frame):
        logger.info("signal_received", signal=sig)
        app.shutdown_event.set()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

async def main():
    app = Application()
    setup_signal_handlers(app)

    try:
        # Run application
        await app.run()

        # Wait for shutdown signal
        await app.shutdown_event.wait()

        # Execute graceful shutdown
        exit_code = await app.shutdown()
        sys.exit(exit_code)

    except Exception as e:
        logger.critical("application_crash", error=str(e))
        sys.exit(1)
```

**Force Kill Behavior** (SIGKILL):
- No cleanup possible (signal cannot be caught)
- In-flight messages in worker queues: Lost
- Pending database writes: Lost (transactions roll back)
- BMP connections: Abruptly closed
- Routers will detect connection loss and reconnect
- Acceptable data loss: Routers will resend routes on reconnection
- Impact: ~10-30 seconds of route updates lost (small window)

**Testing Shutdown**:
- Test with `docker stop <container>` (sends SIGTERM with 10s grace period)
- Test with `kubectl delete pod <pod>` (sends SIGTERM with 30s grace period)
- Verify: Queue drains, workers terminate, connections close gracefully
- Verify: No database errors or orphaned connections

# Security

**Scope**: This is a trusted internal monitoring service, not a public-facing application.

## Security Model

This application relies on **network-level security**:
- Deploy in isolated management network (out-of-band recommended)
- Use firewall rules to restrict port 11019 to trusted router IPs
- BMP traffic is unencrypted (protocol limitation, acceptable for internal networks)
- No application-level authentication (BMP protocol has no auth mechanism)

## Basic Security Practices

**Database**:
- Use asyncpg parameterized queries (prevents SQL injection)
- Store credentials in `.env` with restricted permissions: `chmod 600 .env`
- Use standard PostgreSQL user permissions

**Container**:
- Run as non-root user in Dockerfile
- Use Dependabot for dependency updates

**Logging**:
- Never log passwords or sensitive credentials
- Log all connection attempts with source IP

**Assumptions**:
- Network firewall controls access to BMP port
- Management network is isolated from public internet
- Only authorized routers have network access
- Physical and network security managed externally

# Database Schema

**Philosophy**: Keep it simple. Denormalized storage is acceptable for a monitoring tool. Storage is cheap; developer time debugging joins isn't.

## Core Tables

### route_updates (TimescaleDB hypertable)
Primary table storing all route updates with full denormalization:

```sql
CREATE TABLE route_updates (
    time TIMESTAMPTZ NOT NULL,
    bmp_peer_ip INET NOT NULL,
    bmp_peer_asn INTEGER,
    bgp_peer_ip INET NOT NULL,
    bgp_peer_asn INTEGER,
    
    -- Route information
    family TEXT NOT NULL,  -- 'ipv4_unicast', 'ipv6_unicast', 'evpn'
    prefix CIDR,
    next_hop INET,
    as_path INTEGER[],
    communities TEXT[],
    med INTEGER,
    local_pref INTEGER,
    is_withdrawn BOOLEAN DEFAULT FALSE,
    
    -- EVPN-specific fields (NULL for IPv4/IPv6)
    evpn_route_type INTEGER,
    evpn_rd TEXT,
    evpn_esi TEXT,
    mac_address MACADDR,
    
    PRIMARY KEY (time, bmp_peer_ip, bgp_peer_ip, prefix)
);

-- Convert to hypertable with 1-week chunks
SELECT create_hypertable('route_updates', 'time', chunk_time_interval => INTERVAL '1 week');

-- 5-year retention policy
SELECT add_retention_policy('route_updates', INTERVAL '5 years');

-- Compress data older than 30 days
SELECT add_compression_policy('route_updates', INTERVAL '30 days');
```

### bmp_peers
Track BMP peer sessions:

```sql
CREATE TABLE bmp_peers (
    peer_ip INET PRIMARY KEY,
    router_id INET,
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);
```

### peer_events (TimescaleDB hypertable)
Log peer up/down events:

```sql
CREATE TABLE peer_events (
    time TIMESTAMPTZ NOT NULL,
    peer_ip INET NOT NULL,
    event_type TEXT NOT NULL,  -- 'peer_up', 'peer_down'
    reason_code INTEGER,
    PRIMARY KEY (time, peer_ip)
);

SELECT create_hypertable('peer_events', 'time');
SELECT add_retention_policy('peer_events', INTERVAL '6 months');
```

## Indexes

```sql
-- Route lookups
CREATE INDEX idx_route_prefix ON route_updates (prefix) WHERE prefix IS NOT NULL;
CREATE INDEX idx_route_family ON route_updates (family, time DESC);

-- EVPN lookups
CREATE INDEX idx_route_mac ON route_updates (mac_address) WHERE mac_address IS NOT NULL;
CREATE INDEX idx_route_evpn_rd ON route_updates (evpn_rd) WHERE evpn_rd IS NOT NULL;

-- AS path searches
CREATE INDEX idx_route_aspath ON route_updates USING GIN (as_path);

-- Peer lookups
CREATE INDEX idx_route_bmp_peer ON route_updates (bmp_peer_ip, time DESC);
CREATE INDEX idx_route_bgp_peer ON route_updates (bgp_peer_ip, time DESC);
```

## Storage Trade-offs

**Denormalized approach**:
- Routes stored every time they're seen (not deduplicated)
- ~500 bytes per route update
- 1.1M routes × 5 years ≈ 500GB per peer

**Cost**: ~$20/month for 500GB storage (commodity disk)
**Benefit**: 70% simpler code, no complex joins, easier to understand

## Example Queries

### Route churn analysis
```sql
SELECT prefix, COUNT(*) as updates, MAX(time) as last_change
FROM route_updates
WHERE time > NOW() - INTERVAL '1 hour'
GROUP BY prefix
HAVING COUNT(*) > 5
ORDER BY updates DESC
LIMIT 100;
```

### Find EVPN MAC routes
```sql
SELECT bmp_peer_ip, bgp_peer_ip, prefix, next_hop, mac_address, time
FROM route_updates
WHERE mac_address = '00:02:71:87:da:4d'
  AND is_withdrawn = FALSE
ORDER BY time DESC;
```

### Current routes by peer
```sql
SELECT DISTINCT ON (bgp_peer_ip, prefix)
    bgp_peer_ip, prefix, next_hop, as_path, time as last_seen
FROM route_updates
WHERE is_withdrawn = FALSE
ORDER BY bgp_peer_ip, prefix, time DESC;
```

# Backup and Disaster Recovery

**Purpose**: Ensure data can be recovered after hardware failure, corruption, or accidental deletion while maintaining acceptable Recovery Time Objective (RTO) and Recovery Point Objective (RPO).

**Deployment Model**: All data locally hosted (no cloud storage dependencies)

## Backup Strategy

### Regular Backups

**Daily Full Backups**:
- **Method**: PostgreSQL `pg_dump` with custom format
- **Schedule**: Daily at 02:00 UTC (low-traffic period)
- **Retention**: 30 days of daily backups
- **Storage**: Local disk or network-attached storage (NAS)
- **Compression**: Custom format includes compression automatically
- **Location**: `/var/backups/pybmpmon/` or mounted NFS/CIFS share

**Command**:
```bash
pg_dump -h $DB_HOST -U $DB_USER -d bmpmon \
  --format=custom \
  --compress=9 \
  --file=/var/backups/pybmpmon/bmpmon-$(date +%Y%m%d).dump
```

**Weekly TimescaleDB Compressed Chunks**:
- **Method**: Export compressed chunks separately for faster incremental backups
- **Schedule**: Weekly on Sunday at 03:00 UTC
- **Retention**: 12 weeks (3 months)
- **Purpose**: Faster recovery of older data, smaller backup size

### Backup Automation

**Implementation** (in `scripts/backup.sh`):
```bash
#!/bin/bash
set -e

BACKUP_DIR="/var/backups/pybmpmon"
DATE=$(date +%Y%m%d)
RETENTION_DAYS=30

# Create backup directory if it doesn't exist
mkdir -p $BACKUP_DIR

# Full backup
pg_dump -h $DB_HOST -U $DB_USER -d bmpmon \
  --format=custom \
  --compress=9 \
  --file=$BACKUP_DIR/bmpmon-$DATE.dump

# Verify backup was created
if [ ! -f $BACKUP_DIR/bmpmon-$DATE.dump ]; then
  echo "ERROR: Backup file not created"
  exit 1
fi

# Check backup file size (should be > 1MB for non-empty database)
FILESIZE=$(stat -f%z "$BACKUP_DIR/bmpmon-$DATE.dump" 2>/dev/null || stat -c%s "$BACKUP_DIR/bmpmon-$DATE.dump")
if [ $FILESIZE -lt 1048576 ]; then
  echo "WARNING: Backup file size suspiciously small: $FILESIZE bytes"
fi

# Delete old backups (older than retention period)
find $BACKUP_DIR -name "bmpmon-*.dump" -type f -mtime +$RETENTION_DAYS -delete

echo "Backup completed: bmpmon-$DATE.dump ($FILESIZE bytes)"
echo "Backups retained: $(ls -1 $BACKUP_DIR/bmpmon-*.dump | wc -l)"
```

**Cron Schedule**:
```cron
# Daily backup at 02:00 UTC
0 2 * * * /usr/local/bin/backup.sh >> /var/log/pybmpmon-backup.log 2>&1

# Weekly compressed chunks backup at 03:00 UTC on Sundays
0 3 * * 0 /usr/local/bin/backup-chunks.sh >> /var/log/pybmpmon-backup.log 2>&1
```

**Docker Volume Backup**:
```yaml
# In docker-compose.yml
volumes:
  postgres_data:
  backups:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /var/backups/pybmpmon  # Host directory

services:
  backup:
    image: postgres:16
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - backups:/backups
    environment:
      - PGHOST=postgres
      - PGUSER=bmpmon
      - PGPASSWORD=${DB_PASSWORD}
    command: |
      bash -c "
      while true; do
        pg_dump -h postgres -U bmpmon -d bmpmon \
          --format=custom --compress=9 \
          --file=/backups/bmpmon-\$(date +%Y%m%d-%H%M%S).dump
        sleep 86400  # 24 hours
      done
      "
```

### Point-in-Time Recovery (PITR)

**WAL Archiving Configuration**:
```sql
-- In postgresql.conf
wal_level = replica
archive_mode = on
archive_command = 'test ! -f /var/backups/pybmpmon/wal/%f && cp %p /var/backups/pybmpmon/wal/%f'
archive_timeout = 300  # 5 minutes
```

**WAL Retention**: 7 days
- Allows recovery to any point in the last 7 days
- Stored locally in `/var/backups/pybmpmon/wal/`

**WAL Cleanup Script**:
```bash
#!/bin/bash
# Clean up WAL files older than 7 days
find /var/backups/pybmpmon/wal/ -type f -mtime +7 -delete
```

## Disaster Recovery

### Recovery Objectives

**Recovery Time Objective (RTO)**: 1 hour
- Time from disaster detection to application fully operational
- Includes database restore, application restart, router reconnection

**Recovery Point Objective (RPO)**: 24 hours
- Maximum acceptable data loss (daily backup frequency)
- Acceptable because routers will resend full route tables on reconnection
- Historical churn analysis may have gaps

### Recovery Procedure

**Scenario**: Complete database server failure or corruption

**Step 1: Assess Damage** (5 minutes)
- Verify database is truly unavailable (not transient network issue)
- Check last successful backup: `ls -lh /var/backups/pybmpmon/bmpmon-*.dump`
- Estimate data loss window (time since last backup)

**Step 2: Stop Application** (2 minutes)
```bash
docker-compose stop pybmpmon
# or
systemctl stop pybmpmon
```

**Step 3: Restore Database** (20-40 minutes, depending on data size)
```bash
# Option 1: Restore to existing database (destructive)
dropdb -h localhost -U postgres bmpmon
createdb -h localhost -U postgres bmpmon

# Option 2: Restore to new database (safer)
createdb -h localhost -U postgres bmpmon_new

# Restore from backup
pg_restore -h localhost -U postgres -d bmpmon \
  --clean \
  --if-exists \
  --no-owner \
  --jobs=4 \
  /var/backups/pybmpmon/bmpmon-20250929.dump

# Verify restore
psql -h localhost -U postgres -d bmpmon -c "
  SELECT
    'routes' as table_name, count(*) as row_count FROM routes
  UNION ALL
  SELECT 'route_observations', count(*) FROM route_observations
  UNION ALL
  SELECT 'bmp_peers', count(*) FROM bmp_peers;
"
```

**Step 4: Apply WAL Files (Optional PITR)** (5-10 minutes)
```bash
# If you need to recover to specific point in time
# Create recovery.conf or recovery.signal (PostgreSQL 12+)
cat > /var/lib/postgresql/data/recovery.signal << EOF
restore_command = 'cp /var/backups/pybmpmon/wal/%f %p'
recovery_target_time = '2025-09-29 14:30:00 UTC'
EOF

# Start PostgreSQL, it will apply WAL files
# Then promote to primary when recovery complete
```

**Step 5: Start Application** (3 minutes)
```bash
docker-compose up -d pybmpmon
# or
systemctl start pybmpmon

# Verify health
curl http://localhost:9090/health/ready
```

**Step 6: Verify Router Reconnection** (5-10 minutes)
- Monitor logs: `docker-compose logs -f pybmpmon`
- Verify routers reconnect automatically
- Confirm routes being received: Check metrics or database
- Monitor: `curl http://localhost:9090/metrics | grep pybmpmon_active_peers`

**Total RTO**: ~45-60 minutes (within 1 hour objective)

### Data Loss Analysis

**What is Lost**:
- Route updates between last backup and failure (up to 24 hours)
- In-flight messages in worker queues (~1000-5000 routes)
- Churn events during outage window

**What is NOT Lost**:
- Current routing state (routers resend full tables on reconnection)
- BMP peer relationships (reestablished automatically)
- Long-term route history (from backup)

**Acceptable Impact**:
- Route churn analysis may show gaps for outage period
- Historical queries may miss data from outage window
- No impact on current network state visibility (routers provide current state)

## Backup Testing

### Monthly Restore Test

**Purpose**: Verify backups are restorable and complete

**Procedure** (monthly, first Sunday at 04:00 UTC):
```bash
#!/bin/bash
# Monthly backup test

# 1. Find latest backup
LATEST_BACKUP=$(ls -t /var/backups/pybmpmon/bmpmon-*.dump | head -1)

# 2. Create test database
psql -h localhost -U postgres -c "DROP DATABASE IF EXISTS bmpmon_test;"
psql -h localhost -U postgres -c "CREATE DATABASE bmpmon_test;"

# 3. Restore to test database
pg_restore -h localhost -U postgres -d bmpmon_test \
  --clean \
  --if-exists \
  --no-owner \
  --jobs=4 \
  $LATEST_BACKUP

# 4. Verify data integrity
psql -h localhost -U postgres -d bmpmon_test -c "
  SELECT
    (SELECT count(*) FROM routes) as route_count,
    (SELECT count(*) FROM route_observations) as observation_count,
    (SELECT count(*) FROM bmp_peers) as peer_count;
"

# 5. Check for corruption
vacuumdb -h localhost -U postgres --analyze --verbose bmpmon_test

# 6. Run sample queries from documentation
psql -h localhost -U postgres -d bmpmon_test -f /opt/pybmpmon/tests/sample_queries.sql

# 7. Cleanup test database
psql -h localhost -U postgres -c "DROP DATABASE bmpmon_test;"

# 8. Report results
echo "Backup test completed successfully on $(date)" | tee -a /var/log/pybmpmon-backup-test.log
```

**Success Criteria**:
- Restore completes without errors
- Row counts match expected values (within 5% of production)
- Sample queries return results
- No database corruption detected

**Failure Handling**:
- Log error to `/var/log/pybmpmon-backup-test.log`
- Send alert (email, Slack, PagerDuty)
- Investigate backup process immediately
- May need to restore from older backup

## Backup Monitoring

### Backup Success Tracking

**Log-Based Monitoring**:
```bash
# In backup.sh, log to structured format
echo "{\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"status\":\"success\",\"size\":$FILESIZE,\"file\":\"bmpmon-$DATE.dump\"}" | tee -a /var/log/pybmpmon-backup.json
```

**Prometheus Metrics** (if using node_exporter textfile collector):
```bash
# In backup.sh, export metrics to textfile
cat > /var/lib/node_exporter/textfile_collector/pybmpmon_backup.prom << EOF
# HELP pybmpmon_backup_success Last backup success (1=success, 0=failure)
# TYPE pybmpmon_backup_success gauge
pybmpmon_backup_success 1
# HELP pybmpmon_backup_size_bytes Backup file size in bytes
# TYPE pybmpmon_backup_size_bytes gauge
pybmpmon_backup_size_bytes $FILESIZE
# HELP pybmpmon_backup_timestamp_seconds Backup completion timestamp
# TYPE pybmpmon_backup_timestamp_seconds gauge
pybmpmon_backup_timestamp_seconds $(date +%s)
EOF
```

**Alerting Rules**:
```yaml
groups:
  - name: pybmpmon_backups
    rules:
      - alert: BMPBackupFailed
        expr: pybmpmon_backup_success == 0
        for: 30m
        labels:
          severity: critical
        annotations:
          summary: "Daily backup failed"

      - alert: BMPBackupOld
        expr: time() - pybmpmon_backup_timestamp_seconds > 86400 * 1.5  # 36 hours
        for: 1h
        labels:
          severity: critical
        annotations:
          summary: "No successful backup in 36 hours"
```

## Storage Management

### Backup Storage Sizing

**Estimate for 5 BMP peers over 30 days**:
- Full database size: ~550GB (5 peers × 110GB)
- Compressed backup: ~100-150GB (5-7x compression ratio)
- Daily backups (30 days): ~3-4.5TB
- Weekly compressed chunks (12 weeks): ~1.2-1.8TB
- WAL archives (7 days): ~50-100GB
- **Total local storage needed**: ~4.3-6.4TB

**Storage Recommendations**:
- Use dedicated disk/volume for backups (separate from database)
- Mount network storage (NFS, CIFS) for centralized backup location
- Consider RAID for backup volume (protect against disk failure)
- Monitor disk usage: Alert at 80% full

### Cleanup Policy

**Automated Cleanup** (in backup.sh):
```bash
# Daily backups: Keep 30 days
find $BACKUP_DIR -name "bmpmon-*.dump" -type f -mtime +30 -delete

# Weekly backups: Keep 12 weeks
find $BACKUP_DIR -name "bmpmon-weekly-*.dump" -type f -mtime +84 -delete

# WAL archives: Keep 7 days
find $BACKUP_DIR/wal/ -type f -mtime +7 -delete

# Log cleanup actions
echo "Cleanup: Deleted backups older than $RETENTION_DAYS days" >> /var/log/pybmpmon-backup.log
```

### Offsite Backup Copy

**Recommendation**: Copy backups to secondary location for disaster recovery

**Options**:
1. **Network Storage**: Mount NFS/CIFS share from different physical location
2. **Rsync to Remote Server**:
   ```bash
   rsync -avz --delete /var/backups/pybmpmon/ backup-server:/backups/pybmpmon/
   ```
3. **USB Hard Drive**: Periodic manual copy for air-gapped backup
4. **Secondary Database Server**: PostgreSQL streaming replication (real-time copy)

## Security Considerations

**Backup Encryption** (optional, if backups stored on shared storage):
```bash
# Encrypt backup before writing
pg_dump ... | gpg --encrypt --recipient backup@company.com > bmpmon-$DATE.dump.gpg

# Decrypt for restore
gpg --decrypt bmpmon-$DATE.dump.gpg | pg_restore ...
```

**Access Control**:
- Backup directory permissions: `chmod 700 /var/backups/pybmpmon`
- Owner: Database service account or backup user only
- No world-readable backups (contain routing data)

**Backup Integrity**:
- Generate checksums: `sha256sum bmpmon-$DATE.dump > bmpmon-$DATE.dump.sha256`
- Verify before restore: `sha256sum -c bmpmon-$DATE.dump.sha256`

# Development Workflow

## Testing Strategy

**Philosophy**: Focus testing effort where it matters most. This is a single-purpose monitoring tool—test protocol parsing rigorously, verify the happy path works, then deploy to a test router.

### Test Coverage Requirements

**Coverage Target**: 60% overall
- **Critical paths** (100% coverage required):
  - protocol/bmp_parser.py (BMP message parsing)
  - protocol/bgp_parser.py (BGP route parsing)
- **Everything else**: Best effort

**Coverage validation**:
```bash
pytest --cov=src/pybmpmon --cov-report=term-missing --cov-fail-under=60
```

### Unit Testing

**Priority**: Protocol parsing correctness (RFC7854 compliance)

**What to test**:
- Each BMP message type (Initiation, Termination, Peer Up/Down, Route Monitoring, Statistics)
- Each BGP route type (IPv4 unicast, IPv6 unicast, EVPN)
- BGP path attributes (AS_PATH, NEXT_HOP, COMMUNITIES, MED, LOCAL_PREF)
- Malformed messages (truncated, invalid lengths)
- Edge cases (zero-length AS paths, max attribute sizes)

**Test data**: Binary fixtures in `tests/fixtures/bmp_messages/`
- Captured from real routers (sanitized)
- RFC7854 example messages

**Example tests**:
```python
# tests/unit/test_bmp_parser.py
def test_parse_peer_up_message():
    """Test BMP Peer Up message parsing."""
    data = load_fixture("peer_up_ipv4.bin")
    msg = parse_bmp_message(data)

    assert msg.type == BMPMessageType.PEER_UP
    assert msg.peer_address == "192.0.2.1"
    assert msg.peer_asn == 65000

def test_parse_truncated_message():
    """Test truncated message handling."""
    data = b"\x03\x00\x00\x00\x10"  # Header only
    with pytest.raises(BMPParseError, match="Truncated"):
        parse_bmp_message(data)

@pytest.mark.parametrize("data,error", [
    (b"\x03", "Message too short"),
    (b"\x03\xff\x00\x00\x05", "Invalid BMP version"),
])
def test_malformed_messages(data, error):
    with pytest.raises(BMPParseError, match=error):
        parse_bmp_message(data)
```

### Integration Testing

**Priority**: One happy path test proving the entire flow works

**Happy path test**:
```python
# tests/integration/test_end_to_end.py
async def test_bmp_message_to_database(db_pool):
    """Test complete flow: TCP → Parse → Database."""
    # 1. Connect BMP peer
    reader, writer = await asyncio.open_connection('localhost', 11019)

    # 2. Send Initiation message
    writer.write(create_bmp_initiation())
    await writer.drain()

    # 3. Send Peer Up
    writer.write(create_bmp_peer_up("192.0.2.1", 65000))
    await writer.drain()

    # 4. Send 100 Route Monitoring messages
    for i in range(100):
        writer.write(create_route_monitoring(f"10.{i}.0.0/16"))
        await writer.drain()

    # 5. Wait for processing
    await asyncio.sleep(2)

    # 6. Verify routes in database
    async with db_pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM route_updates")
        assert count == 100
```

**Database tests**: Use `testcontainers-python` for PostgreSQL/TimescaleDB
```python
# tests/integration/conftest.py
import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("timescale/timescaledb:latest-pg16") as pg:
        yield pg

@pytest.fixture
async def db_pool(postgres_container):
    pool = await asyncpg.create_pool(postgres_container.get_connection_url())
    yield pool
    await pool.close()
```

### Performance Testing

**Priority**: Basic throughput validation

**Single test**: Verify we can process 15k+ routes/sec
```python
# tests/performance/test_throughput.py
async def test_route_throughput():
    """Verify 15k+ routes/sec throughput."""
    start = time.time()

    # Send 50k routes
    for i in range(50_000):
        await send_route_monitoring(f"10.{i>>8}.{i&0xff}.0/24")

    await wait_for_processing_complete()

    elapsed = time.time() - start
    throughput = 50_000 / elapsed

    assert throughput >= 15_000, f"Got {throughput:.0f} routes/sec"
```

### Manual Testing

**After deployment**: Connect to real test router
1. Configure router to send BMP traffic to pybmpmon
2. Verify routes appear in database
3. Check logs for errors
4. Run example queries from docs

## Testing Framework

**Required packages**:
```toml
[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-asyncio = "^0.23"
pytest-cov = "^4.1"
testcontainers = "^4.0"
asyncpg = "^0.29"
```

**Test execution**:
```bash
# Run all tests
pytest

# With coverage
pytest --cov=src/pybmpmon --cov-report=html

# Only unit tests (fast)
pytest tests/unit

# Integration tests
pytest tests/integration

# Performance test
pytest tests/performance
```

## Code Quality

**Formatting**: black + isort
```bash
black src/ tests/
isort src/ tests/
```

**Linting**: ruff
```bash
ruff check src/ tests/
```

**Type checking**: mypy
```bash
mypy src/
```

**Pre-commit checks**:
```bash
# Format
black src/ tests/ && isort src/ tests/

# Lint
ruff check src/ tests/

# Type check
mypy src/

# Test
pytest --cov=src/pybmpmon --cov-fail-under=60
```

## CI/CD Pipeline

**GitHub Actions** - single workflow for PRs and main:

```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          pip install poetry
          poetry install

      - name: Format check
        run: |
          poetry run black --check src/ tests/
          poetry run isort --check src/ tests/

      - name: Lint
        run: poetry run ruff check src/ tests/

      - name: Type check
        run: poetry run mypy src/

      - name: Test
        run: poetry run pytest --cov=src/pybmpmon --cov-fail-under=60

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        if: matrix.python-version == '3.12'

  build:
    runs-on: ubuntu-latest
    needs: test
    if: github.ref == 'refs/heads/main'

    steps:
      - uses: actions/checkout@v4

      - name: Build and push Docker image
        run: |
          echo "${{ secrets.GITHUB_TOKEN }}" | docker login ghcr.io -u ${{ github.actor }} --password-stdin
          docker build -t ghcr.io/${{ github.repository }}:latest .
          docker push ghcr.io/${{ github.repository }}:latest
```

**Dependabot**:
```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
```
# Implementation Strategy

Break this project into complete, self-contained phases:

## Project Structure

```
pybmpmon/
├── pyproject.toml              # Poetry configuration
├── .env.example                # Template configuration
├── docker-compose.yml
├── Dockerfile
├── README.md
├── mkdocs.yml
├── .github/
│   └── workflows/
│       └── ci.yml              # Single CI workflow
├── docs/                       # MkDocs documentation
│   ├── index.md
│   ├── installation.md
│   ├── configuration.md
│   └── queries.md
├── src/
│   └── pybmpmon/
│       ├── __init__.py
│       ├── __main__.py         # Entry point
│       ├── config.py           # Pydantic settings from .env
│       ├── listener.py         # Asyncio TCP server
│       ├── protocol/
│       │   ├── __init__.py
│       │   ├── bmp.py          # BMP message types
│       │   ├── bmp_parser.py   # BMP parsing logic
│       │   ├── bgp.py          # BGP message types
│       │   └── bgp_parser.py   # BGP UPDATE parsing
│       ├── models/
│       │   ├── __init__.py
│       │   ├── bmp_peer.py     # Pydantic models
│       │   └── route.py
│       ├── database/
│       │   ├── __init__.py
│       │   ├── connection.py   # asyncpg pool management
│       │   ├── schema.py       # Table definitions
│       │   ├── migrations/     # SQL migration files
│       │   │   ├── 001_initial.sql
│       │   │   └── 002_indexes.sql
│       │   ├── operations.py   # CRUD operations
│       │   └── batch_writer.py # Bulk COPY writer
│       ├── monitoring/
│       │   ├── __init__.py
│       │   ├── logger.py       # Structured logging + Sentry
│       │   └── stats.py        # Statistics collector
│       └── utils/
│           ├── __init__.py
│           └── binary.py       # Binary parsing helpers
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Pytest fixtures
│   ├── unit/
│   │   ├── test_bmp_parser.py
│   │   ├── test_bgp_parser.py
│   │   └── test_models.py
│   ├── integration/
│   │   ├── test_end_to_end.py
│   │   └── test_database.py
│   ├── performance/
│   │   └── test_throughput.py
│   └── fixtures/
│       └── bmp_messages/       # Binary test data
└── scripts/
    └── init_db.py              # Database initialization
```

## Phase 1: Core BMP Listener
**Success Criteria**: TCP listener accepts connections on port 11019 and parses basic BMP headers

- Set up project structure (src/, tests/, docker/) per structure above
- Create pyproject.toml with dependencies (asyncio, asyncpg, pydantic, structlog, sentry-sdk)
- Implement Pydantic config.py for .env settings (fail fast on misconfiguration)
- Implement asyncio TCP listener on port 11019 (listener.py)
- Parse BMP common header (RFC7854 Section 4.1) in protocol/bmp_parser.py
- Setup structured logging with structlog (monitoring/logger.py)
- Create Dockerfile with Python 3.11+ base image, non-root user
- Unit tests for BMP header parsing with pytest (60% coverage target)
- Format with black, lint with ruff, type-check with mypy

## Phase 2: BMP Message Parsing
**Success Criteria**: All RFC7854 message types decoded correctly with test coverage

- Implement parsers for all BMP message types in protocol/bmp_parser.py:
  - Initiation messages
  - Termination messages
  - Peer Up Notifications
  - Peer Down Notifications
  - Route Monitoring messages
  - Statistics Reports
- Comprehensive unit tests with binary fixtures from real routers
- Test malformed messages (truncated, invalid lengths, unknown types)
- Test edge cases (zero-length fields, maximum sizes)

## Phase 3: Database Foundation
**Success Criteria**: TimescaleDB schema created, basic CRUD operations working

- Docker Compose with PostgreSQL + TimescaleDB (timescale/timescaledb:latest-pg16)
- Create migration files in database/migrations/:
  - 001_initial.sql: Create tables (route_updates, bmp_peers, peer_events)
  - 002_hypertables.sql: Convert to hypertables with retention policies
  - 003_indexes.sql: Create all indexes (prefix, family, AS path GIN, peer lookups)
- Implement asyncpg connection pool in database/connection.py (5-10 connections)
- Create Pydantic models in models/:
  - models/bmp_peer.py: BMP peer state
  - models/route.py: Route update data
- Basic CRUD operations in database/operations.py (parameterized queries only)
- Add database configuration to .env (host, port, user, password)
- Integration tests with testcontainers

## Phase 4: BGP Route Parsing
**Success Criteria**: Parse IPv4/IPv6/EVPN routes with all attributes

- Implement BGP UPDATE message parsing in protocol/bgp_parser.py
- Support for IPv4 unicast (AFI=1, SAFI=1)
- Support for IPv6 unicast (AFI=2, SAFI=1)
- Support for EVPN routes (AFI=25, SAFI=70)
- Parse all BGP path attributes:
  - AS_PATH, NEXT_HOP, COMMUNITIES, MED, LOCAL_PREF
  - EVPN-specific: RD, ESI, MAC address
- Unit tests for each route type with binary fixtures
- Test edge cases (empty AS paths, maximum attribute lengths)

## Phase 5: Batch Processing
**Success Criteria**: 15k+ routes/sec throughput with asyncio batching

- Implement BatchWriter class in database/batch_writer.py:
  - Accumulate routes in memory (list of dicts)
  - Batch size: 1,000 routes
  - Batch timeout: 500ms maximum wait
  - Flush on batch full or timeout
  - Use asyncpg connection.copy_records_to_table()
- Update listener.py to:
  - Parse BMP/BGP messages inline (no separate workers)
  - Add parsed routes to batch accumulator
  - Handle state messages (Peer Up/Down) immediately
- Simple error recovery: Log error, skip bad message, continue
- Performance test: Verify 15k+ routes/sec throughput
- Integration test: Send 50k routes, verify all in database

## Phase 6: Peer and Route Tracking
**Success Criteria**: Database accurately reflects current state of peers and routes

- Track BMP peer sessions:
  - Insert/update bmp_peers table on Peer Up
  - Update last_seen timestamp on every message
  - Mark is_active=false on Peer Down
- Insert peer_events records for all Peer Up/Down events
- Track route withdrawals (is_withdrawn=true in route_updates)
- Log structured events:
  - "peer_connected" with peer IP and router ID
  - "peer_disconnected" with duration
  - "route_stats" every 10 seconds (received, processed, by family)

## Phase 7: Monitoring and Logging
**Success Criteria**: 10-second statistics logs, DEBUG mode dumps packets

- Implement stats.py:
  - Per-peer counters (routes received, processed, by family)
  - Periodic logging every 10 seconds using asyncio.create_task()
  - Calculate throughput (routes/sec)
- Structured logging examples:
  - INFO: peer_connected, peer_disconnected, route_stats
  - DEBUG: bmp_message_received with hex dump
  - ERROR: parse_error with context
- All logs as JSON to stdout (structlog)

## Phase 8: Sentry Integration
**Success Criteria**: Issues appear in Sentry with proper context, can be disabled

- Update monitoring/logger.py with Sentry SDK integration:
  - Initialize sentry_sdk only if SENTRY_DSN is set in .env
  - Configure LoggingIntegration (INFO level, ERROR events)
  - Set environment and traces_sample_rate from .env
- Add .env variables:
  - SENTRY_DSN (optional, empty = disabled)
  - SENTRY_ENVIRONMENT (default: "production")
  - SENTRY_TRACES_SAMPLE_RATE (default: 0.1)
- Report errors as Sentry issues with context:
  - Peer IP, message type, error details
  - First 256 bytes of message data (hex)
- Test with Sentry disabled (should work normally)
- Test with Sentry enabled (verify issues appear)

## Phase 9: Documentation
**Success Criteria**: Complete MkDocs site with installation, configuration, and example queries

- Setup mkdocs.yml with material theme
- Write documentation:
  - docs/index.md: Overview and architecture
  - docs/installation.md: Docker Compose setup
  - docs/configuration.md: .env file options, Sentry setup
  - docs/queries.md: Example SQL queries (route churn, EVPN MAC lookup, current routes)
- Include example log output (JSON format)
- Add troubleshooting section (common issues)

## Phase 10: CI/CD and Release
**Success Criteria**: GitHub Actions runs tests/lint, builds container, publishes to GHCR

- Initialize git repository
- Create .github/workflows/ci.yml:
  - Run tests, format check, lint, type check
  - Test on Python 3.11, 3.12, 3.13
  - Build and push Docker image to GHCR on main branch
- Create .github/dependabot.yml (weekly pip updates)
- Create .env.example with all configuration options
- Tag v1.0.0 release

# Important Constraints

## What TO Do
- Complete each feature fully in one session before moving to the next
- Utilize subagents as necessary to research and expand on complex topics
- Ensure all tests pass after every change
- Follow RFC7854 specifications exactly

## What NOT To Do
- Do not partially implement features across multiple sessions
- Do not create Grafana dashboard or visualization tools yet
- Do not add features not specified in this document
- Do not skip test coverage
- Do not hardcode configuration values (use `.env`)

# Notes for Claude

When working on this project:
1. Each prompt should fully complete a feature from one phase
2. Context will be lost between prompts, so avoid partial implementations
3. Always run tests after making changes
4. Always run formatting/linting after making changes
5. Use subagents when deep research is needed (e.g., RFC7854 message format details)