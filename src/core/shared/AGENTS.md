# Shared Core

> Scope: `src/core/shared/` — Cross-cutting infrastructure used by API Gateway and all services.

## Structure

```
shared/
├── types/                  # Pydantic models, enums, type definitions
├── config/                 # Settings factory (Pydantic BaseSettings)
├── auth/                   # JWT, SAML, SSO (WorkOS), cert binding
├── security/               # CORS, rate limiting, PII, crypto, CSRF (see security/AGENTS.md)
├── acgs_logging/           # Structured logging + audit logger (Redis-backed)
├── metrics/                # Prometheus instrumentation (fire-and-forget)
├── errors/                 # Error hierarchy + deprecated logging module
├── cache/                  # Caching abstractions
├── crypto/                 # Cryptographic utilities
├── database/               # DB connection pooling
├── resilience/             # Retry, circuit breaker patterns
├── orchestration/          # Service orchestration utilities
├── policy/                 # Policy evaluation helpers
├── event_schemas/          # Event-driven architecture schemas
├── utilities/              # General-purpose helpers
├── constants.py            # Constitutional hash, version strings
├── constitutional_hash.py  # Hash validation with version deprecation
├── di_container.py         # Dependency injection container
├── enums.py                # Shared enumerations
├── fastapi_base.py         # Base FastAPI app factory
├── feature_flags.py        # Feature flag evaluation
├── http_client.py          # HTTPX client wrapper
├── interfaces.py           # Abstract protocols
├── redis_config.py         # Redis connection config
├── structured_logging.py   # Structlog setup (canonical)
└── type_guards.py          # Runtime type narrowing
```

## Where to Look

| Task                       | Location                     |
| -------------------------- | ---------------------------- |
| Add shared type/model      | `types/`                     |
| Change config settings     | `config/` (Pydantic)         |
| Auth middleware             | `auth/`, `security/auth.py`  |
| Rate limiting              | `security/rate_limiter.py`   |
| Structured logging         | `structured_logging.py`      |
| Prometheus metrics         | `metrics/__init__.py`        |
| Constitutional hash verify | `constitutional_hash.py`     |
| Feature flags              | `feature_flags.py`           |

## Conventions

- All config via Pydantic `BaseSettings` — never raw `os.environ`.
- Metrics are fire-and-forget — failures NEVER block the application.
- Audit queries ALWAYS scoped to requesting tenant (no cross-tenant access).
- `structured_logging.py` is canonical — `errors/logging.py` is deprecated (zero consumers).
- `PYTHONPATH=src/` required for imports to resolve.

## Anti-Patterns

- Do not use `errors/logging.py` — use `structured_logging.py` instead.
- Do not access metrics `.labels()` on `None` — check `METRICS_ENABLED` first.
- Do not hardcode config values — use `config/` settings factory.
- Do not create Redis connections directly — use `redis_config.py`.
