"""Constitutional Hash: cdd01ef066bc6cf2
ACGS-2 API Gateway
Simple development API gateway for routing requests to services

Implements:
- Rate limiting per SPEC_ACGS2_ENHANCED.md Section 3.3
- Health endpoints per SPEC_ACGS2_ENHANCED.md Section 3.3
- API Versioning with /api/v1/ prefix and X-API-Version headers
"""

import asyncio
import json
import os
import re
import secrets
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
import redis.asyncio
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from redis.exceptions import RedisError

# Import rate limiting and health modules
from starlette.middleware.sessions import SessionMiddleware

try:
    from src.core.self_evolution.api import evidence_router

    _SELF_EVOLUTION_AVAILABLE = True
except ImportError:
    evidence_router = None  # type: ignore[assignment]
    _SELF_EVOLUTION_AVAILABLE = False

try:
    from src.core.self_evolution.research.operator_control import (
        DEFAULT_RESEARCH_OPERATOR_CONTROL_KEY_PREFIX,
        create_research_operator_control_plane,
    )
except ImportError:
    DEFAULT_RESEARCH_OPERATOR_CONTROL_KEY_PREFIX = "acgs:research:operator_control"

    async def create_research_operator_control_plane(**kwargs):  # type: ignore[misc]
        """Stub when self_evolution module is not installed."""
        return None
from src.core.shared.api_versioning import (
    DEPRECATED_ROUTES,
    DEPRECATED_VERSIONS,
    SUPPORTED_VERSIONS,
    APIVersioningMiddleware,
    DeprecationNoticeMiddleware,
    VersioningConfig,
    create_version_info_endpoint,
    create_version_metrics_endpoint,
    create_versioned_router,
    get_versioning_documentation,
)
from src.core.shared.config import settings
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.fastapi_base import create_acgs_app
from src.core.shared.metrics import track_request_metrics
from src.core.shared.otel_config import init_otel
from src.core.shared.redis_config import get_redis_url
from src.core.shared.security.auth import (
    UserClaims,
    get_current_user,
    get_current_user_optional,
    require_role,
)
from src.core.shared.security.rate_limiter import (
    RateLimitConfig,
    RateLimitMiddleware,
    RateLimitRule,
    RateLimitScope,
    rate_limiter,
)
from src.core.shared.security.security_headers import add_security_headers
from src.core.shared.structured_logging import configure_logging, get_logger
from src.core.shared.types import JSONDict

from .health import create_health_router
from .metrics import record_feedback_rejection, record_feedback_submission
from .middleware.autonomy_tier import AutonomyTierEnforcementMiddleware, HttpHitlSubmissionClient
from .middleware.pqc_only_mode import PQCOnlyModeMiddleware
from .routes import (
    admin_sso_router,
    admin_workos_router,
    autonomy_tiers_router,
    compliance_router,
    data_subject_v1_router,
    decisions_v1_router,
    evolution_control_router,
    sso_router,
    x402_governance_router,
)
from .routes.pqc_phase5 import pqc_phase5_router

# Service name for logging and tracing
SERVICE_NAME = "api_gateway"

# Configure structured logging (MUST be called before any logging)
configure_logging()

# Get structured logger
logger = get_logger(__name__)

# Feedback stats cache
_feedback_stats_cache: dict = {"data": None, "timestamp": 0.0}
_FEEDBACK_STATS_TTL = 60.0  # 1 minute cache TTL
_FEEDBACK_ANONYMOUS_RATE_LIMIT = 20
_FEEDBACK_AUTHENTICATED_RATE_LIMIT = 60
_FEEDBACK_RATE_WINDOW_SECONDS = 60
_FEEDBACK_MAX_METADATA_BYTES = 8 * 1024
_FEEDBACK_MAX_REQUEST_BYTES = 16 * 1024
# Shared httpx client for proxy requests (Constitutional Hash: cdd01ef066bc6cf2)
_proxy_client: httpx.AsyncClient | None = None
_proxy_client_lock = asyncio.Lock()
_feedback_redis_client: redis.asyncio.Redis | None = None
_feedback_redis_lock = asyncio.Lock()


async def get_proxy_client() -> httpx.AsyncClient:
    """Get or create the shared httpx proxy client (thread-safe)."""
    global _proxy_client
    if _proxy_client is not None and not _proxy_client.is_closed:
        return _proxy_client
    async with _proxy_client_lock:
        # Double-check after acquiring lock
        if _proxy_client is None or _proxy_client.is_closed:
            _proxy_client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
    return _proxy_client


async def close_proxy_client() -> None:
    """Gracefully close the shared httpx proxy client."""
    global _proxy_client
    async with _proxy_client_lock:
        if _proxy_client is not None and not _proxy_client.is_closed:
            await _proxy_client.aclose()
            _proxy_client = None


def get_cached_feedback_stats() -> dict | None:
    """Get cached feedback stats if valid."""
    now = time.time()
    if (
        _feedback_stats_cache["data"]
        and (now - _feedback_stats_cache["timestamp"]) < _FEEDBACK_STATS_TTL
    ):
        return _feedback_stats_cache["data"]
    return None


def update_feedback_stats_cache(stats: dict) -> None:
    """Update the feedback stats cache."""
    _feedback_stats_cache["data"] = stats
    _feedback_stats_cache["timestamp"] = time.time()


environment = os.getenv("ENVIRONMENT", "production").strip().lower()
is_development = environment in {"development", "dev", "test", "testing", "ci"}


@asynccontextmanager
def _verify_constitutional_hash_at_startup() -> None:
    """M-5 fix: Verify CONSTITUTIONAL_HASH matches the env-provided hash at startup.

    In production, operators must set CONSTITUTIONAL_HASH env var explicitly.
    This prevents a tampered deployment from silently bypassing governance by
    using a stale/wrong hash embedded in the codebase.

    In development mode, a mismatch is logged as a warning but does not block.
    """
    env_hash = os.getenv("CONSTITUTIONAL_HASH")
    if not env_hash:
        if not is_development:
            logger.error(
                "CONSTITUTIONAL_HASH env var not set in production — "
                "governance integrity cannot be verified; refusing to start",
                code_hash=CONSTITUTIONAL_HASH,
            )
            raise RuntimeError(
                "CONSTITUTIONAL_HASH must be set explicitly in production. "
                f"Current code constant: {CONSTITUTIONAL_HASH}"
            )
        logger.warning(
            "CONSTITUTIONAL_HASH env var not set; using code constant (dev only)",
            code_hash=CONSTITUTIONAL_HASH,
        )
        return

    if env_hash != CONSTITUTIONAL_HASH:
        msg = (
            f"Constitutional hash mismatch — env={env_hash!r} code={CONSTITUTIONAL_HASH!r}. "
            "Deployment may be tampered or misconfigured."
        )
        if not is_development:
            logger.error(msg)
            raise RuntimeError(msg)
        logger.warning(msg + " (dev mode — continuing)")
    else:
        logger.info(
            "Constitutional hash verified at startup",
            hash=CONSTITUTIONAL_HASH,
        )


async def lifespan(app_instance: FastAPI) -> AsyncGenerator[None, None]:
    """Manage shared client lifecycle (startup/shutdown)."""
    # Startup: verify constitutional hash integrity (M-5)
    _verify_constitutional_hash_at_startup()
    # Startup: initialize HITL client for autonomy tier enforcement
    hitl_url = os.getenv("HITL_URL", "http://localhost:8002")
    app_instance.state.hitl_client = HttpHitlSubmissionClient(url=hitl_url)
    operator_control_backend = os.getenv("SELF_EVOLUTION_OPERATOR_CONTROL_BACKEND", "memory")
    operator_control_redis_url = os.getenv(
        "SELF_EVOLUTION_OPERATOR_CONTROL_REDIS_URL",
        get_redis_url(db=0),
    )
    operator_control_key_prefix = os.getenv(
        "SELF_EVOLUTION_OPERATOR_CONTROL_KEY_PREFIX",
        DEFAULT_RESEARCH_OPERATOR_CONTROL_KEY_PREFIX,
    )
    app_instance.state.research_operator_control_plane = create_research_operator_control_plane(
        backend=operator_control_backend,
        redis_url=operator_control_redis_url if operator_control_backend == "redis" else None,
        key_prefix=operator_control_key_prefix,
    )
    logger.info(
        "AutonomyTierEnforcementMiddleware initialized",
        hitl_url=hitl_url,
        middleware_stack_position="after_authentication,before_proxy",
    )
    logger.info(
        "Self-evolution operator control initialized",
        backend=operator_control_backend,
        key_prefix=operator_control_key_prefix,
    )
    yield
    # Shutdown: close all shared clients gracefully
    research_operator_control_plane = getattr(
        app_instance.state,
        "research_operator_control_plane",
        None,
    )
    if research_operator_control_plane is not None:
        await research_operator_control_plane.aclose()
    await close_proxy_client()
    await _close_feedback_redis()
    logger.info("API Gateway shut down cleanly")


app = create_acgs_app(
    "api-gateway",
    title="ACGS-2 API Gateway",
    description="Development API Gateway for ACGS-2 services with constitutional governance",
    version="1.0.0",
    docs_url="/docs" if is_development else None,
    redoc_url="/redoc" if is_development else None,
    openapi_url="/openapi.json" if is_development else None,
    default_response_class=ORJSONResponse,
    include_default_health_routes=False,
    lifespan=lifespan,
    logger=logger,
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

# Service URLs from centralized config
AGENT_BUS_URL = settings.services.agent_bus_url
ENVIRONMENT = settings.env

# Feedback storage configuration using Redis for persistence
# Constitutional Hash: cdd01ef066bc6cf2
FEEDBACK_REDIS_PREFIX = "acgs:feedback:"
FEEDBACK_REDIS_TTL = 60 * 60 * 24 * 90  # 90 days

# Redis URL from centralized config (not hardcoded)
_feedback_redis_url = get_redis_url(db=0)


async def get_feedback_redis() -> redis.asyncio.Redis:
    """Get or create Redis client for feedback storage (thread-safe)."""
    global _feedback_redis_client
    if _feedback_redis_client is not None:
        return _feedback_redis_client
    async with _feedback_redis_lock:
        if _feedback_redis_client is None:
            _feedback_redis_client = redis.asyncio.from_url(
                _feedback_redis_url,
                decode_responses=True,
            )
    return _feedback_redis_client


async def _close_feedback_redis() -> None:
    """Gracefully close the feedback Redis client."""
    global _feedback_redis_client
    async with _feedback_redis_lock:
        if _feedback_redis_client is not None:
            await _feedback_redis_client.aclose()
            _feedback_redis_client = None


# Feedback Models
class FeedbackRequest(BaseModel):
    """User feedback request model"""

    user_id: str = Field(default="", max_length=128, description="User identifier")
    category: str = Field(
        default="",
        max_length=32,
        description="Feedback category (bug, feature, general)",
    )
    rating: int = Field(default=1, ge=1, le=5, description="Rating from 1-5")
    title: str = Field(default="", max_length=200, description="Feedback title")
    description: str = Field(
        default="",
        max_length=5000,
        description="Detailed feedback description",
    )
    user_agent: str = Field(default="", max_length=512, description="User agent string")
    url: str = Field(default="", max_length=2048, description="Current URL when feedback was given")
    metadata: JSONDict = Field(default_factory=dict, description="Additional metadata")
    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH,
        description="Constitutional hash for governance validation",
    )

    @field_validator("metadata")
    @classmethod
    def validate_metadata_size(cls, value: JSONDict) -> JSONDict:
        """Reject oversized feedback metadata before storage."""
        if (
            len(json.dumps(value, separators=(",", ":")).encode("utf-8"))
            > _FEEDBACK_MAX_METADATA_BYTES
        ):
            raise ValueError("Feedback metadata exceeds size limit")
        return value

    @model_validator(mode="after")
    def validate_total_payload_size(self) -> "FeedbackRequest":
        """Enforce a conservative total payload size for public feedback submissions."""
        payload = {
            "user_id": self.user_id,
            "category": self.category,
            "rating": self.rating,
            "title": self.title,
            "description": self.description,
            "user_agent": self.user_agent,
            "url": self.url,
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
        }
        if (
            len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
            > _FEEDBACK_MAX_REQUEST_BYTES
        ):
            raise ValueError("Feedback payload exceeds size limit")
        return self

    def model_post_init(self, __context: object) -> None:
        self._constitutional_hash = self.constitutional_hash

    def process(self, input_value: str | None) -> str | None:
        """Validate and normalize input."""
        if input_value is None or not isinstance(input_value, str):
            return None
        return input_value


class FeedbackResponse(BaseModel):
    """Feedback submission response"""

    feedback_id: str
    status: str
    timestamp: str
    message: str


# Health check endpoint moved to health.py router
# See: /health, /health/live, /health/ready


# ============================================================================
# Versioned Gateway Router (API v1)
# Constitutional Hash: cdd01ef066bc6cf2
# ============================================================================

# Create versioned router for gateway endpoints
gateway_v1_router = create_versioned_router(
    prefix="/gateway",
    version="v1",
    tags=["Gateway (v1)"],
)

# Add version info and metrics endpoints to the gateway router
create_version_info_endpoint(gateway_v1_router)
create_version_metrics_endpoint(gateway_v1_router)


def _get_feedback_source_identifier(request: Request) -> str:
    """Return the best available source identifier for feedback throttling/logging."""
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        candidate = forwarded_for.split(",", maxsplit=1)[0].strip()
        if candidate:
            return candidate
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _hash_ip_for_storage(ip: str) -> str:
    """Hash an IP address for GDPR-compliant storage (H-2 fix).

    Uses SHA-256 with a daily rotating salt so the hash can still be used
    for abuse detection within a 24h window but cannot be reversed to
    recover the original IP address.
    """
    import hashlib

    daily_salt = datetime.now(UTC).strftime("%Y-%m-%d")
    return hashlib.sha256(f"{ip}:{daily_salt}".encode()).hexdigest()[:16]


async def _enforce_feedback_submission_policy(
    request: Request,
    user: UserClaims | None = Depends(get_current_user_optional),
) -> UserClaims | None:
    """Apply route-specific abuse controls for the public feedback endpoint."""
    source_id = _get_feedback_source_identifier(request)
    auth_mode = "authenticated" if user else "anonymous"
    if user:
        result = await rate_limiter.is_allowed(
            key=f"api-gateway:feedback:user:{user.sub}",
            limit=_FEEDBACK_AUTHENTICATED_RATE_LIMIT,
            window_seconds=_FEEDBACK_RATE_WINDOW_SECONDS,
            scope=RateLimitScope.USER,
        )
    else:
        result = await rate_limiter.is_allowed(
            key=f"api-gateway:feedback:ip:{source_id}",
            limit=_FEEDBACK_ANONYMOUS_RATE_LIMIT,
            window_seconds=_FEEDBACK_RATE_WINDOW_SECONDS,
            scope=RateLimitScope.IP,
        )

    if not result.allowed:
        record_feedback_rejection(reason="rate_limit", auth_mode=auth_mode)
        logger.warning(
            "feedback_rate_limited",
            auth_mode=auth_mode,
            source_id=source_id,
            authenticated_user_id=user.sub if user else None,
            limit=result.limit,
            retry_after=result.retry_after,
        )
        raise HTTPException(
            status_code=429,
            detail="Feedback submission rate limit exceeded",
            headers=result.to_headers(),
        )

    return user


@gateway_v1_router.get(
    "/version/docs",
    summary="Get API Versioning Documentation",
    description="Returns comprehensive documentation about API versioning strategy.",
    tags=["Version"],
)
async def get_versioning_docs() -> dict:
    """Get API versioning documentation and strategy."""
    return get_versioning_documentation()


# User Feedback Collection (Versioned: /api/v1/gateway/feedback)
@gateway_v1_router.post(
    "/feedback",
    response_model=FeedbackResponse,
    summary="Submit public gateway feedback",
    description=(
        "Public feedback submission endpoint. Anonymous submissions are allowed by policy, "
        "while authenticated callers may also submit feedback. This route is an explicit "
        "exception to the default authenticated gateway write posture. Caller-supplied user_id "
        "is treated as metadata and must match the authenticated identity when auth is present."
    ),
)
@track_request_metrics("api-gateway", "/api/v1/gateway/feedback")
async def submit_feedback_v1(
    feedback: FeedbackRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user: UserClaims | None = Depends(_enforce_feedback_submission_policy),
):
    """Submit user feedback for ACGS-2 (API v1)"""
    try:
        source_id = _get_feedback_source_identifier(request)
        if user and feedback.user_id != user.sub:
            record_feedback_rejection(reason="identity_mismatch", auth_mode="authenticated")
            logger.warning(
                "feedback_identity_mismatch",
                authenticated_user_id=user.sub,
                submitted_user_id=feedback.user_id,
                source_id=source_id,
            )
            raise HTTPException(status_code=403, detail="User ID mismatch")
        # Generate feedback ID
        import uuid

        feedback_id = str(uuid.uuid4())

        # Create feedback record
        feedback_record = {
            "feedback_id": feedback_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "user_id": feedback.user_id,
            "category": feedback.category,
            "rating": feedback.rating,
            "title": feedback.title,
            "description": feedback.description,
            "user_agent": feedback.user_agent or request.headers.get("user-agent", ""),
            "url": feedback.url,
            "ip_address_hash": _hash_ip_for_storage(source_id),
            "metadata": feedback.metadata,
            "authenticated_user_id": user.sub if user else None,
            "user_id_verified": bool(user),
            "submission_auth_mode": "authenticated" if user else "anonymous",
            "environment": ENVIRONMENT,
        }

        # Save feedback asynchronously
        background_tasks.add_task(save_feedback_to_redis, feedback_record)
        record_feedback_submission(
            auth_mode=feedback_record["submission_auth_mode"],
            category=feedback.category,
            user_id_verified=feedback_record["user_id_verified"],
        )

        logger.info(
            "feedback_submitted",
            feedback_id=feedback_id,
            category=feedback.category,
            auth_mode=feedback_record["submission_auth_mode"],
            authenticated_user_id=feedback_record["authenticated_user_id"],
            user_id_verified=feedback_record["user_id_verified"],
            source_id=source_id,
        )

        return FeedbackResponse(
            feedback_id=feedback_id,
            status="submitted",
            timestamp=feedback_record["timestamp"],
            message="Thank you for your feedback! We'll review it shortly.",
        )

    except (ValueError, TypeError, KeyError, LookupError) as e:
        logger.error(f"Error processing feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to process feedback") from e


@gateway_v1_router.get("/feedback/stats")
@track_request_metrics("api-gateway", "/api/v1/gateway/feedback/stats")
async def get_feedback_stats_v1(
    user: UserClaims = Depends(get_current_user_optional),
):
    """Get feedback statistics (admin endpoint) (API v1)"""
    # Check for admin role
    if not user or "admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Admin role required")

    try:
        # Log access for audit purposes
        logger.info(
            "Feedback stats accessed",
            user_id=user.sub,
            tenant_id=user.tenant_id,
            roles=user.roles,
        )

        # Gather stats from Redis
        redis_client = await get_feedback_redis()
        feedback_keys = []
        async for key in redis_client.scan_iter(match=f"{FEEDBACK_REDIS_PREFIX}*"):
            feedback_keys.append(key)

        total_feedback = len(feedback_keys)
        categories: dict[str, int] = {}
        ratings = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

        # Process up to 100 feedback entries
        for key in feedback_keys[:100]:
            try:
                data_str = await redis_client.get(key)
                if data_str:
                    data = json.loads(data_str)
                    cat = data.get("category", "unknown")
                    rating = data.get("rating", 0)
                    categories[cat] = categories.get(cat, 0) + 1
                    if rating in ratings:
                        ratings[rating] = ratings[rating] + 1
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.debug(f"Skipping malformed feedback entry: {e}")
                continue

        stats = {
            "total_feedback": total_feedback,
            "categories": categories,
            "ratings": ratings,
            "average_rating": (
                sum(k * v for k, v in ratings.items()) / sum(ratings.values())
                if sum(ratings.values()) > 0
                else 0
            ),
        }

        return stats

    except (
        RedisError,
        OSError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        ValueError,
        TypeError,
    ) as e:
        logger.error(f"Error getting feedback stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve feedback statistics") from e


# Service discovery endpoint (Versioned: /api/v1/gateway/services)
@gateway_v1_router.get("/services")
@track_request_metrics("api-gateway", "/api/v1/gateway/services")
async def list_services_v1(user: UserClaims = Depends(get_current_user)):
    """List available services (admin only) (API v1)"""
    # Require admin role
    if "admin" not in user.roles:
        logger.warning(
            "Unauthorized services list access",
            user_id=user.sub,
            tenant_id=user.tenant_id,
            roles=user.roles,
        )
        raise HTTPException(status_code=403, detail="Admin role required")
    services = {
        "agent-bus": {"url": AGENT_BUS_URL, "status": "configured"},
        "api-gateway": {"url": "http://localhost:8080", "status": "running"},
    }

    # Check service health
    for service_name, service_info in services.items():
        if service_name != "api-gateway":
            try:
                client = await get_proxy_client()
                response = await client.get(f"{service_info['url']}/health")
                service_info["health"] = "healthy" if response.status_code == 200 else "unhealthy"
            except (httpx.RequestError, httpx.TimeoutException, OSError) as e:
                logger.debug(f"Service health check failed for {service_name}: {e}")
                service_info["health"] = "unreachable"

    return services


# Include versioned gateway router
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
# Endpoints: /x402/pricing, /x402/validate, /x402/health
# Constitutional Hash: cdd01ef066bc6cf2
app.include_router(x402_governance_router)
logger.info("x402 governance routes configured: /x402/validate, /x402/pricing, /x402/health")


HOP_BY_HOP_HEADERS = frozenset(
    {
        "host",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "content-length",
    }
)

# SECURITY: Allowlist of headers forwarded to Agent Bus (H-3 fix).
# Using an allowlist instead of a blocklist prevents internal header injection.
_PROXY_FORWARD_HEADERS = frozenset(
    {
        "accept",
        "accept-encoding",
        "accept-language",
        "content-type",
        "user-agent",
        "x-request-id",
        "x-correlation-id",
        "x-idempotency-key",
    }
)

# Maximum proxy request body size (1 MB)
MAX_PROXY_BODY_SIZE = 1 * 1024 * 1024


class ProxyRequestPayload(BaseModel):
    """Validates proxy request JSON payloads have a well-formed structure."""

    model_config = {"extra": "allow"}


# Proxy to Agent Bus (catch-all route - must be last)
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_to_agent_bus(
    request: Request,
    path: str,
    user: UserClaims = Depends(get_current_user_optional),
):
    """Proxy requests to the Agent Bus service (auth required)"""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    incoming_tenant = request.headers.get("x-tenant-id") or request.headers.get("X-Tenant-ID")
    if incoming_tenant and incoming_tenant != user.tenant_id:
        raise HTTPException(
            status_code=403,
            detail=f"Tenant mismatch: token tenant '{user.tenant_id}' != header tenant '{incoming_tenant}'",
        )

    # SECURITY: Hardened path traversal protection
    # Use allowlist approach - only alphanumeric, hyphens, underscores, and forward slashes
    if not re.match(r"^[\w\-/]+$", path):
        raise HTTPException(status_code=400, detail="Invalid path characters")
    normalized_path = path.replace("\\", "/")
    if ".." in normalized_path or normalized_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")

    allowed_prefixes = ("api/v1/agents", "api/v1/messages", "api/v1/deliberations")
    if not any(normalized_path.startswith(prefix) for prefix in allowed_prefixes):
        raise HTTPException(status_code=403, detail="Proxy to this path not allowed")

    target_url = f"{AGENT_BUS_URL}/{normalized_path}"

    try:
        body_bytes = await request.body()

        # Validate payload size
        if len(body_bytes) > MAX_PROXY_BODY_SIZE:
            raise HTTPException(status_code=413, detail="Payload too large")

        # Validate JSON structure if content-type is JSON
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("application/json") and body_bytes:
            try:
                json_data = json.loads(body_bytes)
                if isinstance(json_data, dict):
                    ProxyRequestPayload(**json_data)
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=422, detail="Invalid JSON payload") from e
            except ValidationError as e:
                raise HTTPException(status_code=422, detail="Invalid JSON payload") from e

        # SECURITY: Use allowlist — only forward known-safe headers to Agent Bus.
        # This prevents clients from injecting internal headers (H-3 fix).
        safe_headers = {
            k: v for k, v in request.headers.items() if k.lower() in _PROXY_FORWARD_HEADERS
        }
        # Inject authenticated identity headers (gateway-controlled, not client-settable)
        safe_headers["X-Tenant-ID"] = user.tenant_id
        safe_headers["X-User-ID"] = user.sub

        # NOTE: autonomy tier enforcement is handled by AutonomyTierEnforcementMiddleware

        client = await get_proxy_client()
        response = await client.request(
            method=request.method,
            url=target_url,
            headers=safe_headers,
            content=body_bytes,
            params=dict(request.query_params),
        )

        return ORJSONResponse(
            status_code=response.status_code,
            content=(
                response.json()
                if response.headers.get("content-type", "").startswith("application/json")
                else response.text
            ),
        )

    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        raise HTTPException(status_code=502, detail="Service unavailable") from e
    except (
        ValueError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        LookupError,
    ) as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


async def save_feedback_to_redis(feedback_record: JSONDict) -> None:
    """Save feedback to Redis asynchronously with TTL."""
    try:
        feedback_id = feedback_record["feedback_id"]
        redis_key = f"{FEEDBACK_REDIS_PREFIX}{feedback_id}"

        redis_client = await get_feedback_redis()
        await redis_client.setex(redis_key, FEEDBACK_REDIS_TTL, json.dumps(feedback_record))

        logger.info("feedback_saved", feedback_id=feedback_id, storage="redis")
    except (RedisError, OSError, ValueError, TypeError, KeyError) as e:
        logger.error(
            "feedback_save_failed",
            feedback_id=feedback_record.get("feedback_id"),
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )


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
