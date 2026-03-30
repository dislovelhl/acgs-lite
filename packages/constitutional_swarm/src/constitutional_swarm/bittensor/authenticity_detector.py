"""Authenticity Detector — Phase 4.

Validators assess whether a miner's judgment reflects genuine human
deliberation vs a superficial or AI-generated response.

Five dimensions (matching roadmap Phase 4 spec):
  1. Reasoning depth        25%  — substantive vs superficial analysis
  2. Stakeholder coverage   20%  — engages with all affected parties
  3. Constitutional consistency 20% — references rules, articles, frameworks
  4. Deliberative authenticity  20% — first-person reasoning, hedging, nuance
  5. Precedent compatibility    15% — acknowledges related past cases

Each dimension produces a score in [0.0, 1.0].
Overall authenticity_score = weighted sum.

Anti-gaming design (Phase 4 spec):
  • Combined with GovernanceManifold: no single miner accumulates
    disproportionate influence regardless of authenticity score
  • Score is one input to emission_weight, not the sole determinant
  • Heuristics are transparent and auditable — no black-box model

Roadmap: 08-subnet-implementation-roadmap.md § Phase 4
Q&A:     07-subnet-concept-qa-responses.md § 6 (Deliberative Authenticity)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from constitutional_swarm.bittensor.precedent_store import PrecedentStore


# ---------------------------------------------------------------------------
# Dimension definitions
# ---------------------------------------------------------------------------


class AuthenticityDimension(Enum):
    REASONING_DEPTH          = "reasoning_depth"
    STAKEHOLDER_COVERAGE     = "stakeholder_coverage"
    CONSTITUTIONAL_CONSISTENCY = "constitutional_consistency"
    DELIBERATIVE_AUTHENTICITY = "deliberative_authenticity"
    PRECEDENT_COMPATIBILITY  = "precedent_compatibility"


_DIMENSION_WEIGHTS: dict[AuthenticityDimension, float] = {
    AuthenticityDimension.REASONING_DEPTH:           0.25,
    AuthenticityDimension.STAKEHOLDER_COVERAGE:      0.20,
    AuthenticityDimension.CONSTITUTIONAL_CONSISTENCY: 0.20,
    AuthenticityDimension.DELIBERATIVE_AUTHENTICITY:  0.20,
    AuthenticityDimension.PRECEDENT_COMPATIBILITY:    0.15,
}


# ---------------------------------------------------------------------------
# Scoring signals
# ---------------------------------------------------------------------------

# Reasoning depth: logical connectives, qualifying language, trade-off language
_LOGICAL_CONNECTIVES = re.compile(
    r"\b(because|therefore|however|although|whereas|consequently|thus|hence|"
    r"since|given that|provided that|it follows|as a result)\b",
    re.IGNORECASE,
)
_QUALIFYING_PHRASES = re.compile(
    r"\b(in this context|given that|considering|taking into account|"
    r"in light of|on balance|weighing|this case|specifically here)\b",
    re.IGNORECASE,
)
_TRADEOFF_LANGUAGE = re.compile(
    r"\b(while|although|despite|even though|on the one hand|"
    r"on the other hand|outweighs|outweigh|trade-off|tension between|"
    r"balancing|must be weighed)\b",
    re.IGNORECASE,
)

# Stakeholder coverage
_STAKEHOLDER_REFS = re.compile(
    r"\b(data subject|affected part|third part|stakeholder|user|citizen|"
    r"regulator|operator|controller|processor|individual|people|persons|"
    r"community|public|patient|customer|employee|claimant|respondent)\b",
    re.IGNORECASE,
)

# Constitutional consistency: regulatory frameworks, articles, rules
_CONSTITUTIONAL_REFS = re.compile(
    r"\b(article\s+\d+|gdpr|eu\s+ai\s+act|echr|nist|iso\s+42001|"
    r"hipaa|fairness|transparency|safety|privacy|security|reliability|"
    r"efficiency|constitutional|governance|compliance|rule|principle)\b",
    re.IGNORECASE,
)
_RULE_CITATIONS = re.compile(
    r"\b(section|clause|paragraph|provision|requirement|obligation|"
    r"mandate|standard|criterion|regulation|directive|framework)\b",
    re.IGNORECASE,
)

# Deliberative authenticity: first-person reasoning, hedging, nuance
_FIRST_PERSON = re.compile(
    r"\b(I believe|my assessment|in my judgment|I consider|I find|"
    r"I conclude|my view|I reason|I weigh|having considered)\b",
    re.IGNORECASE,
)
_HEDGING = re.compile(
    r"\b(appears to|seems to|arguably|likely|it is possible|"
    r"may be|could be|suggests|indicates|tends to|on balance|"
    r"in my view|I would argue)\b",
    re.IGNORECASE,
)
_QUESTION_ACKNOWLEDGMENT = re.compile(
    r"\b(the (key|central|core|fundamental) (question|issue|tension|concern|"
    r"problem|challenge) is|the issue here is|what (matters|is at stake|"
    r"needs to be resolved))\b",
    re.IGNORECASE,
)

# AI-typical patterns (presence reduces authenticity score)
_AI_BULLET_LIST = re.compile(r"^\s*[-•*]\s+.+$", re.MULTILINE)
_AI_NUMBERED_LIST = re.compile(r"^\s*\d+\.\s+.+$", re.MULTILINE)
_AI_FORMULAIC_OPENERS = re.compile(
    r"^(certainly|absolutely|of course|great question|"
    r"I'?ll (help|explain|analyze|consider))\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Score dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DimensionScore:
    """Score for a single authenticity dimension."""

    dimension: AuthenticityDimension
    score: float            # 0.0 – 1.0
    weight: float
    evidence: str           # human-readable explanation

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight


@dataclass(frozen=True, slots=True)
class AuthenticityScore:
    """Composite authenticity score for a miner judgment."""

    overall: float                      # weighted sum, 0.0 – 1.0
    dimension_scores: tuple[DimensionScore, ...]
    judgment_word_count: int
    is_authentic: bool                  # overall >= threshold
    threshold: float
    flags: tuple[str, ...]              # notable signals (positive or negative)

    @property
    def as_dict(self) -> dict[str, Any]:
        return {
            "overall": round(self.overall, 3),
            "is_authentic": self.is_authentic,
            "threshold": self.threshold,
            "word_count": self.judgment_word_count,
            "dimensions": {
                ds.dimension.value: {
                    "score": round(ds.score, 3),
                    "weighted": round(ds.weighted_score, 3),
                    "evidence": ds.evidence,
                }
                for ds in self.dimension_scores
            },
            "flags": list(self.flags),
        }


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class AuthenticityDetector:
    """Scores a miner judgment for deliberative authenticity.

    Usage::

        detector = AuthenticityDetector(authenticity_threshold=0.55)

        score = detector.score(
            judgment="Privacy takes precedence in this case. "
                     "While the transparency concern is valid, "
                     "the data subject has not consented under Article 8 ECHR.",
            reasoning="I weigh the privacy interest heavily because...",
            precedent_store=store,            # optional
            query_vector=impact_vector,       # optional, for precedent compat
        )

        print(score.overall)        # e.g. 0.72
        print(score.is_authentic)   # True
        print(score.as_dict)        # full breakdown
    """

    def __init__(
        self,
        authenticity_threshold: float = 0.55,
        min_word_count: int = 30,
    ) -> None:
        self._threshold = authenticity_threshold
        self._min_words = min_word_count

    def score(
        self,
        judgment: str,
        reasoning: str = "",
        precedent_store: "PrecedentStore | None" = None,
        query_vector: dict[str, float] | None = None,
    ) -> AuthenticityScore:
        """Score a judgment + reasoning pair for authenticity.

        Args:
            judgment:       the miner's governance decision text
            reasoning:      the miner's written rationale (combined with judgment)
            precedent_store: optional — used for precedent_compatibility dim
            query_vector:   optional 7-vector — used with precedent_store

        Returns:
            AuthenticityScore with per-dimension breakdown and flags
        """
        full_text = f"{judgment}\n{reasoning}".strip()
        words = full_text.split()
        word_count = len(words)
        flags: list[str] = []

        dim_scores = [
            self._score_reasoning_depth(full_text, word_count, flags),
            self._score_stakeholder_coverage(full_text, flags),
            self._score_constitutional_consistency(full_text, flags),
            self._score_deliberative_authenticity(full_text, flags),
            self._score_precedent_compatibility(
                full_text, precedent_store, query_vector, flags
            ),
        ]

        overall = sum(ds.weighted_score for ds in dim_scores)
        return AuthenticityScore(
            overall=round(overall, 4),
            dimension_scores=tuple(dim_scores),
            judgment_word_count=word_count,
            is_authentic=overall >= self._threshold,
            threshold=self._threshold,
            flags=tuple(flags),
        )

    # ------------------------------------------------------------------
    # Dimension scorers
    # ------------------------------------------------------------------

    def _score_reasoning_depth(
        self,
        text: str,
        word_count: int,
        flags: list[str],
    ) -> DimensionScore:
        dim = AuthenticityDimension.REASONING_DEPTH
        signals = []
        score = 0.0

        # Word count contribution (0.0 – 0.40)
        wc_score = min(word_count / 200.0, 1.0) * 0.4
        score += wc_score
        if word_count < self._min_words:
            flags.append(f"low_word_count:{word_count}")
            signals.append(f"only {word_count} words")
        else:
            signals.append(f"{word_count} words")

        # Logical connectives (0.0 – 0.25)
        conns = len(_LOGICAL_CONNECTIVES.findall(text))
        conn_score = min(conns / 3.0, 1.0) * 0.25
        score += conn_score
        signals.append(f"{conns} logical connectives")

        # Qualifying phrases (0.0 – 0.20)
        quals = len(_QUALIFYING_PHRASES.findall(text))
        qual_score = min(quals / 2.0, 1.0) * 0.20
        score += qual_score

        # Trade-off language (0.0 – 0.15)
        trades = len(_TRADEOFF_LANGUAGE.findall(text))
        trade_score = min(trades / 2.0, 1.0) * 0.15
        score += trade_score
        if trades > 0:
            flags.append("tradeoff_language_present")

        return DimensionScore(
            dimension=dim,
            score=min(score, 1.0),
            weight=_DIMENSION_WEIGHTS[dim],
            evidence="; ".join(signals),
        )

    def _score_stakeholder_coverage(
        self,
        text: str,
        flags: list[str],
    ) -> DimensionScore:
        dim = AuthenticityDimension.STAKEHOLDER_COVERAGE
        refs = _STAKEHOLDER_REFS.findall(text)
        unique = len(set(r.lower() for r in refs))
        score = min(unique / 3.0, 1.0)
        if unique >= 2:
            flags.append(f"stakeholders_mentioned:{unique}")
        return DimensionScore(
            dimension=dim,
            score=score,
            weight=_DIMENSION_WEIGHTS[dim],
            evidence=f"{unique} unique stakeholder references",
        )

    def _score_constitutional_consistency(
        self,
        text: str,
        flags: list[str],
    ) -> DimensionScore:
        dim = AuthenticityDimension.CONSTITUTIONAL_CONSISTENCY
        const_refs = len(_CONSTITUTIONAL_REFS.findall(text))
        rule_cites = len(_RULE_CITATIONS.findall(text))
        total = const_refs + rule_cites * 2  # citations weighted more
        score = min(total / 6.0, 1.0)
        if const_refs > 0:
            flags.append(f"constitutional_refs:{const_refs}")
        return DimensionScore(
            dimension=dim,
            score=score,
            weight=_DIMENSION_WEIGHTS[dim],
            evidence=f"{const_refs} constitutional refs, {rule_cites} rule citations",
        )

    def _score_deliberative_authenticity(
        self,
        text: str,
        flags: list[str],
    ) -> DimensionScore:
        dim = AuthenticityDimension.DELIBERATIVE_AUTHENTICITY
        score = 0.0
        signals = []

        # Positive signals
        fp = len(_FIRST_PERSON.findall(text))
        hedge = len(_HEDGING.findall(text))
        qa = len(_QUESTION_ACKNOWLEDGMENT.findall(text))

        score += min(fp / 2.0, 1.0) * 0.35
        score += min(hedge / 3.0, 1.0) * 0.35
        score += min(qa / 1.0, 1.0) * 0.30

        signals.append(f"first-person:{fp}, hedging:{hedge}, framing:{qa}")

        # Penalties for AI-typical patterns
        bullet_count = len(_AI_BULLET_LIST.findall(text))
        numbered_count = len(_AI_NUMBERED_LIST.findall(text))
        formulaic = bool(_AI_FORMULAIC_OPENERS.search(text))

        if bullet_count >= 3 or numbered_count >= 3:
            penalty = 0.20
            score = max(0.0, score - penalty)
            flags.append("ai_list_pattern")
            signals.append(f"list_penalty:-{penalty}")
        if formulaic:
            penalty = 0.10
            score = max(0.0, score - penalty)
            flags.append("ai_formulaic_opener")

        return DimensionScore(
            dimension=dim,
            score=min(score, 1.0),
            weight=_DIMENSION_WEIGHTS[dim],
            evidence="; ".join(signals),
        )

    def _score_precedent_compatibility(
        self,
        text: str,
        precedent_store: "PrecedentStore | None",
        query_vector: dict[str, float] | None,
        flags: list[str],
    ) -> DimensionScore:
        dim = AuthenticityDimension.PRECEDENT_COMPATIBILITY

        if precedent_store is None or query_vector is None or precedent_store.size == 0:
            # No store available — neutral score
            return DimensionScore(
                dimension=dim,
                score=0.5,
                weight=_DIMENSION_WEIGHTS[dim],
                evidence="no precedent store available; neutral score",
            )

        result = precedent_store.retrieve(query_vector, k=3)
        if not result.matches:
            return DimensionScore(
                dimension=dim,
                score=0.5,
                weight=_DIMENSION_WEIGHTS[dim],
                evidence="no similar precedents found; neutral score",
            )

        top = result.top_match
        assert top is not None
        sim = top.similarity
        # High similarity to accepted precedent → high compatibility
        score = sim
        if sim >= 0.85:
            flags.append(f"precedent_match:{sim:.2f}")
        return DimensionScore(
            dimension=dim,
            score=score,
            weight=_DIMENSION_WEIGHTS[dim],
            evidence=f"top precedent similarity={sim:.3f} ({len(result.matches)} candidates)",
        )
