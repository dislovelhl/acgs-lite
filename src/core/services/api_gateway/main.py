"""Constitutional Hash: cdd01ef066bc6cf2
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
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.fastapi_base import create_acgs_app

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
    x402_governance_router,
    x402_marketplace_router,
)

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

environment = os.getenv("ENVIRONMENT", "production").strip().lower()
is_development = environment in {"development", "dev", "test", "testing", "ci"}

app = create_acgs_app(
    "api-gateway",
    environment=settings.env,
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

# GZip compression for responses > 1KB (60-70% bandwidth reduction for JSON payloads)
from starlette.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)

# ============================================================================
# API Versioning Configuration (Constitutional Hash: cdd01ef066bc6cf2)
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

# Add SessionMiddleware for OAuth state management
# Use JWT secret if available, otherwise generate a secure random key for development
env = os.getenv("ENVIRONMENT", os.getenv("ENV", "development")).lower()

# Add security headers middleware (CSP, X-Frame-Options, HSTS, etc.)
add_security_headers(app, environment=env)
is_production = env in ("production", "prod", "staging")

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
    https_only=(settings.env == "production" or settings.sso.saml_enabled),
)
logger.info("SessionMiddleware configured for OAuth state management")

app.add_middleware(
    CSRFMiddleware,
    config=CSRFConfig(
        cookie_secure=(settings.env == "production" or settings.sso.saml_enabled),
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
    # Constitutional Hash: cdd01ef066bc6cf2
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
            endpoints=["/x402/check", "/x402/verify", "/x402/pricing", "/x402/health"],
        ),
        # x402 paid endpoints — generous but bounded (payment = auth)
        RateLimitRule(
            requests=500,
            window_seconds=60,
            scope=RateLimitScope.IP,
            endpoints=[
                "/x402/validate", "/x402/audit", "/x402/certify", "/x402/batch",
                "/x402/treasury", "/x402/scan", "/x402/classify-risk",
                "/x402/compliance", "/x402/simulate", "/x402/trust",
                "/x402/anomaly", "/x402/explain", "/x402/invariant-guard",
                "/x402/circuit-breaker", "/x402/policy-lint", "/x402/eu-ai-log",
            ],
        ),
        # Default for other endpoints
        RateLimitRule(
            requests=1000,
            window_seconds=60,
            scope=RateLimitScope.IP,
        ),
    ]

    rate_limit_config = RateLimitConfig(
        rules=rate_limit_rules,
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
        fallback_to_memory=True,
        enabled=True,
        exempt_paths=["/docs", "/openapi.json", "/redoc", "/favicon.ico"],
    )

    app.add_middleware(RateLimitMiddleware, config=rate_limit_config)
    logger.info(
        "Redis-backed rate limiting enabled with strict auth limits",
        extra={
            "auth_limit": "10 req/min",
            "login_limit": "5 req/min",
            "logout_limit": "20 req/min",
            "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379"),
            "constitutional_hash": CONSTITUTIONAL_HASH,  # pragma: allowlist secret
        },
    )
else:
    logger.info("Rate limiting middleware disabled")

# PQCOnlyModeMiddleware — rejects classical algorithm requests when PQC_ONLY_MODE is active.
# Registered before business-logic middleware so classical requests never reach downstream handlers.
# (Constitutional Hash: cdd01ef066bc6cf2)
_pqc_redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
try:
    import redis.asyncio as _aioredis

    _pqc_redis_client = _aioredis.from_url(_pqc_redis_url, decode_responses=True)
except Exception:
    _pqc_redis_client = None  # type: ignore[assignment]
app.add_middleware(PQCOnlyModeMiddleware, redis_client=_pqc_redis_client)
logger.info("PQCOnlyModeMiddleware registered in middleware stack")

# AutonomyTierEnforcementMiddleware — added after authentication, before proxy forwarding
# (Constitutional Hash: cdd01ef066bc6cf2)
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
# Constitutional Hash: cdd01ef066bc6cf2
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
# Constitutional Hash: cdd01ef066bc6cf2
app.include_router(pqc_phase5_router, prefix="/api/v1/admin/pqc", tags=["PQC Phase 5 Admin"])
logger.info("PQC Phase 5 admin routes configured: /api/v1/admin/pqc/pqc-only-mode/*")

# Include x402 Governance-as-a-Service routes (pay-per-call constitutional validation)
# Endpoints: /x402/pricing, /x402/validate, /x402/treasury, /x402/health
# Constitutional Hash: cdd01ef066bc6cf2
app.include_router(x402_governance_router)
app.include_router(x402_marketplace_router)
logger.info(
    "x402 routes configured: governance (check/validate/audit/certify/batch/treasury) "
    "+ marketplace (scan/classify-risk/compliance/simulate/trust/anomaly/explain)"
)

# x402 Payment Middleware — activates only when EVM_ADDRESS is set
_x402_pay_to = os.getenv("EVM_ADDRESS", "")
if _x402_pay_to:
    try:
        from x402 import FacilitatorConfig
        from x402.http import HTTPFacilitatorClient
        from x402.http.middleware.fastapi import PaymentMiddlewareASGI
        from x402.http.types import PaymentOption
        from x402.http.types import RouteConfig as X402RouteConfig
        from x402.mechanisms.evm.exact import ExactEvmServerScheme
        from x402.server import x402ResourceServer

        _x402_network = os.getenv("X402_NETWORK", "eip155:84532")
        _price_validate = os.getenv("X402_PRICE_VALIDATE", "0.01")
        _price_audit = os.getenv("X402_PRICE_AUDIT", "0.05")
        _price_certify = os.getenv("X402_PRICE_CERTIFY", "0.50")
        _price_batch = os.getenv("X402_PRICE_BATCH", "0.10")
        _price_treasury = os.getenv("X402_PRICE_TREASURY", "0.05")
        _x402_facilitator_url = os.getenv(
            "FACILITATOR_URL", "https://facilitator.xpay.sh"
        )

        _facilitator_cfg = FacilitatorConfig(url=_x402_facilitator_url)
        _facilitator_client = HTTPFacilitatorClient(_facilitator_cfg)
        _x402_server = x402ResourceServer([_facilitator_client])
        _x402_server.register(_x402_network, ExactEvmServerScheme())

        def _make_option(price: str) -> PaymentOption:
            return PaymentOption(
                scheme="exact",
                pay_to=_x402_pay_to,
                price=f"${price}",
                network=_x402_network,
            )

        _bazaar_meta = {
            "bazaar": {
                "category": "governance",
                "tags": ["ai", "compliance", "constitutional", "maci"],
            },
        }

        _x402_routes = {
            "POST /x402/validate": X402RouteConfig(
                accepts=[_make_option(_price_validate)],
                description="Governance validation ($" + _price_validate + ")",
                extensions=_bazaar_meta,
            ),
            "POST /x402/audit": X402RouteConfig(
                accepts=[_make_option(_price_audit)],
                description="Compliance audit with risk breakdown ($" + _price_audit + ")",
                extensions=_bazaar_meta,
            ),
            "POST /x402/certify": X402RouteConfig(
                accepts=[_make_option(_price_certify)],
                description="Signed attestation — verifiable compliance proof ($" + _price_certify + ")",
                extensions=_bazaar_meta,
            ),
            "POST /x402/batch": X402RouteConfig(
                accepts=[_make_option(_price_batch)],
                description="Bulk validation up to 20 actions ($" + _price_batch + ")",
                extensions=_bazaar_meta,
            ),
            "POST /x402/treasury": X402RouteConfig(
                accepts=[_make_option(_price_treasury)],
                description="DAO treasury intelligence ($" + _price_treasury + ")",
                extensions=_bazaar_meta,
            ),
            # Marketplace endpoints (market-rate pricing)
            "POST /x402/scan": X402RouteConfig(
                accepts=[_make_option(os.getenv("X402_PRICE_SCAN", "0.03"))],
                description="Prompt injection detection ($0.03)",
                extensions=_bazaar_meta,
            ),
            "POST /x402/classify-risk": X402RouteConfig(
                accepts=[_make_option(os.getenv("X402_PRICE_CLASSIFY_RISK", "0.10"))],
                description="EU AI Act risk classification ($0.10)",
                extensions=_bazaar_meta,
            ),
            "POST /x402/compliance": X402RouteConfig(
                accepts=[_make_option(os.getenv("X402_PRICE_COMPLIANCE", "0.25"))],
                description="Multi-framework compliance — 8 frameworks ($0.25)",
                extensions=_bazaar_meta,
            ),
            "POST /x402/simulate": X402RouteConfig(
                accepts=[_make_option(os.getenv("X402_PRICE_SIMULATE", "0.15"))],
                description="Policy change simulation ($0.15)",
                extensions=_bazaar_meta,
            ),
            "POST /x402/trust": X402RouteConfig(
                accepts=[_make_option(os.getenv("X402_PRICE_TRUST", "0.02"))],
                description="Agent trust scoring ($0.02)",
                extensions=_bazaar_meta,
            ),
            "POST /x402/anomaly": X402RouteConfig(
                accepts=[_make_option(os.getenv("X402_PRICE_ANOMALY", "0.03"))],
                description="Governance anomaly detection ($0.03)",
                extensions=_bazaar_meta,
            ),
            "POST /x402/explain": X402RouteConfig(
                accepts=[_make_option(os.getenv("X402_PRICE_EXPLAIN", "0.05"))],
                description="Decision explainability ($0.05)",
                extensions=_bazaar_meta,
            ),
            # Premium endpoints
            "POST /x402/invariant-guard": X402RouteConfig(
                accepts=[_make_option(os.getenv("X402_PRICE_INVARIANT", "0.10"))],
                description="Three-tier invariant enforcement ($0.10)",
                extensions=_bazaar_meta,
            ),
            "POST /x402/circuit-breaker": X402RouteConfig(
                accepts=[_make_option(os.getenv("X402_PRICE_CIRCUIT", "0.10"))],
                description="Governance circuit breaker ($0.10)",
                extensions=_bazaar_meta,
            ),
            "POST /x402/policy-lint": X402RouteConfig(
                accepts=[_make_option(os.getenv("X402_PRICE_POLICY_LINT", "0.05"))],
                description="Policy quality & security scan ($0.05)",
                extensions=_bazaar_meta,
            ),
            "POST /x402/eu-ai-log": X402RouteConfig(
                accepts=[_make_option(os.getenv("X402_PRICE_EU_AI_LOG", "0.10"))],
                description="EU AI Act Article 12 logging ($0.10)",
                extensions=_bazaar_meta,
            ),
        }

        app.add_middleware(
            PaymentMiddlewareASGI,
            routes=_x402_routes,
            server=_x402_server,
        )
        logger.info(
            "x402 payment middleware ACTIVE",
            network=_x402_network,
            prices={
                "validate": _price_validate,
                "audit": _price_audit,
                "certify": _price_certify,
                "batch": _price_batch,
                "treasury": _price_treasury,
            },
            facilitator=_x402_facilitator_url,
            pay_to=_x402_pay_to[:10] + "...",
        )
    except ImportError:
        logger.warning(
            "EVM_ADDRESS set but x402[evm] not installed — "
            "payment middleware disabled. Run: pip install 'x402[evm]'"
        )
else:
    logger.info("x402 payment middleware disabled (EVM_ADDRESS not set)")

# Proxy catch-all MUST be included LAST so it does not shadow other routes
app.include_router(proxy_router)
logger.info("Proxy catch-all route configured: /{path:path}")


if __name__ == "__main__":
    import uvicorn

    environment = os.getenv("ENVIRONMENT", "production").strip().lower()
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
