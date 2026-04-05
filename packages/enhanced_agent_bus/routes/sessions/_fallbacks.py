"""
ACGS-2 Session Governance - Fallback Imports
Constitutional Hash: 608508a9bd224290

Provides fallback implementations for when actual modules are unavailable.
Used for standalone testing and development.
"""

from __future__ import annotations

import os
from datetime import datetime
from enum import Enum

from fastapi import Header, HTTPException, status
from pydantic import BaseModel

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

# Try to import the real implementations
try:
    from ...session_context import SessionContext, SessionContextManager
    from ...session_governance_sdk import RiskLevel
    from ...session_models import SessionGovernanceConfig

    USING_FALLBACKS = False
except (ImportError, ValueError):
    try:
        from session_context import SessionContext, SessionContextManager  # type: ignore[no-redef]
        from session_governance_sdk import RiskLevel  # type: ignore[no-redef]
        from session_models import SessionGovernanceConfig  # type: ignore[no-redef]

        USING_FALLBACKS = False
    except ImportError:
        USING_FALLBACKS = True

        # Define minimal models for standalone testing
        class RiskLevel(str, Enum):  # type: ignore[no-redef]
            LOW = "low"
            MEDIUM = "medium"
            HIGH = "high"
            CRITICAL = "critical"

        class SessionGovernanceConfig(BaseModel):  # type: ignore[no-redef]
            session_id: str
            tenant_id: str
            user_id: str | None = None
            risk_level: RiskLevel = RiskLevel.MEDIUM
            policy_id: str | None = None
            policy_overrides: JSONDict = {}
            enabled_policies: list[str] = []
            disabled_policies: list[str] = []
            require_human_approval: bool = False
            max_automation_level: str | None = None

        class SessionContext(BaseModel):  # type: ignore[no-redef]
            session_id: str
            governance_config: SessionGovernanceConfig
            metadata: JSONDict = {}
            created_at: datetime
            updated_at: datetime
            expires_at: datetime | None = None
            constitutional_hash: str = CONSTITUTIONAL_HASH

        class SessionContextManager:  # type: ignore[no-redef]
            """Mock manager for testing."""

            async def connect(self) -> bool:
                return True

            async def create(self, *args, **kwargs) -> SessionContext:
                raise NotImplementedError("Mock manager") from None

            async def get(self, session_id: str) -> SessionContext | None:
                return None

            async def update(self, *args, **kwargs) -> SessionContext | None:
                return None

            async def delete(self, session_id: str) -> bool:
                return False

            async def exists(self, session_id: str) -> bool:
                return False

            def get_metrics(self) -> JSONDict:
                return {}


def _is_explicit_dev_or_test_mode() -> bool:
    """Allow fallback tenant extraction only in explicit development/test runtimes."""
    runtime_values: tuple[str | None, ...] = (
        os.getenv("AGENT_RUNTIME_ENVIRONMENT"),
        os.getenv("ACGS_ENV"),
        os.getenv("APP_ENV"),
        os.getenv("ENVIRONMENT"),
    )
    allowed_modes = {"dev", "development", "local", "test", "testing", "ci", "qa"}
    production_like_modes = {"production", "prod", "staging", "stage", "preprod"}

    # Block if ANY environment variable indicates a production-like runtime,
    # even when PYTEST_CURRENT_TEST is set (e.g. integration smoke-tests
    # against staging-configured services).
    for raw_value in runtime_values:
        if raw_value and raw_value.strip().lower() in production_like_modes:
            return False

    for raw_value in runtime_values:
        if raw_value and raw_value.strip().lower() in allowed_modes:
            return True

    # pytest sets this for active tests; allow fallback only when no
    # production-like environment was detected (checked above).
    return bool(os.getenv("PYTEST_CURRENT_TEST"))


# Try to import tenant context helper
try:
    from enhanced_agent_bus._compat.security.tenant_context import get_tenant_id

    USING_FALLBACK_TENANT = False
except ImportError:
    USING_FALLBACK_TENANT = True

    async def get_tenant_id(  # type: ignore[misc]
        x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
    ) -> str:
        """Fallback tenant ID getter for explicit development/test runtimes only."""
        if not _is_explicit_dev_or_test_mode():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Fallback tenant extraction is disabled outside development/test mode",
            ) from None

        if not x_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Tenant-ID header is required",
            ) from None
        return x_tenant_id


__all__ = [
    "USING_FALLBACKS",
    "USING_FALLBACK_TENANT",
    "RiskLevel",
    "SessionContext",
    "SessionContextManager",
    "SessionGovernanceConfig",
    "get_tenant_id",
]
