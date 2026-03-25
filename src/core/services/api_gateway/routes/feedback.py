"""Constitutional Hash: 608508a9bd224290
ACGS-2 API Gateway — Feedback endpoints

Extracted from main.py: feedback submission, stats, versioning docs, and service discovery.
All endpoints are mounted on the gateway_v1_router (versioned: /api/v1/gateway/*).
"""

import asyncio
import json
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import redis.asyncio
from fastapi import BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from redis.exceptions import RedisError

from src.core.shared.api_versioning import (
    create_version_info_endpoint,
    create_version_metrics_endpoint,
    create_versioned_router,
    get_versioning_documentation,
)
from src.core.shared.config import settings
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.metrics import track_request_metrics
from src.core.shared.redis_config import get_redis_url
from src.core.shared.security.auth import (
    UserClaims,
    get_current_user,
    get_current_user_optional,
)
from src.core.shared.security.rate_limiter import (
    RateLimitScope,
    rate_limiter,
)
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

from ..metrics import record_feedback_rejection, record_feedback_submission

logger = get_logger(__name__)

# Feedback stats cache
_feedback_stats_cache: dict[str, Any] = {"data": None, "timestamp": 0.0}
_FEEDBACK_STATS_TTL = 60.0  # 1 minute cache TTL
_FEEDBACK_ANONYMOUS_RATE_LIMIT = 20
_FEEDBACK_AUTHENTICATED_RATE_LIMIT = 60
_FEEDBACK_RATE_WINDOW_SECONDS = 60
_FEEDBACK_MAX_METADATA_BYTES = 8 * 1024
_FEEDBACK_MAX_REQUEST_BYTES = 16 * 1024

# Feedback storage configuration using Redis for persistence
# Constitutional Hash: 608508a9bd224290
FEEDBACK_REDIS_PREFIX = "acgs:feedback:"
FEEDBACK_REDIS_TTL = 60 * 60 * 24 * 90  # 90 days

# Redis URL from centralized config (not hardcoded)
_feedback_redis_url = get_redis_url(db=0)
_feedback_redis_client: redis.asyncio.Redis | None = None
_feedback_redis_lock = asyncio.Lock()

# Service URLs from centralized config
AGENT_BUS_URL = settings.services.agent_bus_url
ENVIRONMENT = settings.env


def get_cached_feedback_stats() -> dict[str, Any] | None:
    """Get cached feedback stats if valid."""
    now = time.time()
    if (
        _feedback_stats_cache["data"]
        and (now - _feedback_stats_cache["timestamp"]) < _FEEDBACK_STATS_TTL
    ):
        return _feedback_stats_cache["data"]  # type: ignore[no-any-return]
    return None


def update_feedback_stats_cache(stats: dict[str, Any]) -> None:
    """Update the feedback stats cache."""
    _feedback_stats_cache["data"] = stats
    _feedback_stats_cache["timestamp"] = time.time()


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


# ============================================================================
# Versioned Gateway Router (API v1)
# Constitutional Hash: 608508a9bd224290
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
async def get_versioning_docs() -> dict[str, Any]:
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
@track_request_metrics("api-gateway", "/api/v1/gateway/feedback")  # type: ignore[untyped-decorator]
async def submit_feedback_v1(
    feedback: FeedbackRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user: UserClaims | None = Depends(_enforce_feedback_submission_policy),
) -> FeedbackResponse:
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
        feedback_record: dict[str, Any] = {
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
@track_request_metrics("api-gateway", "/api/v1/gateway/feedback/stats")  # type: ignore[untyped-decorator]
async def get_feedback_stats_v1(
    user: UserClaims = Depends(get_current_user_optional),
) -> dict[str, Any]:
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
@track_request_metrics("api-gateway", "/api/v1/gateway/services")  # type: ignore[untyped-decorator]
async def list_services_v1(user: UserClaims = Depends(get_current_user)) -> dict[str, Any]:
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
                from .proxy import get_proxy_client

                client = await get_proxy_client()
                response = await client.get(f"{service_info['url']}/health")
                service_info["health"] = "healthy" if response.status_code == 200 else "unhealthy"
            except (httpx.RequestError, httpx.TimeoutException, OSError) as e:
                logger.debug(f"Service health check failed for {service_name}: {e}")
                service_info["health"] = "unreachable"

    return services


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
