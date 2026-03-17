# API Auth Boundary

## Public endpoints (`/v1/*`)

- `POST /v1/validate` requires `X-API-Key` via `require_api_key`
- `GET /v1/usage` requires `X-API-Key` via `require_api_key`
- `GET /v1/stats` requires `X-API-Key` via `require_api_key` (from `stats.py`)
- `GET /api/v1/stats` requires `X-API-Key` via `require_api_key` (from `health.py`)
- `POST /v1/signup` is development-only and blocked in production

## Internal endpoints (`/api/v1/*`)

- `POST /api/v1/messages`
- `GET /api/v1/messages/{message_id}`
- `POST /api/v1/policies/validate`
- `POST /api/v1/batch/validate`
- `GET /api/v1/governance/stability/metrics`

These endpoints depend on `get_tenant_id` (from `_tenant_auth.py`) and tenant context middleware.
In production the shared security package provides `get_tenant_id`; in development a fallback
reads the `X-Tenant-ID` header directly. The fallback raises HTTP 503 if used outside dev environments.

## Public unauthenticated utility endpoints

- `GET /health`
- `GET /v1/health`
- `GET /v1/badge/{agent_id}`
- `GET /v1/widget.js`
