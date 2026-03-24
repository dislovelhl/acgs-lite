# ACGS-2 Core Services API Reference

> Constitutional Hash: `cdd01ef066bc6cf2` — embedded in all validation paths, response headers, and JWT claims.

**Audience**: Backend engineers working on auth, gateway routing, or adding new routes.
**Source root**: `src/core/`
**Entry point**: `src/core/services/api_gateway/main.py`
**Port**: 8080 (uvloop + httptools, production-bound to `127.0.0.1`)

---

## Table of Contents

1. [API Gateway Overview](#1-api-gateway-overview)
2. [Route Reference](#2-route-reference)
3. [Security Module](#3-security-module)
4. [Auth Module](#4-auth-module)
5. [Config Module](#5-config-module)
6. [Types Reference](#6-types-reference)
7. [Error Handling](#7-error-handling)
8. [Cache Layer](#8-cache-layer)
9. [Observability](#9-observability)

---

## 1. API Gateway Overview

### Entry Point

`src/core/services/api_gateway/main.py` creates a FastAPI application via `create_acgs_app()` (from `src.core.shared.fastapi_base`). OpenAPI docs (`/docs`, `/redoc`, `/openapi.json`) are only exposed when `ENVIRONMENT` is in `{development, dev, test, testing, ci}`.

### Middleware Stack Order

Starlette/FastAPI applies middleware in reverse registration order (last-added runs first on the way in). Registration order in `main.py`, from first-added to last-added:

| # | Middleware | Purpose |
|---|-----------|---------|
| 1 | `GZipMiddleware(minimum_size=1000)` | Compress responses > 1 KB |
| 2 | `APIVersioningMiddleware` | URL-path versioning, injects `X-API-Version` header |
| 3 | `DeprecationNoticeMiddleware` | Adds `X-API-Deprecated` on legacy routes |
| 4 | `SecurityHeadersMiddleware` | CSP, X-Frame-Options, HSTS, etc. |
| 5 | `SessionMiddleware` | Cookie: `acgs2_session`, `SameSite=None` when SAML enabled |
| 6 | `RateLimitMiddleware` | Redis-backed sliding window (see Section 3.2) |
| 7 | `PQCOnlyModeMiddleware` | Rejects classical-algorithm requests when PQC mode active |
| 8 | `AutonomyTierEnforcementMiddleware` | HITL enforcement per agent tier |

**Execution order on inbound request** (last-registered runs first): AutonomyTier → PQCOnlyMode → RateLimit → Session → SecurityHeaders → Deprecation → APIVersioning → GZip → route handler.

### Versioning

- URL-path versioning: `/api/v1/`, `/api/v2/`
- Default version: `v1`
- `strict_versioning = False` — unversioned paths are allowed for backward compatibility
- Exempt paths (no version enforcement): `/health*`, `/metrics`, `/docs`, `/openapi.json`, `/redoc`, `/favicon.ico`
- Response headers added by versioning middleware: `X-API-Version`, `X-API-Deprecated`, `X-Constitutional-Hash`

### Lifespan (`lifespan.py`)

On startup:
1. Verifies `CONSTITUTIONAL_HASH` env var matches the code constant via `_verify_constitutional_hash_at_startup()`. Raises `RuntimeError` in production on mismatch or absence.
2. Creates `HttpHitlSubmissionClient` pointed at `HITL_URL` (default: `http://localhost:8002`), stored in `app.state.hitl_client`.
3. Initialises self-evolution operator control plane (memory or Redis backend, configurable via `SELF_EVOLUTION_OPERATOR_CONTROL_BACKEND`).

On shutdown: closes operator control plane, proxy HTTP client, feedback Redis connection.

---

## 2. Route Reference

### 2.1 Health (`health.py`)

No authentication. Not subject to versioning middleware. Rate limit: 6000 req/min.

| Method | Path | Response | Notes |
|--------|------|----------|-------|
| GET | `/health` | `BasicHealthResponse` | Always 200 if process alive |
| GET | `/health/live` | `LivenessResponse` | Kubernetes liveness probe |
| GET | `/healthz` | `LivenessResponse` | Alias for `/health/live` |
| GET | `/health/ready` | `ReadinessResponse` | Checks DB, Redis, OPA, constitutional hash. Returns 503 if any dependency is down |
| GET | `/readyz` | `ReadinessResponse` | Alias for `/health/ready` |
| GET | `/health/startup` | `StartupResponse` | Lightweight: validates constitutional hash only, no external calls |
| GET | `/startupz` | `StartupResponse` | Alias for `/health/startup` |

**Readiness probe** accepts optional `X-Constitutional-Hash` header; a mismatch marks the `probe_header` check as down.

**Constitutional hash check** uses `hmac.compare_digest` to prevent timing attacks.

**Dependency check concurrency**: all four checks (database, redis, opa, constitutional_hash) run via `asyncio.gather()` with `return_exceptions=True`.

Response models:

```python
class BasicHealthResponse(BaseModel):
    status: str = "ok"
    constitutional_hash: str

class ReadinessResponse(BaseModel):
    ready: bool
    constitutional_hash: str
    checks: dict[str, DependencyCheck]  # keys: database, redis, opa, constitutional_hash
    timestamp: str  # ISO 8601

class DependencyCheck(BaseModel):
    status: str       # "up" | "down" | "degraded"
    latency_ms: float
    error: str | None
```

---

### 2.2 SSO (`/api/v1/sso/*`)

Router prefix: `/api/v1/sso`. OIDC and SAML sub-routers are mounted at `/oidc` and `/saml` respectively.

#### Session

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/api/v1/sso/session` | None | Returns `{authenticated, user}` from Starlette session cookie |

#### OIDC (`/api/v1/sso/oidc/*`)

Implemented in `routes/sso/oidc.py`. Rate limit on login: 5 req/min per IP.

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/api/v1/sso/oidc/login` | None | Redirects to IdP, sets PKCE code verifier in session |
| GET | `/api/v1/sso/oidc/callback` | None | Exchanges code, provisions user via JIT provisioner, sets session |
| POST | `/api/v1/sso/oidc/logout` | Session | Clears session, optionally calls IdP end_session endpoint |

OIDC uses PKCE by default (`OIDC_USE_PKCE=true`). State is stored in the Starlette session cookie.

#### SAML (`/api/v1/sso/saml/*`)

Implemented in `routes/sso/saml.py`. `SameSite=None` is required on the session cookie for cross-site ACS POST. Rate limit on login: 5 req/min per IP.

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/api/v1/sso/saml/login` | None | Returns SAML AuthnRequest redirect URL |
| POST | `/api/v1/sso/saml/acs` | None | Assertion Consumer Service; processes SAMLResponse |
| GET | `/api/v1/sso/saml/metadata` | None | Returns SP metadata XML |
| GET/POST | `/api/v1/sso/saml/logout` | Session | Initiates SLO |

#### WorkOS (`/api/v1/sso/workos/*`)

Implemented in `routes/sso/workos.py`. Only active when `WORKOS_ENABLED=true`.

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/api/v1/sso/workos/login` | None | Redirects to WorkOS AuthKit |
| GET | `/api/v1/sso/workos/callback` | None | Handles WorkOS callback |
| POST | `/api/v1/sso/workos/webhook` | HMAC | Processes WorkOS webhook events |

---

### 2.3 Admin SSO (`/api/v1/admin/sso/*`)

Implemented in `routes/admin_sso.py`. Requires `admin` role.

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/api/v1/admin/sso/providers` | JWT + admin | List configured SSO providers |
| POST | `/api/v1/admin/sso/providers` | JWT + admin | Register new SSO provider |
| PUT | `/api/v1/admin/sso/providers/{name}` | JWT + admin | Update provider config |
| DELETE | `/api/v1/admin/sso/providers/{name}` | JWT + admin | Remove provider |
| GET | `/api/v1/admin/sso/role-mappings` | JWT + admin | List IdP group → ACGS role mappings |
| POST | `/api/v1/admin/sso/role-mappings` | JWT + admin | Create role mapping |

---

### 2.4 Admin WorkOS (`/api/v1/admin/sso/workos/*`)

Implemented in `routes/admin_workos.py`. Requires `admin` role.

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/api/v1/admin/sso/workos/portal-links` | JWT + admin | Generate WorkOS Admin Portal link |
| GET | `/api/v1/admin/sso/workos/events` | JWT + admin | Pull WorkOS event log |

---

### 2.5 Decisions (`/api/v1/decisions/*`)

Implemented in `routes/decisions.py`. FR-12 Decision Explanation API. Requires JWT.

| Method | Path | Auth | Query params | Notes |
|--------|------|------|-------------|-------|
| GET | `/api/v1/decisions/{decision_id}/explain` | JWT | `include_counterfactuals=true` | Retrieve stored explanation |
| POST | `/api/v1/decisions/explain` | JWT | — | Generate and store new explanation |
| GET | `/api/v1/decisions/governance-vector/schema` | JWT | — | Returns 7-dimension schema |

**Governance vector dimensions**: safety, security, privacy, fairness, reliability, transparency, efficiency. Each is a float in [0.0, 1.0]. Escalation threshold: 0.8.

**Delegation**: `GET` and `POST /explain` delegate to `ExplanationServiceAdapter` from `enhanced_agent_bus.facades.agent_bus_facade`.

---

### 2.6 Data Subject Rights (`/api/v1/data-subject/*`)

Implemented in `routes/data_subject.py`. GDPR/CCPA §16.4. Requires JWT.

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/api/v1/data-subject/access` | JWT | GDPR Art. 15 / CCPA §1798.100 right of access |
| POST | `/api/v1/data-subject/erasure` | JWT | GDPR Art. 17 / CCPA §1798.105 right to erasure |
| POST | `/api/v1/data-subject/rectification` | JWT | GDPR Art. 16 right to rectification |
| POST | `/api/v1/data-subject/portability` | JWT | GDPR Art. 20 data portability |
| POST | `/api/v1/data-subject/opt-out` | JWT | CCPA §1798.120 opt-out of sale |
| GET | `/api/v1/data-subject/requests/{request_id}` | JWT | Status of a pending request |

Delegtes erasure to `GDPRErasureHandler` when `GDPR_ERASURE_AVAILABLE`. Delegates PII detection to `PIIDetector` when `PII_DETECTOR_AVAILABLE`.

---

### 2.7 Compliance (`/api/v1/compliance/*`)

Implemented by shim at `routes/compliance.py`, which imports `src.core.services.compliance.router`. Falls back to an empty router on `ImportError`.

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/api/v1/compliance/assess` | JWT | EU AI Act compliance assessment |
| GET | `/api/v1/compliance/gaps/{system_id}` | JWT | Compliance gap analysis |

---

### 2.8 Admin Autonomy Tiers (`/api/v1/admin/autonomy-tiers/*`)

Implemented in `routes/autonomy_tiers.py`. Safe Autonomy Tiers (ACGS-AI-007). Requires JWT. Backed by PostgreSQL (`DATABASE_URL`) and Redis (`REDIS_URL`).

| Method | Path | Auth | Body / Params | Notes |
|--------|------|------|--------------|-------|
| GET | `/api/v1/admin/autonomy-tiers` | JWT | — | List all tier assignments |
| POST | `/api/v1/admin/autonomy-tiers` | JWT | `AgentTierAssignmentCreate` | Create assignment |
| GET | `/api/v1/admin/autonomy-tiers/{agent_id}` | JWT | — | Get assignment for agent |
| PUT | `/api/v1/admin/autonomy-tiers/{agent_id}` | JWT | `AgentTierAssignmentUpdate` | Update tier |
| DELETE | `/api/v1/admin/autonomy-tiers/{agent_id}` | JWT | — | Remove assignment |

DB session injected via `get_db_session()` dependency (overridable via `app.dependency_overrides`).

---

### 2.9 Self-Evolution Evidence (`/api/v1/admin/evolution/*`)

Requires `admin` role (enforced at router registration via `Depends(require_role("admin"))`). Available only when `src.core.self_evolution.api` is importable.

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/api/v1/admin/evolution/bounded-experiments` | JWT + admin | List evidence records |
| GET | `/api/v1/admin/evolution/bounded-experiments/{evidence_id}` | JWT + admin | Get single evidence record |

---

### 2.10 Self-Evolution Operator Control (`/api/v1/admin/evolution/operator-control*`)

Requires `admin` role.

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/api/v1/admin/evolution/operator-control/pause` | JWT + admin | Pause evolution experiment |
| POST | `/api/v1/admin/evolution/operator-control/resume` | JWT + admin | Resume paused experiment |
| POST | `/api/v1/admin/evolution/operator-control/stop` | JWT + admin | Hard-stop experiment |
| GET | `/api/v1/admin/evolution/operator-control/status` | JWT + admin | Current control plane status |

---

### 2.11 PQC Phase 5 Admin (`/api/v1/admin/pqc/*`)

Implemented in `routes/pqc_phase5.py`. Loaded with `try/except ImportError`.

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/api/v1/admin/pqc/pqc-only-mode/activate` | JWT + admin | Enable PQC-only mode globally |
| GET | `/api/v1/admin/pqc/pqc-only-mode/status` | JWT | Current PQC mode status |

When active, `PQCOnlyModeMiddleware` (registered in the main middleware stack) rejects any requests using classical cryptographic algorithms before they reach route handlers.

---

### 2.12 x402 Governance-as-a-Service (`/x402/*`)

Implemented in `routes/x402_governance.py`. Pay-per-call constitutional validation over the x402 micropayment protocol. Requires JWT for non-public endpoints.

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/x402/health` | None | x402 service health |
| GET | `/x402/pricing` | None | Current price and network info |
| POST | `/x402/validate` | JWT | Constitutional validation (charges USDC via x402) |

Configuration env vars: `X402_GOVERNANCE_PRICE` (default: `0.001`), `X402_NETWORK` (default: `eip155:84532`), `EVM_ADDRESS`, `FACILITATOR_URL`.

`POST /x402/validate` body:
```python
class GovernanceValidationRequest(BaseModel):
    action: str           # max 5000 chars
    agent_id: str = "anonymous"
    context: dict = {}
```

Response:
```python
class GovernanceValidationResponse(BaseModel):
    compliant: bool
    constitutional_hash: str
    decision: str   # APPROVED | BLOCKED | REVIEW_REQUIRED
    confidence: float
    violations: list[str]
```

---

### 2.13 Gateway v1 / Feedback (`/api/v1/gateway/*`)

Implemented in `routes/feedback.py`, exported as `gateway_v1_router`. Handles operator feedback submission.

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/api/v1/gateway/feedback` | JWT (optional) | Submit feedback on agent decisions |
| GET | `/api/v1/gateway/services` | None | List upstream service URLs |
| GET | `/api/v1/gateway/version` | None | API version info |

Feedback submissions are written to Redis and tracked via `FEEDBACK_SUBMISSIONS_TOTAL` / `FEEDBACK_REJECTIONS_TOTAL` Prometheus counters.

---

### 2.14 Proxy Catch-All (`/{path:path}`)

Implemented in `routes/proxy.py`. Registered last so it cannot shadow other routes. Forwards any unmatched request to the appropriate upstream service. Uses a single shared `httpx.AsyncClient` managed via lifespan.

---

## 3. Security Module

Import path: `src.core.shared.security`

### 3.1 JWT Authentication (`security/auth.py`)

#### `UserClaims` model

```python
class UserClaims(BaseModel):
    sub: str              # User ID
    tenant_id: str
    roles: list[str]
    permissions: list[str]
    exp: int
    iat: int
    iss: str = "acgs2"
    aud: str = "acgs2-api"
    jti: str              # UUID, used for revocation tracking
    constitutional_hash: str  # Must match CONSTITUTIONAL_HASH at verify time
```

#### Token creation

```python
from src.core.shared.security.auth import create_access_token

token = create_access_token(
    user_id="user-123",
    tenant_id="tenant-abc",
    roles=["operator"],
    permissions=["policy:read"],
    expires_delta=timedelta(hours=1),
)
```

Default expiry: 1 hour. Key material resolved by `_resolve_jwt_material()`.

#### Supported algorithms

`RS256` (default), `RS384`, `RS512`, `ES256`, `ES384`, `EdDSA`, `HS256`. Set via `JWT_ALGORITHM` env var. Algorithm must be in the canonical allow-list; any other value raises `ConfigurationError`.

#### Key material resolution

| Scenario | Key source |
|----------|-----------|
| `HS256` | `JWT_SECRET` env → `JWT_SECRET_KEY` env → `settings.security.jwt_secret` |
| Asymmetric (default) | `JWT_PRIVATE_KEY` (file path or inline PEM) for signing; `JWT_PUBLIC_KEY` for verification |
| Fallback on RS256 | Raises `ConfigurationError: JWT_RSA_KEYS_MISSING` if keys not configured |

`JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` values are resolved by `load_key_material()`, which accepts both raw PEM strings and file paths.

#### Token verification

`verify_token(token)` checks:
1. Signature and expiry via `jwt.decode`
2. Issuer: must be `"acgs2"`
3. Constitutional hash binding: `payload["constitutional_hash"]` must match `CONSTITUTIONAL_HASH` (H-2 security fix)
4. JTI presence (H-2 security fix)
5. Token revocation blacklist via Redis `TokenRevocationService` (H-1 security fix, fail-open when Redis unavailable)

#### FastAPI dependencies

```python
# Require authentication
user: UserClaims = Depends(get_current_user)

# Optional authentication (returns None if no token)
user: UserClaims | None = Depends(get_current_user_optional)

# Require specific role
user: UserClaims = Depends(require_role("admin"))

# Require specific permission
user: UserClaims = Depends(require_permission("policy:write"))

# Require tenant access (cross-tenant isolation)
user: UserClaims = Depends(require_tenant_access(tenant_id))
```

#### `AuthenticationMiddleware`

An optional Starlette `BaseHTTPMiddleware` that sets `request.state.user`, `request.state.user_id`, `request.state.tenant_id`, `request.state.user_roles`, `request.state.user_permissions` when a valid Bearer token is present. Does not block unauthenticated requests; use `Depends(get_current_user)` on routes to enforce auth.

---

### 3.2 Rate Limiter (`security/rate_limiter.py`)

**Canonical module.** All other rate limiter implementations in the repo are deprecated.

#### Configured rules (registered in `main.py`)

| Endpoints | Limit | Window | Scope | Algorithm |
|-----------|-------|--------|-------|-----------|
| `/api/v1/auth/` | 10 req | 60s | IP | Sliding window |
| `/api/v1/sso/oidc/login`, `/api/v1/sso/saml/login` | 5 req | 60s | IP | Sliding window |
| `/api/v1/sso/oidc/logout`, `/api/v1/sso/saml/logout` | 20 req | 60s | IP | Sliding window |
| `/api/v1/policies` | 100 req | 60s | IP | Sliding window |
| `/api/v1/validate` | 5000 req | 60s | IP | Sliding window |
| `/health` | 6000 req | 60s | IP | Sliding window |
| All other paths | 1000 req | 60s | IP | Sliding window |

Exempt paths: `/docs`, `/openapi.json`, `/redoc`, `/favicon.ico`.

Controlled by `ENABLE_RATE_LIMITING` env var (default: `true`).

#### Rate limit response

HTTP 429. Body:
```json
{
  "error": "Too Many Requests",
  "retry_after": 42,
  "constitutional_hash": "cdd01ef066bc6cf2"
}
```

Response headers on all rate-limited responses:
```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1703001600
X-RateLimit-Scope: ip
Retry-After: 42
```

On tenant-scoped limit violations, additional headers are added:
```
X-Tenant-RateLimit-Limit: 1000
X-Tenant-RateLimit-Remaining: 0
X-Tenant-RateLimit-Reset: 1703001600
```

#### Key classes

```python
@dataclass
class RateLimitRule:
    requests: int
    window_seconds: int = 60
    scope: RateLimitScope = RateLimitScope.IP
    endpoints: list[str] | None = None
    burst_multiplier: float = 1.5
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.SLIDING_WINDOW

@dataclass
class RateLimitConfig:
    rules: list[RateLimitRule]
    redis_url: str | None = None
    fallback_to_memory: bool = True
    enabled: bool = True
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.SLIDING_WINDOW
    exempt_paths: list[str]
    fail_open: bool = True  # Allow requests if rate limiter errors

class RateLimitScope(StrEnum):
    USER = "user"
    IP = "ip"
    ENDPOINT = "endpoint"
    GLOBAL = "global"
    TENANT = "tenant"
```

#### Tenant-specific quotas

```python
from src.core.shared.security.rate_limiter import TenantRateLimitProvider

provider = TenantRateLimitProvider()
provider.set_tenant_quota(
    tenant_id="premium-corp",
    requests=5000,
    window_seconds=60,
    burst_multiplier=2.0,
)

# Pass to middleware at startup
app.add_middleware(
    RateLimitMiddleware,
    config=config,
    tenant_quota_provider=provider,
)
```

Tenant ID is extracted from `request.state.tenant_id` (auth middleware), `request.state.auth_claims`, or `request.state.user.tenant_id`. The `X-Tenant-ID` header is a last-resort untrusted fallback logged as a warning.

#### Environment-based config

```python
config = RateLimitConfig.from_env()
# Reads: RATE_LIMIT_ENABLED, RATE_LIMIT_REQUESTS_PER_MINUTE,
#        RATE_LIMIT_BURST_LIMIT, REDIS_URL, RATE_LIMIT_FAIL_OPEN
```

`fail_open` defaults to `True` in `{development, dev, test, testing, local, ci}` environments; `RATE_LIMIT_FAIL_OPEN` env var overrides.

#### `@rate_limit` endpoint decorator

```python
from src.core.shared.security.rate_limiter import rate_limit

@router.post("/expensive-endpoint")
@rate_limit(requests_per_minute=10, limit_type="user")
async def expensive_endpoint(request: Request):
    ...
```

`limit_type` values: `"user"`, `"ip"`, `"endpoint"`, `"global"`. A custom `key_func(request) -> str` can override identifier extraction.

---

### 3.3 Input Validator (`security/input_validator.py`)

Defense-in-depth layer. Primary defenses remain parameterized queries and output encoding.

```python
from src.core.shared.security.input_validator import InputValidator, validate_request_body

# Path traversal prevention
safe_path = InputValidator.validate_path(user_input, base_dir="/data/uploads")

# Injection detection (SQL, NoSQL, XSS, command injection)
if InputValidator.check_injection(user_string):
    raise HTTPException(400, "Potential injection detected")

# Payload size enforcement (uses sys.getsizeof)
InputValidator.enforce_size_limit(data, max_bytes=1_000_000)

# Middleware-style dependency for request body scanning
@router.post("/submit")
async def submit(request: Request, _: None = Depends(validate_request_body)):
    ...
```

Injection pattern sets: `SQL_INJECTION_PATTERNS`, `NOSQL_INJECTION_PATTERNS` (`$gt`, `$where`, etc.), `XSS_PATTERNS` (script tags, event handlers, data: URLs), `COMMAND_INJECTION_PATTERNS` (backticks, pipes, `$()`).

---

### 3.4 Post-Quantum Cryptography (`security/pqc.py`)

Imported via `src.core.shared.security.PQCWrapper`.

Key types and exceptions:

```python
class PQCKeyPair:     # Generated keypair (public, private)
class PQCSignature:   # Signature output
class KEMResult:      # KEM encapsulation result (ciphertext, shared_secret)

class PQCError(Exception): ...
class PQCKeyGenerationError(PQCError): ...
class PQCEncapsulationError(PQCError): ...
class PQCDecapsulationError(PQCError): ...
class PQCSignatureError(PQCError): ...
class PQCVerificationError(PQCError): ...
class UnsupportedAlgorithmError(PQCError): ...
class ConstitutionalHashMismatchError(PQCError): ...
class SignatureSubstitutionError(PQCError): ...
class PQCConfigurationError(PQCError): ...
```

---

### 3.5 Dual-Key JWT (`security/dual_key_jwt.py`)

Zero-downtime JWT key rotation. Accepts tokens signed by either the current or previous key.

```python
from src.core.shared.security import DualKeyJWTValidator, DualKeyConfig

validator = get_dual_key_validator()
result: JWTValidationResult = await validator.validate(token)
```

---

### 3.6 Security Headers (`security/security_headers.py`)

Applied via `add_security_headers(app, environment=env)` call in `main.py`. Sets CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, HSTS (production only), `Referrer-Policy`.

Configure via `SecurityHeadersConfig`.

---

### 3.7 CORS (`security/cors_config.py`)

```python
from src.core.shared.security import get_cors_config, get_strict_cors_config, CORSEnvironment

config = get_cors_config(environment=CORSEnvironment.PRODUCTION)
```

`DEFAULT_ORIGINS` and per-environment policies are defined in `cors_config.py`. Use `get_strict_cors_config()` for hardened deployments.

---

### 3.8 Tenant Context (`security/tenant_context.py`)

Extracts and validates tenant ID from requests.

```python
from src.core.shared.security import (
    get_current_tenant_id,   # Raises if tenant not present
    get_optional_tenant_id,  # Returns None if absent
    require_tenant_scope,    # Dependency: validates tenant scope
    sanitize_tenant_id,      # Strips invalid characters
    validate_tenant_id,      # Raises TenantValidationError on invalid format
)

# Tenant ID constraints
TENANT_ID_MIN_LENGTH = 3
TENANT_ID_MAX_LENGTH = 64
TENANT_ID_PATTERN     # Regex: alphanumeric + hyphens/underscores
```

`TenantContextMiddleware` can be added to apps that require per-request tenant isolation.

---

### 3.9 Data Classification and Privacy (`§16.4` optional modules)

All modules degrade gracefully when their optional dependencies are absent. Availability flags exported from `src.core.shared.security`:

| Flag | Module | Description |
|------|--------|-------------|
| `DATA_CLASSIFICATION_AVAILABLE` | `data_classification` | Tier-based data classification (PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED) |
| `PII_DETECTOR_AVAILABLE` | `pii_detector` | Regex + field-name PII detection |
| `RETENTION_POLICY_AVAILABLE` | `retention_policy` | Automated retention enforcement (delete, anonymize, archive, pseudonymize) |
| `GDPR_ERASURE_AVAILABLE` | `gdpr_erasure` | GDPR Art. 17 erasure with audit certificates |
| `CCPA_HANDLER_AVAILABLE` | `ccpa_handler` | CCPA request processing |
| `URL_FILE_VALIDATOR_AVAILABLE` | `url_file_validator` | SSRF protection (SEC-003), file upload validation (SEC-006) |
| `SECRET_ROTATION_AVAILABLE` | `secret_rotation` | Secret rotation lifecycle with Vault and in-memory backends |

---

### 3.10 Arcjet Protection (`arcjet_protection.py`)

Optional bot and rate-limit protection via the Arcjet cloud service.

```python
from src.core.services.api_gateway.arcjet_protection import configure_arcjet_protection

configure_arcjet_protection(app)  # No-op if ARCJET_ENABLED != "true"
```

Environment variables:

| Var | Default | Description |
|-----|---------|-------------|
| `ARCJET_ENABLED` | `false` | Enable Arcjet middleware |
| `ARCJET_KEY` | — | API key (required if enabled) |
| `ARCJET_MODE` | `DRY_RUN` | `LIVE` or `DRY_RUN` |
| `ARCJET_RATE_LIMIT_MAX` | `120` | Max requests per window |
| `ARCJET_RATE_LIMIT_WINDOW_SECONDS` | `60` | Window size in seconds |

Fail-open: if the Arcjet check throws, the request is allowed through with a warning log.

---

## 4. Auth Module

Import path: `src.core.shared.auth`

### 4.1 OIDC Handler (`auth/oidc_handler.py`)

```python
from src.core.shared.auth import OIDCHandler
from src.core.shared.auth.oidc_handler import OIDCConfig

handler = OIDCHandler()

# Initiate login
auth_url, state = await handler.initiate_login(
    provider_name="google",
    redirect_uri="https://app.example.com/callback",
)

# Handle callback
user_info = await handler.handle_callback(
    provider_name="google",
    code="authorization_code",
    state="state_from_session",
)
```

Discovers OIDC endpoints via `{oidc_issuer_url}/.well-known/openid-configuration`. PKCE (`code_challenge_method=S256`) is used when `OIDC_USE_PKCE=true`.

---

### 4.2 SAML Handler (`auth/saml_handler.py`)

```python
from src.core.shared.auth import SAMLHandler
from src.core.shared.auth.saml_config import SAMLSPConfig, SAMLIdPConfig

handler = SAMLHandler()
handler.register_idp(
    name="okta",
    metadata_url="https://dev-123.okta.com/app/exk123/sso/saml/metadata",
)

redirect_url, request_id = await handler.initiate_login("okta")
user_info = await handler.process_acs_response(saml_response, request_id)
```

`SAMLSPConfig` fields: `entity_id`, `acs_url`, `slo_url`, `certificate`, `private_key`, `sign_requests`, `want_assertions_signed`, `want_assertions_encrypted`.

Request IDs are tracked via `saml_request_tracker.py` to prevent replay attacks.

---

### 4.3 WorkOS Handler (`auth/workos.py`)

Wraps the WorkOS API. Activated when `WORKOS_ENABLED=true`.

Key operations: `get_authorization_url()`, `authenticate_with_code()`, `get_profile_and_token()`.

Webhook signature verification uses HMAC-SHA256 against `WORKOS_WEBHOOK_SECRET`. Deduplication TTL controlled by `WORKOS_WEBHOOK_DEDUPE_TTL_SECONDS` (default: 86400s). `WORKOS_WEBHOOK_FAIL_CLOSED=true` causes the webhook endpoint to return 500 rather than 200 if the secret is not configured.

---

### 4.4 Role Mapper (`auth/role_mapper.py`)

Maps IdP groups or claims to ACGS roles. Used by OIDC callback and SAML ACS handler.

```python
from src.core.shared.auth import RoleMapper

mapper = RoleMapper()
roles = mapper.map_roles(idp_groups=["engineers", "infra-admins"])
```

---

### 4.5 JIT Provisioner (`auth/provisioning.py`)

Just-in-time user provisioning on first SSO login.

```python
from src.core.shared.auth import JITProvisioner

provisioner = JITProvisioner()
result = await provisioner.get_or_create_user(
    email="user@example.com",
    name="Jane Doe",
    sso_provider="oidc",
    idp_user_id="google-12345",
    roles=["developer"],
)
# result.created: bool
# result.user: provisioned user object
```

`SSO_AUTO_PROVISION=true` enables automatic creation. `SSO_DEFAULT_ROLE` (default: `viewer`) is assigned when no roles are mapped. `SSO_ALLOWED_DOMAINS` restricts provisioning to specific email domains.

---

## 5. Config Module

Import path: `src.core.shared.config`. The singleton `settings` object is re-exported from `src.core.shared.config.factory`.

### 5.1 Settings Hierarchy

`Settings` (from `factory.py`) aggregates all domain config objects:

```python
settings.security       # SecuritySettings
settings.opa            # OPASettings
settings.sso            # SSOSettings
settings.vault          # VaultSettings
settings.audit          # AuditSettings
settings.redis          # RedisSettings
settings.database       # DatabaseSettings
settings.ai             # AISettings
settings.maci           # MACISettings
settings.circuit_breaker # CircuitBreakerSettings
settings.telemetry      # TelemetrySettings
```

### 5.2 SecuritySettings

| Field | Env Var | Default | Notes |
|-------|---------|---------|-------|
| `jwt_secret` | `JWT_SECRET` | None | Required in production for HS256; `SecretStr` |
| `jwt_public_key` | `JWT_PUBLIC_KEY` | `SYSTEM_PUBLIC_KEY_PLACEHOLDER` | PEM or file path |
| `api_key_internal` | `API_KEY_INTERNAL` | None | `SecretStr` |
| `admin_api_key` | `ADMIN_API_KEY` | None | `SecretStr` |

Validator: rejects placeholder values (`PLACEHOLDER`, `CHANGE_ME`, `DANGEROUS_DEFAULT`, `dev-secret`) and secrets shorter than 32 characters.

### 5.3 SSOSettings

| Field | Env Var | Default |
|-------|---------|---------|
| `enabled` | `SSO_ENABLED` | `true` |
| `session_lifetime_seconds` | `SSO_SESSION_LIFETIME` | `3600` |
| `oidc_enabled` | `OIDC_ENABLED` | `true` |
| `oidc_client_id` | `OIDC_CLIENT_ID` | None |
| `oidc_client_secret` | `OIDC_CLIENT_SECRET` | None (SecretStr) |
| `oidc_issuer_url` | `OIDC_ISSUER_URL` | None |
| `oidc_scopes` | `OIDC_SCOPES` | `["openid","email","profile"]` |
| `oidc_use_pkce` | `OIDC_USE_PKCE` | `true` |
| `saml_enabled` | `SAML_ENABLED` | `true` |
| `saml_entity_id` | `SAML_ENTITY_ID` | None |
| `saml_sign_requests` | `SAML_SIGN_REQUESTS` | `true` |
| `saml_want_assertions_signed` | `SAML_WANT_ASSERTIONS_SIGNED` | `true` |
| `saml_want_assertions_encrypted` | `SAML_WANT_ASSERTIONS_ENCRYPTED` | `false` |
| `saml_sp_certificate` | `SAML_SP_CERTIFICATE` | None |
| `saml_sp_private_key` | `SAML_SP_PRIVATE_KEY` | None (SecretStr) |
| `saml_idp_metadata_url` | `SAML_IDP_METADATA_URL` | None |
| `saml_idp_sso_url` | `SAML_IDP_SSO_URL` | None |
| `saml_idp_slo_url` | `SAML_IDP_SLO_URL` | None |
| `saml_idp_certificate` | `SAML_IDP_CERTIFICATE` | None |
| `auto_provision_users` | `SSO_AUTO_PROVISION` | `true` |
| `default_role_on_provision` | `SSO_DEFAULT_ROLE` | `"viewer"` |
| `allowed_domains` | `SSO_ALLOWED_DOMAINS` | None (comma-separated) |
| `workos_enabled` | `WORKOS_ENABLED` | `false` |
| `workos_client_id` | `WORKOS_CLIENT_ID` | None |
| `workos_api_key` | `WORKOS_API_KEY` | None (SecretStr) |
| `workos_webhook_secret` | `WORKOS_WEBHOOK_SECRET` | None (SecretStr) |
| `workos_webhook_dedupe_ttl_seconds` | `WORKOS_WEBHOOK_DEDUPE_TTL_SECONDS` | `86400` |
| `workos_webhook_fail_closed` | `WORKOS_WEBHOOK_FAIL_CLOSED` | `true` |
| `workos_portal_default_intent` | `WORKOS_PORTAL_DEFAULT_INTENT` | `"sso"` |
| `workos_portal_return_url` | `WORKOS_PORTAL_RETURN_URL` | None |
| `trusted_hosts` | `SSO_TRUSTED_HOSTS` | `["localhost","127.0.0.1"]` |

### 5.4 OPASettings

| Field | Env Var | Default | Notes |
|-------|---------|---------|-------|
| `url` | `OPA_URL` | `http://localhost:8181` | |
| `max_connections` | `OPA_MAX_CONNECTIONS` | `100` | |
| `mode` | `OPA_MODE` | `http` | `http`, `embedded`, `fallback` |
| `fail_closed` | — | `true` | Hardcoded. VULN-002 fix: OPA is always fail-closed |
| `ssl_verify` | `OPA_SSL_VERIFY` | `true` | |
| `ssl_cert` | `OPA_SSL_CERT` | None | |
| `ssl_key` | `OPA_SSL_KEY` | None | |

### 5.5 VaultSettings

| Field | Env Var | Default |
|-------|---------|---------|
| `address` | `VAULT_ADDR` | `http://127.0.0.1:8200` |
| `token` | `VAULT_TOKEN` | None (SecretStr) |
| `namespace` | `VAULT_NAMESPACE` | None |
| `transit_mount` | `VAULT_TRANSIT_MOUNT` | `transit` |
| `kv_mount` | `VAULT_KV_MOUNT` | `secret` |
| `kv_version` | `VAULT_KV_VERSION` | `2` |
| `timeout` | `VAULT_TIMEOUT` | `30.0` |
| `verify_tls` | `VAULT_VERIFY_TLS` | `true` |
| `ca_cert` | `VAULT_CACERT` | None |

### 5.6 RedisSettings

| Field | Env Var | Default |
|-------|---------|---------|
| `host` | `REDIS_HOST` | `localhost` |
| `port` | `REDIS_PORT` | `6379` |
| `db` | `REDIS_DB` | `0` |
| `password` | `REDIS_PASSWORD` | None |
| `max_connections` | `REDIS_MAX_CONNECTIONS` | `2000` |
| `socket_timeout` | `REDIS_SOCKET_TIMEOUT` | `1.0` |
| `retry_on_timeout` | `REDIS_RETRY_ON_TIMEOUT` | `true` |
| `ssl` | `REDIS_SSL` | `false` |
| `socket_keepalive` | `REDIS_SOCKET_KEEPALIVE` | `true` |
| `health_check_interval` | `REDIS_HEALTH_CHECK_INTERVAL` | `30` |

### 5.7 Runtime Overrides

```python
from src.core.shared.config import override_config, get_override, clear_overrides

override_config("feature_flag_x", True)
value = get_override("feature_flag_x")
clear_overrides()
```

Use `get_all_overrides()` to inspect all active overrides.

### 5.8 Tenant Quota Registry

```python
from src.core.shared.config import get_tenant_quota_registry, TenantQuotaConfig

registry = get_tenant_quota_registry()
quotas = registry.get_quotas(tenant_id="tenant-abc")
```

---

## 6. Types Reference

Import path: `src.core.shared.types`

### 6.1 JSON Types (`types/json_types.py`)

| Type | Definition |
|------|-----------|
| `JSONPrimitive` | `str \| int \| float \| bool \| None` |
| `JSONValue` | `JSONPrimitive \| dict \| list` (recursive) |
| `JSONDict` | `dict[str, JSONValue]` |
| `JSONList` | `list[JSONValue]` |
| `JSONType` | `JSONDict \| JSONList \| JSONPrimitive` |
| `StringDict` | `dict[str, str]` |
| `MetadataDict` | `dict[str, str \| int \| float \| bool \| None]` |
| `AttributeDict` | `dict[str, object]` |
| `NestedDict` | `dict[str, JSONValue \| dict]` |
| `RecursiveDict` | `dict[str, RecursiveDict \| JSONValue]` |
| `RecursiveList` | `list[RecursiveList \| JSONValue]` |

### 6.2 Agent Types (`types/agent_types.py`)

| Type | Underlying |
|------|-----------|
| `AgentID` | `str` |
| `AgentState` | `JSONDict` |
| `AgentContext` | `JSONDict` |
| `AgentMetadata` | `JSONDict` |
| `AgentInfo` | `JSONDict` |
| `AgentIdentity` | `JSONDict` |
| `ContextData` | `JSONDict` |
| `WorkflowID` | `str` |
| `WorkflowState` | `JSONDict` |
| `WorkflowContext` | `JSONDict` |
| `MessageID` | `str` |
| `MessagePayload` | `JSONDict` |
| `MessageHeaders` | `dict[str, str]` |
| `MessageMetadata` | `JSONDict` |
| `EventID` | `str` |
| `EventData` | `JSONDict` |
| `EventMetadata` | `JSONDict` |
| `EventContext` | `JSONDict` |
| `SessionData` | `JSONDict` |
| `MemoryData` | `JSONDict` |
| `StepParameters` | `JSONDict` |
| `StepResult` | `JSONDict` |
| `TopicName` | `str` |
| `KafkaMessage` | `JSONDict` |

### 6.3 Governance Types (`types/governance_types.py`)

Selected key types:

| Type | Underlying | Purpose |
|------|-----------|---------|
| `TenantID` | `str` | Tenant identifier |
| `CorrelationID` | `str` | Distributed trace correlation |
| `TraceID` | `str` | OTel trace ID |
| `PolicyID` | `str` | Policy registry identifier |
| `PolicyData` | `JSONDict` | Policy content |
| `PolicyDecision` | `JSONDict` | OPA decision payload |
| `PolicyContext` | `JSONDict` | Context passed to OPA |
| `SecurityContext` | `JSONDict` | Auth/authz context |
| `AuthToken` | `str` | JWT or API key string |
| `AuthCredentials` | `JSONDict` | Credential bundle |
| `AuthContext` | `JSONDict` | Authentication context |
| `CacheKey` | `str` | Cache lookup key |
| `CacheValue` | `JSONValue` | Cacheable value |
| `CacheTTL` | `int` | TTL in seconds |
| `ConstitutionalContext` | `JSONDict` | Governance validation context |
| `AuditEntry` | `JSONDict` | Single audit record |
| `AuditTrail` | `list[AuditEntry]` | Sequence of audit entries |
| `ModelID` | `str` | LLM model identifier |
| `ValidationContext` | `JSONDict` | Validation execution context |
| `ValidationErrors` | `list[dict[str, str]]` | Pydantic-style error list |
| `ErrorCode` | `str` | Machine-readable error code |
| `ErrorDetails` | `JSONDict` | Structured error context |

### 6.4 Protocol Types (`types/protocol_types.py`)

Runtime-checkable protocols for structural typing:

| Protocol | Methods |
|---------|---------|
| `SupportsHealthCheck` | `health_check() -> JSONDict` |
| `SupportsValidation` | `validate(data) -> bool` |
| `SupportsCache` | `get(key)`, `set(key, value, ttl)`, `delete(key)` |
| `SupportsCircuitBreaker` | `call(func, *args)` |
| `SupportsAudit` | `log_event(event)` |
| `SupportsAuthentication` | `authenticate(credentials)` |
| `SupportsLogging` | `log(level, message, **context)` |
| `SupportsMiddleware` | `process(request, next)` |
| `SupportsRegistry` | `register(name, obj)`, `get(name)` |
| `SupportsSerialization` | `serialize(obj)`, `deserialize(data)` |
| `SupportsExecution` | `execute(task)` |
| `SupportsCompensation` | `compensate(transaction_id)` |
| `AgentBus` | `publish(message)`, `subscribe(topic, handler)` |
| `GovernanceService` | `validate(action, context)`, `get_policy(policy_id)` |

Generic type variables: `T`, `T_co` (covariant), `T_contra` (contravariant), `ModelT`, `StateT`, `EventT`, `ResponseT`, `ConfigT`, `ContextT`.

---

## 7. Error Handling

Import path: `src.core.shared.errors`

### 7.1 Exception Hierarchy

```
ACGSBaseError (500)
├── ConstitutionalViolationError  (403) CONSTITUTIONAL_VIOLATION
├── MACIEnforcementError          (403) MACI_ENFORCEMENT_FAILURE
├── TenantIsolationError          (403) TENANT_ISOLATION_VIOLATION
├── ValidationError               (400) VALIDATION_ERROR
├── ServiceUnavailableError       (503) SERVICE_UNAVAILABLE
├── RateLimitExceededError        (429) RATE_LIMIT_EXCEEDED
├── AuthenticationError           (401) AUTHENTICATION_FAILED
├── AuthorizationError            (403) AUTHORIZATION_DENIED
├── ResourceNotFoundError         (404) RESOURCE_NOT_FOUND
├── DataIntegrityError            (409) DATA_INTEGRITY_VIOLATION
├── ConfigurationError            (500) CONFIGURATION_ERROR
└── ACGSTimeoutError              (504) OPERATION_TIMEOUT
```

### 7.2 `ACGSBaseError` Fields

| Field | Type | Notes |
|-------|------|-------|
| `message` | `str` | Human-readable description |
| `error_code` | `str` | Machine-readable code, e.g. `VALIDATION_ERROR` |
| `constitutional_hash` | `str` | Defaults to `CONSTITUTIONAL_HASH` constant |
| `correlation_id` | `CorrelationID` | Auto-generated UUID if not provided |
| `details` | `JSONDict` | Additional structured context |
| `http_status_code` | `int` | Maps to HTTP response code |
| `timestamp` | `str` | ISO 8601 UTC |
| `cause` | `BaseException \| None` | Preserved via `__cause__` |

`to_dict()` produces the JSON response body. `to_log_dict()` adds `exception_type`, `http_status_code`, and `cause_traceback` for structured log entries.

### 7.3 Common Exception Constructors

```python
from src.core.shared.errors import (
    ConstitutionalViolationError,
    MACIEnforcementError,
    TenantIsolationError,
    ValidationError,
    ServiceUnavailableError,
    RateLimitExceededError,
    ResourceNotFoundError,
)

raise ConstitutionalViolationError(
    "Action violates safety policy",
    violations=["safety_rule_3"],
    policy_id="pol-001",
    action="deploy_untested_model",
)

raise MACIEnforcementError(
    "Agent cannot validate its own output",
    agent_id="agent-abc",
    role="PROPOSER",
    action="self_validate",
)

raise ValidationError(
    "Invalid email format",
    field="email",
    value=raw_email,
    constraint="email_format",
)

raise ServiceUnavailableError(
    "OPA unavailable",
    service_name="opa",
    endpoint="http://localhost:8181/health",
    retry_after=30,
)
```

### 7.4 Retry Utilities

```python
from src.core.shared.errors import retry, retry_async, RetryConfig, exponential_backoff

@retry(max_retries=3, base_delay=1.0)
async def call_opa():
    ...

# Manual retry budget tracking
budget = RetryBudget(max_retries=5, budget_seconds=60.0)

config = RetryConfig(
    max_retries=3,
    base_delay=0.5,
    max_delay=30.0,
    backoff_multiplier=2.0,
    jitter=True,
)
```

`DEFAULT_RETRYABLE_EXCEPTIONS` covers common transient errors (connection, timeout, etc.).

### 7.5 Circuit Breaker

```python
from src.core.shared.errors import circuit_breaker, CircuitBreakerConfig, CircuitBreakerState

@circuit_breaker("policy_registry")
async def fetch_policy(policy_id: str):
    return await client.get(f"/policies/{policy_id}")

# Get instance for inspection
cb = get_circuit_breaker("policy_registry")
state: CircuitBreakerState  # CLOSED | OPEN | HALF_OPEN

config = CircuitBreakerConfig(
    failure_threshold=5,
    recovery_timeout=30,
    success_threshold=2,
)
```

Raises `CircuitBreakerOpenError` when the breaker is open.

### 7.6 `rate_limit_error_handler`

Register with FastAPI to get standardised 429 responses with proper headers:

```python
from src.core.shared.errors.exceptions import RateLimitExceededError, rate_limit_error_handler

app.add_exception_handler(RateLimitExceededError, rate_limit_error_handler)
```

---

## 8. Cache Layer

Import path: `src.core.shared.cache`

### 8.1 Architecture

Three tiers coordinated by `TieredCacheManager`:

| Tier | Implementation | Default TTL | Scope |
|------|---------------|-------------|-------|
| L1 | `L1Cache` (in-process, LRU) | 300s (5 min) | Process-local |
| L2 | Redis (`redis.asyncio`) | 3600s (1 hr) | Shared across instances |
| L3 | Distributed/persistent | 86400s (24 hr) | Long-term storage |

L1 TTL is automatically clamped to L2 TTL on construction to prevent stale L1 entries outlasting their L2 source.

### 8.2 `TieredCacheConfig`

```python
from src.core.shared.cache import TieredCacheConfig

config = TieredCacheConfig(
    l1_maxsize=1024,         # Max entries in L1 LRU
    l1_ttl=300,              # L1 TTL seconds (auto-clamped to l2_ttl)
    l2_ttl=3600,             # L2 Redis TTL seconds
    redis_url=None,          # None = no Redis, uses L1 + L3 only
    l3_ttl=86400,            # L3 TTL seconds
    l3_enabled=True,
    promotion_threshold=10,  # Accesses/min to promote entry to L1
    demotion_threshold_hours=1.0,  # Hours inactive before L1 → L3 demotion
    serialize=True,          # JSON-serialize values for cross-tier consistency
)
```

### 8.3 Singleton Usage

```python
from src.core.shared.cache import get_tiered_cache, reset_tiered_cache

cache = get_tiered_cache(config=config, name="governance")

await cache.set("policy:abc", policy_data, ttl=600)
value = await cache.get("policy:abc")
await cache.delete("policy:abc")

# Teardown (e.g. in tests)
reset_tiered_cache()
```

### 8.4 Promotion and Demotion

- Entries exceeding `promotion_threshold` accesses per minute are promoted from L2 → L1.
- Entries in L1 not accessed within `demotion_threshold_hours` are demoted to L3.
- Promotions and demotions are tracked by `record_promotion()` / `record_demotion()` Prometheus helpers.

### 8.5 Degraded Mode

On consecutive Redis failures, `TieredCacheManager` sets `tiered_cache_degraded{cache_name}` gauge to `1` and falls back to L1-only. Redis failure count tracked by `tiered_cache_redis_failures_total`.

### 8.6 Cache Warming

```python
from src.core.shared.cache import CacheWarmer, WarmingConfig, warm_cache_on_startup

warmer = get_cache_warmer()
result: WarmingResult = await warmer.warm(config=WarmingConfig(...))
```

`WarmingStatus` values: `PENDING`, `IN_PROGRESS`, `COMPLETED`, `FAILED`. Progress tracked via `WarmingProgress`. Rate limiting during warm applied by the internal `RateLimiter` (not the HTTP rate limiter).

### 8.7 Workflow State Cache

```python
from src.core.shared.cache import WorkflowStateCache, workflow_cache

state = await workflow_cache.get(workflow_id)
await workflow_cache.set(workflow_id, new_state)
```

Backed by the tiered cache manager with workflow-specific key prefixing.

### 8.8 Cache Metrics

All Prometheus counters and histograms are exported from `src.core.shared.cache.metrics`:

| Metric | Type | Labels |
|--------|------|--------|
| `cache_hits_total` | Counter | `tier`, `cache_name` |
| `cache_misses_total` | Counter | `tier`, `cache_name` |
| `cache_evictions_total` | Counter | `tier`, `cache_name` |
| `cache_promotions_total` | Counter | `cache_name` |
| `cache_demotions_total` | Counter | `cache_name` |
| `cache_fallback_total` | Counter | `cache_name` |
| `cache_operation_duration_seconds` | Histogram | `operation`, `tier` |
| `cache_operation_duration_l1` | Histogram | `cache_name` |
| `cache_operation_duration_l2` | Histogram | `cache_name` |
| `cache_operation_duration_l3` | Histogram | `cache_name` |
| `cache_entries` | Gauge | `tier`, `cache_name` |
| `cache_size` | Gauge | `cache_name` |
| `cache_capacity` | Gauge | `cache_name` |
| `cache_tier_health` | Gauge | `tier`, `cache_name` |
| `cache_warming_duration_seconds` | Histogram | `cache_name` |
| `cache_warming_keys_loaded_total` | Counter | `cache_name` |
| `l1_latency` | Histogram | (custom buckets: 0.1ms–10ms) |
| `l2_latency` | Histogram | (custom buckets: 1ms–100ms) |
| `l3_latency` | Histogram | (custom buckets: 10ms–1000ms) |

Helper functions: `record_cache_hit(tier, name)`, `record_cache_miss(tier, name)`, `track_cache_operation(operation, tier)` (context manager), `update_cache_size(name, size)`, `set_tier_health(tier, name, healthy)`.

---

## 9. Observability

### 9.1 Structured Logging

Import path: `src.core.shared.structured_logging`

```python
from src.core.shared.structured_logging import configure_logging, get_logger

configure_logging()  # Call once at startup (done in main.py)
logger = get_logger(__name__)

logger.info("Operation completed", user_id="u-123", tenant_id="t-abc", latency_ms=42.1)
logger.warning("Rate limit near threshold", limit=100, current=95)
logger.error("OPA unreachable", endpoint="http://opa:8181", exc_info=True)
```

Uses `structlog`. All log events are structured JSON in production. The `configure_logging()` call binds the structlog pipeline with context variables for correlation ID propagation.

**Convention**: never use `print()` or the stdlib `logging` module directly in production code. Always use `get_logger(__name__)`.

---

### 9.2 Prometheus Metrics (`metrics.py`)

Registered metrics in the API Gateway:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `http_request_duration_seconds` | Histogram | `method`, `endpoint`, `service`, `status_code` | Request latency. Buckets target P99 < 1ms. |
| `http_requests_total` | Counter | `method`, `endpoint`, `service`, `status_code` | Total requests |
| `http_requests_in_progress` | Gauge | `method`, `service` | In-flight requests |
| `cache_hits_total` | Counter | `cache_type`, `service` | Gateway-level cache hits |
| `cache_misses_total` | Counter | `cache_type`, `service` | Gateway-level cache misses |
| `cache_operation_duration_seconds` | Histogram | `operation`, `cache_type`, `service` | |
| `connection_pool_size` | Gauge | `pool_type`, `service` | |
| `connection_pool_available` | Gauge | `pool_type`, `service` | |
| `proxy_requests_total` | Counter | `target_service`, `status_code` | |
| `proxy_duration_seconds` | Histogram | `target_service` | |
| `feedback_submissions_total` | Counter | `auth_mode`, `category`, `user_id_verified` | |
| `feedback_rejections_total` | Counter | `reason`, `auth_mode` | |
| `rate_limit_exceeded_total` | Counter | `limit_type`, `identifier`, `endpoint` | From rate limiter |
| `rate_limit_requests_total` | Counter | `limit_type`, `identifier`, `endpoint`, `allowed` | From rate limiter |
| `rate_limits_active` | Gauge | — | Active rate limit buckets |
| `acgs_constitutional_hash` | Info | `hash`, `service` | Loaded constitutional hash |

Endpoint path normalization in `MetricsMiddleware._normalize_endpoint()` replaces UUIDs with `{uuid}` and numeric IDs with `{id}` to limit cardinality.

Helper functions:
```python
record_cache_hit(cache_type="redis", service="api_gateway")
record_cache_miss(cache_type="redis", service="api_gateway")
record_proxy_request(target_service="agent-bus", status_code=200, duration=0.042)
record_feedback_submission(auth_mode="jwt", category="governance", user_id_verified=True)
update_connection_pool_metrics(pool_type="http", size=100, available=87)
```

Metrics are accessible via `get_metrics()` → `bytes` and `get_metrics_content_type()`. To expose a `/metrics` endpoint:

```python
from src.core.services.api_gateway.metrics import create_metrics_endpoint
app.add_api_route("/metrics", create_metrics_endpoint())
```

Metric creation uses idempotent `_get_or_create_counter/gauge/histogram()` helpers that check the Prometheus registry before registering to survive multi-process test setups.

---

### 9.3 OpenTelemetry

Initialised in `main.py`:

```python
init_otel("api-gateway", app=app, export_to_console=settings.debug)
```

`init_otel` is imported from `src.core.shared.otel_config`; a no-op fallback is used if the module is unavailable. Console export is active only when `DEBUG=true`.

Spans for requests propagate `correlation_id` as a baggage attribute. Rate limiter, auth, and proxy operations emit child spans.

---

### 9.4 Adding a New Route

1. Create `routes/your_feature.py`. Define a router using `create_versioned_router(prefix="/your-feature", version="v1", tags=["Your Feature"])` from `src.core.shared.api_versioning`.
2. Add your router to the `__all__` list and import in `routes/__init__.py`.
3. Register in `main.py` with `app.include_router(your_router)`. Place it before `proxy_router` (the catch-all must always be last).
4. Add rate limit rules to `rate_limit_rules` in `main.py` if your endpoint has different throughput requirements than the default (1000 req/min).
5. For admin-only routes, pass `dependencies=[Depends(require_role("admin"))]` to `app.include_router()`.
6. Update health check dependencies in `health.py` if your route adds a new required external dependency.
