"""ACGS-2 Public API v1 — governance validation endpoints.
Constitutional Hash: cdd01ef066bc6cf2
"""

import time
from collections.abc import Generator
from contextlib import contextmanager

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.constitutional_hash import validate_constitutional_hash
from src.core.shared.types import JSONDict

from ..api_key_auth import require_api_key
from ..rate_limiting import limiter
from ..runtime_guards import require_sandbox_endpoint
from ..validation_store import ValidationEntry, get_validation_store

try:
    from opentelemetry import trace

    _tracer = trace.get_tracer(__name__)
except ImportError:  # pragma: no cover
    _tracer = None  # type: ignore[assignment]


@contextmanager
def _otel_span(name: str, attributes: dict[str, str] | None = None) -> Generator[None, None, None]:
    """Start an OpenTelemetry span if the SDK is available, otherwise no-op."""
    if _tracer is not None:
        with _tracer.start_as_current_span(name, attributes=attributes or {}):
            yield
    else:
        yield


router = APIRouter(prefix="/v1", tags=["public-v1"])
PUBLIC_API_VERSION = "1.0.0"
HASH_VALIDATION_FAILURE = "Constitutional hash validation failed"
VALIDATION_OK_SCORE = 1.0
VALIDATION_FAILED_SCORE = 0.0


class ValidateRequest(BaseModel):
    """Request body for governance validation."""

    agent_id: str = Field(..., description="Unique agent identifier")
    action: str = Field(..., description="Action being validated")
    context: JSONDict = Field(default_factory=dict, description="Action context")
    policies: list[str] = Field(default_factory=list, description="Policy IDs to check")


class ValidateResponse(BaseModel):
    """Response from governance validation."""

    compliant: bool
    constitutional_hash: str
    score: float = 1.0
    violations: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    request_id: str = ""


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    constitutional_hash: str


def _build_request_id(request: ValidateRequest) -> str:
    """Build stable request ID for validation records."""
    return f"{request.agent_id}:{request.action}"


def _validation_score_and_violations(compliant: bool) -> tuple[float, list[str]]:
    """Map constitutional compliance to API score and violations."""
    if compliant:
        return VALIDATION_OK_SCORE, []
    return VALIDATION_FAILED_SCORE, [HASH_VALIDATION_FAILURE]


def _record_validation(
    request: ValidateRequest,
    compliant: bool,
    score: float,
    elapsed_ms: float,
    request_id: str,
) -> None:
    """Record validation result for stats aggregation."""
    get_validation_store().record(
        ValidationEntry(
            agent_id=request.agent_id,
            action=request.action,
            compliant=compliant,
            score=score,
            latency_ms=elapsed_ms,
            request_id=request_id,
        )
    )


@router.get("/health", response_model=HealthResponse)
async def v1_health() -> HealthResponse:
    """Public health check — no authentication required."""
    return HealthResponse(
        status="healthy",
        version=PUBLIC_API_VERSION,
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


@router.post("/validate", response_model=ValidateResponse)
@limiter.limit("60/minute")
async def v1_validate(
    request: Request,
    body: ValidateRequest,
    _api_key: str = Depends(require_api_key),
) -> ValidateResponse:
    """Sandbox-only validation until authoritative governance wiring lands."""
    require_sandbox_endpoint(
        "Public validation endpoint",
        "it currently performs only a local constitutional-hash self-check and in-memory "
        "stats recording",
    )
    with _otel_span(
        "v1.validate",
        attributes={"agent_id": body.agent_id, "action": body.action},
    ):
        start = time.perf_counter()
        compliant = validate_constitutional_hash(CONSTITUTIONAL_HASH).valid
        score, violations = _validation_score_and_violations(compliant)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
        request_id = _build_request_id(body)
        _record_validation(body, compliant, score, elapsed_ms, request_id)

        return ValidateResponse(
            compliant=compliant,
            constitutional_hash=CONSTITUTIONAL_HASH,
            score=score,
            violations=violations,
            latency_ms=elapsed_ms,
            request_id=request_id,
        )
