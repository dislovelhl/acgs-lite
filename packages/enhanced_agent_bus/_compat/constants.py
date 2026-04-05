"""Shim for src.core.shared.constants."""

from __future__ import annotations

try:
    from src.core.shared.constants import *  # noqa: F403
    from src.core.shared.constants import (  # explicit re-exports
        COMPLIANCE_TARGET,
        CONSTITUTIONAL_HASH,
        CONSTITUTIONAL_HASH_VERSIONED,
        DEFAULT_MAX_RETRIES,
        DEFAULT_MESSAGE_TTL_SECONDS,
        DEFAULT_REDIS_DB,
        DEFAULT_REDIS_URL,
        DEFAULT_TIMEOUT_MS,
        HOTL_OVERRIDE_WINDOW_SECONDS,
        MIN_CACHE_HIT_RATE,
        MIN_THROUGHPUT_RPS,
        P99_LATENCY_TARGET_MS,
        RISK_TIER_HIGH_MIN,
        RISK_TIER_LOW_MAX,
        MACIRole,
        RiskTier,
        classify_risk_tier,
        get_constitutional_hash,
    )
except ImportError:
    from enum import StrEnum

    class RiskTier(StrEnum):
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"

    RISK_TIER_LOW_MAX = 0.3
    RISK_TIER_HIGH_MIN = 0.8
    HOTL_OVERRIDE_WINDOW_SECONDS = 900

    def classify_risk_tier(impact_score: float) -> RiskTier:
        if impact_score < RISK_TIER_LOW_MAX:
            return RiskTier.LOW
        if impact_score >= RISK_TIER_HIGH_MIN:
            return RiskTier.HIGH
        return RiskTier.MEDIUM

    class MACIRole(StrEnum):
        EXECUTIVE = "EXECUTIVE"
        LEGISLATIVE = "LEGISLATIVE"
        JUDICIAL = "JUDICIAL"
        MONITOR = "MONITOR"
        AUDITOR = "AUDITOR"
        CONTROLLER = "CONTROLLER"
        IMPLEMENTER = "IMPLEMENTER"

        @classmethod
        def _missing_(cls, value: object) -> "MACIRole | None":
            if isinstance(value, str):
                n = value.strip().upper()
                if n:
                    for m in cls:
                        if m.value == n or m.name == n:
                            return m
            return None

        @classmethod
        def parse(cls, value: "MACIRole | str") -> "MACIRole":
            if isinstance(value, cls):
                return value
            return cls(value)

    CONSTITUTIONAL_HASH = "608508a9bd224290"
    CONSTITUTIONAL_HASH_VERSIONED = "sha256:v1:608508a9bd224290"
    DEFAULT_REDIS_URL = "redis://localhost:6379"
    DEFAULT_REDIS_DB = 0
    P99_LATENCY_TARGET_MS = 5.0
    MIN_THROUGHPUT_RPS = 100
    MIN_CACHE_HIT_RATE = 0.85
    DEFAULT_MESSAGE_TTL_SECONDS = 3600
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_TIMEOUT_MS = 5000
    COMPLIANCE_TARGET = 1.0

    def get_constitutional_hash() -> str:
        return CONSTITUTIONAL_HASH
