# ACGS-Lite Constitutional Sentinel — Cloud Run deployment
# Serves GitLab webhook events and exposes governance tools via HTTP.
#
# Build:  docker build -t acgs-sentinel .
# Run:    docker run -p 8080:8080 -e GITLAB_TOKEN=... -e GITLAB_PROJECT_ID=... acgs-sentinel
# Deploy: gcloud run deploy acgs-sentinel --source . --region us-central1
#
# Environment variables:
#   GITLAB_TOKEN          — GitLab API token (api scope)
#   GITLAB_PROJECT_ID     — Numeric project ID
#   GITLAB_WEBHOOK_SECRET — Webhook secret for signature verification
#   CONSTITUTION_PATH     — Path to constitution YAML (optional, uses built-in gitlab template)
#   GCP_PROJECT_ID        — GCP project for Cloud Logging (optional, uses ADC)
#   PORT                  — Server port (default: 8080)

FROM python:3.11-slim

WORKDIR /app

# Install production dependencies only
COPY pyproject.toml .
RUN pip install --no-cache-dir "acgs-lite[gitlab,google-cloud] @ ." 2>/dev/null || \
    pip install --no-cache-dir \
        pydantic>=2.0 \
        pyyaml>=6.0 \
        click>=8.0 \
        httpx>=0.27 \
        starlette>=0.27 \
        uvicorn[standard]>=0.20 \
        google-cloud-logging>=3.0

# Copy source
COPY src/ src/

# Install the package itself (editable not needed for production)
RUN pip install --no-cache-dir -e ".[gitlab,google-cloud]"

# Create non-root user for Cloud Run security best practices
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

# Cloud Run injects PORT; default 8080
ENV PORT=8080

EXPOSE 8080

CMD uvicorn acgs_lite.integrations.cloud_run_server:app \
    --host 0.0.0.0 \
    --port ${PORT} \
    --workers 1 \
    --log-level info
