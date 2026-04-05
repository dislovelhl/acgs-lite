"""Shim for src.core.shared.config.governance_constants."""
from __future__ import annotations

try:
    from src.core.shared.config.governance_constants import *  # noqa: F403
except ImportError:

    IMPACT_SCORER_CONFIG: dict[str, object] = {}
    RISK_THRESHOLDS: dict[str, float] = {
        "low": 0.3,
        "medium": 0.6,
        "high": 0.8,
    }
    DEFAULT_VOTING_QUORUM: float = 0.51
    DEFAULT_APPROVAL_THRESHOLD: float = 0.51
    MAX_PROPOSAL_AGE_SECONDS: int = 3600
