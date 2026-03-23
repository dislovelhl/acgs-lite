"""Backward-compatible audit logger enums.

Some legacy routes still import ``src.core.shared.audit.logger`` for audit
event/severity enums. The canonical audit implementation moved to
``src.core.shared.acgs_logging.audit_logger``; keep these enums available so
older import sites continue to work during migration.
"""

from enum import StrEnum

from src.core.shared.acgs_logging.audit_logger import AuditSeverity


class AuditEventType(StrEnum):
    """Legacy audit event types still referenced by service routes."""

    APPROVAL = "approval"
    VALIDATION = "validation"
    DECISION = "decision"
    SYSTEM = "system"


__all__ = ["AuditEventType", "AuditSeverity"]
