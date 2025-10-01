# Troubleshooting

This guide covers common issues and their solutions when running pybmpmon.

## Quick Diagnostics

### Check Service Health

```bash
# Check if services are running
docker-compose ps

# Check BMP port
nc -z localhost 11019 && echo "BMP port OK" || echo "BMP port FAILED"

# Check database
docker-compose exec postgres pg_isready

# View recent logs
docker-compose logs --tail=100 pybmpmon

# Check for errors
docker-compose logs pybmpmon | grep -i error
```

### Common Log Messages

**Successful startup:**
```json
{"event": "bmp_listener_started", "level": "INFO", "host": "0.0.0.0", "port": 11019}
{"event": "sentry_initialized", "level": "INFO", "environment": "production"}
```

**Router connected:**
```json
{"event": "peer_connected", "level": "INFO", "peer": "192.0.2.1"}
```

**Routes being processed:**
```json
{"event": "route_stats", "level": "INFO", "peer": "192.0.2.1", "received": 1523, "processed": 1520}
```

## Installation Issues

### Docker Compose Won't Start

**Symptom:** `docker-compose up` fails

**Causes and Solutions:**

1. **Missing .env file**
   ```bash
   # Error: "DATABASE_PASSWORD is not set"
   # Solution: Create .env file
   cp .env.example .env
   vim .env  # Edit with your settings
   ```

2. **Port already in use**
   ```bash
   # Error: "bind: address already in use"
   # Check what's using port 11019
   lsof -i :11019
   # Kill the process or change BMP_LISTEN_PORT in .env
   ```

3. **Insufficient permissions**
   ```bash
   # Error: "Permission denied"
   # Solution: Add user to docker group
   sudo usermod -aG docker $USER
   # Log out and back in
   ```

### Container Exits Immediately

**Symptom:** `docker-compose ps` shows exited container

**Diagnosis:**
```bash
# View exit logs
docker-compose logs pybmpmon

# Common causes:
# - Configuration error
# - Database connection failure
# - Python import error
```

**Solutions:**

1. **Configuration validation failed**
   ```bash
   # Check configuration
   docker-compose run --rm pybmpmon python -c "from pybmpmon.config import settings; print(settings)"
   ```

2. **Database not ready**
   ```bash
   # Wait for database to start
   docker-compose up -d postgres
   sleep 10
   docker-compose up -d pybmpmon
   ```

## Database Issues

### Cannot Connect to Database

**Symptom:** `ConnectionRefusedError` or timeout

**Diagnosis:**
```bash
# Check if PostgreSQL is running
docker-compose ps postgres

# Check database logs
docker-compose logs postgres

# Test connection
docker-compose exec postgres psql -U bmpmon -d bmpmon
```

**Solutions:**

1. **Database not started**
   ```bash
   docker-compose up -d postgres
   ```

2. **Wrong credentials**
   ```bash
   # Verify credentials in .env match database
   docker-compose exec postgres psql -U bmpmon -d bmpmon
   # If fails, reset password:
   docker-compose exec postgres psql -U postgres -c "ALTER USER bmpmon WITH PASSWORD 'newpassword';"
   ```

3. **Network issue**
   ```bash
   # Verify containers on same network
   docker network inspect pybmpmon_default

   # Test connectivity
   docker-compose exec pybmpmon ping postgres
   ```

### Database Schema Not Created

**Symptom:** `relation "route_updates" does not exist`

**Solution:**
```bash
# Run database initialization
docker-compose exec postgres psql -U bmpmon -d bmpmon -f /docker-entrypoint-initdb.d/01_init.sql

# Or recreate database
docker-compose down -v
docker-compose up -d
```

### Database Fills Up Disk

**Symptom:** `No space left on device`

**Diagnosis:**
```bash
# Check database size
docker-compose exec postgres psql -U bmpmon -d bmpmon -c "
SELECT pg_size_pretty(pg_database_size('bmpmon'));
"

# Check table sizes
docker-compose exec postgres psql -U bmpmon -d bmpmon -c "
SELECT tablename, pg_size_pretty(pg_total_relation_size(tablename::text))
FROM pg_tables WHERE schemaname = 'public';
"

# Check disk usage
docker-compose exec postgres df -h
```

**Solutions:**

1. **Enable compression** (if not already enabled)
   ```sql
   -- Compress data older than 30 days
   SELECT add_compression_policy('route_updates', INTERVAL '30 days');
   ```

2. **Reduce retention**
   ```sql
   -- Change retention from 5 years to 1 year
   SELECT remove_retention_policy('route_updates');
   SELECT add_retention_policy('route_updates', INTERVAL '1 year');
   ```

3. **Vacuum database**
   ```bash
   docker-compose exec postgres vacuumdb -U bmpmon -d bmpmon --analyze --verbose
   ```

## BMP Listener Issues

### BMP Port Not Accessible

**Symptom:** Routers can't connect to port 11019

**Diagnosis:**
```bash
# Check if port is listening
nc -z localhost 11019

# Check from remote host
nc -z <pybmpmon-ip> 11019

# View firewall rules (Linux)
sudo iptables -L -n | grep 11019
```

**Solutions:**

1. **Firewall blocking**
   ```bash
   # Allow BMP port (Linux)
   sudo iptables -A INPUT -p tcp --dport 11019 -j ACCEPT

   # Allow BMP port (macOS)
   # Add rule in System Preferences > Security & Privacy > Firewall
   ```

2. **Docker port mapping issue**
   ```bash
   # Verify port mapping in docker-compose.yml
   ports:
     - "11019:11019"

   # Check actual port mapping
   docker port pybmpmon
   ```

3. **Listening on wrong interface**
   ```bash
   # Ensure BMP_LISTEN_HOST=0.0.0.0 in .env
   # Not 127.0.0.1 (localhost only)
   ```

### No Routes Received

**Symptom:** Database empty after router connects

**Diagnosis:**
```bash
# Check if peer connected
docker-compose exec postgres psql -U bmpmon -d bmpmon -c "SELECT * FROM bmp_peers;"

# Check for route updates
docker-compose exec postgres psql -U bmpmon -d bmpmon -c "SELECT COUNT(*) FROM route_updates;"

# View DEBUG logs
# Set LOG_LEVEL=DEBUG in .env and restart
docker-compose logs -f pybmpmon
```

**Solutions:**

1. **Router not configured correctly**
   - Verify BMP configuration on router
   - Check router logs for BMP connection status
   - Ensure router is sending route-monitoring messages

2. **Parse errors**
   ```bash
   # Check for parse errors in logs
   docker-compose logs pybmpmon | grep -i "parse_error"

   # View error details in DEBUG mode
   # Set LOG_LEVEL=DEBUG in .env
   ```

3. **Batch writer not flushing**
   ```bash
   # Routes may be buffered, wait 10 seconds
   # Or check batch writer stats in logs
   docker-compose logs pybmpmon | grep batch
   ```

## Performance Issues

### High CPU Usage

**Symptom:** Container using 100% CPU

**Diagnosis:**
```bash
# Monitor CPU usage
docker stats pybmpmon

# Check route throughput in logs
docker-compose logs pybmpmon | grep route_stats
```

**Solutions:**

1. **Too many concurrent connections**
   ```bash
   # Check number of BMP peers
   docker-compose exec postgres psql -U bmpmon -d bmpmon -c "SELECT COUNT(*) FROM bmp_peers WHERE is_active = TRUE;"

   # Limit BMP peers if necessary
   ```

2. **DEBUG logging overhead**
   ```bash
   # Change LOG_LEVEL to INFO in .env
   LOG_LEVEL=INFO
   docker-compose restart pybmpmon
   ```

3. **Slow database writes**
   ```bash
   # Check database performance
   docker stats postgres

   # Increase connection pool
   DATABASE_POOL_MAX_SIZE=20  # in .env
   ```

### High Memory Usage

**Symptom:** Container using excessive RAM

**Diagnosis:**
```bash
# Monitor memory usage
docker stats pybmpmon

# Check for memory leaks
# Restart and monitor growth over time
docker-compose restart pybmpmon
watch docker stats pybmpmon
```

**Solutions:**

1. **Large batches**
   ```bash
   # Reduce batch size in code (default: 1000 routes)
   # Or reduce batch timeout (default: 500ms)
   ```

2. **Too many database connections**
   ```bash
   # Reduce connection pool in .env
   DATABASE_POOL_MAX_SIZE=5
   docker-compose restart pybmpmon
   ```

3. **Memory leak**
   ```bash
   # Restart service periodically (workaround)
   # Report issue with reproduction steps
   ```

### Slow Route Processing

**Symptom:** Routes/second much lower than expected

**Diagnosis:**
```bash
# Check throughput in logs (every 10 seconds)
docker-compose logs pybmpmon | grep route_stats

# Expected: throughput_per_sec > 1500

# Check database write latency
docker-compose exec postgres psql -U bmpmon -d bmpmon -c "
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
"
```

**Solutions:**

1. **Database I/O bottleneck**
   ```bash
   # Use SSD for database volume
   # Increase PostgreSQL shared_buffers
   # Add more RAM to database host
   ```

2. **Network latency**
   ```bash
   # Measure network latency to database
   docker-compose exec pybmpmon ping postgres

   # Use local database instead of remote
   ```

3. **Too many indexes**
   ```sql
   -- Remove unused indexes
   -- Check index usage
   SELECT * FROM pg_stat_user_indexes WHERE idx_scan = 0;
   ```

## Logging Issues

### No Logs Appearing

**Symptom:** `docker-compose logs` shows nothing

**Diagnosis:**
```bash
# Check if container is running
docker-compose ps

# Check log level
echo $LOG_LEVEL

# Try running in foreground
docker-compose up pybmpmon
```

**Solutions:**

1. **Container not running**
   ```bash
   docker-compose up -d pybmpmon
   ```

2. **Logs being sent elsewhere**
   ```bash
   # Check Docker logging driver
   docker inspect pybmpmon | grep LogConfig
   ```

### Logs Too Verbose (DEBUG Mode)

**Symptom:** Huge log files with hex dumps

**Solution:**
```bash
# Change LOG_LEVEL to INFO in .env
LOG_LEVEL=INFO
docker-compose restart pybmpmon

# Rotate logs
docker-compose logs --tail=1000 pybmpmon > last_1000.log
```

### Sentry Not Receiving Events

**Symptom:** No events in Sentry dashboard

**Diagnosis:**
```bash
# Check Sentry initialization
docker-compose logs pybmpmon | grep sentry_initialized

# Verify DSN is set
docker-compose exec pybmpmon env | grep SENTRY_DSN

# Test network connectivity
docker-compose exec pybmpmon curl -I https://sentry.io
```

**Solutions:**

1. **Sentry not initialized**
   ```bash
   # Verify SENTRY_DSN in .env
   # Must be valid DSN, not empty
   SENTRY_DSN=https://key@o0.ingest.sentry.io/123456
   ```

2. **Sentry SDK not installed**
   ```bash
   # Rebuild image
   docker-compose build --no-cache pybmpmon
   docker-compose up -d pybmpmon
   ```

3. **Network firewall**
   ```bash
   # Allow HTTPS to *.sentry.io
   docker-compose exec pybmpmon curl -v https://sentry.io
   ```

## Router Compatibility Issues

### Cisco IOS-XR

**Issue:** Router doesn't send routes

**Solution:**
```
! Ensure route-monitoring is configured
bmp server 1
 update-source Loopback0

router bgp 65000
 bmp server 1
  activate
  route-monitoring pre-policy  ! Important
```

### Juniper Junos

**Issue:** Connection established but no routes

**Solution:**
```
! Enable route monitoring
set routing-options bmp station pybmpmon route-monitoring pre-policy
commit and-quit
```

### Arista EOS

**Issue:** BMP session flapping

**Solution:**
```
! Increase hold timers
router bgp 65000
   bmp server pybmpmon
      tcp keepalive idle 120 interval 60 probes 3
```

## Data Integrity Issues

### Duplicate Routes

**Symptom:** Same prefix appears multiple times with same timestamp

**Diagnosis:**
```sql
SELECT prefix, time, COUNT(*)
FROM route_updates
GROUP BY prefix, time
HAVING COUNT(*) > 1;
```

**Cause:** This is expected - denormalized storage stores every route update

**Solution:** Use `DISTINCT ON` queries to get latest state (see [Queries](queries.md))

### Missing Routes

**Symptom:** Routes missing that should be present

**Diagnosis:**
```bash
# Check for parse errors
docker-compose logs pybmpmon | grep parse_error

# Check database capacity
docker-compose exec postgres df -h

# Verify router is sending routes
# Check router BMP statistics
```

**Solutions:**

1. **Parse errors:** Report issue with DEBUG logs
2. **Database full:** Free up space or increase retention policy
3. **Router not sending:** Check router BMP configuration

## Backup and Recovery

### Restore from Backup

```bash
# Stop application
docker-compose stop pybmpmon

# Restore database
docker-compose exec postgres pg_restore \
  -U bmpmon -d bmpmon \
  --clean \
  /path/to/backup.dump

# Restart application
docker-compose start pybmpmon
```

### Emergency Database Reset

!!! danger "Data Loss Warning"
    This will delete all data. Only use as last resort.

```bash
# Stop services
docker-compose down

# Remove volumes
docker-compose down -v

# Restart (will recreate database)
docker-compose up -d
```

## Getting Help

### Collect Diagnostic Information

Before reporting issues, collect:

1. **Version information**
   ```bash
   docker-compose exec pybmpmon python -c "from pybmpmon import __version__; print(__version__)"
   ```

2. **Configuration (redact passwords)**
   ```bash
   docker-compose config
   ```

3. **Logs**
   ```bash
   docker-compose logs --tail=500 pybmpmon > logs.txt
   docker-compose logs --tail=500 postgres >> logs.txt
   ```

4. **System information**
   ```bash
   docker version
   docker-compose version
   uname -a
   df -h
   free -m
   ```

5. **Database stats**
   ```bash
   docker-compose exec postgres psql -U bmpmon -d bmpmon -c "
   SELECT
     (SELECT COUNT(*) FROM route_updates) as total_routes,
     (SELECT COUNT(*) FROM bmp_peers WHERE is_active=TRUE) as active_peers,
     (SELECT pg_size_pretty(pg_database_size('bmpmon'))) as db_size;
   "
   ```

### Report Issues

Include in issue reports:

- Description of problem
- Steps to reproduce
- Expected vs actual behavior
- Diagnostic information (above)
- Relevant log snippets
- Router vendor and OS version

## Next Steps

- [Configuration](configuration.md): Adjust settings
- [Queries](queries.md): Verify data with SQL
- [Logging](logging_examples.md): Understand log messages
- [Sentry](sentry.md): Configure error tracking
