"""Constitutional Hash: 608508a9bd224290
ACGS-2 API Gateway
Simple development API gateway for routing requests to services

Implements:
- Rate limiting per SPEC_ACGS2_ENHANCED.md Section 3.3
- Health endpoints per SPEC_ACGS2_ENHANCED.md Section 3.3
- API Versioning with /api/v1/ prefix and X-API-Version headers
"""

import os
import secrets

from fastapi import APIRouter, Depends
from fastapi.responses import ORJSONResponse

# Import rate limiting and health modules
from starlette.middleware.sessions import SessionMiddleware

try:
    from src.core.self_evolution.api import evidence_router

    _SELF_EVOLUTION_AVAILABLE = True
except ImportError:
    evidence_router = None
    _SELF_EVOLUTION_AVAILABLE = False

from src.core.shared.api_versioning import (
    DEPRECATED_ROUTES,
    DEPRECATED_VERSIONS,
    SUPPORTED_VERSIONS,
    APIVersioningMiddleware,
    DeprecationNoticeMiddleware,
    VersioningConfig,
)
from src.core.shared.config import settings
from src.core.shared.config.runtime_environment import resolve_runtime_environment
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.fastapi_base import create_acgs_app
from src.core.shared.metrics import set_service_info

try:
    from src.core.shared.otel_config import init_otel

    _OTEL_CONFIG_AVAILABLE = True
except ImportError:
    _OTEL_CONFIG_AVAILABLE = False

    def init_otel(*args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Fallback no-op when optional OpenTelemetry config is unavailable."""


from src.core.shared.security.auth import (
    require_role,
)
from src.core.shared.security.csrf import CSRFConfig, CSRFMiddleware
from src.core.shared.security.rate_limiter import (
    RateLimitConfig,
    RateLimitMiddleware,
    RateLimitRule,
    RateLimitScope,
)
from src.core.shared.security.security_headers import add_security_headers
from src.core.shared.structured_logging import configure_logging, get_logger

from .health import create_health_router
from .lifespan import lifespan
from .metrics import MetricsMiddleware, create_metrics_endpoint
from .middleware.autonomy_tier import AutonomyTierEnforcementMiddleware
from .middleware.pqc_only_mode import PQCOnlyModeMiddleware
from .routes import (
    admin_sso_router,
    admin_workos_router,
    autonomy_tiers_router,
    compliance_router,
    data_subject_v1_router,
    decisions_v1_router,
    evolution_control_router,
    gateway_v1_router,
    proxy_router,
    sso_router,
    x402_bundles_router,
    x402_facilitator_router,
    x402_governance_router,
    x402_marketplace_router,
    x402_revenue_router,
)
from .routes._x402_common import configure_x402_payment_middleware
from .routes.x402_governance import ensure_attestation_secret_config

try:
    from .routes.pqc_phase5 import pqc_phase5_router
except ImportError:
    pqc_phase5_router = APIRouter()

# Service name for logging and tracing
SERVICE_NAME = "api_gateway"

# Configure structured logging (MUST be called before any logging)
configure_logging()

# Get structured logger
logger = get_logger(__name__)

if not _OTEL_CONFIG_AVAILABLE:
    logger.warning("OpenTelemetry config unavailable; tracing initialization disabled")


def _runtime_environment() -> str:
    return resolve_runtime_environment(getattr(settings, "env", None))


environment = _runtime_environment()
is_development = environment in {"development", "dev", "test", "testing", "ci"}


def _parse_bool_env(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    return None

app = create_acgs_app(
    "api-gateway",
    environment=environment,
    title="ACGS-2 API Gateway",
    description="Development API Gateway for ACGS-2 services with constitutional governance",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    default_response_class=ORJSONResponse,
    include_default_health_routes=False,
    lifespan=lifespan,
    logger=logger,
    trusted_hosts=settings.sso.trusted_hosts,
)
set_service_info("api-gateway", "1.0.0")

# GZip compression for responses > 1KB (60-70% bandwidth reduction for JSON payloads)
from starlette.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(MetricsMiddleware, service_name="api_gateway")
app.add_api_route("/metrics", create_metrics_endpoint(), include_in_schema=False)

# ============================================================================
# API Versioning Configuration (Constitutional Hash: 608508a9bd224290)
# ============================================================================

# Configure API versioning middleware
# - URL-path versioning: /api/v1/, /api/v2/
# - Response headers: X-API-Version, X-API-Deprecated, X-Constitutional-Hash
# - Version metrics: Usage tracking per version and endpoint
API_VERSIONING_CONFIG = VersioningConfig(
    default_version="v1",
    supported_versions=SUPPORTED_VERSIONS,
    deprecated_versions=DEPRECATED_VERSIONS,
    exempt_paths={
        "/health",
        "/health/live",
        "/health/ready",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/favicon.ico",
    },
    enable_metrics=True,
    strict_versioning=False,  # Allow unversioned paths for backward compatibility
    log_version_usage=True,
)

# Add API versioning middleware (must be added before other middleware)
app.add_middleware(APIVersioningMiddleware, config=API_VERSIONING_CONFIG)

# Add deprecation notice middleware for legacy endpoints
app.add_middleware(DeprecationNoticeMiddleware, deprecated_routes=DEPRECATED_ROUTES)
logger.info("Deprecation notice middleware enabled for legacy endpoints")


# Initialize OTel tracing
init_otel("api-gateway", app=app, export_to_console=settings.debug)

# Add security headers middleware (CSP, X-Frame-Options, HSTS, etc.)
add_security_headers(app, environment=environment)
is_production = environment in ("production", "prod", "staging")

if settings.security.jwt_secret:
    session_secret = settings.security.jwt_secret.get_secret_value()
elif is_production:
    raise RuntimeError(
        "JWT_SECRET is required in production for session security. "
        "Generate a secure secret using `secrets.token_urlsafe(32)`"
    )
else:
    session_secret = secrets.token_urlsafe(32)
    logger.warning(
        "JWT_SECRET not configured - using generated session secret. "
        "Sessions will not persist across restarts. Set JWT_SECRET in production!"
    )

app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret,
    session_cookie="acgs2_session",
    max_age=settings.sso.session_lifetime_seconds,
    # SAML ACS uses cross-site POST; SameSite=None is required for the state cookie.
    same_site=("none" if settings.sso.saml_enabled else "lax"),
    https_only=(is_production or settings.sso.saml_enabled),
)
logger.info("SessionMiddleware configured for OAuth state management")

app.add_middleware(
    CSRFMiddleware,
    config=CSRFConfig(
        cookie_secure=(is_production or settings.sso.saml_enabled),
        exempt_paths=(
            "/health",
            "/health/live",
            "/health/ready",
            "/metrics",
            "/api/v1/sso/saml/acs",
            "/api/v1/sso/saml/sls",
            "/api/v1/sso/workos/webhooks/events",
            "/x402/validate",
            "/x402/audit",
            "/x402/certify",
            "/x402/batch",
            "/x402/treasury",
            "/x402/scan",
            "/x402/classify-risk",
            "/x402/compliance",
            "/x402/simulate",
            "/x402/trust",
            "/x402/anomaly",
            "/x402/explain",
            "/x402/invariant-guard",
            "/x402/circuit-breaker",
            "/x402/policy-lint",
            "/x402/eu-ai-log",
            "/x402/bundle/scout",
            "/x402/bundle/shield",
            "/x402/bundle/fortress",
        ),
        session_cookie_name="acgs2_session",
    ),
)
logger.info("CSRF middleware enabled for session-authenticated browser flows")

# Add rate limiting middleware per SPEC Section 3.3
# Enable only in production/staging or when explicitly configured
ENABLE_RATE_LIMITING = os.getenv("ENABLE_RATE_LIMITING", "true").lower() == "true"
if ENABLE_RATE_LIMITING:
    # Configure Redis-backed rate limiter with strict auth endpoint limits
    # Constitutional Hash: 608508a9bd224290
    rate_limit_rules = [
        # Auth endpoints - STRICT limits to prevent brute force attacks
        RateLimitRule(
            requests=10,
            window_seconds=60,
            scope=RateLimitScope.IP,
            endpoints=["/api/v1/auth/"],
        ),
        RateLimitRule(
            requests=5,
            window_seconds=60,
            scope=RateLimitScope.IP,
            endpoints=["/api/v1/sso/oidc/login", "/api/v1/sso/saml/login"],
        ),
        RateLimitRule(
            requests=20,
            window_seconds=60,
            scope=RateLimitScope.IP,
            endpoints=["/api/v1/sso/oidc/logout", "/api/v1/sso/saml/logout"],
        ),
        # Policy endpoints
        RateLimitRule(
            requests=100,
            window_seconds=60,
            scope=RateLimitScope.IP,
            endpoints=["/api/v1/policies"],
        ),
        # Validation endpoint - high volume
        RateLimitRule(
            requests=5000,
            window_seconds=60,
            scope=RateLimitScope.IP,
            endpoints=["/api/v1/validate"],
        ),
        # Health endpoints - very high limits
        RateLimitRule(
            requests=6000,
            window_seconds=60,
            scope=RateLimitScope.IP,
            endpoints=["/health"],
        ),
        # x402 free endpoints — prevent enumeration/DDoS
        RateLimitRule(
            requests=30,
            window_seconds=60,
            scope=RateLimitScope.IP,
            endpoints=[
                "/x402/check",
                "/x402/verify",
                "/x402/pricing",
                "/x402/health",
                "/x402/bundles",
                "/x402/facilitator-health",
            ],
        ),
        # x402 paid endpoints — generous but bounded (payment = auth)
        RateLimitRule(
            requests=500,
            window_seconds=60,
            scope=RateLimitScope.IP,
            endpoints=[
                "/x402/validate",
                "/x402/audit",
                "/x402/certify",
                "/x402/batch",
                "/x402/treasury",
                "/x402/scan",
                "/x402/classify-risk",
                "/x402/compliance",
                "/x402/simulate",
                "/x402/trust",
                "/x402/anomaly",
                "/x402/explain",
                "/x402/invariant-guard",
                "/x402/circuit-breaker",
                "/x402/policy-lint",
                "/x402/eu-ai-log",
                "/x402/bundle/scout",
                "/x402/bundle/shield",
                "/x402/bundle/fortress",
            ],
        ),
        # x402 admin endpoints — strict rate limit
        RateLimitRule(
            requests=10,
            window_seconds=60,
            scope=RateLimitScope.IP,
            endpoints=["/x402/revenue"],
        ),
        # Default for other endpoints
        RateLimitRule(
            requests=1000,
            window_seconds=60,
            scope=RateLimitScope.IP,
        ),
    ]

    configured_memory_fallback = _parse_bool_env(os.getenv("RATE_LIMIT_FALLBACK_TO_MEMORY"))
    if configured_memory_fallback is None:
        fallback_to_memory = is_development
    else:
        fallback_to_memory = configured_memory_fallback

    rate_limit_config = RateLimitConfig(
        rules=rate_limit_rules,
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
        fallback_to_memory=fallback_to_memory,
        enabled=True,
        fail_open=is_development,
        exempt_paths=["/docs", "/openapi.json", "/redoc", "/favicon.ico"],
    )

    _rate_limit_redis_client = None
    try:
        import redis.asyncio as _rate_limit_redis_async

        _rate_limit_redis_client = _rate_limit_redis_async.from_url(
            rate_limit_config.redis_url,
            decode_responses=True,
        )
    except Exception:
        _rate_limit_redis_client = None

    app.add_middleware(
        RateLimitMiddleware,
        config=rate_limit_config,
        redis_client=_rate_limit_redis_client,
    )
    logger.info(
        "Redis-backed rate limiting enabled with strict auth limits",
        extra={
            "auth_limit": "10 req/min",
            "login_limit": "5 req/min",
            "logout_limit": "20 req/min",
            "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379"),
            "backend_mode": "redis" if _rate_limit_redis_client is not None else "memory",
            "fallback_to_memory": fallback_to_memory,
            "constitutional_hash": CONSTITUTIONAL_HASH,  # pragma: allowlist secret
        },
    )
else:
    logger.info("Rate limiting middleware disabled")

# PQCOnlyModeMiddleware — rejects classical algorithm requests when PQC_ONLY_MODE is active.
# Registered before business-logic middleware so classical requests never reach downstream handlers.
# (Constitutional Hash: 608508a9bd224290)
_pqc_redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
try:
    import redis.asyncio as _aioredis

    _pqc_redis_client = _aioredis.from_url(_pqc_redis_url, decode_responses=True)
except Exception:
    _pqc_redis_client = None  # type: ignore[assignment]
app.add_middleware(PQCOnlyModeMiddleware, redis_client=_pqc_redis_client)
logger.info("PQCOnlyModeMiddleware registered in middleware stack")

# AutonomyTierEnforcementMiddleware — added after authentication, before proxy forwarding
# (Constitutional Hash: 608508a9bd224290)
# The HITL client is set in lifespan via app.state.hitl_client.
# The tier repository is resolved per-request via dependency_overrides or app.state.tier_repo_factory.
app.add_middleware(AutonomyTierEnforcementMiddleware)
logger.info("AutonomyTierEnforcementMiddleware registered in middleware stack")

# Include health check router per SPEC Section 3.3
health_router = create_health_router(
    database_url=os.getenv("DATABASE_URL"),
    redis_url=os.getenv("REDIS_URL"),
    opa_url=os.getenv("OPA_URL", "http://localhost:8181"),
)
app.include_router(health_router)
logger.info("Health check endpoints configured: /health, /health/live, /health/ready")

# Health check endpoint moved to health.py router
# See: /health, /health/live, /health/ready

# Include versioned gateway router (feedback, services, version docs)
app.include_router(gateway_v1_router)
logger.info("API v1 gateway routes configured: /api/v1/gateway/*")


# ============================================================================
# SSO Routers (Already versioned with /api/v1/ prefix)
# ============================================================================

# Include SSO router for OIDC/SAML authentication
# sso_router already has /api/v1/sso prefix internally - include without additional prefix
# Final paths: /api/v1/sso/oidc/*, /api/v1/sso/saml/*, /api/v1/sso/session
app.include_router(sso_router)
logger.info("SSO routes configured: /api/v1/sso/*")

# Include Admin SSO router for SSO provider configuration
# admin_sso_router already has /api/v1/admin/sso prefix internally - include without additional prefix
# Final paths: /api/v1/admin/sso/providers, /api/v1/admin/sso/role-mappings
app.include_router(admin_sso_router)
logger.info("Admin SSO routes configured: /api/v1/admin/sso/*")

# Include Admin WorkOS router for enterprise setup and event pull operations
# Final paths: /api/v1/admin/sso/workos/portal-links, /api/v1/admin/sso/workos/events
app.include_router(admin_workos_router)
logger.info("Admin WorkOS routes configured: /api/v1/admin/sso/workos/*")

# Include Decisions router for FR-12 Decision Explanation API
# decisions_v1_router has /api/v1/decisions prefix internally
# Final paths: /api/v1/decisions/{id}/explain, /api/v1/decisions/explain
app.include_router(decisions_v1_router)
logger.info("Decisions routes configured: /api/v1/decisions/*")

# Include Data Subject Rights router for GDPR/CCPA compliance (§16.4)
# data_subject_v1_router has /api/v1/data-subject prefix internally
# Final paths: /api/v1/data-subject/access, /api/v1/data-subject/erasure, etc.
app.include_router(data_subject_v1_router)
logger.info("Data Subject Rights routes configured: /api/v1/data-subject/*")

# Include compliance router (EU AI Act compliance toolkit)
# compliance_router has /compliance prefix; mounted under /api/v1
# Final paths: /api/v1/compliance/assess, /api/v1/compliance/gaps/{system_id}
app.include_router(compliance_router, prefix="/api/v1", tags=["compliance"])
logger.info("Compliance routes configured: /api/v1/compliance/*")

# Include admin autonomy-tiers router (Safe Autonomy Tiers — ACGS-AI-007)
# autonomy_tiers_router has /autonomy-tiers prefix; mounted under /api/v1/admin
# Final paths: /api/v1/admin/autonomy-tiers, /api/v1/admin/autonomy-tiers/{agent_id}
# Constitutional Hash: 608508a9bd224290
app.include_router(autonomy_tiers_router, prefix="/api/v1/admin", tags=["autonomy-tiers"])
logger.info("Admin autonomy-tiers routes configured: /api/v1/admin/autonomy-tiers/*")

# Include self-evolution evidence router for operator/admin read access
# evidence_router has /evolution prefix; mounted under /api/v1/admin with admin RBAC
# Final paths: /api/v1/admin/evolution/bounded-experiments, /api/v1/admin/evolution/bounded-experiments/{evidence_id}
if _SELF_EVOLUTION_AVAILABLE and evidence_router is not None:
    app.include_router(
        evidence_router,
        prefix="/api/v1/admin",
        tags=["self-evolution-evidence"],
        dependencies=[Depends(require_role("admin"))],
    )
logger.info(
    "Self-evolution evidence routes configured: /api/v1/admin/evolution/bounded-experiments*"
)

# Include self-evolution operator control router for admin pause/resume/stop and status
# Final paths: /api/v1/admin/evolution/operator-control*
app.include_router(
    evolution_control_router,
    prefix="/api/v1/admin",
    tags=["self-evolution-control"],
    dependencies=[Depends(require_role("admin"))],
)
logger.info(
    "Self-evolution operator control routes configured: /api/v1/admin/evolution/operator-control*"
)

# Include PQC Phase 5 admin routes (PQC-only mode activation/status)
# pqc_phase5_router has /pqc-only-mode prefix; mounted under /api/v1/admin/pqc
# Final paths: /api/v1/admin/pqc/pqc-only-mode/activate, /api/v1/admin/pqc/pqc-only-mode/status
# Constitutional Hash: 608508a9bd224290
app.include_router(pqc_phase5_router, prefix="/api/v1/admin/pqc", tags=["PQC Phase 5 Admin"])
logger.info("PQC Phase 5 admin routes configured: /api/v1/admin/pqc/pqc-only-mode/*")

# Include x402 Governance-as-a-Service routes (pay-per-call constitutional validation)
# Endpoints: /x402/pricing, /x402/validate, /x402/treasury, /x402/health
# Constitutional Hash: 608508a9bd224290
ensure_attestation_secret_config()
app.include_router(x402_governance_router)
app.include_router(x402_bundles_router)
app.include_router(x402_facilitator_router)
app.include_router(x402_revenue_router)

# x402 Marketplace (premium endpoints) — opt-in via X402_MARKETPLACE=true
# Disabled by default to focus GTM on core governance endpoints.
X402_MARKETPLACE_ENABLED = os.getenv("X402_MARKETPLACE", "false").lower() == "true"
if X402_MARKETPLACE_ENABLED:
    app.include_router(x402_marketplace_router)
    logger.info("x402 marketplace routes enabled (X402_MARKETPLACE=true)")
else:
    logger.info("x402 marketplace routes disabled (set X402_MARKETPLACE=true to enable)")

logger.info(
    "x402 routes configured: governance + bundles + facilitator + revenue"
)

configure_x402_payment_middleware(app, environ=os.environ)

# Proxy catch-all MUST be included LAST so it does not shadow other routes
app.include_router(proxy_router)
logger.info("Proxy catch-all route configured: /{path:path}")


if __name__ == "__main__":
    import uvicorn

    environment = _runtime_environment()
    is_development = environment in {"development", "dev", "test", "testing", "ci"}
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8080,
        reload=is_development,
        log_level="info",
        loop="uvloop",
        http="httptools",
    )
