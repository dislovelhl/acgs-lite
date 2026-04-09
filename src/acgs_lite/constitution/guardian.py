"""exp178: Graduated autonomy routing with guardian oversight spheres.

Classifies actions into four autonomy spheres based on risk signals,
enabling downstream orchestrators to route governance decisions with
appropriate human oversight levels rather than binary allow/deny.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class AutonomySphere(str, Enum):
    """Graduated autonomy levels for governance routing."""

    AUTONOMOUS = "autonomous"
    CONSULTATIVE = "consultative"
    MANDATORY_APPROVAL = "mandatory_approval"
    FORBIDDEN = "forbidden"


_DEFAULT_THRESHOLDS: dict[str, float] = {
    "autonomous_max": 0.25,
    "consultative_max": 0.55,
    "mandatory_max": 0.85,
}

_SPHERE_METADATA: dict[AutonomySphere, dict[str, Any]] = {
    AutonomySphere.AUTONOMOUS: {
        "human_required": False,
        "latency_budget": "none",
        "description": "Agent proceeds independently; log-only oversight",
    },
    AutonomySphere.CONSULTATIVE: {
        "human_required": False,
        "latency_budget": "async",
        "description": "Agent proceeds but notifies human; review within SLA",
    },
    AutonomySphere.MANDATORY_APPROVAL: {
        "human_required": True,
        "latency_budget": "sync",
        "description": "Agent blocks until human approves; timeout → deny",
    },
    AutonomySphere.FORBIDDEN: {
        "human_required": True,
        "latency_budget": "n/a",
        "description": "Hard deny; no override path without policy amendment",
    },
}


class GuardianGate:
    """Routes actions to autonomy spheres based on risk scoring.

    Combines action risk, context risk, and severity signals into a
    single routing decision. Downstream orchestrators use the sphere
    to determine human oversight level.

    Args:
        thresholds: Risk score boundaries for each sphere.
            Keys: ``autonomous_max``, ``consultative_max``, ``mandatory_max``.
            Scores above ``mandatory_max`` → FORBIDDEN.
        severity_overrides: Map severity names to forced spheres
            (e.g. ``{"critical": "forbidden"}``).
    """

    __slots__ = ("_thresholds", "_severity_overrides", "_history")

    def __init__(
        self,
        *,
        thresholds: dict[str, float] | None = None,
        severity_overrides: dict[str, str] | None = None,
    ) -> None:
        t = thresholds or {}
        self._thresholds = {
            "autonomous_max": t.get("autonomous_max", _DEFAULT_THRESHOLDS["autonomous_max"]),
            "consultative_max": t.get("consultative_max", _DEFAULT_THRESHOLDS["consultative_max"]),
            "mandatory_max": t.get("mandatory_max", _DEFAULT_THRESHOLDS["mandatory_max"]),
        }
        self._severity_overrides: dict[str, AutonomySphere] = {}
        if severity_overrides:
            for sev, sphere_name in severity_overrides.items():
                self._severity_overrides[sev.lower()] = AutonomySphere(sphere_name)
        self._history: list[dict[str, Any]] = []

    def classify(
        self,
        *,
        risk_score: float,
        severity: str = "",
        action: str = "",
        context: dict[str, Any] | None = None,
        agent_id: str = "",
    ) -> dict[str, Any]:
        """Classify an action into an autonomy sphere.

        Args:
            risk_score: Normalized 0-1 risk score (from score_context_risk
                or classify_action_risk).
            severity: Rule severity for override checks.
            action: Action text (for logging/preview).
            context: Optional context signals.
            agent_id: Agent requesting classification.

        Returns:
            dict with ``sphere``, ``risk_score``, ``human_required``,
            ``latency_budget``, ``rationale``, and ``metadata``.
        """
        sev_lower = severity.lower() if severity else ""
        if sev_lower in self._severity_overrides:
            sphere = self._severity_overrides[sev_lower]
            rationale = f"severity override: {severity} → {sphere.value}"
        else:
            sphere = self._score_to_sphere(risk_score)
            rationale = self._build_rationale(risk_score, sphere)

        meta = _SPHERE_METADATA[sphere]
        result: dict[str, Any] = {
            "sphere": sphere.value,
            "risk_score": round(risk_score, 4),
            "human_required": meta["human_required"],
            "latency_budget": meta["latency_budget"],
            "description": meta["description"],
            "rationale": rationale,
            "severity": severity,
            "agent_id": agent_id,
            "action_preview": action[:80] if action else "",
        }

        self._history.append(result)
        return result

    def batch_classify(
        self,
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Classify multiple actions in batch.

        Args:
            items: List of dicts, each with at least ``risk_score``.
                Optional keys: ``severity``, ``action``, ``context``, ``agent_id``.

        Returns:
            List of classification results.
        """
        return [
            self.classify(
                risk_score=item["risk_score"],
                severity=item.get("severity", ""),
                action=item.get("action", ""),
                context=item.get("context"),
                agent_id=item.get("agent_id", ""),
            )
            for item in items
        ]

    def summary(self) -> dict[str, Any]:
        """Summary of classification history."""
        by_sphere: dict[str, int] = {}
        human_required_count = 0
        for entry in self._history:
            s = entry["sphere"]
            by_sphere[s] = by_sphere.get(s, 0) + 1
            if entry["human_required"]:
                human_required_count += 1

        total = len(self._history)
        return {
            "total_classifications": total,
            "by_sphere": by_sphere,
            "human_required_count": human_required_count,
            "human_required_rate": round(human_required_count / total, 4) if total else 0.0,
            "autonomy_rate": round(by_sphere.get("autonomous", 0) / total, 4) if total else 0.0,
            "thresholds": dict(self._thresholds),
        }

    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def _score_to_sphere(self, score: float) -> AutonomySphere:
        if score <= self._thresholds["autonomous_max"]:
            return AutonomySphere.AUTONOMOUS
        if score <= self._thresholds["consultative_max"]:
            return AutonomySphere.CONSULTATIVE
        if score <= self._thresholds["mandatory_max"]:
            return AutonomySphere.MANDATORY_APPROVAL
        return AutonomySphere.FORBIDDEN

    def _build_rationale(self, score: float, sphere: AutonomySphere) -> str:
        t = self._thresholds
        if sphere == AutonomySphere.AUTONOMOUS:
            return f"risk_score={score:.3f} ≤ {t['autonomous_max']} (autonomous threshold)"
        if sphere == AutonomySphere.CONSULTATIVE:
            return (
                f"risk_score={score:.3f} in "
                f"({t['autonomous_max']}, {t['consultative_max']}] (consultative range)"
            )
        if sphere == AutonomySphere.MANDATORY_APPROVAL:
            return (
                f"risk_score={score:.3f} in "
                f"({t['consultative_max']}, {t['mandatory_max']}] (mandatory approval range)"
            )
        return f"risk_score={score:.3f} > {t['mandatory_max']} (forbidden threshold)"

    def __repr__(self) -> str:
        return (
            f"GuardianGate(thresholds={self._thresholds}, "
            f"overrides={len(self._severity_overrides)}, "
            f"history={len(self._history)})"
        )
