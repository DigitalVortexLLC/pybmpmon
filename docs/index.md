# pybmpmon

**BGP Monitoring Protocol (BMP) listener and analyzer**

pybmpmon is a high-performance BMP listener that receives BGP route data from routers, processes it, and stores it in PostgreSQL/TimescaleDB for analysis. It's designed to handle high-throughput BGP route updates with support for multiple address families.

## Overview

BMP (BGP Monitoring Protocol, [RFC 7854](https://datatracker.ietf.org/doc/html/rfc7854)) is a protocol that allows network devices to monitor BGP sessions. Routers send BMP messages to monitoring stations, providing visibility into BGP routing decisions, peer relationships, and route updates.

pybmpmon acts as a BMP monitoring station, receiving and processing these messages to provide:

- **Real-time BGP route monitoring**: Track route announcements and withdrawals
- **Historical route analysis**: Query route changes over time with 5-year retention
- **Multi-protocol support**: IPv4 unicast, IPv6 unicast, and EVPN routes
- **Peer relationship tracking**: Monitor BMP peer sessions and BGP peering
- **Route churn analysis**: Identify unstable routes and routing issues
- **Structured logging**: JSON logs for easy integration with log aggregation systems
- **Error tracking**: Optional Sentry integration for monitoring and alerting

## Key Features

### Protocol Support

- **BMP v3** (RFC 7854): Full compliance with all message types
    - Route Monitoring messages
    - Peer Up/Down notifications
    - Statistics Reports
    - Initiation and Termination messages
- **BGP-4**: Parse UPDATE messages with all standard path attributes
- **Address Families**:
    - IPv4 Unicast (AFI=1, SAFI=1)
    - IPv6 Unicast (AFI=2, SAFI=1)
    - EVPN (AFI=25, SAFI=70) - All route types

### Performance

- **High throughput**: 15,000-20,000 routes/second
- **Fast initial load**: Process 1.1M route table in ~60 seconds
- **Efficient storage**: Batch inserts using PostgreSQL COPY
- **Asyncio-based**: Handle thousands of concurrent BMP peers
- **Low latency**: Inline parsing with no queuing overhead

### Data Storage

- **TimescaleDB**: Time-series database optimized for route data
- **5-year retention**: Long-term historical route analysis
- **Automatic compression**: Reduce storage costs for older data
- **Denormalized schema**: Simple queries without complex joins
- **Rich indexing**: Fast lookups by prefix, AS path, peer, and more

### Monitoring & Observability

- **Structured JSON logs**: All events logged to stdout
- **Per-peer statistics**: Route counts, throughput, errors (logged every 10 seconds)
- **DEBUG mode**: Hex dumps of BMP messages for troubleshooting
- **Sentry integration**: Optional error tracking and alerting
- **Health checks**: Simple process and network checks (no HTTP server needed)

## Architecture

### Design Philosophy

**Start simple. Add complexity only when needed.**

pybmpmon is designed as a focused monitoring tool, not a distributed system. The architecture prioritizes simplicity, reliability, and ease of debugging over premature optimization.

### Component Interaction

```
BMP Peer (Router) → TCP Socket (port 11019) → Asyncio Handler
                                                      ↓
                                              BMP Message Parser
                                                      ↓
                                   ┌──────────────────┴──────────────────┐
                                   ↓                                     ↓
                            State Messages                        Route Messages
                          (Peer Up/Down,                      (Route Monitoring)
                           Statistics, etc.)                          ↓
                                   ↓                          BGP UPDATE Parser
                            Handle Inline                             ↓
                                   ↓                          Batch Accumulator
                              Database                       (1000 routes/batch)
                                                                      ↓
                                                             PostgreSQL COPY
                                                                      ↓
                                                                 Database
```

### Concurrency Model

- **Asyncio only**: All I/O operations use async/await
- **No multiprocessing**: BGP parsing is fast enough inline (~50μs per route)
- **No threading**: Asyncio handles thousands of concurrent connections
- **Inline processing**: Parse BMP and BGP messages directly in connection handlers
- **Batch accumulation**: Collect parsed routes in memory, flush periodically

### Data Flow

1. **BMP Connection**: Router connects to port 11019
2. **BMP Parsing**: Parse message headers and decode message types
3. **State Handling**: Process Peer Up/Down, Statistics, etc. immediately
4. **Route Parsing**: Parse BGP UPDATEs from Route Monitoring messages
5. **Batch Accumulation**: Collect routes until batch size (1000) or timeout (500ms)
6. **Database Write**: Bulk insert using PostgreSQL COPY
7. **Statistics**: Log per-peer metrics every 10 seconds

## Use Cases

### Network Operations

- **Route visibility**: See exactly what routes your BGP peers are advertising
- **Change tracking**: Monitor route announcements and withdrawals over time
- **Troubleshooting**: Analyze BGP routing issues with historical data
- **Capacity planning**: Understand route table growth trends

### Security & Compliance

- **Audit trail**: Complete history of BGP route changes
- **Anomaly detection**: Identify unexpected route changes
- **Prefix hijacking**: Track unauthorized route announcements
- **Route leak detection**: Monitor for unintended route propagation

### Research & Analysis

- **BGP behavior studies**: Analyze routing patterns and convergence
- **Route churn analysis**: Identify unstable prefixes and peers
- **AS path analysis**: Study AS-level routing decisions
- **EVPN monitoring**: Track MAC/IP bindings in EVPN networks

## Technology Stack

### Core Libraries

- **asyncio**: Built-in TCP server and concurrency
- **asyncpg**: Fast async PostgreSQL driver with connection pooling
- **Pydantic v2**: Type-safe configuration from `.env` files
- **structlog**: Structured JSON logging to stdout
- **sentry-sdk** (optional): Error tracking and monitoring

### Database

- **PostgreSQL 16**: Robust relational database
- **TimescaleDB**: Time-series extension for hypertables and compression
- **Connection pooling**: 5-10 async connections via asyncpg

### Development Tools

- **pytest**: Test framework with async support (60% coverage target)
- **black**: Code formatting (line length 88)
- **ruff**: Fast linting and import sorting
- **mypy**: Static type checking (strict mode)

## Quick Start

```bash
# Clone repository
git clone https://github.com/yourusername/pybmpmon.git
cd pybmpmon

# Copy example configuration
cp .env.example .env

# Edit .env with your settings
vim .env

# Start services with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f pybmpmon
```

See [Installation](installation.md) for detailed setup instructions.

## Configuration

pybmpmon is configured entirely via environment variables in a `.env` file:

```bash
# BMP Listener
BMP_LISTEN_HOST=0.0.0.0
BMP_LISTEN_PORT=11019

# Database
DATABASE_HOST=postgres
DATABASE_PORT=5432
DATABASE_NAME=bmpmon
DATABASE_USER=bmpmon
DATABASE_PASSWORD=changeme

# Logging
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR

# Sentry (Optional)
SENTRY_DSN=  # Leave empty to disable
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
```

See [Configuration](configuration.md) for all options.

## Next Steps

- **[Installation](installation.md)**: Set up pybmpmon with Docker Compose
- **[Configuration](configuration.md)**: Configure BMP listener and database
- **[SQL Queries](queries.md)**: Example queries for route analysis
- **[Logging](logging_examples.md)**: Understand structured log output
- **[Sentry](sentry.md)**: Set up error tracking and monitoring
- **[Troubleshooting](troubleshooting.md)**: Common issues and solutions

## Requirements

- **Python**: 3.11, 3.12, or 3.13
- **PostgreSQL**: 16+ with TimescaleDB extension
- **Platform**: Linux or macOS
- **Docker**: Optional but recommended

## License

[Add your license information here]

## Contributing

[Add contribution guidelines here]
