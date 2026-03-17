"""API gateway shim for compliance routes.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

from src.core.services.compliance.router import router as compliance_router

__all__ = ["compliance_router"]
