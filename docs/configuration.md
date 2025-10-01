# Configuration

pybmpmon is configured entirely through environment variables, typically stored in a `.env` file. This approach ensures consistent configuration across development, staging, and production environments.

## Configuration File

### Location

The `.env` file should be placed in the root directory of the project:

```
pybmpmon/
├── .env              # Your configuration
├── .env.example      # Template configuration
├── docker-compose.yml
└── ...
```

### Security

!!! warning "Protect Sensitive Data"
    The `.env` file contains sensitive information (database passwords, Sentry DSN). Ensure proper permissions:

    ```bash
    chmod 600 .env
    ```

    Never commit `.env` to version control. Use `.env.example` as a template.

## Configuration Options

### BMP Listener

Configure the BMP listener TCP server:

```bash
# Host to bind to
BMP_LISTEN_HOST=0.0.0.0

# Port to listen on
BMP_LISTEN_PORT=11019
```

| Variable | Default | Description |
|----------|---------|-------------|
| `BMP_LISTEN_HOST` | `0.0.0.0` | IP address to bind to. Use `0.0.0.0` for all interfaces, `127.0.0.1` for localhost only |
| `BMP_LISTEN_PORT` | `11019` | TCP port for BMP connections. Standard BMP port is 11019 |

!!! tip "Firewall Configuration"
    Ensure your firewall allows inbound TCP connections from routers to the BMP port.

### Database

Configure PostgreSQL/TimescaleDB connection:

```bash
# Database connection
DATABASE_HOST=postgres
DATABASE_PORT=5432
DATABASE_NAME=bmpmon
DATABASE_USER=bmpmon
DATABASE_PASSWORD=changeme

# Optional: Connection pool settings
DATABASE_POOL_MIN_SIZE=5
DATABASE_POOL_MAX_SIZE=10
DATABASE_COMMAND_TIMEOUT=30.0
```

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_HOST` | `postgres` | PostgreSQL hostname or IP address |
| `DATABASE_PORT` | `5432` | PostgreSQL port |
| `DATABASE_NAME` | `bmpmon` | Database name |
| `DATABASE_USER` | `bmpmon` | Database user |
| `DATABASE_PASSWORD` | (required) | Database password - **must be set** |
| `DATABASE_POOL_MIN_SIZE` | `5` | Minimum connections in pool |
| `DATABASE_POOL_MAX_SIZE` | `10` | Maximum connections in pool |
| `DATABASE_COMMAND_TIMEOUT` | `30.0` | Query timeout in seconds |

!!! danger "Required Configuration"
    `DATABASE_PASSWORD` must be set. Application will fail to start if not provided.

#### Connection String Format

Alternatively, use a single connection string:

```bash
DATABASE_URL=postgresql://bmpmon:changeme@postgres:5432/bmpmon
```

### Logging

Configure structured logging output:

```bash
# Log level
LOG_LEVEL=INFO
```

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

#### Log Levels

- **DEBUG**: Verbose logging with BMP message hex dumps. Use for troubleshooting only.
- **INFO**: Standard operational logging with statistics and events.
- **WARNING**: Warnings and errors only.
- **ERROR**: Errors only.

!!! warning "DEBUG Performance Impact"
    DEBUG level logs every BMP message with hex dump (up to 256 bytes). This significantly increases log volume. Use only for troubleshooting.

Example DEBUG output:

```json
{
  "event": "bmp_message_received",
  "level": "DEBUG",
  "timestamp": "2025-09-30T10:15:30.123456Z",
  "peer": "192.0.2.1",
  "version": 3,
  "length": 256,
  "msg_type": "ROUTE_MONITORING",
  "data_hex": "030000010000000000000000...",
  "total_size": 256
}
```

### Sentry Integration

Optional error tracking and monitoring with Sentry:

```bash
# Sentry configuration
SENTRY_DSN=https://examplePublicKey@o0.ingest.sentry.io/0
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
```

| Variable | Default | Description |
|----------|---------|-------------|
| `SENTRY_DSN` | (empty) | Sentry Data Source Name. Leave empty to disable Sentry |
| `SENTRY_ENVIRONMENT` | `production` | Environment name (e.g., `development`, `staging`, `production`) |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.1` | Percentage of transactions to trace (0.0 to 1.0) |

#### Disabling Sentry

To disable Sentry, leave `SENTRY_DSN` empty or unset:

```bash
# Sentry disabled
SENTRY_DSN=
```

#### Sentry Setup

1. Create a Sentry project at [sentry.io](https://sentry.io)
2. Copy the DSN from project settings
3. Set `SENTRY_DSN` in `.env`
4. Restart pybmpmon

See [Sentry Integration](sentry.md) for detailed configuration.

## Environment-Specific Configuration

### Development

Recommended settings for development:

```bash
# .env.development
BMP_LISTEN_HOST=127.0.0.1
BMP_LISTEN_PORT=11019

DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=bmpmon_dev
DATABASE_USER=bmpmon
DATABASE_PASSWORD=dev_password

LOG_LEVEL=DEBUG

SENTRY_DSN=
```

### Staging

Recommended settings for staging:

```bash
# .env.staging
BMP_LISTEN_HOST=0.0.0.0
BMP_LISTEN_PORT=11019

DATABASE_HOST=postgres-staging
DATABASE_PORT=5432
DATABASE_NAME=bmpmon
DATABASE_USER=bmpmon
DATABASE_PASSWORD=staging_password

LOG_LEVEL=INFO

SENTRY_DSN=https://key@sentry.io/staging-project
SENTRY_ENVIRONMENT=staging
SENTRY_TRACES_SAMPLE_RATE=0.5
```

### Production

Recommended settings for production:

```bash
# .env.production
BMP_LISTEN_HOST=0.0.0.0
BMP_LISTEN_PORT=11019

DATABASE_HOST=postgres-prod
DATABASE_PORT=5432
DATABASE_NAME=bmpmon
DATABASE_USER=bmpmon
DATABASE_PASSWORD=strong_random_password

LOG_LEVEL=INFO

SENTRY_DSN=https://key@sentry.io/prod-project
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
```

!!! danger "Production Security"
    - Use strong, randomly generated passwords
    - Restrict database access with firewall rules
    - Use TLS for database connections if over untrusted networks
    - Limit BMP listener to management network
    - Set file permissions: `chmod 600 .env`

## Configuration Validation

### Startup Checks

pybmpmon validates configuration on startup and fails fast with clear error messages:

**Missing required variable:**
```
ERROR: DATABASE_PASSWORD is not set
```

**Invalid log level:**
```
ERROR: Invalid LOG_LEVEL: TRACE (must be DEBUG, INFO, WARNING, or ERROR)
```

**Database connection failure:**
```
ERROR: Failed to connect to database at postgres:5432
ConnectionRefusedError: [Errno 111] Connection refused
```

### Configuration Schema

pybmpmon uses Pydantic Settings for type-safe configuration with automatic validation:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # BMP Listener
    bmp_listen_host: str = "0.0.0.0"
    bmp_listen_port: int = 11019

    # Database
    database_host: str = "postgres"
    database_port: int = 5432
    database_name: str = "bmpmon"
    database_user: str = "bmpmon"
    database_password: str  # Required, no default

    # Logging
    log_level: str = "INFO"

    # Sentry (Optional)
    sentry_dsn: str = ""
    sentry_environment: str = "production"
    sentry_traces_sample_rate: float = 0.1

    class Config:
        env_file = ".env"
        case_sensitive = False
```

## Testing Configuration

### Verify Configuration

```bash
# Print current configuration (redacts passwords)
docker-compose run --rm pybmpmon python -c "
from pybmpmon.config import settings
print(f'BMP Listener: {settings.bmp_listen_host}:{settings.bmp_listen_port}')
print(f'Database: {settings.database_host}:{settings.database_port}/{settings.database_name}')
print(f'Log Level: {settings.log_level}')
print(f'Sentry: {\"Enabled\" if settings.sentry_dsn else \"Disabled\"}')
"
```

### Test Database Connection

```bash
# Test database connectivity
docker-compose exec postgres pg_isready -h localhost -U bmpmon

# Connect to database
docker-compose exec postgres psql -U bmpmon -d bmpmon -c "SELECT version();"
```

### Test BMP Listener

```bash
# Check if BMP port is listening
nc -z localhost 11019 && echo "BMP port is open"

# View listener logs
docker-compose logs -f pybmpmon | grep bmp_listener_started
```

## Configuration Best Practices

### 1. Use Environment-Specific Files

Maintain separate `.env` files for each environment:

```
.env.development
.env.staging
.env.production
```

Symlink or copy the appropriate file:

```bash
ln -sf .env.production .env
```

### 2. Never Commit Secrets

Add `.env` to `.gitignore`:

```gitignore
# Environment files
.env
.env.*
!.env.example
```

### 3. Use Secret Management

For production, consider using secret management tools:

- **Docker Secrets** (Docker Swarm)
- **Kubernetes Secrets**
- **HashiCorp Vault**
- **AWS Secrets Manager**
- **Azure Key Vault**

### 4. Rotate Credentials Regularly

- Change database passwords periodically
- Rotate Sentry DSN if compromised
- Update credentials after staff changes

### 5. Monitor Configuration Changes

- Log configuration changes
- Use infrastructure-as-code (Terraform, Ansible)
- Track changes in version control (for non-sensitive parts)

## Troubleshooting Configuration Issues

### Application Won't Start

**Symptom**: Container exits immediately

**Check:**
```bash
# View exit logs
docker-compose logs pybmpmon

# Common issues:
# - DATABASE_PASSWORD not set
# - Invalid LOG_LEVEL value
# - Database unreachable
```

### Database Connection Errors

**Symptom**: `ConnectionRefusedError` or timeout

**Solutions:**
```bash
# Verify database is running
docker-compose ps postgres

# Check database logs
docker-compose logs postgres

# Test connection manually
docker-compose exec postgres psql -U bmpmon -d bmpmon

# Verify hostname resolution
docker-compose exec pybmpmon ping postgres
```

### Sentry Not Receiving Events

**Symptom**: No errors in Sentry dashboard

**Check:**
```bash
# Verify DSN is set
docker-compose exec pybmpmon env | grep SENTRY_DSN

# Check logs for initialization
docker-compose logs pybmpmon | grep sentry_initialized

# Test network connectivity to sentry.io
docker-compose exec pybmpmon curl -I https://sentry.io
```

### High Memory Usage

**Symptom**: Container using excessive memory

**Check:**
```bash
# Monitor memory usage
docker stats pybmpmon

# Possible causes:
# - Too many database connections (reduce DATABASE_POOL_MAX_SIZE)
# - DEBUG logging with high route volume
# - Large batch sizes
```

## Next Steps

- [SQL Queries](queries.md): Query route data
- [Sentry Integration](sentry.md): Set up error monitoring
- [Logging](logging_examples.md): Understand log output
- [Troubleshooting](troubleshooting.md): Common issues and solutions
