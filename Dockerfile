FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash bmpmon

WORKDIR /app

# Install Poetry
RUN pip install --no-cache-dir poetry==1.7.1

# Copy dependency files and README (required by pyproject.toml)
COPY pyproject.toml poetry.lock README.md ./

# Install dependencies (as root for system packages)
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --only main --no-root

# Copy application source code
COPY src/ ./src/

# Install the pybmpmon package itself
RUN poetry install --no-interaction --no-ansi --only-root

# Copy env example
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
