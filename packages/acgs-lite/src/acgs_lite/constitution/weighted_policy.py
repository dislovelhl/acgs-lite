"""exp227: Soft-constraint penalty weights for graduated governance enforcement.

Binary allow/deny is too coarse for many governance scenarios.  This module
introduces **penalty-weighted policy evaluation** — each rule contributes a
configurable weight to a cumulative ``violation_score`` (0.0–1.0) so that
downstream consumers can:

- **Rank** multiple agent actions by governance risk
- **Threshold** enforcement at organisational risk tolerance (e.g. block > 0.7)
- **Audit** which combination of rules drove a borderline decision
- **Tune** rule influence without changing keyword lists or severities

Design:

- ``RulePenalty`` — maps a rule ID to a weight in [0.0, 1.0].  Weights are
  additive and capped at 1.0.
- ``WeightedEvaluationResult`` — immutable result with ``violation_score``,
  ``blocked`` flag (score ≥ ``block_threshold``), contributing rules, and
  explanation text.
- ``WeightedConstitution`` — thin wrapper around a ``Constitution`` that
  applies configured weights.  Falls back to severity-derived defaults when
  no explicit weight is configured.

Default weight derivation from severity::

    critical → 0.50
    high     → 0.30
    medium   → 0.15
    low      → 0.05

This means 2 high-severity rule hits already reach 0.60 by default, while a
single critical rule hit reaches 0.50 — near typical 0.6 soft-block thresholds.

Usage::

    from acgs_lite.constitution import Constitution
    from acgs_lite.constitution.weighted_policy import WeightedConstitution, RulePenalty

    c = Constitution.from_yaml("policy.yaml")
    wc = WeightedConstitution(c, penalties=[
        RulePenalty(rule_id="GL-001", weight=0.6),
        RulePenalty(rule_id="GL-002", weight=0.3),
    ], block_threshold=0.5)

    result = wc.evaluate("access patient records")
    print(result.violation_score)   # e.g. 0.9
    print(result.blocked)           # True
    print(result.contributing_rules) # ["GL-001", "GL-002"]
    print(result.explanation)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .core import Constitution, Rule

# ── default severity-to-weight mapping ────────────────────────────────────────

_SEVERITY_WEIGHT: dict[str, float] = {
    "critical": 0.50,
    "high": 0.30,
    "medium": 0.15,
    "low": 0.05,
}

_DEFAULT_BLOCK_THRESHOLD: float = 0.5
_DEFAULT_WARN_THRESHOLD: float = 0.25


@dataclass(frozen=True)
class RulePenalty:
    """Maps a rule ID to a governance penalty weight.

    Attributes:
        rule_id: The rule this penalty applies to.
        weight: Penalty contribution in [0.0, 1.0].  Higher = more severe.
    """

    rule_id: str
    weight: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError(f"weight must be in [0.0, 1.0], got {self.weight}")

    def to_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "weight": self.weight}


@dataclass(frozen=True)
class WeightedEvaluationResult:
    """Result of a weighted policy evaluation.

    Attributes:
        action: The evaluated action string.
        violation_score: Cumulative penalty score in [0.0, 1.0].
        blocked: True when violation_score >= block_threshold.
        warned: True when violation_score >= warn_threshold (but not blocked).
        contributing_rules: Ordered list of rule IDs that fired, by weight desc.
        rule_weights: Dict of rule_id → applied weight for each contributing rule.
        block_threshold: The threshold used to determine blocked.
        warn_threshold: The threshold used to determine warned.
        explanation: Human-readable summary.
    """

    action: str
    violation_score: float
    blocked: bool
    warned: bool
    contributing_rules: list[str]
    rule_weights: dict[str, float]
    block_threshold: float
    warn_threshold: float
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "violation_score": round(self.violation_score, 4),
            "blocked": self.blocked,
            "warned": self.warned,
            "contributing_rules": self.contributing_rules,
            "rule_weights": {k: round(v, 4) for k, v in self.rule_weights.items()},
            "block_threshold": self.block_threshold,
            "warn_threshold": self.warn_threshold,
            "explanation": self.explanation,
        }

    def __repr__(self) -> str:
        status = "BLOCKED" if self.blocked else ("WARNED" if self.warned else "ALLOWED")
        return (
            f"WeightedEvaluationResult({status}, score={self.violation_score:.3f}, "
            f"rules={self.contributing_rules})"
        )


class WeightedConstitution:
    """Penalty-weighted policy evaluator wrapping a Constitution.

    Evaluates actions against the wrapped constitution and computes a
    continuous violation score by summing penalty weights of all firing rules.
    Scores are capped at 1.0.

    Falls back to severity-derived default weights when no explicit
    :class:`RulePenalty` is configured for a rule.

    Args:
        constitution: The constitution to wrap.
        penalties: Optional list of :class:`RulePenalty` overrides.
        block_threshold: Violation score >= this → blocked (default 0.5).
        warn_threshold: Violation score >= this → warned (default 0.25).

    Example::

        wc = WeightedConstitution(c, penalties=[
            RulePenalty("GL-001", 0.7),
            RulePenalty("GL-002", 0.2),
        ])
        result = wc.evaluate("delete all records")
        if result.blocked:
            raise GovernanceError(result.explanation)
    """

    def __init__(
        self,
        constitution: Constitution,
        *,
        penalties: list[RulePenalty] | None = None,
        block_threshold: float = _DEFAULT_BLOCK_THRESHOLD,
        warn_threshold: float = _DEFAULT_WARN_THRESHOLD,
    ) -> None:
        if not 0.0 < block_threshold <= 1.0:
            raise ValueError(f"block_threshold must be in (0.0, 1.0], got {block_threshold}")
        if not 0.0 <= warn_threshold < block_threshold:
            raise ValueError(
                f"warn_threshold must be in [0.0, block_threshold), "
                f"got {warn_threshold} vs {block_threshold}"
            )
        self._constitution = constitution
        self._penalties: dict[str, float] = {p.rule_id: p.weight for p in (penalties or [])}
        self._block_threshold = block_threshold
        self._warn_threshold = warn_threshold

    # ── delegation ─────────────────────────────────────────────────────────

    def __getattr__(self, name: str) -> Any:
        return getattr(self._constitution, name)

    @property
    def constitution(self) -> Constitution:
        return self._constitution

    @property
    def block_threshold(self) -> float:
        return self._block_threshold

    @property
    def warn_threshold(self) -> float:
        return self._warn_threshold

    # ── weight resolution ──────────────────────────────────────────────────

    def _weight_for(self, rule: Rule) -> float:
        """Return configured weight, or severity-derived default."""
        if rule.id in self._penalties:
            return self._penalties[rule.id]
        sev = rule.severity.value if hasattr(rule.severity, "value") else str(rule.severity)
        return _SEVERITY_WEIGHT.get(sev.lower(), 0.10)

    # ── evaluation ────────────────────────────────────────────────────────

    def evaluate(
        self,
        action: str,
        context: dict[str, Any] | None = None,
    ) -> WeightedEvaluationResult:
        """Evaluate *action* and return a weighted violation score.

        Rules that match the action contribute their penalty weight to the
        cumulative score.  The score is the sum of all contributing weights,
        capped at 1.0.

        Args:
            action: The agent action string.
            context: Optional runtime context for condition matching.

        Returns:
            :class:`WeightedEvaluationResult` with score, blocked, and details.
        """
        ctx = context or {}
        action_lower = action.lower()

        # Collect firing rules with their weights
        hits: list[tuple[str, float]] = []  # (rule_id, weight)
        for rule in self._constitution.rules:
            if not rule.enabled or rule.deprecated:
                continue
            # Keyword / pattern matching
            matched = any(kw.lower() in action_lower for kw in rule.keywords)
            if not matched:
                matched = any(
                    __import__("re").search(pat, action, __import__("re").IGNORECASE)
                    for pat in (rule.patterns or [])
                )
            if not matched:
                continue
            # Condition matching (exp129)
            if (
                ctx
                and hasattr(rule, "condition")
                and rule.condition
                and not rule.condition_matches(ctx)
            ):
                continue
            hits.append((rule.id, self._weight_for(rule)))

        # Sort by weight descending for explanation clarity
        hits.sort(key=lambda x: x[1], reverse=True)

        score = min(1.0, sum(w for _, w in hits))
        rule_weights = dict(hits)
        contributing = [rid for rid, _ in hits]

        blocked = score >= self._block_threshold
        warned = (not blocked) and score >= self._warn_threshold

        if blocked:
            status = "BLOCKED"
        elif warned:
            status = "WARNED"
        else:
            status = "ALLOWED"

        if contributing:
            rule_summary = ", ".join(f"{rid}(w={w:.2f})" for rid, w in hits[:5])
            explanation = (
                f"{status}: action={action!r} violation_score={score:.3f} "
                f"threshold={self._block_threshold} rules=[{rule_summary}]"
            )
        else:
            explanation = f"{status}: action={action!r} — no rules matched"

        return WeightedEvaluationResult(
            action=action,
            violation_score=score,
            blocked=blocked,
            warned=warned,
            contributing_rules=contributing,
            rule_weights=rule_weights,
            block_threshold=self._block_threshold,
            warn_threshold=self._warn_threshold,
            explanation=explanation,
        )

    def evaluate_batch(
        self,
        actions: list[str],
        context: dict[str, Any] | None = None,
    ) -> list[WeightedEvaluationResult]:
        """Evaluate multiple actions and return results sorted by violation_score desc.

        Args:
            actions: List of action strings.
            context: Optional shared context.

        Returns:
            List of :class:`WeightedEvaluationResult` sorted highest-risk first.
        """
        results = [self.evaluate(a, context) for a in actions]
        results.sort(key=lambda r: r.violation_score, reverse=True)
        return results

    def rank_actions(
        self,
        actions: list[str],
        context: dict[str, Any] | None = None,
    ) -> list[tuple[str, float]]:
        """Return (action, violation_score) pairs sorted highest-risk first.

        Convenience wrapper around :meth:`evaluate_batch` for quick ranking.

        Args:
            actions: Actions to rank.
            context: Optional context.

        Returns:
            List of (action, score) tuples, highest score first.
        """
        results = self.evaluate_batch(actions, context)
        return [(r.action, r.violation_score) for r in results]

    def add_penalty(self, rule_id: str, weight: float) -> WeightedConstitution:
        """Return a new WeightedConstitution with an added/updated penalty.

        Immutable — does not modify self.

        Args:
            rule_id: Rule to configure.
            weight: New penalty weight.

        Returns:
            New :class:`WeightedConstitution`.
        """
        new_penalties = dict(self._penalties)
        new_penalties[rule_id] = weight
        penalty_list = [RulePenalty(rid, w) for rid, w in new_penalties.items()]
        return WeightedConstitution(
            self._constitution,
            penalties=penalty_list,
            block_threshold=self._block_threshold,
            warn_threshold=self._warn_threshold,
        )

    def penalties_summary(self) -> dict[str, Any]:
        """Return a summary of all configured and default-derived penalty weights.

        Returns:
            Dict with configured_penalties and default_severity_weights.
        """
        return {
            "configured_penalties": {k: round(v, 4) for k, v in self._penalties.items()},
            "default_severity_weights": _SEVERITY_WEIGHT,
            "block_threshold": self._block_threshold,
            "warn_threshold": self._warn_threshold,
            "rule_count": len(self._constitution.rules),
        }

    def __repr__(self) -> str:
        return (
            f"WeightedConstitution("
            f"name={self._constitution.name!r}, "
            f"rules={len(self._constitution.rules)}, "
            f"configured_penalties={len(self._penalties)}, "
            f"block_threshold={self._block_threshold})"
        )
