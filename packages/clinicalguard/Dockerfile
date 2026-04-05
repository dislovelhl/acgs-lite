FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for runtime
RUN groupadd -r clinicalguard && useradd -r -g clinicalguard -d /app -s /sbin/nologin clinicalguard

# Copy packages
COPY packages/acgs-lite /app/packages/acgs-lite
COPY packages/clinicalguard /app/packages/clinicalguard

# Install Python deps
RUN pip install --no-cache-dir \
    starlette \
    "uvicorn[standard]" \
    pyyaml \
    anthropic \
    httpx \
    pydantic \
    && pip install --no-cache-dir -e /app/packages/acgs-lite

# clinicalguard is resolved via PYTHONPATH (flat layout)
ENV PYTHONPATH=/app/packages

# Create data directory for audit log with correct ownership
RUN mkdir -p /data /home/clinicalguard \
    && chown clinicalguard:clinicalguard /data /home/clinicalguard

# Default audit log to persistent volume, not /tmp
ENV CLINICALGUARD_AUDIT_LOG=/data/clinicalguard_audit.json
ENV HOME=/home/clinicalguard

VOLUME /data

EXPOSE 8080

# Switch to non-root user
USER clinicalguard

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["uvicorn", "clinicalguard.main:app", "--host", "0.0.0.0", "--port", "8080"]
