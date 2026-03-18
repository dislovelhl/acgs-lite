# API Gateway

> Scope: `src/core/services/api_gateway/` — Port 8080. Unified ingress, auth, rate limiting, SSO.

## Structure

```
api_gateway/
├── main.py              # FastAPI entrypoint, middleware wiring, service init
├── health.py            # Health checks (/health, /health/live, /health/ready)
├── metrics.py           # Prometheus /metrics endpoint
├── redis_backend.py     # Redis state management
├── middleware/
│   └── load_shedding.py # Priority-based load shedding (NEVER_SHED governance/health)
├── routes/
│   ├── compliance.py        # Compliance endpoints
│   ├── x402_governance.py   # Governance/payment routing
│   ├── decisions.py         # Decision APIs
│   ├── admin_workos.py      # WorkOS admin APIs
│   ├── sso/workos.py        # WorkOS SSO handlers
│   └── ...
├── tests/
│   └── unit/            # API Gateway unit tests
├── Dockerfile.dev       # Development Docker image
├── requirements.txt     # Core dependencies
└── requirements-sso.txt # SSO/SAML dependencies (pysaml2, xmlsec1)
```

## Where to Look

| Task                       | Location                                     |
| -------------------------- | -------------------------------------------- |
| Add API route              | `routes/` (follow existing pattern)          |
| Auth middleware             | `src/core/shared/security/auth.py` (canonical)|
| Rate limiting              | `src/core/shared/security/rate_limiter.py`   |
| CORS config                | `src/core/shared/security/cors_config.py`    |
| Load shedding              | `middleware/load_shedding.py`                |
| WorkOS SSO                 | `routes/sso/workos.py`                       |
| Health probes              | `health.py`                                  |

## Conventions

- `PYTHONPATH=src/` required for all imports.
- JWT auth on all protected routes via FastAPI `Depends()`.
- Rate limiting via shared `rate_limiter.py` (not gateway-local).
- Load shedding `NEVER_SHED` frozenset: governance and health requests are never shed (CI-2).
- WorkOS endpoints gated by `WORKOS_ENABLED=true`.

## Anti-Patterns

- Do not create gateway-local auth — use `src/core/shared/security/`.
- Do not use `allow_origins=["*"]` — explicit allowlists only (raises `ValueError` in prod).
- Do not shed governance or health requests — `NEVER_SHED` invariant is constitutional.

## Commands

```bash
make test-gw                                    # Gateway tests
pytest src/core/services/api_gateway/tests/ -v  # Direct
```
