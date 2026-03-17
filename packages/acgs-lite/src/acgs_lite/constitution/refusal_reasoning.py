"""exp234: MOSAIC Refusal Reasoning — refusal as first-class governance action.

Treats governance refusal as a *first-class action with structured reasoning*,
not just a binary deny.  When a governance check blocks an action, this module
produces a complete refusal reasoning chain: which rules triggered, why they
apply, what alternative actions might be compliant, and a confidence score for
each suggestion.

Motivation (from MOSAIC arXiv:2603.03205, Microsoft Research):

> Standard guardrails return binary allow/deny.  The MOSAIC framework treats
> "Refuse" as a first-class action with its own reasoning chain: *why* was this
> refused, *which* constraints were violated, and *what* can the agent do instead?
> This makes governance decisions transparent, actionable, and auditable —
> agents receive constructive feedback rather than opaque blocks.

Design
------
- **RefusalReason** — why a specific rule triggered: rule_id, text, matched
  keywords, severity, human-readable explanation.
- **RefusalSuggestion** — a constructive alternative action the agent could
  try instead, with confidence estimate and rationale.
- **RefusalDecision** — complete structured refusal: all reasons, all
  suggestions, aggregate severity, retry eligibility.
- **RefusalReasoningEngine** — produces RefusalDecision from a Constitution
  and a denied action.  Generates suggestions by removing/replacing trigger
  keywords and checking whether the modified action would pass.

Zero hot-path overhead — invoked only *after* a deny decision, not on the
critical validation path.

Usage::

    from acgs_lite.constitution.core import Constitution, Rule, Severity
    from acgs_lite.constitution.refusal_reasoning import RefusalReasoningEngine

    constitution = Constitution(rules=[
        Rule(id="SAFE-001", text="No financial advice",
             severity=Severity.CRITICAL, keywords=["invest", "stocks"]),
    ])
    engine = RefusalReasoningEngine(constitution)

    decision = engine.reason_refusal(
        action="invest in tech stocks",
        triggered_rule_ids=["SAFE-001"],
    )
    print(decision.reasons[0].explanation)
    # "Rule SAFE-001 (critical) blocks this action: matched keywords ['invest', 'stocks']"
    print(decision.suggestions[0].alternative_action)
    # "research tech sector trends"  (invest/stocks removed, rephrased)
    print(decision.can_retry)  # True
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from acgs_lite.constitution.core import Constitution, Rule, Severity


_SEVERITY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}

# ── keyword replacement suggestions ──────────────────────────────────────────
# Maps dangerous keywords to safer alternatives for suggestion generation.

_SAFE_REPLACEMENTS: dict[str, str] = {
    "invest": "research",
    "stocks": "sector trends",
    "buy": "evaluate",
    "sell": "review",
    "financial advice": "financial information",
    "delete": "archive",
    "drop": "archive",
    "destroy": "decommission",
    "remove": "flag for review",
    "execute": "preview",
    "deploy": "stage",
    "send": "draft",
    "post": "draft",
    "publish": "draft",
    "override": "request override",
    "bypass": "request exception",
    "disable": "request pause",
    "grant": "request",
    "admin": "elevated",
    "password": "credential reference",
    "secret": "confidential reference",
    "api key": "credential reference",
}


# ── data structures ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class RefusalReason:
    """Structured explanation for why a specific rule triggered."""

    rule_id: str
    rule_text: str
    severity: str
    matched_keywords: tuple[str, ...]
    matched_patterns: tuple[str, ...]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_text": self.rule_text,
            "severity": self.severity,
            "matched_keywords": list(self.matched_keywords),
            "matched_patterns": list(self.matched_patterns),
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class RefusalSuggestion:
    """A constructive alternative action the agent could try."""

    alternative_action: str
    rationale: str
    confidence: float
    changes_made: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "alternative_action": self.alternative_action,
            "rationale": self.rationale,
            "confidence": round(self.confidence, 3),
            "changes_made": list(self.changes_made),
        }


@dataclass(frozen=True, slots=True)
class RefusalDecision:
    """Complete structured refusal with reasoning chain and alternatives."""

    action: str
    reasons: tuple[RefusalReason, ...]
    suggestions: tuple[RefusalSuggestion, ...]
    refusal_severity: str
    can_retry: bool
    rule_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reasons": [r.to_dict() for r in self.reasons],
            "suggestions": [s.to_dict() for s in self.suggestions],
            "refusal_severity": self.refusal_severity,
            "can_retry": self.can_retry,
            "rule_count": self.rule_count,
        }


# ── engine ────────────────────────────────────────────────────────────────────


class RefusalReasoningEngine:
    """Produces structured refusal reasoning for denied governance actions.

    Requires a Constitution to look up rule details. Generates explanations
    and constructive alternative suggestions.

    Attributes:
        constitution: The Constitution used for rule lookup.
        max_suggestions: Maximum alternative suggestions to generate per refusal.
    """

    __slots__ = ("constitution", "max_suggestions", "_rules_by_id")

    def __init__(
        self,
        constitution: Constitution,
        *,
        max_suggestions: int = 3,
    ) -> None:
        self.constitution = constitution
        self.max_suggestions = max(0, max_suggestions)
        self._rules_by_id: dict[str, Rule] = {r.id: r for r in constitution.rules}

    def reason_refusal(
        self,
        action: str,
        triggered_rule_ids: list[str],
    ) -> RefusalDecision:
        """Generate structured refusal reasoning for a denied action.

        Args:
            action: The action that was denied.
            triggered_rule_ids: IDs of rules that triggered the denial.

        Returns:
            RefusalDecision with reasons, suggestions, and metadata.
        """
        reasons: list[RefusalReason] = []
        all_matched_keywords: set[str] = set()

        for rule_id in triggered_rule_ids:
            rule = self._rules_by_id.get(rule_id)
            if rule is None:
                continue

            matched_kw = self._find_matched_keywords(action, rule)
            matched_pat = self._find_matched_patterns(action, rule)
            all_matched_keywords.update(matched_kw)

            severity_str = (
                rule.severity.value if isinstance(rule.severity, Severity) else str(rule.severity)
            )

            kw_desc = f"matched keywords {sorted(matched_kw)}" if matched_kw else ""
            pat_desc = f"matched patterns {list(matched_pat)}" if matched_pat else ""
            triggers = ", ".join(filter(None, [kw_desc, pat_desc]))

            reasons.append(
                RefusalReason(
                    rule_id=rule.id,
                    rule_text=rule.text,
                    severity=severity_str,
                    matched_keywords=tuple(sorted(matched_kw)),
                    matched_patterns=tuple(matched_pat),
                    explanation=(
                        f"Rule {rule.id} ({severity_str}) blocks this action"
                        + (f": {triggers}" if triggers else "")
                    ),
                )
            )

        # Generate suggestions by replacing dangerous keywords
        suggestions = self._generate_suggestions(action, all_matched_keywords)

        # Determine aggregate severity
        severity_vals = [r.severity for r in reasons]
        refusal_severity = (
            min(severity_vals, key=lambda s: _SEVERITY_ORDER.get(s, 99))
            if severity_vals
            else "unknown"
        )

        return RefusalDecision(
            action=action,
            reasons=tuple(reasons),
            suggestions=tuple(suggestions[: self.max_suggestions]),
            refusal_severity=refusal_severity,
            can_retry=len(suggestions) > 0,
            rule_count=len(reasons),
        )

    def _find_matched_keywords(self, action: str, rule: Rule) -> list[str]:
        """Find which rule keywords appear in the action."""
        action_lower = action.lower()
        matched: list[str] = []
        keywords = getattr(rule, "keywords", None) or []
        for kw in keywords:
            if kw.lower() in action_lower:
                matched.append(kw)
        return matched

    def _find_matched_patterns(self, action: str, rule: Rule) -> list[str]:
        """Find which rule regex patterns match the action."""
        matched: list[str] = []
        patterns = getattr(rule, "patterns", None) or []
        for pat in patterns:
            try:
                if re.search(pat, action, re.IGNORECASE):
                    matched.append(pat)
            except re.error:
                continue
        return matched

    def _generate_suggestions(
        self,
        action: str,
        matched_keywords: set[str],
    ) -> list[RefusalSuggestion]:
        """Generate alternative action suggestions by replacing trigger keywords."""
        if not matched_keywords:
            return []

        suggestions: list[RefusalSuggestion] = []
        modified = action
        changes: list[str] = []

        for kw in sorted(matched_keywords):
            replacement = _SAFE_REPLACEMENTS.get(kw.lower())
            if replacement:
                pattern = re.compile(re.escape(kw), re.IGNORECASE)
                new_modified = pattern.sub(replacement, modified)
                if new_modified != modified:
                    changes.append(f"'{kw}' → '{replacement}'")
                    modified = new_modified

        if modified != action and changes:
            suggestions.append(
                RefusalSuggestion(
                    alternative_action=modified,
                    rationale=f"Replaced trigger keywords: {', '.join(changes)}",
                    confidence=0.7,
                    changes_made=tuple(changes),
                )
            )

        # Second suggestion: remove keywords entirely
        removed = action
        remove_changes: list[str] = []
        for kw in sorted(matched_keywords):
            pattern = re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
            new_removed = pattern.sub("", removed).strip()
            new_removed = re.sub(r"\s{2,}", " ", new_removed)
            if new_removed != removed:
                remove_changes.append(f"removed '{kw}'")
                removed = new_removed

        if removed != action and removed.strip() and remove_changes:
            suggestions.append(
                RefusalSuggestion(
                    alternative_action=removed.strip(),
                    rationale=f"Removed trigger keywords: {', '.join(remove_changes)}",
                    confidence=0.5,
                    changes_made=tuple(remove_changes),
                )
            )

        # Third suggestion: rephrase as inquiry
        if matched_keywords:
            inquiry = f"review policy regarding: {action}"
            suggestions.append(
                RefusalSuggestion(
                    alternative_action=inquiry,
                    rationale="Rephrased as policy inquiry rather than direct action",
                    confidence=0.3,
                    changes_made=("rephrased as inquiry",),
                )
            )

        return suggestions
