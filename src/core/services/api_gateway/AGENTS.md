# API Gateway

> Scope: `src/core/services/api_gateway/` — unified ingress, auth, rate limiting, and SSO.

## Structure

```
api_gateway/
├── main.py                 # FastAPI entrypoint
├── lifespan.py             # Startup/shutdown wiring
├── health.py               # Health endpoints and checks
├── metrics.py              # Metrics endpoint
├── redis_backend.py        # Redis-backed state helpers
├── workos_event_ingestion.py
├── middleware/
│   ├── load_shedding.py
│   ├── autonomy_tier.py
│   └── pqc_only_mode.py
├── routes/
│   ├── admin_sso.py
│   ├── admin_workos.py
│   ├── autonomy_tiers.py
│   ├── compliance.py
│   ├── data_subject.py
│   ├── decisions.py
│   ├── evolution_control.py
│   ├── feedback.py
│   ├── pipeline_metrics.py
│   ├── pqc_phase5.py
│   ├── proxy.py
│   └── x402_governance.py
├── models/                 # Gateway-local models
├── repositories/           # Gateway persistence helpers
├── schemas/                # Gateway schemas
└── tests/                  # Gateway test suite
```

## Where to Look

| Task | Location |
| ---- | -------- |
| Add API route | `routes/` |
| Auth dependency | `src/core/shared/security/auth_dependency.py` |
| Rate limiting | `src/core/shared/security/rate_limiter.py` |
| CORS config | `src/core/shared/security/cors_config.py` |
| Load shedding | `middleware/load_shedding.py` |
| WorkOS flows | `routes/admin_workos.py`, `workos_event_ingestion.py` |
| Health probes | `health.py` |

## Conventions

- Reuse shared security/auth code from `src/core/shared/security/`.
- Keep protected-route auth explicit through FastAPI dependencies.
- Preserve governance/health load-shedding invariants.
- Keep SSO-specific dependencies isolated to the documented SSO surfaces.

## Anti-Patterns

- Do not create gateway-local replacements for shared auth/security modules.
- Do not use wildcard CORS with credentials.
- Do not treat governance or health traffic as shed-safe by default.

## Commands

```bash
make test-gw
python -m pytest src/core/services/api_gateway/tests/ -v --import-mode=importlib
```
