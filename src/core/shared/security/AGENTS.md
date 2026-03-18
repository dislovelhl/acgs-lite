# Security Subsystem

> Scope: `src/core/shared/security/` — 38 files. CORS, auth, rate limiting, PII, crypto, CSRF, PQC.

## Structure

```
security/
├── auth.py                 # JWT validation + user context extraction
├── auth_dependency.py      # FastAPI Depends() auth injection
├── cors_config.py          # CORS configuration (NEVER wildcard + creds)
├── rate_limiter.py         # Token bucket rate limiting (canonical)
├── rate_limiting/          # Rate limiting backends
├── token_revocation.py     # JWT blacklisting (must survive Redis down)
├── input_validator.py      # Input sanitization
├── pii_detector.py         # PII detection and redaction
├── pqc_crypto.py           # Post-quantum cryptography (liboqs)
├── pqc.py                  # PQC key management
├── encryption.py           # Symmetric/asymmetric encryption
├── csrf.py                 # CSRF token handling
├── security_headers.py     # Security headers middleware
├── error_sanitizer.py      # Error response sanitization
├── sandbox.py              # Sandboxed execution
├── secret_rotation.py      # Secret rotation lifecycle
├── rotation/               # Rotation backends
├── tenant_context.py       # Tenant isolation enforcement
├── gdpr_erasure.py         # GDPR right-to-erasure
├── ccpa_handler.py         # CCPA data handling
├── data_classification.py  # Data sensitivity classification
├── agent_checksum.py       # Agent integrity verification
├── cert_binding.py         # Certificate binding
├── context_integrity.py    # Request context integrity
├── dual_key_jwt.py         # Dual-key JWT for enhanced security
├── execution_time_limit.py # Request timeout enforcement
├── expression_utils.py     # Safe expression evaluation
├── oauth_state_manager.py  # OAuth state CSRF protection
├── spiffe_identity.py      # SPIFFE identity verification
├── spiffe_san.py           # SPIFFE SAN validation
├── url_file_validator.py   # URL/file path validation
├── service_auth.py         # Service-to-service auth
├── error_handler_middleware.py # Global error handler
└── tests/                  # 17 security test files
```

## Where to Look

| Task                        | Location                    |
| --------------------------- | --------------------------- |
| CORS policy changes         | `cors_config.py`            |
| JWT auth flow               | `auth.py`, `dual_key_jwt.py`|
| Rate limiting               | `rate_limiter.py`           |
| PII detection               | `pii_detector.py`           |
| Post-quantum crypto         | `pqc_crypto.py`, `pqc.py`  |
| Token revocation            | `token_revocation.py`       |
| Input sanitization          | `input_validator.py`        |
| GDPR/CCPA compliance        | `gdpr_erasure.py`, `ccpa_handler.py` |
| Secret rotation             | `secret_rotation.py`, `rotation/` |

## Anti-Patterns (CRITICAL)

- **NEVER** `allow_origins=["*"]` with `allow_credentials=True` — raises `ValueError` in prod.
- **NEVER** wildcard CORS origins in production — explicit allowlists only.
- **NEVER** use placeholder secrets (`"PLACEHOLDER"`, `"CHANGE_ME"`, `"dev-secret"`) — raises `ValueError`.
- **NEVER** commit `sp.key` (SAML private key) to version control.
- Token revocation must survive Redis downtime — fail-open with logging, not crash.
- OPA evaluation is ALWAYS fail-closed (VULN-002) — no fail-open override.
- Tenant queries ALWAYS scoped — no cross-tenant access to audit/security data.
