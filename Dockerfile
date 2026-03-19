# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
COPY packages/acgs-lite/pyproject.toml packages/acgs-lite/pyproject.toml
COPY packages/enhanced_agent_bus/pyproject.toml packages/enhanced_agent_bus/pyproject.toml
RUN uv sync --no-dev --frozen 2>/dev/null || uv pip install --system -e ".[test]"

# Copy source
COPY . .
RUN uv pip install --system -e . -e packages/acgs-lite -e packages/enhanced_agent_bus

# Agent Bus service
FROM base AS agent-bus
EXPOSE 8000
CMD ["uvicorn", "enhanced_agent_bus.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

# API Gateway service
FROM base AS api-gateway
EXPOSE 8080
CMD ["uvicorn", "src.core.services.api_gateway.main:app", "--host", "0.0.0.0", "--port", "8080"]
