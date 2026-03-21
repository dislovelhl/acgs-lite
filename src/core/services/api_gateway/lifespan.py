"""Constitutional Hash: cdd01ef066bc6cf2
ACGS-2 API Gateway — Lifespan management

Extracted from main.py: startup/shutdown lifecycle for the FastAPI application.
"""

import os
from collections.abc import AsyncGenerator

from fastapi import FastAPI

try:
    from src.core.self_evolution.research.operator_control import (
        DEFAULT_RESEARCH_OPERATOR_CONTROL_KEY_PREFIX,
        create_research_operator_control_plane,
    )
except ImportError:
    DEFAULT_RESEARCH_OPERATOR_CONTROL_KEY_PREFIX = "acgs:research:operator_control"

    async def create_research_operator_control_plane(**kwargs: object) -> None:
        """Stub when self_evolution module is not installed."""

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.redis_config import get_redis_url
from src.core.shared.structured_logging import get_logger

from .middleware.autonomy_tier import HttpHitlSubmissionClient
from .routes.feedback import _close_feedback_redis
from .routes.proxy import close_proxy_client

logger = get_logger(__name__)

environment = os.getenv("ENVIRONMENT", "production").strip().lower()
is_development = environment in {"development", "dev", "test", "testing", "ci"}


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
