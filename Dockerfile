# Multi-stage build for pybmpmon
FROM python:3.11-slim as builder

# Install Poetry
RUN pip install --no-cache-dir poetry==1.7.1

WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies only (no dev dependencies for production)
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --no-root --only main

# Final stage
FROM python:3.11-slim

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash bmpmon

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY src/ ./src/
COPY .env.example ./.env

# Set ownership
RUN chown -R bmpmon:bmpmon /app

# Switch to non-root user
USER bmpmon

# Expose BMP port
EXPOSE 11019

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(1); s.connect(('127.0.0.1', 11019)); s.close()" || exit 1

# Run application
CMD ["python", "-m", "pybmpmon"]
