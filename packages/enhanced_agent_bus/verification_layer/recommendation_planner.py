from __future__ import annotations

from typing import Any


class MACIRemediationPlanner:
    def generate_recommendations(
        self,
        *,
        judgment: dict[str, Any],
        decision: dict[str, Any],
    ) -> list[str]:
        recommendations: list[str] = []

        if not judgment.get("is_compliant"):
            recommendations.append("Review and address identified violations before proceeding")

        violations = judgment.get("violations", [])
        for violation in violations:
            severity = violation.get("severity", "medium")
            if severity == "critical":
                recommendations.append(
                    f"CRITICAL: {violation.get('description', 'Address critical violation')}"
                )

        risk_score = decision.get("risk_assessment", {}).get("score", 0)
        if risk_score > 0.7:
            recommendations.append("High risk decision: Consider human review before execution")

        return recommendations
