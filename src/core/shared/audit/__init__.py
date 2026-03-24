"""Backward-compatible audit namespace.

Canonical audit logging now lives under ``src.core.shared.acgs_logging``.
This package preserves legacy imports that still resolve
``src.core.shared.audit.logger``.
"""

from .logger import AuditEventType, AuditSeverity

__all__ = ["AuditEventType", "AuditSeverity"]
