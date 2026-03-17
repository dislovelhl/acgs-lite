# Constitutional Hash: cdd01ef066bc6cf2
"""ACGS-2 PQC-Only Mode Enforcement Middleware

Constitutional Hash: cdd01ef066bc6cf2

Starlette BaseHTTPMiddleware that rejects requests referencing classical
algorithm identifiers (Ed25519, X25519) when PQC_ONLY_MODE is active.

Enforcement logic:
  1. Read PQC_ONLY_MODE from Redis key ``pqc:config:pqc_only_mode`` with a
     5-second TTL in-process cache (functools.lru_cache).
  2. If Redis is unavailable, fall back to ``os.environ["PQC_ONLY_MODE"]``
     (default "false").
  3. Fast path: if the request has no JSON body, or the parsed body contains
     no "algorithm" field, skip all checks entirely — zero overhead.
  4. If PQC_ONLY_MODE is active and the body's "algorithm" field is a
     classical identifier, return HTTP 422 with::

         {"error": "CLASSICAL_ALGORITHM_REJECTED", "algorithm": "<name>",
          "detail": "Classical algorithm rejected in PQC-only mode"}

Registration (before business-logic middleware)::

    from .pqc_only_mode import PQCOnlyModeMiddleware
    app.add_middleware(PQCOnlyModeMiddleware, redis_client=<redis.asyncio.Redis>)
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)

# Approved PQC algorithm identifiers (Phase 5: classical algorithms decommissioned)
# Any algorithm field value NOT in this set is rejected when PQC_ONLY_MODE is active.
_APPROVED_PQC_ALGORITHM_STRINGS: frozenset[str] = frozenset(
    {
        "ML-DSA-44",
        "ML-DSA-65",
        "ML-DSA-87",
        "ML-KEM-512",
        "ML-KEM-768",
        "ML-KEM-1024",
    }
)

# Redis key holding the PQC-only mode flag
_REDIS_KEY: str = "pqc:config:pqc_only_mode"

# In-process cache TTL in seconds
_CACHE_TTL: float = 5.0


class PQCOnlyModeMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces PQC-only mode by blocking classical algorithm requests.

    Args:
        app: The ASGI application to wrap.
        redis_client: An ``redis.asyncio.Redis`` instance used to read the
            PQC_ONLY_MODE flag. If not supplied, the middleware falls back to
            the ``PQC_ONLY_MODE`` environment variable immediately.
    """

    def __init__(self, app: ASGIApp, *, redis_client: Any | None = None) -> None:
        super().__init__(app)
        self._redis = redis_client
        # In-process TTL cache: (cached_value: bool, expiry: float)
        self._cached_mode: bool = False
        self._cache_expiry: float = 0.0

    async def _get_pqc_only_mode(self) -> bool:
        """Return the current PQC_ONLY_MODE flag value.

        Order of precedence:
        1. In-process TTL cache (5-second window).
        2. Redis key ``pqc:config:pqc_only_mode``.
        3. ``os.environ["PQC_ONLY_MODE"]`` (default "false").
        """
        now = time.monotonic()
        if now < self._cache_expiry:
            return self._cached_mode

        raw: str | None = None
        if self._redis is not None:
            try:
                raw = await self._redis.get(_REDIS_KEY)
            except Exception:
                logger.warning(
                    "pqc_only_mode_redis_unavailable",
                    fallback="os.environ",
                )

        if raw is None:
            raw = os.environ.get("PQC_ONLY_MODE", "false")

        mode = raw.strip().lower() == "true"
        self._cached_mode = mode
        self._cache_expiry = now + _CACHE_TTL
        return mode

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Inspect the request body for classical algorithm identifiers."""
        # Fast path: skip if PQC_ONLY_MODE is inactive
        pqc_only = await self._get_pqc_only_mode()
        if not pqc_only:
            return await call_next(request)

        # Fast path: skip non-JSON or requests that provably have no body
        content_type = request.headers.get("content-type", "")
        if not content_type.startswith("application/json"):
            return await call_next(request)

        # Attempt to read and parse the body
        try:
            body_bytes = await request.body()
        except Exception:
            return await call_next(request)

        if not body_bytes:
            return await call_next(request)

        try:
            payload = json.loads(body_bytes)
        except (json.JSONDecodeError, ValueError):
            # Malformed JSON passes through; let FastAPI validation handle it
            return await call_next(request)

        if not isinstance(payload, dict):
            return await call_next(request)

        # Fast path: if no "algorithm" field, skip entirely
        algorithm = payload.get("algorithm")
        if algorithm is None:
            return await call_next(request)

        # Reject any algorithm not in the approved PQC set
        if algorithm not in _APPROVED_PQC_ALGORITHM_STRINGS:
            logger.info(
                "classical_algorithm_rejected",
                algorithm=algorithm,
                path=request.url.path,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            return JSONResponse(
                status_code=400,
                content={
                    "error": "CLASSICAL_ALGORITHM_REJECTED",
                    "algorithm": algorithm,
                    "detail": "Classical algorithm rejected in PQC-only mode",
                },
            )

        return await call_next(request)
