"""Shim for src.core.shared.policy.models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    from src.core.shared.policy.models import *  # noqa: F403
except ImportError:

    @dataclass
    class PolicySpecification:
        id: str = ""
        name: str = ""
        version: str = "1.0"
        description: str = ""
        rules: list[dict[str, Any]] = field(default_factory=list)
        metadata: dict[str, Any] = field(default_factory=dict)
        enabled: bool = True

    @dataclass
    class PolicyDecisionResult:
        allowed: bool = False
        reason: str = ""
        policy_id: str = ""
        details: dict[str, Any] = field(default_factory=dict)

    @dataclass
    class PolicyEvaluationContext:
        agent_id: str = ""
        action: str = ""
        resource: str = ""
        environment: dict[str, Any] = field(default_factory=dict)
