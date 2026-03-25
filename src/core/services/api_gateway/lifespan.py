"""Constitutional Hash: 608508a9bd224290
ACGS-2 API Gateway — Lifespan management

Extracted from main.py: startup/shutdown lifecycle for the FastAPI application.
"""

import os
from contextlib import asynccontextmanager
from inspect import isawaitable

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

from src.core.shared.config import settings
from src.core.shared.config.runtime_environment import resolve_runtime_environment
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.redis_config import get_redis_url
from src.core.shared.structured_logging import get_logger

from .middleware.autonomy_tier import HttpHitlSubmissionClient
from .routes.feedback import _close_feedback_redis
from .routes.proxy import close_proxy_client

logger = get_logger(__name__)


def _runtime_environment() -> str:
    """Resolve the current runtime environment at call time.

    Tests in this repo mutate ENVIRONMENT repeatedly, so import-time snapshots
    can become stale and incorrectly force production startup checks.
    """
    return resolve_runtime_environment(getattr(settings, "env", None))


def _is_development_environment() -> bool:
    return _runtime_environment() in {"development", "dev", "test", "testing", "ci"}


def _verify_constitutional_hash_at_startup() -> None:
    """M-5 fix: Verify CONSTITUTIONAL_HASH matches the env-provided hash at startup.

    In production, operators must set CONSTITUTIONAL_HASH env var explicitly.
    This prevents a tampered deployment from silently bypassing governance by
    using a stale/wrong hash embedded in the codebase.

    In development mode, a mismatch is logged as a warning but does not block.
    """
    env_hash = os.getenv("CONSTITUTIONAL_HASH")
    if not env_hash:
        if not _is_development_environment():
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
        if not _is_development_environment():
            logger.error(msg)
            raise RuntimeError(msg)
        logger.warning(msg + " (dev mode — continuing)")
    else:
        logger.info(
            "Constitutional hash verified at startup",
            hash=CONSTITUTIONAL_HASH,
        )


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
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
    operator_control_plane = create_research_operator_control_plane(
        backend=operator_control_backend,
        redis_url=operator_control_redis_url if operator_control_backend == "redis" else None,
        key_prefix=operator_control_key_prefix,
    )
    if isawaitable(operator_control_plane):
        operator_control_plane = await operator_control_plane
    app_instance.state.research_operator_control_plane = operator_control_plane
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
    try:
        yield
    finally:
        # Shutdown: close all shared clients gracefully
        research_operator_control_plane = getattr(
            app_instance.state,
            "research_operator_control_plane",
            None,
        )
        if research_operator_control_plane is not None:
            close_fn = getattr(research_operator_control_plane, "aclose", None)
            if callable(close_fn):
                close_result = close_fn()
                if isawaitable(close_result):
                    await close_result
        await close_proxy_client()
        await _close_feedback_redis()
        logger.info("API Gateway shut down cleanly")
