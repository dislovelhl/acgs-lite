"""Shim for src.core.shared.config.governance."""

from __future__ import annotations

from typing import Any

try:
    from src.core.shared.config.governance import *  # noqa: F403
except ImportError:

    class MACISettings:
        enabled: bool = True
        strict_mode: bool = True
        max_proposal_age_seconds: int = 3600
        quorum_threshold: float = 0.51

        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

    class VotingSettings:
        enabled: bool = True
        min_voters: int = 1
        approval_threshold: float = 0.51
        voting_period_seconds: int = 86400

        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)

    class ConstitutionalSettings:
        hash: str = "608508a9bd224290"
        version: str = "v1"
        enforcement_mode: str = "strict"

        def __init__(self, **kwargs: Any) -> None:
            for k, v in kwargs.items():
                setattr(self, k, v)
