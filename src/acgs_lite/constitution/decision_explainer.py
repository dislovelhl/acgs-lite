"""Governance decision explainer — structured explanations for governance decisions.

Generates human-readable, structured explanations for why a governance decision
was reached. Consumes the rich metadata already produced by the Constitution
(matched rules, severity, workflow action, tags, categories) and renders it into
templated explanation objects suitable for audit logs, HITL review queues,
end-user notifications, and downstream agent reasoning.

Zero hot-path overhead: all explanation work happens post-decision, on demand.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExplanationDetail(str, Enum):
    """How much detail to include in an explanation."""

    BRIEF = "brief"  # one-line summary
    STANDARD = "standard"  # structured sections, no raw rule data
    VERBOSE = "verbose"  # full rule details, matched keywords, remediation


class ExplanationFormat(str, Enum):
    """Output format for explanation rendering."""

    TEXT = "text"
    MARKDOWN = "markdown"
    JSON = "json"


@dataclass
class RuleSummary:
    """Condensed view of a rule that contributed to a decision."""

    rule_id: str
    description: str
    severity: str
    category: str
    workflow_action: str
    matched_keywords: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "description": self.description,
            "severity": self.severity,
            "category": self.category,
            "workflow_action": self.workflow_action,
            "matched_keywords": self.matched_keywords,
            "tags": self.tags,
        }


@dataclass
class DecisionExplanation:
    """Structured explanation of a single governance decision.

    Attributes:
        decision_id: Caller-supplied identifier for the decision being explained.
        outcome: The governance outcome (e.g. ``"allow"``, ``"deny"``, ``"warn"``).
        summary: One-line human-readable summary of the decision.
        rationale: Paragraph-form reasoning (2-4 sentences).
        blocking_rules: Rules that caused a deny/block outcome.
        warning_rules: Rules that triggered warnings but did not block.
        categories_triggered: Unique rule categories that fired.
        tags_triggered: Unique tags across all triggered rules.
        remediation_hints: Actionable suggestions for the requester.
        confidence: Estimated explanation confidence 0.0-1.0.
        detail_level: The detail level used to generate this explanation.
        generated_at: Monotonic timestamp of generation.
        raw_context: Original context dict passed to the decision (if captured).
    """

    decision_id: str
    outcome: str
    summary: str
    rationale: str
    blocking_rules: list[RuleSummary] = field(default_factory=list)
    warning_rules: list[RuleSummary] = field(default_factory=list)
    categories_triggered: list[str] = field(default_factory=list)
    tags_triggered: list[str] = field(default_factory=list)
    remediation_hints: list[str] = field(default_factory=list)
    confidence: float = 1.0
    detail_level: ExplanationDetail = ExplanationDetail.STANDARD
    generated_at: float = field(default_factory=time.monotonic)
    raw_context: dict[str, Any] | None = None

    @property
    def is_blocked(self) -> bool:
        return bool(self.blocking_rules)

    @property
    def has_warnings(self) -> bool:
        return bool(self.warning_rules)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "outcome": self.outcome,
            "summary": self.summary,
            "rationale": self.rationale,
            "blocking_rules": [r.to_dict() for r in self.blocking_rules],
            "warning_rules": [r.to_dict() for r in self.warning_rules],
            "categories_triggered": self.categories_triggered,
            "tags_triggered": self.tags_triggered,
            "remediation_hints": self.remediation_hints,
            "confidence": self.confidence,
            "detail_level": self.detail_level.value,
            "generated_at": self.generated_at,
        }


class GovernanceDecisionExplainer:
    """Generates structured explanations for governance decisions.

    Accepts the rich output already produced by :class:`Constitution.decide()`
    (or equivalent) and renders it into :class:`DecisionExplanation` objects.

    The explainer is intentionally stateless — it keeps an optional explanation
    history for auditability, but the core ``explain()`` method is a pure
    transformation: input → explanation.

    Example usage::

        explainer = GovernanceDecisionExplainer()

        # After calling constitution.decide() / validate()
        explanation = explainer.explain(
            decision_id="dec-001",
            outcome="deny",
            triggered_rules=[
                {"id": "pii-block", "description": "Block PII exfiltration",
                 "severity": "critical", "category": "privacy",
                 "workflow_action": "block", "keywords": ["ssn", "credit_card"]},
            ],
            input_text="Please share the user's SSN",
            context={"agent_id": "agent-7", "domain": "customer-service"},
        )
        print(explanation.summary)
        print(explainer.render(explanation, fmt=ExplanationFormat.MARKDOWN))
    """

    _BLOCK_ACTIONS = frozenset({"block", "deny", "reject", "quarantine"})
    _WARN_ACTIONS = frozenset({"warn", "review", "flag", "monitor", "escalate"})

    _SEVERITY_LANGUAGE: dict[str, str] = {
        "critical": "critically sensitive",
        "high": "high-risk",
        "medium": "moderately sensitive",
        "low": "low-risk",
        "info": "informational",
    }

    def __init__(self, *, store_history: bool = True) -> None:
        self._history: list[DecisionExplanation] = []
        self._store_history = store_history

    def explain(
        self,
        *,
        decision_id: str,
        outcome: str,
        triggered_rules: list[dict[str, Any]],
        input_text: str = "",
        context: dict[str, Any] | None = None,
        detail: ExplanationDetail = ExplanationDetail.STANDARD,
    ) -> DecisionExplanation:
        """Generate a structured explanation for a governance decision.

        Args:
            decision_id: Caller-supplied identifier for this decision.
            outcome: The governance outcome string (``"allow"``, ``"deny"``, etc.).
            triggered_rules: List of rule dicts. Each should have keys:
                ``id``, ``description``, ``severity``, ``category``,
                ``workflow_action``, optionally ``keywords`` and ``tags``.
            input_text: The original text/request that was evaluated (used for
                context-aware remediation hints).
            context: Original context dict passed to the governance engine.
            detail: How much detail to include in the explanation.

        Returns:
            A :class:`DecisionExplanation` ready for rendering or serialisation.
        """
        blocking: list[RuleSummary] = []
        warning: list[RuleSummary] = []

        for rule in triggered_rules:
            action = str(rule.get("workflow_action", "")).lower()
            summary = RuleSummary(
                rule_id=str(rule.get("id", rule.get("rule_id", "unknown"))),
                description=str(rule.get("description", "")),
                severity=str(rule.get("severity", "medium")),
                category=str(rule.get("category", "general")),
                workflow_action=action,
                matched_keywords=list(rule.get("keywords", rule.get("matched_keywords", []))),
                tags=list(rule.get("tags", [])),
            )
            if action in self._BLOCK_ACTIONS:
                blocking.append(summary)
            else:
                warning.append(summary)

        categories = list(dict.fromkeys(r.category for r in (blocking + warning)))
        tags = list(dict.fromkeys(t for r in (blocking + warning) for t in r.tags))

        one_line = self._build_summary(outcome, blocking, warning)
        rationale = self._build_rationale(outcome, blocking, warning, input_text, context)
        hints = self._build_remediation(blocking, warning, input_text, detail)

        explanation = DecisionExplanation(
            decision_id=decision_id,
            outcome=outcome,
            summary=one_line,
            rationale=rationale,
            blocking_rules=blocking,
            warning_rules=warning,
            categories_triggered=categories,
            tags_triggered=tags,
            remediation_hints=hints,
            confidence=self._estimate_confidence(blocking, warning),
            detail_level=detail,
            raw_context=context if detail == ExplanationDetail.VERBOSE else None,
        )

        if self._store_history:
            self._history.append(explanation)

        return explanation

    def render(
        self,
        explanation: DecisionExplanation,
        fmt: ExplanationFormat = ExplanationFormat.TEXT,
    ) -> str:
        """Render an explanation to a string in the requested format.

        Args:
            explanation: The :class:`DecisionExplanation` to render.
            fmt: Output format — text, markdown, or JSON.

        Returns:
            Formatted string representation.
        """
        if fmt == ExplanationFormat.JSON:
            import json

            return json.dumps(explanation.to_dict(), indent=2, default=str)
        if fmt == ExplanationFormat.MARKDOWN:
            return self._render_markdown(explanation)
        return self._render_text(explanation)

    def batch_explain(
        self,
        decisions: list[dict[str, Any]],
        *,
        detail: ExplanationDetail = ExplanationDetail.STANDARD,
    ) -> list[DecisionExplanation]:
        """Explain multiple decisions at once.

        Each item in *decisions* should be a dict with keys matching the
        keyword arguments of :meth:`explain` (minus ``detail``).

        Returns:
            List of :class:`DecisionExplanation` objects in the same order.
        """
        results: list[DecisionExplanation] = []
        for dec in decisions:
            results.append(
                self.explain(
                    decision_id=dec.get("decision_id", ""),
                    outcome=dec.get("outcome", "unknown"),
                    triggered_rules=dec.get("triggered_rules", []),
                    input_text=dec.get("input_text", ""),
                    context=dec.get("context"),
                    detail=detail,
                )
            )
        return results

    def history(
        self,
        *,
        outcome_filter: str | None = None,
        limit: int | None = None,
    ) -> list[DecisionExplanation]:
        """Return stored explanation history.

        Args:
            outcome_filter: If given, return only explanations with this outcome.
            limit: Maximum number of results (most recent first).

        Returns:
            List of :class:`DecisionExplanation` objects.
        """
        items = self._history
        if outcome_filter is not None:
            items = [e for e in items if e.outcome == outcome_filter]
        if limit is not None:
            items = items[-limit:]
        return items

    def summary_report(self) -> dict[str, Any]:
        """Return aggregate statistics over all stored explanations."""
        if not self._history:
            return {"total": 0}

        outcome_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}
        total_blocked = 0
        total_warned = 0

        for exp in self._history:
            outcome_counts[exp.outcome] = outcome_counts.get(exp.outcome, 0) + 1
            for cat in exp.categories_triggered:
                category_counts[cat] = category_counts.get(cat, 0) + 1
            if exp.is_blocked:
                total_blocked += 1
            if exp.has_warnings:
                total_warned += 1

        return {
            "total": len(self._history),
            "outcome_counts": outcome_counts,
            "category_counts": category_counts,
            "total_blocked": total_blocked,
            "total_warned": total_warned,
        }

    def clear_history(self) -> int:
        """Clear the stored explanation history. Returns count cleared."""
        count = len(self._history)
        self._history.clear()
        return count

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_summary(
        self,
        outcome: str,
        blocking: list[RuleSummary],
        warning: list[RuleSummary],
    ) -> str:
        if not blocking and not warning:
            return f"Decision: {outcome} — no governance rules triggered."
        if blocking:
            severities = ", ".join(
                dict.fromkeys(self._SEVERITY_LANGUAGE.get(r.severity, r.severity) for r in blocking)
            )
            cats = ", ".join(dict.fromkeys(r.category for r in blocking))
            return (
                f"Decision: {outcome} — {len(blocking)} blocking rule(s) triggered "
                f"({severities} concern(s) in {cats})."
            )
        return (
            f"Decision: {outcome} — {len(warning)} warning rule(s) triggered; "
            "action permitted with caution."
        )

    def _build_rationale(
        self,
        outcome: str,
        blocking: list[RuleSummary],
        warning: list[RuleSummary],
        input_text: str,
        context: dict[str, Any] | None,
    ) -> str:
        agent = (context or {}).get("agent_id", "The requesting agent")
        parts: list[str] = []

        if blocking:
            rule_descs = "; ".join(f'"{r.description}"' for r in blocking[:3])
            if len(blocking) > 3:
                rule_descs += f" (and {len(blocking) - 3} more)"
            parts.append(
                f"{agent} issued a request that matched {len(blocking)} blocking governance "
                f"rule(s): {rule_descs}."
            )
            top = blocking[0]
            severity_word = self._SEVERITY_LANGUAGE.get(top.severity, top.severity)
            parts.append(
                f"The highest-severity match (rule '{top.rule_id}', severity={top.severity}) "
                f"indicates a {severity_word} violation in the '{top.category}' category, "
                f"triggering the '{top.workflow_action}' enforcement action."
            )
            if any(r.matched_keywords for r in blocking):
                kws = list(dict.fromkeys(k for r in blocking for k in r.matched_keywords))[:5]
                parts.append(f"Matched governance keywords: {', '.join(kws)}.")
        elif warning:
            parts.append(
                f"{agent}'s request raised {len(warning)} governance warning(s)"
                " but was not blocked."
            )
            cats = ", ".join(dict.fromkeys(r.category for r in warning))
            parts.append(f"Warning categories: {cats}. The request was permitted with monitoring.")
        else:
            parts.append(
                f"{agent}'s request passed all governance checks without any rule matches."
            )

        return " ".join(parts)

    def _build_remediation(
        self,
        blocking: list[RuleSummary],
        warning: list[RuleSummary],
        input_text: str,
        detail: ExplanationDetail,
    ) -> list[str]:
        if not blocking and not warning:
            return []

        hints: list[str] = []

        for rule in blocking[:3]:
            action = rule.workflow_action
            cat = rule.category
            if action in ("block", "deny"):
                hints.append(
                    f"Rule '{rule.rule_id}' ({cat}): Revise the request to remove "
                    f"{cat}-sensitive content, or seek explicit approval"
                    " from a governance authority."
                )
            elif action in ("quarantine", "reject"):
                hints.append(
                    f"Rule '{rule.rule_id}' ({cat}): The request has been quarantined. "
                    "Contact your compliance officer to review and release if appropriate."
                )

        for rule in warning[:2]:
            hints.append(
                f"Rule '{rule.rule_id}' ({rule.category}): Proceed with caution — "
                f"this action is flagged for '{rule.workflow_action}' monitoring."
            )

        if detail == ExplanationDetail.BRIEF:
            return hints[:1]
        return hints

    @staticmethod
    def _estimate_confidence(blocking: list[RuleSummary], warning: list[RuleSummary]) -> float:
        if not blocking and not warning:
            return 1.0
        high_sev = sum(1 for r in blocking if r.severity in ("critical", "high"))
        if high_sev:
            return 1.0
        if blocking:
            return 0.95
        return 0.85

    def _render_text(self, exp: DecisionExplanation) -> str:
        lines: list[str] = [
            f"[{exp.decision_id}] {exp.summary}",
            "",
            exp.rationale,
        ]
        if exp.remediation_hints:
            lines += ["", "Remediation:"]
            for hint in exp.remediation_hints:
                lines.append(f"  • {hint}")
        if exp.categories_triggered:
            lines.append(f"\nCategories: {', '.join(exp.categories_triggered)}")
        if exp.tags_triggered:
            lines.append(f"Tags: {', '.join(exp.tags_triggered)}")
        return "\n".join(lines)

    def _render_markdown(self, exp: DecisionExplanation) -> str:
        outcome_emoji = "🚫" if exp.is_blocked else ("⚠️" if exp.has_warnings else "✅")
        lines: list[str] = [
            f"## {outcome_emoji} Governance Decision: `{exp.decision_id}`",
            "",
            f"**Outcome:** `{exp.outcome}`  ",
            f"**Summary:** {exp.summary}",
            "",
            "### Rationale",
            "",
            exp.rationale,
        ]
        if exp.blocking_rules:
            lines += ["", "### Blocking Rules", ""]
            for rule in exp.blocking_rules:
                kws = (
                    f" — keywords: `{', '.join(rule.matched_keywords)}`"
                    if rule.matched_keywords
                    else ""
                )
                lines.append(
                    f"- **{rule.rule_id}** ({rule.severity}/{rule.category}): "
                    f"{rule.description}{kws}"
                )
        if exp.warning_rules:
            lines += ["", "### Warning Rules", ""]
            for rule in exp.warning_rules:
                lines.append(
                    f"- **{rule.rule_id}** ({rule.severity}/{rule.category}): {rule.description}"
                )
        if exp.remediation_hints:
            lines += ["", "### Remediation", ""]
            for hint in exp.remediation_hints:
                lines.append(f"- {hint}")
        if exp.categories_triggered:
            lines += ["", f"**Categories:** {', '.join(exp.categories_triggered)}"]
        if exp.tags_triggered:
            lines.append(f"**Tags:** {', '.join(exp.tags_triggered)}")
        lines.append(f"\n*Confidence: {exp.confidence:.0%} | Detail: {exp.detail_level.value}*")
        return "\n".join(lines)
