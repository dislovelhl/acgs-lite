# Shared Core

> Scope: `src/core/shared/` — cross-cutting infrastructure shared across services.

## Structure

```
shared/
├── types/                  # Shared types and protocols
├── config/                 # Settings and configuration factories
├── auth/                   # OIDC, SAML, provisioning, WorkOS helpers
├── security/               # Auth, CORS, crypto, rate limiting, PII, retention
├── acgs_logging/           # Structured logging and audit events
├── metrics/                # Metrics helpers
├── cache/                  # Cache abstractions and models
├── crypto/                 # Cryptographic utilities
├── database/               # DB session and middleware helpers
├── errors/                 # Shared error definitions
├── event_schemas/          # Event payload schemas
├── orchestration/          # Orchestration utilities
├── policy/                 # Policy helpers and models
├── resilience/             # Retry helpers
├── utilities/              # General utilities
├── constants.py
├── constitutional_hash.py
├── di_container.py
├── fastapi_base.py
├── feature_flags.py
├── http_client.py
├── redis_config.py
└── structured_logging.py
```

## Where to Look

| Task | Location |
| ---- | -------- |
| Add shared type/model | `types/` |
| Change settings/config | `config/` |
| Auth helpers | `auth/`, `security/auth.py`, `security/auth_dependency.py` |
| Rate limiting | `security/rate_limiter.py` |
| Structured logging | `structured_logging.py`, `acgs_logging/` |
| Metrics helpers | `metrics/` |
| Constitutional hash verification | `constitutional_hash.py`, `constants.py` |
| Feature flags | `feature_flags.py` |

## Conventions

- Prefer typed settings and shared helpers over ad hoc environment access in service code.
- Keep tenant scoping explicit in audit and security-sensitive paths.
- `structured_logging.py` is the canonical logging setup.
- Reuse shared Redis, HTTP, and DI helpers instead of open-coding those concerns in services.

## Anti-Patterns

- Do not add new call sites to deprecated logging helpers when `structured_logging.py` already
  covers the need.
- Do not hardcode service configuration values in callers.
- Do not create ad hoc Redis connections when shared config/helpers exist.
