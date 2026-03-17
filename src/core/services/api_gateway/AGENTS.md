# AGENTS.md - API Gateway

Scope: `src/core/services/api_gateway/`

## Overview

Unified ingress for ACGS-2. Port 8080. Load balancing, rate limiting, request routing, authentication gateway.

**Constitutional Hash:** `cdd01ef066bc6cf2`

## Structure

`main.py` - FastAPI entrypoint, service initialization
`health.py` - Health checks and readiness probes
`metrics.py` - Prometheus metrics endpoint
`redis_backend.py` - Redis integration for state
`routes/` - API route modules

## Where to Look

Ingress configuration: `main.py`
Rate limiting: `src/core/shared/security/rate_limiter.py` (canonical)
Circuit breaker: `src/core/shared/circuit_breaker/` (canonical)
Route handlers: `routes/`
