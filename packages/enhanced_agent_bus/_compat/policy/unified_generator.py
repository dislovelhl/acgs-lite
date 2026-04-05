"""Shim for src.core.shared.policy.unified_generator."""

from __future__ import annotations

from typing import Any

try:
    from src.core.shared.policy.unified_generator import *  # noqa: F403
except ImportError:

    class UnifiedPolicyGenerator:
        """Stub policy generator for standalone mode."""

        def __init__(self, **kwargs: Any) -> None:
            pass

        async def generate(self, specification: Any = None, **kwargs: Any) -> dict[str, Any]:
            return {"policy": {}, "generated": False, "reason": "standalone mode"}

        async def validate(self, policy: dict[str, Any]) -> bool:
            return True

    def get_policy_generator(**kwargs: Any) -> UnifiedPolicyGenerator:
        return UnifiedPolicyGenerator(**kwargs)
