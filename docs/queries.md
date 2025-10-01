# SQL Queries

This guide provides example SQL queries for analyzing BGP route data collected by pybmpmon.

## Connecting to Database

### Using Docker Compose

```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U bmpmon -d bmpmon
```

### Direct Connection

```bash
# Using psql
psql -h localhost -U bmpmon -d bmpmon

# Using connection string
psql postgresql://bmpmon:password@localhost:5432/bmpmon
```

## Basic Queries

### Count Total Routes

```sql
SELECT COUNT(*) as total_routes
FROM route_updates;
```

### Count Routes by Address Family

```sql
SELECT
    family,
    COUNT(*) as route_count
FROM route_updates
GROUP BY family
ORDER BY route_count DESC;
```

Expected output:
```
   family      | route_count
---------------+-------------
 ipv4_unicast  |     1100000
 ipv6_unicast  |      500000
 evpn          |      250000
```

### Active BMP Peers

```sql
SELECT
    peer_ip,
    router_id,
    is_active,
    first_seen,
    last_seen,
    AGE(last_seen, first_seen) as session_duration
FROM bmp_peers
WHERE is_active = TRUE
ORDER BY first_seen DESC;
```

### Recent Peer Events

```sql
SELECT
    time,
    peer_ip,
    event_type,
    reason_code
FROM peer_events
ORDER BY time DESC
LIMIT 20;
```

## Route Analysis

### Current Routes (Most Recent Per Prefix)

Get the current state of routes (latest update per prefix):

```sql
SELECT DISTINCT ON (bgp_peer_ip, prefix)
    bgp_peer_ip,
    prefix,
    next_hop,
    as_path,
    time as last_seen,
    is_withdrawn
FROM route_updates
WHERE prefix IS NOT NULL
ORDER BY bgp_peer_ip, prefix, time DESC
LIMIT 100;
```

### Active Routes Only (Not Withdrawn)

```sql
SELECT DISTINCT ON (bgp_peer_ip, prefix)
    bgp_peer_ip,
    prefix,
    next_hop,
    as_path,
    communities,
    time as last_seen
FROM route_updates
WHERE prefix IS NOT NULL
  AND is_withdrawn = FALSE
ORDER BY bgp_peer_ip, prefix, time DESC
LIMIT 100;
```

### Routes by Specific Peer

```sql
SELECT DISTINCT ON (prefix)
    prefix,
    next_hop,
    as_path,
    local_pref,
    med,
    time as last_seen
FROM route_updates
WHERE bgp_peer_ip = '192.0.2.100'
  AND is_withdrawn = FALSE
ORDER BY prefix, time DESC;
```

## Route Churn Analysis

### Most Unstable Prefixes (Highest Update Frequency)

Identify prefixes with frequent updates (flapping routes):

```sql
SELECT
    prefix,
    COUNT(*) as update_count,
    MIN(time) as first_seen,
    MAX(time) as last_seen,
    AGE(MAX(time), MIN(time)) as churn_window
FROM route_updates
WHERE time > NOW() - INTERVAL '1 hour'
  AND prefix IS NOT NULL
GROUP BY prefix
HAVING COUNT(*) > 10
ORDER BY update_count DESC
LIMIT 50;
```

### Route Withdrawals in Last Hour

```sql
SELECT
    time,
    bmp_peer_ip,
    bgp_peer_ip,
    prefix,
    as_path
FROM route_updates
WHERE time > NOW() - INTERVAL '1 hour'
  AND is_withdrawn = TRUE
ORDER BY time DESC;
```

### Routes Announced and Withdrawn Multiple Times

```sql
WITH route_changes AS (
    SELECT
        prefix,
        is_withdrawn,
        time
    FROM route_updates
    WHERE time > NOW() - INTERVAL '24 hours'
      AND prefix IS NOT NULL
)
SELECT
    prefix,
    COUNT(*) as total_changes,
    SUM(CASE WHEN is_withdrawn = TRUE THEN 1 ELSE 0 END) as withdrawals,
    SUM(CASE WHEN is_withdrawn = FALSE THEN 1 ELSE 0 END) as announcements
FROM route_changes
GROUP BY prefix
HAVING COUNT(*) > 5
ORDER BY total_changes DESC
LIMIT 100;
```

## AS Path Analysis

### Routes Containing Specific ASN

Find all routes passing through AS 65001:

```sql
SELECT DISTINCT ON (prefix)
    prefix,
    bgp_peer_ip,
    as_path,
    next_hop,
    time as last_seen
FROM route_updates
WHERE 65001 = ANY(as_path)
  AND is_withdrawn = FALSE
ORDER BY prefix, time DESC
LIMIT 100;
```

### AS Path Length Distribution

```sql
SELECT
    array_length(as_path, 1) as path_length,
    COUNT(*) as route_count
FROM (
    SELECT DISTINCT ON (prefix)
        prefix,
        as_path
    FROM route_updates
    WHERE is_withdrawn = FALSE
      AND as_path IS NOT NULL
    ORDER BY prefix, time DESC
) current_routes
GROUP BY path_length
ORDER BY path_length;
```

### Top Origin ASNs

Find the most common origin ASNs (last AS in path):

```sql
SELECT
    as_path[array_length(as_path, 1)] as origin_asn,
    COUNT(*) as prefix_count
FROM (
    SELECT DISTINCT ON (prefix)
        prefix,
        as_path
    FROM route_updates
    WHERE is_withdrawn = FALSE
      AND as_path IS NOT NULL
      AND array_length(as_path, 1) > 0
    ORDER BY prefix, time DESC
) current_routes
GROUP BY origin_asn
ORDER BY prefix_count DESC
LIMIT 20;
```

### Detect AS Path Prepending

Find routes with AS path prepending (same ASN repeated):

```sql
SELECT
    prefix,
    as_path,
    array_length(as_path, 1) as path_length,
    COUNT(*) OVER (PARTITION BY as_path[1]) as prepend_count
FROM (
    SELECT DISTINCT ON (prefix)
        prefix,
        as_path
    FROM route_updates
    WHERE is_withdrawn = FALSE
      AND array_length(as_path, 1) > 1
    ORDER BY prefix, time DESC
) current_routes
WHERE as_path[1] = as_path[2]  -- First two ASNs are the same
LIMIT 100;
```

## EVPN Queries

### Find MAC Address in EVPN

Locate a specific MAC address in EVPN routes:

```sql
SELECT
    time,
    bmp_peer_ip,
    bgp_peer_ip,
    mac_address,
    prefix,
    evpn_rd,
    evpn_esi,
    next_hop,
    is_withdrawn
FROM route_updates
WHERE mac_address = '00:02:71:87:da:4d'
ORDER BY time DESC
LIMIT 20;
```

### EVPN Routes by Route Type

```sql
SELECT
    evpn_route_type,
    COUNT(*) as route_count
FROM (
    SELECT DISTINCT ON (prefix, mac_address)
        evpn_route_type,
        prefix,
        mac_address
    FROM route_updates
    WHERE family = 'evpn'
      AND is_withdrawn = FALSE
    ORDER BY prefix, mac_address, time DESC
) current_evpn
GROUP BY evpn_route_type
ORDER BY route_count DESC;
```

### EVPN MAC/IP Bindings

```sql
SELECT DISTINCT ON (mac_address, prefix)
    mac_address,
    prefix as ip_address,
    evpn_rd,
    next_hop as vtep,
    time as last_seen
FROM route_updates
WHERE family = 'evpn'
  AND evpn_route_type = 2  -- MAC/IP Advertisement
  AND is_withdrawn = FALSE
ORDER BY mac_address, prefix, time DESC
LIMIT 100;
```

## BGP Communities Analysis

### Routes with Specific Community

```sql
SELECT DISTINCT ON (prefix)
    prefix,
    bgp_peer_ip,
    as_path,
    communities,
    time as last_seen
FROM route_updates
WHERE '65000:100' = ANY(communities)
  AND is_withdrawn = FALSE
ORDER BY prefix, time DESC
LIMIT 100;
```

### Community Distribution

```sql
WITH community_routes AS (
    SELECT DISTINCT ON (prefix)
        prefix,
        communities
    FROM route_updates
    WHERE is_withdrawn = FALSE
      AND communities IS NOT NULL
    ORDER BY prefix, time DESC
)
SELECT
    unnest(communities) as community,
    COUNT(*) as route_count
FROM community_routes
GROUP BY community
ORDER BY route_count DESC
LIMIT 50;
```

## Time-Series Analysis

### Routes Received Per Hour (Last 24 Hours)

```sql
SELECT
    time_bucket('1 hour', time) as hour,
    COUNT(*) as route_updates,
    COUNT(DISTINCT prefix) as unique_prefixes
FROM route_updates
WHERE time > NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour;
```

### Peak Route Update Rate

Find the busiest 5-minute window:

```sql
SELECT
    time_bucket('5 minutes', time) as window,
    COUNT(*) as route_count,
    COUNT(*) / 300.0 as routes_per_second
FROM route_updates
WHERE time > NOW() - INTERVAL '1 hour'
GROUP BY window
ORDER BY route_count DESC
LIMIT 10;
```

### Route Table Growth Over Time

```sql
WITH daily_routes AS (
    SELECT
        time_bucket('1 day', time) as day,
        family,
        COUNT(*) as routes_added
    FROM route_updates
    WHERE is_withdrawn = FALSE
      AND time > NOW() - INTERVAL '30 days'
    GROUP BY day, family
)
SELECT
    day,
    family,
    routes_added,
    SUM(routes_added) OVER (PARTITION BY family ORDER BY day) as cumulative_routes
FROM daily_routes
ORDER BY day, family;
```

## Performance Queries

### Database Size

```sql
SELECT
    pg_size_pretty(pg_database_size('bmpmon')) as database_size;
```

### Table Sizes

```sql
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) as table_size,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) as index_size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Index Usage

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan as index_scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;
```

### Slow Queries

```sql
-- First, enable pg_stat_statements extension
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- View slowest queries
SELECT
    mean_exec_time,
    calls,
    query
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

## Advanced Queries

### Route Changes Timeline for Specific Prefix

```sql
SELECT
    time,
    bgp_peer_ip,
    is_withdrawn,
    next_hop,
    as_path,
    communities
FROM route_updates
WHERE prefix = '10.0.0.0/24'
ORDER BY time DESC
LIMIT 100;
```

### Detect Route Hijacking (Unexpected Origin AS)

```sql
-- First, get normal origin AS for each prefix
WITH normal_origins AS (
    SELECT
        prefix,
        mode() WITHIN GROUP (ORDER BY as_path[array_length(as_path, 1)]) as expected_origin
    FROM route_updates
    WHERE time > NOW() - INTERVAL '7 days'
      AND is_withdrawn = FALSE
      AND array_length(as_path, 1) > 0
    GROUP BY prefix
),
recent_routes AS (
    SELECT DISTINCT ON (prefix)
        prefix,
        bgp_peer_ip,
        as_path,
        time
    FROM route_updates
    WHERE time > NOW() - INTERVAL '1 hour'
      AND is_withdrawn = FALSE
      AND array_length(as_path, 1) > 0
    ORDER BY prefix, time DESC
)
SELECT
    r.prefix,
    r.bgp_peer_ip,
    r.as_path,
    no.expected_origin,
    r.as_path[array_length(r.as_path, 1)] as current_origin,
    r.time
FROM recent_routes r
JOIN normal_origins no ON r.prefix = no.prefix
WHERE r.as_path[array_length(r.as_path, 1)] != no.expected_origin
LIMIT 100;
```

### Peer Comparison (Different Paths to Same Prefix)

```sql
SELECT
    r1.prefix,
    r1.bgp_peer_ip as peer1,
    r1.as_path as peer1_path,
    r2.bgp_peer_ip as peer2,
    r2.as_path as peer2_path
FROM (
    SELECT DISTINCT ON (prefix)
        prefix, bgp_peer_ip, as_path
    FROM route_updates
    WHERE bgp_peer_ip = '192.0.2.100'
      AND is_withdrawn = FALSE
    ORDER BY prefix, time DESC
) r1
JOIN (
    SELECT DISTINCT ON (prefix)
        prefix, bgp_peer_ip, as_path
    FROM route_updates
    WHERE bgp_peer_ip = '192.0.2.101'
      AND is_withdrawn = FALSE
    ORDER BY prefix, time DESC
) r2 ON r1.prefix = r2.prefix
WHERE r1.as_path != r2.as_path
LIMIT 100;
```

## Exporting Data

### CSV Export

```sql
-- Export to CSV
\copy (SELECT * FROM route_updates WHERE time > NOW() - INTERVAL '1 day') TO '/tmp/routes.csv' WITH CSV HEADER;
```

### JSON Export

```sql
-- Export as JSON
\copy (SELECT row_to_json(t) FROM (SELECT * FROM route_updates WHERE time > NOW() - INTERVAL '1 day') t) TO '/tmp/routes.json';
```

## Query Optimization Tips

### 1. Use Time Filters

Always filter by time for large tables:

```sql
-- Good
SELECT * FROM route_updates
WHERE time > NOW() - INTERVAL '1 day';

-- Bad (scans entire table)
SELECT * FROM route_updates;
```

### 2. Use DISTINCT ON for Latest State

```sql
-- Efficient way to get current routes
SELECT DISTINCT ON (prefix)
    prefix, next_hop, time
FROM route_updates
ORDER BY prefix, time DESC;
```

### 3. Leverage Indexes

Indexes exist on:
- `prefix` (GIN index for fast CIDR lookups)
- `family` + `time` (composite index)
- `bmp_peer_ip` + `time`
- `bgp_peer_ip` + `time`
- `as_path` (GIN index for ANY queries)

### 4. Use TimescaleDB Functions

```sql
-- Time bucketing for aggregations
SELECT
    time_bucket('1 hour', time) as hour,
    COUNT(*)
FROM route_updates
GROUP BY hour;
```

### 5. EXPLAIN Your Queries

```sql
EXPLAIN ANALYZE
SELECT * FROM route_updates
WHERE prefix <<= '10.0.0.0/8'
  AND time > NOW() - INTERVAL '1 day';
```

## Next Steps

- [Configuration](configuration.md): Optimize database settings
- [Troubleshooting](troubleshooting.md): Performance troubleshooting
- [Logging](logging_examples.md): Correlate logs with query results
