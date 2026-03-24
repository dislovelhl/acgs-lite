# Security Subsystem

> Scope: `src/core/shared/security/` — shared auth, CORS, rate limiting, crypto, privacy, and
> request-hardening utilities.

## Structure

```
security/
├── auth.py
├── auth_dependency.py
├── cors_config.py
├── rate_limiter.py
├── rate_limiting/          # Rate-limiting support types
├── token_revocation.py
├── input_validator.py
├── pii_detector.py
├── pqc.py
├── pqc_crypto.py
├── encryption.py
├── csrf.py
├── security_headers.py
├── error_handler_middleware.py
├── error_sanitizer.py
├── sandbox.py
├── secret_rotation.py
├── rotation/               # Rotation backends and models
├── tenant_context.py
├── gdpr_erasure.py
├── ccpa_handler.py
├── data_classification.py
├── agent_checksum.py
├── cert_binding.py
├── context_integrity.py
├── dual_key_jwt.py
├── execution_time_limit.py
├── expression_utils.py
├── oauth_state_manager.py
├── service_auth.py
├── spiffe_identity.py
├── spiffe_san.py
├── retention_policy.py
├── testing.py
└── tests/
```

## Where to Look

| Task | Location |
| ---- | -------- |
| CORS policy changes | `cors_config.py` |
| JWT / auth flow | `auth.py`, `auth_dependency.py`, `dual_key_jwt.py` |
| Rate limiting | `rate_limiter.py`, `rate_limiting/` |
| PII detection | `pii_detector.py` |
| Post-quantum crypto | `pqc.py`, `pqc_crypto.py` |
| Token revocation | `token_revocation.py` |
| Input sanitization | `input_validator.py`, `deserialization.py` |
| GDPR / CCPA | `gdpr_erasure.py`, `ccpa_handler.py` |
| Secret rotation | `secret_rotation.py`, `rotation/` |

## Anti-Patterns

- Never allow wildcard CORS with credentials.
- Never ship placeholder secrets in production configuration.
- Do not fail open on policy or tenant-isolation checks unless the design explicitly requires it
  and the fallback is reviewed.
- Do not bypass shared auth, revocation, or sanitization helpers in service code.

## Conventions

- Keep production security defaults strict and explicit.
- Prefer shared middleware/helpers over service-local security forks.
- Add or update tests in `tests/` when changing auth, CORS, crypto, or validation behavior.
