"""Defensive blue team for governance rule hardening.

Analyzes red team bypass results and generates rule patch recommendations.
Patches flow through AmendmentRecommender — never self-enacted.

MACI role: PROPOSER — recommends changes, cannot validate or execute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .red_team import RedTeamReport


@dataclass(slots=True)
class RulePatch:
    """A proposed change to harden a constitutional rule."""

    rule_id: str
    patch_type: str  # "add_keyword" | "add_pattern" | "new_rule" | "adjust_severity"
    proposed_changes: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)  # attack texts that motivated this
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "patch_type": self.patch_type,
            "proposed_changes": self.proposed_changes,
            "evidence": self.evidence,
            "confidence": self.confidence,
        }


class GovernanceBlueTeam:
    """Analyzes red team bypasses and generates hardening patches.

    Parameters
    ----------
    constitution:
        The ``Constitution`` object to defend.
    """

    def __init__(self, constitution: Any) -> None:
        self.constitution = constitution

    def analyze_bypasses(self, report: RedTeamReport) -> list[RulePatch]:
        """Analyze all successful bypasses and propose patches."""
        patches: list[RulePatch] = []

        for rule_id, results in report.results_by_rule.items():
            bypasses = [r for r in results if r.bypassed]
            if not bypasses:
                continue

            # Extract common patterns from bypass texts
            bypass_texts = [r.attack.input_text for r in bypasses]
            keywords = self._extract_candidate_keywords(bypass_texts)
            strategies = {r.attack.strategy for r in bypasses}

            if keywords:
                patches.append(
                    RulePatch(
                        rule_id=rule_id,
                        patch_type="add_keyword",
                        proposed_changes={"keywords_to_add": keywords},
                        evidence=bypass_texts[:5],
                        confidence=min(1.0, len(bypasses) / 10),
                    )
                )

            if "semantic_evasion" in strategies or "paraphrase" in strategies:
                patches.append(
                    RulePatch(
                        rule_id=rule_id,
                        patch_type="add_pattern",
                        proposed_changes={
                            "note": "Semantic evasion detected — consider regex patterns"
                        },
                        evidence=bypass_texts[:3],
                        confidence=0.5,
                    )
                )

            bypass_rate = len(bypasses) / len(results) if results else 0
            if bypass_rate > 0.5:
                patches.append(
                    RulePatch(
                        rule_id=rule_id,
                        patch_type="adjust_severity",
                        proposed_changes={"reason": f"High bypass rate ({bypass_rate:.0%})"},
                        evidence=bypass_texts[:3],
                        confidence=bypass_rate,
                    )
                )

        return patches

    def _extract_candidate_keywords(self, texts: list[str]) -> list[str]:
        """Extract frequently occurring words from bypass texts as keyword candidates."""
        from collections import Counter

        word_counts: Counter[str] = Counter()
        for text in texts:
            words = set(text.lower().split())
            # Filter out common stop words
            words -= {
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
                "i",
                "you",
                "he",
                "she",
                "we",
                "they",
            }
            word_counts.update(words)

        # Words appearing in >50% of bypass texts are candidates
        threshold = max(1, len(texts) // 2)
        return [
            word
            for word, count in word_counts.most_common(10)
            if count >= threshold and len(word) > 3
        ]


__all__ = ["GovernanceBlueTeam", "RulePatch"]
