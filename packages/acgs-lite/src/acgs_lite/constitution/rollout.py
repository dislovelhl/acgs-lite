"""exp173: PolicyRolloutPipeline — staged constitution deployment.

Implements a Shadow → Canary → Enforce rollout pipeline for safely
transitioning from one constitution to another with quantified impact
measurement at each stage.

Stage semantics:

- **shadow**: New constitution evaluates decisions in parallel but results
  are not enforced. Only divergence (flip rate) is tracked.
- **canary**: New constitution enforces decisions for a configurable subset
  of agents (canary_agent_ids). All others use the current constitution.
- **enforce**: New constitution is fully active for all agents.
- **rollback**: Pipeline aborted; current constitution restored for all.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .constitution import Constitution


class RolloutStage(str, Enum):
    """Lifecycle stage of a constitution rollout."""

    shadow = "shadow"
    canary = "canary"
    enforce = "enforce"
    rollback = "rollback"


@dataclass(frozen=True, slots=True)
class DecisionFlip:
    """Record of a single decision that differs between constitutions.

    A flip occurs when the current and candidate constitutions produce
    different outcomes for the same action.
    """

    action: str
    agent_id: str
    current_decision: str  # "allow" | "deny"
    candidate_decision: str  # "allow" | "deny"
    stage: str
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "agent_id": self.agent_id,
            "current_decision": self.current_decision,
            "candidate_decision": self.candidate_decision,
            "stage": self.stage,
            "timestamp": self.timestamp,
        }


@dataclass
class RolloutStageMetrics:
    """Aggregate metrics for a single pipeline stage."""

    stage: str
    evaluations: int = 0
    flips: int = 0
    allow_to_deny: int = 0  # safety-relevant: new constitution is stricter
    deny_to_allow: int = 0  # permissiveness-relevant: new is looser
    canary_evaluations: int = 0  # only for canary stage
    canary_flips: int = 0  # only for canary stage

    @property
    def flip_rate(self) -> float:
        """Fraction of evaluations where decisions diverged (0-1)."""
        return self.flips / self.evaluations if self.evaluations else 0.0

    @property
    def canary_flip_rate(self) -> float:
        """Flip rate among canary agents only."""
        return self.canary_flips / self.canary_evaluations if self.canary_evaluations else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "evaluations": self.evaluations,
            "flips": self.flips,
            "flip_rate": round(self.flip_rate, 6),
            "allow_to_deny": self.allow_to_deny,
            "deny_to_allow": self.deny_to_allow,
            "canary_evaluations": self.canary_evaluations,
            "canary_flips": self.canary_flips,
            "canary_flip_rate": round(self.canary_flip_rate, 6),
        }


def _simple_decision(constitution: Constitution, action: str) -> str:
    """Return 'allow' or 'deny' without raising, for rollout comparison."""
    try:
        from acgs_lite.engine import GovernanceEngine

        engine = GovernanceEngine(constitution)
        result = engine.validate(action)
        return "allow" if result.valid else "deny"
    except (ImportError, ValueError, TypeError, RuntimeError, AttributeError):
        return "deny"


class PolicyRolloutPipeline:
    """Staged pipeline for safely rolling out a new constitution.

    Tracks decision divergence across Shadow → Canary → Enforce stages.
    At each stage, quantifies how many decisions flip (allow→deny or
    deny→allow) so teams can assess risk before full enforcement.

    Usage::

        from acgs_lite.constitution.rollout import PolicyRolloutPipeline, RolloutStage

        pipeline = PolicyRolloutPipeline(
            name="v2-stricter-pii-rules",
            current_constitution=current_c,
            candidate_constitution=candidate_c,
            canary_agent_ids=["agent-sandbox-1", "agent-sandbox-2"],
            flip_rate_threshold=0.05,  # auto-rollback if >5% of decisions flip
        )

        # Shadow: measure divergence without enforcing
        pipeline.advance()  # → shadow

        result = pipeline.evaluate(action="export pii data", agent_id="agent-prod-1")
        # result["enforced_decision"] = "allow" (current constitution, shadow mode)
        # result["shadow_decision"] = "deny" (candidate would block — recorded as flip)

        # Canary: enforce for sandbox agents only
        pipeline.advance()  # → canary

        # Enforce: full rollout
        pipeline.advance()  # → enforce

        print(pipeline.impact_report())

    Auto-rollback::

        pipeline = PolicyRolloutPipeline(
            ...,
            flip_rate_threshold=0.05,
        )
        pipeline.advance()  # shadow

        # After many evaluations, if flip_rate > 0.05 the pipeline auto-rolls back
        for action in actions:
            pipeline.evaluate(action, agent_id="agent-1")

        print(pipeline.stage)  # may be "rollback" if threshold exceeded
    """

    __slots__ = (
        "_name",
        "_current",
        "_candidate",
        "_canary_agents",
        "_flip_threshold",
        "_stage",
        "_flips",
        "_stage_metrics",
        "_created_at",
        "_stage_history",
    )

    def __init__(
        self,
        name: str,
        current_constitution: Constitution,
        candidate_constitution: Constitution,
        *,
        canary_agent_ids: list[str] | None = None,
        flip_rate_threshold: float = 1.0,
    ) -> None:
        """Initialise a rollout pipeline in pre-shadow state.

        Args:
            name: Human-readable pipeline name (e.g. ``"v2-pii-rules"``).
            current_constitution: The currently enforced constitution.
            candidate_constitution: The constitution being rolled out.
            canary_agent_ids: Agent IDs that receive the new constitution
                during the canary stage. All others keep the current one.
            flip_rate_threshold: If the observed flip_rate exceeds this
                value at any stage the pipeline automatically moves to
                ``rollback``. Default is ``1.0`` (never auto-rollback).
        """
        self._name = name
        self._current = current_constitution
        self._candidate = candidate_constitution
        self._canary_agents: frozenset[str] = frozenset(canary_agent_ids or [])
        self._flip_threshold = flip_rate_threshold
        self._stage: RolloutStage = RolloutStage.shadow  # starts at shadow
        self._flips: list[DecisionFlip] = []
        self._stage_metrics: dict[str, RolloutStageMetrics] = {
            s.value: RolloutStageMetrics(stage=s.value) for s in RolloutStage
        }
        self._created_at: str = datetime.now(timezone.utc).isoformat()
        self._stage_history: list[dict[str, str]] = [
            {"stage": RolloutStage.shadow.value, "entered_at": self._created_at}
        ]

    # ── stage control ────────────────────────────────────────────────────────

    @property
    def stage(self) -> str:
        """Current pipeline stage."""
        return self._stage.value

    @property
    def name(self) -> str:
        return self._name

    def advance(self) -> str:
        """Advance to the next stage in order: shadow → canary → enforce.

        If the current flip rate already exceeds the threshold, advances
        to ``rollback`` instead.

        Returns:
            The new stage name.

        Raises:
            RuntimeError: If the pipeline is already in ``enforce`` or
                ``rollback`` — both are terminal stages.
        """
        if self._stage in (RolloutStage.enforce, RolloutStage.rollback):
            msg = f"Pipeline is in terminal stage {self._stage.value!r} — cannot advance."
            raise RuntimeError(msg)

        _order = [RolloutStage.shadow, RolloutStage.canary, RolloutStage.enforce]
        current_idx = _order.index(self._stage)

        # Check threshold before advancing
        current_metrics = self._stage_metrics[self._stage.value]
        if current_metrics.evaluations > 0 and current_metrics.flip_rate > self._flip_threshold:
            self._stage = RolloutStage.rollback
        elif current_idx + 1 < len(_order):
            self._stage = _order[current_idx + 1]
        else:
            self._stage = RolloutStage.enforce

        self._stage_history.append(
            {
                "stage": self._stage.value,
                "entered_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return self._stage.value

    def rollback(self, *, reason: str = "") -> str:
        """Manually abort rollout and restore current constitution for all agents.

        Args:
            reason: Optional human-readable reason for the rollback.

        Returns:
            ``"rollback"``
        """
        self._stage = RolloutStage.rollback
        entry: dict[str, str] = {
            "stage": "rollback",
            "entered_at": datetime.now(timezone.utc).isoformat(),
        }
        if reason:
            entry["reason"] = reason
        self._stage_history.append(entry)
        return "rollback"

    # ── evaluation ───────────────────────────────────────────────────────────

    def evaluate(
        self, action: str, *, agent_id: str = "", context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Evaluate an action against the pipeline's active constitution.

        Behaviour depends on the current stage:

        - **shadow**: Always uses ``current`` for enforcement. Evaluates
          ``candidate`` in parallel and logs any divergence.
        - **canary**: Uses ``candidate`` for agents in ``canary_agent_ids``;
          uses ``current`` for all others. Logs divergence for all.
        - **enforce**: Always uses ``candidate``.
        - **rollback**: Always uses ``current``.

        Args:
            action: The action string to evaluate.
            agent_id: Identifier of the requesting agent (used for canary routing).
            context: Optional context dict (currently unused in evaluation,
                passed through for future extension).

        Returns:
            dict with keys:

            - ``enforced_decision``: The decision that is actually enforced.
            - ``candidate_decision``: What the candidate would decide.
            - ``flip``: True if the two constitutions disagree.
            - ``stage``: Current pipeline stage.
            - ``agent_id``: The provided agent_id.
            - ``action``: The evaluated action.
        """
        ts = datetime.now(timezone.utc).isoformat()
        stage_name = self._stage.value
        metrics = self._stage_metrics[stage_name]

        current_dec = _simple_decision(self._current, action)
        candidate_dec = _simple_decision(self._candidate, action)
        flip = current_dec != candidate_dec

        # Determine enforced decision based on stage
        is_canary_agent = agent_id in self._canary_agents
        if self._stage == RolloutStage.shadow:
            enforced = current_dec
        elif self._stage == RolloutStage.canary:
            enforced = candidate_dec if is_canary_agent else current_dec
        elif self._stage == RolloutStage.enforce:
            enforced = candidate_dec
        else:  # rollback
            enforced = current_dec

        # Record metrics
        metrics.evaluations += 1
        if flip:
            metrics.flips += 1
            if current_dec == "allow" and candidate_dec == "deny":
                metrics.allow_to_deny += 1
            else:
                metrics.deny_to_allow += 1

            flip_record = DecisionFlip(
                action=action,
                agent_id=agent_id,
                current_decision=current_dec,
                candidate_decision=candidate_dec,
                stage=stage_name,
                timestamp=ts,
            )
            self._flips.append(flip_record)

        if self._stage == RolloutStage.canary and is_canary_agent:
            metrics.canary_evaluations += 1
            if flip:
                metrics.canary_flips += 1

        # Auto-rollback check
        if (
            self._stage not in (RolloutStage.enforce, RolloutStage.rollback)
            and metrics.evaluations >= 10  # need minimum sample before auto-rollback
            and metrics.flip_rate > self._flip_threshold
        ):
            self.rollback(
                reason=(
                    f"Auto-rollback: flip_rate={metrics.flip_rate:.4f} "
                    f"exceeded threshold={self._flip_threshold}"
                )
            )

        return {
            "enforced_decision": enforced,
            "candidate_decision": candidate_dec,
            "current_decision": current_dec,
            "flip": flip,
            "stage": stage_name,
            "agent_id": agent_id,
            "action": action,
            "is_canary_agent": is_canary_agent,
        }

    # ── reporting ─────────────────────────────────────────────────────────────

    def impact_report(self) -> dict[str, Any]:
        """Return a full impact analysis of the rollout so far.

        Returns:
            dict with:

            - ``pipeline``: name, stage, created_at, flip_threshold
            - ``current_constitution``: name + hash
            - ``candidate_constitution``: name + hash
            - ``stage_history``: list of stage transitions with timestamps
            - ``stage_metrics``: per-stage evaluation + flip statistics
            - ``total_flips``: aggregate flip count across all stages
            - ``sample_flips``: up to 20 representative flip records
            - ``recommendation``: human-readable assessment
        """
        total_evals = sum(m.evaluations for m in self._stage_metrics.values())
        total_flips = len(self._flips)
        overall_flip_rate = total_flips / total_evals if total_evals else 0.0

        # Recommendation logic
        if self._stage == RolloutStage.rollback:
            recommendation = (
                "Rollback active. Candidate constitution was reverted. "
                "Investigate flips before attempting another rollout."
            )
        elif overall_flip_rate == 0.0:
            recommendation = (
                "No decision flips observed. Candidate constitution is "
                "behaviourally equivalent to current. Safe to advance."
            )
        elif overall_flip_rate < 0.01:
            recommendation = (
                f"Low flip rate ({overall_flip_rate:.2%}). Review sample flips "
                "before advancing to enforce stage."
            )
        elif overall_flip_rate < 0.05:
            recommendation = (
                f"Moderate flip rate ({overall_flip_rate:.2%}). Extend canary "
                "period and review allow→deny flips carefully."
            )
        else:
            recommendation = (
                f"High flip rate ({overall_flip_rate:.2%}). Consider rollback "
                "or revising the candidate constitution before proceeding."
            )

        return {
            "pipeline": {
                "name": self._name,
                "stage": self._stage.value,
                "created_at": self._created_at,
                "flip_rate_threshold": self._flip_threshold,
                "canary_agent_count": len(self._canary_agents),
            },
            "current_constitution": {
                "name": self._current.name,
                "hash": self._current.hash,
            },
            "candidate_constitution": {
                "name": self._candidate.name,
                "hash": self._candidate.hash,
            },
            "stage_history": list(self._stage_history),
            "stage_metrics": {
                stage: m.to_dict() for stage, m in self._stage_metrics.items() if m.evaluations > 0
            },
            "total_evaluations": total_evals,
            "total_flips": total_flips,
            "overall_flip_rate": round(overall_flip_rate, 6),
            "sample_flips": [f.to_dict() for f in self._flips[:20]],
            "recommendation": recommendation,
        }

    def flip_summary(self) -> dict[str, Any]:
        """Return a compact flip-only summary for dashboards.

        Returns:
            dict with flip counts by type and stage.
        """
        by_stage: dict[str, dict[str, int]] = {}
        for flip in self._flips:
            s = flip.stage
            if s not in by_stage:
                by_stage[s] = {"allow_to_deny": 0, "deny_to_allow": 0}
            if flip.current_decision == "allow":
                by_stage[s]["allow_to_deny"] += 1
            else:
                by_stage[s]["deny_to_allow"] += 1

        return {
            "total_flips": len(self._flips),
            "by_stage": by_stage,
            "current_stage": self._stage.value,
        }

    def __repr__(self) -> str:
        return (
            f"PolicyRolloutPipeline("
            f"name={self._name!r}, "
            f"stage={self._stage.value!r}, "
            f"flips={len(self._flips)})"
        )
