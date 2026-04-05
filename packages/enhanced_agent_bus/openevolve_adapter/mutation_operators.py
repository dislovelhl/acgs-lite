"""LLM-guided mutation operators for constitutional rule evolution.

Each operator mutates a specific EVOLVABLE field of a rule while preserving
FROZEN fields (id, text, category). Operators use the LLMGovernanceJudge
protocol for intelligent mutations.

MACI role: PROPOSER — generates candidates, cannot verify or execute.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass
from typing import Any

from enhanced_agent_bus.adaptive_governance.llm_judge import LLMGovernanceJudge

# Fields that evolution MUST NOT modify
FROZEN_FIELDS: frozenset[str] = frozenset({"id", "text", "category"})

# Fields that evolution CAN modify
EVOLVABLE_FIELDS: frozenset[str] = frozenset(
    {
        "keywords",
        "patterns",
        "severity",
        "workflow_action",
        "tags",
        "priority",
        "condition",
    }
)


@dataclass(slots=True)
class MutationResult:
    """Result of applying a mutation operator to a rule."""

    rule_id: str
    operator: str
    field_changed: str
    old_value: Any
    new_value: Any
    description: str


class KeywordMutator:
    """Adds, removes, or refines keywords for a rule.

    Uses bypass evidence (from purple team) and LLM suggestions to
    propose keyword changes that reduce false negatives without
    increasing false positives.
    """

    def __init__(
        self,
        llm: LLMGovernanceJudge | None = None,
        *,
        max_additions: int = 3,
        rng_seed: int = 42,
    ) -> None:
        self.llm = llm
        self.max_additions = max_additions
        self._rng = random.Random(rng_seed)

    async def mutate(
        self,
        rule: dict[str, Any],
        *,
        bypass_evidence: list[str] | None = None,
    ) -> MutationResult:
        """Mutate keywords for a rule.

        If bypass_evidence is provided, extracts candidate keywords from
        the bypass texts. Otherwise uses LLM to suggest additions.
        """
        old_keywords = list(rule.get("keywords", []))
        new_keywords = list(old_keywords)

        if bypass_evidence:
            candidates = self._extract_from_evidence(bypass_evidence, old_keywords)
            additions = candidates[: self.max_additions]
            new_keywords.extend(additions)
        elif self.llm:
            suggestions = await self._llm_suggest(rule)
            new_keywords.extend(suggestions[: self.max_additions])
        else:
            # Random removal (exploration)
            if new_keywords and self._rng.random() < 0.3:
                removed = self._rng.choice(new_keywords)
                new_keywords.remove(removed)

        return MutationResult(
            rule_id=rule["id"],
            operator="keyword_mutation",
            field_changed="keywords",
            old_value=old_keywords,
            new_value=new_keywords,
            description=f"keywords: {len(old_keywords)} -> {len(new_keywords)}",
        )

    def _extract_from_evidence(
        self,
        evidence: list[str],
        existing: list[str],
    ) -> list[str]:
        """Extract frequent words from bypass evidence as keyword candidates."""
        from collections import Counter

        existing_lower = {k.lower() for k in existing}
        word_counts: Counter[str] = Counter()
        for text in evidence:
            words = {w.lower() for w in text.split() if len(w) > 3}
            words -= existing_lower
            words -= _STOP_WORDS
            word_counts.update(words)
        threshold = max(1, len(evidence) // 3)
        return [w for w, c in word_counts.most_common(10) if c >= threshold]

    async def _llm_suggest(self, rule: dict[str, Any]) -> list[str]:
        """Use LLM to suggest additional keywords."""
        if not self.llm:
            return []
        prompt = (
            f"Suggest 3 additional keywords for this governance rule:\n"
            f"Rule: {rule.get('text', '')}\n"
            f"Existing keywords: {rule.get('keywords', [])}\n"
            f"Return only the keywords, one per line."
        )
        judgment = await self.llm.evaluate(prompt, {"mode": "keyword_suggestion"}, None)
        return [
            line.strip().lower()
            for line in judgment.reasoning.split("\n")
            if line.strip() and len(line.strip()) > 2
        ][:3]


class PatternMutator:
    """Adds or refines regex patterns for a rule."""

    def __init__(self, llm: LLMGovernanceJudge | None = None) -> None:
        self.llm = llm

    async def mutate(
        self,
        rule: dict[str, Any],
        *,
        bypass_evidence: list[str] | None = None,
    ) -> MutationResult:
        old_patterns = list(rule.get("patterns", []))
        new_patterns = list(old_patterns)

        if self.llm and bypass_evidence:
            prompt = (
                "This governance rule was bypassed by these inputs:\n"
                + "\n".join(f"- {e[:200]}" for e in bypass_evidence[:5])
                + f"\n\nCurrent patterns: {old_patterns}\n"
                f"Suggest 1-2 regex patterns that would catch these bypasses. "
                f"Return only valid Python regex patterns, one per line."
            )
            judgment = await self.llm.evaluate(prompt, {"mode": "pattern_suggestion"}, None)
            for line in judgment.reasoning.split("\n"):
                pat = line.strip()
                if pat and len(pat) > 3 and pat not in new_patterns:
                    new_patterns.append(pat)
                    if len(new_patterns) - len(old_patterns) >= 2:
                        break

        return MutationResult(
            rule_id=rule["id"],
            operator="pattern_mutation",
            field_changed="patterns",
            old_value=old_patterns,
            new_value=new_patterns,
            description=f"patterns: {len(old_patterns)} -> {len(new_patterns)}",
        )


class SeverityMutator:
    """Shifts severity up or down one level."""

    _LEVELS = ["low", "medium", "high", "critical"]

    def __init__(self, *, rng_seed: int = 42) -> None:
        self._rng = random.Random(rng_seed)

    async def mutate(self, rule: dict[str, Any], **kwargs: Any) -> MutationResult:
        old_severity = rule.get("severity", "medium")
        if hasattr(old_severity, "value"):
            old_severity = old_severity.value
        idx = self._LEVELS.index(old_severity) if old_severity in self._LEVELS else 1
        direction = self._rng.choice([-1, 1])
        new_idx = max(0, min(len(self._LEVELS) - 1, idx + direction))
        new_severity = self._LEVELS[new_idx]

        return MutationResult(
            rule_id=rule["id"],
            operator="severity_mutation",
            field_changed="severity",
            old_value=old_severity,
            new_value=new_severity,
            description=f"severity: {old_severity} -> {new_severity}",
        )


def apply_mutation(rule_dict: dict[str, Any], mutation: MutationResult) -> dict[str, Any]:
    """Apply a mutation result to a rule dict, returning a new dict (immutable pattern)."""
    new_rule = copy.deepcopy(rule_dict)
    if mutation.field_changed in FROZEN_FIELDS:
        raise ValueError(f"Cannot mutate frozen field: {mutation.field_changed}")
    new_rule[mutation.field_changed] = mutation.new_value
    return new_rule


def verify_frozen_fields(original: dict[str, Any], mutated: dict[str, Any]) -> bool:
    """Verify that no frozen fields were changed."""
    for field_name in FROZEN_FIELDS:
        if original.get(field_name) != mutated.get(field_name):
            return False
    return True


_STOP_WORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "can",
        "shall",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "and",
        "but",
        "or",
        "nor",
        "not",
        "no",
        "so",
        "if",
        "then",
        "that",
        "this",
        "it",
        "its",
        "your",
        "their",
        "them",
    }
)


__all__ = [
    "EVOLVABLE_FIELDS",
    "FROZEN_FIELDS",
    "KeywordMutator",
    "MutationResult",
    "PatternMutator",
    "SeverityMutator",
    "apply_mutation",
    "verify_frozen_fields",
]
