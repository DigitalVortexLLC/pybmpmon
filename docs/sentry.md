# Sentry Integration

This document explains how to configure and use Sentry for error tracking and monitoring in pybmpmon.

## Overview

Sentry integration provides:
- **Automatic error tracking**: All ERROR level logs are sent to Sentry
- **Peer event tracking**: BMP peer up/down events with full context
- **Parse error tracking**: BMP and BGP parse errors with message data
- **Route processing errors**: Database and processing errors with context
- **Contextual information**: Peer IPs, message types, error details

## Configuration

### Enable Sentry

Add the following to your `.env` file:

```bash
# Required: Sentry DSN (get from Sentry.io project settings)
SENTRY_DSN=https://examplePublicKey@o0.ingest.sentry.io/0

# Optional: Environment name (default: development)
SENTRY_ENVIRONMENT=production

# Optional: Traces sample rate (0.0 to 1.0, default: 0.1)
SENTRY_TRACES_SAMPLE_RATE=0.1
```

### Disable Sentry

To disable Sentry, simply leave `SENTRY_DSN` empty or unset:

```bash
# Sentry disabled
SENTRY_DSN=
```

Or remove the line entirely from `.env`.

## Sentry Events

### Peer Up Events

When a BMP peer establishes a session:

```json
{
  "level": "info",
  "message": "BMP peer 192.0.2.1 established session with BGP peer 192.0.2.100 (AS65001)",
  "tags": {
    "event_type": "peer_up",
    "peer_ip": "192.0.2.1"
  },
  "contexts": {
    "bmp_peer": {
      "peer_ip": "192.0.2.1",
      "bgp_peer": "192.0.2.100",
      "bgp_peer_asn": 65001
    }
  }
}
```

### Peer Down Events

When a BMP peer disconnects:

```json
{
  "level": "warning",
  "message": "BMP peer 192.0.2.1 disconnected (reason code: 1)",
  "tags": {
    "event_type": "peer_down",
    "peer_ip": "192.0.2.1"
  },
  "contexts": {
    "bmp_peer": {
      "peer_ip": "192.0.2.1",
      "reason_code": 1
    }
  }
}
```

### Parse Errors

When BMP or BGP message parsing fails:

```json
{
  "level": "error",
  "message": "bmp_parse_error: Invalid BMP version from 192.0.2.1",
  "tags": {
    "error_type": "bmp_parse_error",
    "peer_ip": "192.0.2.1"
  },
  "contexts": {
    "parse_error": {
      "peer_ip": "192.0.2.1",
      "error_message": "Invalid BMP version: expected 3, got 2",
      "data_hex": "02000000060400..."
    }
  },
  "exception": {
    "type": "BMPParseError",
    "value": "Invalid BMP version: expected 3, got 2"
  }
}
```

### Route Processing Errors

When route processing fails:

```json
{
  "level": "error",
  "message": "Route processing error from 192.0.2.1: Database connection failed",
  "tags": {
    "error_type": "route_processing_error",
    "peer_ip": "192.0.2.1"
  },
  "contexts": {
    "route_processing": {
      "peer_ip": "192.0.2.1",
      "error_message": "Database connection failed",
      "route_count": 1000
    }
  }
}
```

## Sentry Dashboard Usage

### Filtering Events

Use tags to filter events in Sentry:

- **By event type**: `event_type:peer_up` or `event_type:peer_down`
- **By peer**: `peer_ip:192.0.2.1`
- **By error type**: `error_type:bmp_parse_error`

### Viewing Context

Click on any event to view full context:
- **bmp_peer**: Peer connection details
- **parse_error**: Error details with hex dump
- **route_processing**: Processing details and route counts

### Setting Up Alerts

Create alerts in Sentry for:

1. **High error rates**: Alert when parse errors exceed threshold
2. **Peer instability**: Alert when peer down events are frequent
3. **Route processing failures**: Alert on database errors

Example alert configuration:
```
When event.count in bmp_parse_error
is greater than 100
in 5 minutes
then send notification to #alerts
```

## Integration with Logging

Sentry integrates with the logging system:
- **INFO logs**: Sent to Sentry but not created as issues
- **ERROR logs**: Automatically create Sentry issues
- **Context preservation**: All structured log fields are included

All events are also logged to stdout as JSON, so you have both:
- **Sentry**: For error tracking and alerting
- **Logs**: For full audit trail and debugging

## Performance Impact

Sentry integration has minimal performance impact:
- **Async sending**: Events are sent asynchronously
- **Sampling**: Traces are sampled (default 10%)
- **No blocking**: Logging continues even if Sentry is unavailable
- **Graceful degradation**: Application works normally if Sentry is disabled

## Troubleshooting

### Sentry SDK Not Installed

If you see this warning:
```
sentry_sdk_not_installed
```

Install the Sentry SDK:
```bash
poetry add sentry-sdk
```

### Invalid DSN

If Sentry initialization fails, verify your DSN:
```bash
# Check DSN format
echo $SENTRY_DSN
# Should be: https://KEY@o0.ingest.sentry.io/PROJECT_ID
```

### No Events in Sentry

Check:
1. **DSN is set**: `echo $SENTRY_DSN`
2. **Application started**: Check logs for `sentry_initialized`
3. **Error level**: Only ERROR level logs create issues
4. **Network connectivity**: Ensure outbound HTTPS to sentry.io

### Too Many Events

Reduce event volume by:
1. **Filtering**: Set log level to ERROR only in production
2. **Sampling**: Reduce `SENTRY_TRACES_SAMPLE_RATE`
3. **Fingerprinting**: Group similar errors in Sentry settings

## Best Practices

1. **Use different environments**: Set `SENTRY_ENVIRONMENT` per deployment
2. **Monitor quota**: Check Sentry quota usage regularly
3. **Set up alerts**: Configure alerts for critical errors
4. **Review events**: Regularly review and resolve Sentry issues
5. **Release tracking**: Tag releases in Sentry for better tracking

## Example `.env` Configuration

### Development
```bash
SENTRY_DSN=https://key@sentry.io/dev-project
SENTRY_ENVIRONMENT=development
SENTRY_TRACES_SAMPLE_RATE=1.0  # Sample everything in dev
LOG_LEVEL=DEBUG
```

### Staging
```bash
SENTRY_DSN=https://key@sentry.io/staging-project
SENTRY_ENVIRONMENT=staging
SENTRY_TRACES_SAMPLE_RATE=0.5  # Sample 50%
LOG_LEVEL=INFO
```

### Production
```bash
SENTRY_DSN=https://key@sentry.io/prod-project
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1  # Sample 10%
LOG_LEVEL=INFO
```

## Privacy Considerations

Sentry captures:
- **Error messages**: Full exception details
- **Message data**: First 512 characters of hex dumps
- **IP addresses**: Peer IPs and connection details
- **Stack traces**: Full Python stack traces

**Do not include**:
- Passwords or secrets in log messages
- Sensitive customer data
- Full routing table dumps (truncated automatically)

## Further Reading

- [Sentry Documentation](https://docs.sentry.io/)
- [Python SDK](https://docs.sentry.io/platforms/python/)
- [Performance Monitoring](https://docs.sentry.io/product/performance/)
