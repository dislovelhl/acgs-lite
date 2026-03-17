# Production Dockerfile for Governance Service (Enhanced Agent Bus)
# Build Context: src/core/
# Command: docker build -f enhanced_agent_bus/Dockerfile .

# Stage 1: Build Rust Optimization Kernel
FROM python:3.12-slim as builder

# Install Rust toolchain and build tools
RUN apt-get update && apt-get install -y curl build-essential \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /build

# Copy Rust crate source
COPY rust-perf/ ./rust-perf/

# Build wheel using maturin
RUN pip install maturin
WORKDIR /build/rust-perf
RUN maturin build --release --out dist

# Stage 2: Runtime Environment
FROM python:3.12-slim

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security (Constitutional Hash: cdd01ef066bc6cf2)
RUN groupadd -r acgs --gid=1000 && \
    useradd -r -g acgs --uid=1000 --home-dir=/app --shell=/sbin/nologin acgs && \
    mkdir -p /app && chown -R acgs:acgs /app

WORKDIR /app

# Install Python dependencies
# Using CPU-only PyTorch to minimize image size (~200MB instead of 800MB)
RUN pip install --no-cache-dir \
    fastapi==0.115.6 \
    uvicorn[standard]==0.32.1 \
    redis>=5.0.0 \
    httpx>=0.27.0 \
    pydantic>=2.12.1 \
    litellm>=1.61.6 \
    slowapi>=0.1.9 \
    msgpack>=1.0.0 \
    asyncpg>=0.29.0 \
    prometheus-client>=0.20.0 \
    orjson>=3.9.0 \
    numpy \
    torch --index-url https://download.pytorch.org/whl/cpu

# Copy built Rust extension wheel
COPY --from=builder /build/rust-perf/dist/*.whl /tmp/
RUN pip install /tmp/*.whl

# Copy Service Code
COPY enhanced_agent_bus/ .

# Environment Configuration
ENV PYTHONPATH=/app
ENV MODULE_NAME=api

# Security: Run as non-root user
USER 1000:1000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run Application
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
