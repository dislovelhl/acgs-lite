# ================================
# ACGS-2 Enhanced Agent Bus - Security Hardened Dockerfile
# Constitutional Hash: cdd01ef066bc6cf2
# ================================

# ================================
# Stage 1: Rust Build Stage
# ================================
FROM rust:1.70-slim AS rust-builder

# Security: Install only essential build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libssl-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for build
RUN groupadd -r buildgroup -g 1000 && \
    useradd -r -g buildgroup -u 1000 builduser

WORKDIR /app

# Copy dependency files first for better caching
COPY Cargo.toml Cargo.lock ./

# Copy source code
COPY src/ ./src/

# Change ownership to non-root user
RUN chown -R builduser:buildgroup /app

# Switch to non-root user for build
USER builduser

# Build with security flags
RUN RUSTFLAGS="-C target-cpu=haswell -C opt-level=3 -C panic=abort -C codegen-units=1" \
    cargo build --release --locked

# Maturin Build Stage
FROM python:3.11-slim AS maturin-builder
WORKDIR /app
RUN pip install maturin
COPY --from=rust-builder /app /app
RUN maturin build --release --out dist

# ================================
# Stage 2: Python Dependencies Stage
# ================================
FROM python:3.11-slim AS python-deps

# Security: Install only essential packages and update certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create virtual environment for isolation
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements file and install dependencies
COPY requirements_optimized.txt /tmp/
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --require-hashes -r /tmp/requirements_optimized.txt

# ================================
# Stage 3: Final Runtime Image
# ================================
FROM python:3.11-slim AS runtime

# Security: Add metadata labels
LABEL org.opencontainers.image.title="ACGS-2 Enhanced Agent Bus" \
      org.opencontainers.image.description="Constitutional AI governance with message bus" \
      org.opencontainers.image.vendor="ACGS-2" \
      org.opencontainers.image.version="2.0.0" \
      org.opencontainers.image.source="https://github.com/dislovelhl/acgs2/enhanced-agent-bus" \
      acgs.io/constitutional-hash="cdd01ef066bc6cf2"

# Security: Create non-root user and group
RUN groupadd -r appgroup -g 1000 && \
    useradd -r -g appgroup -u 1000 appuser && \
    mkdir -p /app /app/data /app/logs && \
    chown -R appuser:appgroup /app

# Security: Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libssl3 \
    libffi8 \
    procps \
    curl \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && rm -rf /tmp/* /var/tmp/*

# Security: Remove unnecessary files and capabilities
RUN find /usr -name "*.pyc" -delete && \
    find /usr -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

WORKDIR /app

# Copy Python virtual environment
COPY --from=python-deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy built Rust library
COPY --from=maturin-builder /app/dist/*.whl /tmp/
RUN pip install /tmp/*.whl

# Copy application code with proper ownership
COPY --chown=appuser:appgroup . .

# Security: Ensure proper file permissions
RUN chmod 755 /app && \
    chmod 644 /app/*.py && \
    find /app -type f -name "*.sh" -exec chmod 755 {} \; 2>/dev/null || true

# Security: Create health check script
RUN echo '#!/bin/bash\n\
curl -f http://localhost:8000/health/live || exit 1' > /usr/local/bin/healthcheck.sh && \
    chmod +x /usr/local/bin/healthcheck.sh

# Security: Switch to non-root user
USER appuser

# Expose ports
EXPOSE 8000 9090

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD /usr/local/bin/healthcheck.sh

# Security: Use exec form for CMD to avoid shell injection
CMD ["python", "-m", "enhanced_agent_bus.agent_bus"]
