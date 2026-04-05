"""Shim for src.core.shared.audit.logger."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

try:
    from src.core.shared.audit.logger import *  # noqa: F403
except ImportError:

    class AuditEventType(StrEnum):
        CREATE = "create"
        READ = "read"
        UPDATE = "update"
        DELETE = "delete"
        EXECUTE = "execute"
        LOGIN = "login"
        LOGOUT = "logout"
        POLICY_CHECK = "policy_check"
        CONSTITUTIONAL_REVIEW = "constitutional_review"

    class AuditSeverity(StrEnum):
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"
        CRITICAL = "critical"

    class AuditLogger:
        """No-op audit logger stub."""

        def __init__(self, **kwargs: Any) -> None:
            pass

        async def log(
            self,
            event_type: str = "",
            severity: str = "low",
            message: str = "",
            **kwargs: Any,
        ) -> None:
            pass

        async def query(self, **filters: Any) -> list[dict[str, Any]]:
            return []

    def get_audit_logger(**kwargs: Any) -> AuditLogger:
        return AuditLogger(**kwargs)
