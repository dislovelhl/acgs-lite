"""
ACGS-2 Enhanced Agent Bus - PQC Enforcement Models
Constitutional Hash: 608508a9bd224290

Pydantic models for PQC enforcement mode administration and metrics.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class EnforcementModeRequest(BaseModel):
    """Request model for changing the PQC enforcement mode."""

    mode: Literal["strict", "permissive"] = Field(..., description="Target enforcement mode")
    scope: str = Field(default="global", description="Enforcement scope (global or tenant ID)")


class EnforcementModeResponse(BaseModel):
    """Response model for enforcement mode operations."""

    mode: Literal["strict", "permissive"] = Field(..., description="Current enforcement mode")
    activated_at: datetime = Field(..., description="When the mode was activated")
    activated_by: str = Field(..., description="Identity of the operator who activated the mode")
    scope: str = Field(..., description="Enforcement scope (global or tenant ID)")
    propagation_deadline_seconds: int = Field(
        ..., description="Seconds until mode propagation deadline"
    )


class PQCRejectionError(BaseModel):
    """Error response model for PQC enforcement rejections."""

    error_code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    supported_algorithms: list[str] = Field(
        default_factory=list,
        description="List of supported PQC algorithm families",
    )
    docs_url: str | None = Field(default=None, description="URL to relevant documentation")


class PQCAdoptionWindow(BaseModel):
    """PQC adoption metrics for a single time window."""

    window: Literal["1h", "24h", "7d"] = Field(..., description="Time window for the metrics")
    pqc_verified_count: int = Field(
        ..., description="Number of PQC key verifications in this window"
    )
    classical_verified_count: int = Field(
        ..., description="Number of classical key verifications in this window"
    )
    pqc_adoption_rate: float = Field(..., description="PQC adoption rate as a fraction (0.0-1.0)")


class PQCAdoptionMetricsResponse(BaseModel):
    """Response model for PQC adoption metrics endpoint."""

    windows: list[PQCAdoptionWindow] = Field(..., description="Adoption metrics per time window")
    generated_at: datetime = Field(..., description="When these metrics were generated")


__all__ = [
    "EnforcementModeRequest",
    "EnforcementModeResponse",
    "PQCAdoptionMetricsResponse",
    "PQCAdoptionWindow",
    "PQCRejectionError",
]
