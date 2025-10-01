# Logging Examples

This document provides examples of structured JSON logs produced by pybmpmon.

## Configuration

Configure log level via `.env` file:
```
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

All logs are output to stdout as JSON.

## Application Lifecycle

### Application Startup
```json
{
  "event": "pybmpmon_starting",
  "level": "INFO",
  "timestamp": "2025-09-30T19:30:45.123456Z",
  "version": "0.1.0",
  "python_version": "3.13.7",
  "listen_host": "0.0.0.0",
  "listen_port": 11019,
  "log_level": "INFO"
}
```

### Application Shutdown
```json
{
  "event": "pybmpmon_stopped",
  "level": "INFO",
  "timestamp": "2025-09-30T20:30:45.123456Z"
}
```

## BMP Peer Events

### Peer Connected
```json
{
  "event": "peer_connected",
  "level": "INFO",
  "timestamp": "2025-09-30T19:31:00.123456Z",
  "peer": "192.0.2.1"
}
```

### Peer Disconnected
```json
{
  "event": "peer_disconnected",
  "level": "INFO",
  "timestamp": "2025-09-30T20:15:00.123456Z",
  "peer": "192.0.2.1",
  "reason": "connection_reset",
  "duration_seconds": 2640
}
```

### Peer Connection Closed
```json
{
  "event": "peer_connection_closed",
  "level": "INFO",
  "timestamp": "2025-09-30T20:15:00.234567Z",
  "peer": "192.0.2.1",
  "duration_seconds": 2640
}
```

### BMP Peer Up
```json
{
  "event": "bmp_peer_up",
  "level": "INFO",
  "timestamp": "2025-09-30T19:31:01.123456Z",
  "peer": "192.0.2.1",
  "bgp_peer": "192.0.2.100",
  "bgp_peer_asn": 65001
}
```

### BMP Peer Down
```json
{
  "event": "bmp_peer_down",
  "level": "INFO",
  "timestamp": "2025-09-30T20:14:59.123456Z",
  "peer": "192.0.2.1",
  "reason": 1
}
```

## Route Statistics (Every 10 Seconds)

```json
{
  "event": "route_stats",
  "level": "INFO",
  "timestamp": "2025-09-30T19:31:10.123456Z",
  "peer": "192.0.2.1",
  "received": 1523,
  "processed": 1520,
  "ipv4": 1245,
  "ipv6": 275,
  "evpn": 0,
  "errors": 3,
  "throughput_per_sec": 152
}
```

### Explanation:
- `received`: Total BMP messages received in this 10-second interval
- `processed`: Total routes processed (announced + withdrawn)
- `ipv4`: IPv4 unicast routes processed
- `ipv6`: IPv6 unicast routes processed
- `evpn`: EVPN routes processed
- `errors`: Parse errors encountered
- `throughput_per_sec`: Routes processed per second

## Error Logging

### BMP Parse Error
```json
{
  "event": "bmp_parse_error",
  "level": "ERROR",
  "timestamp": "2025-09-30T19:32:15.123456Z",
  "peer": "192.0.2.1",
  "error": "Invalid BMP version: expected 3, got 2",
  "data_hex": "02000000060400000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
}
```

### BGP Parse Error
```json
{
  "event": "bgp_parse_error",
  "level": "ERROR",
  "timestamp": "2025-09-30T19:32:20.123456Z",
  "peer": "192.0.2.1",
  "error": "Invalid BGP marker"
}
```

### Message Processing Error
```json
{
  "event": "message_processing_error",
  "level": "ERROR",
  "timestamp": "2025-09-30T19:32:25.123456Z",
  "peer": "192.0.2.1",
  "error": "Unexpected error during message processing"
}
```

## DEBUG Level Logging

### BMP Message Received (with Hex Dump)
```json
{
  "event": "bmp_message_received",
  "level": "DEBUG",
  "timestamp": "2025-09-30T19:31:05.123456Z",
  "peer": "192.0.2.1",
  "version": 3,
  "length": 100,
  "msg_type": "ROUTE_MONITORING",
  "data_hex": "0300000064000000000000000001c0a8010a200000001a0200000001010101c0a802fe400101004002004003040ac00001800404000000648005040000006480090408010102",
  "total_size": 100
}
```

### BGP UPDATE Parsed
```json
{
  "event": "bgp_update_parsed",
  "level": "DEBUG",
  "timestamp": "2025-09-30T19:31:05.234567Z",
  "peer": "192.0.2.1",
  "bgp_peer": "192.0.2.100",
  "family": "ipv4_unicast",
  "prefixes_count": 5,
  "withdrawn_count": 2,
  "as_path": [65000, 65001, 65002],
  "next_hop": "192.0.2.254"
}
```

## Database and Service Events

### Database Pool Created
```json
{
  "event": "database_pool_created",
  "level": "INFO",
  "timestamp": "2025-09-30T19:30:50.123456Z"
}
```

### Batch Writer Started
```json
{
  "event": "batch_writer_started",
  "level": "INFO",
  "timestamp": "2025-09-30T19:30:51.123456Z"
}
```

### Statistics Collector Started
```json
{
  "event": "stats_collector_started",
  "level": "INFO",
  "timestamp": "2025-09-30T19:30:52.123456Z",
  "interval_seconds": 10.0
}
```

### BMP Listener Started
```json
{
  "event": "bmp_listener_started",
  "level": "INFO",
  "timestamp": "2025-09-30T19:30:53.123456Z",
  "host": "0.0.0.0",
  "port": 11019,
  "address": ["0.0.0.0", 11019]
}
```

## Sentry Integration (Optional)

### Sentry Initialized
```json
{
  "event": "sentry_initialized",
  "level": "INFO",
  "timestamp": "2025-09-30T19:30:45.567890Z",
  "environment": "production"
}
```

### Sentry Disabled
```json
{
  "event": "sentry_disabled",
  "level": "DEBUG",
  "timestamp": "2025-09-30T19:30:45.567890Z"
}
```

## Log Aggregation and Analysis

These JSON logs can be easily parsed by log aggregation tools:

- **Loki**: Use promtail to ship logs with JSON parsing
- **CloudWatch Logs**: Use JSON parsing in log group filters
- **Elasticsearch**: Direct JSON ingestion
- **Datadog**: JSON log parsing with automatic field extraction
- **Splunk**: JSON source type

### Example Loki Query
```logql
{job="pybmpmon"} | json | event="route_stats" | throughput_per_sec > 1000
```

### Example CloudWatch Insights Query
```
fields @timestamp, peer, throughput_per_sec
| filter event = "route_stats"
| stats avg(throughput_per_sec) by peer
```

## Common Use Cases

### Monitor Route Churn
Filter for high route update counts:
```
event="route_stats" AND (processed > 5000)
```

### Track Peer Session Stability
Monitor peer disconnects:
```
event="peer_disconnected" AND duration_seconds < 300
```

### Debug Parse Errors
View all parse errors with context:
```
level="ERROR" AND (event="bmp_parse_error" OR event="bgp_parse_error")
```

### Monitor Throughput
Track routes per second across all peers:
```
event="route_stats" | stats sum(throughput_per_sec)
```
