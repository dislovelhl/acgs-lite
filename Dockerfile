# Constitutional Hash: cdd01ef066bc6cf2
# ACGS-Lite Cloud Run Deployment
# Minimal production image for GitLab AI Governance Bot

FROM python:3.11-slim AS base

# Prevent .pyc files and enable unbuffered stdout for Cloud Run logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system deps (none needed beyond slim defaults)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Copy and install the package
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN pip install --no-cache-dir ".[google-cloud]" "starlette>=0.27" "uvicorn[standard]>=0.24" "httpx>=0.27"

# Non-root user for production security
RUN useradd --create-home appuser
USER appuser

# Cloud Run default port
ENV PORT=8080
EXPOSE 8080

# Health check against the /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Run the Cloud Run server
CMD ["python", "-m", "uvicorn", "acgs_lite.integrations.cloud_run_server:app", "--host", "0.0.0.0", "--port", "8080"]
