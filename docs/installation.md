# Installation

This guide covers installing pybmpmon using Docker Compose (recommended) or running it directly with Python.

## Prerequisites

### Docker Compose Installation (Recommended)

- Docker Engine 20.10+
- Docker Compose v2+
- 4GB RAM minimum
- 100GB+ disk space for database

### Python Installation (Advanced)

- Python 3.11, 3.12, or 3.13
- PostgreSQL 16+ with TimescaleDB extension
- 4GB RAM minimum
- Linux or macOS

## Quick Start with Docker Compose

### 1. Clone the Repository

```bash
git clone https://github.com/DigitalVortexLLC/pybmpmon.git
cd pybmpmon
```

### 2. Create Configuration File

Copy the example configuration:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```bash
# BMP Listener
BMP_LISTEN_HOST=0.0.0.0
BMP_LISTEN_PORT=11019

# Database
DATABASE_HOST=postgres
DATABASE_PORT=5432
DATABASE_NAME=bmpmon
DATABASE_USER=bmpmon
DATABASE_PASSWORD=changeme  # Change this!

# Logging
LOG_LEVEL=INFO

# Sentry (Optional - leave empty to disable)
SENTRY_DSN=
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
```

!!! warning "Security"
    Change the default database password before deploying to production!

### 3. Start Services

Start PostgreSQL/TimescaleDB and pybmpmon:

```bash
docker-compose up -d
```

This will:

1. Pull the necessary Docker images
2. Start PostgreSQL with TimescaleDB extension
3. Initialize the database schema
4. Start the pybmpmon BMP listener on port 11019

### 4. Verify Installation

Check that services are running:

```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs -f pybmpmon

# Check BMP port is listening
nc -z localhost 11019 && echo "BMP port is open"

# Check database connectivity
docker-compose exec postgres pg_isready
```

Expected output in logs:

```json
{
  "event": "bmp_listener_started",
  "level": "INFO",
  "timestamp": "2025-09-30T10:00:00.000000Z",
  "host": "0.0.0.0",
  "port": 11019
}
```

### 5. Configure Router

Configure your router to send BMP traffic to the pybmpmon listener:

=== "Cisco IOS-XR"

    ```
    bmp server 1
     host <pybmpmon-ip> port 11019
     description pybmpmon monitoring
     initial-delay 5
     stats-reporting-period 60
     update-source Loopback0
    !
    router bgp 65000
     bmp server 1
      activate
    ```

=== "Juniper Junos"

    ```
    set routing-options bmp station pybmpmon
    set routing-options bmp station pybmpmon connection-mode active
    set routing-options bmp station pybmpmon station-address <pybmpmon-ip>
    set routing-options bmp station pybmpmon station-port 11019
    set routing-options bmp station pybmpmon route-monitoring pre-policy
    ```

=== "Arista EOS"

    ```
    router bgp 65000
       bmp server pybmpmon
          host <pybmpmon-ip> port 11019
          send route-monitoring pre-policy
    ```

!!! tip "Network Connectivity"
    Ensure firewall rules allow TCP traffic from your routers to port 11019 on the pybmpmon host.

### 6. Verify Route Data

After routers connect, verify routes are being stored:

```bash
# Connect to database
docker-compose exec postgres psql -U bmpmon -d bmpmon

# Check for routes
SELECT COUNT(*) FROM route_updates;

# Check BMP peers
SELECT peer_ip, is_active, first_seen, last_seen FROM bmp_peers;

# Exit psql
\q
```

## Docker Compose Configuration

### docker-compose.yml

```yaml
version: '3.8'

services:
  postgres:
    image: timescale/timescaledb:latest-pg16
    container_name: pybmpmon-postgres
    environment:
      POSTGRES_DB: ${DATABASE_NAME:-bmpmon}
      POSTGRES_USER: ${DATABASE_USER:-bmpmon}
      POSTGRES_PASSWORD: ${DATABASE_PASSWORD:?DATABASE_PASSWORD not set}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/init_db.sql:/docker-entrypoint-initdb.d/01_init.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DATABASE_USER:-bmpmon}"]
      interval: 10s
      timeout: 5s
      retries: 5

  pybmpmon:
    build: .
    container_name: pybmpmon
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "${BMP_LISTEN_PORT:-11019}:11019"
    environment:
      - BMP_LISTEN_HOST=${BMP_LISTEN_HOST:-0.0.0.0}
      - BMP_LISTEN_PORT=${BMP_LISTEN_PORT:-11019}
      - DATABASE_HOST=${DATABASE_HOST:-postgres}
      - DATABASE_PORT=${DATABASE_PORT:-5432}
      - DATABASE_NAME=${DATABASE_NAME:-bmpmon}
      - DATABASE_USER=${DATABASE_USER:-bmpmon}
      - DATABASE_PASSWORD=${DATABASE_PASSWORD:?DATABASE_PASSWORD not set}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - SENTRY_DSN=${SENTRY_DSN:-}
      - SENTRY_ENVIRONMENT=${SENTRY_ENVIRONMENT:-production}
      - SENTRY_TRACES_SAMPLE_RATE=${SENTRY_TRACES_SAMPLE_RATE:-0.1}
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "nc -z localhost 11019 || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  postgres_data:
```

### Dockerfile

```dockerfile
FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 pybmpmon

WORKDIR /app

# Install Poetry
RUN pip install poetry==1.8.0

# Copy project files
COPY pyproject.toml poetry.lock ./
COPY src/ ./src/
COPY README.md ./

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction --no-ansi

# Switch to non-root user
USER pybmpmon

# Expose BMP port
EXPOSE 11019

# Run application
CMD ["python", "-m", "pybmpmon"]
```

## Advanced Installation Options

### Using External PostgreSQL

If you have an existing PostgreSQL/TimescaleDB instance:

1. Disable the postgres service in `docker-compose.yml`:

```yaml
services:
  postgres:
    deploy:
      replicas: 0  # Disable built-in PostgreSQL
```

2. Update `.env` to point to your database:

```bash
DATABASE_HOST=your-postgres-host
DATABASE_PORT=5432
DATABASE_NAME=bmpmon
DATABASE_USER=bmpmon
DATABASE_PASSWORD=your-password
```

3. Initialize the database schema:

```bash
# Run migration scripts
docker-compose run --rm pybmpmon python scripts/init_db.py
```

### Running Without Docker

For development or custom deployments:

```bash
# Install dependencies
poetry install

# Create .env file
cp .env.example .env
# Edit .env with your settings

# Initialize database
poetry run python scripts/init_db.py

# Run application
poetry run python -m pybmpmon
```

## Scaling Considerations

### Single Server Setup

For most deployments, a single pybmpmon instance is sufficient:

- **Peers**: 100+ BMP peers
- **Routes**: 1-2M routes per peer
- **Throughput**: 15-20k routes/second
- **Hardware**: 4 CPU cores, 16GB RAM, 500GB SSD

### Database Sizing

Calculate storage requirements:

- **Route updates**: ~500 bytes per update
- **Retention**: 5 years
- **Example**: 1.1M routes × 10 updates/day × 365 days × 5 years × 500 bytes ≈ 10TB

!!! tip "Storage Planning"
    Use TimescaleDB compression (30 days old data) to reduce storage by 70-90%.

### Network Planning

- **Bandwidth**: ~1-5 Mbps per BMP peer during initial table transfer
- **Steady state**: ~100 Kbps per peer for route updates
- **Firewall**: Allow TCP from routers to port 11019

## Health Monitoring

### Docker Healthchecks

Built-in healthchecks monitor:

1. **BMP port**: `nc -z localhost 11019`
2. **Database**: `pg_isready`

View health status:

```bash
docker-compose ps
```

### Manual Health Checks

```bash
# Check BMP listener
nc -z localhost 11019 && echo "BMP listener OK"

# Check database
docker-compose exec postgres pg_isready

# Check process
docker-compose exec pybmpmon pgrep -f pybmpmon && echo "Process running"

# Check recent logs for errors
docker-compose logs --tail=100 pybmpmon | grep -i error
```

## Upgrading

### Minor Version Upgrades

```bash
# Pull latest images
docker-compose pull

# Restart services
docker-compose up -d

# Check logs for errors
docker-compose logs -f pybmpmon
```

### Major Version Upgrades

1. **Backup database** (see Troubleshooting section)
2. Pull new images
3. Run database migrations if needed
4. Restart services
5. Verify functionality

## Uninstallation

### Remove Services

```bash
# Stop services
docker-compose down

# Remove volumes (WARNING: deletes all data)
docker-compose down -v
```

### Remove Images

```bash
# Remove pybmpmon images
docker image rm pybmpmon:latest

# Remove PostgreSQL images
docker image rm timescale/timescaledb:latest-pg16
```

## Next Steps

- [Configuration](configuration.md): Configure BMP listener and database options
- [SQL Queries](queries.md): Query route data and analyze BGP routing
- [Troubleshooting](troubleshooting.md): Common issues and solutions
