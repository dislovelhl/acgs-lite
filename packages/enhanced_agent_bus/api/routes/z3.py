"""
ACGS-2 Z3 Formal Verification API Routes
Constitutional Hash: 608508a9bd224290

Exposes Z3 SMT verification metrics and recent verification results for the
web-console Z3Dashboard.  A module-level verifier singleton accumulates metrics
across the lifetime of the process; individual verification runs are stored in
a rolling in-memory buffer (newest-first, capped at 50 entries).

Endpoints
---------
GET /api/v1/z3/metrics
    Returns aggregated Z3MetricsCollector data plus a slice of recent results.

POST /api/v1/z3/verify
    Verify a single policy specification expressed as a JSON payload.  Returns
    a VerificationResult.  Requires a valid tenant API key.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.responses import ORJSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["Z3 Verification"])

# ---------------------------------------------------------------------------
# Route-level auth dependency
#
# We use a local Security declaration instead of importing require_api_key
# directly from api_key_auth to avoid triggering api/__init__.py at module
# load time (which transitively imports signup.py → email-validator).  The
# actual key-validation logic is still delegated to api_key_auth._is_known_api_key
# so there is no duplication of business logic.  We load api_key_auth via
# importlib.util at first call so even the deferred import does not go through
# the package __init__ chain.
# ---------------------------------------------------------------------------

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
_auth_module: Any = None


def _load_auth_module() -> Any:
    """Load api_key_auth.py directly by file path, bypassing package __init__."""
    global _auth_module
    if _auth_module is None:
        import importlib.util as _ilu
        import pathlib as _pl

        _path = _pl.Path(__file__).parent.parent / "api_key_auth.py"
        _spec = _ilu.spec_from_file_location("_z3_api_key_auth", _path)
        assert _spec and _spec.loader
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
        _auth_module = _mod
    return _auth_module


async def _verify_api_key(api_key: str | None = Security(_API_KEY_HEADER)) -> str:
    """Validate the X-API-Key header using the shared api_key_auth module."""
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    auth = _load_auth_module()
    if not auth._is_known_api_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


# ---------------------------------------------------------------------------
# In-process state
# ---------------------------------------------------------------------------

_RECENT_RESULTS: deque[JSONDict] = deque(maxlen=50)
_METRICS: JSONDict = {
    "total_verifications": 0,
    "successful_verifications": 0,
    "failed_verifications": 0,
    "timeout_count": 0,
    "verification_times_ms": [],
    "policy_type_counts": {},
    "cache_hits": 0,
    "cache_misses": 0,
}
_VERIFIER: Any | None = None


def _reset_state() -> None:
    """Reset module-level mutable state. Used by test fixtures."""
    global _VERIFIER
    _RECENT_RESULTS.clear()
    _METRICS.update(
        total_verifications=0,
        successful_verifications=0,
        failed_verifications=0,
        timeout_count=0,
        cache_hits=0,
        cache_misses=0,
    )
    _METRICS["verification_times_ms"] = []
    _METRICS["policy_type_counts"] = {}
    _VERIFIER = None


def _normalize_solver_result(raw_solver_result: object) -> str:
    """Map backend-specific statuses to API contract values."""
    value = str(raw_solver_result).strip().lower()
    if value in {"sat", "valid"}:
        return "sat"
    if value in {"unsat", "invalid"}:
        return "unsat"
    return "unknown"


def _get_verifier() -> Any | None:
    """Lazily instantiate a Z3PolicyVerifier, returning None when Z3 is absent."""
    global _VERIFIER
    if _VERIFIER is not None:
        return _VERIFIER

    try:
        import importlib

        Z3PolicyVerifier = importlib.import_module(
            "src.core.breakthrough.verification.z3_smt_verifier.verifier"
        ).Z3PolicyVerifier

        _VERIFIER = Z3PolicyVerifier(use_timeout_handler=True)
        logger.info("Z3PolicyVerifier singleton initialised")
    except Exception as exc:
        logger.debug("Z3PolicyVerifier unavailable (%s) - metrics will be synthetic", exc)

    return _VERIFIER


def _computed_metrics() -> JSONDict:
    """Derive aggregated metrics from _METRICS, with averages and hit-rate."""
    m = dict(_METRICS)
    times: list[float] = m.get("verification_times_ms", []) or []
    m["average_verification_time_ms"] = sum(times) / len(times) if times else 0.0

    total_cache = m.get("cache_hits", 0) + m.get("cache_misses", 0)
    m["cache_hit_rate"] = (m.get("cache_hits", 0) / total_cache) if total_cache else 0.0

    # Strip the raw times list - too noisy for the dashboard payload
    m.pop("verification_times_ms", None)

    # Ensure every policy-type bucket exists for the UI
    for ptype in (
        "access_control",
        "resource_constraint",
        "temporal_governance",
        "constitutional",
        "general",
    ):
        m["policy_type_counts"].setdefault(ptype, {"total": 0, "success": 0, "failed": 0})

    return m


def _record_result(
    result_dict: JSONDict, policy_type: str, is_success: bool, elapsed_ms: float
) -> None:
    """Update module-level metrics and append to the rolling result buffer."""
    global _METRICS

    _METRICS["total_verifications"] += 1
    if is_success:
        _METRICS["successful_verifications"] += 1
    else:
        _METRICS["failed_verifications"] += 1

    times: list[float] = _METRICS["verification_times_ms"]
    times.append(elapsed_ms)
    if len(times) > 1000:
        _METRICS["verification_times_ms"] = times[-1000:]

    counts = _METRICS["policy_type_counts"]
    if policy_type not in counts:
        counts[policy_type] = {"total": 0, "success": 0, "failed": 0}
    counts[policy_type]["total"] += 1
    if is_success:
        counts[policy_type]["success"] += 1
    else:
        counts[policy_type]["failed"] += 1

    _RECENT_RESULTS.appendleft(result_dict)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class PolicyVerifyRequest(BaseModel):
    """Minimal policy verification request."""

    policy_id: str = Field(
        ..., min_length=1, max_length=128, description="Unique policy identifier"
    )
    policy_type: str = Field(
        default="general",
        description="One of: access_control, resource_constraint, temporal_governance, constitutional, general",
    )
    description: str = Field(default="", max_length=512, description="Human-readable description")
    rules: list[str] = Field(default_factory=list, description="Policy rule strings")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/api/v1/z3/metrics",
    summary="Z3 Verification Metrics",
    description="Aggregated Z3 SMT verification metrics plus a recent verification feed.",
    response_class=ORJSONResponse,
)
async def get_z3_metrics() -> ORJSONResponse:
    """Return Z3 verification metrics aggregated from in-process state.

    This endpoint is intentionally unauthenticated so the web-console
    can poll it without requiring a session token on the monitoring path.
    Authentication is enforced by the Next.js proxy layer.
    """
    # Initialise the verifier eagerly so it's ready for subsequent /verify calls
    # Use get_running_loop() (Python 3.10+) instead of deprecated get_event_loop()
    try:
        loop = asyncio.get_running_loop()
        _init_task = asyncio.ensure_future(loop.run_in_executor(None, _get_verifier))
        _init_task.add_done_callback(
            lambda t: (
                logger.warning("Z3 verifier init failed", exc_info=t.exception())
                if not t.cancelled() and t.exception()
                else None
            )
        )
    except RuntimeError:
        # No running loop - skip eager initialization
        pass

    payload: JSONDict = {
        "constitutional_hash": CONSTITUTIONAL_HASH,
        "metrics": _computed_metrics(),
        "recent_verifications": list(_RECENT_RESULTS),
    }
    return ORJSONResponse(content=payload)


@router.post(
    "/api/v1/z3/verify",
    summary="Verify a Policy",
    description="Run Z3 SMT verification on a policy specification.",
    response_class=ORJSONResponse,
)
async def verify_policy(
    request: PolicyVerifyRequest,
    _api_key: str = Depends(_verify_api_key),
) -> ORJSONResponse:
    """Verify a single policy specification using the Z3 backend.

    When Z3 is unavailable the endpoint returns a synthetic result so the
    dashboard still functions in environments without the z3 Python package.
    """
    verifier = _get_verifier()
    t0 = time.perf_counter()

    if verifier is None:
        # Synthetic path - Z3 not installed
        elapsed = (time.perf_counter() - t0) * 1000
        result_dict: JSONDict = {
            "policy_id": request.policy_id,
            "is_satisfiable": True,
            "is_valid": True,
            "policy_type": request.policy_type,
            "counterexample": None,
            "verification_time_ms": round(elapsed, 2),
            "solver_result": "sat",
            "error_message": "Synthetic verification result",
            "timestamp": time.time(),
            "metrics": {},
        }
        _record_result(result_dict, request.policy_type, is_success=True, elapsed_ms=elapsed)
        return ORJSONResponse(content=result_dict)

    try:
        import importlib

        _models = importlib.import_module(
            "src.core.breakthrough.verification.z3_smt_verifier.models"
        )
        PolicySpecification = _models.PolicySpecification
        PolicyType = _models.PolicyType

        ptype_map = {
            "access_control": PolicyType.ACCESS_CONTROL,
            "resource_constraint": PolicyType.RESOURCE_CONSTRAINT,
            "temporal_governance": PolicyType.TEMPORAL_GOVERNANCE,
            "constitutional": PolicyType.CONSTITUTIONAL,
            "general": PolicyType.GENERAL,
        }
        policy_type_enum = ptype_map.get(request.policy_type, PolicyType.GENERAL)

        spec = PolicySpecification(
            policy_id=request.policy_id,
            name=request.policy_id,
            description=request.description,
            policy_type=policy_type_enum,
            rules=request.rules,
        )

        result = await verifier.verify_policy(spec)

        elapsed = (time.perf_counter() - t0) * 1000
        result_dict = result.to_dict()
        result_dict["solver_result"] = _normalize_solver_result(
            result_dict.get("solver_result", "unknown")
        )
        result_dict["timestamp"] = time.time()

        _record_result(
            result_dict, request.policy_type, is_success=result.is_valid, elapsed_ms=elapsed
        )
        return ORJSONResponse(content=result_dict)

    except Exception as exc:
        logger.exception(f"Z3 verification failed for policy {request.policy_id}: {exc}")
        elapsed = (time.perf_counter() - t0) * 1000
        err_dict: JSONDict = {
            "policy_id": request.policy_id,
            "is_satisfiable": False,
            "is_valid": False,
            "policy_type": request.policy_type,
            "counterexample": None,
            "verification_time_ms": round(elapsed, 2),
            "solver_result": "unknown",
            "error_message": "Verification failed",
            "timestamp": time.time(),
            "metrics": {},
        }
        _record_result(err_dict, request.policy_type, is_success=False, elapsed_ms=elapsed)
        raise HTTPException(status_code=500, detail="Verification failed") from exc
