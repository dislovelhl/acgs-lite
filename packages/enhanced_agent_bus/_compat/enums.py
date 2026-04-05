"""Shim for src.core.shared.enums."""

from __future__ import annotations

try:
    from src.core.shared.enums import *  # noqa: F403
    from src.core.shared.enums import DecisionType, RiskLevel  # explicit re-exports
except ImportError:
    from enum import Enum, StrEnum

    class RiskLevel(StrEnum):
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"
        CRITICAL = "critical"

    class DecisionType(Enum):
        POLICY_CREATION = "policy_creation"
        POLICY_EXECUTION = "policy_execution"
        CONSTITUTIONAL_REVIEW = "constitutional_review"
        DISPUTE_RESOLUTION = "dispute_resolution"
        OVERRIDE_REQUEST = "override_request"
