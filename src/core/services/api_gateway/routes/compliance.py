"""API gateway shim for compliance routes.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

from fastapi import APIRouter

try:
    from src.core.services.compliance.router import router as compliance_router
except ImportError:
    compliance_router = APIRouter(prefix="/compliance", tags=["compliance"])

__all__ = ["compliance_router"]
