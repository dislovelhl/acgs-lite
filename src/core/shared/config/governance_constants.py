"""Centralized governance constants extracted from production modules.

These values were previously scattered as magic numbers across session_governance,
impact_scorer, and monitoring. Centralizing them here enables:
  - Single source of truth for tuning
  - Easier auditing and documentation
  - Future env-var override via ``os.getenv`` wrappers

Categories follow the domain split: session management, impact scoring,
and operational monitoring.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
#  Session Governance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionConfig:
    """Session governance limits and thresholds."""

    cache_ttl_seconds: int = 3600
    """Default cache TTL (1 hour)."""

    max_concurrent_sessions: int = 10_000
    """Hard limit on concurrent sessions per tenant."""

    session_trim_threshold: int = 5_000
    """Keep last N sessions when list exceeds ``max_concurrent_sessions``."""

    violation_escalation_threshold: int = 3
    """Violation count that triggers auto-escalation to CRITICAL risk."""


# ---------------------------------------------------------------------------
#  Impact Scoring
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImpactScorerConfig:
    """Thresholds for the rule-based impact scoring fallback."""

    rf_n_estimators: int = 20
    rf_max_depth: int = 10
    rf_random_state: int = 42

    confidence_fallback: float = 0.7
    """Confidence level for rule-based fallback scoring."""

    conservative_default_score: float = 0.1
    """Score returned when scoring fails entirely."""

    msg_length_high_threshold: int = 10_000
    """Character count that adds +0.3 risk."""

    msg_length_low_threshold: int = 1_000
    """Character count that adds +0.1 risk."""

    agent_count_high_threshold: int = 10
    """Agent count that adds +0.2 risk."""

    agent_count_low_threshold: int = 5
    """Agent count that adds +0.1 risk."""

    min_training_samples: int = 500
    """Minimum samples before model retraining is allowed."""

    retrain_frequency: int = 1000
    """Retrain every N new samples (modulo check)."""

    training_window: int = 2000
    """Sliding window of recent training samples."""

    high_impact_threshold: float = 0.7
    """Score >= this is classified as high-impact."""

    medium_impact_threshold: float = 0.3
    """Score >= this is classified as medium-impact."""


# ---------------------------------------------------------------------------
#  Operational Monitoring
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MonitoringConfig:
    """Operational alert thresholds and limits."""

    process_sample_limit: int = 100
    """Max PIDs sampled for process metrics."""

    cpu_warning_percent: float = 80.0
    cpu_critical_percent: float = 85.0

    memory_warning_percent: float = 80.0
    memory_critical_percent: float = 90.0

    disk_warning_percent: float = 80.0
    disk_critical_percent: float = 90.0

    redis_hit_rate_constitutional_min: float = 85.0
    """Constitutional minimum Redis cache hit rate (percent)."""

    metrics_history_limit: int = 1_000
    """Maximum retained metrics entries."""

    dedup_window_minutes: int = 5
    max_alerts_per_minute: int = 10


# ---------------------------------------------------------------------------
#  Singleton instances — import these directly
# ---------------------------------------------------------------------------

SESSION_CONFIG = SessionConfig()
IMPACT_SCORER_CONFIG = ImpactScorerConfig()
MONITORING_CONFIG = MonitoringConfig()
