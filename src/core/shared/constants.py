"""
ACGS-2 Shared Constants
Constitutional Hash: cdd01ef066bc6cf2

Central location for all system-wide constants used across ACGS-2 services.
This ensures consistency and single source of truth for critical values.

For algorithm-agile constitutional hash management, see constitutional_hash.py
"""

import enum
from enum import StrEnum


class RiskTier(StrEnum):
    """Risk tier classification for governance decisions.

    Constitutional Hash: cdd01ef066bc6cf2

    LOW: score < 0.3 — fast lane, no human involvement
    MEDIUM: score 0.3-0.8 — auto-remediate immediately + 15-min human override window
    HIGH: score >= 0.8 — full HITL gate (existing deliberation behavior)
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Risk tier thresholds
RISK_TIER_LOW_MAX = 0.3  # scores below this → LOW
RISK_TIER_HIGH_MIN = 0.8  # scores at or above this → HIGH
# scores in [RISK_TIER_LOW_MAX, RISK_TIER_HIGH_MIN) → MEDIUM

# HOTL override window duration (seconds)
HOTL_OVERRIDE_WINDOW_SECONDS = 900  # 15 minutes


def classify_risk_tier(impact_score: float) -> RiskTier:
    """Classify an impact score into a risk tier."""
    if impact_score < RISK_TIER_LOW_MAX:
        return RiskTier.LOW
    if impact_score >= RISK_TIER_HIGH_MIN:
        return RiskTier.HIGH
    return RiskTier.MEDIUM


class MACIRole(str, enum.Enum):
    """Multi-Agent Constitutional Intelligence roles (separation of powers).

    Values are UPPERCASE to match the JWT payload contract used by agent_runtime.
    EAB code that previously used lowercase values should compare via enum members
    (e.g., ``MACIRole.EXECUTIVE``) rather than raw strings.
    """

    EXECUTIVE = "EXECUTIVE"
    LEGISLATIVE = "LEGISLATIVE"
    JUDICIAL = "JUDICIAL"
    MONITOR = "MONITOR"
    AUDITOR = "AUDITOR"
    CONTROLLER = "CONTROLLER"
    IMPLEMENTER = "IMPLEMENTER"

    @classmethod
    def _missing_(cls, value: object) -> "MACIRole | None":
        """Accept historical lowercase wire values during enum construction."""
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                normalized = normalized.upper()
                for member in cls:
                    if member.value == normalized or member.name == normalized:
                        return member
        return None

    @classmethod
    def parse(cls, value: "MACIRole | str") -> "MACIRole":
        """Parse a role from either enum members or legacy/current wire strings."""
        if isinstance(value, cls):
            return value
        return cls(value)


# Constitutional AI Governance (legacy bare hash for backwards compatibility)
CONSTITUTIONAL_HASH = "cdd01ef066bc6cf2"

# Versioned Constitutional Hash (canonical format)
# Use this for new code: sha256:v1:cdd01ef066bc6cf2
CONSTITUTIONAL_HASH_VERSIONED = "sha256:v1:cdd01ef066bc6cf2"

# Default Infrastructure Configuration
DEFAULT_REDIS_URL = "redis://localhost:6379"
DEFAULT_REDIS_DB = 0

# Performance Targets (non-negotiable)
P99_LATENCY_TARGET_MS = 5.0
MIN_THROUGHPUT_RPS = 100
MIN_CACHE_HIT_RATE = 0.85

# Message Bus Defaults
DEFAULT_MESSAGE_TTL_SECONDS = 3600
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT_MS = 5000

# Constitutional Compliance
COMPLIANCE_TARGET = 1.0  # 100%


def get_constitutional_hash() -> str:
    """Return the active constitutional hash.

    Use as ``default_factory`` in Pydantic models and dataclasses instead of
    hardcoding the literal string.
    """
    return CONSTITUTIONAL_HASH


__all__ = [
    "COMPLIANCE_TARGET",
    "CONSTITUTIONAL_HASH",
    "CONSTITUTIONAL_HASH_VERSIONED",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_MESSAGE_TTL_SECONDS",
    "DEFAULT_REDIS_DB",
    "DEFAULT_REDIS_URL",
    "DEFAULT_TIMEOUT_MS",
    "HOTL_OVERRIDE_WINDOW_SECONDS",
    "MIN_CACHE_HIT_RATE",
    "MIN_THROUGHPUT_RPS",
    "P99_LATENCY_TARGET_MS",
    "RISK_TIER_HIGH_MIN",
    "RISK_TIER_LOW_MAX",
    "MACIRole",
    "RiskTier",
    "classify_risk_tier",
    "get_constitutional_hash",
]
