from __future__ import annotations

from typing import Any


class GovernanceDecisionValidator:
    async def validate_decision(
        self,
        *,
        decision: dict[str, Any],
        context: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        errors: list[str] = []

        risk_score = float(decision.get("risk_score", 0.0))
        threshold = float(decision.get("recommended_threshold", 0.0))
        action_allowed = bool(decision.get("action_allowed", False))

        if risk_score < 0 or risk_score > 1:
            errors.append("risk_score must be between 0.0 and 1.0")
        if threshold < 0 or threshold > 1:
            errors.append("recommended_threshold must be between 0.0 and 1.0")
        if action_allowed != (risk_score <= threshold):
            errors.append("action_allowed does not match risk/threshold decision rule")

        constitutional_hash = context.get("constitutional_hash")
        if constitutional_hash and constitutional_hash != context.get(
            "expected_constitutional_hash"
        ):
            errors.append("constitutional hash mismatch in validation context")

        return len(errors) == 0, errors
